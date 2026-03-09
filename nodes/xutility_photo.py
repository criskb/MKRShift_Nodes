from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
import torch

from ..categories import UTILITY_PHOTO
from ..lib.image_shared import luma_np, mask_to_batch, smoothstep_np, to_image_batch


def _blur_single_channel(channel: np.ndarray, radius: float) -> np.ndarray:
    r = float(max(0.0, radius))
    if r <= 1e-6:
        return channel.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(channel * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    pil = pil.filter(ImageFilter.GaussianBlur(radius=r))
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _blur_rgb(rgb: np.ndarray, radius: float) -> np.ndarray:
    r = float(max(0.0, radius))
    if r <= 1e-6:
        return rgb.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    pil = pil.filter(ImageFilter.GaussianBlur(radius=r))
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


class x1DenoiseDetail:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "luma_denoise": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
                "chroma_denoise": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_preserve": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "luma_radius": ("FLOAT", {"default": 2.8, "min": 0.0, "max": 32.0, "step": 0.1}),
                "chroma_radius": ("FLOAT", {"default": 3.6, "min": 0.0, "max": 64.0, "step": 0.1}),
                "detail_boost": ("FLOAT", {"default": 0.25, "min": -1.0, "max": 2.0, "step": 0.01}),
                "detail_radius": ("FLOAT", {"default": 1.5, "min": 0.2, "max": 16.0, "step": 0.1}),
                "grain_protect": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "denoise_detail_info")
    FUNCTION = "run"
    CATEGORY = UTILITY_PHOTO

    def run(
        self,
        image: torch.Tensor,
        luma_denoise: float = 0.30,
        chroma_denoise: float = 0.45,
        edge_preserve: float = 0.72,
        luma_radius: float = 2.8,
        chroma_radius: float = 3.6,
        detail_boost: float = 0.25,
        detail_radius: float = 1.5,
        grain_protect: float = 0.25,
        mix: float = 1.0,
        mask_feather: float = 10.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        effect_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        l_dn = float(np.clip(luma_denoise, 0.0, 1.0))
        c_dn = float(np.clip(chroma_denoise, 0.0, 1.0))
        preserve = float(np.clip(edge_preserve, 0.0, 1.0))
        l_rad = float(max(0.0, luma_radius))
        c_rad = float(max(0.0, chroma_radius))
        d_boost = float(np.clip(detail_boost, -1.0, 2.0))
        d_rad = float(max(0.2, detail_radius))
        g_protect = float(np.clip(grain_protect, 0.0, 1.0))
        m = float(np.clip(mix, 0.0, 1.0))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)

            lum_blur = _blur_single_channel(lum, l_rad)
            edge = np.abs(lum - lum_blur)
            edge_gate = smoothstep_np(0.01, 0.06, edge)
            preserve_mask = np.clip(edge_gate * preserve, 0.0, 1.0)

            den_lum = (lum * (1.0 - l_dn)) + (lum_blur * l_dn)
            den_lum = (den_lum * (1.0 - preserve_mask)) + (lum * preserve_mask)

            rgb_blur = _blur_rgb(src, c_rad)
            src_l = lum[..., None]
            blur_l = luma_np(rgb_blur)[..., None]
            src_chroma = src - src_l
            blur_chroma = rgb_blur - blur_l
            den_chroma = (src_chroma * (1.0 - c_dn)) + (blur_chroma * c_dn)
            den = np.clip(den_lum[..., None] + den_chroma, 0.0, 1.0)

            hp_blur = _blur_rgb(den, d_rad)
            highpass = den - hp_blur
            noise_matte = 1.0 - smoothstep_np(0.006, 0.03, np.mean(np.abs(highpass), axis=-1))
            boost = d_boost * (1.0 - (noise_matte * g_protect))
            refined = np.clip(den + (highpass * boost[..., None]), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - m)) + (refined * m), 0.0, 1.0).astype(np.float32, copy=False)
            effect_np[idx] = np.clip((1.0 - preserve_mask) * m, 0.0, 1.0)

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
        effect_t = torch.from_numpy(effect_np).to(device=batch.device, dtype=batch.dtype)
        final_mask = torch.clamp(base_mask * effect_t, 0.0, 1.0).unsqueeze(-1)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = (
            "x1DenoiseDetail: luma={:.2f}@{:.1f}px, chroma={:.2f}@{:.1f}px, edge_preserve={:.2f}, "
            "detail_boost={:+.2f}@{:.1f}px, grain_protect={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            l_dn,
            l_rad,
            c_dn,
            c_rad,
            preserve,
            d_boost,
            d_rad,
            g_protect,
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)
