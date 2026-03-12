from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_MAPS
from ..lib.image_shared import mask_to_batch, rgb_to_hsv_np, to_image_batch
from ..lib.scalar_map_shared import blur_single_channel, mask_tensor_to_np, normalize_scalar, scalar_from_source


def _detail_scalar(rgb: np.ndarray, radius: float) -> np.ndarray:
    base = np.mean(rgb[..., :3], axis=-1).astype(np.float32, copy=False)
    blurred = blur_single_channel(base, radius)
    return np.abs(base - blurred).astype(np.float32, copy=False)


def _grayscale_output(
    batch: torch.Tensor,
    scalar_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    b, h, w, c = batch.shape
    fx_np = np.repeat(np.clip(scalar_np, 0.0, 1.0)[..., None], 3, axis=-1).astype(np.float32, copy=False)
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
    final_mask = effect_mask_t.unsqueeze(-1)
    fx_t = torch.from_numpy(fx_np).to(device=batch.device, dtype=batch.dtype)
    out_rgb = torch.clamp(fx_t * final_mask, 0.0, 1.0)
    alpha_t = batch[..., 3:4] if c == 4 else None
    out = torch.cat([out_rgb, alpha_t], dim=-1) if alpha_t is not None else out_rgb
    scalar_mask = torch.from_numpy(np.clip(scalar_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    out_mask = torch.clamp(scalar_mask * effect_mask_t, 0.0, 1.0)
    coverage = float(effect_mask_t.mean().item()) * 100.0
    return out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), coverage


def _resolve_material_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    saturation_suppress: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode == "detail":
        return _detail_scalar(src[..., :3], detail_radius), mode

    if mode in {"combined_roughness", "combined_specular", "combined_metalness"}:
        base_luma, _ = scalar_from_source(src, "luma", source_mask_np, True)
        detail = _detail_scalar(src[..., :3], detail_radius)
        _, sat, val = rgb_to_hsv_np(src[..., :3])

        if mode == "combined_roughness":
            scalar = (
                (base_luma * 0.55)
                + (detail * (0.45 + detail_strength))
                + (sat * 0.18)
            )
        elif mode == "combined_metalness":
            neutral_metal = val * (1.0 - np.clip(sat * 1.1, 0.0, 1.0))
            colored_metal = np.clip((sat - 0.25) / 0.75, 0.0, 1.0) * np.clip((val - 0.30) / 0.70, 0.0, 1.0)
            scalar = (
                (np.maximum(neutral_metal, colored_metal) * 0.72)
                + (detail * (0.18 + (detail_strength * 0.30)))
                + (np.maximum(base_luma - 0.35, 0.0) * 0.10)
            )
        else:
            scalar = (
                (val * 0.75)
                + (detail * (0.20 + (detail_strength * 0.55)))
                + ((1.0 - (sat * saturation_suppress)) * 0.25)
            )
        if abs(float(contrast) - 1.0) > 1e-6:
            scalar = np.clip(((scalar - 0.5) * float(contrast)) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
        return np.clip(scalar, 0.0, 1.0).astype(np.float32, copy=False), mode

    return scalar_from_source(src, mode, source_mask_np, True)


class x1RoughnessMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_roughness", "luma", "value", "saturation", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.1, "min": 0.1, "max": 4.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "roughness_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_roughness",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.45,
        gamma: float = 1.0,
        contrast: float = 1.1,
        blur_radius: float = 0.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = _resolve_material_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
                saturation_suppress=0.0,
                contrast=contrast,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=raw,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            scalar_np[idx] = blur_single_channel(normalized, blur_radius)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1RoughnessMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
            "detail_strength={:.2f}, gamma={:.2f}, contrast={:.2f}, blur_radius={:.1f}px, "
            "invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(detail_strength),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1SpecularMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_specular", "value", "luma", "saturation", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 2.0, "step": 0.01}),
                "saturation_suppress": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 0.75, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.25, "min": 0.1, "max": 4.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "specular_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_specular",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.35,
        saturation_suppress: float = 0.75,
        gamma: float = 0.75,
        contrast: float = 1.25,
        blur_radius: float = 0.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = _resolve_material_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
                saturation_suppress=saturation_suppress,
                contrast=contrast,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=raw,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            scalar_np[idx] = blur_single_channel(normalized, blur_radius)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1SpecularMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
            "detail_strength={:.2f}, saturation_suppress={:.2f}, gamma={:.2f}, contrast={:.2f}, "
            "blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(detail_strength),
            float(np.clip(saturation_suppress, 0.0, 1.0)),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1MetalnessMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_metalness", "value", "luma", "saturation", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.15, "min": 0.1, "max": 4.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "metalness_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_metalness",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.25,
        gamma: float = 1.0,
        contrast: float = 1.15,
        blur_radius: float = 0.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = _resolve_material_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
                saturation_suppress=0.0,
                contrast=contrast,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=raw,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            scalar_np[idx] = blur_single_channel(normalized, blur_radius)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1MetalnessMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
            "detail_strength={:.2f}, gamma={:.2f}, contrast={:.2f}, blur_radius={:.1f}px, "
            "invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(detail_strength),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1NormalMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["luma", "red", "green", "blue", "max_rgb", "saturation", "value", "alpha", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 128.0, "step": 0.1}),
                "strength": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "convention": (["opengl", "directx"],),
                "invert_height": ("BOOLEAN", {"default": False}),
                "invert_x": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "normal_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "luma",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        gamma: float = 1.0,
        blur_radius: float = 0.0,
        strength: float = 4.0,
        convention: str = "opengl",
        invert_height: bool = False,
        invert_x: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        normal_np = np.zeros((int(b), int(h), int(w), 3), dtype=np.float32)
        height_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        strength_value = float(max(0.0, strength))
        for idx in range(int(b)):
            raw, resolved_source = scalar_from_source(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                fallback_to_luma=True,
            )
            normalized, lo, hi = normalize_scalar(
                scalar=raw,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_height,
            )
            height = blur_single_channel(normalized, blur_radius)
            height_np[idx] = height

            grad_y, grad_x = np.gradient(height)
            nx = -grad_x * strength_value
            ny = (-grad_y if str(convention).lower() == "opengl" else grad_y) * strength_value
            if bool(invert_x):
                nx = -nx
            nz = np.ones_like(height, dtype=np.float32)
            length = np.sqrt((nx * nx) + (ny * ny) + (nz * nz))
            normal = np.stack(
                [
                    (nx / np.maximum(length, 1e-6) * 0.5) + 0.5,
                    (ny / np.maximum(length, 1e-6) * 0.5) + 0.5,
                    (nz / np.maximum(length, 1e-6) * 0.5) + 0.5,
                ],
                axis=-1,
            )
            normal_np[idx] = np.clip(normal, 0.0, 1.0).astype(np.float32, copy=False)
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
        final_mask = effect_mask_t.unsqueeze(-1)
        fx_t = torch.from_numpy(np.clip(normal_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        flat_normal = torch.empty_like(fx_t)
        flat_normal[..., 0] = 0.5
        flat_normal[..., 1] = 0.5
        flat_normal[..., 2] = 1.0
        alpha_t = batch[..., 3:4] if c == 4 else None
        out_rgb = torch.clamp((flat_normal * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha_t], dim=-1) if alpha_t is not None else out_rgb
        scalar_mask = torch.from_numpy(np.clip(height_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_mask = torch.clamp(scalar_mask * effect_mask_t, 0.0, 1.0)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        info = (
            "x1NormalMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], gamma={:.2f}, blur_radius={:.1f}px, "
            "strength={:.2f}, convention={}, invert_height={}, invert_x={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(max(0.1, gamma)),
            float(max(0.0, blur_radius)),
            strength_value,
            str(convention).lower(),
            bool(invert_height),
            bool(invert_x),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)
