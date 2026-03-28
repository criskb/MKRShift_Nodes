import json
from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_MAPS
from ..lib.image_shared import luma_np, mask_to_batch, rgb_to_hsv_np, smoothstep_np, to_image_batch
from ..lib.material_response_shared import (
    apply_contrast as _response_apply_contrast,
    detail_scalar as _response_detail_scalar,
    resolve_clearcoat_roughness_scalar,
    resolve_clearcoat_scalar,
    resolve_anisotropy_scalar,
    resolve_edge_wear_scalar,
    resolve_iridescence_scalar,
    resolve_sheen_scalar,
    resolve_surface_scalar,
    resolve_thickness_scalar,
    resolve_transmission_scalar,
    soft_gate as _response_soft_gate,
)
from ..lib.settings_bundle import parse_settings_payload
from ..lib.scalar_map_shared import blur_single_channel, mask_tensor_to_np, normalize_scalar, scalar_from_source


def _detail_scalar(rgb: np.ndarray, radius: float) -> np.ndarray:
    return _response_detail_scalar(rgb, radius)


def _masked_output(
    batch: torch.Tensor,
    effect_rgb_np: np.ndarray,
    scalar_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    b, h, w, c = batch.shape
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
    fx_t = torch.from_numpy(np.clip(effect_rgb_np, 0.0, 1.0).astype(np.float32, copy=False)).to(
        device=batch.device,
        dtype=batch.dtype,
    )
    out_rgb = torch.clamp(fx_t * final_mask, 0.0, 1.0)
    alpha_t = batch[..., 3:4] if c == 4 else None
    out = torch.cat([out_rgb, alpha_t], dim=-1) if alpha_t is not None else out_rgb
    scalar_mask = torch.from_numpy(np.clip(scalar_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    out_mask = torch.clamp(scalar_mask * effect_mask_t, 0.0, 1.0)
    coverage = float(effect_mask_t.mean().item()) * 100.0
    return out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), coverage


def _grayscale_output(
    batch: torch.Tensor,
    scalar_np: np.ndarray,
    mask: Optional[torch.Tensor],
    mask_feather: float,
    invert_mask: bool,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    fx_np = np.repeat(np.clip(scalar_np, 0.0, 1.0)[..., None], 3, axis=-1).astype(np.float32, copy=False)
    return _masked_output(batch, fx_np, scalar_np, mask, mask_feather, invert_mask)


def _soft_gate(values: np.ndarray, threshold: float, softness: float) -> np.ndarray:
    return _response_soft_gate(values, threshold, softness)


def _apply_contrast(values: np.ndarray, contrast: float) -> np.ndarray:
    return _response_apply_contrast(values, contrast)


_COLOR_REGION_PRESETS: dict[str, float] = {
    "red": 0.000,
    "orange": 0.083,
    "yellow": 0.167,
    "green": 0.333,
    "cyan": 0.500,
    "blue": 0.667,
    "magenta": 0.833,
}


def _resolve_sheen_color_rgb(src: np.ndarray, scalar: np.ndarray, tint_mode: str, tint_strength: float) -> np.ndarray:
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    luma = luma_np(rgb)[..., None]
    resolved_tint = str(tint_mode or "desaturated_source").strip().lower()
    if resolved_tint == "source_color":
        tint = rgb
    elif resolved_tint == "white":
        tint = np.ones_like(rgb, dtype=np.float32)
    elif resolved_tint == "warm_white":
        tint = np.broadcast_to(np.asarray([1.0, 0.93, 0.86], dtype=np.float32), rgb.shape).astype(np.float32, copy=False)
    elif resolved_tint == "cool_white":
        tint = np.broadcast_to(np.asarray([0.86, 0.93, 1.0], dtype=np.float32), rgb.shape).astype(np.float32, copy=False)
    else:
        tint = np.clip((luma * 0.58) + (rgb * 0.42), 0.0, 1.0).astype(np.float32, copy=False)

    strength = float(np.clip(tint_strength, 0.0, 1.0))
    tinted = np.clip((luma * (1.0 - strength)) + (tint * strength), 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip(tinted * np.clip(scalar, 0.0, 1.0)[..., None], 0.0, 1.0).astype(np.float32, copy=False)


def _normalize_direction_field(dir_x: np.ndarray, dir_y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = np.sqrt((dir_x * dir_x) + (dir_y * dir_y)).astype(np.float32, copy=False)
    safe = np.maximum(length, 1e-6)
    norm_x = (dir_x / safe).astype(np.float32, copy=False)
    norm_y = (dir_y / safe).astype(np.float32, copy=False)
    weak = length <= 1e-5
    if np.any(weak):
        norm_x = norm_x.astype(np.float32, copy=True)
        norm_y = norm_y.astype(np.float32, copy=True)
        norm_x[weak] = 1.0
        norm_y[weak] = 0.0
    return norm_x, norm_y


def _resolve_anisotropy_direction(
    src: np.ndarray,
    direction_mode: str,
    direction_angle_deg: float,
    center_x: float,
    center_y: float,
    gradient_radius: float,
) -> tuple[np.ndarray, np.ndarray, str]:
    h, w = src.shape[:2]
    resolved_mode = str(direction_mode or "horizontal").strip().lower()

    if resolved_mode in {"horizontal", "vertical", "angle"}:
        if resolved_mode == "horizontal":
            angle_rad = 0.0
        elif resolved_mode == "vertical":
            angle_rad = np.pi * 0.5
        else:
            angle_rad = np.deg2rad(float(direction_angle_deg))
        dir_x = np.full((h, w), np.cos(angle_rad), dtype=np.float32)
        dir_y = np.full((h, w), np.sin(angle_rad), dtype=np.float32)
        return _normalize_direction_field(dir_x, dir_y) + (resolved_mode,)

    x = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    center_x_val = float(np.clip(center_x, 0.0, 1.0))
    center_y_val = float(np.clip(center_y, 0.0, 1.0))
    off_x = (xx - center_x_val).astype(np.float32, copy=False)
    off_y = (yy - center_y_val).astype(np.float32, copy=False)

    if resolved_mode in {"radial", "tangential"}:
        if resolved_mode == "radial":
            return _normalize_direction_field(off_x, off_y) + (resolved_mode,)
        return _normalize_direction_field(-off_y, off_x) + (resolved_mode,)

    luma = luma_np(np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False))
    if float(max(0.0, gradient_radius)) > 1e-6:
        luma = blur_single_channel(luma, gradient_radius)
    grad_y, grad_x = np.gradient(luma.astype(np.float32, copy=False))
    grad_x = grad_x.astype(np.float32, copy=False)
    grad_y = grad_y.astype(np.float32, copy=False)

    if resolved_mode == "gradient_normal":
        return _normalize_direction_field(grad_x, grad_y) + (resolved_mode,)
    return _normalize_direction_field(-grad_y, grad_x) + ("gradient_tangent",)


def _encode_anisotropy_texture(dir_x: np.ndarray, dir_y: np.ndarray, strength: np.ndarray) -> np.ndarray:
    encoded_r = np.clip((dir_x * 0.5) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
    encoded_g = np.clip((dir_y * 0.5) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
    encoded_b = np.clip(strength, 0.0, 1.0).astype(np.float32, copy=False)
    return np.stack([encoded_r, encoded_g, encoded_b], axis=-1).astype(np.float32, copy=False)


def _resolve_color_region_scalar(
    src: np.ndarray,
    color_preset: str,
    hue_center: float,
    hue_width: float,
    saturation_min: float,
    value_min: float,
    softness: float,
    contrast: float,
    source_mask_np: Optional[np.ndarray],
) -> tuple[np.ndarray, str]:
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, s, v = rgb_to_hsv_np(rgb)

    preset = str(color_preset or "red").strip().lower()
    target_hue = _COLOR_REGION_PRESETS.get(preset, float(hue_center) % 1.0)
    width = float(np.clip(hue_width, 1e-3, 0.5))
    soft = float(max(1e-4, softness))

    hue_distance = np.minimum(np.abs(h - target_hue), 1.0 - np.abs(h - target_hue)).astype(np.float32, copy=False)
    hue_gate = (1.0 - smoothstep_np(max(0.0, width - soft), min(0.5, width + soft), hue_distance)).astype(
        np.float32,
        copy=False,
    )
    sat_gate = _soft_gate(s, threshold=saturation_min, softness=soft)
    val_gate = _soft_gate(v, threshold=value_min, softness=soft)
    scalar = np.clip(hue_gate * sat_gate * ((val_gate * 0.55) + 0.45), 0.0, 1.0).astype(np.float32, copy=False)
    if source_mask_np is not None:
        scalar = np.clip(scalar * np.clip(source_mask_np, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)
    return _apply_contrast(scalar, contrast), (preset if preset in _COLOR_REGION_PRESETS else f"custom({target_hue:.3f})")


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

    if mode in {"combined_roughness", "combined_specular", "combined_metalness", "combined_opacity"}:
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
        elif mode == "combined_opacity":
            if src.shape[-1] >= 4:
                scalar = src[..., 3].astype(np.float32, copy=False)
                resolved_mode = "combined_opacity(alpha)"
            elif source_mask_np is not None:
                scalar = source_mask_np.astype(np.float32, copy=False)
                resolved_mode = "combined_opacity(mask)"
            else:
                scalar = np.ones(src.shape[:2], dtype=np.float32)
                resolved_mode = "combined_opacity(opaque)"
            if abs(float(contrast) - 1.0) > 1e-6:
                scalar = np.clip(((scalar - 0.5) * float(contrast)) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
            return np.clip(scalar, 0.0, 1.0).astype(np.float32, copy=False), resolved_mode
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


def _resolve_emissive_source(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    threshold: float,
    softness: float,
    saturation_gate: float,
) -> tuple[np.ndarray, np.ndarray, str]:
    mode = str(source_mode).lower()
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    _, sat, val = rgb_to_hsv_np(rgb)
    bright_gate = _soft_gate(val, threshold=threshold, softness=softness)
    sat_gate = _soft_gate(sat, threshold=saturation_gate, softness=max(0.02, softness))

    if mode == "bright_color":
        return rgb, bright_gate.astype(np.float32, copy=False), mode
    if mode == "saturated_color":
        return rgb, (bright_gate * sat_gate).astype(np.float32, copy=False), mode
    if mode == "white_hotspots":
        return np.ones_like(rgb, dtype=np.float32), bright_gate.astype(np.float32, copy=False), mode
    if mode == "mask_color":
        if source_mask_np is not None:
            return rgb, np.clip(source_mask_np, 0.0, 1.0).astype(np.float32, copy=False), mode
        return rgb, bright_gate.astype(np.float32, copy=False), "mask_color(fallback)"

    strength = np.clip((bright_gate * 0.65) + ((bright_gate * sat_gate) * 0.35), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    return rgb, strength, "combined_emissive"


class x1RoughnessMap:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_roughness",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "detail_radius": 2.0,
            "detail_strength": 0.45,
            "gamma": 1.0,
            "contrast": 1.1,
            "blur_radius": 0.0,
            "invert_values": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
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
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "detail_radius": {"min": 0.1, "max": 64.0},
                "detail_strength": {"min": 0.0, "max": 2.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        detail_radius = float(settings["detail_radius"])
        detail_strength = float(settings["detail_strength"])
        gamma = float(settings["gamma"])
        contrast = float(settings["contrast"])
        blur_radius = float(settings["blur_radius"])
        invert_values = bool(settings["invert_values"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_specular",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "detail_radius": 2.0,
            "detail_strength": 0.35,
            "saturation_suppress": 0.75,
            "gamma": 0.75,
            "contrast": 1.25,
            "blur_radius": 0.0,
            "invert_values": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
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
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "detail_radius": {"min": 0.1, "max": 64.0},
                "detail_strength": {"min": 0.0, "max": 2.0},
                "saturation_suppress": {"min": 0.0, "max": 1.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        detail_radius = float(settings["detail_radius"])
        detail_strength = float(settings["detail_strength"])
        saturation_suppress = float(settings["saturation_suppress"])
        gamma = float(settings["gamma"])
        contrast = float(settings["contrast"])
        blur_radius = float(settings["blur_radius"])
        invert_values = bool(settings["invert_values"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_metalness",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "detail_radius": 2.0,
            "detail_strength": 0.25,
            "gamma": 1.0,
            "contrast": 1.15,
            "blur_radius": 0.0,
            "invert_values": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
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
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "detail_radius": {"min": 0.1, "max": 64.0},
                "detail_strength": {"min": 0.0, "max": 2.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        detail_radius = float(settings["detail_radius"])
        detail_strength = float(settings["detail_strength"])
        gamma = float(settings["gamma"])
        contrast = float(settings["contrast"])
        blur_radius = float(settings["blur_radius"])
        invert_values = bool(settings["invert_values"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

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


class x1OpacityMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (
                    ["combined_opacity", "alpha", "red", "green", "blue", "luma", "max_rgb", "value", "detail", "mask"],
                ),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "opacity_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_opacity",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 1.5,
        detail_strength: float = 0.0,
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
            "x1OpacityMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1ClearcoatMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_clearcoat", "value", "luma", "saturation", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.20, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "clearcoat_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_clearcoat",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.20,
        gamma: float = 1.0,
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
            raw, resolved_source = resolve_clearcoat_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1ClearcoatMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1ClearcoatRoughnessMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (
                    ["combined_clearcoat_roughness", "detail", "inverse_luma", "luma", "value", "saturation", "mask"],
                ),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 2.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "clearcoat_roughness_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_clearcoat_roughness",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.35,
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
            raw, resolved_source = resolve_clearcoat_roughness_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1ClearcoatRoughnessMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1SheenMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_sheen", "saturation", "value", "luma", "detail", "mask"],),
                "tint_mode": (["desaturated_source", "source_color", "white", "warm_white", "cool_white"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.20, "min": 0.0, "max": 2.0, "step": 0.01}),
                "tint_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "sheen_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_sheen",
        tint_mode: str = "desaturated_source",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.20,
        tint_strength: float = 0.85,
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
        effect_rgb_np = np.zeros((int(b), int(h), int(w), 3), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = resolve_sheen_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            normalized = blur_single_channel(normalized, blur_radius)
            scalar_np[idx] = normalized
            effect_rgb_np[idx] = _resolve_sheen_color_rgb(
                src=src_np[idx],
                scalar=normalized,
                tint_mode=tint_mode,
                tint_strength=tint_strength,
            )
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _masked_output(batch, effect_rgb_np, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1SheenMap: source={}, tint_mode={}, normalize_mode={}, range=[{:.3f},{:.3f}], "
            "detail_radius={:.1f}px, detail_strength={:.2f}, tint_strength={:.2f}, gamma={:.2f}, "
            "contrast={:.2f}, blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(tint_mode).lower(),
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(detail_strength),
            float(np.clip(tint_strength, 0.0, 1.0)),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1IridescenceMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_iridescence", "saturation", "value", "luma", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 2.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "iridescence_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_iridescence",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.10,
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
            raw, resolved_source = resolve_iridescence_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1IridescenceMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1AnisotropyMap:
    SEARCH_ALIASES = ["anisotropy", "brushed metal", "flow map", "fiber direction", "anisotropic"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_anisotropy", "value", "luma", "saturation", "detail", "mask"],),
                "direction_mode": (
                    ["horizontal", "vertical", "angle", "gradient_tangent", "gradient_normal", "radial", "tangential"],
                ),
                "direction_angle_deg": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.5}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "gradient_radius": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 2.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "anisotropy_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_anisotropy",
        direction_mode: str = "horizontal",
        direction_angle_deg: float = 0.0,
        center_x: float = 0.5,
        center_y: float = 0.5,
        gradient_radius: float = 2.0,
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.15,
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
        effect_rgb_np = np.zeros((int(b), int(h), int(w), 3), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        resolved_direction = str(direction_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = resolve_anisotropy_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            normalized = blur_single_channel(normalized, blur_radius)
            dir_x, dir_y, resolved_direction = _resolve_anisotropy_direction(
                src=src_np[idx],
                direction_mode=direction_mode,
                direction_angle_deg=direction_angle_deg,
                center_x=center_x,
                center_y=center_y,
                gradient_radius=gradient_radius,
            )
            scalar_np[idx] = normalized
            effect_rgb_np[idx] = _encode_anisotropy_texture(dir_x, dir_y, normalized)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _masked_output(batch, effect_rgb_np, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1AnisotropyMap: source={}, direction_mode={}, normalize_mode={}, range=[{:.3f},{:.3f}], "
            "detail_radius={:.1f}px, detail_strength={:.2f}, gradient_radius={:.1f}px, gamma={:.2f}, "
            "contrast={:.2f}, blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            resolved_direction,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(detail_strength),
            float(max(0.0, gradient_radius)),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1TransmissionMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_transmission", "alpha", "value", "luma", "saturation", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 2.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "transmission_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_transmission",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.15,
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
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = resolve_transmission_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1TransmissionMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1ThicknessMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["combined_thickness", "inverse_luma", "luma", "value", "alpha", "detail", "mask"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
                "detail_strength": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.10, "min": 0.1, "max": 4.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "thickness_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "combined_thickness",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        detail_radius: float = 2.0,
        detail_strength: float = 0.15,
        gamma: float = 1.0,
        contrast: float = 1.10,
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
            raw, resolved_source = resolve_thickness_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1ThicknessMap: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
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


class x1ScalarMapAdjust:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (
                    ["luma", "inverse_luma", "red", "green", "blue", "alpha", "max_rgb", "value", "saturation", "detail", "mask"],
                ),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "detail_radius": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 64.0, "step": 0.1}),
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
    RETURN_NAMES = ("image", "mask", "scalar_map_info")
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
        detail_radius: float = 2.0,
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
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = resolve_surface_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                detail_radius=detail_radius,
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
            scalar_np[idx] = blur_single_channel(_apply_contrast(normalized, contrast), blur_radius)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1ScalarMapAdjust: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], detail_radius={:.1f}px, "
            "gamma={:.2f}, contrast={:.2f}, blur_radius={:.1f}px, invert_values={}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(detail_radius),
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1ColorRegionMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "color_preset": (["red", "orange", "yellow", "green", "cyan", "blue", "magenta", "custom"],),
                "hue_center": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "hue_width": ("FLOAT", {"default": 0.08, "min": 0.001, "max": 0.5, "step": 0.001}),
                "saturation_min": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 1.0, "step": 0.01}),
                "value_min": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.5, "step": 0.001}),
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
    RETURN_NAMES = ("image", "mask", "region_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        color_preset: str = "red",
        hue_center: float = 0.0,
        hue_width: float = 0.08,
        saturation_min: float = 0.18,
        value_min: float = 0.04,
        softness: float = 0.05,
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

        resolved_preset = str(color_preset).lower()
        for idx in range(int(b)):
            scalar, resolved_preset = _resolve_color_region_scalar(
                src=src_np[idx],
                color_preset=color_preset,
                hue_center=hue_center,
                hue_width=hue_width,
                saturation_min=saturation_min,
                value_min=value_min,
                softness=softness,
                contrast=contrast,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
            )
            if invert_values:
                scalar = (1.0 - scalar).astype(np.float32, copy=False)
            scalar_np[idx] = blur_single_channel(np.clip(scalar, 0.0, 1.0), blur_radius)

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1ColorRegionMask: color={}, hue_width={:.3f}, saturation_min={:.2f}, value_min={:.2f}, "
            "softness={:.3f}, contrast={:.2f}, blur_radius={:.1f}px, invert_values={}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_preset,
            float(np.clip(hue_width, 1e-3, 0.5)),
            float(np.clip(saturation_min, 0.0, 1.0)),
            float(np.clip(value_min, 0.0, 1.0)),
            float(max(0.0, softness)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1EmissiveMap:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_emissive",
            "threshold": 0.6,
            "softness": 0.1,
            "saturation_gate": 0.35,
            "intensity": 1.5,
            "blur_radius": 0.0,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "emissive_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "threshold": {"min": 0.0, "max": 1.0},
                "softness": {"min": 0.0, "max": 0.5},
                "saturation_gate": {"min": 0.0, "max": 1.0},
                "intensity": {"min": 0.0, "max": 8.0},
                "blur_radius": {"min": 0.0, "max": 64.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        threshold = float(settings["threshold"])
        softness = float(settings["softness"])
        saturation_gate = float(settings["saturation_gate"])
        intensity = float(settings["intensity"])
        blur_radius = float(settings["blur_radius"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        emissive_np = np.zeros((int(b), int(h), int(w), 3), dtype=np.float32)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        for idx in range(int(b)):
            color_rgb, strength, resolved_source = _resolve_emissive_source(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                threshold=threshold,
                softness=softness,
                saturation_gate=saturation_gate,
            )
            strength = blur_single_channel(strength, blur_radius)
            scalar_np[idx] = strength
            emissive_np[idx] = np.clip(color_rgb * strength[..., None] * float(max(0.0, intensity)), 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )

        out, out_mask, coverage = _masked_output(batch, emissive_np, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1EmissiveMap: source={}, threshold={:.2f}, softness={:.2f}, saturation_gate={:.2f}, intensity={:.2f}, "
            "blur_radius={:.1f}px, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            float(np.clip(threshold, 0.0, 1.0)),
            float(max(0.0, softness)),
            float(np.clip(saturation_gate, 0.0, 1.0)),
            float(max(0.0, intensity)),
            float(max(0.0, blur_radius)),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1CavityMap:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "luma",
            "polarity": "concave",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "radius": 2.5,
            "gamma": 1.0,
            "contrast": 1.35,
            "blur_radius": 0.0,
            "invert_values": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "cavity_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "radius": {"min": 0.1, "max": 64.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        polarity = str(settings["polarity"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        radius = float(settings["radius"])
        gamma = float(settings["gamma"])
        contrast = float(settings["contrast"])
        blur_radius = float(settings["blur_radius"])
        invert_values = bool(settings["invert_values"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        resolved_polarity = str(polarity).lower()
        last_lo = 0.0
        last_hi = 1.0
        cavity_radius = float(max(0.1, radius))

        for idx in range(int(b)):
            raw, resolved_source = scalar_from_source(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                fallback_to_luma=True,
            )
            local_mean = blur_single_channel(raw, cavity_radius)
            if resolved_polarity == "convex":
                cavity_raw = np.maximum(raw - local_mean, 0.0).astype(np.float32, copy=False)
            elif resolved_polarity == "both":
                cavity_raw = np.abs(raw - local_mean).astype(np.float32, copy=False)
            else:
                cavity_raw = np.maximum(local_mean - raw, 0.0).astype(np.float32, copy=False)

            normalized, lo, hi = normalize_scalar(
                scalar=cavity_raw,
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=invert_values,
            )
            scalar_np[idx] = blur_single_channel(_apply_contrast(normalized, contrast), blur_radius)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = _grayscale_output(batch, scalar_np, mask, mask_feather, invert_mask)
        info = (
            "x1CavityMap: source={}, polarity={}, normalize_mode={}, range=[{:.3f},{:.3f}], radius={:.1f}px, "
            "gamma={:.2f}, contrast={:.2f}, blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            resolved_polarity,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            cavity_radius,
            float(max(0.1, gamma)),
            float(max(0.1, contrast)),
            float(max(0.0, blur_radius)),
            bool(invert_values),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1EdgeWearMask:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_edge_wear",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "edge_radius": 5.0,
            "detail_radius": 2.0,
            "detail_strength": 0.50,
            "gamma": 1.0,
            "contrast": 1.25,
            "blur_radius": 0.0,
            "invert_values": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "wear_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "edge_radius": {"min": 0.1, "max": 128.0},
                "detail_radius": {"min": 0.1, "max": 64.0},
                "detail_strength": {"min": 0.0, "max": 2.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        edge_radius = float(settings["edge_radius"])
        detail_radius = float(settings["detail_radius"])
        detail_strength = float(settings["detail_strength"])
        gamma = float(settings["gamma"])
        contrast = float(settings["contrast"])
        blur_radius = float(settings["blur_radius"])
        invert_values = bool(settings["invert_values"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None

        resolved_source = str(source_mode).lower()
        last_lo = 0.0
        last_hi = 1.0
        for idx in range(int(b)):
            raw, resolved_source = resolve_edge_wear_scalar(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                edge_radius=edge_radius,
                detail_radius=detail_radius,
                detail_strength=detail_strength,
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
            "x1EdgeWearMask: source={}, normalize_mode={}, range=[{:.3f},{:.3f}], edge_radius={:.1f}px, "
            "detail_radius={:.1f}px, detail_strength={:.2f}, gamma={:.2f}, contrast={:.2f}, "
            "blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(edge_radius),
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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "luma",
            "normalize_mode": "auto_percentile",
            "value_min": 0.0,
            "value_max": 1.0,
            "percentile_low": 2.0,
            "percentile_high": 98.0,
            "gamma": 1.0,
            "blur_radius": 0.0,
            "strength": 4.0,
            "convention": "opengl",
            "invert_height": False,
            "invert_x": False,
            "mask_feather": 8.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
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
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "value_min": {"min": 0.0, "max": 1.0},
                "value_max": {"min": 0.0, "max": 1.0},
                "percentile_low": {"min": 0.0, "max": 100.0},
                "percentile_high": {"min": 0.0, "max": 100.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "strength": {"min": 0.0, "max": 64.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_height", "invert_x", "invert_mask"},
            legacy=legacy_settings,
        )
        source_mode = str(settings["source_mode"])
        normalize_mode = str(settings["normalize_mode"])
        value_min = float(settings["value_min"])
        value_max = float(settings["value_max"])
        percentile_low = float(settings["percentile_low"])
        percentile_high = float(settings["percentile_high"])
        gamma = float(settings["gamma"])
        blur_radius = float(settings["blur_radius"])
        strength = float(settings["strength"])
        convention = str(settings["convention"])
        invert_height = bool(settings["invert_height"])
        invert_x = bool(settings["invert_x"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])

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
