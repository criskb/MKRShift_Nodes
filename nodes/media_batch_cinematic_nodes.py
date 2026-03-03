import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageColor, ImageFilter
import torch

from ..categories import MEDIA_VIDEO_EDIT, MEDIA_VIDEO_FX
from .media_batch_video_nodes import _build_video_payload, _decode_video_to_pil, _pil_to_tensor, _save_video_from_pil
from ..xmedia_nodes import _json_text, _make_video_payload, _read_video_metadata
from ..xpresave import _image_batch_to_pil, _output_dir, _resolve_output_file, _sanitize_basename
from ..xpresave_media import _extract_input_file, _ffmpeg_bin, _safe_ext


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _resolve_video_format(source: Optional[Path], requested: str, warnings: List[str]) -> str:
    fmt = _safe_ext(requested)
    if fmt == "auto":
        src = _safe_ext(source.suffix) if source is not None else ""
        fmt = src if src in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
    if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
        warnings.append("Unsupported format, using gif")
        fmt = "gif"
    if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
        warnings.append("ffmpeg unavailable for mp4/mov/webm, using gif")
        fmt = "gif"
    return fmt


def _save_video_result(
    frames: Sequence[Image.Image],
    fps: float,
    source: Optional[Path],
    output_format: str,
    filename_prefix: str,
    filename_label: str,
    subfolder: str,
    overwrite: bool,
    warnings: List[str],
) -> Tuple[Dict[str, Any], str, str]:
    fmt = _resolve_video_format(source, output_format, warnings)
    out_dir = _output_dir(subfolder)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_basename(filename_label or filename_prefix, filename_prefix)
    target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

    ok, error = _save_video_from_pil(frames=frames, fps=float(max(1.0, fps)), target=target, fmt=fmt)
    if not ok:
        warnings.append(f"Failed to save video: {error}")
        payload = _build_video_payload(_pil_to_tensor(frames), fps=float(max(1.0, fps)), source_path=source)
        return payload, "", _json_text({"warnings": warnings})

    meta, meta_warn = _read_video_metadata(target)
    warnings.extend(meta_warn)
    payload = _make_video_payload(path=target, metadata=meta)
    return payload, str(target), ""


def _parse_curve_points(raw: str) -> List[Tuple[float, float]]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    points: List[Tuple[float, float]] = []
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                out_t = float(item.get("out", 0.0))
                src_t = float(item.get("src", 0.0))
            except Exception:
                continue
            points.append((max(0.0, out_t), max(0.0, src_t)))
    if not points:
        for line in text.splitlines():
            parts = [p.strip() for p in line.replace(";", ",").split(",") if p.strip()]
            if len(parts) < 2:
                continue
            try:
                out_t = float(parts[0])
                src_t = float(parts[1])
            except Exception:
                continue
            points.append((max(0.0, out_t), max(0.0, src_t)))
    return sorted(points, key=lambda p: p[0])


def _interp_curve(points: Sequence[Tuple[float, float]], x: float) -> float:
    if not points:
        return float(max(0.0, x))
    if x <= points[0][0]:
        return float(points[0][1])
    if x >= points[-1][0]:
        return float(points[-1][1])
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if x <= x1:
            t = (x - x0) / max(1e-9, (x1 - x0))
            return float(y0 * (1.0 - t) + y1 * t)
    return float(points[-1][1])


def _center_of_mass(frame: Image.Image) -> Tuple[float, float]:
    arr = np.asarray(frame.convert("L"), dtype=np.float32) / 255.0
    h, w = arr.shape
    mask = np.clip(arr - float(np.percentile(arr, 70)), 0.0, 1.0)
    weight = float(np.sum(mask))
    if weight <= 1e-9:
        return float(w / 2.0), float(h / 2.0)
    ys, xs = np.indices(mask.shape, dtype=np.float32)
    cx = float(np.sum(xs * mask) / weight)
    cy = float(np.sum(ys * mask) / weight)
    return cx, cy


