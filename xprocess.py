import math
from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import torch

from .categories import FX_PHOTO, FX_STYLIZE


@dataclass(frozen=True)
class ProcessSettings:
    exposure: float
    contrast: float
    saturation: float
    pixelate_size: int
    posterize_bits: int
    halftone_strength: float
    halftone_size: int
    film_grain_strength: float
    film_grain_size: float
    film_grain_seed: int
    vignette_strength: float
    vignette_roundness: float
    fractal_strength: float
    fractal_scale: float
    fractal_octaves: int
    fractal_seed: int
    bokeh_strength: float
    bokeh_radius: float
    bokeh_threshold: float
    rgb_shift_x: int
    rgb_shift_y: int
    prismatic_strength: float
    prismatic_distance: float
    prismatic_angle: float
    bloom_strength: float
    bloom_radius: float
    bloom_threshold: float
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
        grain_rgb = np.stack(
            [
                grain,
                np.roll(grain, 1, axis=1),
                np.roll(grain, -1, axis=0),
            ],
            axis=-1,
        )
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
        n = noise - 0.5
        chroma = np.stack(
            [
                np.roll(n, 1, axis=1),
                n,
                np.roll(n, -1, axis=0),
            ],
            axis=-1,
        )
        out = np.clip(out + chroma * (0.45 * settings.fractal_strength), 0.0, 1.0)

    if settings.bloom_strength > 1e-6 and settings.bloom_radius > 1e-6:
        threshold = float(min(1.0, max(0.0, settings.bloom_threshold)))
        denom = max(1e-6, 1.0 - threshold)
        highlights = np.clip((out - threshold) / denom, 0.0, 1.0)
        bloom = _rgb_float_from_pil(
            _pil_from_rgb_float(highlights).filter(ImageFilter.GaussianBlur(radius=settings.bloom_radius))
        )
        out = np.clip(out + bloom * settings.bloom_strength, 0.0, 1.0)

    if settings.bokeh_strength > 1e-6 and settings.bokeh_radius > 1e-6:
        luminance = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
        threshold = float(min(1.0, max(0.0, settings.bokeh_threshold)))
        denom = max(1e-6, 1.0 - threshold)
        highlights = np.clip((luminance - threshold) / denom, 0.0, 1.0)
        source = out * highlights[..., None]
        blur_a = _rgb_float_from_pil(_pil_from_rgb_float(source).filter(ImageFilter.GaussianBlur(settings.bokeh_radius)))
        blur_b = _rgb_float_from_pil(
            _pil_from_rgb_float(source).filter(ImageFilter.GaussianBlur(settings.bokeh_radius * 1.9))
        )
        bokeh = np.clip(blur_a * 0.68 + blur_b * 0.32, 0.0, 1.0)
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
        blue = _shift_2d_clamped(out[..., 2], -dx, -dy)
        out = np.stack([red, out[..., 1], blue], axis=-1)

    if settings.prismatic_strength > 1e-6 and settings.prismatic_distance > 1e-6:
        theta = math.radians(settings.prismatic_angle % 360.0)
        dist = settings.prismatic_distance * min(2.0, max(0.0, settings.prismatic_strength))
        dx = int(round(math.cos(theta) * dist))
        dy = int(round(math.sin(theta) * dist))
        if dx != 0 or dy != 0:
            red = _shift_2d_clamped(out[..., 0], dx, dy)
            green = _shift_2d_clamped(out[..., 1], int(round(dx * 0.35)), int(round(dy * 0.35)))
            blue = _shift_2d_clamped(out[..., 2], -dx, -dy)
            prism = np.stack([red, green, blue], axis=-1)
            mix = min(1.0, max(0.0, settings.prismatic_strength))
            out = np.clip(out * (1.0 - mix) + prism * mix, 0.0, 1.0)
            if settings.prismatic_strength > 1.0:
                boost = min(1.0, (settings.prismatic_strength - 1.0) * 0.5)
                out = np.clip(out + (prism - out) * boost, 0.0, 1.0)

    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


