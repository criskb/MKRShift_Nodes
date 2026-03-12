from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_TECH_ART
from ..lib.image_shared import luma_np, to_image_batch
from ..lib.scalar_map_shared import normalize_scalar
from ..lib.technical_art_shared import (
    apply_masked_mix,
    blur_normal_rgb_np,
    channel_to_grayscale_image,
    decode_normal_np,
    emit_masked_grayscale,
    encode_normal_np,
    infer_reference_shape,
    mask_or_gray_input,
    match_image_batch,
)


def _checker_palette(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    palette = str(name).lower()
    if palette == "neutral":
        return (
            np.asarray([0.84, 0.84, 0.82], dtype=np.float32),
            np.asarray([0.22, 0.22, 0.24], dtype=np.float32),
            np.asarray([0.94, 0.38, 0.06], dtype=np.float32),
        )
    if palette == "mono":
        return (
            np.asarray([0.88, 0.88, 0.88], dtype=np.float32),
            np.asarray([0.12, 0.12, 0.12], dtype=np.float32),
            np.asarray([0.50, 0.50, 0.50], dtype=np.float32),
        )
    return (
        np.asarray([0.16, 0.72, 0.88], dtype=np.float32),
        np.asarray([0.96, 0.22, 0.48], dtype=np.float32),
        np.asarray([1.00, 0.88, 0.14], dtype=np.float32),
    )


def _checker_pattern(h: int, w: int, cells_x: int, cells_y: int, palette: str, invert: bool, line_width: float) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:int(h), 0:int(w)].astype(np.float32)
    cell_w = max(1.0, float(w) / float(max(1, int(cells_x))))
    cell_h = max(1.0, float(h) / float(max(1, int(cells_y))))

    checker = ((np.floor(xx / cell_w) + np.floor(yy / cell_h)) % 2.0).astype(np.float32, copy=False)
    line_px = float(max(0.0, line_width))
    frac_x = np.mod(xx, cell_w)
    frac_y = np.mod(yy, cell_h)
    line_mask = (
        (frac_x <= line_px)
        | (frac_x >= (cell_w - line_px))
        | (frac_y <= line_px)
        | (frac_y >= (cell_h - line_px))
    ).astype(np.float32, copy=False)

    color_a, color_b, line_color = _checker_palette(palette)
    if bool(invert):
        color_a, color_b = color_b, color_a
    out = (color_a[None, None, :] * (1.0 - checker[..., None])) + (color_b[None, None, :] * checker[..., None])
    out = np.clip((out * (1.0 - line_mask[..., None])) + (line_color[None, None, :] * line_mask[..., None]), 0.0, 1.0)
    return out.astype(np.float32, copy=False), line_mask.astype(np.float32, copy=False)


class x1ChannelPack:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "output_mode": (["rgb", "rgba"],),
                "fill_missing": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
            },
            "optional": {
                "red_image": ("IMAGE",),
                "green_image": ("IMAGE",),
                "blue_image": ("IMAGE",),
                "alpha_image": ("IMAGE",),
                "red_mask": ("MASK",),
                "green_mask": ("MASK",),
                "blue_mask": ("MASK",),
                "alpha_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "packing_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        output_mode: str = "rgb",
        fill_missing: float = 0.0,
        red_image: Optional[torch.Tensor] = None,
        green_image: Optional[torch.Tensor] = None,
        blue_image: Optional[torch.Tensor] = None,
        alpha_image: Optional[torch.Tensor] = None,
        red_mask: Optional[torch.Tensor] = None,
        green_mask: Optional[torch.Tensor] = None,
        blue_mask: Optional[torch.Tensor] = None,
        alpha_mask: Optional[torch.Tensor] = None,
    ):
        batch, h, w = infer_reference_shape(
            red_image,
            green_image,
            blue_image,
            alpha_image,
            red_mask,
            green_mask,
            blue_mask,
            alpha_mask,
        )

        red_np, red_src = mask_or_gray_input(red_image, red_mask, batch=batch, h=h, w=w, fill_value=fill_missing)
        green_np, green_src = mask_or_gray_input(green_image, green_mask, batch=batch, h=h, w=w, fill_value=fill_missing)
        blue_np, blue_src = mask_or_gray_input(blue_image, blue_mask, batch=batch, h=h, w=w, fill_value=fill_missing)
        alpha_np, alpha_src = mask_or_gray_input(alpha_image, alpha_mask, batch=batch, h=h, w=w, fill_value=1.0)

        channels = [red_np, green_np, blue_np]
        if str(output_mode).lower() == "rgba":
            channels.append(alpha_np)
        packed = np.stack(channels, axis=-1).astype(np.float32, copy=False)

        info = (
            "x1ChannelPack: mode={}, sources=[R:{}, G:{}, B:{}, A:{}], fill_missing={:.3f}"
        ).format(
            str(output_mode).lower(),
            red_src,
            green_src,
            blue_src,
            alpha_src if str(output_mode).lower() == "rgba" else "not_used",
            float(np.clip(fill_missing, 0.0, 1.0)),
        )
        return (torch.from_numpy(packed), info)


