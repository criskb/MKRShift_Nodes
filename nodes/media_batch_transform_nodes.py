import math
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageColor
import torch

from ..categories import MEDIA_AUDIO_FX, MEDIA_AUDIO_UTILITY, MEDIA_VIDEO_EDIT, MEDIA_VIDEO_FX, MEDIA_VIDEO_UTILITY
from .media_batch_video_nodes import (
    _build_video_payload,
    _decode_video_to_pil,
    _pil_to_tensor,
    _save_video_from_pil,
)
from .media_extra_nodes import _align_channels, _amp_from_db, _resample_waveform, _save_audio_waveform
from .media_io_nodes import (
    _atempo_chain,
    _audio_codec_args,
    _json_text,
    _make_audio_payload,
    _make_video_payload,
    _read_audio_duration,
    _read_video_metadata,
    _run_ffprobe_json,
)
from .presave_image_nodes import _output_dir, _resolve_output_file, _sanitize_basename, _temp_dir
from .presave_media_nodes import _extract_input_file, _extract_waveform, _ffmpeg_bin, _run_ffmpeg, _safe_ext


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _resolve_video_output_format(source: Optional[Path], requested: str, warnings: List[str]) -> str:
    fmt = _safe_ext(requested)
    if fmt == "auto":
        src_ext = _safe_ext(source.suffix) if source is not None else ""
        fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
    if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
        fmt = "gif"
        warnings.append("Unsupported video output format, using gif")
    if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
        fmt = "gif"
        warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
    return fmt


def _resolve_audio_output_format(source: Optional[Path], requested: str, warnings: List[str]) -> str:
    fmt = _safe_ext(requested)
    if fmt == "auto":
        src_ext = _safe_ext(source.suffix) if source is not None else ""
        fmt = src_ext if src_ext in {"wav", "mp3", "flac", "ogg"} else "wav"
    if fmt not in {"wav", "mp3", "flac", "ogg"}:
        fmt = "wav"
        warnings.append("Unsupported audio output format, using wav")
    if fmt != "wav" and not _ffmpeg_bin():
        fmt = "wav"
        warnings.append("ffmpeg is not available for encoded audio, using wav")
    return fmt


def _resolve_anchor_offset(space_w: int, space_h: int, content_w: int, content_h: int, anchor: str) -> Tuple[int, int]:
    dx = int(max(0, space_w - content_w))
    dy = int(max(0, space_h - content_h))
    a = str(anchor or "center").strip().lower()

    if "left" in a:
        x = 0
    elif "right" in a:
        x = dx
    else:
        x = dx // 2

    if "top" in a:
        y = 0
    elif "bottom" in a:
        y = dy
    else:
        y = dy // 2
    return int(x), int(y)


def _resolve_crop_offset(content_w: int, content_h: int, target_w: int, target_h: int, anchor: str) -> Tuple[int, int]:
    dx = int(max(0, content_w - target_w))
    dy = int(max(0, content_h - target_h))
    a = str(anchor or "center").strip().lower()

    if "left" in a:
        x = 0
    elif "right" in a:
        x = dx
    else:
        x = dx // 2

    if "top" in a:
        y = 0
    elif "bottom" in a:
        y = dy
    else:
        y = dy // 2
    return int(x), int(y)


def _parse_background_color(value: str) -> Tuple[int, int, int]:
    text = str(value or "").strip() or "#000000"
    try:
        color = ImageColor.getrgb(text)
        return int(color[0]), int(color[1]), int(color[2])
    except Exception:
        return 0, 0, 0