def _parse_color(color: str, fallback: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[int, int, int]:
    try:
        c = ImageColor.getrgb(str(color or "").strip() or "#ffffff")
        return int(c[0]), int(c[1]), int(c[2])
    except Exception:
        return fallback


class MKROpticalFlowInterpolate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "interpolation_factor": ("INT", {"default": 2, "min": 1, "max": 8, "step": 1}),
                "blend_curve": (["linear", "smoothstep"], {"default": "smoothstep"}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_flow_interp"}),
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
        interpolation_factor: int = 2,
        blend_curve: str = "smoothstep",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_flow_interp",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        factor = int(max(1, interpolation_factor))
        curve = str(blend_curve or "smoothstep").strip().lower()

        if len(frames) < 2 or factor <= 1:
            payload, out_path, save_summary = _save_video_result(
                frames=frames or [Image.new("RGB", (64, 64), (0, 0, 0))],
                fps=fps,
                source=source,
                output_format=output_format,
                filename_prefix=filename_prefix,
                filename_label=filename_label,
                subfolder=subfolder,
                overwrite=overwrite,
                warnings=warnings,
            )
            summary = {"output_path": out_path, "factor": factor, "warnings": warnings}
            if save_summary:
                summary = {"output_path": "", "factor": factor, "warnings": warnings}
            return (payload, out_path, _json_text(summary))

        arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]
        out: List[Image.Image] = []
        for i in range(len(arrs) - 1):
            a = arrs[i]
            b = arrs[i + 1]
            out.append(Image.fromarray(np.clip(a, 0.0, 255.0).astype(np.uint8), mode="RGB"))
            for k in range(1, factor):
                t = float(k / float(factor))
                if curve == "smoothstep":
                    t = float(t * t * (3.0 - 2.0 * t))
                mix = a * (1.0 - t) + b * t
                out.append(Image.fromarray(np.clip(mix, 0.0, 255.0).astype(np.uint8), mode="RGB"))
        out.append(frames[-1].convert("RGB"))

        out_fps = float(fps * factor)
        payload, out_path, save_summary = _save_video_result(
            frames=out,
            fps=out_fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "input_frames": int(len(frames)),
            "output_frames": int(len(out)),
            "input_fps": float(fps),
            "output_fps": float(out_fps),
            "factor": int(factor),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRTimeRemapCurve:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "curve_json": (
                    "STRING",
                    {
                        "default": '[{"out":0.0,"src":0.0},{"out":1.0,"src":0.5},{"out":2.0,"src":2.0}]',
                        "multiline": True,
                    },
                ),
                "output_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_time_remap"}),
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
        curve_json: str = '[{"out":0.0,"src":0.0},{"out":1.0,"src":0.5},{"out":2.0,"src":2.0}]',
        output_fps: float = 24.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_time_remap",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, in_fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        in_fps = float(max(1.0, in_fps if in_fps > 0.0 else fallback_fps))
        out_fps = float(max(1.0, output_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        points = _parse_curve_points(curve_json)
        in_duration = float(len(frames) / in_fps)
        if not points:
            points = [(0.0, 0.0), (in_duration, in_duration)]
            warnings.append("curve_json invalid or empty; using identity curve")
        if points[0][0] > 0.0:
            points.insert(0, (0.0, points[0][1]))
        out_duration = float(max(points[-1][0], 1.0 / out_fps))

        out_count = int(max(1, round(out_duration * out_fps)))
        out_frames: List[Image.Image] = []
        for i in range(out_count):
            t_out = float(i / out_fps)
            t_src = float(_interp_curve(points, t_out))
            src_idx = _clamp_int(int(round(t_src * in_fps)), 0, len(frames) - 1)
            out_frames.append(frames[src_idx].convert("RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=out_fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "input_frames": int(len(frames)),
            "output_frames": int(len(out_frames)),
            "input_fps": float(in_fps),
            "output_fps": float(out_fps),
            "curve_points": points,
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRAutoReframeSubject:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "target_width": ("INT", {"default": 1080, "min": 64, "max": 8192, "step": 1}),
                "target_height": ("INT", {"default": 1920, "min": 64, "max": 8192, "step": 1}),
                "smoothing": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 0.99, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_auto_reframe"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "track_json", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(
        self,
        video: Any,
        target_width: int = 1080,
        target_height: int = 1920,
        smoothing: float = 0.85,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_auto_reframe",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", "[]", _json_text({"warnings": warnings}))

        tw = int(max(64, target_width))
        th = int(max(64, target_height))
        target_ar = float(tw / float(th))
        smooth = float(_clamp_float(smoothing, 0.0, 0.99))

        first = frames[0].convert("RGB")
        sw, sh = first.size
        src_ar = float(sw / float(sh))
        if src_ar >= target_ar:
            crop_h = int(sh)
            crop_w = int(round(crop_h * target_ar))
        else:
            crop_w = int(sw)
            crop_h = int(round(crop_w / target_ar))
        crop_w = int(max(1, min(sw, crop_w)))
        crop_h = int(max(1, min(sh, crop_h)))

        smoothed_cx, smoothed_cy = _center_of_mass(first)
        out_frames: List[Image.Image] = []
        track: List[Dict[str, Any]] = []
        for idx, frame in enumerate(frames):
            img = frame.convert("RGB")
            cx, cy = _center_of_mass(img)
            smoothed_cx = smoothed_cx * smooth + cx * (1.0 - smooth)
            smoothed_cy = smoothed_cy * smooth + cy * (1.0 - smooth)

            x0 = int(round(smoothed_cx - crop_w / 2.0))
            y0 = int(round(smoothed_cy - crop_h / 2.0))
            x0 = _clamp_int(x0, 0, max(0, sw - crop_w))
            y0 = _clamp_int(y0, 0, max(0, sh - crop_h))
            x1 = x0 + crop_w
            y1 = y0 + crop_h

            cut = img.crop((x0, y0, x1, y1)).resize((tw, th), resample=Image.Resampling.LANCZOS)
            out_frames.append(cut)
            track.append({"frame": int(idx), "cx": round(float(smoothed_cx), 3), "cy": round(float(smoothed_cy), 3), "crop": [int(x0), int(y0), int(x1), int(y1)]})

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "target_resolution": f"{tw}x{th}",
            "track_points": int(len(track)),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(track), _json_text(summary))


class MKRMatchCutByMotion:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_a": ("*",),
                "video_b": ("*",),
                "search_window_frames": ("INT", {"default": 48, "min": 1, "max": 10000, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT", "FLOAT", "STRING")
    RETURN_NAMES = ("best_frame_b", "match_score", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_EDIT

    def run(self, video_a: Any, video_b: Any, search_window_frames: int = 48):
        warnings: List[str] = []
        a_frames, _, wa = _decode_video_to_pil(video=video_a, requested_fps=0.0, max_frames=0)
        b_frames, _, wb = _decode_video_to_pil(video=video_b, requested_fps=0.0, max_frames=0)
        warnings.extend(wa)
        warnings.extend(wb)
        if len(a_frames) < 2 or len(b_frames) < 2:
            warnings.append("Need at least 2 frames in each input")
            return (0, 1e9, _json_text({"warnings": warnings}))

        ref = np.asarray(a_frames[-1].convert("L"), dtype=np.float32) / 255.0
        ref_prev = np.asarray(a_frames[-2].convert("L"), dtype=np.float32) / 255.0
        ref_motion = float(np.mean(np.abs(ref - ref_prev)))

        max_b = int(min(len(b_frames), max(1, search_window_frames)))
        best_idx = 0
        best_score = 1e9
        for idx in range(max_b):
            cur = np.asarray(b_frames[idx].convert("L"), dtype=np.float32) / 255.0
            diff_score = float(np.mean(np.abs(ref - cur)))
            motion_score = 0.0
            if idx > 0:
                prv = np.asarray(b_frames[idx - 1].convert("L"), dtype=np.float32) / 255.0
                motion_score = abs(float(np.mean(np.abs(cur - prv))) - ref_motion)
            score = diff_score + (0.5 * motion_score)
            if score < best_score:
                best_score = score
                best_idx = idx

        summary = {
            "best_frame_b": int(best_idx),
            "score": float(best_score),
            "search_window_frames": int(max_b),
            "warnings": warnings,
        }
        return (int(best_idx), float(best_score), _json_text(summary))


class MKRShotMatchColor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_video": ("*",),
                "reference_video": ("*",),
                "reference_sample_frames": ("INT", {"default": 8, "min": 1, "max": 256, "step": 1}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_shot_match_color"}),
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
        source_video: Any,
        reference_video: Any,
        reference_sample_frames: int = 8,
        strength: float = 1.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_shot_match_color",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        src_frames, fps, wa = _decode_video_to_pil(video=source_video, requested_fps=0.0, max_frames=0)
        ref_frames, _, wb = _decode_video_to_pil(video=reference_video, requested_fps=0.0, max_frames=0)
        warnings.extend(wa)
        warnings.extend(wb)
        source = _extract_input_file(source_video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not src_frames or not ref_frames:
            warnings.append("Both source and reference videos are required")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        nref = int(max(1, min(len(ref_frames), reference_sample_frames)))
        ref_arr = np.stack(
            [np.asarray(ref_frames[i].convert("RGB"), dtype=np.float32) / 255.0 for i in range(nref)],
            axis=0,
        )
        ref_mu = np.mean(ref_arr, axis=(0, 1, 2))
        ref_sigma = np.std(ref_arr, axis=(0, 1, 2)) + 1e-6
        str_v = float(_clamp_float(strength, 0.0, 1.0))

        out_frames: List[Image.Image] = []
        for frame in src_frames:
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32) / 255.0
            mu = np.mean(arr, axis=(0, 1))
            sigma = np.std(arr, axis=(0, 1)) + 1e-6
            matched = (arr - mu) / sigma * ref_sigma + ref_mu
            blend = arr * (1.0 - str_v) + matched * str_v
            out_frames.append(Image.fromarray((np.clip(blend, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "reference_frames_used": int(nref),
            "strength": float(str_v),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRFilmGatePack:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "flicker_strength": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01}),
                "dust_amount": ("FLOAT", {"default": 0.02, "min": 0.0, "max": 0.4, "step": 0.005}),
                "scratch_amount": ("FLOAT", {"default": 0.01, "min": 0.0, "max": 0.2, "step": 0.005}),
                "gate_weave_px": ("INT", {"default": 2, "min": 0, "max": 20, "step": 1}),
                "seed": ("INT", {"default": 1234, "min": 0, "max": 2**31 - 1, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_film_gate"}),
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
        flicker_strength: float = 0.08,
        dust_amount: float = 0.02,
        scratch_amount: float = 0.01,
        gate_weave_px: int = 2,
        seed: int = 1234,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_film_gate",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        random.seed(int(seed))
        np.random.seed(int(seed) % (2**32 - 1))

        f_str = float(_clamp_float(flicker_strength, 0.0, 0.5))
        d_amt = float(_clamp_float(dust_amount, 0.0, 0.4))
        s_amt = float(_clamp_float(scratch_amount, 0.0, 0.2))
        weave = int(max(0, gate_weave_px))

        out_frames: List[Image.Image] = []
        for idx, frame in enumerate(frames):
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
            h, w, _ = arr.shape

            # Gate weave as per-frame x/y shifts.
            if weave > 0:
                dx = int(round(math.sin(idx * 0.37) * weave))
                dy = int(round(math.cos(idx * 0.29) * weave))
                arr = np.roll(arr, shift=dx, axis=1)
                arr = np.roll(arr, shift=dy, axis=0)

            # Exposure flicker.
            flicker = 1.0 + random.uniform(-f_str, f_str)
            arr *= float(flicker)

            # Dust specks.
            specks = int(d_amt * (w * h) / 1500.0)
            for _ in range(max(0, specks)):
                x = random.randint(0, max(0, w - 1))
                y = random.randint(0, max(0, h - 1))
                val = random.randint(200, 255) if random.random() > 0.5 else random.randint(0, 40)
                r = random.randint(1, 2)
                arr[max(0, y - r) : min(h, y + r + 1), max(0, x - r) : min(w, x + r + 1), :] = val

            # Vertical scratches.
            scratches = int(s_amt * (w / 8.0))
            for _ in range(max(0, scratches)):
                x = random.randint(0, max(0, w - 1))
                val = random.randint(170, 255)
                width = random.randint(1, 2)
                arr[:, max(0, x - width) : min(w, x + width + 1), :] = arr[:, max(0, x - width) : min(w, x + width + 1), :] * 0.6 + val * 0.4

            out_frames.append(Image.fromarray(np.clip(arr, 0.0, 255.0).astype(np.uint8), mode="RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "flicker_strength": float(f_str),
            "dust_amount": float(d_amt),
            "scratch_amount": float(s_amt),
            "gate_weave_px": int(weave),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRLightWrapComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "foreground": ("IMAGE",),
                "background": ("IMAGE",),
                "wrap_radius": ("INT", {"default": 16, "min": 1, "max": 256, "step": 1}),
                "strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 2.0, "step": 0.01}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_VIDEO_FX

    def run(self, foreground: torch.Tensor, background: torch.Tensor, wrap_radius: int = 16, strength: float = 0.35, mask: Optional[torch.Tensor] = None):
        warnings: List[str] = []
        fg_frames = _image_batch_to_pil(foreground)
        bg_frames = _image_batch_to_pil(background)
        if not fg_frames or not bg_frames:
            warnings.append("Foreground and background images are required")
            return (torch.zeros((1, 64, 64, 3), dtype=torch.float32), _json_text({"warnings": warnings}))

        count = min(len(fg_frames), len(bg_frames))
        if len(fg_frames) != len(bg_frames):
            warnings.append("Batch size mismatch; using shortest batch length")
        radius = int(max(1, wrap_radius))
        str_v = float(_clamp_float(strength, 0.0, 2.0))

        mask_imgs: List[Image.Image] = []
        if torch.is_tensor(mask):
            m = mask.detach().float().cpu()
            if m.ndim == 2:
                m = m.unsqueeze(0)
            if m.ndim == 3:
                for i in range(min(count, m.shape[0])):
                    arr = np.clip(m[i].numpy(), 0.0, 1.0)
                    mask_imgs.append(Image.fromarray((arr * 255.0).astype(np.uint8), mode="L"))

        out_frames: List[Image.Image] = []
        for i in range(count):
            fg = fg_frames[i].convert("RGB")
            bg = bg_frames[i].convert("RGB").resize(fg.size, resample=Image.Resampling.BILINEAR)
            blur = bg.filter(ImageFilter.GaussianBlur(radius=radius))

            if i < len(mask_imgs):
                m = mask_imgs[i].resize(fg.size, resample=Image.Resampling.BILINEAR)
                edge = m.filter(ImageFilter.MaxFilter(size=5))
                edge_np = np.clip(np.asarray(edge, dtype=np.float32) - np.asarray(m, dtype=np.float32), 0.0, 255.0) / 255.0
            else:
                gray = fg.convert("L")
                edge = gray.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(radius=2))
                edge_np = np.asarray(edge, dtype=np.float32) / 255.0

            fg_np = np.asarray(fg, dtype=np.float32) / 255.0
            blur_np = np.asarray(blur, dtype=np.float32) / 255.0
            wrap = blur_np * edge_np[:, :, None] * str_v
            comp = np.clip(fg_np + wrap, 0.0, 1.0)
            out_frames.append(Image.fromarray((comp * 255.0).astype(np.uint8), mode="RGB"))

        summary = {
            "frame_count": int(len(out_frames)),
            "wrap_radius": int(radius),
            "strength": float(str_v),
            "warnings": warnings,
        }
        return (_pil_to_tensor(out_frames), _json_text(summary))


class MKRMotionBlurVector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "shutter_frames": ("INT", {"default": 5, "min": 1, "max": 31, "step": 2}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "direction": (["centered", "forward", "backward"], {"default": "centered"}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_motion_blur"}),
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
        shutter_frames: int = 5,
        strength: float = 1.0,
        direction: str = "centered",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_motion_blur",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        n = int(max(1, shutter_frames))
        str_v = float(_clamp_float(strength, 0.0, 2.0))
        mode = str(direction or "centered").strip().lower()
        arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]
        out_frames: List[Image.Image] = []

        for i in range(len(arrs)):
            if mode == "forward":
                idxs = list(range(i, min(len(arrs), i + n)))
            elif mode == "backward":
                idxs = list(range(max(0, i - n + 1), i + 1))
            else:
                r = n // 2
                idxs = list(range(max(0, i - r), min(len(arrs), i + r + 1)))
            if not idxs:
                idxs = [i]
            stack = np.stack([arrs[j] for j in idxs], axis=0)
            blur = np.mean(stack, axis=0)
            mixed = arrs[i] * (1.0 - str_v) + blur * str_v
            out_frames.append(Image.fromarray(np.clip(mixed, 0.0, 255.0).astype(np.uint8), mode="RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "shutter_frames": int(n),
            "strength": float(str_v),
            "direction": mode,
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRLensFX:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "vignette": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "chromatic_aberration_px": ("INT", {"default": 2, "min": 0, "max": 32, "step": 1}),
                "barrel": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "sharpen": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_lens_fx"}),
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
        vignette: float = 0.25,
        chromatic_aberration_px: int = 2,
        barrel: float = 0.0,
        sharpen: float = 0.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_lens_fx",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        vig = float(_clamp_float(vignette, 0.0, 1.0))
        ca = int(max(0, chromatic_aberration_px))
        bar = float(_clamp_float(barrel, -1.0, 1.0))
        shp = float(max(0.0, sharpen))

        out_frames: List[Image.Image] = []
        for frame in frames:
            img = frame.convert("RGB")
            if abs(bar) > 1e-6:
                scale = 1.0 - (bar * 0.15)
                scale = max(0.7, min(1.3, scale))
                nw = int(max(1, round(img.width * scale)))
                nh = int(max(1, round(img.height * scale)))
                rez = img.resize((nw, nh), resample=Image.Resampling.BICUBIC)
                canvas = Image.new("RGB", img.size, (0, 0, 0))
                ox = (img.width - nw) // 2
                oy = (img.height - nh) // 2
                canvas.paste(rez, (ox, oy))
                img = canvas

            arr = np.asarray(img, dtype=np.float32)
            if ca > 0:
                r = np.roll(arr[:, :, 0], shift=ca, axis=1)
                g = arr[:, :, 1]
                b = np.roll(arr[:, :, 2], shift=-ca, axis=1)
                arr = np.stack([r, g, b], axis=2)

            if vig > 1e-6:
                h, w, _ = arr.shape
                y = np.linspace(-1.0, 1.0, num=h, dtype=np.float32)
                x = np.linspace(-1.0, 1.0, num=w, dtype=np.float32)
                yy, xx = np.meshgrid(y, x, indexing="ij")
                rad = np.sqrt(xx * xx + yy * yy)
                mask = 1.0 - np.clip((rad - 0.2) / 0.9, 0.0, 1.0) * vig
                arr = arr * mask[:, :, None]

            out = Image.fromarray(np.clip(arr, 0.0, 255.0).astype(np.uint8), mode="RGB")
            if shp > 1e-6:
                out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=int(min(500, round(shp * 120.0))), threshold=2))
            out_frames.append(out)

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "vignette": float(vig),
            "chromatic_aberration_px": int(ca),
            "barrel": float(bar),
            "sharpen": float(shp),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRDepthFog:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "fog_color": ("STRING", {"default": "#AFC6D8"}),
                "near_start": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.01}),
                "far_end": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fog_strength": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_depth_fog"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "depth_map": ("IMAGE",),
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
        fog_color: str = "#AFC6D8",
        near_start: float = 0.2,
        far_end: float = 1.0,
        fog_strength: float = 0.65,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_depth_fog",
        subfolder: str = "",
        overwrite: bool = False,
        depth_map: Optional[torch.Tensor] = None,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        fog_rgb = np.array(_parse_color(fog_color, fallback=(175, 198, 216)), dtype=np.float32) / 255.0
        n0 = float(_clamp_float(near_start, 0.0, 1.0))
        n1 = float(_clamp_float(far_end, 0.0, 1.0))
        if n1 <= n0 + 1e-6:
            n1 = min(1.0, n0 + 0.01)
        str_v = float(_clamp_float(fog_strength, 0.0, 1.0))

        depth_frames: List[Image.Image] = []
        if torch.is_tensor(depth_map):
            depth_frames = _image_batch_to_pil(depth_map)

        out_frames: List[Image.Image] = []
        for idx, frame in enumerate(frames):
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32) / 255.0
            h, w, _ = arr.shape
            if idx < len(depth_frames):
                dimg = depth_frames[idx].convert("L").resize((w, h), resample=Image.Resampling.BILINEAR)
                depth = np.asarray(dimg, dtype=np.float32) / 255.0
            else:
                # Fallback synthetic depth: farther toward top.
                y = np.linspace(0.0, 1.0, num=h, dtype=np.float32)
                depth = np.tile((1.0 - y)[:, None], (1, w))

            t = np.clip((depth - n0) / max(1e-6, (n1 - n0)), 0.0, 1.0) * str_v
            mix = arr * (1.0 - t[:, :, None]) + fog_rgb[None, None, :] * t[:, :, None]
            out_frames.append(Image.fromarray((np.clip(mix, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "fog_color": str(fog_color),
            "near_start": float(n0),
            "far_end": float(n1),
            "fog_strength": float(str_v),
            "used_depth_map": bool(len(depth_frames) > 0),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))
