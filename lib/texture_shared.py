import numpy as np

from .image_shared import gaussian_blur_rgb_np, smoothstep_np
from .scalar_map_shared import blur_single_channel


def roll_image_np(image: np.ndarray, shift_y: int, shift_x: int) -> np.ndarray:
    if image.ndim == 2:
        return np.roll(image, shift=(int(shift_y), int(shift_x)), axis=(0, 1))
    return np.roll(image, shift=(int(shift_y), int(shift_x)), axis=(0, 1)).astype(np.float32, copy=False)


def seam_band_1d(length: int, positions: list[float], half_width: float, softness: float) -> np.ndarray:
    coords = np.arange(int(length), dtype=np.float32)
    width = float(max(0.0, half_width))
    soft = float(max(0.0, softness))
    mask = np.zeros((int(length),), dtype=np.float32)
    if width <= 1e-6 or not positions:
        return mask

    inner = max(0.0, width - soft)
    outer = width + soft
    for position in positions:
        dist = np.abs(coords - float(position))
        if soft <= 1e-6:
            band = (dist <= width).astype(np.float32)
        else:
            band = 1.0 - smoothstep_np(inner, outer, dist)
        mask = np.maximum(mask, np.clip(band, 0.0, 1.0).astype(np.float32, copy=False))
    return mask


def cross_seam_mask(
    h: int,
    w: int,
    seam_x: float | None,
    seam_y: float | None,
    half_width: float,
    softness: float,
) -> np.ndarray:
    x_positions = [] if seam_x is None else [float(seam_x)]
    y_positions = [] if seam_y is None else [float(seam_y)]
    x_mask = seam_band_1d(int(w), x_positions, half_width=half_width, softness=softness)[None, :]
    y_mask = seam_band_1d(int(h), y_positions, half_width=half_width, softness=softness)[:, None]
    return np.maximum(y_mask, x_mask).astype(np.float32, copy=False)


def tile_grid_mask(h: int, w: int, tiles_y: int, tiles_x: int, half_width: float, softness: float) -> np.ndarray:
    x_positions = [float((w * idx) / tiles_x) for idx in range(1, max(1, int(tiles_x)))]
    y_positions = [float((h * idx) / tiles_y) for idx in range(1, max(1, int(tiles_y)))]
    x_mask = seam_band_1d(int(w), x_positions, half_width=half_width, softness=softness)[None, :]
    y_mask = seam_band_1d(int(h), y_positions, half_width=half_width, softness=softness)[:, None]
    return np.maximum(y_mask, x_mask).astype(np.float32, copy=False)


def edge_match_low_frequency(image: np.ndarray, blur_radius: float, edge_band: int, strength: float) -> np.ndarray:
    if image.ndim not in (2, 3):
        raise ValueError(f"Unsupported image dims={image.ndim}")

    h, w = image.shape[:2]
    band = int(max(1, min(edge_band, h, w)))
    amt = float(np.clip(strength, 0.0, 1.0))
    if amt <= 1e-6:
        return image.astype(np.float32, copy=False)

    if image.ndim == 3:
        low = gaussian_blur_rgb_np(image, radius=blur_radius)
    else:
        low = blur_single_channel(image, radius=blur_radius)
    high = image - low

    left = np.mean(low[:, :band, ...], axis=(0, 1))
    right = np.mean(low[:, w - band :, ...], axis=(0, 1))
    top = np.mean(low[:band, :, ...], axis=(0, 1))
    bottom = np.mean(low[h - band :, :, ...], axis=(0, 1))

    x = np.linspace(0.5, -0.5, int(w), dtype=np.float32)
    y = np.linspace(0.5, -0.5, int(h), dtype=np.float32)

    if image.ndim == 3:
        corr_x = x[None, :, None] * (right - left)[None, None, :]
        corr_y = y[:, None, None] * (bottom - top)[None, None, :]
    else:
        corr_x = x[None, :] * float(right - left)
        corr_y = y[:, None] * float(bottom - top)

    matched = np.clip(low + ((corr_x + corr_y) * amt) + high, 0.0, 1.0)
    return matched.astype(np.float32, copy=False)


def smooth_seams(image: np.ndarray, seam_mask: np.ndarray, blur_radius: float, detail_preserve: float) -> np.ndarray:
    blend = np.clip(seam_mask, 0.0, 1.0).astype(np.float32, copy=False)
    keep = float(np.clip(detail_preserve, 0.0, 1.0))
    if np.max(blend) <= 1e-6 or float(max(0.0, blur_radius)) <= 1e-6:
        return image.astype(np.float32, copy=False)

    if image.ndim == 3:
        low = gaussian_blur_rgb_np(image, radius=blur_radius)
        high = image - low
        softened = np.clip(low + (high * keep), 0.0, 1.0)
        out = (image * (1.0 - blend[..., None])) + (softened * blend[..., None])
    else:
        low = blur_single_channel(image, radius=blur_radius)
        high = image - low
        softened = np.clip(low + (high * keep), 0.0, 1.0)
        out = (image * (1.0 - blend)) + (softened * blend)
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)
