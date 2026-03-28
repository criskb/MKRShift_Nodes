import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageSequence
import torch

from ..categories import MEDIA_AUDIO_UTILITY, MEDIA_TIMELINE, MEDIA_VIDEO_EDIT
from .media_io_nodes import (
    _audio_codec_args,
    _json_text,
    _make_audio_payload,
    _make_video_payload,
    _read_audio_duration,
    _read_video_metadata,
    _video_codec_args,
)
from .presave_image_nodes import _output_dir, _resolve_output_file, _sanitize_basename, _temp_dir
from .presave_media_nodes import (
    _copy_or_transcode,
    _extract_input_file,
    _extract_waveform,
    _ffmpeg_bin,
    _run_ffmpeg,
    _safe_ext,
    _save_wav,
)


def _split_items(text: Any) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for line in raw.splitlines():
        for chunk in re.split(r"[,;]", line):
            item = str(chunk).strip()
            if item:
                out.append(item)
    return out


def _ffconcat_line(path: Path) -> str:
    escaped = str(path).replace("'", r"'\''")
    return f"file '{escaped}'"


def _collect_unique_files(values: Sequence[Any]) -> List[Path]:
    out: List[Path] = []
    seen: set = set()
    for value in values:
        resolved = _extract_input_file(value)
        if resolved is None:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _amp_from_db(value_db: float) -> float:
    return float(10.0 ** (float(value_db) / 20.0))


def _align_channels(waveform: np.ndarray, channels: int) -> np.ndarray:
    c = int(max(1, channels))
    if waveform.shape[0] == c:
        return waveform
    if waveform.shape[0] > c:
        return waveform[:c, :]
    if waveform.shape[0] == 1:
        return np.repeat(waveform, c, axis=0)

    # Generic upmix fallback: repeat and crop.
    reps = int(math.ceil(float(c) / float(max(1, waveform.shape[0]))))
    tiled = np.tile(waveform, (reps, 1))
    return tiled[:c, :]


def _resample_waveform(waveform: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    src = int(max(1, src_rate))
    dst = int(max(1, dst_rate))
    if src == dst:
        return waveform.astype(np.float32, copy=False)

    src_len = int(waveform.shape[1])
    if src_len <= 1:
        return waveform.astype(np.float32, copy=False)

    dst_len = int(max(1, round(float(src_len) * float(dst) / float(src))))
    x_old = np.linspace(0.0, 1.0, num=src_len, endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, num=dst_len, endpoint=False, dtype=np.float64)

    channels = int(waveform.shape[0])
    out = np.zeros((channels, dst_len), dtype=np.float32)
    for idx in range(channels):
        out[idx] = np.interp(x_new, x_old, waveform[idx].astype(np.float64, copy=False)).astype(np.float32)
    return out


def _shift_waveform_samples(waveform: np.ndarray, shift_samples: int) -> np.ndarray:
    shift = int(shift_samples)
    src = waveform.astype(np.float32, copy=False)
    if shift == 0:
        return src
    channels = int(src.shape[0])
    if shift > 0:
        pad = np.zeros((channels, shift), dtype=np.float32)
        return np.concatenate([pad, src], axis=1)

    trim = int(min(src.shape[1], abs(shift)))
    if trim >= src.shape[1]:
        return np.zeros((channels, 1), dtype=np.float32)
    return src[:, trim:]


def _save_audio_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    target: Path,
    ext: str,
) -> Tuple[bool, str]:
    fmt = _safe_ext(ext)
    if fmt == "wav":
        return _save_wav(target, waveform=waveform, sample_rate=int(sample_rate))

    temp_dir = _temp_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = _resolve_output_file(out_dir=temp_dir, stem=f"{target.stem}_src", ext="wav", overwrite=False)
    ok, error = _save_wav(temp_wav, waveform=waveform, sample_rate=int(sample_rate))
    if not ok:
        return False, error

    trans_ok, trans_err = _copy_or_transcode(source=temp_wav, target=target, ext=fmt, kind="audio")
    try:
        temp_wav.unlink(missing_ok=True)
    except Exception:
        pass
    if not trans_ok:
        return False, trans_err
    return True, ""


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


