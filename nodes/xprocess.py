import json
import math
from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import torch

from ..categories import FX_PHOTO, FX_STYLIZE
from ..lib.settings_bundle import parse_settings_payload


@dataclass(frozen=True)
class ProcessSettings:
    exposure: float
    contrast: float
    saturation: float
    tone_warmth: float
    tone_fade: float
    pixelate_size: int
    posterize_bits: int
    halftone_strength: float
    halftone_size: int
    stylize_ink_strength: float
    stylize_ink_threshold: float
    film_grain_strength: float
    film_grain_size: float
    film_grain_seed: int
    film_grain_chroma: float
    vignette_strength: float
    vignette_roundness: float
    fractal_strength: float
    fractal_scale: float
    fractal_octaves: int
    fractal_seed: int
    fractal_contrast: float
    fractal_drift: float
    bokeh_strength: float
    bokeh_radius: float
    bokeh_threshold: float
    bokeh_softness: float
    bokeh_warmth: float
    rgb_shift_x: int
    rgb_shift_y: int
    prismatic_strength: float
    prismatic_distance: float
    prismatic_angle: float
    chromatic_edge_weight: float
    chromatic_green_shift: float
    bloom_strength: float
    bloom_radius: float
    bloom_threshold: float
    bloom_softness: float
    bloom_warmth: float
    blur_radius: float
    sharpen: float


def _to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")
    t = image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(t.shape)}")
    if t.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(t.shape)}")
    return t.clamp(0.0, 1.0)


def _mask_to_batch(
    mask: Optional[torch.Tensor],
    batch: int,
    h: int,
    w: int,
    feather_radius: float,
    invert_mask: bool,
    device: torch.device,
) -> torch.Tensor:
    if mask is None:
        out = torch.ones((batch, h, w), dtype=torch.float32)
        return out.to(device=device)

    if not torch.is_tensor(mask):
        raise TypeError("mask input is not a torch tensor")

    m = mask.detach().float().cpu()

    if m.ndim == 2:
        m = m.unsqueeze(0)
    elif m.ndim == 4:
        if m.shape[-1] in (1, 3, 4):
            m = m[..., 0]
        elif m.shape[1] in (1, 3, 4):
            m = m[:, 0, ...]
        else:
            raise ValueError(f"Unsupported MASK shape={tuple(m.shape)}")
    elif m.ndim != 3:
        raise ValueError(f"Unsupported MASK dims={m.ndim}")

    if m.shape[0] == 1 and batch > 1:
        m = m.expand(batch, -1, -1)
    elif m.shape[0] != batch:
        raise ValueError(f"Mask batch {m.shape[0]} does not match image batch {batch}")

    out_np = np.zeros((batch, h, w), dtype=np.float32)
    do_feather = feather_radius > 0.0
    feather = float(max(0.0, feather_radius))

    for idx in range(batch):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        pil = Image.fromarray((sample * 255.0).astype(np.uint8), mode="L")
        if pil.size != (w, h):
            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
        if do_feather:
            pil = pil.filter(ImageFilter.GaussianBlur(radius=feather))
        out_np[idx] = np.asarray(pil, dtype=np.float32) / 255.0

    out = torch.from_numpy(np.clip(out_np, 0.0, 1.0))
    if invert_mask:
        out = 1.0 - out
    return out.to(device=device)


def _pil_from_rgb_float(rgb: np.ndarray) -> Image.Image:
    rgb_u8 = np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(rgb_u8, mode="RGB")


