import math
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import torch
import torch.nn.functional as F

from ..categories import COLOR_LUT, COLOR_TOOLS, FX_CONCEPT, FX_PHOTO, FX_STYLIZE
from ..lib.image_shared import (
    gaussian_blur_rgb_np as _gaussian_blur_rgb_np,
    hsv_to_rgb_np as _hsv_to_rgb_np,
    luma_np as _luma,
    mask_to_batch as _mask_to_batch,
    resize_rgb_np as _resize_rgb_np,
    rgb_to_hsv_np as _rgb_to_hsv_np,
    smoothstep_np as _smoothstep,
    to_image_batch as _to_image_batch,
)


def _apply_toe_shoulder(rgb: np.ndarray, toe: float, shoulder: float, pivot: float = 0.5) -> np.ndarray:
    x = np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)
    p = float(np.clip(pivot, 0.1, 0.9))
    t_toe = float(np.clip(toe, 0.0, 1.0))
    t_shoulder = float(np.clip(shoulder, 0.0, 1.0))

    if t_toe > 1e-6:
        shadow_gate = 1.0 - _smoothstep(0.0, p, x)
        lifted = x / np.maximum(x + (t_toe * (1.0 - x)), 1e-6)
        x = (x * (1.0 - shadow_gate)) + (lifted * shadow_gate)

    if t_shoulder > 1e-6:
        over = np.maximum(x - p, 0.0)
        k = t_shoulder * 8.0
        comp = over / (1.0 + (k * over / max(1e-6, 1.0 - p)))
        shoulder_gate = _smoothstep(p, 1.0, x)
        compressed = x - over + comp
        x = (x * (1.0 - shoulder_gate)) + (compressed * shoulder_gate)

    return np.clip(x, 0.0, 1.0).astype(np.float32, copy=False)


def _base_grid(h: int, w: int, device: torch.device, dtype: torch.dtype):
    ys = torch.linspace(-1.0, 1.0, int(h), device=device, dtype=dtype)
    xs = torch.linspace(-1.0, 1.0, int(w), device=device, dtype=dtype)
    yy, xx = torch.meshgrid(ys, xs, indexing="ij")
    return xx, yy


def _sample_rgb_with_grid(rgb: torch.Tensor, grid: torch.Tensor) -> torch.Tensor:
    rgb_bchw = rgb.permute(0, 3, 1, 2)
    warped = F.grid_sample(
        rgb_bchw,
        grid,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )
    return warped.permute(0, 2, 3, 1)


