import math
import os
from pathlib import Path
from typing import Optional
import uuid

import numpy as np
from PIL import Image, ImageFilter
import torch

from ..categories import UTILITY_MASK

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
THIS_DIR = str(PACKAGE_ROOT)


def _to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")
    t = image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(t.shape)}")
    if t.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(t.shape)}")
    return t.clamp(0.0, 1.0)


def _to_mask_batch(mask: Optional[torch.Tensor], batch: int, h: int, w: int) -> Optional[np.ndarray]:
    if mask is None:
        return None
    if not torch.is_tensor(mask):
        raise TypeError("base_mask input is not a torch tensor")

    m = mask.detach().float().cpu()
    if m.ndim == 2:
        m = m.unsqueeze(0)
    elif m.ndim == 4:
        if m.shape[-1] in (1, 3, 4):
            m = m[..., 0]
        elif m.shape[1] in (1, 3, 4):
            m = m[:, 0, ...]
        else:
            raise ValueError(f"Unsupported base_mask shape={tuple(m.shape)}")
    elif m.ndim != 3:
        raise ValueError(f"Unsupported base_mask dims={m.ndim}")

    if m.shape[0] == 1 and batch > 1:
        m = m.expand(batch, -1, -1)
    elif m.shape[0] != batch:
        raise ValueError(f"base_mask batch {m.shape[0]} does not match image batch {batch}")

    out = np.zeros((batch, h, w), dtype=np.float32)
    for idx in range(batch):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        pil = Image.fromarray((sample * 255.0).astype(np.uint8), mode="L")
        if pil.size != (w, h):
            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
        out[idx] = np.asarray(pil, dtype=np.float32) / 255.0
    return np.clip(out, 0.0, 1.0)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= edge1).astype(np.float32)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32, copy=False)


def _soft_threshold(x: np.ndarray, threshold: float, softness: float) -> np.ndarray:
    s = max(0.0, float(softness))
    if s <= 1e-6:
        return (x >= float(threshold)).astype(np.float32)
    half = s * 0.5
    return _smoothstep(float(threshold) - half, float(threshold) + half, x)


def _soft_range(x: np.ndarray, min_v: float, max_v: float, softness: float) -> np.ndarray:
    lo = float(min(min_v, max_v))
    hi = float(max(min_v, max_v))
    lower = _soft_threshold(x, lo, softness)
    upper = 1.0 - _soft_threshold(x, hi, softness)
    return np.clip(lower * upper, 0.0, 1.0)


def _soft_band_circular(x: np.ndarray, center: float, half_width: float, softness: float) -> np.ndarray:
    c = float(center)
    hw = max(0.0, float(half_width))
    soft = max(0.0, float(softness))
    dist = np.abs(((x - c + 0.5) % 1.0) - 0.5)
    inner = hw
    outer = hw + soft
    return 1.0 - _smoothstep(inner, outer, dist)


def _rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    v = maxc
    s = np.where(maxc > 1e-8, delta / np.maximum(maxc, 1e-8), 0.0).astype(np.float32, copy=False)
    h = np.zeros_like(maxc, dtype=np.float32)

    mask = delta > 1e-8
    r_is_max = (maxc == r) & mask
    g_is_max = (maxc == g) & mask
    b_is_max = (maxc == b) & mask

    h[r_is_max] = ((g[r_is_max] - b[r_is_max]) / delta[r_is_max]) % 6.0
    h[g_is_max] = ((b[g_is_max] - r[g_is_max]) / delta[g_is_max]) + 2.0
    h[b_is_max] = ((r[b_is_max] - g[b_is_max]) / delta[b_is_max]) + 4.0
    h = (h / 6.0) % 1.0
    return h.astype(np.float32, copy=False), s, v.astype(np.float32, copy=False)


def _channel_map(rgb: np.ndarray, alpha: np.ndarray, channel: str) -> np.ndarray:
    key = str(channel).lower()
    if key == "red":
        return rgb[..., 0]
    if key == "green":
        return rgb[..., 1]
    if key == "blue":
        return rgb[..., 2]
    if key == "alpha":
        return alpha
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32, copy=False)


