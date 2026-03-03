import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageSequence
import torch

from ..categories import MEDIA_IO, MEDIA_TIMELINE, MEDIA_VIDEO_EDIT
from ..xmedia_nodes import (
    _json_text,
    _make_audio_payload,
    _make_video_payload,
    _read_video_metadata,
    _run_ffprobe_json,
)
from ..xpresave import _image_batch_to_pil, _output_dir, _resolve_output_file, _sanitize_basename, _save_animation, _save_still_image, _temp_dir
from ..xpresave_media import (
    _extract_input_file,
    _extract_video_frames,
    _extract_waveform,
    _ffmpeg_bin,
    _run_ffmpeg,
    _safe_ext,
    _save_frames_with_ffmpeg,
)


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _pil_to_tensor(frames: Sequence[Image.Image]) -> torch.Tensor:
    if not frames:
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    arr = np.stack([
        np.asarray(frame.convert("RGB"), dtype=np.uint8).astype(np.float32) / 255.0
        for frame in frames
    ], axis=0)
    return torch.from_numpy(arr).float().clamp(0.0, 1.0)


def _normalize_markers_json(raw: str) -> List[float]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    values: List[float] = []
    if isinstance(parsed, list):
        for item in parsed:
            try:
                values.append(float(item))
            except Exception:
                continue
        return values

    # Fallback: line/comma/semicolon split.
    chunks = text.replace(";", "\n").replace(",", "\n").splitlines()
    for chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        try:
            values.append(float(c))
        except Exception:
            continue
    return values


def _normalize_ramp_points(raw: str, total_frames: int) -> List[Tuple[int, float]]:
    text = str(raw or "").strip()
    if not text:
        return [(0, 1.0), (max(0, int(total_frames) - 1), 1.0)]

    points: List[Tuple[int, float]] = []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            frame = item.get("frame", item.get("index", 0))
            speed = item.get("speed", 1.0)
            try:
                fi = int(frame)
                sp = float(speed)
            except Exception:
                continue
            points.append((fi, max(0.01, sp)))

    if not points:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.replace(";", ",").split(",") if p.strip()]
            if len(parts) < 2:
                continue
            try:
                fi = int(float(parts[0]))
                sp = float(parts[1])
            except Exception:
                continue
            points.append((fi, max(0.01, sp)))

    if not points:
        points = [(0, 1.0)]

    points = sorted(points, key=lambda x: x[0])
    first_frame = max(0, points[0][0])
    if first_frame > 0:
        points.insert(0, (0, points[0][1]))

    last_target = max(0, int(total_frames) - 1)
    if points[-1][0] < last_target:
        points.append((last_target, points[-1][1]))

    out: List[Tuple[int, float]] = []
    for fi, sp in points:
        out.append((_clamp_int(fi, 0, last_target), max(0.01, float(sp))))
    return out


def _resolve_video_source(video: Any) -> Tuple[Optional[Path], Optional[torch.Tensor]]:
    source = _extract_input_file(video)
    if source is not None:
        return source, None
    frames = _extract_video_frames(video)
    return None, frames


def _video_fps_from_input(video: Any, source: Optional[Path], fallback: float = 24.0) -> float:
    if isinstance(video, dict):
        for key in ("fps", "frame_rate"):
            if key in video:
                try:
                    v = float(video[key])
                    if v > 0.0:
                        return float(v)
                except Exception:
                    continue
    if source is not None:
        metadata, _ = _read_video_metadata(source)
        try:
            fps = float(metadata.get("fps", 0.0) or 0.0)
            if fps > 0.0:
                return fps
        except Exception:
            pass
    return float(max(1.0, fallback))


def _load_gif_or_webp(path: Path) -> Tuple[List[Image.Image], List[float]]:
    frames: List[Image.Image] = []
    durations: List[float] = []
    with Image.open(path) as img:
        default_ms = float(img.info.get("duration", 83) or 83)
        for frame in ImageSequence.Iterator(img):
            frames.append(frame.convert("RGB"))
            dur_ms = float(frame.info.get("duration", default_ms) or default_ms)
            durations.append(max(1.0, dur_ms) / 1000.0)
    return frames, durations


