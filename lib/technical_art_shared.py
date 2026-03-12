from typing import Optional

import numpy as np
import torch

from .image_shared import gaussian_blur_rgb_np, luma_np, mask_to_batch, to_image_batch
from .scalar_map_shared import mask_tensor_to_np


def match_image_batch(image: torch.Tensor, batch: int, h: int, w: int) -> torch.Tensor:
    t = to_image_batch(image)
    if t.shape[0] == 1 and int(batch) > 1:
        t = t.expand(int(batch), -1, -1, -1)
    elif t.shape[0] != int(batch):
        raise ValueError(f"Image batch {t.shape[0]} does not match reference batch {batch}")
    if t.shape[1] != int(h) or t.shape[2] != int(w):
        t = torch.nn.functional.interpolate(
            t.permute(0, 3, 1, 2),
            size=(int(h), int(w)),
            mode="bilinear",
            align_corners=False,
        ).permute(0, 2, 3, 1)
    return t.clamp(0.0, 1.0)


def infer_reference_shape(*inputs: Optional[torch.Tensor]) -> tuple[int, int, int]:
    for value in inputs:
        if value is None or not torch.is_tensor(value):
            continue
        if value.ndim in (2, 3, 4) and (value.ndim != 4 or value.shape[-1] in (1, 3, 4) or value.shape[1] in (1, 3, 4)):
            if value.ndim == 2:
                return (1, int(value.shape[0]), int(value.shape[1]))
            if value.ndim == 3:
                return (int(value.shape[0]), int(value.shape[1]), int(value.shape[2]))
            batch = int(value.shape[0])
            if value.shape[-1] in (1, 3, 4):
                return (batch, int(value.shape[1]), int(value.shape[2]))
            return (batch, int(value.shape[2]), int(value.shape[3]))
    raise ValueError("At least one image or mask input is required")


def image_to_gray_np(image: torch.Tensor, batch: int, h: int, w: int) -> np.ndarray:
    matched = match_image_batch(image, batch=batch, h=h, w=w)
    src = matched.detach().cpu().numpy().astype(np.float32, copy=False)
    if src.shape[-1] >= 3:
        return np.stack([luma_np(sample[..., :3]) for sample in src], axis=0).astype(np.float32, copy=False)
    return src[..., 0].astype(np.float32, copy=False)


def channel_to_grayscale_image(channel_np: np.ndarray, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    rgb = np.repeat(np.clip(channel_np, 0.0, 1.0)[..., None], 3, axis=-1).astype(np.float32, copy=False)
    return torch.from_numpy(rgb).to(device=device, dtype=dtype)


def decode_normal_np(rgb: np.ndarray) -> np.ndarray:
    normal = (np.clip(rgb[..., :3], 0.0, 1.0) * 2.0) - 1.0
    length = np.sqrt(np.sum(normal * normal, axis=-1, keepdims=True))
    return (normal / np.maximum(length, 1e-6)).astype(np.float32, copy=False)


def encode_normal_np(normal: np.ndarray) -> np.ndarray:
    length = np.sqrt(np.sum(normal * normal, axis=-1, keepdims=True))
    normalized = normal / np.maximum(length, 1e-6)
    return np.clip((normalized * 0.5) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)


def neutral_normal_rgb(shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    out = np.empty((int(h), int(w), 3), dtype=np.float32)
    out[..., 0] = 0.5
    out[..., 1] = 0.5
    out[..., 2] = 1.0
    return out


def blur_normal_rgb_np(rgb: np.ndarray, radius: float) -> np.ndarray:
    if float(max(0.0, radius)) <= 1e-6:
        return np.clip(rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    return gaussian_blur_rgb_np(np.clip(rgb[..., :3], 0.0, 1.0), radius=radius)


def apply_masked_mix(
    base: torch.Tensor,
    fx_np: np.ndarray,
    matte_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    batch = to_image_batch(base)
    b, h, w, c = batch.shape
    rgb = batch[..., :3]
    alpha = batch[..., 3:4] if c == 4 else None

    base_mask = mask_to_batch(
        mask=mask,
        batch=int(b),
        h=int(h),
        w=int(w),
        feather_radius=float(max(0.0, mask_feather)),
        invert_mask=bool(invert_mask),
        device=batch.device,
        dtype=batch.dtype,
    )
    matte_t = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    final_mask = torch.clamp(base_mask * matte_t, 0.0, 1.0).unsqueeze(-1)
    fx_t = torch.from_numpy(np.clip(fx_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)

    out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb
    out_mask = final_mask.squeeze(-1).clamp(0.0, 1.0)
    coverage = float(out_mask.mean().item()) * 100.0
    return out.clamp(0.0, 1.0), out_mask, coverage


def emit_masked_grayscale(
    base: torch.Tensor,
    scalar_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    batch = to_image_batch(base)
    b, h, w, c = batch.shape
    base_mask = mask_to_batch(
        mask=mask,
        batch=int(b),
        h=int(h),
        w=int(w),
        feather_radius=float(max(0.0, mask_feather)),
        invert_mask=bool(invert_mask),
        device=batch.device,
        dtype=batch.dtype,
    )
    final_mask = base_mask.unsqueeze(-1)
    fx_np = np.repeat(np.clip(scalar_np, 0.0, 1.0)[..., None], 3, axis=-1).astype(np.float32, copy=False)
    fx_t = torch.from_numpy(fx_np).to(device=batch.device, dtype=batch.dtype)
    out_rgb = torch.clamp(fx_t * final_mask, 0.0, 1.0)
    alpha = batch[..., 3:4] if c == 4 else None
    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb
    scalar_mask = torch.from_numpy(np.clip(scalar_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    out_mask = torch.clamp(scalar_mask * base_mask, 0.0, 1.0)
    coverage = float(base_mask.mean().item()) * 100.0
    return out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), coverage


def mask_or_gray_input(
    image: Optional[torch.Tensor],
    mask: Optional[torch.Tensor],
    batch: int,
    h: int,
    w: int,
    fill_value: float,
) -> tuple[np.ndarray, str]:
    if torch.is_tensor(mask):
        return mask_tensor_to_np(mask, batch=batch, h=h, w=w).astype(np.float32, copy=False), "mask"
    if torch.is_tensor(image):
        return image_to_gray_np(image, batch=batch, h=h, w=w).astype(np.float32, copy=False), "image_luma"
    out = np.full((int(batch), int(h), int(w)), float(np.clip(fill_value, 0.0, 1.0)), dtype=np.float32)
    return out, "fill"
