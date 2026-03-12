from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_TECH_ART
from ..lib.image_shared import gaussian_blur_rgb_np, hsv_to_rgb_np, mask_to_batch, rgb_to_hsv_np, to_image_batch
from ..lib.scalar_map_shared import blur_single_channel, mask_tensor_to_np, normalize_scalar, scalar_from_source
from ..lib.technical_art_shared import apply_masked_mix, blur_normal_rgb_np, decode_normal_np, emit_masked_grayscale, encode_normal_np


def _id_palette(count: int, mode: str) -> np.ndarray:
    total = max(1, int(count))
    palette_mode = str(mode).lower()
    hues = np.linspace(0.0, 1.0, total, endpoint=False, dtype=np.float32)
    if palette_mode == "id_pastel":
        sat = np.full((total,), 0.36, dtype=np.float32)
        val = np.full((total,), 0.98, dtype=np.float32)
    else:
        sat = np.full((total,), 0.82, dtype=np.float32)
        val = np.full((total,), 0.95, dtype=np.float32)
    return hsv_to_rgb_np(hues, sat, val).astype(np.float32, copy=False)


def _quantized_id_map(
    rgb: np.ndarray,
    levels: int,
    color_space: str,
    palette_mode: str,
    smoothing: float,
) -> tuple[np.ndarray, np.ndarray, int]:
    src = np.clip(rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    if float(max(0.0, smoothing)) > 1e-6:
        src = gaussian_blur_rgb_np(src, radius=float(max(0.0, smoothing)))

    lvl = int(max(2, levels))
    mode = str(color_space).lower()
    if mode == "hsv":
        h, s, v = rgb_to_hsv_np(src)
        hs = lvl
        sv = max(2, int(round(lvl * 0.5)))
        hq = np.floor(np.clip(h * hs, 0.0, hs - 1e-6)).astype(np.int32)
        sq = np.floor(np.clip(s * sv, 0.0, sv - 1e-6)).astype(np.int32)
        vq = np.floor(np.clip(v * sv, 0.0, sv - 1e-6)).astype(np.int32)
        codes = (hq * sv * sv) + (sq * sv) + vq

        if str(palette_mode).lower() == "preserve":
            quant_h = ((hq.astype(np.float32) + 0.5) / float(hs)).astype(np.float32, copy=False)
            quant_s = np.clip((sq.astype(np.float32) + 0.5) / float(sv), 0.0, 1.0).astype(np.float32, copy=False)
            quant_v = np.clip((vq.astype(np.float32) + 0.5) / float(sv), 0.0, 1.0).astype(np.float32, copy=False)
            out = hsv_to_rgb_np(quant_h, quant_s, quant_v).astype(np.float32, copy=False)
        else:
            unique_codes, inverse = np.unique(codes, return_inverse=True)
            palette = _id_palette(len(unique_codes), palette_mode)
            out = palette[inverse.reshape(codes.shape)].astype(np.float32, copy=False)
        region_count = int(np.unique(codes).size)
    else:
        q = np.floor(np.clip(src * lvl, 0.0, lvl - 1e-6)).astype(np.int32)
        codes = (q[..., 0] * lvl * lvl) + (q[..., 1] * lvl) + q[..., 2]

        if str(palette_mode).lower() == "preserve":
            out = (q.astype(np.float32) / float(max(1, lvl - 1))).astype(np.float32, copy=False)
        else:
            unique_codes, inverse = np.unique(codes, return_inverse=True)
            palette = _id_palette(len(unique_codes), palette_mode)
            out = palette[inverse.reshape(codes.shape)].astype(np.float32, copy=False)
        region_count = int(np.unique(codes).size)

    edges = np.zeros(codes.shape, dtype=np.float32)
    edges[:, 1:] = np.maximum(edges[:, 1:], (codes[:, 1:] != codes[:, :-1]).astype(np.float32))
    edges[1:, :] = np.maximum(edges[1:, :], (codes[1:, :] != codes[:-1, :]).astype(np.float32))
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False), edges.astype(np.float32, copy=False), region_count