def _decode_video_to_pil(
    video: Any,
    requested_fps: float = 0.0,
    max_frames: int = 0,
) -> Tuple[List[Image.Image], float, List[str]]:
    warnings: List[str] = []
    source, frame_tensor = _resolve_video_source(video)

    if frame_tensor is not None:
        frames = _image_batch_to_pil(frame_tensor)
        fps = _video_fps_from_input(video, source=None, fallback=float(max(1.0, requested_fps or 24.0)))
        if max_frames > 0:
            frames = frames[: int(max_frames)]
        return frames, fps, warnings

    if source is None:
        warnings.append("No video source found")
        return [], float(max(1.0, requested_fps or 24.0)), warnings

    ext = _safe_ext(source.suffix)
    if ext in {"gif", "webp"}:
        try:
            frames, durations = _load_gif_or_webp(source)
            duration = float(sum(durations))
            fps = float(len(frames) / duration) if duration > 1e-9 else float(max(1.0, requested_fps or 24.0))
        except Exception as exc:
            warnings.append(f"Failed to decode {ext.upper()} frames: {exc}")
            return [], float(max(1.0, requested_fps or 24.0)), warnings

        if requested_fps > 0.0 and frames:
            fps_in = float(max(1.0, fps))
            fps_out = float(max(1.0, requested_fps))
            duration = float(len(frames) / fps_in)
            out_count = max(1, int(round(duration * fps_out)))
            sampled: List[Image.Image] = []
            for idx in range(out_count):
                t = float(idx / fps_out)
                src_idx = int(round(t * fps_in))
                src_idx = _clamp_int(src_idx, 0, len(frames) - 1)
                sampled.append(frames[src_idx])
            frames = sampled
            fps = fps_out

        if max_frames > 0:
            frames = frames[: int(max_frames)]
        return frames, float(max(1.0, fps)), warnings

    if not _ffmpeg_bin():
        warnings.append("ffmpeg is not available for decoding this video format")
        return [], float(max(1.0, requested_fps or 24.0)), warnings

    temp_root = _temp_dir()
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=str(temp_root), prefix="mkr_decode_video_") as tmp:
        tmp_path = Path(tmp)
        pattern = tmp_path / "frame_%06d.png"

        args: List[str] = ["-y", "-i", str(source)]
        if requested_fps > 0.0:
            args += ["-vf", f"fps={float(max(1.0, requested_fps)):.6f}"]
        args += [str(pattern)]

        ok, error = _run_ffmpeg(args)
        if not ok:
            warnings.append(f"ffmpeg decode failed: {error}")
            return [], float(max(1.0, requested_fps or 24.0)), warnings

        frame_files = sorted(tmp_path.glob("frame_*.png"))
        if max_frames > 0:
            frame_files = frame_files[: int(max_frames)]
        frames = [Image.open(p).convert("RGB") for p in frame_files]

        fps = _video_fps_from_input(video, source=source, fallback=float(max(1.0, requested_fps or 24.0)))
        if requested_fps > 0.0:
            fps = float(max(1.0, requested_fps))
        return frames, fps, warnings


def _save_video_from_pil(
    frames: Sequence[Image.Image],
    fps: float,
    target: Path,
    fmt: str,
) -> Tuple[bool, str]:
    frame_list = list(frames)
    if not frame_list:
        return False, "No frames to save"

    ext = _safe_ext(fmt)
    if ext in {"gif", "webp"}:
        if len(frame_list) == 1:
            _save_still_image(
                image=frame_list[0],
                path=target,
                output_format=ext,
                png_compress_level=4,
                jpeg_quality=92,
                webp_quality=90,
                pnginfo=None,
            )
            return True, ""
        try:
            _save_animation(
                frames=frame_list,
                path=target,
                output_format=ext,
                webp_quality=90,
                animation_fps=int(max(1, round(float(fps)))),
                animation_loop=0,
            )
            return True, ""
        except Exception as exc:
            return False, str(exc)

    if ext in {"mp4", "mov", "webm"}:
        ok, error = _save_frames_with_ffmpeg(
            frames=frame_list,
            target=target,
            ext=ext,
            fps=int(max(1, round(float(fps)))),
        )
        return bool(ok), str(error)

    return False, f"Unsupported output format '{fmt}'"