def _read_wav_waveform(path: Path) -> Tuple[Optional[np.ndarray], int, str]:
    try:
        with wave.open(str(path), "rb") as wf:
            channels = int(max(1, wf.getnchannels()))
            sample_width = int(wf.getsampwidth())
            sample_rate = int(max(1, wf.getframerate()))
            frame_count = int(max(0, wf.getnframes()))
            raw = wf.readframes(frame_count)
    except Exception as exc:
        return None, 0, str(exc)

    if sample_width == 1:
        mono = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        mono = (mono - 128.0) / 128.0
    elif sample_width == 2:
        mono = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 3:
        u8 = np.frombuffer(raw, dtype=np.uint8)
        if u8.size % 3 != 0:
            return None, sample_rate, "Invalid 24-bit wav frame size"
        triplets = u8.reshape(-1, 3)
        vals = (
            triplets[:, 0].astype(np.int32)
            | (triplets[:, 1].astype(np.int32) << 8)
            | (triplets[:, 2].astype(np.int32) << 16)
        )
        sign = vals & 0x800000
        vals = vals - (sign << 1)
        mono = vals.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        mono = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        return None, sample_rate, f"Unsupported wav sample width: {sample_width}"

    if mono.size == 0:
        return np.zeros((1, 1), dtype=np.float32), sample_rate, ""

    if mono.size % channels != 0:
        return None, sample_rate, "Wav sample count is not divisible by channel count"

    audio = mono.reshape(-1, channels).T.astype(np.float32, copy=False)
    return audio, sample_rate, ""


def _audio_sr_from_payload(audio: Any, source: Optional[Path], fallback: int = 44100) -> int:
    if isinstance(audio, dict):
        for key in ("sample_rate", "sr", "rate"):
            try:
                value = int(audio.get(key) or 0)
                if value > 0:
                    return int(value)
            except Exception:
                continue

    if source is not None:
        data, _ = _run_ffprobe_json(source)
        if isinstance(data, dict):
            streams = data.get("streams") if isinstance(data.get("streams"), list) else []
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                if str(stream.get("codec_type", "")).lower() != "audio":
                    continue
                try:
                    value = int(float(stream.get("sample_rate") or 0))
                    if value > 0:
                        return int(value)
                except Exception:
                    continue
    return int(max(1, fallback))


def _load_audio_waveform(audio: Any) -> Tuple[Optional[np.ndarray], int, Optional[Path], str]:
    source = _extract_input_file(audio)
    wave_data, wave_sr = _extract_waveform(audio)
    if wave_data is not None:
        return wave_data.astype(np.float32, copy=False), int(max(1, wave_sr)), source, ""

    if source is None:
        return None, 0, None, "No audio source found"

    ext = _safe_ext(source.suffix)
    if ext == "wav":
        wave_arr, sr, err = _read_wav_waveform(source)
        return wave_arr, int(sr), source, str(err)

    if not _ffmpeg_bin():
        return None, 0, source, "ffmpeg is required to decode non-wav audio"

    temp_root = _temp_dir()
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=str(temp_root), prefix="mkr_audio_decode_") as tmp:
        tmp_path = Path(tmp)
        wav_path = tmp_path / "decoded.wav"
        ok, error = _run_ffmpeg(["-y", "-i", str(source), "-vn", "-acodec", "pcm_s16le", str(wav_path)])
        if not ok:
            return None, 0, source, f"ffmpeg decode failed: {error}"
        wave_arr, sr, err = _read_wav_waveform(wav_path)
        return wave_arr, int(sr), source, str(err)


def _target_channels(waveform: np.ndarray, mode: str) -> np.ndarray:
    m = str(mode or "keep").strip().lower()
    if m == "mono":
        if waveform.shape[0] == 1:
            return waveform
        mono = np.mean(waveform, axis=0, keepdims=True, dtype=np.float32)
        return mono.astype(np.float32, copy=False)
    if m == "stereo":
        if waveform.shape[0] == 2:
            return waveform
        if waveform.shape[0] == 1:
            return np.repeat(waveform, 2, axis=0)
        return waveform[:2, :]
    return waveform


