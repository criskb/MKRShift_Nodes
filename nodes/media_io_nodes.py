import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageSequence
import torch

from ..categories import MEDIA_ANALYSIS, MEDIA_AUDIO_UTILITY, MEDIA_IO, MEDIA_TIMELINE
from .presave_image_nodes import _image_batch_to_pil, _output_dir, _resolve_output_file, _sanitize_basename, _temp_dir
from .presave_media_nodes import (
    _copy_or_transcode,
    _extract_input_file,
    _extract_video_frames,
    _extract_waveform,
    _ffmpeg_bin,
    _run_ffmpeg,
    _safe_ext,
    _save_wav,
)


def _ffprobe_bin() -> Optional[str]:
    found = shutil.which("ffprobe")
    if found:
        return found
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return None
    sibling = Path(ffmpeg).with_name("ffprobe")
    if sibling.exists() and sibling.is_file():
        return str(sibling)
    return None


def _ratio_to_float(raw: Any) -> float:
    text = str(raw or "").strip()
    if not text:
        return 0.0
    if "/" in text:
        parts = text.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
            if abs(den) < 1e-9:
                return 0.0
            return float(num / den)
        except Exception:
            return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _run_ffprobe_json(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    ffprobe = _ffprobe_bin()
    if not ffprobe:
        return None, "ffprobe is not available"

    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-print_format",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return None, str(exc)

    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or f"ffprobe exited with code {proc.returncode}").strip()

    try:
        data = json.loads(proc.stdout or "{}")
        if not isinstance(data, dict):
            return None, "Unexpected ffprobe output format"
        return data, ""
    except Exception as exc:
        return None, f"Failed to parse ffprobe json: {exc}"


def _read_video_metadata(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    metadata: Dict[str, Any] = {
        "path": str(path),
        "fps": 0.0,
        "duration": 0.0,
        "frame_count": 0,
        "width": 0,
        "height": 0,
        "resolution": "0x0",
        "has_audio": False,
        "format": _safe_ext(path.suffix),
    }

    data, error = _run_ffprobe_json(path)
    if data is not None:
        streams = data.get("streams") if isinstance(data.get("streams"), list) else []
        fmt = data.get("format") if isinstance(data.get("format"), dict) else {}

        video_stream = None
        for stream in streams:
            if isinstance(stream, dict) and str(stream.get("codec_type", "")).lower() == "video":
                video_stream = stream
                break

        has_audio = any(
            isinstance(stream, dict) and str(stream.get("codec_type", "")).lower() == "audio"
            for stream in streams
        )
        metadata["has_audio"] = bool(has_audio)

        if isinstance(video_stream, dict):
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            fps = _ratio_to_float(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
            duration = float(video_stream.get("duration") or 0.0)
            if duration <= 0.0:
                try:
                    duration = float(fmt.get("duration") or 0.0)
                except Exception:
                    duration = 0.0

            frame_count = int(video_stream.get("nb_frames") or 0)
            if frame_count <= 0 and fps > 0.0 and duration > 0.0:
                frame_count = int(max(1, round(duration * fps)))

            metadata.update(
                {
                    "fps": float(max(0.0, fps)),
                    "duration": float(max(0.0, duration)),
                    "frame_count": int(max(0, frame_count)),
                    "width": int(max(0, width)),
                    "height": int(max(0, height)),
                    "resolution": f"{int(max(0, width))}x{int(max(0, height))}",
                }
            )
            return metadata, warnings

        warnings.append("ffprobe did not report a video stream")
    elif error:
        warnings.append(error)

    ext = _safe_ext(path.suffix)
    if ext in {"gif", "webp"}:
        try:
            with Image.open(path) as img:
                width, height = img.size
                durations: List[float] = []
                frames = 0
                for frame in ImageSequence.Iterator(img):
                    frames += 1
                    dur_ms = frame.info.get("duration", img.info.get("duration", 83))
                    try:
                        durations.append(max(1.0, float(dur_ms)) / 1000.0)
                    except Exception:
                        durations.append(0.083)
                duration = float(sum(durations))
                fps = float(frames / duration) if duration > 1e-9 else 0.0
                metadata.update(
                    {
                        "fps": fps,
                        "duration": duration,
                        "frame_count": int(frames),
                        "width": int(width),
                        "height": int(height),
                        "resolution": f"{int(width)}x{int(height)}",
                        "has_audio": False,
                    }
                )
                return metadata, warnings
        except Exception as exc:
            warnings.append(f"Fallback GIF/WEBP parser failed: {exc}")

    return metadata, warnings


def _read_audio_duration(path: Path) -> float:
    data, _ = _run_ffprobe_json(path)
    if data is None:
        return 0.0

    fmt = data.get("format") if isinstance(data.get("format"), dict) else {}
    try:
        duration = float(fmt.get("duration") or 0.0)
        if duration > 0.0:
            return float(duration)
    except Exception:
        pass

    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("codec_type", "")).lower() != "audio":
            continue
        try:
            duration = float(stream.get("duration") or 0.0)
            if duration > 0.0:
                return float(duration)
        except Exception:
            continue
    return 0.0


def _audio_codec_args(ext: str) -> Optional[List[str]]:
    fmt = _safe_ext(ext)
    if fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if fmt == "flac":
        return ["-c:a", "flac"]
    if fmt == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "5"]
    return None