_DEFAULT_PROCESS_SETTINGS = ProcessSettings(
    exposure=0.0,
    contrast=1.0,
    saturation=1.0,
    pixelate_size=1,
    posterize_bits=8,
    halftone_strength=0.0,
    halftone_size=8,
    film_grain_strength=0.0,
    film_grain_size=32.0,
    film_grain_seed=42,
    vignette_strength=0.0,
    vignette_roundness=1.2,
    fractal_strength=0.0,
    fractal_scale=96.0,
    fractal_octaves=4,
    fractal_seed=23,
    bokeh_strength=0.0,
    bokeh_radius=10.0,
    bokeh_threshold=0.72,
    rgb_shift_x=0,
    rgb_shift_y=0,
    prismatic_strength=0.0,
    prismatic_distance=5.0,
    prismatic_angle=25.0,
    bloom_strength=0.0,
    bloom_radius=14.0,
    bloom_threshold=0.7,
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
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "exposure": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                **_mask_required_inputs(),
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
        exposure: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            exposure=float(exposure),
            contrast=float(max(0.0, contrast)),
            saturation=float(max(0.0, saturation)),
        )
        detail = "exposure={:.2f}, contrast={:.2f}, saturation={:.2f}".format(
            settings.exposure,
            settings.contrast,
            settings.saturation,
        )
        return _run_effect_node(
            label="x1Tone",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Stylize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "posterize_bits": ("INT", {"default": 8, "min": 1, "max": 8, "step": 1}),
                "halftone_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "halftone_size": ("INT", {"default": 8, "min": 2, "max": 128, "step": 1}),
                **_mask_required_inputs(),
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
        posterize_bits: int = 8,
        halftone_strength: float = 0.0,
        halftone_size: int = 8,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            posterize_bits=int(min(8, max(1, posterize_bits))),
            halftone_strength=float(min(1.0, max(0.0, halftone_strength))),
            halftone_size=int(max(2, halftone_size)),
        )
        detail = "posterize={}bit, halftone={:.2f}@{}".format(
            settings.posterize_bits,
            settings.halftone_strength,
            settings.halftone_size,
        )
        return _run_effect_node(
            label="x1Stylize",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Pixelate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "pixel_size_x": ("INT", {"default": 8, "min": 1, "max": 256, "step": 1}),
                "pixel_size_y": ("INT", {"default": 8, "min": 1, "max": 256, "step": 1}),
                "downsample_mode": (list(_PIXEL_DOWNSAMPLE_MODES.keys()),),
                "upscale_mode": (list(_PIXEL_UPSAMPLE_MODES.keys()),),
                "cell_blend": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "color_levels": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
                "grid_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "grid_width": ("INT", {"default": 1, "min": 0, "max": 16, "step": 1}),
                **_mask_required_inputs(),
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
        pixel_size_x: int = 8,
        pixel_size_y: int = 8,
        downsample_mode: str = "box",
        upscale_mode: str = "nearest",
        cell_blend: float = 0.0,
        color_levels: int = 0,
        grid_strength: float = 0.0,
        grid_width: int = 1,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        return _run_pixelate_node(
            image=image,
            pixel_size_x=int(max(1, pixel_size_x)),
            pixel_size_y=int(max(1, pixel_size_y)),
            downsample_mode=str(downsample_mode),
            upscale_mode=str(upscale_mode),
            cell_blend=float(cell_blend),
            color_levels=int(color_levels),
            grid_strength=float(grid_strength),
            grid_width=int(grid_width),
            mask_feather=float(mask_feather),
            invert_mask=bool(invert_mask),
            mask=mask,
        )


class x1Film:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "film_grain_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.5, "step": 0.01}),
                "film_grain_size": ("FLOAT", {"default": 32.0, "min": 2.0, "max": 256.0, "step": 1.0}),
                "film_grain_seed": ("INT", {"default": 42, "min": 0, "max": 999999, "step": 1}),
                "vignette_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "vignette_roundness": ("FLOAT", {"default": 1.2, "min": 0.2, "max": 3.0, "step": 0.01}),
                **_mask_required_inputs(),
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
        film_grain_strength: float = 0.0,
        film_grain_size: float = 32.0,
        film_grain_seed: int = 42,
        vignette_strength: float = 0.0,
        vignette_roundness: float = 1.2,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            film_grain_strength=float(max(0.0, film_grain_strength)),
            film_grain_size=float(max(2.0, film_grain_size)),
            film_grain_seed=int(max(0, film_grain_seed)),
            vignette_strength=float(min(1.0, max(0.0, vignette_strength))),
            vignette_roundness=float(max(0.2, vignette_roundness)),
        )
        detail = "grain={:.2f}(s{:.1f},seed{}), vignette={:.2f}(r{:.2f})".format(
            settings.film_grain_strength,
            settings.film_grain_size,
            settings.film_grain_seed,
            settings.vignette_strength,
            settings.vignette_roundness,
        )
        return _run_effect_node(
            label="x1Film",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Fractal:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "fractal_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "fractal_scale": ("FLOAT", {"default": 96.0, "min": 2.0, "max": 1024.0, "step": 1.0}),
                "fractal_octaves": ("INT", {"default": 4, "min": 1, "max": 8, "step": 1}),
                "fractal_seed": ("INT", {"default": 23, "min": 0, "max": 999999, "step": 1}),
                **_mask_required_inputs(),
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
        fractal_strength: float = 0.0,
        fractal_scale: float = 96.0,
        fractal_octaves: int = 4,
        fractal_seed: int = 23,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            fractal_strength=float(min(1.0, max(0.0, fractal_strength))),
            fractal_scale=float(max(2.0, fractal_scale)),
            fractal_octaves=int(min(8, max(1, fractal_octaves))),
            fractal_seed=int(max(0, fractal_seed)),
        )
        detail = "fractal={:.2f}(s{:.1f},o{},seed{})".format(
            settings.fractal_strength,
            settings.fractal_scale,
            settings.fractal_octaves,
            settings.fractal_seed,
        )
        return _run_effect_node(
            label="x1Fractal",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Bloom:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "bloom_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "bloom_radius": ("FLOAT", {"default": 14.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "bloom_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
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
        bloom_strength: float = 0.0,
        bloom_radius: float = 14.0,
        bloom_threshold: float = 0.7,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            bloom_strength=float(max(0.0, bloom_strength)),
            bloom_radius=float(max(0.0, bloom_radius)),
            bloom_threshold=float(min(1.0, max(0.0, bloom_threshold))),
        )
        detail = "bloom={:.2f}@{:.1f}(thr={:.2f})".format(
            settings.bloom_strength,
            settings.bloom_radius,
            settings.bloom_threshold,
        )
        return _run_effect_node(
            label="x1Bloom",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Bokeh:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "bokeh_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "bokeh_radius": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "bokeh_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
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
        bokeh_strength: float = 0.0,
        bokeh_radius: float = 10.0,
        bokeh_threshold: float = 0.72,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            bokeh_strength=float(max(0.0, bokeh_strength)),
            bokeh_radius=float(max(0.0, bokeh_radius)),
            bokeh_threshold=float(min(1.0, max(0.0, bokeh_threshold))),
        )
        detail = "bokeh={:.2f}@{:.1f}(thr={:.2f})".format(
            settings.bokeh_strength,
            settings.bokeh_radius,
            settings.bokeh_threshold,
        )
        return _run_effect_node(
            label="x1Bokeh",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Chromatic:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "rgb_shift_x": ("INT", {"default": 0, "min": -128, "max": 128, "step": 1}),
                "rgb_shift_y": ("INT", {"default": 0, "min": -128, "max": 128, "step": 1}),
                "prismatic_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "prismatic_distance": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "prismatic_angle": ("FLOAT", {"default": 25.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                **_mask_required_inputs(),
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
        rgb_shift_x: int = 0,
        rgb_shift_y: int = 0,
        prismatic_strength: float = 0.0,
        prismatic_distance: float = 5.0,
        prismatic_angle: float = 25.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            rgb_shift_x=int(rgb_shift_x),
            rgb_shift_y=int(rgb_shift_y),
            prismatic_strength=float(max(0.0, prismatic_strength)),
            prismatic_distance=float(max(0.0, prismatic_distance)),
            prismatic_angle=float(prismatic_angle),
        )
        detail = "rgb_shift=({},{}), prismatic={:.2f}@{:.1f}px/{:.0f}deg".format(
            settings.rgb_shift_x,
            settings.rgb_shift_y,
            settings.prismatic_strength,
            settings.prismatic_distance,
            settings.prismatic_angle,
        )
        return _run_effect_node(
            label="x1Chromatic",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )


class x1Focus:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "blur_radius": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 128.0, "step": 0.5}),
                "sharpen": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                **_mask_required_inputs(),
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
        blur_radius: float = 0.0,
        sharpen: float = 0.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        settings = _with_settings(
            blur_radius=float(max(0.0, blur_radius)),
            sharpen=float(max(0.0, sharpen)),
        )
        detail = "blur={:.1f}px, sharpen={:.2f}".format(settings.blur_radius, settings.sharpen)
        return _run_effect_node(
            label="x1Focus",
            detail=detail,
            image=image,
            settings=settings,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
        )
