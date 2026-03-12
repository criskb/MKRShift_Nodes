from typing import Optional

import numpy as np
import torch

from ..categories import COLOR_ANALYZE, SURFACE_MAPS
from ..lib.image_shared import mask_to_batch, to_image_batch
from ..lib.scalar_map_shared import apply_palette, blur_single_channel, mask_tensor_to_np, normalize_scalar, scalar_from_source


class x1Heatmap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["luma", "red", "green", "blue", "max_rgb", "saturation", "value", "alpha", "mask"],),
                "palette": (["inferno", "viridis", "plasma", "magma", "turbo", "thermal", "icefire"],),
                "normalize_mode": (["manual_range", "auto_range", "auto_percentile"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "invert_values": ("BOOLEAN", {"default": False}),
                "overlay_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "source_mask": ("MASK",),
                "effect_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "heatmap_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "luma",
        palette: str = "inferno",
        normalize_mode: str = "manual_range",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        gamma: float = 1.0,
        invert_values: bool = False,
        overlay_opacity: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        effect_mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        op = float(np.clip(overlay_opacity, 0.0, 1.0))

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0

        for idx in range(int(b)):
            src = src_np[idx]
            rgb = src[..., :3]
            scalar, resolved_source = scalar_from_source(
                src=src,
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                fallback_to_luma=True,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=scalar,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            heat = apply_palette(normalized, palette=palette)
            out_np[idx] = np.clip((rgb * (1.0 - op)) + (heat * op), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = normalized
            last_lo = lo
            last_hi = hi

        effect_mask_t = mask_to_batch(
            mask=effect_mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        final_mask = effect_mask_t.unsqueeze(-1)
        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        rgb_t = batch[..., :3]
        alpha_t = batch[..., 3:4] if c == 4 else None
        out_rgb = torch.clamp((rgb_t * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha_t], dim=-1) if alpha_t is not None else out_rgb
        scalar_mask = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_mask = torch.clamp(scalar_mask * effect_mask_t, 0.0, 1.0)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        info = (
            "x1Heatmap: source={}, palette={}, normalize_mode={}, range=[{:.3f},{:.3f}], gamma={:.2f}, "
            "invert_values={}, opacity={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(palette).lower(),
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(max(0.1, gamma)),
            bool(invert_values),
            op,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)


class x1Heightmap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["luma", "red", "green", "blue", "max_rgb", "saturation", "value", "alpha", "mask"],),
                "normalize_mode": (["manual_range", "auto_range", "auto_percentile"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 128.0, "step": 0.1}),
                "invert_values": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "heightmap_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "luma",
        normalize_mode: str = "manual_range",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        gamma: float = 1.0,
        contrast: float = 1.0,
        blur_radius: float = 0.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        contrast_value = float(max(0.1, contrast))
        blur_value = float(max(0.0, blur_radius))

        for idx in range(int(b)):
            src = src_np[idx]
            scalar, resolved_source = scalar_from_source(
                src=src,
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                fallback_to_luma=True,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=scalar,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            if abs(contrast_value - 1.0) > 1e-6:
                normalized = np.clip(((normalized - 0.5) * contrast_value) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
            normalized = blur_single_channel(normalized, blur_value)

            out_np[idx] = np.repeat(normalized[..., None], 3, axis=-1).astype(np.float32, copy=False)
            matte_np[idx] = normalized
            last_lo = lo
            last_hi = hi

        effect_mask_t = mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        final_mask = effect_mask_t.unsqueeze(-1)
        out_rgb = torch.clamp(fx_t * final_mask, 0.0, 1.0)
        alpha_t = batch[..., 3:4] if c == 4 else None
        out = torch.cat([out_rgb, alpha_t], dim=-1) if alpha_t is not None else out_rgb
        scalar_mask = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_mask = torch.clamp(scalar_mask * effect_mask_t, 0.0, 1.0)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        info = (
            "x1Heightmap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], gamma={:.2f}, contrast={:.2f}, "
            "blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(max(0.1, gamma)),
            contrast_value,
            blur_value,
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)