def _build_video_payload(
    frames_tensor: torch.Tensor,
    fps: float,
    source_path: Optional[Path] = None,
) -> Dict[str, Any]:
    t = frames_tensor.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    b = int(t.shape[0]) if t.ndim == 4 else 1
    h = int(t.shape[1]) if t.ndim == 4 else 0
    w = int(t.shape[2]) if t.ndim == 4 else 0
    payload: Dict[str, Any] = {
        "kind": "video",
        "frames": t.clamp(0.0, 1.0),
        "fps": float(max(1.0, fps)),
        "frame_count": int(b),
        "width": int(w),
        "height": int(h),
        "duration": float(b / float(max(1.0, fps))),
        "has_audio": False,
    }
    if source_path is not None:
        payload["path"] = str(source_path)
    return payload


def _extract_audio_file_or_wave(audio: Any) -> Tuple[Optional[Path], Optional[np.ndarray], int]:
    source = _extract_input_file(audio)
    if source is not None:
        return source, None, 0
    waveform, sample_rate = _extract_waveform(audio)
    return None, waveform, int(sample_rate)


class MKRLoadAudioMetadata:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "audio": ("*",),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "INT", "INT", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "sample_rate", "channels", "duration_sec", "metadata_json")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(self, audio_path: str = "", audio: Any = None):
        warnings: List[str] = []
        source, waveform, sample_rate = _extract_audio_file_or_wave(audio)
        if source is None:
            source = _extract_input_file(audio_path)

        metadata: Dict[str, Any] = {
            "path": str(source) if source is not None else "",
            "sample_rate": int(max(0, sample_rate)),
            "channels": 0,
            "duration": 0.0,
            "bitrate": 0,
            "codec": "",
            "warnings": warnings,
        }

        if source is not None:
            data, error = _run_ffprobe_json(source)
            if data is None:
                if error:
                    warnings.append(error)
                metadata["warnings"] = warnings
                payload = _make_audio_payload(path=source)
                return (payload, int(metadata["sample_rate"]), int(metadata["channels"]), float(metadata["duration"]), _json_text(metadata))

            streams = data.get("streams") if isinstance(data.get("streams"), list) else []
            fmt = data.get("format") if isinstance(data.get("format"), dict) else {}

            audio_stream = None
            for stream in streams:
                if isinstance(stream, dict) and str(stream.get("codec_type", "")).lower() == "audio":
                    audio_stream = stream
                    break

            if isinstance(audio_stream, dict):
                try:
                    metadata["sample_rate"] = int(float(audio_stream.get("sample_rate") or 0))
                except Exception:
                    pass
                try:
                    metadata["channels"] = int(audio_stream.get("channels") or 0)
                except Exception:
                    pass
                metadata["codec"] = str(audio_stream.get("codec_name") or "")
                try:
                    d = float(audio_stream.get("duration") or 0.0)
                    if d > 0.0:
                        metadata["duration"] = float(d)
                except Exception:
                    pass

            if metadata["duration"] <= 0.0:
                try:
                    metadata["duration"] = float(fmt.get("duration") or 0.0)
                except Exception:
                    metadata["duration"] = 0.0

            try:
                metadata["bitrate"] = int(float(fmt.get("bit_rate") or 0.0))
            except Exception:
                metadata["bitrate"] = 0

            metadata["warnings"] = warnings
            payload = _make_audio_payload(path=source, sample_rate=int(metadata["sample_rate"]))
            return (
                payload,
                int(metadata["sample_rate"]),
                int(metadata["channels"]),
                float(metadata["duration"]),
                _json_text(metadata),
            )

        if waveform is not None:
            channels = int(max(1, waveform.shape[0]))
            duration = float(waveform.shape[1] / float(max(1, sample_rate)))
            metadata.update(
                {
                    "sample_rate": int(max(1, sample_rate)),
                    "channels": channels,
                    "duration": duration,
                }
            )
            payload = _make_audio_payload(path=None, sample_rate=int(metadata["sample_rate"]))
            payload["waveform"] = torch.from_numpy(waveform)
            return (
                payload,
                int(metadata["sample_rate"]),
                int(metadata["channels"]),
                float(metadata["duration"]),
                _json_text(metadata),
            )

        warnings.append("No audio input found")
        metadata["warnings"] = warnings
        return (_make_audio_payload(path=None), 0, 0, 0.0, _json_text(metadata))


class MKRExtractVideoFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "sample_fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 240.0, "step": 0.1}),
                "start_frame": ("INT", {"default": 0, "min": 0, "max": 10000000, "step": 1}),
                "end_frame": ("INT", {"default": -1, "min": -1, "max": 10000000, "step": 1}),
                "stride": ("INT", {"default": 1, "min": 1, "max": 1000, "step": 1}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 1000000, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "FLOAT", "INT", "INT", "STRING")
    RETURN_NAMES = ("frames", "frame_count", "fps", "width", "height", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(
        self,
        video: Any,
        sample_fps: float = 0.0,
        start_frame: int = 0,
        end_frame: int = -1,
        stride: int = 1,
        max_frames: int = 0,
    ):
        frames, fps, warnings = _decode_video_to_pil(
            video=video,
            requested_fps=float(max(0.0, sample_fps)),
            max_frames=0,
        )

        total = len(frames)
        if total <= 0:
            dummy = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            summary = {"frame_count": 0, "fps": float(max(1.0, fps)), "warnings": warnings}
            return (dummy, 0, float(max(1.0, fps)), 64, 64, _json_text(summary))

        sf = _clamp_int(start_frame, 0, total - 1)
        ef = total - 1 if int(end_frame) < 0 else _clamp_int(end_frame, sf, total - 1)
        st = int(max(1, stride))

        selected = frames[sf : ef + 1 : st]
        if max_frames > 0:
            selected = selected[: int(max_frames)]

        tensor = _pil_to_tensor(selected)
        b, h, w, _ = tensor.shape
        summary = {
            "frame_count": int(b),
            "fps": float(max(1.0, fps)),
            "start_frame": int(sf),
            "end_frame": int(ef),
            "stride": int(st),
            "warnings": warnings,
        }
        return (tensor, int(b), float(max(1.0, fps)), int(w), int(h), _json_text(summary))


class MKRAssembleFramesToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["gif", "webp", "mp4", "mov", "webm"], {"default": "gif"}),
                "filename_prefix": ("STRING", {"default": "MKR_frames_video"}),
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
    CATEGORY = MEDIA_IO

    def run(
        self,
        image: torch.Tensor,
        fps: float = 24.0,
        output_format: str = "gif",
        filename_prefix: str = "MKR_frames_video",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames = _image_batch_to_pil(image)
        if not frames:
            warnings.append("No frames in input IMAGE")
            return (_make_video_payload(path=None), "", _json_text({"warnings": warnings}))

        fmt = _safe_ext(output_format)
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            warnings.append(f"Unsupported output format '{output_format}', using gif")
            fmt = "gif"

        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_frames_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(frames=frames, fps=float(fps), target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to assemble video: {error}")
            payload = _build_video_payload(_pil_to_tensor(frames), fps=float(max(1.0, fps)), source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        metadata, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=metadata)
        summary = {
            "output_path": str(target),
            "frame_count": int(len(frames)),
            "fps": float(max(1.0, fps)),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoSplitAtTimes:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "split_times_json": ("STRING", {"default": "[]", "multiline": True}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_split_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "INT", "STRING")
    RETURN_NAMES = ("first_clip", "clips_json", "clip_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        split_times_json: str = "[]",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_split_video",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        markers = sorted(set(float(max(0.0, x)) for x in _normalize_markers_json(split_times_json)))
        source, _ = _resolve_video_source(video)
        fps = _video_fps_from_input(video, source=source, fallback=float(fallback_fps))

        frames, decoded_fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        if decoded_fps > 0.0:
            fps = float(decoded_fps)

        if not frames:
            warnings.append("No frames available for split")
            return (_make_video_payload(path=source), "[]", 0, _json_text({"warnings": warnings}))

        total_frames = len(frames)
        duration = float(total_frames / float(max(1.0, fps)))
        boundaries = [0.0]
        boundaries.extend([m for m in markers if 0.0 < m < duration])
        boundaries.append(duration)

        fmt = _safe_ext(output_format)
        if fmt == "auto":
            src_ext = _safe_ext(source.suffix) if source is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)

        clips: List[Dict[str, Any]] = []
        first_payload: Optional[Dict[str, Any]] = None
        for idx in range(max(0, len(boundaries) - 1)):
            start_t = float(boundaries[idx])
            end_t = float(boundaries[idx + 1])
            if end_t <= start_t + 1e-6:
                continue

            sf = _clamp_int(int(math.floor(start_t * fps)), 0, total_frames - 1)
            ef = _clamp_int(int(math.ceil(end_t * fps)), sf + 1, total_frames)
            segment = frames[sf:ef]
            if not segment:
                continue

            stem = _sanitize_basename(f"{filename_prefix}_{idx:03d}", f"MKR_split_{idx:03d}")
            target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))
            ok, error = _save_video_from_pil(segment, fps=float(fps), target=target, fmt=fmt)
            if not ok:
                warnings.append(f"Failed to save clip {idx}: {error}")
                continue

            clip_info = {
                "index": int(idx),
                "path": str(target),
                "start_sec": round(start_t, 6),
                "end_sec": round(end_t, 6),
                "duration_sec": round(max(0.0, end_t - start_t), 6),
                "frame_count": int(len(segment)),
            }
            clips.append(clip_info)

            if first_payload is None:
                meta, meta_warnings = _read_video_metadata(target)
                warnings.extend(meta_warnings)
                first_payload = _make_video_payload(path=target, metadata=meta)

        if first_payload is None:
            first_payload = _build_video_payload(_pil_to_tensor(frames), fps=float(fps), source_path=source)

        summary = {
            "clip_count": int(len(clips)),
            "fps": float(fps),
            "duration_sec": round(duration, 6),
            "warnings": warnings,
        }
        return (first_payload, _json_text(clips), int(len(clips)), _json_text(summary))


class MKRVideoSelectRangeByFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "start_frame": ("INT", {"default": 0, "min": 0, "max": 10000000, "step": 1}),
                "end_frame": ("INT", {"default": 0, "min": 0, "max": 10000000, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_select_frames"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        start_frame: int = 0,
        end_frame: int = 0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_select_frames",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=_extract_input_file(video)), "", _json_text({"warnings": warnings}))

        total = len(frames)
        sf = _clamp_int(start_frame, 0, total - 1)
        ef = _clamp_int(end_frame, sf, total - 1)
        segment = frames[sf : ef + 1]

        fmt = _safe_ext(output_format)
        source = _extract_input_file(video)
        if fmt == "auto":
            src_ext = _safe_ext(source.suffix) if source is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_select_frames")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(segment, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save range clip: {error}")
            payload = _build_video_payload(_pil_to_tensor(segment), fps=fps, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "start_frame": int(sf),
            "end_frame": int(ef),
            "frame_count": int(len(segment)),
            "fps": float(fps),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRReverseVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_reverse_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_reverse_video",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=_extract_input_file(video)), "", _json_text({"warnings": warnings}))

        reversed_frames = list(reversed(frames))

        fmt = _safe_ext(output_format)
        source = _extract_input_file(video)
        if fmt == "auto":
            src_ext = _safe_ext(source.suffix) if source is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_reverse_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(reversed_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save reversed clip: {error}")
            payload = _build_video_payload(_pil_to_tensor(reversed_frames), fps=fps)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "frame_count": int(len(reversed_frames)),
            "fps": float(fps),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRFreezeFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "frame_index": ("INT", {"default": 0, "min": 0, "max": 10000000, "step": 1}),
                "hold_duration_sec": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 600.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["gif", "webp", "mp4", "mov", "webm"], {"default": "gif"}),
                "filename_prefix": ("STRING", {"default": "MKR_freeze_frame"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        frame_index: int = 0,
        hold_duration_sec: float = 1.0,
        fallback_fps: float = 24.0,
        output_format: str = "gif",
        filename_prefix: str = "MKR_freeze_frame",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=_extract_input_file(video)), "", _json_text({"warnings": warnings}))

        idx = _clamp_int(frame_index, 0, len(frames) - 1)
        base = frames[idx]
        count = int(max(1, round(float(max(0.01, hold_duration_sec)) * fps)))
        frozen = [base.copy() for _ in range(count)]

        fmt = _safe_ext(output_format)
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            warnings.append(f"Unsupported output format '{output_format}', using gif")
            fmt = "gif"
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_freeze_frame")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(frozen, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save freeze clip: {error}")
            payload = _build_video_payload(_pil_to_tensor(frozen), fps=fps)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "frame_index": int(idx),
            "frame_count": int(count),
            "hold_duration_sec": float(max(0.01, hold_duration_sec)),
            "fps": float(fps),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoLoopBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "loop_count": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "crossfade_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_loop_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
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
        crossfade_sec: float = 0.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_loop_video",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=_extract_input_file(video)), "", _json_text({"warnings": warnings}))

        loops = int(max(1, loop_count))
        cross = int(max(0, round(float(max(0.0, crossfade_sec)) * fps)))

        result: List[Image.Image] = []
        base = [f.copy() for f in frames]
        result.extend(base)

        if loops > 1:
            for _ in range(loops - 1):
                if cross > 0 and len(base) > 1:
                    overlap = int(min(cross, len(base) - 1, len(result)))
                    if overlap > 0:
                        head = base[:overlap]
                        tail = result[-overlap:]
                        blended: List[Image.Image] = []
                        for i in range(overlap):
                            a = np.asarray(tail[i].convert("RGB"), dtype=np.float32)
                            b = np.asarray(head[i].convert("RGB"), dtype=np.float32)
                            t = float((i + 1) / (overlap + 1))
                            mix = np.clip(a * (1.0 - t) + b * t, 0.0, 255.0).astype(np.uint8)
                            blended.append(Image.fromarray(mix, mode="RGB"))
                        result[-overlap:] = blended
                        result.extend(base[overlap:])
                    else:
                        result.extend(base)
                else:
                    result.extend(base)

        fmt = _safe_ext(output_format)
        source = _extract_input_file(video)
        if fmt == "auto":
            src_ext = _safe_ext(source.suffix) if source is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_loop_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(result, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save loop clip: {error}")
            payload = _build_video_payload(_pil_to_tensor(result), fps=fps)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "input_frames": int(len(base)),
            "output_frames": int(len(result)),
            "loop_count": int(loops),
            "crossfade_frames": int(cross),
            "fps": float(fps),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoSpeedRamp:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "ramp_points_json": (
                    "STRING",
                    {
                        "default": '[{"frame":0,"speed":1.0},{"frame":60,"speed":0.6},{"frame":120,"speed":1.8}]',
                        "multiline": True,
                    },
                ),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_speed_ramp"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        video: Any,
        ramp_points_json: str = '[{"frame":0,"speed":1.0},{"frame":60,"speed":0.6},{"frame":120,"speed":1.8}]',
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_speed_ramp",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=_extract_input_file(video)), "", _json_text({"warnings": warnings}))

        total = len(frames)
        points = _normalize_ramp_points(ramp_points_json, total_frames=total)

        speeds = np.ones((total,), dtype=np.float32)
        for idx in range(len(points) - 1):
            f0, s0 = points[idx]
            f1, s1 = points[idx + 1]
            if f1 <= f0:
                speeds[f0] = float(max(0.01, s0))
                continue
            segment = np.linspace(float(s0), float(s1), num=(f1 - f0 + 1), dtype=np.float32)
            speeds[f0 : f1 + 1] = np.clip(segment, 0.01, 100.0)

        if points:
            speeds[: points[0][0] + 1] = float(max(0.01, points[0][1]))
            speeds[points[-1][0] :] = float(max(0.01, points[-1][1]))

        dt = 1.0 / fps
        frame_durations = dt / np.clip(speeds, 0.01, 100.0)
        cumulative = np.cumsum(frame_durations)
        total_out_duration = float(cumulative[-1]) if cumulative.size > 0 else dt
        out_count = int(max(1, round(total_out_duration * fps)))

        out_frames: List[Image.Image] = []
        for i in range(out_count):
            t = float(i / fps)
            src_idx = int(np.searchsorted(cumulative, t, side="right"))
            src_idx = _clamp_int(src_idx, 0, total - 1)
            out_frames.append(frames[src_idx])

        fmt = _safe_ext(output_format)
        source = _extract_input_file(video)
        if fmt == "auto":
            src_ext = _safe_ext(source.suffix) if source is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_speed_ramp")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save speed-ramped video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "input_frames": int(total),
            "output_frames": int(len(out_frames)),
            "fps": float(fps),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoCrossfade:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_a": ("*",),
                "video_b": ("*",),
                "transition_duration_sec": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 10.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_crossfade_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video_a: Any,
        video_b: Any,
        transition_duration_sec: float = 0.5,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_crossfade_video",
        subfolder: str = "",
        overwrite: bool = False,
    ):
        warnings: List[str] = []
        frames_a, fps_a, wa = _decode_video_to_pil(video=video_a, requested_fps=0.0, max_frames=0)
        frames_b, fps_b, wb = _decode_video_to_pil(video=video_b, requested_fps=0.0, max_frames=0)
        warnings.extend(wa)
        warnings.extend(wb)

        fps = float(max(1.0, fps_a if fps_a > 0.0 else (fps_b if fps_b > 0.0 else fallback_fps)))

        if not frames_a or not frames_b:
            warnings.append("Both video_a and video_b must provide frames")
            return (_make_video_payload(path=_extract_input_file(video_a) or _extract_input_file(video_b)), "", _json_text({"warnings": warnings}))

        # Match resolution to A.
        target_size = frames_a[0].size
        if frames_b[0].size != target_size:
            frames_b = [f.resize(target_size, resample=Image.Resampling.BILINEAR) for f in frames_b]

        n = int(max(0, round(float(max(0.0, transition_duration_sec)) * fps)))
        n = int(min(n, len(frames_a), len(frames_b)))

        out_frames: List[Image.Image] = []
        if n <= 0:
            out_frames.extend(frames_a)
            out_frames.extend(frames_b)
        else:
            out_frames.extend(frames_a[:-n])
            tail = frames_a[-n:]
            head = frames_b[:n]
            for idx in range(n):
                a = np.asarray(tail[idx].convert("RGB"), dtype=np.float32)
                b = np.asarray(head[idx].convert("RGB"), dtype=np.float32)
                t = float((idx + 1) / (n + 1))
                mixed = np.clip(a * (1.0 - t) + b * t, 0.0, 255.0).astype(np.uint8)
                out_frames.append(Image.fromarray(mixed, mode="RGB"))
            out_frames.extend(frames_b[n:])

        fmt = _safe_ext(output_format)
        source_a = _extract_input_file(video_a)
        if fmt == "auto":
            src_ext = _safe_ext(source_a.suffix) if source_a is not None else "gif"
            fmt = src_ext if src_ext in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
        if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
            fmt = "gif"
            warnings.append("Unsupported output format, using gif")
        if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
            warnings.append("ffmpeg is not available for mp4/mov/webm, using gif")
            fmt = "gif"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_prefix, "MKR_crossfade_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save crossfade video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "fps": float(fps),
            "transition_frames": int(n),
            "output_frames": int(len(out_frames)),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))
