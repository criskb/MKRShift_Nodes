import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image
import torch

from ..categories import MEDIA_ANALYSIS, MEDIA_IO
from .media_batch_video_nodes import _decode_video_to_pil, _save_video_from_pil
from .media_batch_transform_nodes import _load_audio_waveform
from ..xmedia_nodes import _json_text, _make_video_payload, _read_video_metadata, _run_ffprobe_json
from ..xpresave import _output_dir, _resolve_output_file, _sanitize_basename
from ..xpresave_media import _extract_input_file, _ffmpeg_bin, _run_ffmpeg, _safe_ext


_VIDEO_EXTS = {"mp4", "mov", "mkv", "webm", "avi", "gif", "webp"}
_AUDIO_EXTS = {"wav", "mp3", "flac", "ogg", "m4a", "aac", "aiff"}


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _is_video_path(path: Optional[Path]) -> bool:
    if path is None:
        return False
    return _safe_ext(path.suffix) in _VIDEO_EXTS


def _is_audio_path(path: Optional[Path]) -> bool:
    if path is None:
        return False
    return _safe_ext(path.suffix) in _AUDIO_EXTS


def _resolve_video_candidate(primary: Any, video: Any = None) -> Any:
    if video is not None:
        return video
    return primary


def _resolve_audio_candidate(primary: Any, audio: Any = None) -> Any:
    if audio is not None:
        return audio
    return primary


def _luma_mean(frame: Image.Image) -> float:
    arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
    lum = arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722
    return float(np.mean(lum) / 255.0)


def _contiguous_true_runs(flags: Sequence[bool], min_len: int) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    run_start: Optional[int] = None
    for idx, flag in enumerate(flags):
        if flag and run_start is None:
            run_start = idx
            continue
        if (not flag) and run_start is not None:
            end = idx - 1
            if (end - run_start + 1) >= int(max(1, min_len)):
                out.append((int(run_start), int(end)))
            run_start = None
    if run_start is not None:
        end = len(flags) - 1
        if (end - run_start + 1) >= int(max(1, min_len)):
            out.append((int(run_start), int(end)))
    return out


def _ranges_to_json(runs: Sequence[Tuple[int, int]], fps: float, offset: int = 0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    fp = float(max(1.0, fps))
    for start, end in runs:
        s = int(start) + int(offset)
        e = int(end) + int(offset)
        out.append(
            {
                "start_frame": int(s),
                "end_frame": int(e),
                "length_frames": int(max(0, e - s + 1)),
                "start_sec": float(round(float(s) / fp, 6)),
                "end_sec": float(round(float(e + 1) / fp, 6)),
            }
        )
    return out


def _audio_stats(waveform: np.ndarray) -> Dict[str, float]:
    data = waveform.astype(np.float32, copy=False)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(data)) + 1e-12)) if data.size else 0.0
    return {
        "peak": float(peak),
        "peak_db": float(20.0 * math.log10(max(1e-9, peak))),
        "rms": float(rms),
        "rms_db": float(20.0 * math.log10(max(1e-9, rms))),
    }


def _approx_integrated_lufs(waveform: np.ndarray) -> float:
    if waveform.size == 0:
        return -120.0
    mono = np.mean(waveform.astype(np.float32, copy=False), axis=0)
    rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
    return float(20.0 * math.log10(max(1e-9, rms)))


