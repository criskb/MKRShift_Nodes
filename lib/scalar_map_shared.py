from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
import torch

from .image_shared import luma_np, rgb_to_hsv_np


PALETTES: dict[str, tuple[np.ndarray, np.ndarray]] = {
    "inferno": (
        np.asarray([0.00, 0.12, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.00, 0.00, 0.02],
                [0.12, 0.04, 0.25],
                [0.34, 0.06, 0.43],
                [0.58, 0.14, 0.39],
                [0.82, 0.28, 0.22],
                [0.96, 0.50, 0.10],
                [0.99, 0.77, 0.21],
                [0.99, 0.99, 0.64],
            ],
            dtype=np.float32,
        ),
    ),
    "viridis": (
        np.asarray([0.00, 0.18, 0.35, 0.52, 0.70, 0.86, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.27, 0.00, 0.33],
                [0.26, 0.23, 0.51],
                [0.16, 0.47, 0.56],
                [0.13, 0.66, 0.52],
                [0.37, 0.79, 0.38],
                [0.68, 0.86, 0.19],
                [0.99, 0.91, 0.14],
            ],
            dtype=np.float32,
        ),
    ),
    "plasma": (
        np.asarray([0.00, 0.18, 0.36, 0.54, 0.72, 0.88, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.05, 0.03, 0.53],
                [0.37, 0.00, 0.65],
                [0.64, 0.11, 0.61],
                [0.84, 0.29, 0.46],
                [0.96, 0.53, 0.28],
                [0.99, 0.75, 0.16],
                [0.94, 0.98, 0.13],
            ],
            dtype=np.float32,
        ),
    ),
    "magma": (
        np.asarray([0.00, 0.16, 0.32, 0.48, 0.66, 0.84, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.00, 0.00, 0.02],
                [0.18, 0.05, 0.34],
                [0.41, 0.10, 0.43],
                [0.64, 0.18, 0.38],
                [0.86, 0.32, 0.27],
                [0.98, 0.57, 0.22],
                [0.99, 0.99, 0.75],
            ],
            dtype=np.float32,
        ),
    ),
    "turbo": (
        np.asarray([0.00, 0.14, 0.28, 0.42, 0.56, 0.70, 0.84, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.19, 0.07, 0.23],
                [0.27, 0.27, 0.77],
                [0.16, 0.54, 0.96],
                [0.13, 0.78, 0.59],
                [0.67, 0.90, 0.18],
                [0.98, 0.74, 0.17],
                [0.93, 0.39, 0.13],
                [0.48, 0.02, 0.01],
            ],
            dtype=np.float32,
        ),
    ),
    "thermal": (
        np.asarray([0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.00, 0.00, 0.00],
                [0.00, 0.00, 0.80],
                [0.00, 0.70, 1.00],
                [0.00, 1.00, 0.00],
                [1.00, 1.00, 0.00],
                [1.00, 0.45, 0.00],
                [1.00, 0.00, 0.00],
            ],
            dtype=np.float32,
        ),
    ),
    "icefire": (
        np.asarray([0.00, 0.18, 0.34, 0.50, 0.66, 0.82, 1.00], dtype=np.float32),
        np.asarray(
            [
                [0.02, 0.07, 0.25],
                [0.00, 0.34, 0.68],
                [0.33, 0.72, 0.93],
                [0.94, 0.95, 0.97],
                [0.96, 0.63, 0.39],
                [0.80, 0.20, 0.11],
                [0.28, 0.01, 0.08],
            ],
            dtype=np.float32,
        ),
    ),
}


