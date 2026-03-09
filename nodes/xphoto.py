from typing import Optional

import numpy as np
import torch

from ..categories import COLOR_GRADE, COLOR_TOOLS, FX_PHOTO
from ..lib.image_shared import (
    gaussian_blur_rgb_np,
    luma_np,
    mask_to_batch,
    smoothstep_np,
    to_image_batch,
)


def _apply_masked_output(
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


class x1HighlightRecovery:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "recovery": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "chroma_preserve": ("FLOAT", {"default": 0.60, "min": 0.0, "max": 1.0, "step": 0.01}),
                "desaturate_clips": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "highlight_recovery_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        threshold: float = 0.72,
        softness: float = 0.10,
        recovery: float = 0.72,
        chroma_preserve: float = 0.60,
        desaturate_clips: float = 0.18,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        thr = float(np.clip(threshold, 0.0, 1.0))
        soft = float(max(0.0, softness))
        rec = float(np.clip(recovery, 0.0, 1.0))
        chroma_keep = float(np.clip(chroma_preserve, 0.0, 1.0))
        de_sat = float(np.clip(desaturate_clips, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            hi = smoothstep_np(thr - soft, thr + soft, lum)
            over = np.maximum(lum - thr, 0.0)
            comp = over / (1.0 + (rec * 10.0 * over / max(1e-6, 1.0 - thr)))
            target_l = lum - over + comp

            norm = src / np.maximum(lum[..., None], 1e-6)
            norm = norm / np.maximum(np.max(norm, axis=-1, keepdims=True), 1e-6)
            color_rebuild = np.clip(norm * target_l[..., None], 0.0, 1.0)
            scalar_rebuild = np.clip(src * (target_l[..., None] / np.maximum(lum[..., None], 1e-6)), 0.0, 1.0)
            rebuilt = np.clip(
                (scalar_rebuild * (1.0 - chroma_keep)) + (color_rebuild * chroma_keep),
                0.0,
                1.0,
            )

            if de_sat > 1e-6:
                gray = target_l[..., None]
                rebuilt = np.clip((rebuilt * (1.0 - (de_sat * hi[..., None]))) + (gray * (de_sat * hi[..., None])), 0.0, 1.0)

            local_mix = hi[..., None] * m
            out_np[idx] = np.clip((src * (1.0 - local_mix)) + (rebuilt * local_mix), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(hi * m, 0.0, 1.0)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1HighlightRecovery: threshold={:.2f}, softness={:.3f}, recovery={:.2f}, "
            "chroma_preserve={:.2f}, desaturate_clips={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            thr,
            soft,
            rec,
            chroma_keep,
            de_sat,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1LocalContrast:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "radius": ("FLOAT", {"default": 28.0, "min": 1.0, "max": 256.0, "step": 0.5}),
                "amount": ("FLOAT", {"default": 0.55, "min": -1.0, "max": 2.0, "step": 0.01}),
                "shadow_weight": ("FLOAT", {"default": 0.70, "min": 0.0, "max": 2.0, "step": 0.01}),
                "highlight_weight": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 2.0, "step": 0.01}),
                "midtone_boost": ("FLOAT", {"default": 0.70, "min": 0.0, "max": 2.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": True}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "local_contrast_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        radius: float = 28.0,
        amount: float = 0.55,
        shadow_weight: float = 0.70,
        highlight_weight: float = 0.55,
        midtone_boost: float = 0.70,
        preserve_luma: bool = True,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        rad = float(max(1.0, radius))
        amt = float(np.clip(amount, -1.0, 2.0))
        sh_w = float(max(0.0, shadow_weight))
        hi_w = float(max(0.0, highlight_weight))
        mid_w = float(max(0.0, midtone_boost))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            base = gaussian_blur_rgb_np(src, radius=rad)
            base_l = luma_np(base)
            detail = lum - base_l

            sh = 1.0 - smoothstep_np(0.20, 0.55, lum)
            hi = smoothstep_np(0.45, 0.82, lum)
            mid = 1.0 - np.clip(sh + hi, 0.0, 1.0)
            weight = (sh * sh_w) + (hi * hi_w) + (mid * mid_w)
            weight = np.clip(weight, 0.0, 2.5).astype(np.float32, copy=False)

            out_l = np.clip(lum + (detail * amt * weight), 0.0, 1.0)
            if preserve_luma:
                scale = out_l / np.maximum(lum, 1e-6)
                graded = np.clip(src * scale[..., None], 0.0, 1.0)
            else:
                delta = (out_l - lum)[..., None]
                graded = np.clip(src + delta, 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (graded * m), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.full((int(h), int(w)), m, dtype=np.float32)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1LocalContrast: radius={:.1f}px, amount={:.2f}, weights(sh={:.2f},mid={:.2f},hi={:.2f}), "
            "preserve_luma={}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            rad,
            amt,
            sh_w,
            mid_w,
            hi_w,
            bool(preserve_luma),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1SharpenPro:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["unsharp", "highpass"],),
                "radius": ("FLOAT", {"default": 1.6, "min": 0.1, "max": 32.0, "step": 0.1}),
                "amount": ("FLOAT", {"default": 1.05, "min": 0.0, "max": 4.0, "step": 0.01}),
                "threshold": ("FLOAT", {"default": 0.015, "min": 0.0, "max": 0.2, "step": 0.001}),
                "halo_suppress": ("FLOAT", {"default": 0.40, "min": 0.0, "max": 1.0, "step": 0.01}),
                "luma_only": ("BOOLEAN", {"default": True}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "sharpen_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        mode: str = "unsharp",
        radius: float = 1.6,
        amount: float = 1.05,
        threshold: float = 0.015,
        halo_suppress: float = 0.40,
        luma_only: bool = True,
        mix: float = 1.0,
        mask_feather: float = 8.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        mode_key = str(mode).lower()
        if mode_key not in {"unsharp", "highpass"}:
            mode_key = "unsharp"

        rad = float(max(0.1, radius))
        amt = float(max(0.0, amount))
        thr = float(np.clip(threshold, 0.0, 0.2))
        halo = float(np.clip(halo_suppress, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            blurred = gaussian_blur_rgb_np(src, radius=rad)
            high = src - blurred
            edge = np.mean(np.abs(high), axis=-1)
            edge_gate = smoothstep_np(thr, thr + max(0.004, thr * 1.8 + 0.004), edge)

            clip_scale = 1.0 - (0.85 * halo)
            high = np.clip(high, -clip_scale, clip_scale).astype(np.float32, copy=False)

            if mode_key == "highpass":
                hp = np.clip((high * 0.5) + 0.5, 0.0, 1.0)
                sharpened = np.clip(src + ((hp - 0.5) * 2.0 * amt * edge_gate[..., None]), 0.0, 1.0)
            else:
                sharpened = np.clip(src + (high * amt * edge_gate[..., None]), 0.0, 1.0)

            if bool(luma_only):
                src_l = luma_np(src)
                shp_l = luma_np(sharpened)
                scale = shp_l / np.maximum(src_l, 1e-6)
                sharpened = np.clip(src * scale[..., None], 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (sharpened * m), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(edge_gate * m, 0.0, 1.0).astype(np.float32, copy=False)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1SharpenPro: mode={}, radius={:.2f}px, amount={:.2f}, threshold={:.3f}, halo_suppress={:.2f}, "
            "luma_only={}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            mode_key,
            rad,
            amt,
            thr,
            halo,
            bool(luma_only),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
