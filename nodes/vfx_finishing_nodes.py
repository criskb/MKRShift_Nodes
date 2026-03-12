import math
from typing import Optional

import numpy as np
import torch

from ..categories import FX_DISTORT, FX_OPTICS
from ..lib.image_shared import gaussian_blur_rgb_np, luma_np, resize_rgb_np, smoothstep_np, to_image_batch
from ..lib.vfx_shared import apply_masked_output, normalized_grid, sample_rgb_grid, screen_blend_np


def _build_streak_np(bright_rgb: np.ndarray, orientation: str, length_px: float) -> np.ndarray:
    h, w = bright_rgb.shape[:2]
    length = float(max(1.0, length_px))
    squeeze = max(1.5, 1.0 + (length / 10.0))
    soft_radius = max(0.5, length * 0.12)

    if str(orientation).lower() == "vertical":
        reduced_h = max(1, int(round(h / squeeze)))
        streak = resize_rgb_np(bright_rgb, reduced_h, w)
        streak = gaussian_blur_rgb_np(streak, radius=soft_radius)
        streak = resize_rgb_np(streak, h, w)
    else:
        reduced_w = max(1, int(round(w / squeeze)))
        streak = resize_rgb_np(bright_rgb, h, reduced_w)
        streak = gaussian_blur_rgb_np(streak, radius=soft_radius)
        streak = resize_rgb_np(streak, h, w)

    tail = gaussian_blur_rgb_np(streak, radius=max(0.5, length * 0.06))
    return np.clip((streak * 0.72) + (tail * 0.28), 0.0, 1.0).astype(np.float32, copy=False)


