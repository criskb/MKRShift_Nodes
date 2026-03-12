from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from .image_shared import mask_to_batch, to_image_batch


def apply_masked_output(
    image: torch.Tensor,
    fx_np: np.ndarray,
    matte_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
):
    batch = to_image_batch(image)
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
    return out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), float(final_mask.mean().item()) * 100.0


def screen_blend_np(src: np.ndarray, fx: np.ndarray) -> np.ndarray:
    return (1.0 - (1.0 - np.clip(src, 0.0, 1.0)) * (1.0 - np.clip(fx, 0.0, 1.0))).astype(np.float32, copy=False)


def normalized_grid(h: int, w: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    ys = torch.linspace(-1.0, 1.0, int(h), device=device, dtype=dtype)
    xs = torch.linspace(-1.0, 1.0, int(w), device=device, dtype=dtype)
    yy, xx = torch.meshgrid(ys, xs, indexing="ij")
    return torch.stack((xx, yy), dim=-1)


def sample_rgb_grid(rgb: torch.Tensor, grid: torch.Tensor, padding_mode: str = "border") -> torch.Tensor:
    rgb_bchw = rgb.permute(0, 3, 1, 2)
    sampled = F.grid_sample(
        rgb_bchw,
        grid,
        mode="bilinear",
        padding_mode=padding_mode,
        align_corners=True,
    )
    return sampled.permute(0, 2, 3, 1)