def _rgb_float_from_pil(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _shift_2d_clamped(channel: np.ndarray, dx: int, dy: int) -> np.ndarray:
    if channel.ndim != 2:
        raise ValueError("Expected 2D channel for RGB shift")
    h, w = channel.shape
    if h == 0 or w == 0 or (dx == 0 and dy == 0):
        return channel
    y_idx = np.clip(np.arange(h, dtype=np.int32) - int(dy), 0, h - 1)
    x_idx = np.clip(np.arange(w, dtype=np.int32) - int(dx), 0, w - 1)
    return channel[y_idx[:, None], x_idx[None, :]]


def _centered_xy_grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    return np.meshgrid(x, y)


def _value_noise(h: int, w: int, cell_size: float, seed: int) -> np.ndarray:
    cell = max(1.0, float(cell_size))
    grid_h = max(2, int(math.ceil(h / cell)) + 2)
    grid_w = max(2, int(math.ceil(w / cell)) + 2)
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    grid = rng.random((grid_h, grid_w), dtype=np.float32)
    grid_u8 = np.clip(grid * 255.0, 0.0, 255.0).astype(np.uint8)
    noise = Image.fromarray(grid_u8, mode="L").resize((w, h), resample=Image.Resampling.BICUBIC)
    return np.asarray(noise, dtype=np.float32) / 255.0


def _fractal_noise(h: int, w: int, base_scale: float, octaves: int, seed: int) -> np.ndarray:
    layers = max(1, min(8, int(octaves)))
    scale = max(2.0, float(base_scale))
    total = np.zeros((h, w), dtype=np.float32)
    weight_sum = 0.0
    weight = 1.0
    for oct_idx in range(layers):
        octave_scale = max(1.0, scale / (2.0 ** oct_idx))
        layer = _value_noise(h, w, octave_scale, seed + oct_idx * 97)
        total += layer * weight
        weight_sum += weight
        weight *= 0.55
    if weight_sum <= 1e-8:
        return total
    return total / weight_sum


def _apply_effects(src_rgb: np.ndarray, settings: ProcessSettings) -> np.ndarray:
    out = np.clip(src_rgb.astype(np.float32, copy=False), 0.0, 1.0)

    if abs(settings.exposure) > 1e-6:
        out = np.clip(out * (2.0 ** settings.exposure), 0.0, 1.0)

    if abs(settings.contrast - 1.0) > 1e-6:
        out = _rgb_float_from_pil(ImageEnhance.Contrast(_pil_from_rgb_float(out)).enhance(settings.contrast))

    if abs(settings.saturation - 1.0) > 1e-6:
        out = _rgb_float_from_pil(ImageEnhance.Color(_pil_from_rgb_float(out)).enhance(settings.saturation))

    if abs(settings.tone_warmth) > 1e-6:
        warmth = float(max(-1.0, min(1.0, settings.tone_warmth)))
        warmed = out.copy()
        if warmth >= 0.0:
            warmed[..., 0] = np.clip(warmed[..., 0] + ((1.0 - warmed[..., 0]) * warmth * 0.18), 0.0, 1.0)
            warmed[..., 1] = np.clip(warmed[..., 1] + ((1.0 - warmed[..., 1]) * warmth * 0.04), 0.0, 1.0)
            warmed[..., 2] = np.clip(warmed[..., 2] * (1.0 - warmth * 0.14), 0.0, 1.0)
        else:
            cool = abs(warmth)
            warmed[..., 0] = np.clip(warmed[..., 0] * (1.0 - cool * 0.16), 0.0, 1.0)
            warmed[..., 1] = np.clip(warmed[..., 1] + ((1.0 - warmed[..., 1]) * cool * 0.03), 0.0, 1.0)
            warmed[..., 2] = np.clip(warmed[..., 2] + ((1.0 - warmed[..., 2]) * cool * 0.18), 0.0, 1.0)
        out = np.clip(warmed, 0.0, 1.0)

    if settings.tone_fade > 1e-6:
        fade = float(min(1.0, max(0.0, settings.tone_fade)))
        faded = np.clip((out * (1.0 - 0.18 * fade)) + (0.08 * fade), 0.0, 1.0)
        out = np.clip((out * (1.0 - fade)) + (faded * fade), 0.0, 1.0)

    if settings.posterize_bits < 8:
        bits = int(min(8, max(1, settings.posterize_bits)))
        out = _rgb_float_from_pil(ImageOps.posterize(_pil_from_rgb_float(out), bits=bits))

    if settings.pixelate_size > 1:
        pixel_block = int(max(1, settings.pixelate_size))
        h, w = out.shape[:2]
        small_w = max(1, int(round(w / pixel_block)))
        small_h = max(1, int(round(h / pixel_block)))
        out = _rgb_float_from_pil(
            _pil_from_rgb_float(out)
            .resize((small_w, small_h), resample=Image.Resampling.BILINEAR)
            .resize((w, h), resample=Image.Resampling.NEAREST)
        )

    if settings.halftone_strength > 1e-6:
        h, w = out.shape[:2]
        cell = int(max(2, settings.halftone_size))
        x = (((np.arange(w, dtype=np.float32) + 0.5) % cell) / float(cell)) - 0.5
        y = (((np.arange(h, dtype=np.float32) + 0.5) % cell) / float(cell)) - 0.5
        xx, yy = np.meshgrid(x, y)
        dist = np.sqrt(xx * xx + yy * yy)
        luminance = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        radius = 0.08 + 0.43 * (1.0 - np.clip(luminance, 0.0, 1.0))
        dots = (dist <= radius).astype(np.float32)
        halftone = out * (0.45 + 0.55 * dots[..., None])
        mix = float(min(1.0, max(0.0, settings.halftone_strength)))
        out = np.clip(out * (1.0 - mix) + halftone * mix, 0.0, 1.0)

    if settings.stylize_ink_strength > 1e-6:
        lum = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        dx = np.abs(np.roll(lum, -1, axis=1) - lum)
        dy = np.abs(np.roll(lum, -1, axis=0) - lum)
        edge = np.sqrt((dx * dx) + (dy * dy))
        thr = float(min(1.0, max(0.0, settings.stylize_ink_threshold))) * 0.35
        ink_mask = np.clip((edge - thr) / max(1e-6, 0.48 - thr), 0.0, 1.0).astype(np.float32, copy=False)
        ink_mix = float(min(1.0, max(0.0, settings.stylize_ink_strength)))
        ink_dark = 1.0 - (ink_mask[..., None] * ink_mix * 0.82)
        out = np.clip(out * ink_dark, 0.0, 1.0)

    if settings.film_grain_strength > 1e-6:
        h, w = out.shape[:2]
        grain = _fractal_noise(
            h=h,
            w=w,
            base_scale=max(2.0, settings.film_grain_size),
            octaves=3,
            seed=settings.film_grain_seed,
        ) - 0.5
        luminance = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        shadow_weight = 0.35 + 0.65 * (1.0 - np.clip(luminance, 0.0, 1.0))
        grain_mono = np.repeat(grain[..., None], 3, axis=-1)
        grain_rgb = np.stack(
            [
                grain,
                np.roll(grain, 1, axis=1),
                np.roll(grain, -1, axis=0),
            ],
            axis=-1,
        )
        chroma_mix = float(min(1.0, max(0.0, settings.film_grain_chroma)))
        grain_rgb = (grain_mono * (1.0 - chroma_mix)) + (grain_rgb * chroma_mix)
        out = np.clip(
            out + grain_rgb * (0.22 * settings.film_grain_strength) * shadow_weight[..., None],
            0.0,
            1.0,
        )

    if settings.vignette_strength > 1e-6:
        h, w = out.shape[:2]
        xx, yy = _centered_xy_grid(h, w)
        radius = np.sqrt(xx * xx + yy * yy)
        softness = max(0.2, settings.vignette_roundness)
        edge = np.clip((radius - 0.18) / max(1e-6, 0.92), 0.0, 1.0)
        falloff = np.power(edge, 1.1 * softness)
        vignette = 1.0 - np.clip(settings.vignette_strength * falloff, 0.0, 1.0)
        out = np.clip(out * vignette[..., None], 0.0, 1.0)

    if settings.fractal_strength > 1e-6:
        h, w = out.shape[:2]
        noise = _fractal_noise(
            h=h,
            w=w,
            base_scale=settings.fractal_scale,
            octaves=settings.fractal_octaves,
            seed=settings.fractal_seed,
        )
        contrast = float(max(0.1, settings.fractal_contrast))
        n = (noise - 0.5) * contrast
        drift_px = int(max(0, round(settings.fractal_drift * 12.0)))
        chroma = np.stack(
            [
                np.roll(n, max(1, drift_px), axis=1),
                n,
                np.roll(n, -max(1, drift_px), axis=0),
            ],
            axis=-1,
        )
        out = np.clip(out + chroma * (0.45 * settings.fractal_strength), 0.0, 1.0)

    if settings.bloom_strength > 1e-6 and settings.bloom_radius > 1e-6:
        threshold = float(min(1.0, max(0.0, settings.bloom_threshold)))
        denom = max(1e-6, 1.0 - threshold)
        highlights = np.clip((out - threshold) / denom, 0.0, 1.0)
        softness = float(min(1.0, max(0.0, settings.bloom_softness)))
        bloom_a = _rgb_float_from_pil(
            _pil_from_rgb_float(highlights).filter(ImageFilter.GaussianBlur(radius=settings.bloom_radius))
        )
        bloom_b = _rgb_float_from_pil(
            _pil_from_rgb_float(highlights).filter(ImageFilter.GaussianBlur(radius=settings.bloom_radius * (1.5 + softness * 1.7)))
        )
        bloom = np.clip((bloom_a * (0.82 - softness * 0.22)) + (bloom_b * (0.18 + softness * 0.22)), 0.0, 1.0)
        warmth = float(max(-1.0, min(1.0, settings.bloom_warmth)))
        if abs(warmth) > 1e-6:
            if warmth >= 0.0:
                tint = np.asarray([1.0 + warmth * 0.22, 1.0 + warmth * 0.05, 1.0 - warmth * 0.16], dtype=np.float32)
            else:
                cool = abs(warmth)
                tint = np.asarray([1.0 - cool * 0.16, 1.0 + cool * 0.04, 1.0 + cool * 0.22], dtype=np.float32)
            bloom = np.clip(bloom * tint[None, None, :], 0.0, 1.0)
        out = np.clip(out + bloom * settings.bloom_strength, 0.0, 1.0)

    if settings.bokeh_strength > 1e-6 and settings.bokeh_radius > 1e-6:
        luminance = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        threshold = float(min(1.0, max(0.0, settings.bokeh_threshold)))
        denom = max(1e-6, 1.0 - threshold)
        highlights = np.clip((luminance - threshold) / denom, 0.0, 1.0)
        source = out * highlights[..., None]
        softness = float(min(1.0, max(0.0, settings.bokeh_softness)))
        blur_a = _rgb_float_from_pil(_pil_from_rgb_float(source).filter(ImageFilter.GaussianBlur(settings.bokeh_radius)))
        blur_b = _rgb_float_from_pil(
            _pil_from_rgb_float(source).filter(ImageFilter.GaussianBlur(settings.bokeh_radius * (1.4 + softness * 1.3)))
        )
        bokeh = np.clip(blur_a * (0.76 - softness * 0.22) + blur_b * (0.24 + softness * 0.22), 0.0, 1.0)
        warmth = float(max(-1.0, min(1.0, settings.bokeh_warmth)))
        if abs(warmth) > 1e-6:
            if warmth >= 0.0:
                tint = np.asarray([1.0 + warmth * 0.18, 1.0 + warmth * 0.06, 1.0 - warmth * 0.14], dtype=np.float32)
            else:
                cool = abs(warmth)
                tint = np.asarray([1.0 - cool * 0.12, 1.0 + cool * 0.05, 1.0 + cool * 0.18], dtype=np.float32)
            bokeh = np.clip(bokeh * tint[None, None, :], 0.0, 1.0)
        out = np.clip(out + bokeh * settings.bokeh_strength, 0.0, 1.0)

    if settings.blur_radius > 1e-6:
        out = _rgb_float_from_pil(_pil_from_rgb_float(out).filter(ImageFilter.GaussianBlur(radius=settings.blur_radius)))

    if settings.sharpen > 1e-6:
        percent = int(min(500, max(1, round(settings.sharpen * 220.0))))
        sharpen_radius = max(0.5, min(5.0, 1.0 + settings.sharpen * 1.5))
        out = _rgb_float_from_pil(
            _pil_from_rgb_float(out).filter(ImageFilter.UnsharpMask(radius=sharpen_radius, percent=percent, threshold=2))
        )

    if settings.rgb_shift_x != 0 or settings.rgb_shift_y != 0:
        dx = int(settings.rgb_shift_x)
        dy = int(settings.rgb_shift_y)
        red = _shift_2d_clamped(out[..., 0], dx, dy)
        green = _shift_2d_clamped(
            out[..., 1],
            int(round(dx * settings.chromatic_green_shift * 0.5)),
            int(round(dy * settings.chromatic_green_shift * 0.5)),
        )
        blue = _shift_2d_clamped(out[..., 2], -dx, -dy)
        shifted = np.stack([red, green, blue], axis=-1)
        h, w = out.shape[:2]
        xx, yy = _centered_xy_grid(h, w)
        lens = np.sqrt(xx * xx + yy * yy)
        lens = np.clip((lens - 0.05) / 1.15, 0.0, 1.0).astype(np.float32, copy=False)
        edge_weight = float(min(1.0, max(0.0, settings.chromatic_edge_weight)))
        weight = (1.0 - edge_weight) + (lens * edge_weight)
        out = np.clip((out * (1.0 - weight[..., None])) + (shifted * weight[..., None]), 0.0, 1.0)

    if settings.prismatic_strength > 1e-6 and settings.prismatic_distance > 1e-6:
        theta = math.radians(settings.prismatic_angle % 360.0)
        dist = settings.prismatic_distance * min(2.0, max(0.0, settings.prismatic_strength))
        dx = int(round(math.cos(theta) * dist))
        dy = int(round(math.sin(theta) * dist))
        if dx != 0 or dy != 0:
            red = _shift_2d_clamped(out[..., 0], dx, dy)
            green = _shift_2d_clamped(
                out[..., 1],
                int(round(dx * (0.35 + settings.chromatic_green_shift * 0.2))),
                int(round(dy * (0.35 + settings.chromatic_green_shift * 0.2))),
            )
            blue = _shift_2d_clamped(out[..., 2], -dx, -dy)
            prism = np.stack([red, green, blue], axis=-1)
            mix = min(1.0, max(0.0, settings.prismatic_strength))
            h, w = out.shape[:2]
            xx, yy = _centered_xy_grid(h, w)
            lens = np.sqrt(xx * xx + yy * yy)
            lens = np.clip((lens - 0.05) / 1.15, 0.0, 1.0).astype(np.float32, copy=False)
            edge_weight = float(min(1.0, max(0.0, settings.chromatic_edge_weight)))
            weight = ((1.0 - edge_weight) + (lens * edge_weight)) * mix
            out = np.clip(out * (1.0 - weight[..., None]) + prism * weight[..., None], 0.0, 1.0)
            if settings.prismatic_strength > 1.0:
                boost = min(1.0, (settings.prismatic_strength - 1.0) * 0.5)
                out = np.clip(out + (prism - out) * boost, 0.0, 1.0)

    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


_DEFAULT_PROCESS_SETTINGS = ProcessSettings(
    exposure=0.0,
    contrast=1.0,
    saturation=1.0,
    tone_warmth=0.0,
    tone_fade=0.0,
    pixelate_size=1,
    posterize_bits=8,
    halftone_strength=0.0,
    halftone_size=8,
    stylize_ink_strength=0.0,
    stylize_ink_threshold=0.28,
    film_grain_strength=0.0,
    film_grain_size=32.0,
    film_grain_seed=42,
    film_grain_chroma=0.35,
    vignette_strength=0.0,
    vignette_roundness=1.2,
    fractal_strength=0.0,
    fractal_scale=96.0,
    fractal_octaves=4,
    fractal_seed=23,
    fractal_contrast=1.0,
    fractal_drift=0.1,
    bokeh_strength=0.0,
    bokeh_radius=10.0,
    bokeh_threshold=0.72,
    bokeh_softness=0.5,
    bokeh_warmth=0.0,
    rgb_shift_x=0,
    rgb_shift_y=0,
    prismatic_strength=0.0,
    prismatic_distance=5.0,
    prismatic_angle=25.0,
    chromatic_edge_weight=0.65,
    chromatic_green_shift=0.0,
    bloom_strength=0.0,
    bloom_radius=14.0,
    bloom_threshold=0.7,
    bloom_softness=0.4,
    bloom_warmth=0.0,
    blur_radius=0.0,
    sharpen=0.0,
)


def _with_settings(**overrides) -> ProcessSettings:
    return replace(_DEFAULT_PROCESS_SETTINGS, **overrides)


def _mask_required_inputs():
    return {
        "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
        "invert_mask": ("BOOLEAN", {"default": False}),
    }


def _apply_settings_to_batch(
    image: torch.Tensor,
    settings: ProcessSettings,
    mask_feather: float,
    invert_mask: bool,
    mask: Optional[torch.Tensor],
):
    batch = _to_image_batch(image)
    b, h, w, c = batch.shape

    mask_batch = _mask_to_batch(
        mask=mask,
        batch=int(b),
        h=int(h),
        w=int(w),
        feather_radius=float(max(0.0, mask_feather)),
        invert_mask=bool(invert_mask),
        device=batch.device,
    ).unsqueeze(-1)

    rgb = batch[..., :3]
    alpha = batch[..., 3:4] if c == 4 else None

    out_rgb = torch.empty_like(rgb)
    rgb_np_batch = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
    for idx in range(int(b)):
        fx_np = _apply_effects(rgb_np_batch[idx], settings)
        fx_t = torch.from_numpy(fx_np).to(device=batch.device, dtype=batch.dtype)
        m = mask_batch[idx]
        out_rgb[idx] = (rgb[idx] * (1.0 - m)) + (fx_t * m)

    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb
    return out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), float(mask_batch.mean().item())