def _save_gif_or_webp_with_durations(
    frames: List[Image.Image],
    durations_sec: List[float],
    target: Path,
    fmt: str,
) -> Tuple[bool, str]:
    if not frames:
        return False, "No frames to save"

    mode = _safe_ext(fmt)
    if mode not in {"gif", "webp"}:
        return False, f"Unsupported format '{mode}'"

    sequence = [f.convert("RGB") for f in frames]
    first = sequence[0]
    rest = sequence[1:]
    ms_values = [int(max(1, round(float(d) * 1000.0))) for d in (durations_sec or [0.083] * len(sequence))]
    if len(ms_values) < len(sequence):
        ms_values += [ms_values[-1] if ms_values else 83] * (len(sequence) - len(ms_values))

    try:
        if mode == "gif":
            first.save(
                target,
                format="GIF",
                save_all=True,
                append_images=rest,
                duration=ms_values,
                loop=0,
                optimize=False,
            )
        else:
            first.save(
                target,
                format="WEBP",
                save_all=True,
                append_images=rest,
                duration=ms_values,
                loop=0,
                quality=90,
                method=6,
            )
    except Exception as exc:
        return False, str(exc)
    return True, ""


def _parse_scene_ranges(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            return []
    else:
        parsed = value

    if not isinstance(parsed, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            out.append(item)
    return out


class MKRTrimVideoByTime:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "start_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.01}),
                "end_sec": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 86400.0, "step": 0.01}),
                "output_format": (["auto", "mp4", "mov", "webm", "gif", "webp"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_trim_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "reencode": ("BOOLEAN", {"default": True}),
                "keep_audio": ("BOOLEAN", {"default": True}),
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
        start_sec: float = 0.0,
        end_sec: float = -1.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_trim_video",
        subfolder: str = "",
        overwrite: bool = False,
        reencode: bool = True,
        keep_audio: bool = True,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        source = _extract_input_file(video)
        if source is None:
            warnings.append("Video input could not be resolved to a file path")
            return (_make_video_payload(path=None), "", _json_text({"warnings": warnings}))

        src_ext = _safe_ext(source.suffix)
        fmt = _safe_ext(output_format)
        if fmt == "auto":
            fmt = src_ext if src_ext else "mp4"
        if fmt not in {"mp4", "mov", "webm", "gif", "webp"}:
            fmt = "mp4"
            warnings.append("Unsupported output format, using mp4")

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_trim_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        start = float(max(0.0, start_sec))
        end = float(end_sec)

        # Lightweight fallback for GIF/WEBP when ffmpeg is unavailable.
        if not _ffmpeg_bin() and src_ext in {"gif", "webp"} and fmt in {"gif", "webp"}:
            try:
                frames, durations = _load_gif_or_webp(source)
                if not frames:
                    raise ValueError("No frames in source")
                times: List[Tuple[float, int]] = []
                t = 0.0
                for idx, d in enumerate(durations):
                    times.append((t, idx))
                    t += float(d)
                max_end = t
                end_eff = max_end if end <= start else min(end, max_end)

                chosen_idx = [idx for (t0, idx) in times if t0 >= start and t0 < end_eff]
                if not chosen_idx:
                    if times:
                        nearest = min(times, key=lambda pair: abs(pair[0] - start))[1]
                        chosen_idx = [nearest]

                trimmed = [frames[idx] for idx in chosen_idx]
                trimmed_durs = [durations[idx] for idx in chosen_idx]
                ok, err = _save_gif_or_webp_with_durations(trimmed, trimmed_durs, target=target, fmt=fmt)
                if not ok:
                    warnings.append(f"Trim fallback failed: {err}")
                else:
                    metadata, meta_warn = _read_video_metadata(target)
                    warnings.extend(meta_warn)
                    payload = _make_video_payload(path=target, metadata=metadata)
                    summary = {
                        "output_path": str(target),
                        "trim_start_sec": start,
                        "trim_end_sec": end,
                        "warnings": warnings,
                    }
                    return (payload, str(target), _json_text(summary))
            except Exception as exc:
                warnings.append(f"GIF/WEBP trim fallback error: {exc}")

        if not _ffmpeg_bin():
            warnings.append("ffmpeg is not available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        args: List[str] = ["-y", "-ss", f"{start:.6f}", "-i", str(source)]
        if end > start:
            args += ["-to", f"{end:.6f}"]
        if not bool(keep_audio):
            args += ["-an"]

        if bool(reencode):
            if fmt in {"mp4", "mov", "webm"}:
                codec = _video_codec_args(fmt)
                if codec is None:
                    warnings.append(f"No codec for format '{fmt}'")
                    return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))
                args += codec
            elif fmt == "gif":
                args += ["-an", "-vf", "fps=15"]
            elif fmt == "webp":
                args += ["-an", "-loop", "0"]
        else:
            if fmt == src_ext:
                args += ["-c", "copy"]
            else:
                warnings.append("Stream copy requested with different format; re-encoding instead")
                codec = _video_codec_args(fmt)
                if codec:
                    args += codec

        args += [str(target)]

        ok, error = _run_ffmpeg(args)
        if not ok:
            warnings.append(f"Trim failed: {error}")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        metadata, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=metadata)
        summary = {
            "output_path": str(target),
            "trim_start_sec": start,
            "trim_end_sec": end,
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRConcatVideos:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_a": ("*",),
                "video_b": ("*",),
                "output_format": (["auto", "mp4", "mov", "webm", "gif", "webp"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_concat_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "stream_copy_if_possible": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "video_c": ("*",),
                "video_paths": ("STRING", {"default": "", "multiline": True}),
                "filename_label": ("STRING", {"default": "", "multiline": False}),
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
        output_format: str = "auto",
        filename_prefix: str = "MKR_concat_video",
        subfolder: str = "",
        overwrite: bool = False,
        stream_copy_if_possible: bool = True,
        video_c: Any = None,
        video_paths: str = "",
        filename_label: str = "",
    ):
        warnings: List[str] = []
        extra_values: List[Any] = [video_a, video_b]
        if video_c is not None:
            extra_values.append(video_c)
        for token in _split_items(video_paths):
            extra_values.append(token)

        sources = _collect_unique_files(extra_values)
        if len(sources) < 2:
            warnings.append("At least two video inputs are required")
            payload = _make_video_payload(path=sources[0] if sources else None)
            return (payload, "", _json_text({"warnings": warnings}))

        first_ext = _safe_ext(sources[0].suffix)
        fmt = _safe_ext(output_format)
        if fmt == "auto":
            fmt = first_ext if first_ext in {"mp4", "mov", "webm", "gif", "webp"} else "mp4"
        if fmt not in {"mp4", "mov", "webm", "gif", "webp"}:
            fmt = "mp4"
            warnings.append("Unsupported output format, using mp4")

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_concat_video")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        # GIF/WEBP fallback path without ffmpeg.
        if not _ffmpeg_bin() and fmt in {"gif", "webp"} and all(_safe_ext(p.suffix) in {"gif", "webp"} for p in sources):
            try:
                all_frames: List[Image.Image] = []
                all_durations: List[float] = []
                for src in sources:
                    frames, durations = _load_gif_or_webp(src)
                    all_frames.extend(frames)
                    all_durations.extend(durations)

                ok, err = _save_gif_or_webp_with_durations(all_frames, all_durations, target=target, fmt=fmt)
                if not ok:
                    warnings.append(f"GIF/WEBP concat fallback failed: {err}")
                else:
                    metadata, meta_warnings = _read_video_metadata(target)
                    warnings.extend(meta_warnings)
                    payload = _make_video_payload(path=target, metadata=metadata)
                    summary = {
                        "output_path": str(target),
                        "source_count": len(sources),
                        "warnings": warnings,
                    }
                    return (payload, str(target), _json_text(summary))
            except Exception as exc:
                warnings.append(f"GIF/WEBP concat fallback error: {exc}")

        if not _ffmpeg_bin():
            warnings.append("ffmpeg is not available")
            return (_make_video_payload(path=sources[0]), "", _json_text({"warnings": warnings}))

        temp_dir = _temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        concat_file = _resolve_output_file(out_dir=temp_dir, stem=f"{stem}_concat", ext="txt", overwrite=False)
        try:
            concat_file.write_text("\n".join(_ffconcat_line(path) for path in sources), encoding="utf-8")
        except Exception as exc:
            warnings.append(f"Failed to build concat list: {exc}")
            return (_make_video_payload(path=sources[0]), "", _json_text({"warnings": warnings}))

        same_ext = len({_safe_ext(p.suffix) for p in sources}) == 1
        tried_copy = False
        if bool(stream_copy_if_possible) and same_ext and _safe_ext(sources[0].suffix) == fmt:
            tried_copy = True
            ok, error = _run_ffmpeg(
                [
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-c",
                    "copy",
                    str(target),
                ]
            )
            if ok:
                try:
                    concat_file.unlink(missing_ok=True)
                except Exception:
                    pass
                metadata, meta_warnings = _read_video_metadata(target)
                warnings.extend(meta_warnings)
                payload = _make_video_payload(path=target, metadata=metadata)
                summary = {
                    "output_path": str(target),
                    "source_count": len(sources),
                    "mode": "stream_copy",
                    "warnings": warnings,
                }
                return (payload, str(target), _json_text(summary))
            warnings.append(f"Stream copy failed, retrying with re-encode: {error}")

        codec = None
        if fmt in {"mp4", "mov", "webm"}:
            codec = _video_codec_args(fmt)
        if codec is None and fmt in {"gif", "webp"}:
            codec = ["-an", "-vf", "fps=15"] if fmt == "gif" else ["-an", "-loop", "0"]
        if codec is None:
            warnings.append(f"No codec profile for format '{fmt}'")
            return (_make_video_payload(path=sources[0]), "", _json_text({"warnings": warnings}))

        ok, error = _run_ffmpeg(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                *codec,
                str(target),
            ]
        )
        try:
            concat_file.unlink(missing_ok=True)
        except Exception:
            pass

        if not ok:
            warnings.append(f"Concat failed: {error}")
            payload = _make_video_payload(path=sources[0])
            return (payload, "", _json_text({"warnings": warnings, "tried_copy": tried_copy}))

        metadata, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=metadata)
        summary = {
            "output_path": str(target),
            "source_count": len(sources),
            "mode": "reencode",
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRSelectSceneRange:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scene_ranges_json": ("STRING", {"default": "[]", "multiline": True}),
                "scene_index": ("INT", {"default": 0, "min": 0, "max": 100000, "step": 1}),
            }
        }

    RETURN_TYPES = ("FLOAT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("start_sec", "end_sec", "duration_sec", "scene_json")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(self, scene_ranges_json: str = "[]", scene_index: int = 0):
        ranges = _parse_scene_ranges(scene_ranges_json)
        if not ranges:
            default = {"index": 0, "start_time": 0.0, "end_time": 0.0, "duration": 0.0}
            return (0.0, 0.0, 0.0, _json_text(default))

        idx = int(max(0, min(int(scene_index), len(ranges) - 1)))
        selected = ranges[idx]
        start = float(selected.get("start_time", 0.0) or 0.0)
        end = float(selected.get("end_time", start) or start)
        duration = float(max(0.0, end - start))
        if "duration" not in selected:
            selected = {**selected, "duration": duration}
        return (start, end, duration, _json_text(selected))


class MKRAudioMix:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_a": ("*",),
                "audio_b": ("*",),
                "gain_a_db": ("FLOAT", {"default": 0.0, "min": -40.0, "max": 40.0, "step": 0.1}),
                "gain_b_db": ("FLOAT", {"default": 0.0, "min": -40.0, "max": 40.0, "step": 0.1}),
                "offset_b_ms": ("INT", {"default": 0, "min": -600000, "max": 600000, "step": 1}),
                "normalize_peak": ("BOOLEAN", {"default": True}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_mix"}),
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
        audio_a: Any,
        audio_b: Any,
        gain_a_db: float = 0.0,
        gain_b_db: float = 0.0,
        offset_b_ms: int = 0,
        normalize_peak: bool = True,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_mix",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        path_a = _extract_input_file(audio_a)
        path_b = _extract_input_file(audio_b)
        offset_ms = int(offset_b_ms)

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_audio_mix")

        fmt = _safe_ext(output_format)
        if fmt == "auto":
            ext_a = _safe_ext(path_a.suffix) if path_a is not None else ""
            fmt = ext_a if ext_a in {"wav", "mp3", "flac", "ogg"} else "wav"
        if fmt not in {"wav", "mp3", "flac", "ogg"}:
            fmt = "wav"
            warnings.append("Unsupported output format, using wav")

        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        if path_a is not None and path_b is not None and _ffmpeg_bin():
            codec = _audio_codec_args(fmt)
            if codec is None:
                warnings.append(f"No codec profile for '{fmt}'")
                return (_make_audio_payload(path=path_a), "", 0.0, _json_text({"warnings": warnings}))

            filter_parts = [
                f"[0:a]volume={float(gain_a_db):.3f}dB[a0]",
                f"[1:a]volume={float(gain_b_db):.3f}dB[a1]",
            ]
            mix_input_b = "a1"
            if offset_ms > 0:
                filter_parts.append(f"[a1]adelay={int(offset_ms)}:all=1[a1o]")
                mix_input_b = "a1o"
            elif offset_ms < 0:
                filter_parts.append(f"[a1]atrim=start={abs(float(offset_ms)) / 1000.0:.6f},asetpts=PTS-STARTPTS[a1o]")
                mix_input_b = "a1o"
            filter_parts.append(f"[a0][{mix_input_b}]amix=inputs=2:normalize=0[m]")
            filter_chain = ";".join(filter_parts)

            args: List[str] = [
                "-y",
                "-i",
                str(path_a),
                "-i",
                str(path_b),
                "-filter_complex",
                filter_chain,
                "-map",
                "[m]",
            ]
            if bool(normalize_peak):
                args += ["-af", "alimiter=limit=0.98"]
            args += codec
            args += [str(target)]

            ok, error = _run_ffmpeg(args)
            if not ok:
                warnings.append(f"File-based mix failed: {error}")
            else:
                duration = _read_audio_duration(target)
                payload = _make_audio_payload(path=target)
                summary = {
                    "output_path": str(target),
                    "mode": "file_ffmpeg",
                    "offset_b_ms": int(offset_ms),
                    "warnings": warnings,
                }
                return (payload, str(target), float(duration), _json_text(summary))

        wa, sra = _extract_waveform(audio_a)
        wb, srb = _extract_waveform(audio_b)
        if wa is None or wb is None:
            warnings.append("Waveform mix fallback requires waveform-compatible inputs on both audio_a and audio_b")
            payload = _make_audio_payload(path=path_a or path_b)
            return (payload, "", 0.0, _json_text({"warnings": warnings}))

        target_sr = int(max(1, max(int(sra), int(srb))))
        ra = _resample_waveform(wa, int(sra), target_sr)
        rb = _resample_waveform(wb, int(srb), target_sr)
        rb = _shift_waveform_samples(rb, int(round(float(offset_ms) * float(target_sr) / 1000.0)))

        channels = max(int(ra.shape[0]), int(rb.shape[0]))
        ra = _align_channels(ra, channels)
        rb = _align_channels(rb, channels)

        total_samples = int(max(ra.shape[1], rb.shape[1]))
        if ra.shape[1] < total_samples:
            pad = np.zeros((channels, total_samples - ra.shape[1]), dtype=np.float32)
            ra = np.concatenate([ra, pad], axis=1)
        if rb.shape[1] < total_samples:
            pad = np.zeros((channels, total_samples - rb.shape[1]), dtype=np.float32)
            rb = np.concatenate([rb, pad], axis=1)

        mixed = ra * _amp_from_db(gain_a_db) + rb * _amp_from_db(gain_b_db)
        if bool(normalize_peak):
            peak = float(np.max(np.abs(mixed)))
            if peak > 1e-9:
                mixed *= float(0.98 / peak)
        mixed = np.clip(mixed, -1.0, 1.0).astype(np.float32, copy=False)

        ok, error = _save_audio_waveform(mixed, sample_rate=target_sr, target=target, ext=fmt)
        if not ok:
            warnings.append(f"Waveform mix failed: {error}")
            return (_make_audio_payload(path=None, sample_rate=target_sr), "", 0.0, _json_text({"warnings": warnings}))

        duration = float(mixed.shape[1] / float(max(1, target_sr)))
        payload = _make_audio_payload(path=target, sample_rate=target_sr)
        payload["waveform"] = torch.from_numpy(mixed)
        summary = {
            "output_path": str(target),
            "mode": "waveform",
            "offset_b_ms": int(offset_ms),
            "warnings": warnings,
        }
        return (payload, str(target), duration, _json_text(summary))


class MKRAudioConcat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_a": ("*",),
                "audio_b": ("*",),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_concat"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "stream_copy_if_possible": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "audio_c": ("*",),
                "audio_paths": ("STRING", {"default": "", "multiline": True}),
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio_a: Any,
        audio_b: Any,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_concat",
        subfolder: str = "",
        overwrite: bool = False,
        stream_copy_if_possible: bool = True,
        audio_c: Any = None,
        audio_paths: str = "",
        filename_label: str = "",
    ):
        warnings: List[str] = []
        entries: List[Any] = [audio_a, audio_b]
        if audio_c is not None:
            entries.append(audio_c)
        entries.extend(_split_items(audio_paths))

        sources = _collect_unique_files(entries)

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_audio_concat")

        fmt = _safe_ext(output_format)
        if fmt == "auto":
            first_ext = _safe_ext(sources[0].suffix) if sources else ""
            fmt = first_ext if first_ext in {"wav", "mp3", "flac", "ogg"} else "wav"
        if fmt not in {"wav", "mp3", "flac", "ogg"}:
            fmt = "wav"
            warnings.append("Unsupported output format, using wav")

        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        if len(sources) >= 2 and _ffmpeg_bin():
            temp_dir = _temp_dir()
            temp_dir.mkdir(parents=True, exist_ok=True)
            concat_file = _resolve_output_file(out_dir=temp_dir, stem=f"{stem}_concat", ext="txt", overwrite=False)
            try:
                concat_file.write_text("\n".join(_ffconcat_line(path) for path in sources), encoding="utf-8")
            except Exception as exc:
                warnings.append(f"Failed to build concat list: {exc}")
                concat_file = None

            if concat_file is not None:
                same_ext = len({_safe_ext(path.suffix) for path in sources}) == 1
                copy_ok = False
                if bool(stream_copy_if_possible) and same_ext and _safe_ext(sources[0].suffix) == fmt:
                    ok, _ = _run_ffmpeg(
                        [
                            "-y",
                            "-f",
                            "concat",
                            "-safe",
                            "0",
                            "-i",
                            str(concat_file),
                            "-c",
                            "copy",
                            str(target),
                        ]
                    )
                    copy_ok = bool(ok)

                if not copy_ok:
                    codec = _audio_codec_args(fmt)
                    if codec is None:
                        warnings.append(f"No codec profile for '{fmt}'")
                    else:
                        ok, error = _run_ffmpeg(
                            [
                                "-y",
                                "-f",
                                "concat",
                                "-safe",
                                "0",
                                "-i",
                                str(concat_file),
                                *codec,
                                str(target),
                            ]
                        )
                        if not ok:
                            warnings.append(f"File concat failed: {error}")
                        else:
                            try:
                                concat_file.unlink(missing_ok=True)
                            except Exception:
                                pass
                            duration = _read_audio_duration(target)
                            payload = _make_audio_payload(path=target)
                            summary = {
                                "output_path": str(target),
                                "source_count": len(sources),
                                "mode": "file_ffmpeg",
                                "warnings": warnings,
                            }
                            return (payload, str(target), float(duration), _json_text(summary))

                try:
                    concat_file.unlink(missing_ok=True)
                except Exception:
                    pass

        # Waveform fallback path.
        wave_inputs: List[Tuple[np.ndarray, int]] = []
        for candidate in [audio_a, audio_b, audio_c]:
            if candidate is None:
                continue
            wave, sr = _extract_waveform(candidate)
            if wave is None:
                continue
            wave_inputs.append((wave, int(sr)))

        if len(wave_inputs) < 2:
            warnings.append("Concatenation requires at least two audio file inputs (ffmpeg) or two waveform-compatible inputs")
            payload = _make_audio_payload(path=sources[0] if sources else None)
            return (payload, "", 0.0, _json_text({"warnings": warnings}))

        target_sr = int(max(sr for _, sr in wave_inputs))
        target_channels = int(max(wf.shape[0] for wf, _ in wave_inputs))

        parts: List[np.ndarray] = []
        for wf, sr in wave_inputs:
            rw = _resample_waveform(wf, src_rate=sr, dst_rate=target_sr)
            rw = _align_channels(rw, target_channels)
            parts.append(rw)

        combined = np.concatenate(parts, axis=1)
        combined = np.clip(combined, -1.0, 1.0).astype(np.float32, copy=False)

        ok, error = _save_audio_waveform(combined, sample_rate=target_sr, target=target, ext=fmt)
        if not ok:
            warnings.append(f"Waveform concat failed: {error}")
            return (_make_audio_payload(path=None, sample_rate=target_sr), "", 0.0, _json_text({"warnings": warnings}))

        duration = float(combined.shape[1] / float(max(1, target_sr)))
        payload = _make_audio_payload(path=target, sample_rate=target_sr)
        payload["waveform"] = torch.from_numpy(combined)
        summary = {
            "output_path": str(target),
            "source_count": len(parts),
            "mode": "waveform",
            "warnings": warnings,
        }
        return (payload, str(target), duration, _json_text(summary))


class MKRBeatMarkerGrid:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bpm": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 400.0, "step": 0.1}),
                "duration_sec": ("FLOAT", {"default": 60.0, "min": 0.0, "max": 86400.0, "step": 0.01}),
                "beats_per_bar": ("INT", {"default": 4, "min": 1, "max": 16, "step": 1}),
                "offset_sec": ("FLOAT", {"default": 0.0, "min": -60.0, "max": 60.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("beat_markers_json", "bar_markers_json", "beat_count", "bar_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        bpm: float = 120.0,
        duration_sec: float = 60.0,
        beats_per_bar: int = 4,
        offset_sec: float = 0.0,
    ):
        tempo = float(max(1.0, bpm))
        duration = float(max(0.0, duration_sec))
        bar_size = int(max(1, beats_per_bar))
        beat_interval = float(60.0 / tempo)
        offset = float(offset_sec)

        beats: List[float] = []
        bars: List[float] = []

        if duration <= 0.0:
            summary = {
                "bpm": tempo,
                "duration_sec": duration,
                "beat_interval_sec": beat_interval,
                "beats_per_bar": bar_size,
            }
            return (_json_text(beats), _json_text(bars), 0, 0, _json_text(summary))

        idx = 0
        t = offset
        while t < 0.0:
            idx += 1
            t += beat_interval

        while t <= duration + 1e-9:
            stamp = float(round(t, 6))
            beats.append(stamp)
            if idx % bar_size == 0:
                bars.append(stamp)
            idx += 1
            t += beat_interval

        summary = {
            "bpm": tempo,
            "duration_sec": duration,
            "beat_interval_sec": beat_interval,
            "beats_per_bar": bar_size,
            "beat_count": len(beats),
            "bar_count": len(bars),
        }
        return (_json_text(beats), _json_text(bars), len(beats), len(bars), _json_text(summary))