def _video_codec_args(ext: str) -> Optional[List[str]]:
    fmt = _safe_ext(ext)
    if fmt == "mp4":
        return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k"]
    if fmt == "mov":
        return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    if fmt == "webm":
        return ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-c:a", "libopus", "-b:a", "160k"]
    return None


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _make_video_payload(path: Optional[Path], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"kind": "video"}
    if path is not None:
        payload["path"] = str(path)
    if isinstance(metadata, dict):
        payload.update(metadata)
    return payload


def _make_audio_payload(path: Optional[Path], sample_rate: int = 0) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"kind": "audio"}
    if path is not None:
        payload["path"] = str(path)
    if int(sample_rate) > 0:
        payload["sample_rate"] = int(sample_rate)
    return payload


def _ensure_audio_file(audio: Any, stem_hint: str) -> Tuple[Optional[Path], int, str]:
    source = _extract_input_file(audio)
    if source is not None:
        return source, 0, ""

    waveform, sample_rate = _extract_waveform(audio)
    if waveform is None:
        return None, 0, "No usable audio source was found"

    temp_dir = _temp_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_basename(stem_hint, "MKR_audio")
    wav_path = _resolve_output_file(temp_dir, stem, "wav", overwrite=False)
    ok, error = _save_wav(wav_path, waveform=waveform, sample_rate=int(sample_rate))
    if not ok:
        return None, int(sample_rate), error
    return wav_path, int(sample_rate), ""


def _clamp_audio_speed(value: float) -> float:
    return float(max(0.01, min(100.0, float(value))))


def _atempo_chain(speed: float) -> str:
    value = _clamp_audio_speed(speed)
    factors: List[float] = []

    while value > 2.0:
        factors.append(2.0)
        value /= 2.0
    while value < 0.5:
        factors.append(0.5)
        value /= 0.5
    factors.append(value)

    return ",".join(f"atempo={float(f):.6f}" for f in factors)


def _video_duration_from_frames(video: Any, fallback_fps: int = 12) -> Tuple[float, int]:
    frames = _extract_video_frames(video)
    if frames is None:
        return 0.0, 0
    frame_count = int(frames.shape[0]) if frames.ndim == 4 else 1
    fps = max(1, int(fallback_fps))
    return float(frame_count / float(fps)), frame_count


def _detect_scene_cuts_ffmpeg(path: Path, threshold: float, min_scene_length_sec: float) -> Tuple[List[float], str]:
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return [], "ffmpeg is not available"

    th = float(max(0.0, min(1.0, threshold)))
    filter_expr = f"select=gt(scene\\,{th:.6f}),showinfo"

    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "info",
                "-i",
                str(path),
                "-filter:v",
                filter_expr,
                "-an",
                "-f",
                "null",
                "-",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return [], str(exc)

    text = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    raw_times: List[float] = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", text):
        try:
            raw_times.append(float(match.group(1)))
        except Exception:
            continue

    if not raw_times and proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or f"ffmpeg exited with code {proc.returncode}").strip()

    min_gap = float(max(0.0, min_scene_length_sec))
    out = [0.0]
    last = 0.0
    for t in sorted(raw_times):
        if t - last + 1e-6 < min_gap:
            continue
        out.append(float(t))
        last = float(t)
    return out, ""


