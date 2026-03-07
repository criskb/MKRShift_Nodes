import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

from .categories import FX_PLAY
from .xshared import mask_to_batch as _mask_to_batch, to_image_batch as _to_image_batch


@dataclass(frozen=True)
class PaletteSet:
    low: Tuple[float, float, float]
    mid: Tuple[float, float, float]
    high: Tuple[float, float, float]
    glow: Tuple[float, float, float]


PALETTES: Dict[str, PaletteSet] = {
    "aurora": PaletteSet(
        low=(0.03, 0.07, 0.18),
        mid=(0.10, 0.50, 0.68),
        high=(0.48, 0.96, 0.61),
        glow=(0.64, 0.82, 1.00),
    ),
    "sunset": PaletteSet(
        low=(0.13, 0.04, 0.08),
        mid=(0.86, 0.24, 0.30),
        high=(1.00, 0.62, 0.18),
        glow=(1.00, 0.84, 0.49),
    ),
    "cyber": PaletteSet(
        low=(0.03, 0.02, 0.07),
        mid=(0.45, 0.10, 0.86),
        high=(0.07, 0.98, 0.89),
        glow=(1.00, 0.34, 0.92),
    ),
    "toxic": PaletteSet(
        low=(0.05, 0.08, 0.02),
        mid=(0.24, 0.54, 0.06),
        high=(0.86, 1.00, 0.15),
        glow=(0.94, 1.00, 0.44),
    ),
    "mono": PaletteSet(
        low=(0.03, 0.03, 0.03),
        mid=(0.40, 0.40, 0.40),
        high=(0.90, 0.90, 0.90),
        glow=(1.00, 1.00, 1.00),
    ),
}


@lru_cache(maxsize=12)
def _uv_grid(h: int, w: int) -> Tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)
    return np.meshgrid(x, y)


def _value_noise(h: int, w: int, cell_size: float, seed: int) -> np.ndarray:
    cell = max(1.0, float(cell_size))
    grid_h = max(2, int(math.ceil(h / cell)) + 2)
    grid_w = max(2, int(math.ceil(w / cell)) + 2)
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    grid = rng.random((grid_h, grid_w), dtype=np.float32)
    noise = Image.fromarray((grid * 255.0).astype(np.uint8), mode="L").resize((w, h), resample=Image.Resampling.BICUBIC)
    return np.asarray(noise, dtype=np.float32) / 255.0


