import json
from typing import Optional

import numpy as np
from PIL import Image
import torch

from ..categories import SURFACE_TEXTURE
from ..lib.image_shared import gaussian_blur_rgb_np, hsv_to_rgb_np, luma_np, mask_to_batch, rgb_to_hsv_np, smoothstep_np, to_image_batch
from ..lib.procedural_texture_shared import (
    grayscale_to_rgb,
    procedural_cell_pattern,
    procedural_hex_pattern,
    procedural_noise_field,
    procedural_strata_pattern,
    procedural_weave_pattern,
    shape_scalar_field,
)
from ..lib.settings_bundle import parse_settings_payload
from ..lib.scalar_map_shared import blur_single_channel, mask_tensor_to_np
from ..lib.texture_shared import cross_seam_mask, edge_match_low_frequency, roll_image_np, smooth_seams, tile_grid_mask


def _to_tensor(image_np: np.ndarray, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    return torch.from_numpy(np.clip(image_np, 0.0, 1.0).astype(np.float32, copy=False)).to(device=device, dtype=dtype)


def _field_output(field: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
    clipped = np.clip(field, 0.0, 1.0).astype(np.float32, copy=False)
    return (
        torch.from_numpy(grayscale_to_rgb(clipped)[None, ...]),
        torch.from_numpy(clipped[None, ...]),
    )


def _resolve_offset_pixels(h: int, w: int, mode: str, offset_x: float, offset_y: float) -> tuple[int, int]:
    resolved = str(mode).lower()
    if resolved == "half_tile":
        return int(h // 2), int(w // 2)
    if resolved == "pixels":
        return int(round(offset_y)), int(round(offset_x))
    return int(round(float(offset_y) * float(h))), int(round(float(offset_x) * float(w)))


def _offset_seam_mask(h: int, w: int, shift_y: int, shift_x: int, seam_width: float, seam_softness: float) -> np.ndarray:
    seam_x = None if int(shift_x) % max(1, int(w)) == 0 else float(int(shift_x) % int(w))
    seam_y = None if int(shift_y) % max(1, int(h)) == 0 else float(int(shift_y) % int(h))
    return cross_seam_mask(
        h=int(h),
        w=int(w),
        seam_x=seam_x,
        seam_y=seam_y,
        half_width=float(max(0.0, seam_width)),
        softness=float(max(0.0, seam_softness)),
    )


def _tile_image_np(image: np.ndarray, tiles_y: int, tiles_x: int) -> np.ndarray:
    reps = (int(max(1, tiles_y)), int(max(1, tiles_x)), 1) if image.ndim == 3 else (int(max(1, tiles_y)), int(max(1, tiles_x)))
    return np.tile(image, reps).astype(np.float32, copy=False)


def _overlay_seams(rgb: np.ndarray, seam_mask: np.ndarray, opacity: float) -> np.ndarray:
    op = float(np.clip(opacity, 0.0, 1.0))
    if op <= 1e-6:
        return rgb.astype(np.float32, copy=False)
    seam_color = np.asarray([1.0, 0.45, 0.10], dtype=np.float32)
    mix = np.clip(seam_mask, 0.0, 1.0)[..., None] * op
    return np.clip((rgb * (1.0 - mix)) + (seam_color[None, None, :] * mix), 0.0, 1.0).astype(np.float32, copy=False)


def _edge_pad_rgb(rgb: np.ndarray, valid_mask: np.ndarray, pad_pixels: int) -> tuple[np.ndarray, np.ndarray]:
    color = rgb.astype(np.float32, copy=True)
    valid = valid_mask.astype(bool, copy=True)
    initial_valid = valid.copy()

    for _ in range(int(max(0, pad_pixels))):
        if bool(np.all(valid)):
            break
        padded_valid = np.pad(valid, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        padded_color = np.pad(color, ((1, 1), (1, 1), (0, 0)), mode="constant", constant_values=0.0)

        accum = np.zeros_like(color, dtype=np.float32)
        count = np.zeros(valid.shape, dtype=np.float32)
        for dy in range(3):
            for dx in range(3):
                if dx == 1 and dy == 1:
                    continue
                neighbor_valid = padded_valid[dy : dy + valid.shape[0], dx : dx + valid.shape[1]]
                neighbor_color = padded_color[dy : dy + color.shape[0], dx : dx + color.shape[1], :]
                accum += neighbor_color * neighbor_valid[..., None]
                count += neighbor_valid.astype(np.float32)

        can_fill = (~valid) & (count > 0.0)
        if not bool(np.any(can_fill)):
            break
        fill = accum / np.maximum(count[..., None], 1e-6)
        color[can_fill] = fill[can_fill]
        valid[can_fill] = True

    fill_mask = np.clip(valid.astype(np.float32) - initial_valid.astype(np.float32), 0.0, 1.0)
    return color.astype(np.float32, copy=False), fill_mask.astype(np.float32, copy=False)


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    weights_np = np.clip(weights, 0.0, 1.0).astype(np.float32, copy=False)
    denom = float(np.sum(weights_np))
    if denom <= 1e-6:
        return float(np.mean(values))
    return float(np.sum(values * weights_np) / denom)


def _delight_rgb(
    rgb: np.ndarray,
    effect_mask: np.ndarray,
    blur_radius: float,
    flatten_strength: float,
    detail_preserve: float,
    shadow_lift: float,
    highlight_compress: float,
    saturation_restore: float,
) -> tuple[np.ndarray, np.ndarray]:
    h, s, v = rgb_to_hsv_np(rgb)
    light_field = blur_single_channel(v, radius=blur_radius)
    neutral_level = max(_weighted_mean(light_field, effect_mask), 1e-4)
    neutral_field = np.clip(light_field / neutral_level, 0.25, 4.0).astype(np.float32, copy=False)

    shadow_weight = np.clip((1.0 - neutral_field) / 0.75, 0.0, 1.0).astype(np.float32, copy=False)
    highlight_weight = np.clip((neutral_field - 1.0) / 0.75, 0.0, 1.0).astype(np.float32, copy=False)
    exponent = np.clip(
        float(max(0.0, flatten_strength))
        + (shadow_weight * float(max(0.0, shadow_lift)))
        + (highlight_weight * float(max(0.0, highlight_compress))),
        0.0,
        4.0,
    ).astype(np.float32, copy=False)

    corrected_v = np.clip(v * np.power(np.maximum(neutral_field, 1e-4), -exponent), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    detail_radius = max(1.0, min(float(max(1.0, blur_radius)) * 0.15, 12.0))
    original_low = blur_single_channel(v, radius=detail_radius)
    corrected_low = blur_single_channel(corrected_v, radius=detail_radius)
    original_high = v - original_low
    corrected_high = corrected_v - corrected_low
    keep_detail = float(np.clip(detail_preserve, 0.0, 1.0))
    final_v = np.clip(
        corrected_low + (corrected_high * (1.0 - keep_detail)) + (original_high * keep_detail),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    effect = np.clip(effect_mask, 0.0, 1.0).astype(np.float32, copy=False)
    sat_restore = float(np.clip(saturation_restore, 0.0, 1.0))
    sat_gain = np.clip(
        1.0 + ((shadow_weight * 0.18) + (highlight_weight * 0.08)) * sat_restore,
        0.55,
        1.4,
    ).astype(np.float32, copy=False)
    corrected_s = np.clip(s * sat_gain, 0.0, 1.0).astype(np.float32, copy=False)
    blended_s = ((s * (1.0 - effect)) + (corrected_s * effect)).astype(np.float32, copy=False)
    blended_v = ((v * (1.0 - effect)) + (final_v * effect)).astype(np.float32, copy=False)
    adjustment_mask = np.clip((np.abs(blended_v - v) * 2.25) + (np.abs(blended_s - s) * 0.85), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    return hsv_to_rgb_np(h, blended_s, blended_v), adjustment_mask


def _albedo_safe_rgb(
    rgb: np.ndarray,
    target_black: float,
    target_white: float,
    saturation_limit: float,
    shadow_lift: float,
    highlight_rolloff: float,
    midtone_preserve: float,
) -> tuple[np.ndarray, np.ndarray]:
    src = np.clip(rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, s, v = rgb_to_hsv_np(src)

    lo = float(np.percentile(v, 1.5))
    hi = float(np.percentile(v, 98.5))
    low = float(np.clip(target_black, 0.0, 1.0))
    high = float(np.clip(max(low + 1e-3, target_white), 0.0, 1.0))
    if hi <= lo + 1e-6:
        remapped_v = np.clip(v, low, high).astype(np.float32, copy=False)
    else:
        remapped_v = np.clip(low + (np.clip((v - lo) / (hi - lo), 0.0, 1.0) * (high - low)), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    shadow_gate = np.clip((0.26 - v) / 0.26, 0.0, 1.0).astype(np.float32, copy=False)
    highlight_gate = np.clip((v - 0.72) / 0.28, 0.0, 1.0).astype(np.float32, copy=False)
    blend = np.clip(0.42 + (shadow_gate * float(np.clip(shadow_lift, 0.0, 1.0))) + (highlight_gate * float(np.clip(highlight_rolloff, 0.0, 1.0))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    safe_v = np.clip((v * (1.0 - blend)) + (remapped_v * blend), 0.0, 1.0).astype(np.float32, copy=False)

    sat_limit = float(np.clip(saturation_limit, 0.0, 1.0))
    sat_over = np.maximum(s - sat_limit, 0.0).astype(np.float32, copy=False)
    sat_compress = np.clip(0.30 + (highlight_gate * 0.40) + (shadow_gate * 0.18), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    safe_s = np.clip(s - (sat_over * sat_compress), 0.0, 1.0).astype(np.float32, copy=False)

    safe_rgb = hsv_to_rgb_np(h, safe_s, safe_v)
    orig_luma = np.clip(luma_np(src), 1e-4, 1.0).astype(np.float32, copy=False)
    safe_luma = np.clip(luma_np(safe_rgb), 0.0, 1.0).astype(np.float32, copy=False)
    hue_preserved = np.clip(src * (safe_luma[..., None] / orig_luma[..., None]), 0.0, 1.0).astype(np.float32, copy=False)
    max_channel = np.maximum(np.max(hue_preserved, axis=-1, keepdims=True), 1e-6)
    hue_preserved = np.where(max_channel > 1.0, hue_preserved / max_channel, hue_preserved).astype(np.float32, copy=False)
    safe_rgb = hue_preserved
    preserve = float(np.clip(midtone_preserve, 0.0, 1.0))
    if preserve > 1e-6:
        midtone_gate = np.clip(1.0 - (np.abs(v - 0.5) / 0.5), 0.0, 1.0).astype(np.float32, copy=False)
        preserve_mix = np.clip(midtone_gate * preserve, 0.0, 1.0).astype(np.float32, copy=False)
        safe_rgb = np.clip((safe_rgb * (1.0 - preserve_mix[..., None])) + (src * preserve_mix[..., None]), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    adjustment_mask = np.clip(np.mean(np.abs(safe_rgb - src), axis=-1) * 7.0, 0.0, 1.0).astype(np.float32, copy=False)
    return safe_rgb, adjustment_mask


def _upsampled_noise_field(h: int, w: int, cells_y: int, cells_x: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    low_res = rng.uniform(0.0, 1.0, size=(int(max(2, cells_y)), int(max(2, cells_x)))).astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(low_res * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    pil = pil.resize((int(w), int(h)), resample=Image.Resampling.BICUBIC)
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _macro_variation_field(h: int, w: int, macro_scale_px: float, seed: int) -> np.ndarray:
    scale = float(max(16.0, macro_scale_px))
    base = _upsampled_noise_field(
        h=int(h),
        w=int(w),
        cells_y=int(np.ceil(float(h) / scale)) + 1,
        cells_x=int(np.ceil(float(w) / scale)) + 1,
        seed=int(seed),
    )
    detail = _upsampled_noise_field(
        h=int(h),
        w=int(w),
        cells_y=int(np.ceil(float(h) / max(12.0, scale * 0.55))) + 1,
        cells_x=int(np.ceil(float(w) / max(12.0, scale * 0.55))) + 1,
        seed=int(seed) + 1,
    )
    return np.clip((base * 0.72) + (detail * 0.28), 0.0, 1.0).astype(np.float32, copy=False)


def _macro_variation_rgb(
    rgb: np.ndarray,
    macro_scale_px: float,
    strength: float,
    hue_variation: float,
    saturation_variation: float,
    value_variation: float,
    contrast_variation: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    h_px, w_px = rgb.shape[:2]
    field = _macro_variation_field(h=int(h_px), w=int(w_px), macro_scale_px=macro_scale_px, seed=seed)
    field = blur_single_channel(field, radius=max(1.0, float(macro_scale_px) * 0.08))
    centered = np.clip(((field * 2.0) - 1.0) * 1.45, -1.0, 1.0).astype(np.float32, copy=False)
    amt = float(np.clip(strength, 0.0, 1.0))

    contrasted = np.clip(
        ((np.clip(rgb[..., :3], 0.0, 1.0) - 0.5) * (1.0 + (centered[..., None] * float(max(0.0, contrast_variation)) * amt))) + 0.5,
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    h, s, v = rgb_to_hsv_np(contrasted)
    h = np.mod(h + (centered * float(max(0.0, hue_variation)) * amt), 1.0).astype(np.float32, copy=False)
    s = np.clip(s * (1.0 + (centered * float(max(0.0, saturation_variation)) * amt)), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    v = np.clip(v * (1.0 + (centered * float(max(0.0, value_variation)) * amt)), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    varied = hsv_to_rgb_np(h, s, v)
    return varied, np.clip(np.abs(centered) * amt, 0.0, 1.0).astype(np.float32, copy=False)


def _detile_blend_rgb(
    rgb: np.ndarray,
    macro_scale_px: float,
    blend_strength: float,
    color_match_blur: float,
    detail_preserve: float,
    variation_breakup: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    h_px, w_px = rgb.shape[:2]
    shift_y = max(1, int(h_px // 2))
    shift_x = max(1, int(w_px // 2))
    offset_rgb = roll_image_np(rgb, shift_y=shift_y, shift_x=shift_x)

    field = _macro_variation_field(h=int(h_px), w=int(w_px), macro_scale_px=macro_scale_px, seed=seed)
    field = blur_single_channel(field, radius=max(1.0, float(macro_scale_px) * 0.08))
    mix = smoothstep_np(0.28, 0.72, field).astype(np.float32, copy=False)
    breakup = float(np.clip(variation_breakup, 0.0, 1.0))
    if breakup > 1e-6:
        breakup_field = _macro_variation_field(
            h=int(h_px),
            w=int(w_px),
            macro_scale_px=max(16.0, float(macro_scale_px) * 0.72),
            seed=int(seed) + 19,
        )
        breakup_field = blur_single_channel(breakup_field, radius=max(1.0, float(macro_scale_px) * 0.04))
        mix = np.clip(mix + (((breakup_field * 2.0) - 1.0) * breakup * 0.24), 0.0, 1.0).astype(np.float32, copy=False)
    amt = float(np.clip(blend_strength, 0.0, 1.0))
    mix = np.clip(mix * amt, 0.0, 1.0).astype(np.float32, copy=False)

    blur_r = float(max(0.0, color_match_blur))
    matched_offset = offset_rgb
    if blur_r > 1e-6:
        low_src = gaussian_blur_rgb_np(np.clip(rgb[..., :3], 0.0, 1.0), radius=blur_r)
        low_offset = gaussian_blur_rgb_np(np.clip(offset_rgb[..., :3], 0.0, 1.0), radius=blur_r)
        gain = np.clip((low_src + 0.03) / np.maximum(low_offset + 0.03, 1e-4), 0.65, 1.55).astype(
            np.float32,
            copy=False,
        )
        matched_offset = np.clip(offset_rgb * gain, 0.0, 1.0).astype(np.float32, copy=False)

    blended = np.clip((rgb * (1.0 - mix[..., None])) + (matched_offset * mix[..., None]), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    keep = float(np.clip(detail_preserve, 0.0, 1.0))
    if keep > 1e-6:
        detail_radius = max(1.0, float(macro_scale_px) * 0.05)
        orig_low = gaussian_blur_rgb_np(np.clip(rgb[..., :3], 0.0, 1.0), radius=detail_radius)
        blend_low = gaussian_blur_rgb_np(np.clip(blended[..., :3], 0.0, 1.0), radius=detail_radius)
        orig_high = np.clip(rgb[..., :3], 0.0, 1.0) - orig_low
        blend_high = blended[..., :3] - blend_low
        blended = np.clip(blend_low + (orig_high * keep) + (blend_high * (1.0 - keep)), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    adjustment_mask = np.clip((np.mean(np.abs(blended - rgb[..., :3]), axis=-1) * 5.5) + (mix * 0.35), 0.0, 1.0)
    return blended.astype(np.float32, copy=False), adjustment_mask.astype(np.float32, copy=False)


class x1TextureOffset:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "mode": "half_tile",
            "offset_x": 0.5,
            "offset_y": 0.5,
            "seam_width": 6.0,
            "seam_softness": 3.0,
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
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "offset_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "offset_x": {"min": -4096.0, "max": 4096.0},
                "offset_y": {"min": -4096.0, "max": 4096.0},
                "seam_width": {"min": 0.0, "max": 256.0},
                "seam_softness": {"min": 0.0, "max": 256.0},
            },
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        mode = str(settings["mode"]).lower()
        if mode not in {"half_tile", "fraction", "pixels"}:
            mode = "half_tile"
        shift_y, shift_x = _resolve_offset_pixels(int(h), int(w), mode, settings["offset_x"], settings["offset_y"])
        seam_mask = _offset_seam_mask(
            int(h),
            int(w),
            shift_y,
            shift_x,
            float(max(0.0, settings["seam_width"])),
            float(max(0.0, settings["seam_softness"])),
        )

        for idx in range(int(b)):
            out_np[idx] = roll_image_np(src_np[idx], shift_y=shift_y, shift_x=shift_x)
            mask_np[idx] = seam_mask

        info = (
            "x1TextureOffset: mode={}, shift_x={}px, shift_y={}px, seam_width={:.1f}px, seam_softness={:.1f}px"
        ).format(
            mode,
            int(shift_x),
            int(shift_y),
            float(max(0.0, settings["seam_width"])),
            float(max(0.0, settings["seam_softness"])),
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureSeamless:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "blend_width": 24.0,
            "edge_match_strength": 0.85,
            "edge_match_blur": 18.0,
            "detail_preserve": 0.65,
            "seam_blur": 12.0,
            "seam_softness": 12.0,
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
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "seamless_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "blend_width": {"min": 1.0, "max": 512.0},
                "edge_match_strength": {"min": 0.0, "max": 1.0},
                "edge_match_blur": {"min": 0.0, "max": 256.0},
                "detail_preserve": {"min": 0.0, "max": 1.0},
                "seam_blur": {"min": 0.0, "max": 256.0},
                "seam_softness": {"min": 0.5, "max": 256.0},
            },
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        shift_y = int(h // 2)
        shift_x = int(w // 2)
        bw = float(max(1.0, settings["blend_width"]))
        edge_band = max(1, int(round(bw)))
        seam_mask_center = cross_seam_mask(
            h=int(h),
            w=int(w),
            seam_x=float(shift_x),
            seam_y=float(shift_y),
            half_width=bw,
            softness=float(max(0.5, settings["seam_softness"])),
        )
        seam_mask_output = roll_image_np(seam_mask_center, shift_y=-shift_y, shift_x=-shift_x)

        for idx in range(int(b)):
            sample = src_np[idx]
            rgb = edge_match_low_frequency(
                image=sample[..., :3],
                blur_radius=float(max(0.0, settings["edge_match_blur"])),
                edge_band=edge_band,
                strength=float(np.clip(settings["edge_match_strength"], 0.0, 1.0)),
            )
            rgb = roll_image_np(rgb, shift_y=shift_y, shift_x=shift_x)
            rgb = smooth_seams(
                image=rgb,
                seam_mask=seam_mask_center,
                blur_radius=float(max(0.0, settings["seam_blur"])),
                detail_preserve=float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
            )
            rgb = roll_image_np(rgb, shift_y=-shift_y, shift_x=-shift_x)

            if c == 4:
                alpha = edge_match_low_frequency(
                    image=sample[..., 3],
                    blur_radius=float(max(0.0, settings["edge_match_blur"])),
                    edge_band=edge_band,
                    strength=float(np.clip(settings["edge_match_strength"], 0.0, 1.0)),
                )
                alpha = roll_image_np(alpha, shift_y=shift_y, shift_x=shift_x)
                alpha = smooth_seams(
                    image=alpha,
                    seam_mask=seam_mask_center,
                    blur_radius=float(max(0.0, settings["seam_blur"])),
                    detail_preserve=float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
                )
                alpha = roll_image_np(alpha, shift_y=-shift_y, shift_x=-shift_x)
                out_np[idx] = np.concatenate([rgb, alpha[..., None]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = rgb
            mask_np[idx] = seam_mask_output

        info = (
            "x1TextureSeamless: blend_width={:.1f}px, edge_match_strength={:.2f}, edge_match_blur={:.1f}px, "
            "detail_preserve={:.2f}, seam_blur={:.1f}px, seam_softness={:.1f}px"
        ).format(
            bw,
            float(np.clip(settings["edge_match_strength"], 0.0, 1.0)),
            float(max(0.0, settings["edge_match_blur"])),
            float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
            float(max(0.0, settings["seam_blur"])),
            float(max(0.5, settings["seam_softness"])),
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureTilePreview:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "tiles_x": 3,
            "tiles_y": 3,
            "show_seams": True,
            "seam_width": 2.0,
            "seam_opacity": 0.65,
            "seam_softness": 1.0,
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
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "tile_preview_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "tiles_x": {"min": 1, "max": 8, "integer": True},
                "tiles_y": {"min": 1, "max": 8, "integer": True},
                "seam_width": {"min": 0.0, "max": 32.0},
                "seam_opacity": {"min": 0.0, "max": 1.0},
                "seam_softness": {"min": 0.0, "max": 32.0},
            },
            boolean_keys={"show_seams"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)

        out_samples: list[np.ndarray] = []
        mask_samples: list[np.ndarray] = []
        tiles_x = int(max(1, settings["tiles_x"]))
        tiles_y = int(max(1, settings["tiles_y"]))
        seam_width = float(max(0.0, settings["seam_width"]))
        seam_opacity = float(np.clip(settings["seam_opacity"], 0.0, 1.0))
        seam_softness = float(max(0.0, settings["seam_softness"]))
        tiled_h = int(h) * tiles_y
        tiled_w = int(w) * tiles_x
        seam_mask = tile_grid_mask(
            h=tiled_h,
            w=tiled_w,
            tiles_y=tiles_y,
            tiles_x=tiles_x,
            half_width=seam_width,
            softness=max(0.5, seam_softness),
        )

        for idx in range(int(b)):
            tiled = _tile_image_np(src_np[idx], tiles_y=tiles_y, tiles_x=tiles_x)
            if bool(settings["show_seams"]):
                rgb = _overlay_seams(tiled[..., :3], seam_mask=seam_mask, opacity=seam_opacity)
                if c == 4:
                    tiled = np.concatenate([rgb, tiled[..., 3:4]], axis=-1).astype(np.float32, copy=False)
                else:
                    tiled = rgb
            out_samples.append(tiled.astype(np.float32, copy=False))
            mask_samples.append(seam_mask.astype(np.float32, copy=False))

        out_np = np.stack(out_samples, axis=0).astype(np.float32, copy=False)
        mask_np = np.stack(mask_samples, axis=0).astype(np.float32, copy=False)
        info = (
            "x1TextureTilePreview: tiles_x={}, tiles_y={}, seam_width={:.1f}px, seam_softness={:.1f}px, show_seams={}, seam_opacity={:.2f}"
        ).format(
            tiles_x,
            tiles_y,
            seam_width,
            seam_softness,
            bool(settings["show_seams"]),
            seam_opacity,
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureEdgePad:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "alpha",
            "pad_pixels": 16,
            "alpha_threshold": 0.01,
            "expand_alpha": False,
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
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "edge_pad_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "pad_pixels": {"min": 1, "max": 512, "integer": True},
                "alpha_threshold": {"min": 0.0, "max": 1.0},
            },
            boolean_keys={"expand_alpha"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        fill_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        threshold = float(np.clip(settings["alpha_threshold"], 0.0, 1.0))

        resolved_source = str(settings["source_mode"]).lower()
        if resolved_source not in {"alpha", "mask", "luma_nonzero"}:
            resolved_source = "alpha"
        for idx in range(int(b)):
            sample = src_np[idx]
            rgb = sample[..., :3]
            if resolved_source == "mask" and source_mask_np is not None:
                valid = source_mask_np[idx] > threshold
                resolved = "mask"
            elif resolved_source == "alpha" and c == 4:
                valid = sample[..., 3] > threshold
                resolved = "alpha"
            else:
                valid = luma_np(rgb) > threshold
                resolved = "luma_nonzero"

            padded_rgb, fill_mask = _edge_pad_rgb(rgb, valid, int(max(1, settings["pad_pixels"])))
            fill_mask_np[idx] = fill_mask

            if c == 4:
                alpha = sample[..., 3:4]
                if bool(settings["expand_alpha"]):
                    alpha = np.maximum(alpha, fill_mask[..., None]).astype(np.float32, copy=False)
                out_np[idx] = np.concatenate([padded_rgb, alpha], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = padded_rgb
            resolved_source = resolved

        info = (
            "x1TextureEdgePad: source_mode={}, pad_pixels={}, alpha_threshold={:.3f}, expand_alpha={}"
        ).format(resolved_source, int(max(1, settings["pad_pixels"])), threshold, bool(settings["expand_alpha"]))
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(fill_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureDelight:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "blur_radius": 32.0,
            "flatten_strength": 0.85,
            "detail_preserve": 0.8,
            "shadow_lift": 0.3,
            "highlight_compress": 0.2,
            "saturation_restore": 0.18,
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
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "delight_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "blur_radius": {"min": 1.0, "max": 512.0},
                "flatten_strength": {"min": 0.0, "max": 2.0},
                "detail_preserve": {"min": 0.0, "max": 1.0},
                "shadow_lift": {"min": 0.0, "max": 2.0},
                "highlight_compress": {"min": 0.0, "max": 2.0},
                "saturation_restore": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        adjustment_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        effect_mask_t = mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_mask_np = effect_mask_t.detach().cpu().numpy().astype(np.float32, copy=False)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        for idx in range(int(b)):
            sample = src_np[idx]
            delighted_rgb, adjustment_mask = _delight_rgb(
                rgb=sample[..., :3],
                effect_mask=effect_mask_np[idx],
                blur_radius=float(max(1.0, settings["blur_radius"])),
                flatten_strength=float(max(0.0, settings["flatten_strength"])),
                detail_preserve=float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
                shadow_lift=float(max(0.0, settings["shadow_lift"])),
                highlight_compress=float(max(0.0, settings["highlight_compress"])),
                saturation_restore=float(np.clip(settings["saturation_restore"], 0.0, 1.0)),
            )
            adjustment_mask_np[idx] = adjustment_mask
            if c == 4:
                out_np[idx] = np.concatenate([delighted_rgb, sample[..., 3:4]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = delighted_rgb

        info = (
            "x1TextureDelight: blur_radius={:.1f}px, flatten_strength={:.2f}, detail_preserve={:.2f}, "
            "shadow_lift={:.2f}, highlight_compress={:.2f}, saturation_restore={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            float(max(1.0, settings["blur_radius"])),
            float(max(0.0, settings["flatten_strength"])),
            float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
            float(max(0.0, settings["shadow_lift"])),
            float(max(0.0, settings["highlight_compress"])),
            float(np.clip(settings["saturation_restore"], 0.0, 1.0)),
            float(max(0.0, settings["mask_feather"])),
            coverage,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(adjustment_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureAlbedoSafe:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "target_black": 0.04,
            "target_white": 0.82,
            "saturation_limit": 0.85,
            "shadow_lift": 0.35,
            "highlight_rolloff": 0.55,
            "midtone_preserve": 0.28,
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
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "albedo_safe_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "target_black": {"min": 0.0, "max": 0.5},
                "target_white": {"min": 0.1, "max": 1.0},
                "saturation_limit": {"min": 0.0, "max": 1.0},
                "shadow_lift": {"min": 0.0, "max": 1.0},
                "highlight_rolloff": {"min": 0.0, "max": 1.0},
                "midtone_preserve": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        adjustment_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        effect_mask_t = mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_mask_np = effect_mask_t.detach().cpu().numpy().astype(np.float32, copy=False)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        for idx in range(int(b)):
            sample = src_np[idx]
            safe_rgb, adjust_mask = _albedo_safe_rgb(
                rgb=sample[..., :3],
                target_black=float(np.clip(settings["target_black"], 0.0, 0.5)),
                target_white=float(np.clip(settings["target_white"], 0.1, 1.0)),
                saturation_limit=float(np.clip(settings["saturation_limit"], 0.0, 1.0)),
                shadow_lift=float(np.clip(settings["shadow_lift"], 0.0, 1.0)),
                highlight_rolloff=float(np.clip(settings["highlight_rolloff"], 0.0, 1.0)),
                midtone_preserve=float(np.clip(settings["midtone_preserve"], 0.0, 1.0)),
            )
            effect = effect_mask_np[idx][..., None]
            mixed_rgb = np.clip((sample[..., :3] * (1.0 - effect)) + (safe_rgb * effect), 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )
            adjustment_mask_np[idx] = np.clip(adjust_mask * effect_mask_np[idx], 0.0, 1.0)
            if c == 4:
                out_np[idx] = np.concatenate([mixed_rgb, sample[..., 3:4]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = mixed_rgb

        info = (
            "x1TextureAlbedoSafe: target_black={:.3f}, target_white={:.3f}, saturation_limit={:.2f}, "
            "shadow_lift={:.2f}, highlight_rolloff={:.2f}, midtone_preserve={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            float(np.clip(settings["target_black"], 0.0, 0.5)),
            float(np.clip(settings["target_white"], 0.1, 1.0)),
            float(np.clip(settings["saturation_limit"], 0.0, 1.0)),
            float(np.clip(settings["shadow_lift"], 0.0, 1.0)),
            float(np.clip(settings["highlight_rolloff"], 0.0, 1.0)),
            float(np.clip(settings["midtone_preserve"], 0.0, 1.0)),
            float(max(0.0, settings["mask_feather"])),
            coverage,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(adjustment_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureMacroVariation:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "macro_scale_px": 160.0,
            "strength": 0.55,
            "hue_variation": 0.02,
            "saturation_variation": 0.12,
            "value_variation": 0.12,
            "contrast_variation": 0.18,
            "seed": 11,
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
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "macro_variation_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "macro_scale_px": {"min": 16.0, "max": 2048.0},
                "strength": {"min": 0.0, "max": 1.0},
                "hue_variation": {"min": 0.0, "max": 0.25},
                "saturation_variation": {"min": 0.0, "max": 1.0},
                "value_variation": {"min": 0.0, "max": 1.0},
                "contrast_variation": {"min": 0.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        variation_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        effect_mask_t = mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_mask_np = effect_mask_t.detach().cpu().numpy().astype(np.float32, copy=False)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        for idx in range(int(b)):
            sample = src_np[idx]
            varied_rgb, variation_mask = _macro_variation_rgb(
                rgb=sample[..., :3],
                macro_scale_px=float(max(16.0, settings["macro_scale_px"])),
                strength=float(np.clip(settings["strength"], 0.0, 1.0)),
                hue_variation=float(max(0.0, settings["hue_variation"])),
                saturation_variation=float(max(0.0, settings["saturation_variation"])),
                value_variation=float(max(0.0, settings["value_variation"])),
                contrast_variation=float(max(0.0, settings["contrast_variation"])),
                seed=int(settings["seed"] + idx),
            )
            effect = effect_mask_np[idx][..., None]
            mixed_rgb = np.clip((sample[..., :3] * (1.0 - effect)) + (varied_rgb * effect), 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )
            variation_mask_np[idx] = np.clip(variation_mask * effect_mask_np[idx], 0.0, 1.0)
            if c == 4:
                out_np[idx] = np.concatenate([mixed_rgb, sample[..., 3:4]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = mixed_rgb

        info = (
            "x1TextureMacroVariation: macro_scale_px={:.1f}, strength={:.2f}, hue_variation={:.3f}, "
            "saturation_variation={:.2f}, value_variation={:.2f}, contrast_variation={:.2f}, seed={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            float(max(16.0, settings["macro_scale_px"])),
            float(np.clip(settings["strength"], 0.0, 1.0)),
            float(max(0.0, settings["hue_variation"])),
            float(max(0.0, settings["saturation_variation"])),
            float(max(0.0, settings["value_variation"])),
            float(max(0.0, settings["contrast_variation"])),
            int(settings["seed"]),
            float(max(0.0, settings["mask_feather"])),
            coverage,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(variation_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureDetileBlend:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "macro_scale_px": 196.0,
            "blend_strength": 0.55,
            "color_match_blur": 20.0,
            "detail_preserve": 0.72,
            "variation_breakup": 0.22,
            "seed": 101,
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
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "detile_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "macro_scale_px": {"min": 16.0, "max": 2048.0},
                "blend_strength": {"min": 0.0, "max": 1.0},
                "color_match_blur": {"min": 0.0, "max": 256.0},
                "detail_preserve": {"min": 0.0, "max": 1.0},
                "variation_breakup": {"min": 0.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        detile_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        effect_mask_t = mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_mask_np = effect_mask_t.detach().cpu().numpy().astype(np.float32, copy=False)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        for idx in range(int(b)):
            sample = src_np[idx]
            detiled_rgb, detile_mask = _detile_blend_rgb(
                rgb=sample[..., :3],
                macro_scale_px=float(max(16.0, settings["macro_scale_px"])),
                blend_strength=float(np.clip(settings["blend_strength"], 0.0, 1.0)),
                color_match_blur=float(max(0.0, settings["color_match_blur"])),
                detail_preserve=float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
                variation_breakup=float(np.clip(settings["variation_breakup"], 0.0, 1.0)),
                seed=int(settings["seed"] + idx),
            )
            effect = effect_mask_np[idx][..., None]
            mixed_rgb = np.clip((sample[..., :3] * (1.0 - effect)) + (detiled_rgb * effect), 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )
            detile_mask_np[idx] = np.clip(detile_mask * effect_mask_np[idx], 0.0, 1.0)
            if c == 4:
                out_np[idx] = np.concatenate([mixed_rgb, sample[..., 3:4]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = mixed_rgb

        info = (
            "x1TextureDetileBlend: macro_scale_px={:.1f}, blend_strength={:.2f}, color_match_blur={:.1f}px, "
            "detail_preserve={:.2f}, variation_breakup={:.2f}, seed={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            float(max(16.0, settings["macro_scale_px"])),
            float(np.clip(settings["blend_strength"], 0.0, 1.0)),
            float(max(0.0, settings["color_match_blur"])),
            float(np.clip(settings["detail_preserve"], 0.0, 1.0)),
            float(np.clip(settings["variation_breakup"], 0.0, 1.0)),
            int(settings["seed"]),
            float(max(0.0, settings["mask_feather"])),
            coverage,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(detile_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureNoiseField:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "variant": "fbm",
            "scale_px": 160.0,
            "octaves": 5,
            "lacunarity": 2.0,
            "gain": 0.55,
            "detail_mix": 0.18,
            "contrast": 1.15,
            "balance": 0.0,
            "invert": False,
            "seed": 17,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "noise_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "scale_px": {"min": 2.0, "max": 4096.0},
                "octaves": {"min": 1, "max": 8, "integer": True},
                "lacunarity": {"min": 1.1, "max": 4.0},
                "gain": {"min": 0.01, "max": 1.0},
                "detail_mix": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.05, "max": 4.0},
                "balance": {"min": -1.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
            },
            boolean_keys={"invert"},
            legacy=legacy_settings,
        )
        resolved_variant = str(settings["variant"]).lower()
        if resolved_variant not in {"fbm", "value", "turbulence", "ridged"}:
            resolved_variant = "fbm"
        width = int(max(64, settings["width"]))
        height = int(max(64, settings["height"]))
        scale_px = float(max(2.0, settings["scale_px"]))
        octaves = 1 if resolved_variant == "value" else int(max(1, settings["octaves"]))
        lacunarity = float(max(1.1, settings["lacunarity"]))
        gain = float(np.clip(settings["gain"], 0.01, 1.0))
        detail_mix = float(np.clip(settings["detail_mix"], 0.0, 1.0))
        seed = int(settings["seed"])
        field = procedural_noise_field(
            h=int(height),
            w=int(width),
            scale_px=scale_px,
            octaves=octaves,
            lacunarity=lacunarity,
            gain=gain,
            seed=seed,
            variant=resolved_variant,
        )
        if detail_mix > 1e-6:
            fine_scale = max(2.0, scale_px * 0.42)
            detail_variant = resolved_variant if resolved_variant != "value" else "fbm"
            detail_field = procedural_noise_field(
                h=int(height),
                w=int(width),
                scale_px=fine_scale,
                octaves=min(8, max(2, octaves + 1)),
                lacunarity=lacunarity,
                gain=gain,
                seed=seed + 101,
                variant=detail_variant,
            )
            field = np.clip((field * (1.0 - detail_mix)) + (detail_field * detail_mix), 0.0, 1.0).astype(np.float32, copy=False)
        shaped = shape_scalar_field(
            field=field,
            contrast=float(max(0.05, settings["contrast"])),
            balance=float(np.clip(settings["balance"], -1.0, 1.0)),
            invert=bool(settings["invert"]),
        )
        image_t, mask_t = _field_output(shaped)
        info = (
            "x1TextureNoiseField: size={}x{}, variant={}, scale_px={:.1f}, octaves={}, "
            "lacunarity={:.2f}, gain={:.2f}, detail_mix={:.2f}, contrast={:.2f}, balance={:.2f}, seed={}{}"
        ).format(
            int(width),
            int(height),
            resolved_variant,
            float(scale_px),
            int(octaves),
            float(lacunarity),
            float(gain),
            float(detail_mix),
            float(max(0.05, settings["contrast"])),
            float(np.clip(settings["balance"], -1.0, 1.0)),
            seed,
            " (inverted)" if settings["invert"] else "",
        )
        return image_t, mask_t, info


class x1TextureCellPattern:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "pattern_mode": "fill",
            "cell_scale_px": 96.0,
            "jitter": 0.85,
            "edge_width": 0.18,
            "softness": 0.0,
            "contrast": 1.2,
            "balance": 0.0,
            "invert": False,
            "seed": 31,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "cell_pattern_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "cell_scale_px": {"min": 4.0, "max": 4096.0},
                "jitter": {"min": 0.0, "max": 1.0},
                "edge_width": {"min": 0.01, "max": 1.0},
                "softness": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.05, "max": 4.0},
                "balance": {"min": -1.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
            },
            boolean_keys={"invert"},
            legacy=legacy_settings,
        )
        width = int(max(64, settings["width"]))
        height = int(max(64, settings["height"]))
        pattern_mode = str(settings["pattern_mode"]).lower()
        if pattern_mode not in {"fill", "edge", "cracks", "distance", "bevel"}:
            pattern_mode = "fill"
        field = procedural_cell_pattern(
            h=int(height),
            w=int(width),
            cell_scale_px=float(max(4.0, settings["cell_scale_px"])),
            jitter=float(np.clip(settings["jitter"], 0.0, 1.0)),
            edge_width=float(np.clip(settings["edge_width"], 0.01, 1.0)),
            seed=int(settings["seed"]),
            pattern_mode=pattern_mode,
        )
        softness = float(np.clip(settings["softness"], 0.0, 1.0))
        if softness > 1e-6:
            field = blur_single_channel(
                field,
                radius=max(0.5, float(max(4.0, settings["cell_scale_px"])) * (0.08 * softness)),
            )
        shaped = shape_scalar_field(
            field=field,
            contrast=float(max(0.05, settings["contrast"])),
            balance=float(np.clip(settings["balance"], -1.0, 1.0)),
            invert=bool(settings["invert"]),
        )
        image_t, mask_t = _field_output(shaped)
        info = (
            "x1TextureCellPattern: size={}x{}, mode={}, cell_scale_px={:.1f}, jitter={:.2f}, "
            "edge_width={:.2f}, softness={:.2f}, contrast={:.2f}, balance={:.2f}, seed={}{}"
        ).format(
            int(width),
            int(height),
            pattern_mode,
            float(max(4.0, settings["cell_scale_px"])),
            float(np.clip(settings["jitter"], 0.0, 1.0)),
            float(np.clip(settings["edge_width"], 0.01, 1.0)),
            softness,
            float(max(0.05, settings["contrast"])),
            float(np.clip(settings["balance"], -1.0, 1.0)),
            int(settings["seed"]),
            " (inverted)" if settings["invert"] else "",
        )
        return image_t, mask_t, info


class x1TextureStrata:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "profile": "soft",
            "band_scale_px": 180.0,
            "direction_deg": 24.0,
            "warp_strength": 0.32,
            "breakup_scale_px": 112.0,
            "breakup_strength": 0.38,
            "micro_breakup": 0.18,
            "contrast": 1.15,
            "balance": 0.0,
            "invert": False,
            "seed": 53,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "strata_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "band_scale_px": {"min": 4.0, "max": 4096.0},
                "direction_deg": {"min": -180.0, "max": 180.0},
                "warp_strength": {"min": 0.0, "max": 1.0},
                "breakup_scale_px": {"min": 4.0, "max": 4096.0},
                "breakup_strength": {"min": 0.0, "max": 1.0},
                "micro_breakup": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.05, "max": 4.0},
                "balance": {"min": -1.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
            },
            boolean_keys={"invert"},
            legacy=legacy_settings,
        )
        width = int(max(64, settings["width"]))
        height = int(max(64, settings["height"]))
        profile = str(settings["profile"]).lower()
        if profile not in {"soft", "veins", "terrace"}:
            profile = "soft"
        field = procedural_strata_pattern(
            h=int(height),
            w=int(width),
            band_scale_px=float(max(4.0, settings["band_scale_px"])),
            direction_deg=float(settings["direction_deg"]),
            warp_strength=float(np.clip(settings["warp_strength"], 0.0, 1.0)),
            breakup_scale_px=float(max(4.0, settings["breakup_scale_px"])),
            breakup_strength=float(np.clip(settings["breakup_strength"], 0.0, 1.0)),
            seed=int(settings["seed"]),
            profile=profile,
        )
        micro_breakup = float(np.clip(settings["micro_breakup"], 0.0, 1.0))
        if micro_breakup > 1e-6:
            fine_breakup = procedural_noise_field(
                h=int(height),
                w=int(width),
                scale_px=max(4.0, float(settings["breakup_scale_px"]) * 0.32),
                octaves=3,
                lacunarity=2.0,
                gain=0.55,
                seed=int(settings["seed"]) + 37,
                variant="fbm",
            )
            mix = micro_breakup * 0.22
            field = np.clip((field * (1.0 - mix)) + (fine_breakup * mix), 0.0, 1.0).astype(np.float32, copy=False)
        shaped = shape_scalar_field(
            field=field,
            contrast=float(max(0.05, settings["contrast"])),
            balance=float(np.clip(settings["balance"], -1.0, 1.0)),
            invert=bool(settings["invert"]),
        )
        image_t, mask_t = _field_output(shaped)
        info = (
            "x1TextureStrata: size={}x{}, profile={}, band_scale_px={:.1f}, direction_deg={:.1f}, "
            "warp_strength={:.2f}, breakup_scale_px={:.1f}, breakup_strength={:.2f}, micro_breakup={:.2f}, "
            "contrast={:.2f}, balance={:.2f}, seed={}{}"
        ).format(
            int(width),
            int(height),
            profile,
            float(max(4.0, settings["band_scale_px"])),
            float(settings["direction_deg"]),
            float(np.clip(settings["warp_strength"], 0.0, 1.0)),
            float(max(4.0, settings["breakup_scale_px"])),
            float(np.clip(settings["breakup_strength"], 0.0, 1.0)),
            micro_breakup,
            float(max(0.05, settings["contrast"])),
            float(np.clip(settings["balance"], -1.0, 1.0)),
            int(settings["seed"]),
            " (inverted)" if settings["invert"] else "",
        )
        return image_t, mask_t, info


class x1TextureHexTiles:
    SEARCH_ALIASES = ["honeycomb", "hexagon", "scales"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "pattern_mode": "fill",
            "hex_scale_px": 84.0,
            "line_width": 0.18,
            "softness": 0.0,
            "contrast": 1.15,
            "balance": 0.0,
            "invert": False,
            "seed": 67,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "hex_tiles_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "hex_scale_px": {"min": 4.0, "max": 4096.0},
                "line_width": {"min": 0.01, "max": 1.0},
                "softness": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.05, "max": 4.0},
                "balance": {"min": -1.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
            },
            boolean_keys={"invert"},
            legacy=legacy_settings,
        )
        width = int(max(64, settings["width"]))
        height = int(max(64, settings["height"]))
        pattern_mode = str(settings["pattern_mode"]).lower()
        if pattern_mode not in {"fill", "lines", "centers", "bevel"}:
            pattern_mode = "fill"
        field = procedural_hex_pattern(
            h=int(height),
            w=int(width),
            hex_scale_px=float(max(4.0, settings["hex_scale_px"])),
            line_width=float(np.clip(settings["line_width"], 0.01, 1.0)),
            seed=int(settings["seed"]),
            pattern_mode=pattern_mode,
        )
        softness = float(np.clip(settings["softness"], 0.0, 1.0))
        if softness > 1e-6:
            field = blur_single_channel(field, radius=max(0.5, float(settings["hex_scale_px"]) * (0.06 * softness)))
        shaped = shape_scalar_field(
            field=field,
            contrast=float(max(0.05, settings["contrast"])),
            balance=float(np.clip(settings["balance"], -1.0, 1.0)),
            invert=bool(settings["invert"]),
        )
        image_t, mask_t = _field_output(shaped)
        info = (
            "x1TextureHexTiles: size={}x{}, mode={}, hex_scale_px={:.1f}, line_width={:.2f}, softness={:.2f}, "
            "contrast={:.2f}, balance={:.2f}, seed={}{}"
        ).format(
            int(width),
            int(height),
            pattern_mode,
            float(max(4.0, settings["hex_scale_px"])),
            float(np.clip(settings["line_width"], 0.01, 1.0)),
            softness,
            float(max(0.05, settings["contrast"])),
            float(np.clip(settings["balance"], -1.0, 1.0)),
            int(settings["seed"]),
            " (inverted)" if settings["invert"] else "",
        )
        return image_t, mask_t, info


class x1TextureWeavePattern:
    SEARCH_ALIASES = ["fabric", "cloth", "carbon fiber"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "style": "plain",
            "warp_scale_px": 32.0,
            "weft_scale_px": 32.0,
            "thread_width": 0.72,
            "relief": 0.82,
            "fiber_variation": 0.22,
            "contrast": 1.2,
            "balance": 0.0,
            "invert": False,
            "seed": 79,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "weave_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "warp_scale_px": {"min": 4.0, "max": 4096.0},
                "weft_scale_px": {"min": 4.0, "max": 4096.0},
                "thread_width": {"min": 0.05, "max": 0.98},
                "relief": {"min": 0.0, "max": 1.0},
                "fiber_variation": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.05, "max": 4.0},
                "balance": {"min": -1.0, "max": 1.0},
                "seed": {"min": 0, "max": 2_147_483_647, "integer": True},
            },
            boolean_keys={"invert"},
            legacy=legacy_settings,
        )
        width = int(max(64, settings["width"]))
        height = int(max(64, settings["height"]))
        style = str(settings["style"]).lower()
        if style not in {"plain", "twill", "basket"}:
            style = "plain"
        field = procedural_weave_pattern(
            h=int(height),
            w=int(width),
            warp_scale_px=float(max(4.0, settings["warp_scale_px"])),
            weft_scale_px=float(max(4.0, settings["weft_scale_px"])),
            thread_width=float(np.clip(settings["thread_width"], 0.05, 0.98)),
            relief=float(np.clip(settings["relief"], 0.0, 1.0)),
            seed=int(settings["seed"]),
            style=style,
        )
        fiber_variation = float(np.clip(settings["fiber_variation"], 0.0, 1.0))
        if fiber_variation > 1e-6:
            fiber = procedural_noise_field(
                h=int(height),
                w=int(width),
                scale_px=max(4.0, min(float(settings["warp_scale_px"]), float(settings["weft_scale_px"])) * 0.7),
                octaves=3,
                lacunarity=2.1,
                gain=0.58,
                seed=int(settings["seed"]) + 121,
                variant="fbm",
            )
            fiber = ((fiber * 2.0) - 1.0).astype(np.float32, copy=False)
            field = np.clip(field * (1.0 + (fiber * fiber_variation * 0.22)), 0.0, 1.0).astype(np.float32, copy=False)
        shaped = shape_scalar_field(
            field=field,
            contrast=float(max(0.05, settings["contrast"])),
            balance=float(np.clip(settings["balance"], -1.0, 1.0)),
            invert=bool(settings["invert"]),
        )
        image_t, mask_t = _field_output(shaped)
        info = (
            "x1TextureWeavePattern: size={}x{}, style={}, warp_scale_px={:.1f}, weft_scale_px={:.1f}, "
            "thread_width={:.2f}, relief={:.2f}, fiber_variation={:.2f}, contrast={:.2f}, balance={:.2f}, seed={}{}"
        ).format(
            int(width),
            int(height),
            style,
            float(max(4.0, settings["warp_scale_px"])),
            float(max(4.0, settings["weft_scale_px"])),
            float(np.clip(settings["thread_width"], 0.05, 0.98)),
            float(np.clip(settings["relief"], 0.0, 1.0)),
            fiber_variation,
            float(max(0.05, settings["contrast"])),
            float(np.clip(settings["balance"], -1.0, 1.0)),
            int(settings["seed"]),
            " (inverted)" if settings["invert"] else "",
        )
        return image_t, mask_t, info