def mask_tensor_to_np(mask: torch.Tensor, batch: int, h: int, w: int) -> np.ndarray:
    m = mask.detach().float().cpu()
    if m.ndim == 2:
        m = m.unsqueeze(0)
    elif m.ndim == 4:
        if m.shape[-1] in (1, 3, 4):
            m = m[..., 0]
        elif m.shape[1] in (1, 3, 4):
            m = m[:, 0, ...]
        else:
            raise ValueError(f"Unsupported MASK shape={tuple(m.shape)}")
    elif m.ndim != 3:
        raise ValueError(f"Unsupported MASK dims={m.ndim}")

    if m.shape[0] == 1 and batch > 1:
        m = m.expand(batch, -1, -1)
    elif m.shape[0] != batch:
        raise ValueError(f"Mask batch {m.shape[0]} does not match image batch {batch}")

    out = np.zeros((batch, h, w), dtype=np.float32)
    for idx in range(batch):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        if sample.shape != (h, w):
            sample_t = torch.from_numpy(sample).unsqueeze(0).unsqueeze(0)
            sample = (
                torch.nn.functional.interpolate(
                    sample_t,
                    size=(h, w),
                    mode="bilinear",
                    align_corners=False,
                )
                .squeeze()
                .numpy()
            )
        out[idx] = np.clip(sample, 0.0, 1.0)
    return out


def scalar_from_source(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    fallback_to_luma: bool,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode == "red":
        return src[..., 0].astype(np.float32, copy=False), mode
    if mode == "green":
        return src[..., 1].astype(np.float32, copy=False), mode
    if mode == "blue":
        return src[..., 2].astype(np.float32, copy=False), mode
    if mode == "max_rgb":
        return np.max(src[..., :3], axis=-1).astype(np.float32, copy=False), mode
    if mode in {"saturation", "value"}:
        _, s, v = rgb_to_hsv_np(src[..., :3])
        return (s if mode == "saturation" else v).astype(np.float32, copy=False), mode
    if mode == "alpha":
        if src.shape[-1] >= 4:
            return src[..., 3].astype(np.float32, copy=False), mode
        if fallback_to_luma:
            return luma_np(src[..., :3]), "luma(fallback)"
    if mode == "mask":
        if source_mask_np is not None:
            return source_mask_np.astype(np.float32, copy=False), mode
        if fallback_to_luma:
            return luma_np(src[..., :3]), "luma(fallback)"
    return luma_np(src[..., :3]), "luma"


def normalize_scalar(
    scalar: np.ndarray,
    normalize_mode: str,
    value_min: float,
    value_max: float,
    percentile_low: float,
    percentile_high: float,
    gamma: float,
    invert_values: bool,
) -> tuple[np.ndarray, float, float]:
    mode = str(normalize_mode).lower()
    if mode == "auto_range":
        lo = float(np.min(scalar))
        hi = float(np.max(scalar))
    elif mode == "auto_percentile":
        low = float(np.clip(percentile_low, 0.0, 100.0))
        high = float(np.clip(percentile_high, low, 100.0))
        lo = float(np.percentile(scalar, low))
        hi = float(np.percentile(scalar, high))
    else:
        lo = float(value_min)
        hi = float(value_max)

    if hi <= lo + 1e-6:
        normalized = np.zeros_like(scalar, dtype=np.float32)
    else:
        normalized = np.clip((scalar - lo) / (hi - lo), 0.0, 1.0).astype(np.float32, copy=False)

    if bool(invert_values):
        normalized = 1.0 - normalized

    gamma_value = float(max(1e-3, gamma))
    if abs(gamma_value - 1.0) > 1e-6:
        normalized = np.power(np.clip(normalized, 0.0, 1.0), gamma_value).astype(np.float32, copy=False)

    return np.clip(normalized, 0.0, 1.0).astype(np.float32, copy=False), lo, hi


def apply_palette(values: np.ndarray, palette: str) -> np.ndarray:
    stops, colors = PALETTES.get(str(palette).lower(), PALETTES["inferno"])
    out = np.empty(values.shape + (3,), dtype=np.float32)
    for channel in range(3):
        out[..., channel] = np.interp(values, stops, colors[:, channel]).astype(np.float32, copy=False)
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def blur_single_channel(channel: np.ndarray, radius: float) -> np.ndarray:
    blur_radius = float(max(0.0, radius))
    if blur_radius <= 1e-6:
        return channel.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(channel * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    pil = pil.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)