def _fractal_noise(h: int, w: int, base_scale: float, octaves: int, seed: int) -> np.ndarray:
    layers = max(1, min(7, int(octaves)))
    scale = max(2.0, float(base_scale))
    out = np.zeros((h, w), dtype=np.float32)
    weight = 1.0
    weight_sum = 0.0
    for idx in range(layers):
        octave_scale = max(1.0, scale / (2.0 ** idx))
        out += _value_noise(h, w, octave_scale, seed + idx * 131) * weight
        weight_sum += weight
        weight *= 0.56
    if weight_sum <= 1e-8:
        return out
    return out / weight_sum


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    denom = max(1e-6, edge1 - edge0)
    t = np.clip((x - edge0) / denom, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _lerp3(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return a * (1.0 - t[..., None]) + b * t[..., None]


def _render_aura(
    h: int,
    w: int,
    palette: PaletteSet,
    intensity: float,
    contrast: float,
    noise_scale: float,
    swirl: float,
    sparkle: float,
    seed: int,
) -> np.ndarray:
    x, y = _uv_grid(h, w)
    xx = (x - 0.5) * 2.0
    yy = (y - 0.5) * 2.0
    radius = np.sqrt(xx * xx + yy * yy)

    n_base = _fractal_noise(h, w, noise_scale, 5, seed)
    n_detail = _fractal_noise(h, w, max(2.0, noise_scale * 0.35), 4, seed + 947)

    angle = np.arctan2(yy, xx)
    flow = np.sin((xx * 1.8 + yy * 0.9 + n_base * (4.0 + swirl * 3.2)) * math.pi + angle * swirl * 0.7)
    flow = 0.5 + 0.5 * flow

    band = np.clip((flow * 0.75) + (n_detail * 0.35), 0.0, 1.0)
    lift = np.clip(1.0 - np.power(np.clip(radius, 0.0, 1.6), 1.35), 0.0, 1.0)
    aura = np.clip((band * 0.70) + (lift * 0.30), 0.0, 1.0)

    low = np.asarray(palette.low, dtype=np.float32)
    mid = np.asarray(palette.mid, dtype=np.float32)
    high = np.asarray(palette.high, dtype=np.float32)
    glow = np.asarray(palette.glow, dtype=np.float32)

    base = _lerp3(low, mid, _smoothstep(0.12, 0.60, aura))
    hot = _lerp3(mid, high, _smoothstep(0.48, 0.92, aura))
    mix_hot = _smoothstep(0.28, 0.88, aura)
    rgb = _lerp3(base, hot, mix_hot)

    glow_mask = _smoothstep(0.58, 0.98, aura) * np.clip(1.15 - radius, 0.0, 1.0)
    rgb = np.clip(rgb + glow * (0.26 * glow_mask[..., None] * max(0.0, intensity)), 0.0, 1.0)

    sparkle_amt = max(0.0, float(sparkle))
    if sparkle_amt > 1e-6:
        spark_noise = _fractal_noise(h, w, max(1.0, noise_scale * 0.12), 2, seed + 2221)
        spark_mask = (spark_noise > (0.92 - 0.16 * min(1.0, sparkle_amt))).astype(np.float32)
        spark_color = np.asarray([1.0, 0.98, 0.92], dtype=np.float32)
        rgb = np.clip(rgb + spark_color * (spark_mask[..., None] * 0.38 * min(1.5, sparkle_amt)), 0.0, 1.0)

    c = max(0.2, float(contrast))
    rgb = np.clip((rgb - 0.5) * c + 0.5, 0.0, 1.0)
    rgb = np.clip(rgb * max(0.0, float(intensity)), 0.0, 1.0)
    return rgb.astype(np.float32, copy=False)


def _apply_slice_glitch(
    src_rgb: np.ndarray,
    slice_count: int,
    max_shift: int,
    direction: str,
    channel_split: float,
    scanline_jitter: float,
    grain: float,
    seed: int,
) -> np.ndarray:
    out = np.clip(src_rgb.astype(np.float32, copy=True), 0.0, 1.0)
    h, w = out.shape[:2]
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    max_shift_px = max(0, int(max_shift))
    count = max(1, int(slice_count))
    use_h = direction in {"horizontal", "both"}
    use_v = direction in {"vertical", "both"}

    for _ in range(count):
        if use_h and use_v:
            orient_h = bool(rng.integers(0, 2))
        else:
            orient_h = use_h

        if orient_h:
            band_h = int(rng.integers(max(1, h // 80), max(2, h // 8) + 1))
            y0 = int(rng.integers(0, max(1, h - band_h + 1)))
            shift = int(rng.integers(-max_shift_px, max_shift_px + 1)) if max_shift_px > 0 else 0
            out[y0 : y0 + band_h, :, :] = np.roll(out[y0 : y0 + band_h, :, :], shift=shift, axis=1)
        else:
            band_w = int(rng.integers(max(1, w // 80), max(2, w // 8) + 1))
            x0 = int(rng.integers(0, max(1, w - band_w + 1)))
            shift = int(rng.integers(-max_shift_px, max_shift_px + 1)) if max_shift_px > 0 else 0
            out[:, x0 : x0 + band_w, :] = np.roll(out[:, x0 : x0 + band_w, :], shift=shift, axis=0)

    split = max(0.0, float(channel_split))
    if split > 1e-6 and max_shift_px > 0:
        amp = max(1, int(round(max_shift_px * split)))
        r_shift = int(rng.integers(-amp, amp + 1))
        g_shift = int(rng.integers(-max(1, amp // 2), max(1, amp // 2) + 1))
        b_shift = int(rng.integers(-amp, amp + 1))
        red = np.roll(out[..., 0], shift=r_shift, axis=1)
        green = np.roll(out[..., 1], shift=g_shift, axis=0)
        blue = np.roll(out[..., 2], shift=-b_shift, axis=1)
        out = np.stack([red, green, blue], axis=-1)

    jitter = max(0.0, float(scanline_jitter))
    if jitter > 1e-6:
        lines = int(round((h * 0.10) * min(1.0, jitter)))
        for _ in range(max(1, lines)):
            y = int(rng.integers(0, h))
            bright = float(0.70 + rng.random() * 0.75)
            out[y : y + 1, :, :] = np.clip(out[y : y + 1, :, :] * bright, 0.0, 1.0)

    grain_amt = max(0.0, float(grain))
    if grain_amt > 1e-6:
        noise = rng.normal(0.0, grain_amt * 0.08, size=out.shape).astype(np.float32)
        out = np.clip(out + noise, 0.0, 1.0)

    return out.astype(np.float32, copy=False)


class x1Kaleido:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "segments": ("INT", {"default": 6, "min": 2, "max": 32, "step": 1}),
                "rotation": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.1}),
                "spin": ("FLOAT", {"default": 35.0, "min": -540.0, "max": 540.0, "step": 0.1}),
                "zoom": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "kaleido_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

    def run(
        self,
        image: torch.Tensor,
        segments: int = 6,
        rotation: float = 0.0,
        spin: float = 35.0,
        zoom: float = 1.0,
        center_x: float = 0.5,
        center_y: float = 0.5,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape

        mix_clamped = float(min(1.0, max(0.0, mix)))
        seg = max(2, int(segments))
        zoom_v = max(0.1, float(zoom))

        device = batch.device
        dtype = batch.dtype

        ys = torch.linspace(0.0, 1.0, int(h), device=device, dtype=dtype)
        xs = torch.linspace(0.0, 1.0, int(w), device=device, dtype=dtype)
        yy, xx = torch.meshgrid(ys, xs, indexing="ij")

        x = (xx - float(center_x)) * 2.0
        y = (yy - float(center_y)) * 2.0
        r = torch.sqrt((x * x) + (y * y) + 1e-12)
        theta = torch.atan2(y, x)

        theta = theta + math.radians(float(rotation)) + (r * math.radians(float(spin)))
        sector = (2.0 * math.pi) / float(seg)
        fold = torch.remainder(theta, sector)
        half_sector = sector * 0.5
        fold = torch.where(fold > half_sector, sector - fold, fold)

        src_r = r / zoom_v
        sx = torch.cos(fold) * src_r
        sy = torch.sin(fold) * src_r

        u = (sx * 0.5) + float(center_x)
        v = (sy * 0.5) + float(center_y)
        grid_x = (u * 2.0) - 1.0
        grid_y = (v * 2.0) - 1.0
        grid = torch.stack([grid_x, grid_y], dim=-1).unsqueeze(0).expand(int(b), -1, -1, -1)

        rgb = batch[..., :3]
        rgb_bchw = rgb.permute(0, 3, 1, 2)
        warped = F.grid_sample(rgb_bchw, grid, mode="bilinear", padding_mode="border", align_corners=True)
        warped_rgb = warped.permute(0, 2, 3, 1)
        fx_rgb = torch.clamp((rgb * (1.0 - mix_clamped)) + (warped_rgb * mix_clamped), 0.0, 1.0)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        ).unsqueeze(-1)
        out_rgb = torch.clamp((rgb * (1.0 - mask_batch)) + (fx_rgb * mask_batch), 0.0, 1.0)

        if c == 4:
            out = torch.cat([out_rgb, batch[..., 3:4]], dim=-1)
        else:
            out = out_rgb

        coverage = float(mask_batch.mean().item())
        info = (
            "x1Kaleido: segments={}, rotation={:.1f}deg, spin={:.1f}deg, zoom={:.2f}, "
            "center=({:.3f},{:.3f}), mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            seg,
            float(rotation),
            float(spin),
            zoom_v,
            float(center_x),
            float(center_y),
            mix_clamped,
            float(max(0.0, mask_feather)),
            coverage * 100.0,
            " (inverted)" if invert_mask else "",
        )
        return (out, mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1Glitch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "slice_count": ("INT", {"default": 28, "min": 1, "max": 512, "step": 1}),
                "max_shift": ("INT", {"default": 80, "min": 0, "max": 1024, "step": 1}),
                "direction": (["horizontal", "vertical", "both"],),
                "channel_split": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "scanline_jitter": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "grain": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01}),
                "seed": ("INT", {"default": 1337, "min": 0, "max": 99999999, "step": 1}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "glitch_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

    def run(
        self,
        image: torch.Tensor,
        slice_count: int = 28,
        max_shift: int = 80,
        direction: str = "both",
        channel_split: float = 0.35,
        scanline_jitter: float = 0.25,
        grain: float = 0.08,
        seed: int = 1337,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(rgb_np)

        for idx in range(int(b)):
            out_np[idx] = _apply_slice_glitch(
                src_rgb=rgb_np[idx],
                slice_count=int(slice_count),
                max_shift=int(max_shift),
                direction=str(direction),
                channel_split=float(channel_split),
                scanline_jitter=float(scanline_jitter),
                grain=float(grain),
                seed=int(seed) + idx * 7919,
            )

        fx_rgb = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
            dtype=batch.dtype,
        ).unsqueeze(-1)
        base_rgb = batch[..., :3]
        out_rgb = torch.clamp((base_rgb * (1.0 - mask_batch)) + (fx_rgb * mask_batch), 0.0, 1.0)
        if c == 4:
            out = torch.cat([out_rgb, batch[..., 3:4]], dim=-1)
        else:
            out = out_rgb

        coverage = float(mask_batch.mean().item())
        info = (
            "x1Glitch: slices={}, shift={}px, direction={}, channel_split={:.2f}, "
            "scanline_jitter={:.2f}, grain={:.2f}, seed={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            int(max(1, slice_count)),
            int(max(0, max_shift)),
            str(direction),
            float(max(0.0, min(1.0, channel_split))),
            float(max(0.0, min(1.0, scanline_jitter))),
            float(max(0.0, grain)),
            int(max(0, seed)),
            float(max(0.0, mask_feather)),
            coverage * 100.0,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1AuraFlow:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 8}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 8}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 24, "step": 1}),
                "palette": (list(PALETTES.keys()),),
                "intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.1, "min": 0.2, "max": 3.0, "step": 0.01}),
                "noise_scale": ("FLOAT", {"default": 92.0, "min": 2.0, "max": 512.0, "step": 1.0}),
                "swirl": ("FLOAT", {"default": 1.1, "min": 0.0, "max": 3.0, "step": 0.01}),
                "sparkle": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.5, "step": 0.01}),
                "seed": ("INT", {"default": 2024, "min": 0, "max": 99999999, "step": 1}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "aura_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

    def run(
        self,
        width: int = 1024,
        height: int = 1024,
        batch_size: int = 1,
        palette: str = "aurora",
        intensity: float = 1.0,
        contrast: float = 1.1,
        noise_scale: float = 92.0,
        swirl: float = 1.1,
        sparkle: float = 0.35,
        seed: int = 2024,
        image: Optional[torch.Tensor] = None,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        w = int(max(64, width))
        h = int(max(64, height))
        b = int(max(1, batch_size))
        target_device = None
        target_dtype = torch.float32

        if image is not None and torch.is_tensor(image):
            ref = _to_image_batch(image)
            _, h, w, _ = ref.shape
            target_device = ref.device
            target_dtype = ref.dtype

        palette_key = str(palette) if str(palette) in PALETTES else "aurora"
        palette_set = PALETTES[palette_key]

        out_np = np.empty((b, h, w, 3), dtype=np.float32)
        for idx in range(b):
            out_np[idx] = _render_aura(
                h=h,
                w=w,
                palette=palette_set,
                intensity=float(intensity),
                contrast=float(contrast),
                noise_scale=float(noise_scale),
                swirl=float(swirl),
                sparkle=float(sparkle),
                seed=int(seed) + idx * 3571,
            )

        out = torch.from_numpy(out_np)
        if target_device is not None:
            out = out.to(device=target_device, dtype=target_dtype)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=out.device,
            dtype=out.dtype,
        ).unsqueeze(-1)
        out = torch.clamp(out * mask_batch, 0.0, 1.0)
        coverage = float(mask_batch.mean().item())
        info = (
            "x1AuraFlow: {}x{} x{}, palette={}, intensity={:.2f}, contrast={:.2f}, "
            "noise_scale={:.1f}, swirl={:.2f}, sparkle={:.2f}, seed={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            w,
            h,
            b,
            palette_key,
            float(max(0.0, intensity)),
            float(max(0.2, contrast)),
            float(max(2.0, noise_scale)),
            float(max(0.0, swirl)),
            float(max(0.0, sparkle)),
            int(max(0, seed)),
            float(max(0.0, mask_feather)),
            coverage * 100.0,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)