class x1NormalTweak:
    SEARCH_ALIASES = ["normal tweak", "normal adjust", "flip normal y", "normal convention"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0, "step": 0.01}),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "input_convention": (["opengl", "directx"],),
                "output_convention": (["match_input", "opengl", "directx"],),
                "flip_x": ("BOOLEAN", {"default": False}),
                "flip_y": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "strength_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "normal_tweak_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        strength: float = 1.0,
        blur_radius: float = 0.0,
        input_convention: str = "opengl",
        output_convention: str = "match_input",
        flip_x: bool = False,
        flip_y: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        strength_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.ones((int(b), int(h), int(w)), dtype=np.float32)

        strength_value = float(max(0.0, strength))
        blur_value = float(max(0.0, blur_radius))
        source_convention = str(input_convention).lower()
        target_convention = str(output_convention).lower()
        if target_convention == "match_input":
            target_convention = source_convention

        strength_mask_np = (
            mask_tensor_to_np(strength_mask, int(b), int(h), int(w)) if torch.is_tensor(strength_mask) else None
        )

        no_strength_change = abs(strength_value - 1.0) <= 1e-6
        no_convention_change = target_convention == source_convention
        no_flip = (not bool(flip_x)) and (not bool(flip_y))
        bypass_core = blur_value <= 1e-6 and no_strength_change and no_convention_change and no_flip

        for idx in range(int(b)):
            influence = (
                np.clip(strength_mask_np[idx], 0.0, 1.0).astype(np.float32, copy=False)
                if strength_mask_np is not None
                else np.ones((int(h), int(w)), dtype=np.float32)
            )
            matte_np[idx] = influence

            if bypass_core:
                out_np[idx] = np.clip(src_np[idx][..., :3], 0.0, 1.0)
                continue

            encoded = src_np[idx][..., :3]
            if blur_value > 1e-6:
                encoded = blur_normal_rgb_np(encoded, radius=blur_value)

            # Normalize into an internal OpenGL-style tangent basis before edits.
            normal = decode_normal_np(encoded)
            if source_convention == "directx":
                normal[..., 1] = -normal[..., 1]

            scale = 1.0 + ((strength_value - 1.0) * influence)
            adjusted = normal.copy()
            adjusted[..., 0] = adjusted[..., 0] * scale
            adjusted[..., 1] = adjusted[..., 1] * scale

            if bool(flip_x):
                adjusted[..., 0] = -adjusted[..., 0]
            if bool(flip_y):
                adjusted[..., 1] = -adjusted[..., 1]
            if target_convention == "directx":
                adjusted[..., 1] = -adjusted[..., 1]

            out_np[idx] = encode_normal_np(adjusted)

        out, out_mask, coverage = apply_masked_mix(
            base=batch,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1NormalTweak: strength={:.2f}, blur_radius={:.1f}px, input_convention={}, output_convention={}, "
            "flip_x={}, flip_y={}, strength_mask={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            strength_value,
            blur_value,
            source_convention,
            target_convention,
            bool(flip_x),
            bool(flip_y),
            bool(strength_mask_np is not None),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)