def _safe_duration_sec(waveform: np.ndarray, sample_rate: int) -> float:
    if waveform is None:
        return 0.0
    if waveform.ndim != 2:
        return 0.0
    return float(waveform.shape[1] / float(max(1, int(sample_rate))))


def _save_audio_result(
    waveform: np.ndarray,
    sample_rate: int,
    source: Optional[Path],
    output_format: str,
    filename_prefix: str,
    filename_label: str,
    subfolder: str,
    overwrite: bool,
    warnings: List[str],
) -> Tuple[Dict[str, Any], str, float, str]:
    out_dir = _output_dir(subfolder)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = _resolve_audio_output_format(source, output_format, warnings)
    stem = _sanitize_basename(filename_label or filename_prefix, filename_prefix)
    target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

    clipped = np.clip(waveform.astype(np.float32, copy=False), -1.0, 1.0)
    ok, error = _save_audio_waveform(clipped, sample_rate=int(max(1, sample_rate)), target=target, ext=fmt)
    if not ok:
        warnings.append(f"Failed to save audio: {error}")
        payload = _make_audio_payload(path=source, sample_rate=int(max(1, sample_rate)))
        payload["waveform"] = torch.from_numpy(clipped)
        return payload, "", _safe_duration_sec(clipped, sample_rate), _json_text({"warnings": warnings})

    payload = _make_audio_payload(path=target, sample_rate=int(max(1, sample_rate)))
    payload["waveform"] = torch.from_numpy(clipped)
    duration = _safe_duration_sec(clipped, sample_rate)
    summary = {
        "output_path": str(target),
        "sample_rate": int(max(1, sample_rate)),
        "channels": int(clipped.shape[0]),
        "duration_sec": round(float(duration), 6),
        "warnings": warnings,
    }
    return payload, str(target), float(duration), _json_text(summary)


def _atempo_filters(speed: float) -> List[str]:
    chain = _atempo_chain(float(max(0.01, speed)))
    return [p for p in chain.split(",") if p.strip()]


