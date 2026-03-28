import json
from typing import Optional

import numpy as np
import torch

from ..categories import COLOR_FINISH, COLOR_GRADE, FX_PHOTO
from ..lib.image_shared import (
    gaussian_blur_rgb_np,
    luma_np,
    mask_to_batch,
    smoothstep_np,
    to_image_batch,
)
from ..lib.settings_bundle import parse_settings_payload


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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "threshold": 0.72,
            "softness": 0.10,
            "recovery": 0.72,
            "chroma_preserve": 0.60,
            "desaturate_clips": 0.18,
            "mix": 1.0,
            "mask_feather": 12.0,
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
    RETURN_NAMES = ("image", "mask", "highlight_recovery_info")
    FUNCTION = "run"
    CATEGORY = COLOR_FINISH

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
                "threshold": {"min": 0.0, "max": 1.0},
                "softness": {"min": 0.0, "max": 0.5},
                "recovery": {"min": 0.0, "max": 1.0},
                "chroma_preserve": {"min": 0.0, "max": 1.0},
                "desaturate_clips": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        threshold = float(settings["threshold"])
        softness = float(settings["softness"])
        recovery = float(settings["recovery"])
        chroma_preserve = float(settings["chroma_preserve"])
        desaturate_clips = float(settings["desaturate_clips"])
        mix = float(settings["mix"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])
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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "radius": 28.0,
            "amount": 0.55,
            "shadow_weight": 0.70,
            "highlight_weight": 0.55,
            "midtone_boost": 0.70,
            "preserve_luma": True,
            "mix": 1.0,
            "mask_feather": 12.0,
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
    RETURN_NAMES = ("image", "mask", "local_contrast_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

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
                "radius": {"min": 1.0, "max": 256.0},
                "amount": {"min": -1.0, "max": 2.0},
                "shadow_weight": {"min": 0.0, "max": 2.0},
                "highlight_weight": {"min": 0.0, "max": 2.0},
                "midtone_boost": {"min": 0.0, "max": 2.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"preserve_luma", "invert_mask"},
            legacy=legacy_settings,
        )
        radius = float(settings["radius"])
        amount = float(settings["amount"])
        shadow_weight = float(settings["shadow_weight"])
        highlight_weight = float(settings["highlight_weight"])
        midtone_boost = float(settings["midtone_boost"])
        preserve_luma = bool(settings["preserve_luma"])
        mix = float(settings["mix"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])
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
    @staticmethod
    def _default_settings() -> dict:
        return {
            "mode": "unsharp",
            "radius": 1.6,
            "amount": 1.05,
            "threshold": 0.015,
            "halo_suppress": 0.40,
            "luma_only": True,
            "mix": 1.0,
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
    RETURN_NAMES = ("image", "mask", "sharpen_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

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
                "radius": {"min": 0.1, "max": 32.0},
                "amount": {"min": 0.0, "max": 4.0},
                "threshold": {"min": 0.0, "max": 0.2},
                "halo_suppress": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"luma_only", "invert_mask"},
            legacy=legacy_settings,
        )
        mode = str(settings["mode"])
        radius = float(settings["radius"])
        amount = float(settings["amount"])
        threshold = float(settings["threshold"])
        halo_suppress = float(settings["halo_suppress"])
        luma_only = bool(settings["luma_only"])
        mix = float(settings["mix"])
        mask_feather = float(settings["mask_feather"])
        invert_mask = bool(settings["invert_mask"])
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