def _damage_noise(h: int, w: int, seed: int, blur_radius: float = 1.2) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    noise = rng.random((int(h), int(w)), dtype=np.float32)
    pil = Image.fromarray(np.clip(noise * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    if blur_radius > 1e-6:
        pil = pil.filter(ImageFilter.GaussianBlur(radius=float(blur_radius)))
    arr = np.asarray(pil, dtype=np.float32) / 255.0
    return np.clip(arr, 0.0, 1.0).astype(np.float32, copy=False)


def _render_damage_maps(
    h: int,
    w: int,
    dust_amount: float,
    scratch_amount: float,
    burn_amount: float,
    seed: int,
):
    rng = np.random.default_rng(int(seed))
    h = int(h)
    w = int(w)
    dust_amt = float(np.clip(dust_amount, 0.0, 1.0))
    scratch_amt = float(np.clip(scratch_amount, 0.0, 1.0))
    burn_amt = float(np.clip(burn_amount, 0.0, 1.0))

    dust_img = Image.new("L", (w, h), 0)
    scratch_img = Image.new("L", (w, h), 0)
    dust_draw = ImageDraw.Draw(dust_img)
    scratch_draw = ImageDraw.Draw(scratch_img)

    if dust_amt > 1e-6:
        count = int(max(1, round((h * w / 45000.0) * (6.0 + (160.0 * dust_amt)))))
        for _ in range(count):
            x = float(rng.uniform(0.0, w - 1.0))
            y = float(rng.uniform(0.0, h - 1.0))
            r = float(rng.uniform(0.4, 1.8 + (5.0 * dust_amt)))
            v = int(rng.integers(120, 255))
            dust_draw.ellipse((x - r, y - r, x + r, y + r), fill=v)
        if dust_amt > 0.15:
            dust_img = dust_img.filter(ImageFilter.GaussianBlur(radius=0.35 + (dust_amt * 0.8)))

    if scratch_amt > 1e-6:
        line_count = int(max(1, round(1.0 + (18.0 * scratch_amt))))
        for _ in range(line_count):
            vertical = bool(rng.random() >= 0.22)
            width = int(max(1, round(rng.uniform(1.0, 1.0 + (2.8 * scratch_amt)))))
            alpha = int(rng.integers(96, 255))
            segments = int(max(6, round(h / 42.0))) if vertical else int(max(6, round(w / 42.0)))

            if vertical:
                x0 = float(rng.uniform(0.0, w - 1.0))
                points = []
                for i in range(segments + 1):
                    t = i / max(1, segments)
                    y = t * (h - 1)
                    x = np.clip(x0 + rng.normal(0.0, 0.35 + (2.8 * scratch_amt)), 0.0, w - 1.0)
                    points.append((float(x), float(y)))
            else:
                y0 = float(rng.uniform(0.0, h - 1.0))
                points = []
                for i in range(segments + 1):
                    t = i / max(1, segments)
                    x = t * (w - 1)
                    y = np.clip(y0 + rng.normal(0.0, 0.35 + (2.8 * scratch_amt)), 0.0, h - 1.0)
                    points.append((float(x), float(y)))
            scratch_draw.line(points, fill=alpha, width=width)

        if scratch_amt > 0.08:
            scratch_img = scratch_img.filter(ImageFilter.GaussianBlur(radius=0.3 + (scratch_amt * 0.65)))

    xv = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    yv = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    radial = np.sqrt((xv * xv) + (yv * yv))
    edge = np.clip((radial - 0.76) / 0.24, 0.0, 1.0)
    burn_noise = _damage_noise(h=h, w=w, seed=seed + 909, blur_radius=1.8)
    burn = np.clip(edge * (0.65 + (0.35 * burn_noise)) * burn_amt, 0.0, 1.0).astype(np.float32, copy=False)

    dust = (np.asarray(dust_img, dtype=np.float32) / 255.0).astype(np.float32, copy=False)
    scratches = (np.asarray(scratch_img, dtype=np.float32) / 255.0).astype(np.float32, copy=False)
    return np.clip(dust, 0.0, 1.0), np.clip(scratches, 0.0, 1.0), burn


class x1Halation:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "radius": ("FLOAT", {"default": 14.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "strength": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 3.0, "step": 0.01}),
                "tint_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_g": ("FLOAT", {"default": 0.34, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_b": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "halation_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        threshold: float = 0.72,
        softness: float = 0.10,
        radius: float = 14.0,
        strength: float = 0.45,
        tint_r: float = 1.0,
        tint_g: float = 0.34,
        tint_b: float = 0.08,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        effect_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        thr = float(np.clip(threshold, 0.0, 1.0))
        soft = float(max(0.0, softness))
        rad = float(max(0.0, radius))
        st = float(max(0.0, strength))
        m = float(np.clip(mix, 0.0, 1.0))
        tint = np.asarray([np.clip(tint_r, 0.0, 1.0), np.clip(tint_g, 0.0, 1.0), np.clip(tint_b, 0.0, 1.0)], dtype=np.float32)

        for idx in range(int(b)):
            src = src_np[idx]
            lum = _luma(src)
            hi = _smoothstep(thr - soft, thr + soft, lum)
            bright = np.clip(src * hi[..., None], 0.0, 1.0)
            halo = _gaussian_blur_rgb_np(bright, radius=rad) * tint[None, None, :] * st
            halo = np.clip(halo, 0.0, 1.0).astype(np.float32, copy=False)
            screened = 1.0 - ((1.0 - src) * (1.0 - halo))
            fx = np.clip((src * (1.0 - m)) + (screened * m), 0.0, 1.0).astype(np.float32, copy=False)
            out_np[idx] = fx
            effect_mask_np[idx] = np.clip(_luma(halo) * 2.0, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_t = torch.from_numpy(effect_mask_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * effect_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1Halation: threshold={:.2f}, softness={:.3f}, radius={:.1f}px, strength={:.2f}, "
            "tint=({:.2f},{:.2f},{:.2f}), mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            thr,
            soft,
            rad,
            st,
            float(tint[0]),
            float(tint[1]),
            float(tint[2]),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


_FILM_PRINT_PROFILES = {
    "kodak_2383": {
        "matrix": [[1.05, -0.02, -0.03], [-0.03, 1.02, 0.01], [-0.02, 0.01, 1.01]],
        "gamma": [0.97, 1.00, 1.03],
        "contrast": 1.18,
        "saturation": 1.08,
        "toe": 0.18,
        "shoulder": 0.24,
    },
    "fuji_3513": {
        "matrix": [[1.02, -0.01, -0.01], [-0.02, 1.01, 0.01], [-0.01, 0.00, 1.03]],
        "gamma": [0.99, 1.00, 1.02],
        "contrast": 1.10,
        "saturation": 1.03,
        "toe": 0.14,
        "shoulder": 0.20,
    },
    "bleach_bypass": {
        "matrix": [[1.00, 0.00, 0.00], [0.00, 1.00, 0.00], [0.00, 0.00, 1.00]],
        "gamma": [1.00, 1.00, 1.00],
        "contrast": 1.26,
        "saturation": 0.58,
        "toe": 0.10,
        "shoulder": 0.30,
    },
    "silver_fade": {
        "matrix": [[0.99, 0.01, 0.00], [0.00, 1.00, 0.00], [0.00, 0.02, 0.98]],
        "gamma": [1.03, 1.01, 0.99],
        "contrast": 0.96,
        "saturation": 0.85,
        "toe": 0.28,
        "shoulder": 0.14,
    },
    "neutral_clean": {
        "matrix": [[1.00, 0.00, 0.00], [0.00, 1.00, 0.00], [0.00, 0.00, 1.00]],
        "gamma": [1.00, 1.00, 1.00],
        "contrast": 1.00,
        "saturation": 1.00,
        "toe": 0.10,
        "shoulder": 0.10,
    },
}


class x1FilmPrint:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "stock": (list(_FILM_PRINT_PROFILES.keys()),),
                "density": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.3, "max": 2.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "warmth": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "toe": ("FLOAT", {"default": 0.20, "min": 0.0, "max": 1.0, "step": 0.01}),
                "shoulder": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fade": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.6, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "film_print_info")
    FUNCTION = "run"
    CATEGORY = COLOR_LUT

    def run(
        self,
        image: torch.Tensor,
        stock: str = "kodak_2383",
        density: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        warmth: float = 0.0,
        toe: float = 0.20,
        shoulder: float = 0.22,
        fade: float = 0.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)

        profile_key = str(stock) if str(stock) in _FILM_PRINT_PROFILES else "kodak_2383"
        profile = _FILM_PRINT_PROFILES[profile_key]
        mat = np.asarray(profile["matrix"], dtype=np.float32)
        gamma = np.asarray(profile["gamma"], dtype=np.float32)
        contrast_v = float(max(0.3, contrast)) * float(profile["contrast"])
        sat_v = float(max(0.0, saturation)) * float(profile["saturation"])
        toe_v = float(np.clip(toe + float(profile["toe"]) - 0.20, 0.0, 1.0))
        shoulder_v = float(np.clip(shoulder + float(profile["shoulder"]) - 0.22, 0.0, 1.0))
        density_ev = float(np.clip(density, -1.0, 1.0))
        warm = float(np.clip(warmth, -1.0, 1.0))
        fade_v = float(np.clip(fade, 0.0, 0.6))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            out = src.reshape(-1, 3) @ mat.T
            out = np.clip(out.reshape(src.shape), 0.0, 1.0).astype(np.float32, copy=False)
            out = np.power(np.clip(out, 0.0, 1.0), gamma[None, None, :]).astype(np.float32, copy=False)
            out = np.clip(out * float(2.0 ** density_ev), 0.0, 1.0)
            out = np.clip((out - 0.5) * contrast_v + 0.5, 0.0, 1.0)
            out = _apply_toe_shoulder(out, toe=toe_v, shoulder=shoulder_v, pivot=0.5)

            out_l = _luma(out)[..., None]
            out = np.clip(out_l + ((out - out_l) * sat_v), 0.0, 1.0)

            warmth_vec = np.asarray([0.060, 0.012, -0.052], dtype=np.float32) * warm
            out = np.clip(out + warmth_vec[None, None, :], 0.0, 1.0)

            if fade_v > 1e-6:
                faded = np.clip((_luma(out)[..., None] + 0.02), 0.0, 1.0)
                out = np.clip((out * (1.0 - fade_v)) + (faded * fade_v), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        comp_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        ).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - comp_mask)) + (fx_t * comp_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(comp_mask.mean().item()) * 100.0
        info = (
            "x1FilmPrint: stock={}, density={:+.2f}ev, contrast={:.2f}, saturation={:.2f}, warmth={:+.2f}, "
            "toe={:.2f}, shoulder={:.2f}, fade={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            profile_key,
            density_ev,
            contrast_v,
            sat_v,
            warm,
            toe_v,
            shoulder_v,
            fade_v,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), comp_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1HighlightRollOff:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "pivot": ("FLOAT", {"default": 0.68, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "amount": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_color": ("BOOLEAN", {"default": True}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "highlight_rolloff_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        pivot: float = 0.68,
        softness: float = 0.10,
        amount: float = 0.65,
        preserve_color: bool = True,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        p = float(np.clip(pivot, 0.0, 1.0))
        soft = float(max(0.0, softness))
        amt = float(np.clip(amount, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = _luma(src)
            hi = _smoothstep(p - soft, p + soft, lum)
            over = np.maximum(lum - p, 0.0)
            comp = over / (1.0 + (amt * 8.0 * over / max(1e-6, 1.0 - p)))
            target_l = lum - over + comp

            if preserve_color:
                scale = target_l / np.maximum(lum, 1e-6)
                rolled = np.clip(src * scale[..., None], 0.0, 1.0)
            else:
                delta = (over - comp)[..., None]
                rolled = np.clip(src - delta, 0.0, 1.0)

            local_mix = hi[..., None] * m
            out_np[idx] = np.clip((src * (1.0 - local_mix)) + (rolled * local_mix), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(hi * m, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        matte_t = torch.from_numpy(matte_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * matte_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1HighlightRollOff: pivot={:.2f}, softness={:.3f}, amount={:.2f}, preserve_color={}, "
            "mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            p,
            soft,
            amt,
            bool(preserve_color),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1SkinToneProtect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["auto", "naturalize", "reference_restore"],),
                "protect_strength": ("FLOAT", {"default": 0.70, "min": 0.0, "max": 1.0, "step": 0.01}),
                "hue_center": ("FLOAT", {"default": 28.0, "min": 0.0, "max": 360.0, "step": 0.5}),
                "hue_width": ("FLOAT", {"default": 40.0, "min": 1.0, "max": 180.0, "step": 0.5}),
                "sat_min": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sat_max": ("FLOAT", {"default": 0.80, "min": 0.0, "max": 1.0, "step": 0.01}),
                "val_min": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "val_max": ("FLOAT", {"default": 1.00, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 16.0, "min": 0.0, "max": 120.0, "step": 0.5}),
                "saturation_limit": ("FLOAT", {"default": 0.75, "min": 0.2, "max": 1.0, "step": 0.01}),
                "warmth_balance": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "reference_image": ("IMAGE",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "skin_mask", "skin_protect_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        mode: str = "auto",
        protect_strength: float = 0.70,
        hue_center: float = 28.0,
        hue_width: float = 40.0,
        sat_min: float = 0.10,
        sat_max: float = 0.80,
        val_min: float = 0.08,
        val_max: float = 1.00,
        softness: float = 16.0,
        saturation_limit: float = 0.75,
        warmth_balance: float = 0.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        reference_image: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        skin_matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        ref_np = None
        if reference_image is not None:
            ref_batch = _to_image_batch(reference_image)[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
            if ref_batch.shape[0] == 1 and int(b) > 1:
                ref_np = np.repeat(ref_batch, int(b), axis=0)
            elif ref_batch.shape[0] != int(b):
                raise ValueError(f"reference_image batch {ref_batch.shape[0]} does not match image batch {int(b)}")
            else:
                ref_np = ref_batch

        strength = float(np.clip(protect_strength, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))
        hc = (float(hue_center) % 360.0) / 360.0
        hw = max(1.0, float(hue_width)) * 0.5 / 360.0
        sf = max(0.0, float(softness)) / 360.0
        smin = float(np.clip(min(sat_min, sat_max), 0.0, 1.0))
        smax = float(np.clip(max(sat_min, sat_max), 0.0, 1.0))
        vmin = float(np.clip(min(val_min, val_max), 0.0, 1.0))
        vmax = float(np.clip(max(val_min, val_max), 0.0, 1.0))
        sat_cap = float(np.clip(saturation_limit, 0.2, 1.0))
        warm = float(np.clip(warmth_balance, -1.0, 1.0))

        mode_key = str(mode).lower()
        if mode_key not in {"auto", "naturalize", "reference_restore"}:
            mode_key = "auto"
        actual_mode = "reference_restore" if (mode_key == "reference_restore" and ref_np is not None) else "naturalize"
        if mode_key == "auto" and ref_np is not None:
            actual_mode = "reference_restore"

        sat_feather = min(0.5, max(0.005, sf * 2.0))
        val_feather = min(0.5, max(0.005, sf * 2.0))

        for idx in range(int(b)):
            src = src_np[idx]
            h_ch, s_ch, v_ch = _rgb_to_hsv_np(src)

            dist = np.abs(((h_ch - hc + 0.5) % 1.0) - 0.5)
            hsel = 1.0 - _smoothstep(hw, hw + sf, dist)
            ssel = _smoothstep(smin - sat_feather, smin + sat_feather, s_ch) * (
                1.0 - _smoothstep(smax - sat_feather, smax + sat_feather, s_ch)
            )
            vsel = _smoothstep(vmin - val_feather, vmin + val_feather, v_ch) * (
                1.0 - _smoothstep(vmax - val_feather, vmax + val_feather, v_ch)
            )
            matte = np.clip(hsel * ssel * vsel, 0.0, 1.0).astype(np.float32, copy=False)

            if actual_mode == "reference_restore" and ref_np is not None:
                target = _resize_rgb_np(ref_np[idx], int(h), int(w))
            else:
                sat_t = np.minimum(s_ch, sat_cap)
                hue_shift = warm * (24.0 / 360.0)
                h_t = np.mod(h_ch + hue_shift, 1.0)
                delta = ((h_t - hc + 0.5) % 1.0) - 0.5
                clamp_hw = max(1e-4, hw * 0.85)
                h_t = np.mod(hc + np.clip(delta, -clamp_hw, clamp_hw), 1.0)
                s_t = s_ch + ((sat_t - s_ch) * 0.9)
                v_t = v_ch
                target = _hsv_to_rgb_np(h_t, np.clip(s_t, 0.0, 1.0), np.clip(v_t, 0.0, 1.0))

            local_mix = matte[..., None] * strength
            protected = np.clip((src * (1.0 - local_mix)) + (target * local_mix), 0.0, 1.0)
            out_np[idx] = np.clip((src * (1.0 - m)) + (protected * m), 0.0, 1.0).astype(np.float32, copy=False)
            skin_matte_np[idx] = np.clip(matte * m, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        matte_t = torch.from_numpy(skin_matte_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * matte_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1SkinToneProtect: mode={}, strength={:.2f}, hue={:.1f}±{:.1f}, sat=[{:.2f},{:.2f}], val=[{:.2f},{:.2f}], "
            "softness={:.1f}, sat_limit={:.2f}, warmth={:+.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            actual_mode,
            strength,
            float(hue_center % 360.0),
            float(max(1.0, hue_width) * 0.5),
            smin,
            smax,
            vmin,
            vmax,
            float(max(0.0, softness)),
            sat_cap,
            warm,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1Diffusion:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "radius": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "highlight_threshold": ("FLOAT", {"default": 0.68, "min": 0.0, "max": 1.0, "step": 0.01}),
                "highlight_softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "highlight_strength": ("FLOAT", {"default": 0.48, "min": 0.0, "max": 3.0, "step": 0.01}),
                "diffusion_strength": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "contrast_softness": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "shadow_lift": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "diffusion_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        radius: float = 12.0,
        highlight_threshold: float = 0.68,
        highlight_softness: float = 0.10,
        highlight_strength: float = 0.48,
        diffusion_strength: float = 0.45,
        contrast_softness: float = 0.25,
        shadow_lift: float = 0.10,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        effect_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        rad = float(max(0.0, radius))
        thr = float(np.clip(highlight_threshold, 0.0, 1.0))
        hsoft = float(max(0.0, highlight_softness))
        high_st = float(max(0.0, highlight_strength))
        diff_st = float(np.clip(diffusion_strength, 0.0, 1.0))
        soft_c = float(np.clip(contrast_softness, 0.0, 1.0))
        sh_lift = float(np.clip(shadow_lift, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = _luma(src)
            hi = _smoothstep(thr - hsoft, thr + hsoft, lum)

            broad = _gaussian_blur_rgb_np(src, radius=rad * 0.5)
            hi_src = np.clip(src * (0.15 + (0.85 * hi[..., None])), 0.0, 1.0)
            hi_glow = _gaussian_blur_rgb_np(hi_src, radius=rad)

            softened = np.clip((src * (1.0 - diff_st)) + (broad * diff_st), 0.0, 1.0)
            if soft_c > 1e-6:
                slope = 1.0 - (0.38 * soft_c)
                softened = np.clip((softened - 0.5) * slope + 0.5, 0.0, 1.0)

            bloom = np.clip(hi_glow * high_st, 0.0, 1.0)
            screened = 1.0 - ((1.0 - softened) * (1.0 - bloom))

            if sh_lift > 1e-6:
                shadow = np.power(np.clip(1.0 - lum, 0.0, 1.0), 1.45).astype(np.float32, copy=False)
                screened = np.clip(screened + (shadow[..., None] * sh_lift * 0.14), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (screened * m), 0.0, 1.0).astype(np.float32, copy=False)
            effect_np[idx] = np.clip((0.30 + (0.70 * hi)) * m, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        effect_t = torch.from_numpy(effect_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * effect_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1Diffusion: radius={:.1f}px, highlight=thr{:.2f}/soft{:.3f}/str{:.2f}, diffusion={:.2f}, "
            "contrast_soft={:.2f}, shadow_lift={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            rad,
            thr,
            hsoft,
            high_st,
            diff_st,
            soft_c,
            sh_lift,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1GateWeave:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "shift_x_px": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "shift_y_px": ("FLOAT", {"default": 1.4, "min": 0.0, "max": 64.0, "step": 0.1}),
                "rotation_deg": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 8.0, "step": 0.01}),
                "scale_jitter": ("FLOAT", {"default": 0.010, "min": 0.0, "max": 0.20, "step": 0.001}),
                "jitter_mode": (["gaussian", "uniform"],),
                "seed": ("INT", {"default": 2048, "min": 0, "max": 99999999, "step": 1}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "gate_weave_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        shift_x_px: float = 2.0,
        shift_y_px: float = 1.4,
        rotation_deg: float = 0.35,
        scale_jitter: float = 0.010,
        jitter_mode: str = "gaussian",
        seed: int = 2048,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        device = batch.device
        dtype = batch.dtype

        sx = float(max(0.0, shift_x_px))
        sy = float(max(0.0, shift_y_px))
        rot = float(max(0.0, rotation_deg))
        scl = float(max(0.0, scale_jitter))
        m = float(np.clip(mix, 0.0, 1.0))
        mode = str(jitter_mode).lower()
        if mode not in {"gaussian", "uniform"}:
            mode = "gaussian"

        xx, yy = _base_grid(int(h), int(w), device=device, dtype=dtype)
        grids = []
        dx_list = []
        dy_list = []
        ang_list = []
        sc_list = []
        for idx in range(int(b)):
            rng = np.random.default_rng(int(seed) + (idx * 3089))
            if mode == "uniform":
                dx = float(rng.uniform(-sx, sx))
                dy = float(rng.uniform(-sy, sy))
                ang = float(rng.uniform(-rot, rot))
                sc = float(1.0 + rng.uniform(-scl, scl))
            else:
                dx = float(np.clip(rng.normal(0.0, sx * 0.42), -sx, sx))
                dy = float(np.clip(rng.normal(0.0, sy * 0.42), -sy, sy))
                ang = float(np.clip(rng.normal(0.0, rot * 0.42), -rot, rot))
                sc = float(1.0 + np.clip(rng.normal(0.0, scl * 0.42), -scl, scl))

            dx_n = float(2.0 * dx / max(1, int(w) - 1))
            dy_n = float(2.0 * dy / max(1, int(h) - 1))
            ang_r = math.radians(ang)
            ca = float(math.cos(ang_r))
            sa = float(math.sin(ang_r))
            sc_safe = max(0.5, sc)

            x0 = xx - dx_n
            y0 = yy - dy_n
            x_in = ((ca * x0) + (sa * y0)) / sc_safe
            y_in = ((-sa * x0) + (ca * y0)) / sc_safe
            grid = torch.stack([x_in, y_in], dim=-1)
            grids.append(grid)
            dx_list.append(dx)
            dy_list.append(dy)
            ang_list.append(ang)
            sc_list.append(sc)

        grid_b = torch.stack(grids, dim=0)
        warped = _sample_rgb_with_grid(rgb, grid_b)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=device,
            dtype=dtype,
        )
        final_mask = torch.clamp(base_mask * m, 0.0, 1.0).unsqueeze(-1)

        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (warped * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        avg_dx = float(np.mean(np.abs(dx_list))) if dx_list else 0.0
        avg_dy = float(np.mean(np.abs(dy_list))) if dy_list else 0.0
        avg_ang = float(np.mean(np.abs(ang_list))) if ang_list else 0.0
        avg_sc = float(np.mean(np.abs(np.asarray(sc_list, dtype=np.float32) - 1.0))) if sc_list else 0.0
        info = (
            "x1GateWeave: shift=({:.2f},{:.2f})px, rot={:.3f}deg, scale_jitter={:.4f}, mode={}, "
            "avg_abs=({:.2f}px,{:.2f}px,{:.3f}deg,{:.4f}), seed={}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            sx,
            sy,
            rot,
            scl,
            mode,
            avg_dx,
            avg_dy,
            avg_ang,
            avg_sc,
            int(max(0, seed)),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1FilmDamage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "dust_amount": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "scratch_amount": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "burn_amount": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
                "flicker_amount": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.005}),
                "seed": ("INT", {"default": 1977, "min": 0, "max": 99999999, "step": 1}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "film_damage_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        dust_amount: float = 0.25,
        scratch_amount: float = 0.22,
        burn_amount: float = 0.10,
        flicker_amount: float = 0.08,
        seed: int = 1977,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        damage_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        dust_amt = float(np.clip(dust_amount, 0.0, 1.0))
        scratch_amt = float(np.clip(scratch_amount, 0.0, 1.0))
        burn_amt = float(np.clip(burn_amount, 0.0, 1.0))
        flick = float(np.clip(flicker_amount, 0.0, 0.5))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            rng = np.random.default_rng(int(seed) + (idx * 7411))
            dust, scratches, burn = _render_damage_maps(
                h=int(h),
                w=int(w),
                dust_amount=dust_amt,
                scratch_amount=scratch_amt,
                burn_amount=burn_amt,
                seed=int(seed) + (idx * 9137),
            )

            exposure_ev = float(rng.uniform(-flick, flick))
            out = np.clip(src * float(2.0 ** exposure_ev), 0.0, 1.0)
            out = np.clip(out + (dust[..., None] * (0.05 + (0.50 * dust_amt))), 0.0, 1.0)
            out = np.clip(out - (scratches[..., None] * (0.10 + (0.70 * scratch_amt))), 0.0, 1.0)

            if burn_amt > 1e-6:
                burn_mix = burn[..., None] * (0.24 + (0.58 * burn_amt))
                out = np.clip(out * (1.0 - burn_mix), 0.0, 1.0)
                out[..., 0] = np.clip(out[..., 0] + (burn * 0.11), 0.0, 1.0)
                out[..., 1] = np.clip(out[..., 1] + (burn * 0.04), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)
            damage_np[idx] = np.clip(((0.75 * dust) + scratches + (0.85 * burn)) * m, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        )
        damage_t = torch.from_numpy(damage_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * damage_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1FilmDamage: dust={:.2f}, scratches={:.2f}, burn={:.2f}, flicker={:.3f}, "
            "seed={}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            dust_amt,
            scratch_amt,
            burn_amt,
            flick,
            int(max(0, seed)),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1LensBreathing:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "breath_amount": ("FLOAT", {"default": 0.08, "min": -0.35, "max": 0.35, "step": 0.001}),
                "edge_response": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "anisotropy": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "chroma": ("FLOAT", {"default": 0.16, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "depth_map": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "lens_breathing_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        breath_amount: float = 0.08,
        edge_response: float = 0.72,
        anisotropy: float = 0.0,
        center_x: float = 0.5,
        center_y: float = 0.5,
        chroma: float = 0.16,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        depth_map: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        device = batch.device
        dtype = batch.dtype

        ba = float(np.clip(breath_amount, -0.35, 0.35))
        er = float(np.clip(edge_response, 0.0, 1.0))
        aniso = float(np.clip(anisotropy, -1.0, 1.0))
        cx = float(np.clip(center_x, 0.0, 1.0)) * 2.0 - 1.0
        cy = float(np.clip(center_y, 0.0, 1.0)) * 2.0 - 1.0
        chr_amt = float(np.clip(chroma, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        xx, yy = _base_grid(int(h), int(w), device=device, dtype=dtype)
        dx = xx - cx
        dy = yy - cy
        radius = torch.sqrt((dx * dx) + (dy * dy) + 1e-12) / 1.41421356237
        radius = torch.clamp(radius, 0.0, 1.0)

        depth_t = None
        if depth_map is not None:
            depth_t = _mask_to_batch(
                mask=depth_map,
                batch=int(b),
                h=int(h),
                w=int(w),
                feather_radius=0.0,
                invert_mask=False,
                device=device,
                dtype=dtype,
            )

        out_rgb_full = torch.empty_like(rgb)
        response_stack = torch.empty((int(b), int(h), int(w)), device=device, dtype=dtype)
        rgb_bchw = rgb.permute(0, 3, 1, 2)
        for idx in range(int(b)):
            response = er * (0.30 + (0.70 * torch.pow(radius, 1.35)))
            if depth_t is not None:
                response = response * (0.55 + (0.45 * depth_t[idx]))

            scale = 1.0 + (ba * response)
            ax = 1.0 + (aniso * 0.18)
            ay = 1.0 - (aniso * 0.18)
            sx = torch.clamp(scale * ax, 0.35, 4.0)
            sy = torch.clamp(scale * ay, 0.35, 4.0)

            x_in = cx + (dx / sx)
            y_in = cy + (dy / sy)

            warp = torch.pow(radius, 2.0) * ba * er * 0.08
            x_in = x_in + (dx * warp)
            y_in = y_in + (dy * warp)
            main_grid = torch.stack([x_in, y_in], dim=-1).unsqueeze(0)

            main_sample = F.grid_sample(
                rgb_bchw[idx : idx + 1],
                main_grid,
                mode="bilinear",
                padding_mode="border",
                align_corners=True,
            )
            out_i = main_sample.permute(0, 2, 3, 1)[0]

            if chr_amt > 1e-6:
                fringe = chr_amt * (0.10 + (0.40 * abs(ba)))
                sx_r = torch.clamp(sx * (1.0 + fringe), 0.35, 4.0)
                sy_r = torch.clamp(sy * (1.0 + (fringe * 0.6)), 0.35, 4.0)
                sx_b = torch.clamp(sx * (1.0 - fringe), 0.35, 4.0)
                sy_b = torch.clamp(sy * (1.0 - (fringe * 0.6)), 0.35, 4.0)

                x_r = cx + (dx / sx_r) + (dx * warp)
                y_r = cy + (dy / sy_r) + (dy * warp)
                x_b = cx + (dx / sx_b) + (dx * warp)
                y_b = cy + (dy / sy_b) + (dy * warp)
                grid_r = torch.stack([x_r, y_r], dim=-1).unsqueeze(0)
                grid_b = torch.stack([x_b, y_b], dim=-1).unsqueeze(0)

                r_plane = F.grid_sample(
                    rgb_bchw[idx : idx + 1, 0:1, :, :],
                    grid_r,
                    mode="bilinear",
                    padding_mode="border",
                    align_corners=True,
                )
                b_plane = F.grid_sample(
                    rgb_bchw[idx : idx + 1, 2:3, :, :],
                    grid_b,
                    mode="bilinear",
                    padding_mode="border",
                    align_corners=True,
                )
                out_i[..., 0] = r_plane[0, 0]
                out_i[..., 2] = b_plane[0, 0]

            out_rgb_full[idx] = torch.clamp(out_i, 0.0, 1.0)
            response_stack[idx] = torch.clamp(response, 0.0, 1.0)

        base_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=device,
            dtype=dtype,
        )
        effect_mask = torch.clamp((0.30 + (0.70 * response_stack)) * m, 0.0, 1.0)
        final_mask = torch.clamp(base_mask * effect_mask, 0.0, 1.0).unsqueeze(-1)

        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (out_rgb_full * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1LensBreathing: breath={:+.4f}, edge_response={:.2f}, anisotropy={:+.2f}, center=({:.3f},{:.3f}), "
            "chroma={:.2f}, depth_map={}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            ba,
            er,
            aniso,
            float(np.clip(center_x, 0.0, 1.0)),
            float(np.clip(center_y, 0.0, 1.0)),
            chr_amt,
            "yes" if depth_map is not None else "no",
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)