def _build_mode_mask(
    rgb: np.ndarray,
    alpha: np.ndarray,
    mode: str,
    channel: str,
    threshold: float,
    softness: float,
    min_value: float,
    max_value: float,
    hue_center: float,
    hue_width: float,
    target_r: float,
    target_g: float,
    target_b: float,
    color_tolerance: float,
    edge_radius: float,
    edge_strength: float,
    center_x: float,
    center_y: float,
    radius: float,
    falloff: float,
) -> np.ndarray:
    h, w = rgb.shape[:2]
    mode_key = str(mode).lower()
    soft = float(max(0.0, softness))

    if mode_key == "channel":
        v = _channel_map(rgb, alpha, channel)
        return _soft_threshold(v, float(threshold), soft)

    if mode_key == "hue":
        hue, _, _ = _rgb_to_hsv(rgb)
        hc = (float(hue_center) % 360.0) / 360.0
        hw = max(0.0, min(180.0, float(hue_width))) / 360.0
        hs = max(1e-6, soft * 0.5) / 360.0
        return np.clip(_soft_band_circular(hue, hc, hw, hs), 0.0, 1.0)

    if mode_key == "saturation":
        _, sat, _ = _rgb_to_hsv(rgb)
        return _soft_range(sat, float(min_value), float(max_value), soft)

    if mode_key == "value":
        _, _, val = _rgb_to_hsv(rgb)
        return _soft_range(val, float(min_value), float(max_value), soft)

    if mode_key == "skin_tones":
        hue, sat, val = _rgb_to_hsv(rgb)
        warm_band = _soft_band_circular(hue, 24.0 / 360.0, 32.0 / 360.0, max(0.02, soft * 0.5))
        sat_band = _soft_range(sat, 0.10, 0.68, max(0.04, soft))
        val_band = _soft_range(val, 0.18, 1.0, max(0.05, soft))
        red_over_green = _soft_threshold(rgb[..., 0] - rgb[..., 1], 0.015, max(0.02, soft * 0.5))
        green_over_blue = _soft_threshold(rgb[..., 1] - rgb[..., 2], -0.02, max(0.02, soft * 0.5))
        red_over_blue = _soft_threshold(rgb[..., 0] - rgb[..., 2], 0.08, max(0.03, soft))
        return np.clip(
            warm_band * sat_band * val_band * red_over_green * green_over_blue * red_over_blue,
            0.0,
            1.0,
        )

    if mode_key == "chroma_key":
        target = np.asarray([target_r, target_g, target_b], dtype=np.float32)
        dist = np.linalg.norm(rgb - target[None, None, :], axis=-1) / math.sqrt(3.0)
        tol = float(max(0.0, color_tolerance))
        return np.clip(1.0 - _soft_threshold(dist, tol, soft), 0.0, 1.0)

    if mode_key == "edge":
        luma = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32, copy=False)
        if edge_radius > 1e-6:
            pil = Image.fromarray(np.clip(luma * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
            pil = pil.filter(ImageFilter.GaussianBlur(radius=float(max(0.0, edge_radius))))
            luma = np.asarray(pil, dtype=np.float32) / 255.0
        gy, gx = np.gradient(luma)
        mag = np.sqrt((gx * gx) + (gy * gy))
        norm = np.percentile(mag, 98.0)
        mag = mag / max(1e-6, float(norm))
        mag = np.clip(mag * float(max(0.0, edge_strength)), 0.0, 1.0)
        return _soft_threshold(mag, float(threshold), soft)

    if mode_key == "radial":
        xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        dist = np.sqrt((xx - float(center_x)) ** 2 + (yy - float(center_y)) ** 2)
        r0 = float(max(0.0, radius))
        s = max(1e-6, soft)
        mask = 1.0 - _smoothstep(r0, r0 + s, dist)
        return np.power(np.clip(mask, 0.0, 1.0), float(max(0.05, falloff))).astype(np.float32, copy=False)

    luma = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32, copy=False)
    return _soft_threshold(luma, float(threshold), soft)


def _expand_or_erode(mask: np.ndarray, pixels: int) -> np.ndarray:
    px = int(pixels)
    if px == 0:
        return np.clip(mask, 0.0, 1.0).astype(np.float32, copy=False)

    kernel = max(3, (abs(px) * 2) + 1)
    if kernel % 2 == 0:
        kernel += 1
    pil = Image.fromarray(np.clip(mask * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    if px > 0:
        pil = pil.filter(ImageFilter.MaxFilter(size=kernel))
    else:
        pil = pil.filter(ImageFilter.MinFilter(size=kernel))
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _temp_dir() -> str:
    if folder_paths and hasattr(folder_paths, "get_temp_directory"):
        return str(folder_paths.get_temp_directory())
    fallback = os.path.join(THIS_DIR, ".temp")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _make_preview_image(image: np.ndarray) -> Optional[Image.Image]:
    try:
        arr = np.asarray(image)
        if arr.ndim != 3 or arr.shape[-1] not in (1, 3, 4):
            return None
        if arr.shape[-1] == 1:
            arr = np.repeat(arr, 3, axis=-1)
        elif arr.shape[-1] == 4:
            arr = arr[..., :3]
        arr = np.clip(arr, 0.0, 1.0)
        arr_u8 = (arr * 255.0).round().astype(np.uint8)
        img = Image.fromarray(arr_u8, mode="RGB")
        img.thumbnail((1024, 1024), resample=Image.Resampling.LANCZOS)
        return img
    except Exception:
        return None


def _save_temp_preview(image: np.ndarray, prefix: str = "mkrshift_maskgen") -> Optional[dict]:
    preview = _make_preview_image(image)
    if preview is None:
        return None
    output_dir = _temp_dir()
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.png"
    target = os.path.join(output_dir, filename)
    preview.save(target, format="PNG", compress_level=1)
    return {"filename": filename, "subfolder": "", "type": "temp"}


class x1MaskGen:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (
                    [
                        "luminance",
                        "channel",
                        "hue",
                        "saturation",
                        "value",
                        "skin_tones",
                        "chroma_key",
                        "edge",
                        "radial",
                    ],
                ),
                "channel": (["luma", "red", "green", "blue", "alpha"],),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "softness": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.001}),
                "min_value": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.001}),
                "max_value": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.001}),
                "hue_center": ("FLOAT", {"default": 120.0, "min": 0.0, "max": 360.0, "step": 0.1}),
                "hue_width": ("FLOAT", {"default": 24.0, "min": 0.0, "max": 180.0, "step": 0.1}),
                "target_r": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "target_g": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "target_b": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "color_tolerance": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.001}),
                "edge_radius": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 32.0, "step": 0.1}),
                "edge_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "radius": ("FLOAT", {"default": 0.28, "min": 0.0, "max": 2.0, "step": 0.001}),
                "falloff": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 6.0, "step": 0.01}),
                "combine_mode": (["replace", "multiply", "maximum", "minimum", "add"],),
                "expand_pixels": ("INT", {"default": 0, "min": -64, "max": 64, "step": 1}),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "mask_gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "base_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("mask", "preview", "mask_info")
    FUNCTION = "run"
    CATEGORY = UTILITY_MASK

    def run(
        self,
        image: torch.Tensor,
        mode: str = "luminance",
        channel: str = "luma",
        threshold: float = 0.5,
        softness: float = 0.08,
        min_value: float = 0.2,
        max_value: float = 0.8,
        hue_center: float = 120.0,
        hue_width: float = 24.0,
        target_r: float = 0.0,
        target_g: float = 1.0,
        target_b: float = 0.0,
        color_tolerance: float = 0.25,
        edge_radius: float = 1.0,
        edge_strength: float = 1.0,
        center_x: float = 0.5,
        center_y: float = 0.5,
        radius: float = 0.28,
        falloff: float = 1.0,
        combine_mode: str = "replace",
        expand_pixels: int = 0,
        blur_radius: float = 0.0,
        mask_gamma: float = 1.0,
        invert_mask: bool = False,
        base_mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        if c == 4:
            alpha_np = batch[..., 3].detach().cpu().numpy().astype(np.float32, copy=False)
        else:
            alpha_np = np.ones((int(b), int(h), int(w)), dtype=np.float32)

        base_np = _to_mask_batch(base_mask, int(b), int(h), int(w))

        out_mask = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        out_preview = np.zeros((int(b), int(h), int(w), 3), dtype=np.float32)

        for idx in range(int(b)):
            m = _build_mode_mask(
                rgb=rgb_np[idx],
                alpha=alpha_np[idx],
                mode=str(mode),
                channel=str(channel),
                threshold=float(threshold),
                softness=float(softness),
                min_value=float(min_value),
                max_value=float(max_value),
                hue_center=float(hue_center),
                hue_width=float(hue_width),
                target_r=float(target_r),
                target_g=float(target_g),
                target_b=float(target_b),
                color_tolerance=float(color_tolerance),
                edge_radius=float(edge_radius),
                edge_strength=float(edge_strength),
                center_x=float(center_x),
                center_y=float(center_y),
                radius=float(radius),
                falloff=float(falloff),
            )

            if base_np is not None:
                base = base_np[idx]
                mode_key = str(combine_mode).lower()
                if mode_key == "multiply":
                    m = m * base
                elif mode_key == "maximum":
                    m = np.maximum(m, base)
                elif mode_key == "minimum":
                    m = np.minimum(m, base)
                elif mode_key == "add":
                    m = np.clip(m + base, 0.0, 1.0)

            m = _expand_or_erode(m, int(expand_pixels))

            if float(blur_radius) > 1e-6:
                pil = Image.fromarray(np.clip(m * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
                pil = pil.filter(ImageFilter.GaussianBlur(radius=float(max(0.0, blur_radius))))
                m = np.asarray(pil, dtype=np.float32) / 255.0

            g = float(max(0.1, mask_gamma))
            if abs(g - 1.0) > 1e-6:
                m = np.power(np.clip(m, 0.0, 1.0), g)

            if invert_mask:
                m = 1.0 - m

            m = np.clip(m, 0.0, 1.0).astype(np.float32, copy=False)
            out_mask[idx] = m

            overlay = np.asarray([0.16, 0.98, 0.42], dtype=np.float32)
            out_preview[idx] = np.clip(
                (rgb_np[idx] * (1.0 - (m[..., None] * 0.55))) + (overlay[None, None, :] * (m[..., None] * 0.55)),
                0.0,
                1.0,
            )

        mask_t = torch.from_numpy(out_mask).to(device=batch.device, dtype=batch.dtype)
        preview_t = torch.from_numpy(out_preview).to(device=batch.device, dtype=batch.dtype)

        coverage = float(out_mask.mean() * 100.0)
        info = (
            "x1MaskGen: mode={}, combine={}, threshold={:.3f}, softness={:.3f}, "
            "range=[{:.3f},{:.3f}], hue={:.1f}±{:.1f}, key=({:.2f},{:.2f},{:.2f}) tol={:.3f}, "
            "edge(r={:.1f},s={:.2f}), radial(c={:.3f},{:.3f},r={:.3f},f={:.2f}), "
            "expand={}px, blur={:.1f}px, gamma={:.2f}, coverage={:.2f}%{}"
        ).format(
            str(mode),
            str(combine_mode),
            float(threshold),
            float(softness),
            float(min_value),
            float(max_value),
            float(hue_center),
            float(hue_width),
            float(target_r),
            float(target_g),
            float(target_b),
            float(color_tolerance),
            float(edge_radius),
            float(edge_strength),
            float(center_x),
            float(center_y),
            float(radius),
            float(falloff),
            int(expand_pixels),
            float(blur_radius),
            float(mask_gamma),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        preview_info = _save_temp_preview(out_preview[0] if out_preview.size > 0 else out_preview)
        ui_payload = {}
        if preview_info is not None:
            ui_payload["mask_preview"] = [preview_info]
        ui_payload["mask_stats"] = [{"coverage": coverage}]

        return {
            "ui": ui_payload,
            "result": (
                mask_t.clamp(0.0, 1.0),
                preview_t.clamp(0.0, 1.0),
                info,
            ),
        }
