import math
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import torch

from ..categories import FX_DISTORT, FX_OPTICS
from ..lib.image_shared import gaussian_blur_rgb_np, luma_np, smoothstep_np, to_image_batch
from ..lib.vfx_shared import apply_masked_output, normalized_grid, sample_rgb_grid, screen_blend_np


def _resized_noise_map(h: int, w: int, seed: int, cell_size: float) -> np.ndarray:
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    cell = max(2.0, float(cell_size))
    grid_h = max(2, int(math.ceil(h / cell)) + 1)
    grid_w = max(2, int(math.ceil(w / cell)) + 1)
    grid = rng.random((grid_h, grid_w), dtype=np.float32)
    pil = Image.fromarray(np.clip(grid * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    pil = pil.resize((int(w), int(h)), resample=Image.Resampling.BICUBIC)
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _lens_dirt_texture(h: int, w: int, dirt_scale: float, dirt_contrast: float, seed: int) -> np.ndarray:
    h = int(h)
    w = int(w)
    scale = float(max(8.0, dirt_scale))
    contrast = float(max(0.1, dirt_contrast))

    base = _resized_noise_map(h=h, w=w, seed=seed, cell_size=scale)
    smudge = _resized_noise_map(h=h, w=w, seed=seed + 37, cell_size=scale * 0.6)
    fine = _resized_noise_map(h=h, w=w, seed=seed + 91, cell_size=max(2.0, scale * 0.18))

    base_img = Image.fromarray(np.clip(base * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    blur_radius = max(0.5, scale * 0.06)
    base_img = base_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    base = np.asarray(base_img, dtype=np.float32) / 255.0

    scratches = Image.new("L", (w, h), 0)
    scratch_draw = ImageDraw.Draw(scratches)
    rng = np.random.default_rng(int(seed) + 173)
    scratch_count = int(max(3, round((w + h) / max(scale * 8.0, 24.0))))
    for _ in range(scratch_count):
        x0 = float(rng.uniform(0.0, w - 1.0))
        y0 = float(rng.uniform(0.0, h - 1.0))
        angle = float(rng.uniform(0.0, math.tau))
        length = float(rng.uniform(scale * 0.5, scale * 1.8))
        x1 = np.clip(x0 + math.cos(angle) * length, 0.0, w - 1.0)
        y1 = np.clip(y0 + math.sin(angle) * length, 0.0, h - 1.0)
        alpha = int(rng.integers(70, 180))
        width_px = int(max(1, round(rng.uniform(1.0, 2.4))))
        scratch_draw.line((x0, y0, x1, y1), fill=alpha, width=width_px)
    scratches = scratches.filter(ImageFilter.GaussianBlur(radius=max(0.3, scale * 0.01)))
    scratch_np = np.asarray(scratches, dtype=np.float32) / 255.0

    xv = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    yv = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    radial = np.sqrt((xv * xv) + (yv * yv))
    vignette = 1.0 - np.clip((radial - 0.15) / 1.25, 0.0, 1.0)

    dirt = (base * 0.55) + (smudge * 0.25) + (fine * 0.12) + (scratch_np * 0.35)
    dirt = np.clip(dirt * (0.82 + (0.18 * vignette)), 0.0, 1.0)
    dirt = np.power(np.clip(dirt, 0.0, 1.0), 1.0 / contrast).astype(np.float32, copy=False)
    dirt = smoothstep_np(0.25, 0.95, dirt)
    return np.clip(dirt, 0.0, 1.0).astype(np.float32, copy=False)


class x1LensDirtBloom:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.005}),
                "bloom_radius": ("FLOAT", {"default": 18.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "bloom_strength": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 3.0, "step": 0.01}),
                "dirt_amount": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "dirt_scale": ("FLOAT", {"default": 72.0, "min": 8.0, "max": 512.0, "step": 1.0}),
                "dirt_contrast": ("FLOAT", {"default": 1.35, "min": 0.2, "max": 4.0, "step": 0.01}),
                "tint_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_g": ("FLOAT", {"default": 0.96, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_b": ("FLOAT", {"default": 0.88, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 23, "min": 0, "max": 2147483647}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "lens_dirt_bloom_info")
    FUNCTION = "run"
    CATEGORY = FX_OPTICS

    def run(
        self,
        image: torch.Tensor,
        threshold: float = 0.72,
        softness: float = 0.10,
        bloom_radius: float = 18.0,
        bloom_strength: float = 0.75,
        dirt_amount: float = 0.65,
        dirt_scale: float = 72.0,
        dirt_contrast: float = 1.35,
        tint_r: float = 1.0,
        tint_g: float = 0.96,
        tint_b: float = 0.88,
        seed: int = 23,
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
        radius = float(max(0.0, bloom_radius))
        strength = float(max(0.0, bloom_strength))
        dirt_mix = float(np.clip(dirt_amount, 0.0, 1.0))
        tint = np.asarray(
            [np.clip(tint_r, 0.0, 1.0), np.clip(tint_g, 0.0, 1.0), np.clip(tint_b, 0.0, 1.0)],
            dtype=np.float32,
        )
        m = float(np.clip(mix, 0.0, 1.0))
        dirt_tex = _lens_dirt_texture(h=int(h), w=int(w), dirt_scale=dirt_scale, dirt_contrast=dirt_contrast, seed=int(seed))

        for idx in range(int(b)):
            src = src_np[idx]
            lum = luma_np(src)
            hi = smoothstep_np(thr - soft, thr + soft, lum)
            bright_rgb = np.clip(src * hi[..., None], 0.0, 1.0)
            bloom = gaussian_blur_rgb_np(bright_rgb, radius=radius)
            dirt_gain = (1.0 - dirt_mix) + ((0.5 + (dirt_tex * 1.35)) * dirt_mix)
            dirt_bloom = np.clip(bloom * dirt_gain[..., None] * tint[None, None, :] * strength, 0.0, 1.0).astype(np.float32, copy=False)
            screened = screen_blend_np(src, dirt_bloom)
            out_np[idx] = np.clip((src * (1.0 - m)) + (screened * m), 0.0, 1.0).astype(np.float32, copy=False)
            matte_np[idx] = np.clip(luma_np(dirt_bloom) * (1.3 * m), 0.0, 1.0)

        out, out_mask, coverage = apply_masked_output(
            image=image,
            fx_np=out_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1LensDirtBloom: threshold={:.2f}, softness={:.3f}, bloom_radius={:.1f}px, bloom_strength={:.2f}, "
            "dirt_amount={:.2f}, dirt_scale={:.1f}px, dirt_contrast={:.2f}, seed={}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            thr,
            soft,
            radius,
            strength,
            dirt_mix,
            float(dirt_scale),
            float(dirt_contrast),
            int(seed),
            m,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)


class x1ShockwaveDistort:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "radius": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.5, "step": 0.001}),
                "width": ("FLOAT", {"default": 0.08, "min": 0.001, "max": 0.75, "step": 0.001}),
                "amplitude_px": ("FLOAT", {"default": 14.0, "min": -128.0, "max": 128.0, "step": 0.25}),
                "ring_hardness": ("FLOAT", {"default": 1.5, "min": 0.5, "max": 6.0, "step": 0.05}),
                "chroma_split_px": ("FLOAT", {"default": 1.2, "min": 0.0, "max": 16.0, "step": 0.05}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "shockwave_info")
    FUNCTION = "run"
    CATEGORY = FX_DISTORT

    def run(
        self,
        image: torch.Tensor,
        center_x: float = 0.5,
        center_y: float = 0.5,
        radius: float = 0.22,
        width: float = 0.08,
        amplitude_px: float = 14.0,
        ring_hardness: float = 1.5,
        chroma_split_px: float = 1.2,
        mix: float = 1.0,
        mask_feather: float = 4.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3]
        mix_value = float(np.clip(mix, 0.0, 1.0))
        amplitude = float(amplitude_px)

        if abs(amplitude) <= 1e-6 or mix_value <= 1e-6:
            passthrough = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
            matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
            out, out_mask, _ = apply_masked_output(
                image=image,
                fx_np=passthrough,
                matte_np=matte_np,
                mask=mask,
                mask_feather=mask_feather,
                invert_mask=invert_mask,
            )
            return (out, out_mask, "x1ShockwaveDistort: bypassed (amplitude or mix is 0)")

        device = batch.device
        dtype = batch.dtype
        base_grid = normalized_grid(int(h), int(w), device=device, dtype=dtype).unsqueeze(0).expand(int(b), -1, -1, -1)

        cx = (float(np.clip(center_x, 0.0, 1.0)) * 2.0) - 1.0
        cy = (float(np.clip(center_y, 0.0, 1.0)) * 2.0) - 1.0
        rad = float(max(0.0, radius)) * 2.0
        band = float(max(1e-4, width)) * 2.0
        hardness = float(max(0.5, ring_hardness))

        dx = base_grid[..., 0] - cx
        dy = base_grid[..., 1] - cy
        dist = torch.sqrt((dx * dx) + (dy * dy) + 1e-8)
        nx = dx / dist
        ny = dy / dist

        edge = torch.abs(dist - rad)
        ring = torch.clamp(1.0 - (edge / band), 0.0, 1.0)
        ring = torch.pow(ring, hardness)

        amp_x = amplitude * 2.0 / max(float(max(int(w) - 1, 1)), 1.0)
        amp_y = amplitude * 2.0 / max(float(max(int(h) - 1, 1)), 1.0)
        offset_x = nx * ring * amp_x
        offset_y = ny * ring * amp_y

        distortion_grid = base_grid.clone()
        distortion_grid[..., 0] = torch.clamp(distortion_grid[..., 0] + offset_x, -1.0, 1.0)
        distortion_grid[..., 1] = torch.clamp(distortion_grid[..., 1] + offset_y, -1.0, 1.0)

        split = float(max(0.0, chroma_split_px))
        split_x = split * 2.0 / max(float(max(int(w) - 1, 1)), 1.0)
        split_y = split * 2.0 / max(float(max(int(h) - 1, 1)), 1.0)
        red_grid = distortion_grid.clone()
        blue_grid = distortion_grid.clone()
        red_grid[..., 0] = torch.clamp(red_grid[..., 0] + (nx * ring * split_x), -1.0, 1.0)
        red_grid[..., 1] = torch.clamp(red_grid[..., 1] + (ny * ring * split_y), -1.0, 1.0)
        blue_grid[..., 0] = torch.clamp(blue_grid[..., 0] - (nx * ring * split_x), -1.0, 1.0)
        blue_grid[..., 1] = torch.clamp(blue_grid[..., 1] - (ny * ring * split_y), -1.0, 1.0)

        sampled = sample_rgb_grid(rgb, distortion_grid)
        if split > 1e-6:
            sampled_r = sample_rgb_grid(rgb[..., 0:1], red_grid)
            sampled_b = sample_rgb_grid(rgb[..., 2:3], blue_grid)
            sampled = torch.cat((sampled_r, sampled[..., 1:2], sampled_b), dim=-1)

        fx_rgb = torch.clamp((rgb * (1.0 - mix_value)) + (sampled * mix_value), 0.0, 1.0)
        fx_np = fx_rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        matte_np = torch.clamp(ring * mix_value, 0.0, 1.0).detach().cpu().numpy().astype(np.float32, copy=False)

        out, out_mask, coverage = apply_masked_output(
            image=image,
            fx_np=fx_np,
            matte_np=matte_np,
            mask=mask,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
        )
        info = (
            "x1ShockwaveDistort: center=({:.3f},{:.3f}), radius={:.3f}, width={:.3f}, amplitude={:.2f}px, "
            "ring_hardness={:.2f}, chroma_split={:.2f}px, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            float(np.clip(center_x, 0.0, 1.0)),
            float(np.clip(center_y, 0.0, 1.0)),
            float(max(0.0, radius)),
            float(max(0.001, width)),
            amplitude,
            hardness,
            split,
            mix_value,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out, out_mask, info)
