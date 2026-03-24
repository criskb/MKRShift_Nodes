from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PIL import Image
import torch

from .image_shared import mask_to_batch, to_image_batch


def _pil_rgba_from_float(image: np.ndarray) -> Image.Image:
    rgba = np.clip(image * 255.0, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _float_rgba_from_pil(image: Image.Image) -> np.ndarray:
    return (np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _resize_rgba(image: np.ndarray, height: int, width: int, resize_mode: str) -> np.ndarray:
    if image.shape[0] == height and image.shape[1] == width:
        return image.astype(np.float32, copy=False)

    pil = _pil_rgba_from_float(image)
    mode = str(resize_mode or "stretch").lower()
    if mode == "contain":
        fitted = pil.copy()
        fitted.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offset = ((width - fitted.width) // 2, (height - fitted.height) // 2)
        canvas.alpha_composite(fitted, dest=offset)
        return _float_rgba_from_pil(canvas)

    if mode == "cover":
        scale = max(width / max(1, pil.width), height / max(1, pil.height))
        next_size = (
            max(1, int(round(pil.width * scale))),
            max(1, int(round(pil.height * scale))),
        )
        fitted = pil.resize(next_size, resample=Image.Resampling.LANCZOS)
        left = max(0, (fitted.width - width) // 2)
        top = max(0, (fitted.height - height) // 2)
        cropped = fitted.crop((left, top, left + width, top + height))
        return _float_rgba_from_pil(cropped)

    stretched = pil.resize((width, height), resample=Image.Resampling.LANCZOS)
    return _float_rgba_from_pil(stretched)


def fit_image_batch_to_rgba(image: torch.Tensor, batch: int, height: int, width: int, resize_mode: str = "stretch") -> np.ndarray:
    tensor = to_image_batch(image).detach().cpu().numpy().astype(np.float32, copy=False)
    if tensor.shape[0] == 1 and batch > 1:
        tensor = np.repeat(tensor, batch, axis=0)
    if tensor.shape[0] != batch:
        raise ValueError(f"Image batch {tensor.shape[0]} does not match expected batch {batch}")

    output = np.empty((batch, height, width, 4), dtype=np.float32)
    for idx in range(batch):
        sample = tensor[idx]
        if sample.shape[-1] == 3:
            alpha = np.ones(sample.shape[:2] + (1,), dtype=np.float32)
            rgba = np.concatenate([sample, alpha], axis=-1)
        elif sample.shape[-1] == 4:
            rgba = sample
        else:
            raise ValueError(f"Unsupported image channels={sample.shape[-1]}")
        output[idx] = _resize_rgba(np.clip(rgba, 0.0, 1.0), height, width, resize_mode)
    return output


def fit_optional_mask(mask: Optional[torch.Tensor], batch: int, height: int, width: int, feather_radius: float, device: torch.device, dtype: torch.dtype) -> Optional[np.ndarray]:
    if mask is None:
        return None
    mask_tensor = mask_to_batch(
        mask=mask,
        batch=batch,
        h=height,
        w=width,
        feather_radius=feather_radius,
        invert_mask=False,
        device=device,
        dtype=dtype,
    )
    return mask_tensor.detach().cpu().numpy().astype(np.float32, copy=False)


def blend_mode_np(base: np.ndarray, layer: np.ndarray, mode: str) -> np.ndarray:
    m = str(mode or "normal").lower()
    if m == "normal":
        return layer
    if m == "add":
        return np.clip(base + layer, 0.0, 1.0).astype(np.float32, copy=False)
    if m == "screen":
        return (1.0 - (1.0 - base) * (1.0 - layer)).astype(np.float32, copy=False)
    if m == "multiply":
        return (base * layer).astype(np.float32, copy=False)
    if m == "overlay":
        return np.where(base <= 0.5, 2.0 * base * layer, 1.0 - 2.0 * (1.0 - base) * (1.0 - layer)).astype(np.float32, copy=False)
    if m == "soft_light":
        root = np.sqrt(np.clip(base, 0.0, 1.0))
        return np.where(
            layer <= 0.5,
            base - (1.0 - (2.0 * layer)) * base * (1.0 - base),
            base + ((2.0 * layer) - 1.0) * (root - base),
        ).astype(np.float32, copy=False)
    if m == "lighten":
        return np.maximum(base, layer).astype(np.float32, copy=False)
    if m == "darken":
        return np.minimum(base, layer).astype(np.float32, copy=False)
    return layer.astype(np.float32, copy=False)


def composite_single_layer(
    base_rgb: np.ndarray,
    layer_rgba: np.ndarray,
    extra_mask: Optional[np.ndarray],
    opacity: float,
    blend_mode: str,
) -> Tuple[np.ndarray, np.ndarray]:
    layer_rgb = np.clip(layer_rgba[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    layer_alpha = np.clip(layer_rgba[..., 3], 0.0, 1.0).astype(np.float32, copy=False)
    if extra_mask is not None:
        layer_alpha = np.clip(layer_alpha * np.clip(extra_mask, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)
    layer_alpha = np.clip(layer_alpha * float(np.clip(opacity, 0.0, 1.0)), 0.0, 1.0).astype(np.float32, copy=False)
    blended = blend_mode_np(base_rgb, layer_rgb, blend_mode)
    out = (base_rgb * (1.0 - layer_alpha[..., None])) + (blended * layer_alpha[..., None])
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False), layer_alpha