class MKRVideoRotateFlip:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "rotate_degrees": (["0", "90", "180", "270"], {"default": "0"}),
                "flip_horizontal": ("BOOLEAN", {"default": False}),
                "flip_vertical": ("BOOLEAN", {"default": False}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_rotate_flip"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_UTILITY

    def run(
        self,
        video: Any,
        rotate_degrees: str = "0",
        flip_horizontal: bool = False,
        flip_vertical: bool = False,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_rotate_flip",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        deg = int(str(rotate_degrees or "0").strip())
        out_frames: List[Image.Image] = []
        for frame in frames:
            img = frame.convert("RGB")
            if deg == 90:
                img = img.transpose(Image.Transpose.ROTATE_90)
            elif deg == 180:
                img = img.transpose(Image.Transpose.ROTATE_180)
            elif deg == 270:
                img = img.transpose(Image.Transpose.ROTATE_270)
            if bool(flip_horizontal):
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if bool(flip_vertical):
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            out_frames.append(img)

        fmt = _resolve_video_output_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_rotate_flip")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "rotation": int(deg),
            "flip_horizontal": bool(flip_horizontal),
            "flip_vertical": bool(flip_vertical),
            "frame_count": int(len(out_frames)),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoResizePad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "target_width": ("INT", {"default": 1280, "min": 16, "max": 8192, "step": 1}),
                "target_height": ("INT", {"default": 720, "min": 16, "max": 8192, "step": 1}),
                "fit_mode": (["contain", "cover", "stretch"], {"default": "contain"}),
                "anchor": (
                    [
                        "center",
                        "top",
                        "bottom",
                        "left",
                        "right",
                        "top_left",
                        "top_right",
                        "bottom_left",
                        "bottom_right",
                    ],
                    {"default": "center"},
                ),
                "background_color": ("STRING", {"default": "#000000"}),
                "resample": (["bicubic", "bilinear", "lanczos", "nearest"], {"default": "bicubic"}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_resize_pad"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_UTILITY

    def run(
        self,
        video: Any,
        target_width: int = 1280,
        target_height: int = 720,
        fit_mode: str = "contain",
        anchor: str = "center",
        background_color: str = "#000000",
        resample: str = "bicubic",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_resize_pad",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        tw = int(max(16, target_width))
        th = int(max(16, target_height))
        bg = _parse_background_color(background_color)

        resample_mode = {
            "nearest": Image.Resampling.NEAREST,
            "bilinear": Image.Resampling.BILINEAR,
            "lanczos": Image.Resampling.LANCZOS,
            "bicubic": Image.Resampling.BICUBIC,
        }.get(str(resample or "bicubic").strip().lower(), Image.Resampling.BICUBIC)

        out_frames: List[Image.Image] = []
        mode = str(fit_mode or "contain").strip().lower()
        for frame in frames:
            src = frame.convert("RGB")
            sw, sh = src.size
            if mode == "stretch":
                out_frames.append(src.resize((tw, th), resample=resample_mode))
                continue

            if mode == "cover":
                scale = max(float(tw) / float(max(1, sw)), float(th) / float(max(1, sh)))
                nw = max(1, int(round(sw * scale)))
                nh = max(1, int(round(sh * scale)))
                tmp = src.resize((nw, nh), resample=resample_mode)
                cx, cy = _resolve_crop_offset(nw, nh, tw, th, anchor)
                out_frames.append(tmp.crop((cx, cy, cx + tw, cy + th)))
                continue

            scale = min(float(tw) / float(max(1, sw)), float(th) / float(max(1, sh)))
            nw = max(1, int(round(sw * scale)))
            nh = max(1, int(round(sh * scale)))
            tmp = src.resize((nw, nh), resample=resample_mode)
            canvas = Image.new("RGB", (tw, th), bg)
            px, py = _resolve_anchor_offset(tw, th, nw, nh, anchor)
            canvas.paste(tmp, (int(px), int(py)))
            out_frames.append(canvas)

        fmt = _resolve_video_output_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_resize_pad")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "target_resolution": f"{int(tw)}x{int(th)}",
            "fit_mode": mode,
            "anchor": str(anchor),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoPingPong:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "loop_count": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "include_end_frames": ("BOOLEAN", {"default": False}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_pingpong_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        loop_count: int = 2,
        include_end_frames: bool = False,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_pingpong_video",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        loop_n = int(max(1, loop_count))
        base = [f.copy() for f in frames]
        if len(base) <= 1:
            cycle = base
        elif bool(include_end_frames):
            cycle = base + list(reversed(base))
        else:
            cycle = base + list(reversed(base[1:-1]))

        out_frames: List[Image.Image] = []
        for _ in range(loop_n):
            out_frames.extend(cycle)

        fmt = _resolve_video_output_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_pingpong_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "input_frames": int(len(base)),
            "output_frames": int(len(out_frames)),
            "loop_count": int(loop_n),
            "include_end_frames": bool(include_end_frames),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoTemporalBlend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "blend_window": ("INT", {"default": 3, "min": 1, "max": 16, "step": 1}),
                "blend_strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mode": (["mean", "motion_trail"], {"default": "mean"}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_temporal_blend"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_FX

    def run(
        self,
        video: Any,
        blend_window: int = 3,
        blend_strength: float = 0.5,
        mode: str = "mean",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_temporal_blend",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        window = int(max(1, blend_window))
        strength = _clamp_float(blend_strength, 0.0, 1.0)
        m = str(mode or "mean").strip().lower()
        arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]

        out_frames: List[Image.Image] = []
        for idx, current in enumerate(arrs):
            if window <= 1 or strength <= 1e-6:
                out_frames.append(Image.fromarray(np.clip(current, 0.0, 255.0).astype(np.uint8), mode="RGB"))
                continue
            start = max(0, idx - window + 1)
            history = arrs[start : idx + 1]
            if m == "motion_trail":
                count = len(history)
                weights = np.linspace(0.2, 1.0, num=count, dtype=np.float32)
                weights /= np.sum(weights)
                stacked = np.stack(history, axis=0)
                mixed = np.sum(stacked * weights[:, None, None, None], axis=0)
            else:
                mixed = np.mean(np.stack(history, axis=0), axis=0)
            out = current * (1.0 - strength) + mixed * strength
            out_frames.append(Image.fromarray(np.clip(out, 0.0, 255.0).astype(np.uint8), mode="RGB"))

        fmt = _resolve_video_output_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_temporal_blend")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "blend_window": int(window),
            "blend_strength": float(strength),
            "mode": m,
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoPosterize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "levels": ("INT", {"default": 8, "min": 2, "max": 64, "step": 1}),
                "dither": ("BOOLEAN", {"default": False}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_posterize_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_FX

    def run(
        self,
        video: Any,
        levels: int = 8,
        dither: bool = False,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_posterize_video",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        lv = _clamp_int(levels, 2, 64)
        step = 255.0 / float(max(1, lv - 1))
        out_frames: List[Image.Image] = []
        for frame in frames:
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
            if bool(dither):
                noise = np.random.uniform(-0.5 * step, 0.5 * step, size=arr.shape).astype(np.float32)
                arr = arr + noise
            arr = np.round(arr / step) * step
            out_frames.append(Image.fromarray(np.clip(arr, 0.0, 255.0).astype(np.uint8), mode="RGB"))

        fmt = _resolve_video_output_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_posterize_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "levels": int(lv),
            "dither": bool(dither),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRAudioResampleConvert:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "target_sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000, "step": 1}),
                "target_channels": (["keep", "mono", "stereo"], {"default": "keep"}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_resample"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        target_sample_rate: int = 48000,
        target_channels: str = "keep",
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_resample",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

        dst_sr = int(max(8000, target_sample_rate))
        tuned = _target_channels(waveform.astype(np.float32, copy=False), target_channels)
        if sample_rate != dst_sr:
            tuned = _resample_waveform(tuned, int(sample_rate), int(dst_sr)).astype(np.float32, copy=False)

        return _save_audio_result(
            waveform=tuned,
            sample_rate=dst_sr,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )


class MKRAudioSilenceTrim:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "threshold_db": ("FLOAT", {"default": -45.0, "min": -90.0, "max": 0.0, "step": 0.1}),
                "min_silence_ms": ("INT", {"default": 120, "min": 0, "max": 10000, "step": 1}),
                "trim_start": ("BOOLEAN", {"default": True}),
                "trim_end": ("BOOLEAN", {"default": True}),
                "pad_ms": ("INT", {"default": 0, "min": 0, "max": 5000, "step": 1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_trim_silence"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        threshold_db: float = -45.0,
        min_silence_ms: int = 120,
        trim_start: bool = True,
        trim_end: bool = True,
        pad_ms: int = 0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_trim_silence",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

        w = waveform.astype(np.float32, copy=False)
        samples = int(w.shape[1])
        if samples <= 1:
            return _save_audio_result(
                waveform=w,
                sample_rate=sample_rate,
                source=source,
                output_format=output_format,
                filename_prefix=filename_prefix,
                filename_label=filename_label,
                subfolder=subfolder,
                overwrite=overwrite,
                warnings=warnings,
            )

        threshold = float(max(0.0, min(1.0, 10.0 ** (float(threshold_db) / 20.0))))
        envelope = np.max(np.abs(w), axis=0)
        active = envelope > threshold
        min_samples = int(max(0, round(float(max(0, min_silence_ms)) * float(sample_rate) / 1000.0)))
        pad_samples = int(max(0, round(float(max(0, pad_ms)) * float(sample_rate) / 1000.0)))

        if not np.any(active):
            warnings.append("Entire audio appears below threshold; returning original")
            trimmed = w
        else:
            start_idx = int(np.argmax(active))
            end_idx = int(samples - np.argmax(active[::-1]))
            leading = int(start_idx)
            trailing = int(samples - end_idx)

            start = 0
            end = samples
            if bool(trim_start) and leading >= min_samples:
                start = int(max(0, start_idx - pad_samples))
            if bool(trim_end) and trailing >= min_samples:
                end = int(min(samples, end_idx + pad_samples))
            if end <= start:
                trimmed = np.zeros((w.shape[0], 1), dtype=np.float32)
                warnings.append("Trim would remove all content; outputting short silence")
            else:
                trimmed = w[:, start:end]

        return _save_audio_result(
            waveform=trimmed,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )


class MKRAudioGainPan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "gain_db": ("FLOAT", {"default": 0.0, "min": -60.0, "max": 24.0, "step": 0.1}),
                "pan": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "force_stereo": ("BOOLEAN", {"default": False}),
                "normalize_peak": ("BOOLEAN", {"default": False}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_gain_pan"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        gain_db: float = 0.0,
        pan: float = 0.0,
        force_stereo: bool = False,
        normalize_peak: bool = False,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_gain_pan",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

        w = waveform.astype(np.float32, copy=False).copy()
        gain = float(_amp_from_db(gain_db))
        pan_v = _clamp_float(pan, -1.0, 1.0)

        if w.shape[0] == 1:
            mono = w[0] * gain
            if bool(force_stereo) or abs(pan_v) > 1e-6:
                angle = float((pan_v + 1.0) * (math.pi / 4.0))
                left = float(math.cos(angle) * math.sqrt(2.0))
                right = float(math.sin(angle) * math.sqrt(2.0))
                w = np.stack([mono * left, mono * right], axis=0).astype(np.float32, copy=False)
            else:
                w[0] = mono
        else:
            w *= gain
            if abs(pan_v) > 1e-6:
                angle = float((pan_v + 1.0) * (math.pi / 4.0))
                left = float(math.cos(angle) * math.sqrt(2.0))
                right = float(math.sin(angle) * math.sqrt(2.0))
                w[0] *= left
                w[1] *= right
            if bool(force_stereo) and w.shape[0] != 2:
                w = _align_channels(w, 2).astype(np.float32, copy=False)

        if bool(normalize_peak):
            peak = float(np.max(np.abs(w)))
            if peak > 1e-9:
                w *= float(0.98 / peak)
        w = np.clip(w, -1.0, 1.0)

        return _save_audio_result(
            waveform=w,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )


class MKRAudioLimiter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "threshold_db": ("FLOAT", {"default": -1.0, "min": -24.0, "max": 0.0, "step": 0.1}),
                "ceiling_db": ("FLOAT", {"default": -0.5, "min": -24.0, "max": 0.0, "step": 0.1}),
                "release_ms": ("FLOAT", {"default": 50.0, "min": 1.0, "max": 1000.0, "step": 0.1}),
                "makeup_db": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "soft_clip": ("BOOLEAN", {"default": False}),
                "normalize_peak": ("BOOLEAN", {"default": False}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_limiter"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_FX

    def run(
        self,
        audio: Any,
        threshold_db: float = -1.0,
        ceiling_db: float = -0.5,
        release_ms: float = 50.0,
        makeup_db: float = 0.0,
        soft_clip: bool = False,
        normalize_peak: bool = False,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_limiter",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

        w = waveform.astype(np.float32, copy=False)
        threshold = float(max(1e-6, 10.0 ** (float(threshold_db) / 20.0)))
        ceiling = float(max(1e-6, 10.0 ** (float(ceiling_db) / 20.0)))
        rel_samples = max(1, int(round(float(max(1.0, release_ms)) * float(sample_rate) / 1000.0)))
        release_coeff = float(math.exp(-1.0 / float(rel_samples)))

        out = np.empty_like(w)
        env = 0.0
        for i in range(w.shape[1]):
            peak = float(np.max(np.abs(w[:, i])))
            env = max(peak, (env * release_coeff) + (peak * (1.0 - release_coeff)))
            gain = 1.0 if env <= threshold else float(threshold / max(1e-9, env))
            out[:, i] = w[:, i] * gain

        out *= float(_amp_from_db(makeup_db))
        if bool(soft_clip):
            out = (np.tanh(out / ceiling) * ceiling).astype(np.float32, copy=False)
        else:
            out = np.clip(out, -ceiling, ceiling)
        if bool(normalize_peak):
            peak = float(np.max(np.abs(out)))
            if peak > 1e-9:
                out *= float(ceiling / peak)
        out = np.clip(out, -ceiling, ceiling)

        return _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )


class MKRAudioTempoPitch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "tempo": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 4.0, "step": 0.01}),
                "pitch_semitones": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_tempo_pitch"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_FX

    def run(
        self,
        audio: Any,
        tempo: float = 1.0,
        pitch_semitones: float = 0.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_tempo_pitch",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        tempo_v = float(max(0.25, min(4.0, tempo)))
        semi_v = float(max(-24.0, min(24.0, pitch_semitones)))
        source = _extract_input_file(audio)
        fmt = _resolve_audio_output_format(source, output_format, warnings)

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_audio_tempo_pitch")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        if _ffmpeg_bin() and source is not None:
            src_sr = _audio_sr_from_payload(audio, source=source, fallback=44100)
            pitch_factor = float(2.0 ** (semi_v / 12.0))
            filters: List[str] = []

            if abs(semi_v) > 1e-6:
                filters.append(f"asetrate={int(src_sr)}*{pitch_factor:.8f}")
                filters.append(f"aresample={int(src_sr)}")
                filters.extend(_atempo_filters(1.0 / pitch_factor))

            if abs(tempo_v - 1.0) > 1e-6:
                filters.extend(_atempo_filters(tempo_v))

            chain = ",".join(filters) if filters else "anull"
            codec = _audio_codec_args(fmt)
            if codec is None:
                warnings.append(f"Unsupported codec for format '{fmt}'")
                return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

            ok, error = _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    str(source),
                    "-filter:a",
                    chain,
                    *codec,
                    str(target),
                ]
            )
            if ok:
                payload = _make_audio_payload(path=target)
                duration = _read_audio_duration(target)
                summary = {
                    "output_path": str(target),
                    "mode": "ffmpeg",
                    "tempo": float(tempo_v),
                    "pitch_semitones": float(semi_v),
                    "warnings": warnings,
                }
                return (payload, str(target), float(duration), _json_text(summary))
            warnings.append(f"ffmpeg tempo/pitch processing failed: {error}")

        waveform, sample_rate, source2, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_make_audio_payload(path=source or source2), "", 0.0, _json_text({"warnings": warnings}))

        # Fallback is tape-style resample. Pitch and tempo both change together here.
        tape_factor = float(tempo_v * (2.0 ** (semi_v / 12.0)))
        if abs(semi_v) > 1e-6 and not _ffmpeg_bin():
            warnings.append("ffmpeg unavailable: using tape-style fallback where pitch also changes tempo")

        src_len = int(waveform.shape[1])
        out_len = int(max(1, round(float(src_len) / max(0.01, tape_factor))))
        x_old = np.linspace(0.0, 1.0, num=src_len, endpoint=False, dtype=np.float64)
        x_new = np.linspace(0.0, 1.0, num=out_len, endpoint=False, dtype=np.float64)
        out = np.zeros((waveform.shape[0], out_len), dtype=np.float32)
        for ch in range(waveform.shape[0]):
            out[ch] = np.interp(x_new, x_old, waveform[ch].astype(np.float64)).astype(np.float32)
        out = np.clip(out, -1.0, 1.0)

        return _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source or source2,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
