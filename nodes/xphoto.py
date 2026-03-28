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


class x1VignettePro:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "amount": 0.42,
            "midpoint": 0.58,
            "feather": 0.24,
            "roundness": 0.78,
            "center_x": 0.50,
            "center_y": 0.50,
            "highlight_protect": 0.35,
            "saturation_shift": -0.06,
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
    RETURN_NAMES = ("image", "mask", "vignette_info")
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
                "amount": {"min": -1.0, "max": 1.0},
                "midpoint": {"min": 0.0, "max": 1.0},
                "feather": {"min": 0.0, "max": 1.0},
                "roundness": {"min": 0.1, "max": 1.5},
                "center_x": {"min": 0.0, "max": 1.0},
                "center_y": {"min": 0.0, "max": 1.0},
                "highlight_protect": {"min": 0.0, "max": 1.0},
                "saturation_shift": {"min": -1.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        amount = float(np.clip(settings["amount"], -1.0, 1.0))
        midpoint = float(np.clip(settings["midpoint"], 0.0, 1.0))
        feather = float(np.clip(settings["feather"], 0.0, 1.0))
        roundness = float(np.clip(settings["roundness"], 0.1, 1.5))
        center_x = float(np.clip(settings["center_x"], 0.0, 1.0))
        center_y = float(np.clip(settings["center_y"], 0.0, 1.0))
        highlight_protect = float(np.clip(settings["highlight_protect"], 0.0, 1.0))
        saturation_shift = float(np.clip(settings["saturation_shift"], -1.0, 1.0))
        mix = float(np.clip(settings["mix"], 0.0, 1.0))
        mask_feather = float(max(0.0, settings["mask_feather"]))
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        x = np.linspace(0.0, 1.0, int(w), dtype=np.float32)
        y = np.linspace(0.0, 1.0, int(h), dtype=np.float32)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        dx = (xx - center_x) / max(1e-4, roundness)
        dy = yy - center_y
        radius = np.sqrt((dx * dx) + (dy * dy)).astype(np.float32, copy=False)
        midpoint_edge = max(0.01, midpoint)
        feather_edge = max(0.001, feather * 0.85 + 0.001)
        vignette = smoothstep_np(midpoint_edge - feather_edge, midpoint_edge + feather_edge, radius).astype(np.float32, copy=False)
        vignette = np.clip(vignette, 0.0, 1.0)

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            protect = 1.0 - (smoothstep_np(0.55, 0.95, lum) * highlight_protect)
            effect = np.clip(vignette * protect, 0.0, 1.0).astype(np.float32, copy=False)

            if amount >= 0.0:
                graded = src * (1.0 - (effect[..., None] * amount))
            else:
                graded = src + ((1.0 - src) * effect[..., None] * abs(amount))

            if abs(saturation_shift) > 1e-6:
                gray = lum[..., None]
                sat_mix = np.clip(saturation_shift * effect[..., None], -1.0, 1.0)
                if saturation_shift >= 0.0:
                    graded = np.clip(graded + ((graded - gray) * sat_mix), 0.0, 1.0)
                else:
                    graded = np.clip((graded * (1.0 + sat_mix)) + (gray * -sat_mix), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - mix)) + (graded * mix), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(effect * mix, 0.0, 1.0).astype(np.float32, copy=False)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1VignettePro: amount={:.2f}, midpoint={:.2f}, feather={:.2f}, roundness={:.2f}, "
            "center=({:.2f},{:.2f}), highlight_protect={:.2f}, saturation_shift={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            amount,
            midpoint,
            feather,
            roundness,
            center_x,
            center_y,
            highlight_protect,
            saturation_shift,
            mix,
            mask_feather,
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1OrtonGlow:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "blur_radius": 18.0,
            "glow_strength": 0.52,
            "contrast_softness": 0.22,
            "detail_preserve": 0.48,
            "highlight_bias": 0.34,
            "black_lift": 0.05,
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
    RETURN_NAMES = ("image", "mask", "orton_info")
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
                "blur_radius": {"min": 0.0, "max": 128.0},
                "glow_strength": {"min": 0.0, "max": 2.0},
                "contrast_softness": {"min": 0.0, "max": 1.0},
                "detail_preserve": {"min": 0.0, "max": 1.0},
                "highlight_bias": {"min": 0.0, "max": 1.0},
                "black_lift": {"min": 0.0, "max": 0.5},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        blur_radius = float(max(0.0, settings["blur_radius"]))
        glow_strength = float(np.clip(settings["glow_strength"], 0.0, 2.0))
        contrast_softness = float(np.clip(settings["contrast_softness"], 0.0, 1.0))
        detail_preserve = float(np.clip(settings["detail_preserve"], 0.0, 1.0))
        highlight_bias = float(np.clip(settings["highlight_bias"], 0.0, 1.0))
        black_lift = float(np.clip(settings["black_lift"], 0.0, 0.5))
        mix = float(np.clip(settings["mix"], 0.0, 1.0))
        mask_feather = float(max(0.0, settings["mask_feather"]))
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            blur = gaussian_blur_rgb_np(src, radius=max(0.5, blur_radius))
            screen = 1.0 - ((1.0 - src) * (1.0 - blur))
            base_glow = np.clip((src * (1.0 - glow_strength * 0.35)) + (screen * glow_strength * 0.85), 0.0, 1.0)

            hi_gate = smoothstep_np(0.42 - (highlight_bias * 0.18), 0.82 - (highlight_bias * 0.08), lum)
            low_gate = 1.0 - smoothstep_np(0.10, 0.48, lum)
            soft = gaussian_blur_rgb_np(base_glow, radius=max(0.4, blur_radius * 0.22))
            contrast_mix = np.clip(contrast_softness, 0.0, 1.0)
            detail_mix = np.clip(detail_preserve, 0.0, 1.0)

            dreamy = np.clip((base_glow * (1.0 - contrast_mix)) + (soft * contrast_mix), 0.0, 1.0)
            dreamy = np.clip(dreamy + (black_lift * low_gate[..., None]), 0.0, 1.0)
            preserve = np.clip((src * detail_mix) + (dreamy * (1.0 - detail_mix)), 0.0, 1.0)
            effect = np.clip(0.25 + (hi_gate * 0.75), 0.0, 1.0).astype(np.float32, copy=False)

            out_np[idx] = np.clip((src * (1.0 - effect[..., None])) + (preserve * effect[..., None]), 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )
            out_np[idx] = np.clip((src * (1.0 - mix)) + (out_np[idx] * mix), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(effect * mix, 0.0, 1.0).astype(np.float32, copy=False)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1OrtonGlow: blur_radius={:.1f}px, glow_strength={:.2f}, contrast_softness={:.2f}, "
            "detail_preserve={:.2f}, highlight_bias={:.2f}, black_lift={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            blur_radius,
            glow_strength,
            contrast_softness,
            detail_preserve,
            highlight_bias,
            black_lift,
            mix,
            mask_feather,
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1FlashPop:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "amount": 0.56,
            "edge_falloff": 0.46,
            "center_x": 0.50,
            "center_y": 0.50,
            "shadow_lift": 0.34,
            "highlight_rolloff": 0.22,
            "warmth": 0.08,
            "clarity": 0.18,
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
    RETURN_NAMES = ("image", "mask", "flash_pop_info")
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
                "amount": {"min": 0.0, "max": 1.0},
                "edge_falloff": {"min": 0.05, "max": 1.0},
                "center_x": {"min": 0.0, "max": 1.0},
                "center_y": {"min": 0.0, "max": 1.0},
                "shadow_lift": {"min": 0.0, "max": 1.0},
                "highlight_rolloff": {"min": 0.0, "max": 1.0},
                "warmth": {"min": -1.0, "max": 1.0},
                "clarity": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        amount = float(np.clip(settings["amount"], 0.0, 1.0))
        edge_falloff = float(np.clip(settings["edge_falloff"], 0.05, 1.0))
        center_x = float(np.clip(settings["center_x"], 0.0, 1.0))
        center_y = float(np.clip(settings["center_y"], 0.0, 1.0))
        shadow_lift = float(np.clip(settings["shadow_lift"], 0.0, 1.0))
        highlight_rolloff = float(np.clip(settings["highlight_rolloff"], 0.0, 1.0))
        warmth = float(np.clip(settings["warmth"], -1.0, 1.0))
        clarity = float(np.clip(settings["clarity"], 0.0, 1.0))
        mix = float(np.clip(settings["mix"], 0.0, 1.0))
        mask_feather = float(max(0.0, settings["mask_feather"]))
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        x = np.linspace(0.0, 1.0, int(w), dtype=np.float32)
        y = np.linspace(0.0, 1.0, int(h), dtype=np.float32)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        radius = np.sqrt(((xx - center_x) ** 2) + ((yy - center_y) ** 2)).astype(np.float32, copy=False)
        start = max(0.02, edge_falloff * 0.28)
        end = min(1.25, edge_falloff * 1.08 + 0.08)
        flash_shape = (1.0 - smoothstep_np(start, end, radius)).astype(np.float32, copy=False)
        flash_shape = np.clip(flash_shape, 0.0, 1.0)

        tint = np.asarray(
            [
                1.0 + (warmth * 0.16),
                1.0 + (warmth * 0.04),
                1.0 - (warmth * 0.16),
            ],
            dtype=np.float32,
        )

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            protected_luma = lum / (1.0 + (highlight_rolloff * lum * 1.8))
            lift = (1.0 - protected_luma) * shadow_lift * flash_shape * amount
            flashed = np.clip(src + lift[..., None], 0.0, 1.0).astype(np.float32, copy=False)
            flashed = np.clip(flashed * tint[None, None, :], 0.0, 1.0).astype(np.float32, copy=False)

            if clarity > 1e-6:
                blur = gaussian_blur_rgb_np(flashed, radius=2.6)
                detail = flashed - blur
                flashed = np.clip(flashed + (detail * clarity * flash_shape[..., None] * 0.75), 0.0, 1.0).astype(
                    np.float32,
                    copy=False,
                )

            out_np[idx] = flashed
            matte_np[idx] = np.clip(flash_shape * amount * mix, 0.0, 1.0).astype(np.float32, copy=False)

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1FlashPop: amount={:.2f}, edge_falloff={:.2f}, center=({:.2f},{:.2f}), shadow_lift={:.2f}, "
            "highlight_rolloff={:.2f}, warmth={:.2f}, clarity={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            amount,
            edge_falloff,
            center_x,
            center_y,
            shadow_lift,
            highlight_rolloff,
            warmth,
            clarity,
            mix,
            mask_feather,
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1PhotoMatte:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "black_lift": 0.10,
            "white_compress": 0.14,
            "contrast_softness": 0.22,
            "saturation_soften": 0.14,
            "warmth": 0.04,
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
    RETURN_NAMES = ("image", "mask", "photo_matte_info")
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
                "black_lift": {"min": 0.0, "max": 0.5},
                "white_compress": {"min": 0.0, "max": 0.5},
                "contrast_softness": {"min": 0.0, "max": 1.0},
                "saturation_soften": {"min": 0.0, "max": 1.0},
                "warmth": {"min": -1.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        black_lift = float(np.clip(settings["black_lift"], 0.0, 0.5))
        white_compress = float(np.clip(settings["white_compress"], 0.0, 0.5))
        contrast_softness = float(np.clip(settings["contrast_softness"], 0.0, 1.0))
        saturation_soften = float(np.clip(settings["saturation_soften"], 0.0, 1.0))
        warmth = float(np.clip(settings["warmth"], -1.0, 1.0))
        mix = float(np.clip(settings["mix"], 0.0, 1.0))
        mask_feather = float(max(0.0, settings["mask_feather"]))
        invert_mask = bool(settings["invert_mask"])

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        tint = np.asarray(
            [
                1.0 + (warmth * 0.10),
                1.0 + (warmth * 0.03),
                1.0 - (warmth * 0.10),
            ],
            dtype=np.float32,
        )

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            lifted = lum + ((1.0 - lum) * black_lift)
            compressed = lifted - (smoothstep_np(0.55, 1.0, lifted) * white_compress * 0.42)
            flattened = np.clip(((compressed - 0.5) * (1.0 - (contrast_softness * 0.72))) + 0.5, 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )

            scale = flattened / np.maximum(lum, 1e-6)
            graded = np.clip(src * scale[..., None], 0.0, 1.0).astype(np.float32, copy=False)
            gray = flattened[..., None]
            if saturation_soften > 1e-6:
                graded = np.clip((graded * (1.0 - saturation_soften)) + (gray * saturation_soften), 0.0, 1.0).astype(
                    np.float32,
                    copy=False,
                )

            graded = np.clip(graded * tint[None, None, :], 0.0, 1.0).astype(np.float32, copy=False)
            out_np[idx] = graded
            matte_np[idx] = np.clip(np.mean(np.abs(graded - src), axis=-1) * 6.0 * mix, 0.0, 1.0).astype(
                np.float32,
                copy=False,
            )

        out, out_mask, coverage = _apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1PhotoMatte: black_lift={:.2f}, white_compress={:.2f}, contrast_softness={:.2f}, "
            "saturation_soften={:.2f}, warmth={:.2f}, mix={:.2f}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            black_lift,
            white_compress,
            contrast_softness,
            saturation_soften,
            warmth,
            mix,
            mask_feather,
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