def _detect_scene_cuts_from_frames(
    frames: Sequence[Image.Image],
    fps: float,
    threshold: float,
    min_scene_length_sec: float,
) -> List[float]:
    if not frames:
        return [0.0]

    out = [0.0]
    prev: Optional[np.ndarray] = None
    min_gap = float(max(0.0, min_scene_length_sec))
    last_time = 0.0

    for idx, frame in enumerate(frames):
        gray = np.asarray(frame.convert("L").resize((96, 96), resample=Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
        if prev is None:
            prev = gray
            continue

        score = float(np.mean(np.abs(gray - prev)))
        prev = gray
        t = float(idx / max(1e-6, float(fps)))
        if score >= float(threshold) and (t - last_time + 1e-6) >= min_gap:
            out.append(t)
            last_time = t

    return sorted(set(float(x) for x in out))


def _build_scene_ranges(cuts: List[float], duration: float, fps: float) -> List[Dict[str, Any]]:
    points = sorted(float(max(0.0, c)) for c in cuts)
    if not points:
        points = [0.0]
    if points[0] > 1e-6:
        points.insert(0, 0.0)

    dur = float(max(0.0, duration))
    if dur > 1e-6 and (not points or points[-1] < dur - 1e-6):
        points.append(dur)

    ranges: List[Dict[str, Any]] = []
    for idx in range(max(0, len(points) - 1)):
        start_t = float(points[idx])
        end_t = float(points[idx + 1])
        if end_t < start_t:
            continue
        start_f = int(max(0, round(start_t * fps)))
        end_f = int(max(start_f, round(end_t * fps)))
        ranges.append(
            {
                "index": int(idx),
                "start_time": round(start_t, 6),
                "end_time": round(end_t, 6),
                "duration": round(max(0.0, end_t - start_t), 6),
                "start_frame": int(start_f),
                "end_frame": int(end_f),
            }
        )
    return ranges


def _process_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    start_sec: float,
    end_sec: float,
    fade_in_sec: float,
    fade_out_sec: float,
    normalize_mode: str,
) -> np.ndarray:
    sr = int(max(1, sample_rate))
    samples = waveform.astype(np.float32, copy=True)

    start_idx = int(max(0, round(float(max(0.0, start_sec)) * sr)))
    if float(end_sec) > float(start_sec):
        end_idx = int(max(start_idx, round(float(end_sec) * sr)))
    else:
        end_idx = int(samples.shape[1])

    end_idx = int(max(start_idx, min(end_idx, int(samples.shape[1]))))
    trimmed = samples[:, start_idx:end_idx]

    if trimmed.size <= 0:
        return np.zeros((samples.shape[0], 1), dtype=np.float32)

    fade_in = int(max(0, round(float(max(0.0, fade_in_sec)) * sr)))
    fade_out = int(max(0, round(float(max(0.0, fade_out_sec)) * sr)))

    if fade_in > 0:
        n = min(fade_in, trimmed.shape[1])
        ramp = np.linspace(0.0, 1.0, num=n, dtype=np.float32)
        trimmed[:, :n] *= ramp[None, :]

    if fade_out > 0:
        n = min(fade_out, trimmed.shape[1])
        ramp = np.linspace(1.0, 0.0, num=n, dtype=np.float32)
        trimmed[:, -n:] *= ramp[None, :]

    mode = str(normalize_mode or "off").strip().lower()
    if mode == "peak_-1db":
        peak = float(np.max(np.abs(trimmed)))
        target = float(10.0 ** (-1.0 / 20.0))
        if peak > 1e-9:
            trimmed *= float(target / peak)
    elif mode in {"lufs_-14", "lufs_-16"}:
        target_db = -14.0 if mode == "lufs_-14" else -16.0
        rms = float(np.sqrt(np.mean(np.square(trimmed)) + 1e-12))
        current_db = 20.0 * math.log10(max(rms, 1e-9))
        gain = float(10.0 ** ((target_db - current_db) / 20.0))
        trimmed *= gain

    return np.clip(trimmed, -1.0, 1.0).astype(np.float32, copy=False)


class MKRLoadVideoMetadata:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "video": ("*",),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "FLOAT", "FLOAT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("video", "fps", "duration_sec", "frame_count", "width", "height", "metadata_json")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(self, video_path: str = "", video: Any = None):
        warnings: List[str] = []
        source = _extract_input_file(video) if video is not None else None
        if source is None:
            source = _extract_input_file(video_path)

        if source is None:
            warnings.append("Video file was not found")
            payload = _make_video_payload(path=None)
            metadata = {
                "path": "",
                "fps": 0.0,
                "duration": 0.0,
                "frame_count": 0,
                "width": 0,
                "height": 0,
                "resolution": "0x0",
                "warnings": warnings,
            }
            return (payload, 0.0, 0.0, 0, 0, 0, _json_text(metadata))

        metadata, meta_warnings = _read_video_metadata(source)
        warnings.extend(meta_warnings)
        if warnings:
            metadata["warnings"] = warnings

        payload = _make_video_payload(path=source, metadata=metadata)
        return (
            payload,
            float(metadata.get("fps", 0.0) or 0.0),
            float(metadata.get("duration", 0.0) or 0.0),
            int(metadata.get("frame_count", 0) or 0),
            int(metadata.get("width", 0) or 0),
            int(metadata.get("height", 0) or 0),
            _json_text(metadata),
        )


class MKRMuxVideoAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "audio": ("*",),
                "output_format": (["mp4", "mov", "webm"], {"default": "mp4"}),
                "filename_prefix": ("STRING", {"default": "MKR_mux"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "audio_offset_ms": ("INT", {"default": 0, "min": 0, "max": 600000, "step": 1}),
                "audio_gain_db": ("FLOAT", {"default": 0.0, "min": -30.0, "max": 30.0, "step": 0.1}),
                "shortest": ("BOOLEAN", {"default": True}),
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
        video: Any,
        audio: Any,
        output_format: str = "mp4",
        filename_prefix: str = "MKR_mux",
        subfolder: str = "",
        overwrite: bool = False,
        audio_offset_ms: int = 0,
        audio_gain_db: float = 0.0,
        shortest: bool = True,
        filename_label: str = "",
    ):
        warnings: List[str] = []

        video_path = _extract_input_file(video)
        if video_path is None:
            warnings.append("Video input could not be resolved to a file path")
            return (_make_video_payload(path=None), "", _json_text({"warnings": warnings}))

        audio_path, _, audio_err = _ensure_audio_file(audio=audio, stem_hint="mkr_mux_audio")
        if audio_path is None:
            warnings.append(f"Audio input could not be resolved: {audio_err}")
            return (_make_video_payload(path=video_path), "", _json_text({"warnings": warnings}))

        fmt = _safe_ext(output_format or "mp4")
        codec_args = _video_codec_args(fmt)
        if codec_args is None:
            warnings.append(f"Unsupported output format '{output_format}'")
            return (_make_video_payload(path=video_path), "", _json_text({"warnings": warnings}))

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_mux")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        args: List[str] = ["-y", "-i", str(video_path)]
        offset_sec = float(max(0, int(audio_offset_ms))) / 1000.0
        if offset_sec > 1e-6:
            args += ["-itsoffset", f"{offset_sec:.3f}"]
        args += ["-i", str(audio_path)]
        args += ["-map", "0:v:0", "-map", "1:a:0"]

        if abs(float(audio_gain_db)) > 1e-6:
            args += ["-filter:a", f"volume={float(audio_gain_db):.3f}dB"]

        args += codec_args
        if bool(shortest):
            args += ["-shortest"]
        args += [str(target)]

        ok, error = _run_ffmpeg(args)
        if not ok:
            warnings.append(f"Mux failed: {error}")
            return (_make_video_payload(path=video_path), "", _json_text({"warnings": warnings}))

        metadata, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)

        payload = _make_video_payload(path=target, metadata=metadata)
        summary = {
            "output_path": str(target),
            "warnings": warnings,
            "video_source": str(video_path),
            "audio_source": str(audio_path),
        }
        return (payload, str(target), _json_text(summary))


class MKRAudioTrimFadeNormalize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "start_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.01}),
                "end_sec": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 86400.0, "step": 0.01}),
                "fade_in_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 60.0, "step": 0.01}),
                "fade_out_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 60.0, "step": 0.01}),
                "normalize_mode": (["off", "peak_-1db", "lufs_-14", "lufs_-16"], {"default": "peak_-1db"}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_edit"}),
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
        start_sec: float = 0.0,
        end_sec: float = -1.0,
        fade_in_sec: float = 0.0,
        fade_out_sec: float = 0.0,
        normalize_mode: str = "peak_-1db",
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_edit",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []

        source = _extract_input_file(audio)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_audio_edit")

        mode = str(normalize_mode or "off").strip().lower()
        start = float(max(0.0, start_sec))
        end = float(end_sec)
        fade_in = float(max(0.0, fade_in_sec))
        fade_out = float(max(0.0, fade_out_sec))

        if source is not None:
            src_ext = _safe_ext(source.suffix)
            dst_ext = src_ext if _safe_ext(output_format) == "auto" else _safe_ext(output_format)
            if dst_ext not in {"wav", "mp3", "flac", "ogg"}:
                dst_ext = "wav"

            target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))

            trim_duration = _read_audio_duration(source)
            if end > start:
                trim_duration = float(max(0.0, end - start))
            elif trim_duration > 0.0:
                trim_duration = float(max(0.0, trim_duration - start))

            filters: List[str] = []
            if end > start:
                filters.append(f"atrim=start={start:.6f}:end={end:.6f}")
            elif start > 1e-9:
                filters.append(f"atrim=start={start:.6f}")
            filters.append("asetpts=PTS-STARTPTS")

            if fade_in > 1e-6:
                filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
            if fade_out > 1e-6 and trim_duration > 1e-6:
                out_start = max(0.0, trim_duration - fade_out)
                filters.append(f"afade=t=out:st={out_start:.6f}:d={fade_out:.6f}")

            if mode == "peak_-1db":
                filters.append("dynaudnorm=f=200:g=15:p=0.90")
            elif mode == "lufs_-14":
                filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
            elif mode == "lufs_-16":
                filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

            codec = _audio_codec_args(dst_ext)
            if codec is None:
                warnings.append(f"Unsupported output audio format '{dst_ext}'")
                return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

            args: List[str] = ["-y", "-i", str(source), "-vn"]
            if filters:
                args += ["-af", ",".join(filters)]
            args += codec
            args += [str(target)]

            ok, error = _run_ffmpeg(args)
            if not ok:
                warnings.append(f"Audio processing failed: {error}")
                return (_make_audio_payload(path=source), "", 0.0, _json_text({"warnings": warnings}))

            duration = _read_audio_duration(target)
            payload = _make_audio_payload(path=target)
            summary = {
                "output_path": str(target),
                "warnings": warnings,
                "normalize_mode": mode,
            }
            return (payload, str(target), float(duration), _json_text(summary))

        waveform, sample_rate = _extract_waveform(audio)
        if waveform is None:
            warnings.append("Audio input is not file-like and no waveform tensor was detected")
            return (_make_audio_payload(path=None), "", 0.0, _json_text({"warnings": warnings}))

        processed = _process_waveform(
            waveform=waveform,
            sample_rate=int(sample_rate),
            start_sec=start,
            end_sec=end,
            fade_in_sec=fade_in,
            fade_out_sec=fade_out,
            normalize_mode=mode,
        )

        dst_ext = _safe_ext(output_format)
        if dst_ext == "auto" or dst_ext not in {"wav", "mp3", "flac", "ogg"}:
            dst_ext = "wav"

        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))

        if dst_ext == "wav":
            ok, error = _save_wav(target, waveform=processed, sample_rate=int(sample_rate))
            if not ok:
                warnings.append(f"Failed to write WAV output: {error}")
                return (_make_audio_payload(path=None, sample_rate=int(sample_rate)), "", 0.0, _json_text({"warnings": warnings}))
        else:
            temp_dir = _temp_dir()
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_wav = _resolve_output_file(out_dir=temp_dir, stem=f"{stem}_src", ext="wav", overwrite=False)
            ok, error = _save_wav(temp_wav, waveform=processed, sample_rate=int(sample_rate))
            if not ok:
                warnings.append(f"Failed to create temporary WAV: {error}")
                return (_make_audio_payload(path=None, sample_rate=int(sample_rate)), "", 0.0, _json_text({"warnings": warnings}))

            transcode_ok, transcode_error = _copy_or_transcode(
                source=temp_wav,
                target=target,
                ext=dst_ext,
                kind="audio",
            )
            try:
                temp_wav.unlink(missing_ok=True)
            except Exception:
                pass

            if not transcode_ok:
                warnings.append(f"Failed to encode audio output: {transcode_error}")
                return (_make_audio_payload(path=None, sample_rate=int(sample_rate)), "", 0.0, _json_text({"warnings": warnings}))

        duration = float(processed.shape[1] / max(1, int(sample_rate)))
        payload = _make_audio_payload(path=target, sample_rate=int(sample_rate))
        payload["waveform"] = torch.from_numpy(processed)

        summary = {
            "output_path": str(target),
            "warnings": warnings,
            "normalize_mode": mode,
            "sample_rate": int(sample_rate),
        }
        return (payload, str(target), duration, _json_text(summary))