def _run_effect_node(
    label: str,
    detail: str,
    image: torch.Tensor,
    settings: ProcessSettings,
    mask_feather: float,
    invert_mask: bool,
    mask: Optional[torch.Tensor],
):
    out, out_mask, coverage = _apply_settings_to_batch(
        image=image,
        settings=settings,
        mask_feather=mask_feather,
        invert_mask=invert_mask,
        mask=mask,
    )
    info = (
        "{}: {}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
    ).format(
        label,
        detail,
        float(max(0.0, mask_feather)),
        coverage * 100.0,
        " (inverted)" if invert_mask else "",
    )
    return (out, out_mask, info)


_PIXEL_DOWNSAMPLE_MODES = {
    "box": Image.Resampling.BOX,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "nearest": Image.Resampling.NEAREST,
    "hamming": Image.Resampling.HAMMING,
    "lanczos": Image.Resampling.LANCZOS,
}
_PIXEL_UPSAMPLE_MODES = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
}


def _pixelate_rgb(
    src_rgb: np.ndarray,
    pixel_size_x: int,
    pixel_size_y: int,
    downsample_mode: str,
    upscale_mode: str,
    cell_blend: float,
    color_levels: int,
    grid_strength: float,
    grid_width: int,
) -> np.ndarray:
    h, w = src_rgb.shape[:2]
    px = max(1, int(pixel_size_x))
    py = max(1, int(pixel_size_y))
    down_w = max(1, int(round(w / float(px))))
    down_h = max(1, int(round(h / float(py))))

    down_filter = _PIXEL_DOWNSAMPLE_MODES.get(str(downsample_mode), Image.Resampling.BILINEAR)
    up_filter = _PIXEL_UPSAMPLE_MODES.get(str(upscale_mode), Image.Resampling.NEAREST)

    src_pil = _pil_from_rgb_float(np.clip(src_rgb, 0.0, 1.0))
    small = src_pil.resize((down_w, down_h), resample=down_filter)
    nearest = small.resize((w, h), resample=Image.Resampling.NEAREST)
    smooth = small.resize((w, h), resample=up_filter)

    blend = float(min(1.0, max(0.0, cell_blend)))
    out = _rgb_float_from_pil(nearest)
    if blend > 1e-6:
        smooth_np = _rgb_float_from_pil(smooth)
        out = np.clip(out * (1.0 - blend) + smooth_np * blend, 0.0, 1.0)

    levels = int(max(0, color_levels))
    if levels >= 2:
        out = np.clip(np.round(out * (levels - 1)) / float(levels - 1), 0.0, 1.0)

    g_strength = float(min(1.0, max(0.0, grid_strength)))
    g_width = int(max(0, grid_width))
    if g_strength > 1e-6 and g_width > 0:
        yy = np.arange(h, dtype=np.int32)[:, None]
        xx = np.arange(w, dtype=np.int32)[None, :]
        grid_mask = ((xx % px) < g_width) | ((yy % py) < g_width)
        darken = 1.0 - (0.88 * g_strength)
        out[grid_mask] *= darken

    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def _run_pixelate_node(
    image: torch.Tensor,
    pixel_size_x: int,
    pixel_size_y: int,
    downsample_mode: str,
    upscale_mode: str,
    cell_blend: float,
    color_levels: int,
    grid_strength: float,
    grid_width: int,
    mask_feather: float,
    invert_mask: bool,
    mask: Optional[torch.Tensor],
):
    batch = _to_image_batch(image)
    b, h, w, c = batch.shape

    mask_batch = _mask_to_batch(
        mask=mask,
        batch=int(b),
        h=int(h),
        w=int(w),
        feather_radius=float(max(0.0, mask_feather)),
        invert_mask=bool(invert_mask),
        device=batch.device,
    ).unsqueeze(-1)

    rgb = batch[..., :3]
    alpha = batch[..., 3:4] if c == 4 else None
    rgb_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
    fx_np = np.empty_like(rgb_np)

    for idx in range(int(b)):
        fx_np[idx] = _pixelate_rgb(
            src_rgb=rgb_np[idx],
            pixel_size_x=int(pixel_size_x),
            pixel_size_y=int(pixel_size_y),
            downsample_mode=str(downsample_mode),
            upscale_mode=str(upscale_mode),
            cell_blend=float(cell_blend),
            color_levels=int(color_levels),
            grid_strength=float(grid_strength),
            grid_width=int(grid_width),
        )

    fx = torch.from_numpy(fx_np).to(device=batch.device, dtype=batch.dtype)
    out_rgb = torch.clamp((rgb * (1.0 - mask_batch)) + (fx * mask_batch), 0.0, 1.0)
    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

    coverage = float(mask_batch.mean().item())
    info = (
        "x1Pixelate: size={}x{}px, down={}, up={}, cell_blend={:.2f}, color_levels={}, "
        "grid={:.2f}@{}px, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
    ).format(
        int(max(1, pixel_size_x)),
        int(max(1, pixel_size_y)),
        str(downsample_mode),
        str(upscale_mode),
        float(min(1.0, max(0.0, cell_blend))),
        int(max(0, color_levels)),
        float(min(1.0, max(0.0, grid_strength))),
        int(max(0, grid_width)),
        float(max(0.0, mask_feather)),
        coverage * 100.0,
        " (inverted)" if invert_mask else "",
    )
    return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1Tone:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "exposure": 0.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "tone_warmth": 0.0,
            "tone_fade": 0.0,
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
    RETURN_NAMES = ("image", "mask", "tone_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "exposure": {"min": -2.0, "max": 2.0},
                "contrast": {"min": 0.0, "max": 3.0},
                "saturation": {"min": 0.0, "max": 3.0},
                "tone_warmth": {"min": -1.0, "max": 1.0},
                "tone_fade": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            exposure=float(settings_payload["exposure"]),
            contrast=float(max(0.0, settings_payload["contrast"])),
            saturation=float(max(0.0, settings_payload["saturation"])),
            tone_warmth=float(settings_payload["tone_warmth"]),
            tone_fade=float(settings_payload["tone_fade"]),
        )
        detail = "exposure={:.2f}, contrast={:.2f}, saturation={:.2f}, warmth={:.2f}, fade={:.2f}".format(
            settings.exposure,
            settings.contrast,
            settings.saturation,
            settings.tone_warmth,
            settings.tone_fade,
        )
        return _run_effect_node(
            label="x1Tone",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Stylize:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "posterize_bits": 8,
            "halftone_strength": 0.0,
            "halftone_size": 8,
            "stylize_ink_strength": 0.0,
            "stylize_ink_threshold": 0.28,
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
    RETURN_NAMES = ("image", "mask", "stylize_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "posterize_bits": {"min": 1, "max": 8, "integer": True},
                "halftone_strength": {"min": 0.0, "max": 1.0},
                "halftone_size": {"min": 2, "max": 128, "integer": True},
                "stylize_ink_strength": {"min": 0.0, "max": 1.0},
                "stylize_ink_threshold": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            posterize_bits=int(min(8, max(1, settings_payload["posterize_bits"]))),
            halftone_strength=float(min(1.0, max(0.0, settings_payload["halftone_strength"]))),
            halftone_size=int(max(2, settings_payload["halftone_size"])),
            stylize_ink_strength=float(min(1.0, max(0.0, settings_payload["stylize_ink_strength"]))),
            stylize_ink_threshold=float(min(1.0, max(0.0, settings_payload["stylize_ink_threshold"]))),
        )
        detail = "posterize={}bit, halftone={:.2f}@{}, ink={:.2f}(thr={:.2f})".format(
            settings.posterize_bits,
            settings.halftone_strength,
            settings.halftone_size,
            settings.stylize_ink_strength,
            settings.stylize_ink_threshold,
        )
        return _run_effect_node(
            label="x1Stylize",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Pixelate:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "pixel_size_x": 8,
            "pixel_size_y": 8,
            "downsample_mode": "box",
            "upscale_mode": "nearest",
            "cell_blend": 0.0,
            "color_levels": 0,
            "grid_strength": 0.0,
            "grid_width": 1,
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
    RETURN_NAMES = ("image", "mask", "pixelate_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "pixel_size_x": {"min": 1, "max": 256, "integer": True},
                "pixel_size_y": {"min": 1, "max": 256, "integer": True},
                "cell_blend": {"min": 0.0, "max": 1.0},
                "color_levels": {"min": 0, "max": 64, "integer": True},
                "grid_strength": {"min": 0.0, "max": 1.0},
                "grid_width": {"min": 0, "max": 16, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        downsample_mode = str(settings_payload["downsample_mode"])
        if downsample_mode not in _PIXEL_DOWNSAMPLE_MODES:
            downsample_mode = "box"
        upscale_mode = str(settings_payload["upscale_mode"])
        if upscale_mode not in _PIXEL_UPSAMPLE_MODES:
            upscale_mode = "nearest"
        return _run_pixelate_node(
            image=image,
            pixel_size_x=int(max(1, settings_payload["pixel_size_x"])),
            pixel_size_y=int(max(1, settings_payload["pixel_size_y"])),
            downsample_mode=downsample_mode,
            upscale_mode=upscale_mode,
            cell_blend=float(settings_payload["cell_blend"]),
            color_levels=int(settings_payload["color_levels"]),
            grid_strength=float(settings_payload["grid_strength"]),
            grid_width=int(settings_payload["grid_width"]),
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Film:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "film_grain_strength": 0.0,
            "film_grain_size": 32.0,
            "film_grain_seed": 42,
            "film_grain_chroma": 0.35,
            "vignette_strength": 0.0,
            "vignette_roundness": 1.2,
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
    RETURN_NAMES = ("image", "mask", "film_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "film_grain_strength": {"min": 0.0, "max": 1.5},
                "film_grain_size": {"min": 2.0, "max": 256.0},
                "film_grain_seed": {"min": 0, "max": 999999, "integer": True},
                "film_grain_chroma": {"min": 0.0, "max": 1.0},
                "vignette_strength": {"min": 0.0, "max": 1.0},
                "vignette_roundness": {"min": 0.2, "max": 3.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            film_grain_strength=float(max(0.0, settings_payload["film_grain_strength"])),
            film_grain_size=float(max(2.0, settings_payload["film_grain_size"])),
            film_grain_seed=int(max(0, settings_payload["film_grain_seed"])),
            film_grain_chroma=float(min(1.0, max(0.0, settings_payload["film_grain_chroma"]))),
            vignette_strength=float(min(1.0, max(0.0, settings_payload["vignette_strength"]))),
            vignette_roundness=float(max(0.2, settings_payload["vignette_roundness"])),
        )
        detail = "grain={:.2f}(s{:.1f},seed{},chroma{:.2f}), vignette={:.2f}(r{:.2f})".format(
            settings.film_grain_strength,
            settings.film_grain_size,
            settings.film_grain_seed,
            settings.film_grain_chroma,
            settings.vignette_strength,
            settings.vignette_roundness,
        )
        return _run_effect_node(
            label="x1Film",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Fractal:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "fractal_strength": 0.0,
            "fractal_scale": 96.0,
            "fractal_octaves": 4,
            "fractal_seed": 23,
            "fractal_contrast": 1.0,
            "fractal_drift": 0.1,
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
    RETURN_NAMES = ("image", "mask", "fractal_info")
    FUNCTION = "run"
    CATEGORY = FX_STYLIZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "fractal_strength": {"min": 0.0, "max": 1.0},
                "fractal_scale": {"min": 2.0, "max": 1024.0},
                "fractal_octaves": {"min": 1, "max": 8, "integer": True},
                "fractal_seed": {"min": 0, "max": 999999, "integer": True},
                "fractal_contrast": {"min": 0.1, "max": 3.0},
                "fractal_drift": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            fractal_strength=float(min(1.0, max(0.0, settings_payload["fractal_strength"]))),
            fractal_scale=float(max(2.0, settings_payload["fractal_scale"])),
            fractal_octaves=int(min(8, max(1, settings_payload["fractal_octaves"]))),
            fractal_seed=int(max(0, settings_payload["fractal_seed"])),
            fractal_contrast=float(max(0.1, settings_payload["fractal_contrast"])),
            fractal_drift=float(min(1.0, max(0.0, settings_payload["fractal_drift"]))),
        )
        detail = "fractal={:.2f}(s{:.1f},o{},seed{},c{:.2f},d{:.2f})".format(
            settings.fractal_strength,
            settings.fractal_scale,
            settings.fractal_octaves,
            settings.fractal_seed,
            settings.fractal_contrast,
            settings.fractal_drift,
        )
        return _run_effect_node(
            label="x1Fractal",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Bloom:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "bloom_strength": 0.0,
            "bloom_radius": 14.0,
            "bloom_threshold": 0.7,
            "bloom_softness": 0.4,
            "bloom_warmth": 0.0,
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
    RETURN_NAMES = ("image", "mask", "bloom_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "bloom_strength": {"min": 0.0, "max": 2.0},
                "bloom_radius": {"min": 0.0, "max": 128.0},
                "bloom_threshold": {"min": 0.0, "max": 1.0},
                "bloom_softness": {"min": 0.0, "max": 1.0},
                "bloom_warmth": {"min": -1.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            bloom_strength=float(max(0.0, settings_payload["bloom_strength"])),
            bloom_radius=float(max(0.0, settings_payload["bloom_radius"])),
            bloom_threshold=float(min(1.0, max(0.0, settings_payload["bloom_threshold"]))),
            bloom_softness=float(min(1.0, max(0.0, settings_payload["bloom_softness"]))),
            bloom_warmth=float(max(-1.0, min(1.0, settings_payload["bloom_warmth"]))),
        )
        detail = "bloom={:.2f}@{:.1f}(thr={:.2f},soft={:.2f},warm={:.2f})".format(
            settings.bloom_strength,
            settings.bloom_radius,
            settings.bloom_threshold,
            settings.bloom_softness,
            settings.bloom_warmth,
        )
        return _run_effect_node(
            label="x1Bloom",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Bokeh:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "bokeh_strength": 0.0,
            "bokeh_radius": 10.0,
            "bokeh_threshold": 0.72,
            "bokeh_softness": 0.5,
            "bokeh_warmth": 0.0,
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
    RETURN_NAMES = ("image", "mask", "bokeh_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "bokeh_strength": {"min": 0.0, "max": 2.0},
                "bokeh_radius": {"min": 0.0, "max": 128.0},
                "bokeh_threshold": {"min": 0.0, "max": 1.0},
                "bokeh_softness": {"min": 0.0, "max": 1.0},
                "bokeh_warmth": {"min": -1.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            bokeh_strength=float(max(0.0, settings_payload["bokeh_strength"])),
            bokeh_radius=float(max(0.0, settings_payload["bokeh_radius"])),
            bokeh_threshold=float(min(1.0, max(0.0, settings_payload["bokeh_threshold"]))),
            bokeh_softness=float(min(1.0, max(0.0, settings_payload["bokeh_softness"]))),
            bokeh_warmth=float(max(-1.0, min(1.0, settings_payload["bokeh_warmth"]))),
        )
        detail = "bokeh={:.2f}@{:.1f}(thr={:.2f},soft={:.2f},warm={:.2f})".format(
            settings.bokeh_strength,
            settings.bokeh_radius,
            settings.bokeh_threshold,
            settings.bokeh_softness,
            settings.bokeh_warmth,
        )
        return _run_effect_node(
            label="x1Bokeh",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Chromatic:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "rgb_shift_x": 0,
            "rgb_shift_y": 0,
            "prismatic_strength": 0.0,
            "prismatic_distance": 5.0,
            "prismatic_angle": 25.0,
            "chromatic_edge_weight": 0.65,
            "chromatic_green_shift": 0.0,
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
    RETURN_NAMES = ("image", "mask", "chromatic_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "rgb_shift_x": {"min": -128, "max": 128, "integer": True},
                "rgb_shift_y": {"min": -128, "max": 128, "integer": True},
                "prismatic_strength": {"min": 0.0, "max": 2.0},
                "prismatic_distance": {"min": 0.0, "max": 128.0},
                "prismatic_angle": {"min": 0.0, "max": 360.0},
                "chromatic_edge_weight": {"min": 0.0, "max": 1.0},
                "chromatic_green_shift": {"min": -1.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            rgb_shift_x=int(settings_payload["rgb_shift_x"]),
            rgb_shift_y=int(settings_payload["rgb_shift_y"]),
            prismatic_strength=float(max(0.0, settings_payload["prismatic_strength"])),
            prismatic_distance=float(max(0.0, settings_payload["prismatic_distance"])),
            prismatic_angle=float(settings_payload["prismatic_angle"]),
            chromatic_edge_weight=float(min(1.0, max(0.0, settings_payload["chromatic_edge_weight"]))),
            chromatic_green_shift=float(max(-1.0, min(1.0, settings_payload["chromatic_green_shift"]))),
        )
        detail = "rgb_shift=({},{}), prismatic={:.2f}@{:.1f}px/{:.0f}deg, edge={:.2f}, green={:.2f}".format(
            settings.rgb_shift_x,
            settings.rgb_shift_y,
            settings.prismatic_strength,
            settings.prismatic_distance,
            settings.prismatic_angle,
            settings.chromatic_edge_weight,
            settings.chromatic_green_shift,
        )
        return _run_effect_node(
            label="x1Chromatic",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )


class x1Focus:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "blur_radius": 0.0,
            "sharpen": 0.0,
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
    RETURN_NAMES = ("image", "mask", "focus_info")
    FUNCTION = "run"
    CATEGORY = FX_PHOTO

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings_payload = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "blur_radius": {"min": 0.0, "max": 128.0},
                "sharpen": {"min": 0.0, "max": 2.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )
        settings = _with_settings(
            blur_radius=float(max(0.0, settings_payload["blur_radius"])),
            sharpen=float(max(0.0, settings_payload["sharpen"])),
        )
        detail = "blur={:.1f}px, sharpen={:.2f}".format(settings.blur_radius, settings.sharpen)
        return _run_effect_node(
            label="x1Focus",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=float(settings_payload["mask_feather"]),
            invert_mask=bool(settings_payload["invert_mask"]),
            mask=mask,
        )