def _approx_lra_db(waveform: np.ndarray, sample_rate: int, window_ms: int = 3000) -> float:
    if waveform.size == 0:
        return 0.0
    mono = np.mean(waveform.astype(np.float32, copy=False), axis=0)
    win = int(max(64, round(float(max(50, window_ms)) * float(max(1, sample_rate)) / 1000.0)))
    if mono.size < win:
        return 0.0
    vals: List[float] = []
    step = max(1, win // 2)
    for i in range(0, mono.size - win + 1, step):
        seg = mono[i : i + win]
        rms = float(np.sqrt(np.mean(np.square(seg)) + 1e-12))
        vals.append(float(20.0 * math.log10(max(1e-9, rms))))
    if not vals:
        return 0.0
    lo = float(np.percentile(vals, 10))
    hi = float(np.percentile(vals, 95))
    return float(max(0.0, hi - lo))


def _fit_contain(frame: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src = frame.convert("RGB")
    sw, sh = src.size
    scale = min(float(target_w) / float(max(1, sw)), float(target_h) / float(max(1, sh)))
    nw = int(max(1, round(sw * scale)))
    nh = int(max(1, round(sh * scale)))
    resized = src.resize((nw, nh), resample=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (int(target_w), int(target_h)), (0, 0, 0))
    x = int((target_w - nw) // 2)
    y = int((target_h - nh) // 2)
    canvas.paste(resized, (x, y))
    return canvas


def _ffprobe_audio_sample_rate(path: Path, fallback: int = 44100) -> int:
    data, _ = _run_ffprobe_json(path)
    if not isinstance(data, dict):
        return int(max(1, fallback))
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("codec_type", "")).lower() != "audio":
            continue
        try:
            v = int(float(stream.get("sample_rate") or 0))
            if v > 0:
                return int(v)
        except Exception:
            continue
    return int(max(1, fallback))


def _sec_to_tc(seconds: float, fps: float) -> str:
    f = float(max(1.0, fps))
    total_frames = int(max(0, round(float(max(0.0, seconds)) * f)))
    ff = int(total_frames % int(round(f)))
    total_seconds = int(total_frames // int(round(f)))
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _tc_to_sec(tc: str, fps: float) -> float:
    text = str(tc or "").strip()
    parts = text.split(":")
    if len(parts) != 4:
        return 0.0
    try:
        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2])
        ff = int(parts[3])
    except Exception:
        return 0.0
    f = float(max(1.0, fps))
    return float(hh * 3600 + mm * 60 + ss + (ff / f))


class MKRQualityReport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "media": ("*",),
                "report_profile": (["quick", "standard"], {"default": "standard"}),
            },
            "optional": {
                "video": ("*",),
                "audio": ("*",),
            },
        }

    RETURN_TYPES = ("STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("report_json", "quality_score", "issues_json")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(self, media: Any, report_profile: str = "standard", video: Any = None, audio: Any = None):
        warnings: List[str] = []
        issues: List[Dict[str, Any]] = []
        score = 100.0

        video_input = _resolve_video_candidate(primary=media, video=video)
        audio_input = _resolve_audio_candidate(primary=media, audio=audio)

        video_path = _extract_input_file(video_input)
        if video_path is not None and (not _is_video_path(video_path)):
            video_path = None
        audio_path = _extract_input_file(audio_input)
        if audio_path is not None and (not _is_audio_path(audio_path)):
            audio_path = None

        v_meta: Dict[str, Any] = {"path": "", "fps": 0.0, "duration": 0.0, "frame_count": 0, "width": 0, "height": 0}
        a_meta: Dict[str, Any] = {"path": "", "sample_rate": 0, "channels": 0, "duration": 0.0, "peak_db": -120.0, "rms_db": -120.0}

        if video_path is not None:
            meta, meta_warn = _read_video_metadata(video_path)
            warnings.extend(meta_warn)
            v_meta.update(meta)
            v_meta["path"] = str(video_path)
        else:
            frames, fps_guess, decode_warn = _decode_video_to_pil(video=video_input, requested_fps=0.0, max_frames=200)
            warnings.extend(decode_warn)
            if frames:
                v_meta["fps"] = float(max(1.0, fps_guess))
                v_meta["frame_count"] = int(len(frames))
                v_meta["duration"] = float(len(frames) / max(1.0, float(fps_guess)))
                v_meta["width"], v_meta["height"] = int(frames[0].width), int(frames[0].height)

        wave, sr, _, audio_err = _load_audio_waveform(audio_input)
        if wave is not None:
            stats = _audio_stats(wave)
            a_meta.update(
                {
                    "path": str(audio_path) if audio_path is not None else "",
                    "sample_rate": int(max(1, sr)),
                    "channels": int(wave.shape[0]),
                    "duration": float(wave.shape[1] / float(max(1, sr))),
                    "peak_db": float(stats["peak_db"]),
                    "rms_db": float(stats["rms_db"]),
                    "lufs_approx": float(_approx_integrated_lufs(wave)),
                    "lra_db_approx": float(_approx_lra_db(wave, sample_rate=int(max(1, sr)))),
                }
            )
        elif audio_path is not None:
            sr2 = _ffprobe_audio_sample_rate(audio_path, fallback=44100)
            a_meta["path"] = str(audio_path)
            a_meta["sample_rate"] = int(sr2)
        elif audio_err:
            warnings.append(audio_err)

        # Basic issue scoring.
        if float(v_meta.get("frame_count", 0) or 0) <= 0:
            issues.append({"type": "video_missing", "severity": "error", "message": "No video content detected"})
            score -= 25.0
        else:
            w = int(v_meta.get("width", 0) or 0)
            h = int(v_meta.get("height", 0) or 0)
            if w > 0 and h > 0 and min(w, h) < 480:
                issues.append({"type": "low_resolution", "severity": "warn", "message": f"Low resolution: {w}x{h}"})
                score -= 8.0
            fps = float(v_meta.get("fps", 0.0) or 0.0)
            if fps > 0 and fps < 20.0:
                issues.append({"type": "low_fps", "severity": "warn", "message": f"Low frame rate: {fps:.2f} fps"})
                score -= 6.0

        if float(a_meta.get("duration", 0.0) or 0.0) > 0.0:
            peak_db = float(a_meta.get("peak_db", -120.0) or -120.0)
            if peak_db > -0.2:
                issues.append({"type": "audio_near_clip", "severity": "warn", "message": f"Audio peak is high ({peak_db:.2f} dBFS)"})
                score -= 8.0
            lufs = float(a_meta.get("lufs_approx", -120.0) or -120.0)
            if lufs < -26.0 or lufs > -9.0:
                issues.append({"type": "loudness_out_of_range", "severity": "warn", "message": f"Approx loudness is unusual ({lufs:.1f} LUFS)"})
                score -= 6.0

        vd = float(v_meta.get("duration", 0.0) or 0.0)
        ad = float(a_meta.get("duration", 0.0) or 0.0)
        if vd > 0.0 and ad > 0.0:
            delta = abs(vd - ad)
            if delta > 0.25:
                issues.append({"type": "av_duration_mismatch", "severity": "warn", "message": f"Audio/video duration mismatch ({delta:.2f}s)"})
                score -= min(15.0, delta * 3.0)

        if report_profile == "quick":
            score = max(0.0, min(100.0, score))
        else:
            score = max(0.0, min(100.0, score - (2.0 if warnings else 0.0)))

        report = {
            "profile": str(report_profile),
            "quality_score": round(float(score), 2),
            "video": v_meta,
            "audio": a_meta,
            "issues": issues,
            "warnings": warnings,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        return (_json_text(report), float(round(score, 2)), _json_text(issues))


class MKRBlackFrameDetector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "luma_threshold": ("FLOAT", {"default": 0.03, "min": 0.0, "max": 1.0, "step": 0.001}),
                "min_run_frames": ("INT", {"default": 3, "min": 1, "max": 100000, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("black_ranges_json", "range_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(self, video: Any, luma_threshold: float = 0.03, min_run_frames: int = 3, fallback_fps: float = 24.0):
        warnings: List[str] = []
        frames, fps, decode_warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warn)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return ("[]", 0, _json_text({"warnings": warnings}))

        th = float(_clamp_float(luma_threshold, 0.0, 1.0))
        flags = [(_luma_mean(frame) <= th) for frame in frames]
        runs = _contiguous_true_runs(flags=flags, min_len=int(max(1, min_run_frames)))
        ranges = _ranges_to_json(runs, fps=fps)
        summary = {
            "frame_count": int(len(frames)),
            "black_frame_count": int(sum(1 for f in flags if f)),
            "range_count": int(len(ranges)),
            "threshold": float(th),
            "warnings": warnings,
        }
        return (_json_text(ranges), int(len(ranges)), _json_text(summary))


class MKRFreezeFrameDetector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "diff_threshold": ("FLOAT", {"default": 0.0015, "min": 0.0, "max": 1.0, "step": 0.0001}),
                "min_run_frames": ("INT", {"default": 4, "min": 2, "max": 100000, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("freeze_ranges_json", "range_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(self, video: Any, diff_threshold: float = 0.0015, min_run_frames: int = 4, fallback_fps: float = 24.0):
        warnings: List[str] = []
        frames, fps, decode_warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warn)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if len(frames) < 2:
            warnings.append("Need at least 2 frames")
            return ("[]", 0, _json_text({"warnings": warnings}))

        arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]
        th = float(_clamp_float(diff_threshold, 0.0, 1.0))
        still_flags: List[bool] = []
        for i in range(1, len(arrs)):
            d = float(np.mean(np.abs(arrs[i] - arrs[i - 1])) / 255.0)
            still_flags.append(d <= th)

        # still_flags is between frames, so offset by +1 for frame index mapping.
        runs = _contiguous_true_runs(still_flags, min_len=max(1, int(min_run_frames) - 1))
        ranges = _ranges_to_json(runs, fps=fps, offset=1)
        summary = {
            "frame_count": int(len(frames)),
            "freeze_transitions": int(sum(1 for f in still_flags if f)),
            "range_count": int(len(ranges)),
            "threshold": float(th),
            "warnings": warnings,
        }
        return (_json_text(ranges), int(len(ranges)), _json_text(summary))


class MKRAudioClippingDetector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "clip_threshold_db": ("FLOAT", {"default": -0.3, "min": -24.0, "max": -0.01, "step": 0.01}),
                "min_clip_ms": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "STRING")
    RETURN_NAMES = ("clip_ranges_json", "clipped_samples", "clip_ratio", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(self, audio: Any, clip_threshold_db: float = -0.3, min_clip_ms: float = 1.0):
        warnings: List[str] = []
        waveform, sample_rate, _, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return ("[]", 0, 0.0, _json_text({"warnings": warnings}))

        data = waveform.astype(np.float32, copy=False)
        sr = int(max(1, sample_rate))
        threshold = float(10.0 ** (float(clip_threshold_db) / 20.0))
        mono_peak = np.max(np.abs(data), axis=0)
        flags = mono_peak >= threshold
        min_len = int(max(1, round(float(max(0.0, min_clip_ms)) * float(sr) / 1000.0)))

        runs = _contiguous_true_runs(flags.tolist(), min_len=min_len)
        ranges: List[Dict[str, Any]] = []
        for s, e in runs:
            ranges.append(
                {
                    "start_sample": int(s),
                    "end_sample": int(e),
                    "length_samples": int(e - s + 1),
                    "start_sec": float(round(float(s) / float(sr), 6)),
                    "end_sec": float(round(float(e + 1) / float(sr), 6)),
                }
            )

        clipped = int(np.sum(flags))
        ratio = float(clipped / max(1, flags.size))
        summary = {
            "sample_rate": int(sr),
            "channels": int(data.shape[0]),
            "total_samples": int(flags.size),
            "clipped_samples": int(clipped),
            "clip_ratio": float(ratio),
            "threshold_db": float(clip_threshold_db),
            "warnings": warnings,
        }
        return (_json_text(ranges), int(clipped), float(ratio), _json_text(summary))


class MKRLoudnessMeter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "window_ms": ("INT", {"default": 400, "min": 50, "max": 10000, "step": 10}),
            }
        }

    RETURN_TYPES = ("FLOAT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("integrated_lufs_approx", "true_peak_db", "lra_db_approx", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_ANALYSIS

    def run(self, audio: Any, window_ms: int = 400):
        warnings: List[str] = []
        waveform, sample_rate, _, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return (-120.0, -120.0, 0.0, _json_text({"warnings": warnings}))

        data = waveform.astype(np.float32, copy=False)
        stats = _audio_stats(data)
        integrated = float(_approx_integrated_lufs(data))
        lra = float(_approx_lra_db(data, sample_rate=int(max(1, sample_rate)), window_ms=int(window_ms)))
        summary = {
            "sample_rate": int(max(1, sample_rate)),
            "channels": int(data.shape[0]),
            "duration_sec": float(data.shape[1] / float(max(1, sample_rate))),
            "integrated_lufs_approx": float(integrated),
            "true_peak_db": float(stats["peak_db"]),
            "lra_db_approx": float(lra),
            "warnings": warnings,
        }
        return (float(integrated), float(stats["peak_db"]), float(lra), _json_text(summary))


class MKRProxyTranscode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "scale_percent": ("INT", {"default": 50, "min": 5, "max": 100, "step": 1}),
                "target_fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 240.0, "step": 0.1}),
                "output_format": (["mp4", "mov", "webm", "gif", "webp"], {"default": "mp4"}),
                "video_bitrate_kbps": ("INT", {"default": 3000, "min": 200, "max": 50000, "step": 50}),
                "keep_audio": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": "MKR_proxy"}),
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
        video: Any,
        scale_percent: int = 50,
        target_fps: float = 0.0,
        output_format: str = "mp4",
        video_bitrate_kbps: int = 3000,
        keep_audio: bool = True,
        filename_prefix: str = "MKR_proxy",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        source = _extract_input_file(video)
        fmt = _safe_ext(output_format or "mp4")
        if fmt not in {"mp4", "mov", "webm", "gif", "webp"}:
            fmt = "mp4"
            warnings.append("Unsupported output format, using mp4")

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_proxy")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        sc = int(max(5, min(100, scale_percent)))
        fps_opt = float(max(0.0, target_fps))
        kbps = int(max(200, video_bitrate_kbps))

        if source is not None and _ffmpeg_bin():
            vf: List[str] = [f"scale=trunc(iw*{sc}/100/2)*2:trunc(ih*{sc}/100/2)*2"]
            if fps_opt > 0.0:
                vf.append(f"fps={fps_opt:.6f}")

            args: List[str] = ["-y", "-i", str(source), "-vf", ",".join(vf)]
            if fmt == "mp4":
                args += ["-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{kbps}k", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            elif fmt == "mov":
                args += ["-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{kbps}k", "-pix_fmt", "yuv420p"]
            elif fmt == "webm":
                args += ["-c:v", "libvpx-vp9", "-b:v", f"{kbps}k", "-crf", "32"]
            elif fmt == "gif":
                args += ["-an"]
            elif fmt == "webp":
                args += ["-an", "-loop", "0"]

            if bool(keep_audio) and fmt in {"mp4", "mov", "webm"}:
                if fmt == "webm":
                    args += ["-c:a", "libopus", "-b:a", "128k"]
                else:
                    args += ["-c:a", "aac", "-b:a", "128k"]
            else:
                args += ["-an"]
            args += [str(target)]

            ok, error = _run_ffmpeg(args)
            if ok:
                meta, meta_warn = _read_video_metadata(target)
                warnings.extend(meta_warn)
                payload = _make_video_payload(path=target, metadata=meta)
                summary = {
                    "output_path": str(target),
                    "mode": "ffmpeg",
                    "scale_percent": int(sc),
                    "target_fps": float(fps_opt),
                    "warnings": warnings,
                }
                return (payload, str(target), _json_text(summary))
            warnings.append(f"ffmpeg proxy transcode failed: {error}")

        frames, fps, decode_warn = _decode_video_to_pil(video=video, requested_fps=fps_opt, max_frames=0)
        warnings.extend(decode_warn)
        if not frames:
            warnings.append("No video content available for fallback proxy")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        out_frames: List[Image.Image] = []
        for frame in frames:
            nw = int(max(1, round(float(frame.width) * float(sc) / 100.0)))
            nh = int(max(1, round(float(frame.height) * float(sc) / 100.0)))
            out_frames.append(frame.convert("RGB").resize((nw, nh), resample=Image.Resampling.BILINEAR))

        save_fps = float(max(1.0, fps if fps > 0.0 else 24.0))
        ok, error = _save_video_from_pil(out_frames, fps=save_fps, target=target, fmt=fmt if fmt in {"gif", "webp", "mp4", "mov", "webm"} else "gif")
        if not ok:
            warnings.append(f"Fallback proxy save failed: {error}")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        meta, meta_warn = _read_video_metadata(target)
        warnings.extend(meta_warn)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "mode": "frame_fallback",
            "scale_percent": int(sc),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRExportPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "preset": (
                    [
                        "youtube_1080p",
                        "youtube_4k",
                        "reels_1080x1920",
                        "tiktok_1080x1920",
                        "square_1080",
                        "master_prores",
                    ],
                    {"default": "youtube_1080p"},
                ),
                "keep_audio": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": "MKR_export"}),
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
        video: Any,
        preset: str = "youtube_1080p",
        keep_audio: bool = True,
        filename_prefix: str = "MKR_export",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        source = _extract_input_file(video)

        preset_name = str(preset or "youtube_1080p").strip().lower()
        ext = "mp4"
        tw, th, fps, kbps = 1920, 1080, 30.0, 8000
        if preset_name == "youtube_4k":
            tw, th, fps, kbps = 3840, 2160, 30.0, 30000
            ext = "mp4"
        elif preset_name in {"reels_1080x1920", "tiktok_1080x1920"}:
            tw, th, fps, kbps = 1080, 1920, 30.0, 8000
            ext = "mp4"
        elif preset_name == "square_1080":
            tw, th, fps, kbps = 1080, 1080, 30.0, 7000
            ext = "mp4"
        elif preset_name == "master_prores":
            tw, th, fps, kbps = 1920, 1080, 24.0, 20000
            ext = "mov"

        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_export")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=ext, overwrite=bool(overwrite))

        if source is not None and _ffmpeg_bin():
            vf = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black,fps={fps:.6f}"
            args: List[str] = ["-y", "-i", str(source), "-vf", vf]
            if preset_name == "master_prores":
                args += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
            else:
                args += ["-c:v", "libx264", "-preset", "slow", "-b:v", f"{kbps}k", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

            if bool(keep_audio):
                if ext == "mov" and preset_name == "master_prores":
                    args += ["-c:a", "pcm_s16le"]
                else:
                    args += ["-c:a", "aac", "-b:a", "192k"]
            else:
                args += ["-an"]
            args += [str(target)]

            ok, error = _run_ffmpeg(args)
            if ok:
                meta, meta_warn = _read_video_metadata(target)
                warnings.extend(meta_warn)
                payload = _make_video_payload(path=target, metadata=meta)
                summary = {"output_path": str(target), "preset": preset_name, "mode": "ffmpeg", "warnings": warnings}
                return (payload, str(target), _json_text(summary))
            warnings.append(f"Preset export failed with ffmpeg: {error}")

        frames, in_fps, decode_warn = _decode_video_to_pil(video=video, requested_fps=fps, max_frames=0)
        warnings.extend(decode_warn)
        if not frames:
            warnings.append("No frames available for fallback export")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        out_frames = [_fit_contain(frame, target_w=int(tw), target_h=int(th)) for frame in frames]
        fmt = "mp4" if ext in {"mp4", "mov", "webm"} else ext
        ok, error = _save_video_from_pil(out_frames, fps=float(max(1.0, fps if fps > 0.0 else in_fps)), target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Fallback preset export failed: {error}")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        meta, meta_warn = _read_video_metadata(target)
        warnings.extend(meta_warn)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {"output_path": str(target), "preset": preset_name, "mode": "frame_fallback", "warnings": warnings}
        return (payload, str(target), _json_text(summary))


class MKRProjectManifest:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_name": ("STRING", {"default": "MKR Project", "multiline": False}),
                "save_manifest_file": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": "MKR_manifest"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "notes_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "video": ("*",),
                "audio": ("*",),
                "scene_ranges_json": ("STRING", {"default": "[]", "multiline": True}),
                "beat_markers_json": ("STRING", {"default": "[]", "multiline": True}),
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("manifest_json", "manifest_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(
        self,
        project_name: str = "MKR Project",
        save_manifest_file: bool = True,
        filename_prefix: str = "MKR_manifest",
        subfolder: str = "",
        overwrite: bool = False,
        notes_json: str = "{}",
        video: Any = None,
        audio: Any = None,
        scene_ranges_json: str = "[]",
        beat_markers_json: str = "[]",
        filename_label: str = "",
    ):
        warnings: List[str] = []
        video_path = _extract_input_file(video) if video is not None else None
        audio_path = _extract_input_file(audio) if audio is not None else None

        video_meta: Dict[str, Any] = {}
        if video_path is not None and _is_video_path(video_path):
            vmeta, vw = _read_video_metadata(video_path)
            warnings.extend(vw)
            video_meta = vmeta

        audio_meta: Dict[str, Any] = {}
        wave, sr, _, aerr = _load_audio_waveform(audio) if audio is not None else (None, 0, None, "")
        if wave is not None:
            audio_meta = {
                "sample_rate": int(max(1, sr)),
                "channels": int(wave.shape[0]),
                "duration": float(wave.shape[1] / float(max(1, sr))),
                "peak_db": float(_audio_stats(wave)["peak_db"]),
            }
        elif audio_path is not None and _is_audio_path(audio_path):
            audio_meta = {"sample_rate": int(_ffprobe_audio_sample_rate(audio_path, fallback=44100))}
            if aerr:
                warnings.append(aerr)

        parsed_notes: Any = notes_json
        try:
            parsed_notes = json.loads(str(notes_json or "{}"))
        except Exception:
            warnings.append("notes_json is not valid JSON, stored as raw string")

        parsed_scenes: Any = scene_ranges_json
        try:
            parsed_scenes = json.loads(str(scene_ranges_json or "[]"))
        except Exception:
            warnings.append("scene_ranges_json is not valid JSON, stored as raw string")

        parsed_beats: Any = beat_markers_json
        try:
            parsed_beats = json.loads(str(beat_markers_json or "[]"))
        except Exception:
            warnings.append("beat_markers_json is not valid JSON, stored as raw string")

        manifest: Dict[str, Any] = {
            "project_name": str(project_name),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "video": {"path": str(video_path) if video_path is not None else "", **video_meta},
            "audio": {"path": str(audio_path) if audio_path is not None else "", **audio_meta},
            "scene_ranges": parsed_scenes,
            "beat_markers": parsed_beats,
            "notes": parsed_notes,
            "warnings": warnings,
        }

        manifest_path = ""
        if bool(save_manifest_file):
            out_dir = _output_dir(subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = _sanitize_basename(filename_label or filename_prefix, "MKR_manifest")
            target = _resolve_output_file(out_dir=out_dir, stem=stem, ext="json", overwrite=bool(overwrite))
            try:
                target.write_text(_json_text(manifest), encoding="utf-8")
                manifest_path = str(target)
            except Exception as exc:
                warnings.append(f"Failed to write manifest: {exc}")

        summary = {
            "manifest_path": manifest_path,
            "has_video": bool(video_path is not None),
            "has_audio": bool(audio_path is not None),
            "warnings": warnings,
        }
        return (_json_text(manifest), str(manifest_path), _json_text(summary))


class MKREDLImport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "edl_path": ("STRING", {"default": ""}),
                "edl_text": ("STRING", {"default": "", "multiline": True}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("events_json", "cut_times_json", "event_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(self, edl_path: str = "", edl_text: str = "", fps: float = 24.0):
        warnings: List[str] = []
        text = str(edl_text or "")
        candidate = Path(str(edl_path or "").strip())
        if candidate.as_posix().strip():
            try:
                if candidate.exists() and candidate.is_file():
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                warnings.append(f"Failed to read edl_path: {exc}")

        lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]
        events: List[Dict[str, Any]] = []
        clip_name_for_event: Optional[str] = None
        f = float(max(1.0, fps))

        for line in lines:
            s = line.strip()
            if s.upper().startswith("* FROM CLIP NAME:"):
                clip_name_for_event = s.split(":", 1)[1].strip()
                if events:
                    events[-1]["clip_name"] = clip_name_for_event
                continue

            parts = s.split()
            if len(parts) < 8:
                continue
            if not parts[0].isdigit():
                continue

            event_id = int(parts[0])
            reel = parts[1]
            track = parts[2]
            trans = parts[3]
            src_in_tc, src_out_tc, rec_in_tc, rec_out_tc = parts[4], parts[5], parts[6], parts[7]

            ev = {
                "event": int(event_id),
                "reel": str(reel),
                "track": str(track),
                "transition": str(trans),
                "src_in_tc": str(src_in_tc),
                "src_out_tc": str(src_out_tc),
                "rec_in_tc": str(rec_in_tc),
                "rec_out_tc": str(rec_out_tc),
                "src_in_sec": float(_tc_to_sec(src_in_tc, f)),
                "src_out_sec": float(_tc_to_sec(src_out_tc, f)),
                "rec_in_sec": float(_tc_to_sec(rec_in_tc, f)),
                "rec_out_sec": float(_tc_to_sec(rec_out_tc, f)),
            }
            if clip_name_for_event:
                ev["clip_name"] = clip_name_for_event
            events.append(ev)

        cuts = sorted(set(float(ev.get("rec_in_sec", 0.0) or 0.0) for ev in events))
        summary = {
            "event_count": int(len(events)),
            "cut_count": int(len(cuts)),
            "fps": float(f),
            "warnings": warnings,
        }
        return (_json_text(events), _json_text(cuts), int(len(events)), _json_text(summary))


class MKREDLExport:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "events_json": ("STRING", {"default": "[]", "multiline": True}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.01}),
                "title": ("STRING", {"default": "MKR_EDL", "multiline": False}),
                "save_file": ("BOOLEAN", {"default": True}),
                "filename_prefix": ("STRING", {"default": "MKR_timeline"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("edl_text", "edl_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_IO

    def run(
        self,
        events_json: str = "[]",
        fps: float = 24.0,
        title: str = "MKR_EDL",
        save_file: bool = True,
        filename_prefix: str = "MKR_timeline",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        events: List[Dict[str, Any]] = []
        try:
            parsed = json.loads(str(events_json or "[]"))
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        events.append(item)
        except Exception as exc:
            warnings.append(f"events_json parse failed: {exc}")

        f = float(max(1.0, fps))
        lines: List[str] = [f"TITLE: {str(title)}", "FCM: NON-DROP FRAME", ""]

        for idx, ev in enumerate(events, start=1):
            rec_in_sec = float(ev.get("rec_in_sec", 0.0) or 0.0)
            rec_out_sec = float(ev.get("rec_out_sec", rec_in_sec) or rec_in_sec)
            src_in_sec = float(ev.get("src_in_sec", 0.0) or 0.0)
            src_out_sec = float(ev.get("src_out_sec", src_in_sec + max(0.0, rec_out_sec - rec_in_sec)) or 0.0)

            src_in_tc = str(ev.get("src_in_tc") or _sec_to_tc(src_in_sec, f))
            src_out_tc = str(ev.get("src_out_tc") or _sec_to_tc(src_out_sec, f))
            rec_in_tc = str(ev.get("rec_in_tc") or _sec_to_tc(rec_in_sec, f))
            rec_out_tc = str(ev.get("rec_out_tc") or _sec_to_tc(rec_out_sec, f))

            reel = str(ev.get("reel", "AX"))
            track = str(ev.get("track", "V"))
            trans = str(ev.get("transition", "C"))
            lines.append(f"{idx:03d}  {reel:<8} {track:<4} {trans:<4} {src_in_tc} {src_out_tc} {rec_in_tc} {rec_out_tc}")
            clip_name = str(ev.get("clip_name", "")).strip()
            if clip_name:
                lines.append(f"* FROM CLIP NAME: {clip_name}")
            lines.append("")

        edl_text_out = "\n".join(lines).rstrip() + "\n"

        out_path = ""
        if bool(save_file):
            out_dir = _output_dir(subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = _sanitize_basename(filename_label or filename_prefix, "MKR_timeline")
            target = _resolve_output_file(out_dir=out_dir, stem=stem, ext="edl", overwrite=bool(overwrite))
            try:
                target.write_text(edl_text_out, encoding="utf-8")
                out_path = str(target)
            except Exception as exc:
                warnings.append(f"Failed to write EDL: {exc}")

        summary = {"event_count": int(len(events)), "edl_path": out_path, "warnings": warnings}
        return (edl_text_out, str(out_path), _json_text(summary))