class x1ChannelBreakout:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "alpha_fallback": (["zero", "one", "luma"],),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "IMAGE", "MASK", "MASK", "MASK", "MASK", "STRING")
    RETURN_NAMES = (
        "red_image",
        "green_image",
        "blue_image",
        "alpha_image",
        "red_mask",
        "green_mask",
        "blue_mask",
        "alpha_mask",
        "breakout_info",
    )
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(self, image: torch.Tensor, alpha_fallback: str = "zero"):
        batch = to_image_batch(image)
        src = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        red = src[..., 0].astype(np.float32, copy=False)
        green = src[..., 1].astype(np.float32, copy=False)
        blue = src[..., 2].astype(np.float32, copy=False)

        resolved_alpha = "alpha"
        if src.shape[-1] >= 4:
            alpha = src[..., 3].astype(np.float32, copy=False)
        elif str(alpha_fallback).lower() == "one":
            alpha = np.ones_like(red, dtype=np.float32)
            resolved_alpha = "one"
        elif str(alpha_fallback).lower() == "luma":
            alpha = np.stack([luma_np(sample[..., :3]) for sample in src], axis=0).astype(np.float32, copy=False)
            resolved_alpha = "luma"
        else:
            alpha = np.zeros_like(red, dtype=np.float32)
            resolved_alpha = "zero"

        info = "x1ChannelBreakout: channels=RGB{}, alpha_fallback={}".format(
            "A" if src.shape[-1] >= 4 else "",
            resolved_alpha,
        )
        return (
            channel_to_grayscale_image(red, batch.device, batch.dtype),
            channel_to_grayscale_image(green, batch.device, batch.dtype),
            channel_to_grayscale_image(blue, batch.device, batch.dtype),
            channel_to_grayscale_image(alpha, batch.device, batch.dtype),
            torch.from_numpy(red).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(green).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(blue).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(alpha).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1NormalBlend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_normal": ("IMAGE",),
                "detail_normal": ("IMAGE",),
                "blend_mode": (["whiteout", "add", "lerp"],),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "normal_blend_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        base_normal: torch.Tensor,
        detail_normal: torch.Tensor,
        blend_mode: str = "whiteout",
        strength: float = 1.0,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        base_batch = to_image_batch(base_normal)
        b, h, w, c = base_batch.shape
        detail_batch = match_image_batch(detail_normal, batch=int(b), h=int(h), w=int(w))

        base_np = base_batch.detach().cpu().numpy().astype(np.float32, copy=False)
        detail_np = detail_batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.ones((int(b), int(h), int(w)), dtype=np.float32)
        s = float(max(0.0, strength))

        for idx in range(int(b)):
            base_dec = decode_normal_np(base_np[idx][..., :3])
            detail_dec = decode_normal_np(detail_np[idx][..., :3])
            detail_weighted = np.empty_like(detail_dec)
            detail_weighted[..., 0:2] = detail_dec[..., 0:2] * s
            detail_weighted[..., 2] = 1.0 - ((1.0 - detail_dec[..., 2]) * min(1.0, s))

            mode = str(blend_mode).lower()
            if mode == "add":
                blended = np.stack(
                    [
                        base_dec[..., 0] + detail_weighted[..., 0],
                        base_dec[..., 1] + detail_weighted[..., 1],
                        base_dec[..., 2],
                    ],
                    axis=-1,
                )
            elif mode == "lerp":
                target = decode_normal_np(encode_normal_np(detail_weighted))
                mix = np.clip(s / max(1.0, s), 0.0, 1.0)
                blended = (base_dec * (1.0 - mix)) + (target * mix)
            else:
                blended = np.stack(
                    [
                        base_dec[..., 0] + detail_weighted[..., 0],
                        base_dec[..., 1] + detail_weighted[..., 1],
                        base_dec[..., 2] * detail_weighted[..., 2],
                    ],
                    axis=-1,
                )
            out_np[idx] = encode_normal_np(blended)

        out, out_mask, coverage = apply_masked_mix(
            base=base_batch,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        if c == 4:
            out = torch.cat([out[..., :3], base_batch[..., 3:4]], dim=-1)

        info = (
            "x1NormalBlend: mode={}, strength={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            str(blend_mode).lower(),
            s,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)


class x1CurvatureFromNormal:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["combined", "convex", "concave"],),
                "normalize_mode": (["auto_percentile", "manual_range", "auto_range"],),
                "value_min": ("FLOAT", {"default": 0.0, "min": -4.0, "max": 4.0, "step": 0.001}),
                "value_max": ("FLOAT", {"default": 1.0, "min": -4.0, "max": 4.0, "step": 0.001}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "blur_radius": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "strength": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 16.0, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "curvature_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        mode: str = "combined",
        normalize_mode: str = "auto_percentile",
        value_min: float = 0.0,
        value_max: float = 1.0,
        percentile_low: float = 2.0,
        percentile_high: float = 98.0,
        blur_radius: float = 1.0,
        strength: float = 2.0,
        gamma: float = 1.0,
        invert_values: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        s = float(max(0.0, strength))
        last_lo = 0.0
        last_hi = 1.0

        for idx in range(int(b)):
            blurred = blur_normal_rgb_np(src_np[idx][..., :3], radius=float(max(0.0, blur_radius)))
            normal = decode_normal_np(blurred)
            dnx_dy, dnx_dx = np.gradient(normal[..., 0])
            dny_dy, dny_dx = np.gradient(normal[..., 1])
            raw = (dnx_dx + dny_dy) * s

            resolved = str(mode).lower()
            if resolved == "convex":
                scalar = np.maximum(raw, 0.0).astype(np.float32, copy=False)
            elif resolved == "concave":
                scalar = np.maximum(-raw, 0.0).astype(np.float32, copy=False)
            else:
                scalar = np.abs(raw).astype(np.float32, copy=False)

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
            matte_np[idx] = normalized
            out_np[idx] = np.repeat(normalized[..., None], 3, axis=-1).astype(np.float32, copy=False)
            last_lo = lo
            last_hi = hi

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )

        info = (
            "x1CurvatureFromNormal: mode={}, normalize_mode={}, range=[{:.3f},{:.3f}], blur_radius={:.1f}px, "
            "strength={:.2f}, gamma={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            str(mode).lower(),
            str(normalize_mode).lower(),
            last_lo,
            last_hi,
            float(max(0.0, blur_radius)),
            s,
            float(max(0.1, gamma)),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)


class x1UVCheckerOverlay:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["overlay", "generate"],),
                "palette": (["uv", "neutral", "mono"],),
                "cells_x": ("INT", {"default": 8, "min": 1, "max": 128, "step": 1}),
                "cells_y": ("INT", {"default": 8, "min": 1, "max": 128, "step": 1}),
                "line_width": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.1}),
                "mix": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                "invert_pattern": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "checker_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TECH_ART

    def run(
        self,
        image: torch.Tensor,
        mode: str = "overlay",
        palette: str = "uv",
        cells_x: int = 8,
        cells_y: int = 8,
        line_width: float = 1.0,
        mix: float = 0.75,
        invert_pattern: bool = False,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty((int(b), int(h), int(w), 3), dtype=np.float32)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        pattern, lines = _checker_pattern(
            h=int(h),
            w=int(w),
            cells_x=int(max(1, cells_x)),
            cells_y=int(max(1, cells_y)),
            palette=palette,
            invert=bool(invert_pattern),
            line_width=float(max(0.0, line_width)),
        )
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            if str(mode).lower() == "generate":
                out_np[idx] = pattern
            else:
                out_np[idx] = np.clip((src_np[idx][..., :3] * (1.0 - m)) + (pattern * m), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.full((int(h), int(w)), m, dtype=np.float32)

        out, out_mask, coverage = apply_masked_mix(
            base=batch,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        line_mask = torch.from_numpy(np.repeat(lines[None, ...], int(b), axis=0)).to(device=batch.device, dtype=batch.dtype)
        out_mask = torch.clamp(out_mask * line_mask, 0.0, 1.0)
        if c == 4:
            out = torch.cat([out[..., :3], batch[..., 3:4]], dim=-1)

        info = (
            "x1UVCheckerOverlay: mode={}, palette={}, cells={}x{}, line_width={:.1f}px, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            str(mode).lower(),
            str(palette).lower(),
            int(max(1, cells_x)),
            int(max(1, cells_y)),
            float(max(0.0, line_width)),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), out_mask.clamp(0.0, 1.0), info)