class x1AnamorphicStreaks:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "orientation": (["horizontal", "vertical"],),
                "threshold": ("FLOAT", {"default": 0.74, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "length_px": ("FLOAT", {"default": 48.0, "min": 1.0, "max": 512.0, "step": 1.0}),
                "strength": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 3.0, "step": 0.01}),
                "tint_r": ("FLOAT", {"default": 0.92, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_g": ("FLOAT", {"default": 0.86, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_b": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "anamorphic_streaks_info")
    FUNCTION = "run"
    CATEGORY = FX_OPTICS

    def run(
        self,
        image: torch.Tensor,
        orientation: str = "horizontal",
        threshold: float = 0.74,
        softness: float = 0.10,
        length_px: float = 48.0,
        strength: float = 0.75,
        tint_r: float = 0.92,
        tint_g: float = 0.86,
        tint_b: float = 1.0,
        mix: float = 1.0,
        mask_feather: float = 10.0,
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
        length = float(max(1.0, length_px))
        streak_strength = float(max(0.0, strength))
        tint = np.asarray(
            [np.clip(tint_r, 0.0, 1.0), np.clip(tint_g, 0.0, 1.0), np.clip(tint_b, 0.0, 1.0)],
            dtype=np.float32,
        )
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            highlight = smoothstep_np(thr - soft, thr + soft, lum)
            bright_rgb = np.clip(src * highlight[..., None], 0.0, 1.0)
            streak = _build_streak_np(bright_rgb, orientation=orientation, length_px=length)
            tinted = np.clip(streak * tint[None, None, :] * streak_strength, 0.0, 1.0).astype(np.float32, copy=False)
            screened = screen_blend_np(src, tinted)
            out_np[idx] = np.clip((src * (1.0 - m)) + (screened * m), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(luma_np(tinted) * (1.25 * m), 0.0, 1.0)

        out, out_mask, coverage = apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1AnamorphicStreaks: orientation={}, threshold={:.2f}, softness={:.3f}, length={:.1f}px, "
            "strength={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            str(orientation).lower(),
            thr,
            soft,
            length,
            streak_strength,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1HeatHaze:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "direction": (["up", "down", "left", "right"],),
                "strength_px": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 128.0, "step": 0.25}),
                "scale": ("FLOAT", {"default": 3.2, "min": 0.25, "max": 16.0, "step": 0.05}),
                "phase_deg": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "chroma_split_px": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 12.0, "step": 0.05}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "heat_haze_info")
    FUNCTION = "run"
    CATEGORY = FX_DISTORT

    def run(
        self,
        image: torch.Tensor,
        direction: str = "up",
        strength_px: float = 8.0,
        scale: float = 3.2,
        phase_deg: float = 0.0,
        chroma_split_px: float = 0.8,
        mix: float = 1.0,
        mask_feather: float = 6.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3]

        strength = float(max(0.0, strength_px))
        if strength <= 1e-6 or float(np.clip(mix, 0.0, 1.0)) <= 1e-6:
            matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
            passthrough = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
            out, out_mask, coverage = apply_masked_output(
                image=image,
                fx_np=passthrough,
                matte_np=matte_np,
                mask=mask,
                mask_feather=mask_feather,
                invert_mask=invert_mask,
            )
            info = "x1HeatHaze: bypassed (strength or mix is 0)"
            return (out, out_mask, info)

        device = batch.device
        dtype = batch.dtype
        base_grid = normalized_grid(int(h), int(w), device=device, dtype=dtype).unsqueeze(0).expand(int(b), -1, -1, -1)
        xx = base_grid[..., 0]
        yy = base_grid[..., 1]

        direction_key = str(direction).lower()
        along = yy if direction_key in {"up", "down"} else xx
        cross = xx if direction_key in {"up", "down"} else yy
        phase = math.radians(float(phase_deg))
        scale_value = float(max(0.25, scale))

        wave_a = torch.sin((along * scale_value * math.pi * 2.15) + phase)
        wave_b = torch.sin((along * scale_value * math.pi * 4.35) - (phase * 1.7) + (cross * math.pi * 1.1))
        wave_c = torch.cos((cross * scale_value * math.pi * 0.85) + (phase * 0.35))
        field = (wave_a * 0.56) + (wave_b * 0.29) + (wave_c * 0.15)
        shimmer = torch.clamp((field * 0.5) + 0.5, 0.0, 1.0)

        px_norm_x = float(strength) * 2.0 / max(float(max(int(w) - 1, 1)), 1.0)
        px_norm_y = float(strength) * 2.0 / max(float(max(int(h) - 1, 1)), 1.0)

        if direction_key in {"up", "down"}:
            offset_x = field * px_norm_x * (0.42 + (0.58 * shimmer))
            drift_sign = -1.0 if direction_key == "up" else 1.0
            offset_y = wave_b * px_norm_y * 0.18 * drift_sign
        else:
            offset_y = field * px_norm_y * (0.42 + (0.58 * shimmer))
            drift_sign = 1.0 if direction_key == "right" else -1.0
            offset_x = wave_b * px_norm_x * 0.18 * drift_sign

        distortion_grid = base_grid.clone()
        distortion_grid[..., 0] = torch.clamp(distortion_grid[..., 0] + offset_x, -1.0, 1.0)
        distortion_grid[..., 1] = torch.clamp(distortion_grid[..., 1] + offset_y, -1.0, 1.0)

        split_px = float(max(0.0, chroma_split_px))
        split_norm_x = split_px * 2.0 / max(float(max(int(w) - 1, 1)), 1.0)
        split_norm_y = split_px * 2.0 / max(float(max(int(h) - 1, 1)), 1.0)

        red_grid = distortion_grid.clone()
        blue_grid = distortion_grid.clone()
        if direction_key in {"up", "down"}:
            red_grid[..., 0] = torch.clamp(red_grid[..., 0] + (field * split_norm_x), -1.0, 1.0)
            blue_grid[..., 0] = torch.clamp(blue_grid[..., 0] - (field * split_norm_x), -1.0, 1.0)
        else:
            red_grid[..., 1] = torch.clamp(red_grid[..., 1] + (field * split_norm_y), -1.0, 1.0)
            blue_grid[..., 1] = torch.clamp(blue_grid[..., 1] - (field * split_norm_y), -1.0, 1.0)

        sampled = sample_rgb_grid(rgb, distortion_grid)
        if split_px > 1e-6:
            sampled_r = sample_rgb_grid(rgb[..., 0:1], red_grid)
            sampled_b = sample_rgb_grid(rgb[..., 2:3], blue_grid)
            sampled = torch.cat((sampled_r, sampled[..., 1:2], sampled_b), dim=-1)

        mix_value = float(np.clip(mix, 0.0, 1.0))
        fx_rgb = torch.clamp((rgb * (1.0 - mix_value)) + (sampled * mix_value), 0.0, 1.0)
        fx_np = fx_rgb.detach().cpu().numpy().astype(np.float32, copy=False)

        magnitude = torch.sqrt((offset_x * offset_x) + (offset_y * offset_y))
        max_mag = torch.clamp(magnitude.max(), min=1e-6)
        matte_np = torch.clamp((magnitude / max_mag) * mix_value, 0.0, 1.0).detach().cpu().numpy().astype(np.float32, copy=False)

        out, out_mask, coverage = apply_masked_output(
            image=image,
            fx_np=fx_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1HeatHaze: direction={}, strength={:.2f}px, scale={:.2f}, phase={:.1f}deg, "
            "chroma_split={:.2f}px, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            direction_key,
            strength,
            scale_value,
            float(phase_deg),
            split_px,
            mix_value,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