class x1SlopeMaskFromNormal:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["+x", "-x", "+y", "-y", "+z", "-z", "rim"],),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "invert_values": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "slope_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        mode: str = "+z",
        strength: float = 1.0,
        gamma: float = 1.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_mode = str(mode).lower()
        s = float(max(0.0, strength))
        g = float(max(0.1, gamma))

        for idx in range(int(b)):
            normal = decode_normal_np(src_np[idx][..., :3])
            if resolved_mode == "+x":
                raw = np.maximum(normal[..., 0], 0.0)
            elif resolved_mode == "-x":
                raw = np.maximum(-normal[..., 0], 0.0)
            elif resolved_mode == "+y":
                raw = np.maximum(normal[..., 1], 0.0)
            elif resolved_mode == "-y":
                raw = np.maximum(-normal[..., 1], 0.0)
            elif resolved_mode == "-z":
                raw = np.maximum(-normal[..., 2], 0.0)
            elif resolved_mode == "rim":
                raw = np.clip(1.0 - np.maximum(normal[..., 2], 0.0), 0.0, 1.0)
            else:
                raw = np.maximum(normal[..., 2], 0.0)

            scalar = np.clip(raw * s, 0.0, 1.0).astype(np.float32, copy=False)
            if bool(invert_values):
                scalar = 1.0 - scalar
            if abs(g - 1.0) > 1e-6:
                scalar = np.power(np.clip(scalar, 0.0, 1.0), g).astype(np.float32, copy=False)
            matte_np[idx] = scalar

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1SlopeMaskFromNormal: mode={}, strength={:.2f}, gamma={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_mode,
            s,
            g,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1AOFromHeight:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["luma", "red", "green", "blue", "value", "alpha", "mask"],),
                "output_mode": (["ao", "cavity"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": -1.0, "max": 1.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "radius": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 128.0, "step": 0.1}),
                "intensity": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 8.0, "step": 0.01}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "invert_height": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "ao_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "luma",
        output_mode: str = "ao",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        radius: float = 8.0,
        intensity: float = 2.0,
        gamma: float = 1.0,
        invert_height: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        src_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        r = float(max(0.0, radius))
        last_lo = 0.0
        last_hi = 1.0
        resolved_source = str(source_mode).lower()

        for idx in range(int(b)):
            scalar, resolved_source = scalar_from_source(
                src=src_np[idx],
                source_mode=source_mode,
                source_mask_np=src_mask_np[idx] if src_mask_np is not None else None,
                fallback_to_luma=True,
            )
            height, _, _ = normalize_scalar(
                scalar=scalar,
                normalize_mode="auto_range",
                value_min=0.0,
                value_max=1.0,
                percentile_low=0.0,
                percentile_high=100.0,
                gamma=1.0,
                invert_values=invert_height,
            )
            blur_small = blur_single_channel(height, r)
            blur_large = blur_single_channel(height, r * 2.0)
            raw = np.maximum(((blur_small - height) * 0.65) + ((blur_large - height) * 0.35), 0.0) * float(max(0.0, intensity))
            normalized, lo, hi = normalize_scalar(
                scalar=raw.astype(np.float32, copy=False),
                normalize_mode=normalize_mode,
                value_min=value_min,
                value_max=value_max,
                percentile_low=percentile_low,
                percentile_high=percentile_high,
                gamma=gamma,
                invert_values=False,
            )
            matte_np[idx] = (1.0 - normalized) if str(output_mode).lower() == "ao" else normalized
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=np.clip(matte_np, 0.0, 1.0).astype(np.float32, copy=False),
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1AOFromHeight: source={}, output_mode={}, normalize_mode={}, range=[{:.3f},{:.3f}], radius={:.1f}px, "
            "intensity={:.2f}, gamma={:.2f}, invert_height={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_source,
            str(output_mode).lower(),
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            r,
            float(max(0.0, intensity)),
            float(max(0.1, gamma)),
            bool(invert_height),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1IDMapQuantize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "color_space": (["rgb", "hsv"],),
                "levels": ("INT", {"default": 4, "min": 2, "max": 16, "step": 1}),
                "palette_mode": (["id_vivid", "id_pastel", "preserve"],),
                "smoothing": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "edge_softness": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 32.0, "step": 0.1}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "id_map_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        color_space: str = "rgb",
        levels: int = 4,
        palette_mode: str = "id_vivid",
        smoothing: float = 0.0,
        edge_softness: float = 0.5,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        edge_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        region_counts: list[int] = []

        for idx in range(int(b)):
            quantized, edges, region_count = _quantized_id_map(
                rgb=src_np[idx][..., :3],
                levels=int(levels),
                color_space=color_space,
                palette_mode=palette_mode,
                smoothing=float(max(0.0, smoothing)),
            )
            if float(max(0.0, edge_softness)) > 1e-6:
                edges = blur_single_channel(edges, radius=float(max(0.0, edge_softness)))
            out_np[idx] = quantized
            edge_np[idx] = np.clip(edges, 0.0, 1.0)
            region_counts.append(int(region_count))

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
        out_rgb = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        if c == 4:
            out_rgb = torch.cat([out_rgb, batch[..., 3:4]], dim=-1)
        base_mask_t = effect_mask_t.unsqueeze(-1)
        image_out = torch.clamp((batch * (1.0 - base_mask_t)) + (out_rgb * base_mask_t), 0.0, 1.0)
        out_mask = torch.from_numpy(np.clip(edge_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_mask = torch.clamp(out_mask * effect_mask_t, 0.0, 1.0)
        coverage = float(effect_mask_t.mean().item()) * 100.0

        info = (
            "x1IDMapQuantize: color_space={}, levels={}, palette_mode={}, smoothing={:.1f}px, "
            "edge_softness={:.1f}px, regions≈{}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            str(color_space).lower(),
            int(max(2, levels)),
            str(palette_mode).lower(),
            float(max(0.0, smoothing)),
            float(max(0.0, edge_softness)),
            int(max(region_counts) if region_counts else 0),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (image_out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)


class x1IDMaskExtract:
    SEARCH_ALIASES = ["id mask extract", "material id isolate", "pick id color", "id selection mask"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "selection_mode": (["manual_color", "sample_position"],),
                "color_space": (["rgb", "hsv"],),
                "target_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "target_g": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "target_b": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "sample_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "sample_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "tolerance": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 1.0, "step": 0.001}),
                "softness": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 0.5, "step": 0.001}),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "invert_values": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "id_mask_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        selection_mode: str = "manual_color",
        color_space: str = "rgb",
        target_r: float = 1.0,
        target_g: float = 0.0,
        target_b: float = 0.0,
        sample_x: float = 0.5,
        sample_y: float = 0.5,
        tolerance: float = 0.12,
        softness: float = 0.04,
        blur_radius: float = 0.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_selection = str(selection_mode).lower()
        resolved_space = str(color_space).lower()
        tol = float(np.clip(tolerance, 0.0, 1.0))
        soft = float(np.clip(softness, 0.0, 0.5))
        blur_value = float(max(0.0, blur_radius))

        picked_color = np.asarray(
            [np.clip(target_r, 0.0, 1.0), np.clip(target_g, 0.0, 1.0), np.clip(target_b, 0.0, 1.0)],
            dtype=np.float32,
        )
        if resolved_space == "hsv":
            pick_h, pick_s, pick_v = rgb_to_hsv_np(picked_color.reshape(1, 1, 3))
            picked_space = np.asarray([pick_h[0, 0], pick_s[0, 0], pick_v[0, 0]], dtype=np.float32)
        else:
            picked_space = picked_color

        for idx in range(int(b)):
            rgb = np.clip(src_np[idx][..., :3], 0.0, 1.0).astype(np.float32, copy=False)
            if resolved_selection == "sample_position":
                sx = int(round(float(np.clip(sample_x, 0.0, 1.0)) * float(max(1, int(w) - 1))))
                sy = int(round(float(np.clip(sample_y, 0.0, 1.0)) * float(max(1, int(h) - 1))))
                picked_color = rgb[sy, sx].astype(np.float32, copy=False)
                if resolved_space == "hsv":
                    pick_h, pick_s, pick_v = rgb_to_hsv_np(picked_color.reshape(1, 1, 3))
                    picked_space = np.asarray([pick_h[0, 0], pick_s[0, 0], pick_v[0, 0]], dtype=np.float32)
                else:
                    picked_space = picked_color

            if resolved_space == "hsv":
                h_src, s_src, v_src = rgb_to_hsv_np(rgb)
                sample_space = np.stack([h_src, s_src, v_src], axis=-1).astype(np.float32, copy=False)
                hue_delta = np.abs(sample_space[..., 0] - picked_space[0])
                hue_delta = np.minimum(hue_delta, 1.0 - hue_delta)
                delta = np.empty_like(sample_space)
                delta[..., 0] = hue_delta * 2.0
                delta[..., 1] = sample_space[..., 1] - picked_space[1]
                delta[..., 2] = sample_space[..., 2] - picked_space[2]
            else:
                delta = rgb - picked_space[None, None, :]

            distance = np.sqrt(np.sum(delta * delta, axis=-1))
            if soft > 1e-6:
                matte = 1.0 - np.clip((distance - tol) / max(soft, 1e-6), 0.0, 1.0)
            else:
                matte = (distance <= tol).astype(np.float32, copy=False)
            if blur_value > 1e-6:
                matte = blur_single_channel(matte.astype(np.float32, copy=False), blur_value)
            if bool(invert_values):
                matte = 1.0 - matte
            matte_np[idx] = np.clip(matte, 0.0, 1.0).astype(np.float32, copy=False)

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1IDMaskExtract: selection_mode={}, color_space={}, picked=[{:.3f},{:.3f},{:.3f}], "
            "tolerance={:.3f}, softness={:.3f}, blur_radius={:.1f}px, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            resolved_selection,
            resolved_space,
            float(picked_color[0]),
            float(picked_color[1]),
            float(picked_color[2]),
            tol,
            soft,
            blur_value,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