class MKRSceneCutDetector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "threshold": ("FLOAT", {"default": 0.32, "min": 0.0, "max": 1.0, "step": 0.001}),
                "min_scene_length_sec": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 30.0, "step": 0.01}),
                "fallback_fps": ("INT", {"default": 12, "min": 1, "max": 240, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("cut_times_json", "scene_ranges_json", "scene_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(
        self,
        video: Any,
        threshold: float = 0.32,
        min_scene_length_sec: float = 0.35,
        fallback_fps: int = 12,
    ):
        warnings: List[str] = []
        source = _extract_input_file(video)

        duration = 0.0
        fps = float(max(1, int(fallback_fps)))
        cuts: List[float] = [0.0]

        if source is not None:
            metadata, meta_warnings = _read_video_metadata(source)
            warnings.extend(meta_warnings)
            duration = float(metadata.get("duration", 0.0) or 0.0)
            fps = float(metadata.get("fps", fps) or fps)

            ffmpeg_cuts, ffmpeg_error = _detect_scene_cuts_ffmpeg(
                path=source,
                threshold=float(threshold),
                min_scene_length_sec=float(min_scene_length_sec),
            )
            if ffmpeg_cuts:
                cuts = ffmpeg_cuts
            elif ffmpeg_error:
                warnings.append(ffmpeg_error)

        if len(cuts) <= 1:
            frames_tensor = _extract_video_frames(video)
            if frames_tensor is None and source is not None and _safe_ext(source.suffix) in {"gif", "webp"}:
                try:
                    with Image.open(source) as img:
                        frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(img)]
                except Exception:
                    frames = []
            else:
                frames = _image_batch_to_pil(frames_tensor) if frames_tensor is not None else []

            if frames:
                if duration <= 0.0:
                    duration = float(len(frames) / max(1.0, fps))
                cuts = _detect_scene_cuts_from_frames(
                    frames=frames,
                    fps=fps,
                    threshold=float(threshold),
                    min_scene_length_sec=float(min_scene_length_sec),
                )
            elif source is None:
                warnings.append("No file path or frame tensor found for scene detection")

        cuts = sorted(set(float(max(0.0, c)) for c in cuts))
        if not cuts:
            cuts = [0.0]

        if duration <= 0.0:
            duration, _ = _video_duration_from_frames(video, fallback_fps=int(fallback_fps))

        if duration > 1e-6 and cuts[-1] < duration - 1e-6:
            cuts.append(float(duration))

        ranges = _build_scene_ranges(cuts=cuts, duration=duration, fps=fps)
        scene_count = int(len(ranges))

        summary = {
            "scene_count": scene_count,
            "fps": float(fps),
            "duration": float(duration),
            "warnings": warnings,
        }

        return (
            _json_text(cuts),
            _json_text(ranges),
            scene_count,
            _json_text(summary),
        )


class MKRBeatSyncRetimer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "target_bpm": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 400.0, "step": 0.1}),
                "beats_per_segment": ("INT", {"default": 4, "min": 1, "max": 32, "step": 1}),
                "source_bpm": ("FLOAT", {"default": 120.0, "min": 0.0, "max": 400.0, "step": 0.1}),
                "mode": (["plan_only", "retime_with_ffmpeg"], {"default": "plan_only"}),
                "output_format": (["auto", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_beat_sync"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "FLOAT", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("video", "speed_factor", "beat_interval_sec", "beat_markers_json", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        video: Any,
        target_bpm: float = 120.0,
        beats_per_segment: int = 4,
        source_bpm: float = 120.0,
        mode: str = "plan_only",
        output_format: str = "auto",
        filename_prefix: str = "MKR_beat_sync",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        source = _extract_input_file(video)

        fps = 12.0
        duration = 0.0
        has_audio = False
        metadata: Dict[str, Any] = {}

        if source is not None:
            metadata, meta_warnings = _read_video_metadata(source)
            warnings.extend(meta_warnings)
            fps = float(metadata.get("fps", fps) or fps)
            duration = float(metadata.get("duration", 0.0) or 0.0)
            has_audio = bool(metadata.get("has_audio", False))
        else:
            duration, frame_count = _video_duration_from_frames(video=video, fallback_fps=12)
            fps = 12.0
            metadata = {
                "fps": fps,
                "duration": duration,
                "frame_count": int(frame_count),
                "has_audio": False,
            }

        target = float(max(1.0, target_bpm))
        beats = int(max(1, beats_per_segment))
        beat_interval = float((60.0 / target) * beats)

        if source_bpm > 1e-6:
            speed = float(target / float(source_bpm))
        else:
            speed = 1.0
            warnings.append("source_bpm <= 0, speed factor defaults to 1.0")

        markers: List[float] = [0.0]
        if duration > 1e-6 and beat_interval > 1e-6:
            t = beat_interval
            while t < duration - 1e-6:
                markers.append(float(round(t, 6)))
                t += beat_interval
            markers.append(float(round(duration, 6)))

        out_payload = _make_video_payload(path=source, metadata=metadata if metadata else None)

        do_retime = str(mode or "plan_only").strip().lower() == "retime_with_ffmpeg"
        if do_retime:
            if source is None:
                warnings.append("Retime requires a file-based video input")
            elif not _ffmpeg_bin():
                warnings.append("ffmpeg is not available for retime")
            else:
                ext = _safe_ext(output_format)
                src_ext = _safe_ext(source.suffix)
                if ext == "auto":
                    ext = src_ext if src_ext in {"mp4", "mov", "webm"} else "mp4"
                if ext not in {"mp4", "mov", "webm"}:
                    warnings.append(f"Unsupported output format '{output_format}', using mp4")
                    ext = "mp4"

                out_dir = _output_dir(subfolder)
                out_dir.mkdir(parents=True, exist_ok=True)
                stem = _sanitize_basename(filename_label or filename_prefix, "MKR_beat_sync")
                target_path = _resolve_output_file(out_dir=out_dir, stem=stem, ext=ext, overwrite=bool(overwrite))

                args: List[str] = ["-y", "-i", str(source), "-map", "0:v:0"]
                args += ["-filter:v", f"setpts=PTS/{float(speed):.10f}"]

                if has_audio:
                    args += ["-map", "0:a:0?"]
                    args += ["-filter:a", _atempo_chain(speed)]

                codec = _video_codec_args(ext)
                if codec is None:
                    warnings.append(f"No codec profile found for '{ext}'")
                else:
                    args += codec
                    args += [str(target_path)]
                    ok, error = _run_ffmpeg(args)
                    if not ok:
                        warnings.append(f"Beat sync retime failed: {error}")
                    else:
                        out_meta, meta_warnings = _read_video_metadata(target_path)
                        warnings.extend(meta_warnings)
                        out_payload = _make_video_payload(path=target_path, metadata=out_meta)

        summary = {
            "speed_factor": float(speed),
            "beat_interval_sec": float(beat_interval),
            "duration": float(duration),
            "warnings": warnings,
        }

        return (
            out_payload,
            float(speed),
            float(beat_interval),
            _json_text(markers),
            _json_text(summary),
        )
