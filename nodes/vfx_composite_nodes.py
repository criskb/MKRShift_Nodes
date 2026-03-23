from typing import Optional

import numpy as np
import torch

from ..categories import FX_DISTORT, FX_OPTICS
from ..lib.image_shared import gaussian_blur_rgb_np, luma_np, mask_to_batch, resize_rgb_np, smoothstep_np, to_image_batch


def _fit_batch_to_shape(image: torch.Tensor, batch: int, h: int, w: int) -> np.ndarray:
    t = to_image_batch(image)[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
    if t.shape[0] == 1 and batch > 1:
        t = np.repeat(t, batch, axis=0)
    if t.shape[0] != batch:
        raise ValueError(f"Image batch {t.shape[0]} does not match expected batch {batch}")
    if t.shape[1] == h and t.shape[2] == w:
        return t
    out = np.empty((batch, h, w, 3), dtype=np.float32)
    for idx in range(batch):
        out[idx] = resize_rgb_np(t[idx], h, w)
    return out


class x1LightWrapComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "foreground": ("IMAGE",),
                "background": ("IMAGE",),
                "matte": ("MASK",),
                "wrap_radius": ("FLOAT", {"default": 18.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "wrap_strength": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 3.0, "step": 0.01}),
                "edge_bias": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "inside_holdout": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "light_wrap_info")
    FUNCTION = "run"
    CATEGORY = FX_OPTICS

    def run(
        self,
        foreground: torch.Tensor,
        background: torch.Tensor,
        matte: torch.Tensor,
        wrap_radius: float = 18.0,
        wrap_strength: float = 0.65,
        edge_bias: float = 0.55,
        inside_holdout: float = 0.75,
        mix: float = 1.0,
    ):
        fg_batch = to_image_batch(foreground)
        b, h, w, c = fg_batch.shape
        bg_np = _fit_batch_to_shape(background, int(b), int(h), int(w))
        fg_np = fg_batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        matte_t = mask_to_batch(
            mask=matte,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=0.0,
            invert_mask=False,
            device=fg_batch.device,
            dtype=fg_batch.dtype,
        )
        matte_np = matte_t.detach().cpu().numpy().astype(np.float32, copy=False)

        radius = float(max(0.0, wrap_radius))
        strength = float(max(0.0, wrap_strength))
        bias = float(np.clip(edge_bias, 0.0, 1.0))
        holdout = float(np.clip(inside_holdout, 0.0, 1.0))
        mix_value = float(np.clip(mix, 0.0, 1.0))

        out_np = np.empty_like(fg_np)
        wrap_matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        for idx in range(int(b)):
            fg = fg_np[idx]
            bg = bg_np[idx]
            m = np.clip(matte_np[idx], 0.0, 1.0)
            composite = (fg * m[..., None]) + (bg * (1.0 - m[..., None]))
            if radius <= 1e-6 or strength <= 1e-6 or mix_value <= 1e-6:
                out_np[idx] = np.clip(composite, 0.0, 1.0).astype(np.float32, copy=False)
                continue
            outer = gaussian_blur_rgb_np(bg * (1.0 - m[..., None]), radius=radius)
            edge = smoothstep_np(0.02, max(0.05, 1.0 - bias), gaussian_blur_rgb_np(np.repeat(m[..., None], 3, axis=-1), radius=max(1.0, radius * 0.55))[..., 0] - m)
            edge = np.clip(edge, 0.0, 1.0)
            holdout_mask = 1.0 - (m * holdout)
            wrapped = composite + (outer * edge[..., None] * holdout_mask[..., None] * strength)
            out_np[idx] = np.clip((composite * (1.0 - mix_value)) + (wrapped * mix_value), 0.0, 1.0).astype(np.float32, copy=False)
            wrap_matte_np[idx] = np.clip(edge * mix_value, 0.0, 1.0)

        alpha = fg_batch[..., 3:4] if c == 4 else None
        out_t = torch.from_numpy(out_np).to(device=fg_batch.device, dtype=fg_batch.dtype)
        out = torch.cat((out_t, alpha), dim=-1) if alpha is not None else out_t
        mask_out = torch.from_numpy(wrap_matte_np).to(device=fg_batch.device, dtype=fg_batch.dtype)
        info = (
            "x1LightWrapComposite: wrap_radius={:.1f}px, wrap_strength={:.2f}, edge_bias={:.2f}, "
            "inside_holdout={:.2f}, mix={:.2f}"
        ).format(radius, strength, bias, holdout, mix_value)
        return (out.clamp(0.0, 1.0), mask_out.clamp(0.0, 1.0), info)


class x1EdgeAberration:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "strength_px": ("FLOAT", {"default": 2.4, "min": 0.0, "max": 24.0, "step": 0.05}),
                "edge_threshold": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.005}),
                "edge_softness": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 1.0, "step": 0.005}),
                "radial_bias": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "edge_aberration_info")
    FUNCTION = "run"
    CATEGORY = FX_DISTORT

    def run(
        self,
        image: torch.Tensor,
        strength_px: float = 2.4,
        edge_threshold: float = 0.10,
        edge_softness: float = 0.18,
        radial_bias: float = 0.65,
        mix: float = 1.0,
        mask_feather: float = 4.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        rgb_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(rgb_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        px = float(max(0.0, strength_px))
        thr = float(np.clip(edge_threshold, 0.0, 1.0))
        soft = float(max(1e-6, edge_softness))
        radial = float(np.clip(radial_bias, 0.0, 1.0))
        mix_value = float(np.clip(mix, 0.0, 1.0))

        yy, xx = np.meshgrid(
            np.linspace(-1.0, 1.0, int(h), dtype=np.float32),
            np.linspace(-1.0, 1.0, int(w), dtype=np.float32),
            indexing="ij",
        )
        lens = np.sqrt((xx * xx) + (yy * yy))
        lens = np.clip((lens - 0.1) / 1.2, 0.0, 1.0).astype(np.float32, copy=False)
        px_x = int(max(1, round(px)))

        for idx in range(int(b)):
            src = rgb_np[idx]
            lum = luma_np(src)
            dx = np.abs(np.roll(lum, -1, axis=1) - lum)
            dy = np.abs(np.roll(lum, -1, axis=0) - lum)
            edge = np.sqrt((dx * dx) + (dy * dy))
            edge = smoothstep_np(thr, thr + soft, edge)
            radial_weight = np.clip((edge * (1.0 - radial)) + (edge * lens * radial), 0.0, 1.0).astype(np.float32, copy=False)

            shift = max(1, px_x)
            red = np.roll(src[..., 0], shift, axis=1)
            blue = np.roll(src[..., 2], -shift, axis=1)
            aberrated = np.stack((red, src[..., 1], blue), axis=-1).astype(np.float32, copy=False)
            mixed = src * (1.0 - radial_weight[..., None]) + aberrated * radial_weight[..., None]
            out_np[idx] = np.clip((src * (1.0 - mix_value)) + (mixed * mix_value), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(radial_weight * mix_value, 0.0, 1.0)

        from ..lib.vfx_shared import apply_masked_output

        out, out_mask, coverage = apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1EdgeAberration: strength={:.2f}px, edge_threshold={:.3f}, edge_softness={:.3f}, "
            "radial_bias={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            px,
            thr,
            soft,
            radial,
            mix_value,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
