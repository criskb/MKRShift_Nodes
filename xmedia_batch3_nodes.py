import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import torch

from .categories import MEDIA_AUDIO_FX, MEDIA_AUDIO_UTILITY, MEDIA_VIDEO_FX, MEDIA_VIDEO_UTILITY, MEDIA_WATERMARK
from .xmedia_batch1_nodes import (
    _build_video_payload,
    _decode_video_to_pil,
    _pil_to_tensor,
    _save_video_from_pil,
)
from .xmedia_batch2_nodes import _load_audio_waveform, _save_audio_result
from .xmedia_nodes import _json_text, _make_video_payload, _read_video_metadata
from .xpresave import _image_batch_to_pil, _output_dir, _resolve_output_file, _sanitize_basename
from .xpresave_media import _extract_input_file, _safe_ext


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _parse_color(value: str, fallback: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[int, int, int]:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        c = ImageColor.getrgb(text)
        return int(c[0]), int(c[1]), int(c[2])
    except Exception:
        return fallback


def _resolve_pos(canvas_w: int, canvas_h: int, item_w: int, item_h: int, position: str, margin: int) -> Tuple[int, int]:
    m = int(max(0, margin))
    px = int(max(0, canvas_w - item_w) // 2)
    py = int(max(0, canvas_h - item_h) // 2)
    pos = str(position or "bottom_right").strip().lower()

    if "left" in pos:
        px = m
    elif "right" in pos:
        px = int(max(0, canvas_w - item_w - m))

    if "top" in pos:
        py = m
    elif "bottom" in pos:
        py = int(max(0, canvas_h - item_h - m))

    return int(px), int(py)


def _resolve_video_format(source: Optional[Path], requested: str, warnings: List[str]) -> str:
    fmt = _safe_ext(requested)
    if fmt == "auto":
        src = _safe_ext(source.suffix) if source is not None else ""
        fmt = src if src in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
    if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
        fmt = "gif"
        warnings.append("Unsupported video output format, using gif")
    return fmt


def _get_font(size: int) -> ImageFont.ImageFont:
    safe_size = int(max(8, size))
    try:
        return ImageFont.truetype("DejaVuSans.ttf", safe_size)
    except Exception:
        try:
            return ImageFont.truetype("Arial.ttf", safe_size)
        except Exception:
            return ImageFont.load_default()


def _alpha_composite(base_rgb: Image.Image, overlay_rgba: Image.Image, x: int, y: int, opacity: float) -> Image.Image:
    base = base_rgb.convert("RGBA")
    ov = overlay_rgba.convert("RGBA")
    a = np.asarray(ov.getchannel("A"), dtype=np.float32)
    a *= float(_clamp_float(opacity, 0.0, 1.0))
    ov.putalpha(Image.fromarray(np.clip(a, 0.0, 255.0).astype(np.uint8), mode="L"))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(ov, (int(x), int(y)), ov)
    mixed = Image.alpha_composite(base, layer)
    return mixed.convert("RGB")


def _build_logo_rgba(
    watermark_image: Optional[torch.Tensor],
    base_size: Tuple[int, int],
    scale: float,
    rotation_deg: float,
) -> Optional[Image.Image]:
    if watermark_image is None:
        return None
    if not torch.is_tensor(watermark_image):
        return None
    t = watermark_image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4 or int(t.shape[-1]) not in {3, 4}:
        return None

    first = t[0].cpu().numpy()
    if first.shape[-1] == 4:
        rgba = np.clip(first * 255.0, 0.0, 255.0).astype(np.uint8)
        logo = Image.fromarray(rgba, mode="RGBA")
    else:
        rgb = np.clip(first[:, :, :3] * 255.0, 0.0, 255.0).astype(np.uint8)
        logo = Image.fromarray(rgb, mode="RGB").convert("RGBA")

    bw, bh = base_size
    sc = _clamp_float(scale, 0.02, 1.0)
    target_w = int(max(1, round(float(max(1, bw)) * sc)))
    ratio = float(target_w) / float(max(1, logo.width))
    target_h = int(max(1, round(float(logo.height) * ratio)))
    resized = logo.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

    rot = float(rotation_deg)
    if abs(rot) > 1e-6:
        resized = resized.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)
    return resized


def _watermark_single_image(
    base: Image.Image,
    text: str,
    text_size: int,
    text_color: str,
    text_bg_color: str,
    text_bg_opacity: float,
    logo_rgba: Optional[Image.Image],
    position: str,
    margin: int,
    opacity: float,
) -> Image.Image:
    canvas = base.convert("RGB")
    out = canvas.copy()

    if logo_rgba is not None:
        x, y = _resolve_pos(canvas.width, canvas.height, logo_rgba.width, logo_rgba.height, position, margin)
        out = _alpha_composite(out, logo_rgba, x, y, opacity=opacity)

    label = str(text or "").strip()
    if label:
        font = _get_font(text_size)
        drawer = ImageDraw.Draw(out, mode="RGBA")
        bbox = drawer.textbbox((0, 0), label, font=font)
        tw = int(max(1, bbox[2] - bbox[0]))
        th = int(max(1, bbox[3] - bbox[1]))
        pad = int(max(2, round(float(text_size) * 0.25)))
        box_w = tw + pad * 2
        box_h = th + pad * 2
        x, y = _resolve_pos(out.width, out.height, box_w, box_h, position, margin)

        bg_rgb = _parse_color(text_bg_color, fallback=(0, 0, 0))
        bg_a = int(round(255.0 * _clamp_float(text_bg_opacity, 0.0, 1.0)))
        drawer.rectangle((x, y, x + box_w, y + box_h), fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_a))

        tc = _parse_color(text_color, fallback=(255, 255, 255))
        drawer.text((x + pad, y + pad), label, fill=(tc[0], tc[1], tc[2], 255), font=font)

    return out


def _merge_summary(base_json: str, extra: Dict[str, Any]) -> str:
    data: Dict[str, Any] = {}
    try:
        parsed = json.loads(str(base_json or "{}"))
        if isinstance(parsed, dict):
            data.update(parsed)
    except Exception:
        pass
    data.update(extra)
    return _json_text(data)


def _envelope_from_pattern(length: int, sample_rate: int, pattern: str, unit_ms: int) -> np.ndarray:
    total = int(max(1, length))
    unit_samples = int(max(1, round(float(max(10, unit_ms)) * float(sample_rate) / 1000.0)))
    bits: List[int] = []
    text = str(pattern or "").strip()
    if not text:
        bits = [1]
    else:
        for ch in text.encode("utf-8", errors="ignore"):
            for shift in range(7, -1, -1):
                bits.append((ch >> shift) & 1)
            bits.append(0)

    if not bits:
        bits = [1]

    env = np.zeros((total,), dtype=np.float32)
    cursor = 0
    for bit in bits:
        if cursor >= total:
            break
        end = int(min(total, cursor + unit_samples))
        if bit > 0:
            env[cursor:end] = 1.0
        cursor = int(end)
    return env


class MKRImageWatermark:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "text": ("STRING", {"default": "", "multiline": False}),
                "text_size": ("INT", {"default": 28, "min": 8, "max": 512, "step": 1}),
                "text_color": ("STRING", {"default": "#FFFFFF"}),
                "text_bg_color": ("STRING", {"default": "#000000"}),
                "text_bg_opacity": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "position": (
                    [
                        "bottom_right",
                        "bottom_left",
                        "top_right",
                        "top_left",
                        "center",
                    ],
                    {"default": "bottom_right"},
                ),
                "margin": ("INT", {"default": 24, "min": 0, "max": 2048, "step": 1}),
                "watermark_opacity": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}),
                "logo_scale": ("FLOAT", {"default": 0.2, "min": 0.02, "max": 1.0, "step": 0.01}),
                "logo_rotation_deg": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.1}),
            },
            "optional": {
                "watermark_image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_WATERMARK

    def run(
        self,
        image: torch.Tensor,
        text: str = "",
        text_size: int = 28,
        text_color: str = "#FFFFFF",
        text_bg_color: str = "#000000",
        text_bg_opacity: float = 0.35,
        position: str = "bottom_right",
        margin: int = 24,
        watermark_opacity: float = 0.8,
        logo_scale: float = 0.2,
        logo_rotation_deg: float = 0.0,
        watermark_image: Optional[torch.Tensor] = None,
    ):
        warnings: List[str] = []
        frames = _image_batch_to_pil(image)
        if not frames:
            warnings.append("No frames in IMAGE input")
            dummy = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (dummy, _json_text({"warnings": warnings}))

        logo = _build_logo_rgba(
            watermark_image=watermark_image,
            base_size=frames[0].size,
            scale=float(logo_scale),
            rotation_deg=float(logo_rotation_deg),
        )
        if logo is None and not str(text or "").strip():
            warnings.append("No text or watermark_image provided, returning input unchanged")
            return (_pil_to_tensor(frames), _json_text({"warnings": warnings}))

        out: List[Image.Image] = []
        for frame in frames:
            out.append(
                _watermark_single_image(
                    base=frame,
                    text=text,
                    text_size=int(text_size),
                    text_color=text_color,
                    text_bg_color=text_bg_color,
                    text_bg_opacity=float(text_bg_opacity),
                    logo_rgba=logo,
                    position=position,
                    margin=int(margin),
                    opacity=float(watermark_opacity),
                )
            )

        summary = {
            "frame_count": int(len(out)),
            "used_text": bool(str(text or "").strip()),
            "used_logo": bool(logo is not None),
            "position": str(position),
            "warnings": warnings,
        }
        return (_pil_to_tensor(out), _json_text(summary))


class MKRAudioWatermark:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "mode": (["tone_pulse", "chirp_pulse", "text_pattern"], {"default": "tone_pulse"}),
                "frequency_hz": ("FLOAT", {"default": 1800.0, "min": 40.0, "max": 20000.0, "step": 1.0}),
                "level_db": ("FLOAT", {"default": -28.0, "min": -60.0, "max": -3.0, "step": 0.1}),
                "interval_sec": ("FLOAT", {"default": 4.0, "min": 0.05, "max": 120.0, "step": 0.01}),
                "pulse_duration_ms": ("INT", {"default": 120, "min": 10, "max": 5000, "step": 1}),
                "start_offset_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 120.0, "step": 0.01}),
                "signature_text": ("STRING", {"default": "MKRSHIFT", "multiline": False}),
                "pattern_unit_ms": ("INT", {"default": 80, "min": 10, "max": 2000, "step": 1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_watermark"}),
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
    CATEGORY = MEDIA_WATERMARK

    def run(
        self,
        audio: Any,
        mode: str = "tone_pulse",
        frequency_hz: float = 1800.0,
        level_db: float = -28.0,
        interval_sec: float = 4.0,
        pulse_duration_ms: int = 120,
        start_offset_sec: float = 0.0,
        signature_text: str = "MKRSHIFT",
        pattern_unit_ms: int = 80,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_watermark",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return (_merge_audio_empty(source, warnings))

        w = waveform.astype(np.float32, copy=False).copy()
        total = int(w.shape[1])
        sr = int(max(1, sample_rate))
        t = np.arange(total, dtype=np.float32) / float(sr)
        freq = float(_clamp_float(frequency_hz, 40.0, 20000.0))
        amp = float(10.0 ** (float(level_db) / 20.0))
        interval = float(max(0.05, interval_sec))
        pulse_n = int(max(1, round(float(max(10, pulse_duration_ms)) * float(sr) / 1000.0)))
        start_n = int(max(0, round(float(max(0.0, start_offset_sec)) * float(sr))))

        wm = np.zeros((total,), dtype=np.float32)
        selected_mode = str(mode or "tone_pulse").strip().lower()
        if selected_mode == "text_pattern":
            env = _envelope_from_pattern(length=total - start_n, sample_rate=sr, pattern=signature_text, unit_ms=int(pattern_unit_ms))
            if env.size > 0 and start_n < total:
                wm[start_n : start_n + env.size] = env
            phase = 2.0 * np.pi * freq * t
            wm *= np.sin(phase).astype(np.float32)
        else:
            pulse_count = 0
            cursor = int(start_n)
            while cursor < total:
                end = int(min(total, cursor + pulse_n))
                seg_t = np.arange(end - cursor, dtype=np.float32) / float(sr)
                if selected_mode == "chirp_pulse":
                    f0 = freq
                    f1 = freq * 1.35
                    k = (f1 - f0) / max(1e-6, float((end - cursor) / float(sr)))
                    phase = 2.0 * np.pi * (f0 * seg_t + 0.5 * k * seg_t * seg_t)
                    tone = np.sin(phase).astype(np.float32)
                else:
                    tone = np.sin(2.0 * np.pi * freq * seg_t).astype(np.float32)
                # Quick fade to avoid clicks.
                fade = int(min(len(tone) // 2, max(1, int(0.01 * sr))))
                if fade > 0 and len(tone) > 2:
                    ramp = np.linspace(0.0, 1.0, num=fade, dtype=np.float32)
                    tone[:fade] *= ramp
                    tone[-fade:] *= ramp[::-1]
                wm[cursor:end] += tone[: end - cursor]
                pulse_count += 1
                cursor = int(round(float(cursor) + interval * float(sr)))
            if pulse_count <= 0:
                warnings.append("No pulses scheduled, interval might be too large for clip duration")

        wm *= float(amp)
        if w.shape[0] > 1:
            wm_multi = np.repeat(wm[np.newaxis, :], int(w.shape[0]), axis=0)
        else:
            wm_multi = wm[np.newaxis, :]
        mixed = np.clip(w + wm_multi, -1.0, 1.0).astype(np.float32, copy=False)

        payload, path, duration, summary = _save_audio_result(
            waveform=mixed,
            sample_rate=sr,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "mode": selected_mode,
            "frequency_hz": float(freq),
            "level_db": float(level_db),
            "interval_sec": float(interval),
            "pulse_duration_ms": int(pulse_duration_ms),
            "signature_text": str(signature_text),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


def _merge_audio_empty(source: Optional[Path], warnings: List[str]):
    payload = {"kind": "audio"}
    if source is not None:
        payload["path"] = str(source)
    return (payload, "", 0.0, _json_text({"warnings": warnings}))


class MKRVideoWatermark:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "text": ("STRING", {"default": "", "multiline": False}),
                "text_size": ("INT", {"default": 32, "min": 8, "max": 512, "step": 1}),
                "text_color": ("STRING", {"default": "#FFFFFF"}),
                "text_bg_color": ("STRING", {"default": "#000000"}),
                "text_bg_opacity": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "position": (
                    [
                        "bottom_right",
                        "bottom_left",
                        "top_right",
                        "top_left",
                        "center",
                    ],
                    {"default": "bottom_right"},
                ),
                "margin": ("INT", {"default": 24, "min": 0, "max": 2048, "step": 1}),
                "watermark_opacity": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}),
                "logo_scale": ("FLOAT", {"default": 0.2, "min": 0.02, "max": 1.0, "step": 0.01}),
                "logo_rotation_deg": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_video_watermark"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "watermark_image": ("IMAGE",),
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_WATERMARK

    def run(
        self,
        video: Any,
        text: str = "",
        text_size: int = 32,
        text_color: str = "#FFFFFF",
        text_bg_color: str = "#000000",
        text_bg_opacity: float = 0.35,
        position: str = "bottom_right",
        margin: int = 24,
        watermark_opacity: float = 0.8,
        logo_scale: float = 0.2,
        logo_rotation_deg: float = 0.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_video_watermark",
        subfolder: str = "",
        overwrite: bool = False,
        watermark_image: Optional[torch.Tensor] = None,
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

        logo = _build_logo_rgba(
            watermark_image=watermark_image,
            base_size=frames[0].size,
            scale=float(logo_scale),
            rotation_deg=float(logo_rotation_deg),
        )
        if logo is None and not str(text or "").strip():
            warnings.append("No text or watermark_image provided, returning input unchanged")

        out_frames: List[Image.Image] = []
        for frame in frames:
            out_frames.append(
                _watermark_single_image(
                    base=frame,
                    text=text,
                    text_size=int(text_size),
                    text_color=text_color,
                    text_bg_color=text_bg_color,
                    text_bg_opacity=float(text_bg_opacity),
                    logo_rgba=logo,
                    position=position,
                    margin=int(margin),
                    opacity=float(watermark_opacity),
                )
            )

        fmt = _resolve_video_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_video_watermark")
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
            "frame_count": int(len(out_frames)),
            "used_text": bool(str(text or "").strip()),
            "used_logo": bool(logo is not None),
            "position": str(position),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoFrameRateConvert:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "target_fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 240.0, "step": 0.01}),
                "resample_mode": (["nearest", "blend"], {"default": "nearest"}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_fps_convert"}),
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
        target_fps: float = 30.0,
        resample_mode: str = "nearest",
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_fps_convert",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps_in, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps_in = float(max(1.0, fps_in if fps_in > 0.0 else fallback_fps))
        fps_out = float(max(1.0, target_fps))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        duration = float(len(frames) / fps_in)
        out_count = int(max(1, round(duration * fps_out)))
        mode = str(resample_mode or "nearest").strip().lower()
        frame_arr = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]

        out_frames: List[Image.Image] = []
        for idx in range(out_count):
            t = float(idx / fps_out)
            src_f = t * fps_in
            if mode == "blend":
                lo = _clamp_int(int(math.floor(src_f)), 0, len(frame_arr) - 1)
                hi = _clamp_int(int(math.ceil(src_f)), 0, len(frame_arr) - 1)
                frac = float(src_f - math.floor(src_f))
                if lo == hi:
                    arr = frame_arr[lo]
                else:
                    arr = frame_arr[lo] * (1.0 - frac) + frame_arr[hi] * frac
                out_frames.append(Image.fromarray(np.clip(arr, 0.0, 255.0).astype(np.uint8), mode="RGB"))
            else:
                si = _clamp_int(int(round(src_f)), 0, len(frame_arr) - 1)
                out_frames.append(Image.fromarray(np.clip(frame_arr[si], 0.0, 255.0).astype(np.uint8), mode="RGB"))

        fmt = _resolve_video_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_fps_convert")
        target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))

        ok, error = _save_video_from_pil(out_frames, fps=fps_out, target=target, fmt=fmt)
        if not ok:
            warnings.append(f"Failed to save output video: {error}")
            payload = _build_video_payload(_pil_to_tensor(out_frames), fps=fps_out, source_path=None)
            return (payload, "", _json_text({"warnings": warnings}))

        meta, meta_warnings = _read_video_metadata(target)
        warnings.extend(meta_warnings)
        payload = _make_video_payload(path=target, metadata=meta)
        summary = {
            "output_path": str(target),
            "input_fps": float(fps_in),
            "target_fps": float(fps_out),
            "input_frames": int(len(frames)),
            "output_frames": int(len(out_frames)),
            "mode": mode,
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRVideoGammaContrast:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "brightness": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_video_grade"}),
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
        gamma: float = 1.0,
        contrast: float = 1.0,
        brightness: float = 0.0,
        saturation: float = 1.0,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_video_grade",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, decode_warnings = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(decode_warnings)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        g = float(max(0.1, gamma))
        c = float(max(0.1, contrast))
        b = float(_clamp_float(brightness, -1.0, 1.0))
        s = float(max(0.0, saturation))

        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        out_frames: List[Image.Image] = []
        for frame in frames:
            arr = np.asarray(frame.convert("RGB"), dtype=np.float32) / 255.0
            arr = np.power(np.clip(arr, 0.0, 1.0), 1.0 / g)
            arr = (arr - 0.5) * c + 0.5
            lum = arr[:, :, 0:1] * 0.2126 + arr[:, :, 1:2] * 0.7152 + arr[:, :, 2:3] * 0.0722
            arr = lum * (1.0 - s) + arr * s
            arr = arr + b
            arr = np.clip(arr, 0.0, 1.0)
            out_frames.append(Image.fromarray((arr * 255.0).astype(np.uint8), mode="RGB"))

        fmt = _resolve_video_format(source=source, requested=output_format, warnings=warnings)
        out_dir = _output_dir(subfolder)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = _sanitize_basename(filename_label or filename_prefix, "MKR_video_grade")
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
            "gamma": float(g),
            "contrast": float(c),
            "brightness": float(b),
            "saturation": float(s),
            "warnings": warnings,
        }
        return (payload, str(target), _json_text(summary))


class MKRAudioEQ3Band:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "low_gain_db": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "mid_gain_db": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "high_gain_db": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "low_mid_hz": ("FLOAT", {"default": 250.0, "min": 20.0, "max": 4000.0, "step": 1.0}),
                "mid_high_hz": ("FLOAT", {"default": 3000.0, "min": 200.0, "max": 16000.0, "step": 1.0}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_eq3"}),
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
        low_gain_db: float = 0.0,
        mid_gain_db: float = 0.0,
        high_gain_db: float = 0.0,
        low_mid_hz: float = 250.0,
        mid_high_hz: float = 3000.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_eq3",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return _merge_audio_empty(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sr = int(max(1, sample_rate))
        n = int(w.shape[1])
        if n < 2:
            return _save_audio_result(
                waveform=w,
                sample_rate=sr,
                source=source,
                output_format=output_format,
                filename_prefix=filename_prefix,
                filename_label=filename_label,
                subfolder=subfolder,
                overwrite=overwrite,
                warnings=warnings,
            )

        f1 = float(max(20.0, min(float(low_mid_hz), sr * 0.45)))
        f2 = float(max(f1 + 20.0, min(float(mid_high_hz), sr * 0.49)))
        g_low = float(10.0 ** (float(low_gain_db) / 20.0))
        g_mid = float(10.0 ** (float(mid_gain_db) / 20.0))
        g_high = float(10.0 ** (float(high_gain_db) / 20.0))

        freqs = np.fft.rfftfreq(n, d=1.0 / float(sr)).astype(np.float32)
        gain = np.ones_like(freqs, dtype=np.float32) * g_mid
        low_mask = freqs <= f1
        high_mask = freqs >= f2
        gain[low_mask] = g_low
        gain[high_mask] = g_high

        # Smooth transitions between bands to avoid zipper artifacts.
        trans1 = (freqs > (f1 * 0.8)) & (freqs < (f1 * 1.2))
        if np.any(trans1):
            t = (freqs[trans1] - (f1 * 0.8)) / max(1e-6, f1 * 0.4)
            gain[trans1] = g_low * (1.0 - t) + g_mid * t
        trans2 = (freqs > (f2 * 0.8)) & (freqs < (f2 * 1.2))
        if np.any(trans2):
            t = (freqs[trans2] - (f2 * 0.8)) / max(1e-6, f2 * 0.4)
            gain[trans2] = g_mid * (1.0 - t) + g_high * t

        out = np.zeros_like(w, dtype=np.float32)
        for ch in range(w.shape[0]):
            spec = np.fft.rfft(w[ch].astype(np.float64))
            spec *= gain.astype(np.float64)
            out[ch] = np.fft.irfft(spec, n=n).astype(np.float32)
        out = np.clip(out, -1.0, 1.0)

        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sr,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "low_gain_db": float(low_gain_db),
            "mid_gain_db": float(mid_gain_db),
            "high_gain_db": float(high_gain_db),
            "low_mid_hz": float(f1),
            "mid_high_hz": float(f2),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRAudioStereoWidth:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "width": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.5, "step": 0.01}),
                "normalize_peak": ("BOOLEAN", {"default": False}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_stereo_width"}),
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
        width: float = 1.0,
        normalize_peak: bool = False,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_stereo_width",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return _merge_audio_empty(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        if w.shape[0] < 2:
            warnings.append("Input is mono; stereo width has no effect")
            out = w
        else:
            width_v = float(max(0.0, min(2.5, width)))
            left = w[0]
            right = w[1]
            mid = 0.5 * (left + right)
            side = 0.5 * (left - right) * width_v
            out_l = mid + side
            out_r = mid - side
            out = w.copy()
            out[0] = out_l
            out[1] = out_r

        if bool(normalize_peak):
            peak = float(np.max(np.abs(out)))
            if peak > 1e-9:
                out = out * float(0.98 / peak)
        out = np.clip(out, -1.0, 1.0)

        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=int(max(1, sample_rate)),
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        return (payload, path, float(duration), _merge_summary(summary, {"width": float(width)}))


class MKRAudioPadTrimDuration:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "target_duration_sec": ("FLOAT", {"default": 10.0, "min": 0.01, "max": 86400.0, "step": 0.01}),
                "pad_position": (["end", "start", "both"], {"default": "end"}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_padtrim"}),
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
        target_duration_sec: float = 10.0,
        pad_position: str = "end",
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_padtrim",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return _merge_audio_empty(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sr = int(max(1, sample_rate))
        target_samples = int(max(1, round(float(max(0.01, target_duration_sec)) * float(sr))))
        current = int(w.shape[1])
        out = w

        if current > target_samples:
            out = w[:, :target_samples]
        elif current < target_samples:
            pad = target_samples - current
            mode = str(pad_position or "end").strip().lower()
            if mode == "start":
                left = np.zeros((w.shape[0], pad), dtype=np.float32)
                out = np.concatenate([left, w], axis=1)
            elif mode == "both":
                left_n = pad // 2
                right_n = pad - left_n
                left = np.zeros((w.shape[0], left_n), dtype=np.float32)
                right = np.zeros((w.shape[0], right_n), dtype=np.float32)
                out = np.concatenate([left, w, right], axis=1)
            else:
                right = np.zeros((w.shape[0], pad), dtype=np.float32)
                out = np.concatenate([w, right], axis=1)

        payload, path, duration, summary = _save_audio_result(
            waveform=np.clip(out, -1.0, 1.0),
            sample_rate=sr,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "target_duration_sec": float(target_duration_sec),
            "output_samples": int(out.shape[1]),
            "pad_position": str(pad_position),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRAudioChannelRouter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "mode": (["keep", "mono_mix", "left_only", "right_only", "swap_lr", "stereo_from_mono"], {"default": "keep"}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_channel_router"}),
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
        mode: str = "keep",
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_channel_router",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return _merge_audio_empty(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        m = str(mode or "keep").strip().lower()
        out = w
        if m == "mono_mix":
            mono = np.mean(w, axis=0, keepdims=True, dtype=np.float32)
            out = mono
        elif m == "left_only":
            left = w[0:1, :]
            out = np.repeat(left, 2, axis=0)
        elif m == "right_only":
            if w.shape[0] >= 2:
                right = w[1:2, :]
            else:
                right = w[0:1, :]
            out = np.repeat(right, 2, axis=0)
        elif m == "swap_lr":
            if w.shape[0] >= 2:
                out = w.copy()
                out[0], out[1] = w[1], w[0]
            else:
                warnings.append("Input is mono, cannot swap LR")
                out = np.repeat(w[0:1, :], 2, axis=0)
        elif m == "stereo_from_mono":
            if w.shape[0] == 1:
                out = np.repeat(w, 2, axis=0)
            else:
                out = w[:2, :]

        out = np.clip(out, -1.0, 1.0)
        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=int(max(1, sample_rate)),
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        return (payload, path, float(duration), _merge_summary(summary, {"mode": m}))


class MKRAudioBitcrush:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "bit_depth": ("INT", {"default": 8, "min": 2, "max": 16, "step": 1}),
                "sample_hold": ("INT", {"default": 1, "min": 1, "max": 128, "step": 1}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio_bitcrush"}),
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
        bit_depth: int = 8,
        sample_hold: int = 1,
        mix: float = 1.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio_bitcrush",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sample_rate, source, error = _load_audio_waveform(audio)
        if waveform is None:
            if error:
                warnings.append(error)
            return _merge_audio_empty(source, warnings)

        dry = waveform.astype(np.float32, copy=False)
        bits = int(_clamp_int(bit_depth, 2, 16))
        hold = int(max(1, sample_hold))
        wet = dry.copy()

        levels = float((2 ** bits) - 1)
        wet = np.round(((wet + 1.0) * 0.5) * levels) / levels
        wet = (wet * 2.0) - 1.0

        if hold > 1:
            for ch in range(wet.shape[0]):
                ch_arr = wet[ch]
                for i in range(0, len(ch_arr), hold):
                    ch_arr[i : i + hold] = ch_arr[i]
                wet[ch] = ch_arr

        mix_v = float(_clamp_float(mix, 0.0, 1.0))
        out = dry * (1.0 - mix_v) + wet * mix_v
        out = np.clip(out, -1.0, 1.0)

        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=int(max(1, sample_rate)),
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {"bit_depth": int(bits), "sample_hold": int(hold), "mix": float(mix_v)}
        return (payload, path, float(duration), _merge_summary(summary, extra))
