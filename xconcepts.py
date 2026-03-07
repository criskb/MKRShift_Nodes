import colorsys
import math
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
import torch
import torch.nn.functional as F

from .categories import FX_CONCEPT
from .xshared import (
    hsv_to_rgb_np as _hsv_to_rgb_np,
    mask_to_batch as _mask_to_batch,
    rgb_to_hsv_np as _rgb_to_hsv_np,
    smoothstep_np as _smoothstep,
    to_image_batch as _to_image_batch,
)


def _image_map_to_np_batch(map_image: Optional[torch.Tensor], batch: int, h: int, w: int) -> Optional[np.ndarray]:
    if map_image is None:
        return None
    maps = _to_image_batch(map_image).detach().cpu().numpy().astype(np.float32, copy=False)
    if maps.shape[0] == 1 and batch > 1:
        maps = np.repeat(maps, batch, axis=0)
    elif maps.shape[0] != batch:
        raise ValueError(f"direction_map batch {maps.shape[0]} does not match image batch {batch}")

    c = maps.shape[-1]
    out = np.zeros((batch, h, w, c), dtype=np.float32)
    for idx in range(batch):
        src = np.clip(maps[idx], 0.0, 1.0)
        if src.shape[0] != h or src.shape[1] != w:
            pil = Image.fromarray((src * 255.0).astype(np.uint8), mode="RGB" if c >= 3 else "L")
            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
            resized = np.asarray(pil, dtype=np.float32) / 255.0
            if resized.ndim == 2:
                resized = resized[..., None]
            if resized.shape[-1] != c:
                if c == 1:
                    resized = resized[..., :1]
                else:
                    resized = np.repeat(resized[..., :1], c, axis=-1)
            out[idx] = resized
        else:
            out[idx] = src
    return out


def _mask_map_to_np_batch(mask: Optional[torch.Tensor], batch: int, h: int, w: int) -> Optional[np.ndarray]:
    if mask is None:
        return None
    m = _mask_to_batch(
        mask=mask,
        batch=batch,
        h=h,
        w=w,
        feather_radius=0.0,
        invert_mask=False,
        device=torch.device("cpu"),
    )
    return m.detach().cpu().numpy().astype(np.float32, copy=False)


def _pil_from_rgb_float(rgb: np.ndarray) -> Image.Image:
    rgb_u8 = np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(rgb_u8, mode="RGB")


def _rgb_float_from_pil(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _centered_xy_grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    return np.meshgrid(x, y)


def _blend_mode(src: np.ndarray, fx: np.ndarray, mode: str) -> np.ndarray:
    m = str(mode).lower()
    if m == "add":
        return np.clip(src + fx, 0.0, 1.0)
    if m == "overlay":
        return np.where(src <= 0.5, 2.0 * src * fx, 1.0 - 2.0 * (1.0 - src) * (1.0 - fx)).astype(np.float32)
    if m == "soft_light":
        g = np.sqrt(np.clip(src, 0.0, 1.0))
        return np.where(
            fx <= 0.5,
            src - (1.0 - (2.0 * fx)) * src * (1.0 - src),
            src + ((2.0 * fx) - 1.0) * (g - src),
        ).astype(np.float32)
    if m == "screen":
        return (1.0 - (1.0 - src) * (1.0 - fx)).astype(np.float32)
    return np.clip(src * (1.0 - 0.5) + fx * 0.5, 0.0, 1.0).astype(np.float32)


def _torch_normalized_grid(h: int, w: int, device: torch.device, dtype: torch.dtype):
    ys = torch.linspace(-1.0, 1.0, h, device=device, dtype=dtype)
    xs = torch.linspace(-1.0, 1.0, w, device=device, dtype=dtype)
    yy, xx = torch.meshgrid(ys, xs, indexing="ij")
    return xx, yy


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


def _mask_required_inputs():
    return {
        "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
        "invert_mask": ("BOOLEAN", {"default": False}),
    }


def _run_masked_rgb_node(
    label: str,
    detail: str,
    image: torch.Tensor,
    mask_feather: float,
    invert_mask: bool,
    mask: Optional[torch.Tensor],
    fx_fn,
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
    src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
    fx_np = np.empty_like(src_np)
    for idx in range(int(b)):
        fx_np[idx] = fx_fn(src_np[idx], idx)

    fx_t = torch.from_numpy(np.clip(fx_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    out_rgb = torch.clamp((rgb * (1.0 - mask_batch)) + (fx_t * mask_batch), 0.0, 1.0)
    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

    coverage = float(mask_batch.mean().item()) * 100.0
    info = "{}: {}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}".format(
        label,
        detail,
        float(max(0.0, mask_feather)),
        coverage,
        " (inverted)" if invert_mask else "",
    )
    return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


def _light_leak_ramp(preset: str, custom_start: tuple[float, float, float], custom_end: tuple[float, float, float]):
    p = str(preset).lower()
    ramps = {
        "warm": ((1.00, 0.36, 0.10), (1.00, 0.86, 0.42)),
        "sunset": ((1.00, 0.24, 0.35), (1.00, 0.67, 0.15)),
        "teal_orange": ((0.14, 0.78, 0.86), (1.00, 0.56, 0.20)),
        "magenta_cyan": ((0.96, 0.26, 0.88), (0.20, 0.90, 1.00)),
    }
    if p == "custom":
        return np.asarray(custom_start, dtype=np.float32), np.asarray(custom_end, dtype=np.float32)
    c0, c1 = ramps.get(p, ramps["warm"])
    return np.asarray(c0, dtype=np.float32), np.asarray(c1, dtype=np.float32)


def _apply_light_leak_rgb(
    src: np.ndarray,
    strength: float,
    angle: float,
    scale: float,
    softness: float,
    seed: int,
    ramp_preset: str,
    blend_mode: str,
    custom_start: tuple[float, float, float],
    custom_end: tuple[float, float, float],
) -> np.ndarray:
    h, w = src.shape[:2]
    xx, yy = _centered_xy_grid(h, w)
    theta = math.radians(float(angle) % 360.0)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    xr = (xx * cos_t) + (yy * sin_t)
    yr = (-xx * sin_t) + (yy * cos_t)

    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    offx = float(rng.uniform(-0.35, 0.35))
    offy = float(rng.uniform(-0.40, 0.40))
    s = max(0.15, float(scale))
    soft = max(0.2, float(softness))

    core = np.exp(-((((xr - offx) / (0.46 * s)) ** 2) + (((yr - offy) / (0.36 * s)) ** 2)))
    streak = np.exp(-(((xr - offx) / (0.18 * soft)) ** 2)) * np.exp(-((((yr - offy) * 0.75) / (0.52 * s)) ** 2))
    leak = np.clip((core * 0.68) + (streak * 0.88), 0.0, 1.0)
    leak = np.power(leak, 1.0 / soft).astype(np.float32, copy=False)

    t = np.clip((xr * 0.5 / max(0.1, s)) + 0.5, 0.0, 1.0)
    c0, c1 = _light_leak_ramp(ramp_preset, custom_start, custom_end)
    ramp = (c0[None, None, :] * (1.0 - t[..., None])) + (c1[None, None, :] * t[..., None])
    fx = np.clip(ramp * leak[..., None] * max(0.0, float(strength)), 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip(_blend_mode(src, fx, blend_mode), 0.0, 1.0).astype(np.float32, copy=False)


def _apply_split_tone_rgb(
    src: np.ndarray,
    shadow_hue: float,
    shadow_sat: float,
    highlight_hue: float,
    highlight_sat: float,
    balance: float,
    pivot: float,
    mix: float,
) -> np.ndarray:
    luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
    p = float(np.clip(pivot + (balance * 0.35), 0.02, 0.98))
    sh = np.clip((p - luma) / max(1e-6, p), 0.0, 1.0)
    hi = np.clip((luma - p) / max(1e-6, 1.0 - p), 0.0, 1.0)

    sh_color = np.asarray(colorsys.hsv_to_rgb((shadow_hue % 360.0) / 360.0, np.clip(shadow_sat, 0.0, 1.0), 1.0), dtype=np.float32)
    hi_color = np.asarray(
        colorsys.hsv_to_rgb((highlight_hue % 360.0) / 360.0, np.clip(highlight_sat, 0.0, 1.0), 1.0),
        dtype=np.float32,
    )

    sh_mix = sh[..., None] * np.clip(shadow_sat, 0.0, 1.0)
    hi_mix = hi[..., None] * np.clip(highlight_sat, 0.0, 1.0)
    toned = src * (1.0 - sh_mix) + sh_color[None, None, :] * sh_mix
    toned = toned * (1.0 - hi_mix) + hi_color[None, None, :] * hi_mix

    m = np.clip(float(mix), 0.0, 1.0)
    return np.clip((src * (1.0 - m)) + (toned * m), 0.0, 1.0).astype(np.float32, copy=False)


def _selective_range(range_mode: str, custom_center: float, custom_width: float) -> tuple[float, float]:
    ranges = {
        "reds": (0.0, 24.0),
        "yellows": (58.0, 24.0),
        "greens": (120.0, 28.0),
        "cyans": (180.0, 28.0),
        "blues": (230.0, 30.0),
        "magentas": (300.0, 28.0),
    }
    if str(range_mode).lower() == "custom":
        return float(custom_center), float(custom_width)
    return ranges.get(str(range_mode).lower(), ranges["blues"])


def _apply_selective_color_rgb(
    src: np.ndarray,
    range_mode: str,
    custom_hue_center: float,
    custom_hue_width: float,
    hue_shift: float,
    sat_shift: float,
    value_shift: float,
    softness: float,
    amount: float,
    preserve_luma: bool,
) -> np.ndarray:
    center_deg, width_deg = _selective_range(range_mode, custom_hue_center, custom_hue_width)
    center = (center_deg % 360.0) / 360.0
    width = np.clip(width_deg, 1.0, 180.0) / 360.0
    soft = max(1.0 / 360.0, abs(float(softness)) / 360.0)

    h, s, v = _rgb_to_hsv_np(src)
    dist = np.abs(((h - center + 0.5) % 1.0) - 0.5)
    sel = 1.0 - _smoothstep(width, width + soft, dist)

    hh = np.mod(h + (sel * (float(hue_shift) / 360.0)), 1.0)
    ss = np.clip(s + (sel * float(sat_shift)), 0.0, 1.0)
    vv = np.clip(v + (sel * float(value_shift)), 0.0, 1.0)

    out = _hsv_to_rgb_np(hh, ss, vv)
    if preserve_luma:
        src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])
        out_l = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])
        gain = (src_l / np.maximum(out_l, 1e-6))[..., None]
        out = np.clip(out * gain, 0.0, 1.0)

    mix = np.clip(float(amount), 0.0, 1.0)
    return np.clip((src * (1.0 - mix)) + (out * mix), 0.0, 1.0).astype(np.float32, copy=False)


def _apply_lens_distort_rgb(
    src: np.ndarray,
    distortion: float,
    chroma_aberration: float,
    edge_vignette: float,
    zoom_compensation: bool,
) -> np.ndarray:
    h, w = src.shape[:2]
    t = torch.from_numpy(src).permute(2, 0, 1).unsqueeze(0).float()
    device = t.device
    dtype = t.dtype
    xx, yy = _torch_normalized_grid(h, w, device=device, dtype=dtype)
    r2 = (xx * xx) + (yy * yy)

    def make_grid(k: float):
        factor = 1.0 + (float(k) * r2)
        if zoom_compensation:
            factor = factor * (1.0 / max(0.2, 1.0 + (abs(float(k)) * 0.38)))
        gx = xx * factor
        gy = yy * factor
        return torch.stack([gx, gy], dim=-1).unsqueeze(0)

    k = float(distortion)
    base = F.grid_sample(t, make_grid(k), mode="bilinear", padding_mode="border", align_corners=True)

    ca = float(max(0.0, chroma_aberration))
    if ca > 1e-6:
        r = F.grid_sample(t[:, 0:1, ...], make_grid(k + (ca * 0.45)), mode="bilinear", padding_mode="border", align_corners=True)
        b = F.grid_sample(t[:, 2:3, ...], make_grid(k - (ca * 0.45)), mode="bilinear", padding_mode="border", align_corners=True)
        base[:, 0:1, ...] = r
        base[:, 2:3, ...] = b

    out = base.squeeze(0).permute(1, 2, 0).cpu().numpy().astype(np.float32, copy=False)
    if edge_vignette > 1e-6:
        radius = np.sqrt((xx.cpu().numpy() ** 2) + (yy.cpu().numpy() ** 2))
        edge = np.clip((radius - 0.12) / 0.95, 0.0, 1.0)
        coupling = min(1.0, abs(k) + (ca * 0.8))
        vig = 1.0 - (np.clip(edge_vignette, 0.0, 1.0) * coupling * edge)
        out = np.clip(out * vig[..., None], 0.0, 1.0)
    return out


def _apply_crt_scan_rgb(
    src: np.ndarray,
    scanline_strength: float,
    scanline_density: float,
    phosphor_strength: float,
    bloom_bleed: float,
    warp_strength: float,
    curvature: float,
    noise_strength: float,
    seed: int,
) -> np.ndarray:
    h, w = src.shape[:2]
    t = torch.from_numpy(src).permute(2, 0, 1).unsqueeze(0).float()
    device = t.device
    dtype = t.dtype
    xx, yy = _torch_normalized_grid(h, w, device=device, dtype=dtype)

    curv = float(max(0.0, curvature))
    warp = float(max(0.0, warp_strength))
    gx = xx * (1.0 + (curv * yy * yy)) + (torch.sin((yy + 1.0) * math.pi) * (warp * 0.02))
    gy = yy * (1.0 + (curv * xx * xx))
    grid = torch.stack([gx, gy], dim=-1).unsqueeze(0)

    warped = F.grid_sample(t, grid, mode="bilinear", padding_mode="border", align_corners=True)
    out = warped.squeeze(0).permute(1, 2, 0).cpu().numpy().astype(np.float32, copy=False)

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    sl = 1.0 - (np.clip(scanline_strength, 0.0, 1.0) * (0.5 + 0.5 * np.sin((ys * h * max(0.2, scanline_density)) * math.pi)))
    out *= sl[:, None, None]

    p = float(np.clip(phosphor_strength, 0.0, 1.0))
    if p > 1e-6:
        x = np.arange(w, dtype=np.int32) % 3
        gains = np.ones((w, 3), dtype=np.float32)
        gains[x == 0, 0] = 1.0 + (0.22 * p)
        gains[x == 0, 1] = 1.0 - (0.06 * p)
        gains[x == 0, 2] = 1.0 - (0.06 * p)
        gains[x == 1, 1] = 1.0 + (0.22 * p)
        gains[x == 1, 0] = 1.0 - (0.06 * p)
        gains[x == 1, 2] = 1.0 - (0.06 * p)
        gains[x == 2, 2] = 1.0 + (0.22 * p)
        gains[x == 2, 0] = 1.0 - (0.06 * p)
        gains[x == 2, 1] = 1.0 - (0.06 * p)
        out = np.clip(out * gains[None, :, :], 0.0, 1.0)

    bleed = float(np.clip(bloom_bleed, 0.0, 1.0))
    if bleed > 1e-6:
        radius = 1.0 + (bleed * 5.0)
        blur = _rgb_float_from_pil(_pil_from_rgb_float(out).filter(ImageFilter.GaussianBlur(radius=radius)))
        out = np.clip(out + (blur * (bleed * 0.35)), 0.0, 1.0)

    noise = float(np.clip(noise_strength, 0.0, 1.0))
    if noise > 1e-6:
        n = _fractal_noise(h=h, w=w, base_scale=36.0, octaves=3, seed=int(seed)) - 0.5
        out = np.clip(out + (n[..., None] * (noise * 0.18)), 0.0, 1.0)
    return out.astype(np.float32, copy=False)


def _warp_with_offsets(src: np.ndarray, dx_px: np.ndarray, dy_px: np.ndarray) -> np.ndarray:
    h, w = src.shape[:2]
    t = torch.from_numpy(src).permute(2, 0, 1).unsqueeze(0).float()
    device = t.device
    dtype = t.dtype
    xx, yy = _torch_normalized_grid(h, w, device=device, dtype=dtype)

    dx = torch.from_numpy(dx_px.astype(np.float32, copy=False)).to(device=device, dtype=dtype)
    dy = torch.from_numpy(dy_px.astype(np.float32, copy=False)).to(device=device, dtype=dtype)
    if w > 1:
        gx = xx + ((2.0 * dx) / float(w - 1))
    else:
        gx = xx
    if h > 1:
        gy = yy + ((2.0 * dy) / float(h - 1))
    else:
        gy = yy
    grid = torch.stack([gx, gy], dim=-1).unsqueeze(0)

    out = F.grid_sample(t, grid, mode="bilinear", padding_mode="border", align_corners=True)
    return out.squeeze(0).permute(1, 2, 0).cpu().numpy().astype(np.float32, copy=False)


def _apply_glow_edges_rgb(
    src: np.ndarray,
    edge_threshold: float,
    edge_softness: float,
    glow_spread: float,
    glow_strength: float,
    tint: tuple[float, float, float],
    composite_mode: str,
    ink_amount: float,
) -> np.ndarray:
    luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
    gy, gx = np.gradient(luma)
    mag = np.sqrt((gx * gx) + (gy * gy))
    mag_norm = mag / max(1e-6, float(np.percentile(mag, 98.0)))
    edge = np.clip((mag_norm - float(edge_threshold)) / max(1e-6, 1.0 - float(edge_threshold)), 0.0, 1.0)
    edge = np.power(edge, 1.0 / max(0.1, float(edge_softness)))

    spread = float(max(0.0, glow_spread))
    if spread > 1e-6:
        e_pil = Image.fromarray(np.clip(edge * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
        e_pil = e_pil.filter(ImageFilter.GaussianBlur(radius=spread))
        edge = np.asarray(e_pil, dtype=np.float32) / 255.0

    tint_arr = np.asarray(tint, dtype=np.float32)
    glow = tint_arr[None, None, :] * edge[..., None] * float(max(0.0, glow_strength))

    mode = str(composite_mode).lower()
    if mode == "ink":
        dark = 1.0 - (np.clip(float(ink_amount), 0.0, 1.0) * edge[..., None])
        return np.clip((src * dark) + (tint_arr[None, None, :] * edge[..., None] * 0.25), 0.0, 1.0).astype(np.float32)
    return np.clip(_blend_mode(src, glow, mode), 0.0, 1.0).astype(np.float32, copy=False)


class x1LightLeak:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 2.0, "step": 0.01}),
                "angle": ("FLOAT", {"default": 35.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "scale": ("FLOAT", {"default": 1.0, "min": 0.2, "max": 3.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 1.0, "min": 0.2, "max": 3.0, "step": 0.01}),
                "seed": ("INT", {"default": 1337, "min": 0, "max": 999999, "step": 1}),
                "ramp_preset": (["warm", "sunset", "teal_orange", "magenta_cyan", "custom"],),
                "blend_mode": (["screen", "add", "overlay", "soft_light"],),
                "custom_start_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "custom_start_g": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "custom_start_b": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
                "custom_end_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "custom_end_g": ("FLOAT", {"default": 0.86, "min": 0.0, "max": 1.0, "step": 0.01}),
                "custom_end_b": ("FLOAT", {"default": 0.42, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "lightleak_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        strength: float = 0.35,
        angle: float = 35.0,
        scale: float = 1.0,
        softness: float = 1.0,
        seed: int = 1337,
        ramp_preset: str = "warm",
        blend_mode: str = "screen",
        custom_start_r: float = 1.0,
        custom_start_g: float = 0.45,
        custom_start_b: float = 0.10,
        custom_end_r: float = 1.0,
        custom_end_g: float = 0.86,
        custom_end_b: float = 0.42,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = "strength={:.2f}, angle={:.1f}, scale={:.2f}, softness={:.2f}, ramp={}, blend={}, seed={}".format(
            float(max(0.0, strength)),
            float(angle),
            float(max(0.2, scale)),
            float(max(0.2, softness)),
            str(ramp_preset),
            str(blend_mode),
            int(max(0, seed)),
        )
        return _run_masked_rgb_node(
            label="x1LightLeak",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_light_leak_rgb(
                src=src,
                strength=float(max(0.0, strength)),
                angle=float(angle),
                scale=float(max(0.2, scale)),
                softness=float(max(0.2, softness)),
                seed=int(max(0, seed)),
                ramp_preset=str(ramp_preset),
                blend_mode=str(blend_mode),
                custom_start=(float(custom_start_r), float(custom_start_g), float(custom_start_b)),
                custom_end=(float(custom_end_r), float(custom_end_g), float(custom_end_b)),
            ),
        )


class x1SplitTone:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "shadow_hue": ("FLOAT", {"default": 210.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "shadow_sat": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
                "highlight_hue": ("FLOAT", {"default": 36.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "highlight_sat": ("FLOAT", {"default": 0.32, "min": 0.0, "max": 1.0, "step": 0.01}),
                "balance": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "pivot": ("FLOAT", {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "split_tone_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        shadow_hue: float = 210.0,
        shadow_sat: float = 0.30,
        highlight_hue: float = 36.0,
        highlight_sat: float = 0.32,
        balance: float = 0.0,
        pivot: float = 0.50,
        mix: float = 0.75,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = (
            "shadow=({:.0f},{:.2f}), highlight=({:.0f},{:.2f}), balance={:.2f}, pivot={:.2f}, mix={:.2f}"
        ).format(
            float(shadow_hue),
            float(np.clip(shadow_sat, 0.0, 1.0)),
            float(highlight_hue),
            float(np.clip(highlight_sat, 0.0, 1.0)),
            float(np.clip(balance, -1.0, 1.0)),
            float(np.clip(pivot, 0.0, 1.0)),
            float(np.clip(mix, 0.0, 1.0)),
        )
        return _run_masked_rgb_node(
            label="x1SplitTone",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_split_tone_rgb(
                src=src,
                shadow_hue=float(shadow_hue),
                shadow_sat=float(shadow_sat),
                highlight_hue=float(highlight_hue),
                highlight_sat=float(highlight_sat),
                balance=float(balance),
                pivot=float(pivot),
                mix=float(mix),
            ),
        )


class x1SelectiveColor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "range_mode": (["reds", "yellows", "greens", "cyans", "blues", "magentas", "custom"],),
                "custom_hue_center": ("FLOAT", {"default": 220.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "custom_hue_width": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 180.0, "step": 1.0}),
                "hue_shift": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.5}),
                "sat_shift": ("FLOAT", {"default": 0.20, "min": -1.0, "max": 1.0, "step": 0.01}),
                "value_shift": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "softness": ("FLOAT", {"default": 20.0, "min": 0.0, "max": 120.0, "step": 0.5}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": True}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "selective_color_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        range_mode: str = "blues",
        custom_hue_center: float = 220.0,
        custom_hue_width: float = 30.0,
        hue_shift: float = 0.0,
        sat_shift: float = 0.20,
        value_shift: float = 0.0,
        softness: float = 20.0,
        amount: float = 1.0,
        preserve_luma: bool = True,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = "range={}, hue_shift={:.1f}, sat_shift={:.2f}, val_shift={:.2f}, softness={:.1f}, amount={:.2f}".format(
            str(range_mode),
            float(hue_shift),
            float(sat_shift),
            float(value_shift),
            float(max(0.0, softness)),
            float(np.clip(amount, 0.0, 1.0)),
        )
        return _run_masked_rgb_node(
            label="x1SelectiveColor",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_selective_color_rgb(
                src=src,
                range_mode=str(range_mode),
                custom_hue_center=float(custom_hue_center),
                custom_hue_width=float(custom_hue_width),
                hue_shift=float(hue_shift),
                sat_shift=float(sat_shift),
                value_shift=float(value_shift),
                softness=float(softness),
                amount=float(amount),
                preserve_luma=bool(preserve_luma),
            ),
        )


class x1LensDistort:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "distortion": ("FLOAT", {"default": 0.12, "min": -0.8, "max": 0.8, "step": 0.001}),
                "chroma_aberration": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.35, "step": 0.001}),
                "edge_vignette": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "zoom_compensation": ("BOOLEAN", {"default": True}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "lens_distort_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        distortion: float = 0.12,
        chroma_aberration: float = 0.05,
        edge_vignette: float = 0.22,
        zoom_compensation: bool = True,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = "k={:.3f}, ca={:.3f}, vignette={:.2f}, zoom_comp={}".format(
            float(np.clip(distortion, -0.8, 0.8)),
            float(max(0.0, chroma_aberration)),
            float(np.clip(edge_vignette, 0.0, 1.0)),
            bool(zoom_compensation),
        )
        return _run_masked_rgb_node(
            label="x1LensDistort",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_lens_distort_rgb(
                src=src,
                distortion=float(np.clip(distortion, -0.8, 0.8)),
                chroma_aberration=float(max(0.0, chroma_aberration)),
                edge_vignette=float(np.clip(edge_vignette, 0.0, 1.0)),
                zoom_compensation=bool(zoom_compensation),
            ),
        )


class x1CRTScan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "scanline_strength": ("FLOAT", {"default": 0.28, "min": 0.0, "max": 1.0, "step": 0.01}),
                "scanline_density": ("FLOAT", {"default": 1.0, "min": 0.2, "max": 4.0, "step": 0.01}),
                "phosphor_strength": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
                "bloom_bleed": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "warp_strength": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 1.0, "step": 0.01}),
                "curvature": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 0.8, "step": 0.01}),
                "noise_strength": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.25, "step": 0.005}),
                "seed": ("INT", {"default": 777, "min": 0, "max": 999999, "step": 1}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "crt_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        scanline_strength: float = 0.28,
        scanline_density: float = 1.0,
        phosphor_strength: float = 0.30,
        bloom_bleed: float = 0.22,
        warp_strength: float = 0.12,
        curvature: float = 0.18,
        noise_strength: float = 0.05,
        seed: int = 777,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = "scan={:.2f}@{:.2f}, phosphor={:.2f}, bleed={:.2f}, warp={:.2f}, curve={:.2f}, noise={:.3f}, seed={}".format(
            float(np.clip(scanline_strength, 0.0, 1.0)),
            float(max(0.2, scanline_density)),
            float(np.clip(phosphor_strength, 0.0, 1.0)),
            float(np.clip(bloom_bleed, 0.0, 1.0)),
            float(np.clip(warp_strength, 0.0, 1.0)),
            float(np.clip(curvature, 0.0, 0.8)),
            float(np.clip(noise_strength, 0.0, 0.25)),
            int(max(0, seed)),
        )
        return _run_masked_rgb_node(
            label="x1CRTScan",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_crt_scan_rgb(
                src=src,
                scanline_strength=float(scanline_strength),
                scanline_density=float(scanline_density),
                phosphor_strength=float(phosphor_strength),
                bloom_bleed=float(bloom_bleed),
                warp_strength=float(warp_strength),
                curvature=float(curvature),
                noise_strength=float(noise_strength),
                seed=int(max(0, seed)),
            ),
        )


class x1WarpDisplace:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "displace_strength": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 128.0, "step": 0.1}),
                "base_direction": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "noise_scale": ("FLOAT", {"default": 64.0, "min": 2.0, "max": 512.0, "step": 1.0}),
                "noise_mix": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 321, "min": 0, "max": 999999, "step": 1}),
                **_mask_required_inputs(),
            },
            "optional": {
                "direction_map": ("IMAGE",),
                "strength_map": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "warp_displace_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        displace_strength: float = 12.0,
        base_direction: float = 0.0,
        noise_scale: float = 64.0,
        noise_mix: float = 0.35,
        seed: int = 321,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        direction_map: Optional[torch.Tensor] = None,
        strength_map: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)

        comp_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
        ).unsqueeze(-1)

        dir_np = _image_map_to_np_batch(direction_map, batch=int(b), h=int(h), w=int(w))
        strength_np = _mask_map_to_np_batch(strength_map, batch=int(b), h=int(h), w=int(w))

        out_np = np.empty_like(src_np)
        base_theta = math.radians(float(base_direction) % 360.0)
        base_dx = math.cos(base_theta)
        base_dy = math.sin(base_theta)
        n_mix = float(np.clip(noise_mix, 0.0, 1.0))
        amp = float(max(0.0, displace_strength))

        for idx in range(int(b)):
            if dir_np is not None:
                dm = dir_np[idx]
                if dm.shape[-1] >= 2:
                    dx = (dm[..., 0] * 2.0) - 1.0
                    dy = (dm[..., 1] * 2.0) - 1.0
                else:
                    angle = dm[..., 0] * (2.0 * math.pi)
                    dx = np.cos(angle)
                    dy = np.sin(angle)
            else:
                noise = _fractal_noise(
                    h=int(h),
                    w=int(w),
                    base_scale=float(max(2.0, noise_scale)),
                    octaves=3,
                    seed=int(seed + (idx * 37)),
                )
                n_angle = noise * (2.0 * math.pi)
                ndx = np.cos(n_angle)
                ndy = np.sin(n_angle)
                dx = (base_dx * (1.0 - n_mix)) + (ndx * n_mix)
                dy = (base_dy * (1.0 - n_mix)) + (ndy * n_mix)

            if strength_np is not None:
                local_amp = amp * np.clip(strength_np[idx], 0.0, 1.0)
            else:
                local_amp = np.full((int(h), int(w)), amp, dtype=np.float32)

            dx_px = dx.astype(np.float32, copy=False) * local_amp
            dy_px = dy.astype(np.float32, copy=False) * local_amp
            out_np[idx] = _warp_with_offsets(src_np[idx], dx_px=dx_px, dy_px=dy_px)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - comp_mask)) + (fx_t * comp_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(comp_mask.mean().item()) * 100.0
        info = (
            "x1WarpDisplace: strength={:.1f}px, dir={:.1f}deg, noise_mix={:.2f}@{:.1f}, seed={}, "
            "dir_map={}, strength_map={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            amp,
            float(base_direction),
            n_mix,
            float(max(2.0, noise_scale)),
            int(max(0, seed)),
            "yes" if direction_map is not None else "no",
            "yes" if strength_map is not None else "no",
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), comp_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1GlowEdges:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "edge_threshold": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_softness": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01}),
                "glow_spread": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 64.0, "step": 0.5}),
                "glow_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "tint_r": ("FLOAT", {"default": 0.56, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_g": ("FLOAT", {"default": 0.92, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tint_b": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "composite_mode": (["screen", "add", "soft_light", "ink"],),
                "ink_amount": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "glow_edges_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        edge_threshold: float = 0.22,
        edge_softness: float = 1.0,
        glow_spread: float = 8.0,
        glow_strength: float = 1.0,
        tint_r: float = 0.56,
        tint_g: float = 0.92,
        tint_b: float = 1.0,
        composite_mode: str = "screen",
        ink_amount: float = 0.45,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        detail = "thr={:.2f}, soft={:.2f}, spread={:.1f}, strength={:.2f}, tint=({:.2f},{:.2f},{:.2f}), mode={}".format(
            float(np.clip(edge_threshold, 0.0, 1.0)),
            float(max(0.1, edge_softness)),
            float(max(0.0, glow_spread)),
            float(max(0.0, glow_strength)),
            float(np.clip(tint_r, 0.0, 1.0)),
            float(np.clip(tint_g, 0.0, 1.0)),
            float(np.clip(tint_b, 0.0, 1.0)),
            str(composite_mode),
        )
        return _run_masked_rgb_node(
            label="x1GlowEdges",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=lambda src, _: _apply_glow_edges_rgb(
                src=src,
                edge_threshold=float(edge_threshold),
                edge_softness=float(edge_softness),
                glow_spread=float(glow_spread),
                glow_strength=float(glow_strength),
                tint=(float(tint_r), float(tint_g), float(tint_b)),
                composite_mode=str(composite_mode),
                ink_amount=float(ink_amount),
            ),
        )


class x1Depth:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "depth_mode": (["luma", "inverted_luma", "radial", "custom_map"],),
                "focal_depth": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "depth_range": ("FLOAT", {"default": 0.25, "min": 0.02, "max": 1.0, "step": 0.01}),
                "near_blur": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 64.0, "step": 0.5}),
                "far_blur": ("FLOAT", {"default": 18.0, "min": 0.0, "max": 64.0, "step": 0.5}),
                "depth_contrast": ("FLOAT", {"default": 1.0, "min": 0.2, "max": 3.0, "step": 0.01}),
                "haze_strength": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01}),
                "haze_r": ("FLOAT", {"default": 0.74, "min": 0.0, "max": 1.0, "step": 0.01}),
                "haze_g": ("FLOAT", {"default": 0.82, "min": 0.0, "max": 1.0, "step": 0.01}),
                "haze_b": ("FLOAT", {"default": 0.92, "min": 0.0, "max": 1.0, "step": 0.01}),
                **_mask_required_inputs(),
            },
            "optional": {
                "depth_map": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "depth_mask", "depth_info")
    FUNCTION = "run"
    CATEGORY = FX_CONCEPT

    def run(
        self,
        image: torch.Tensor,
        depth_mode: str = "luma",
        focal_depth: float = 0.5,
        depth_range: float = 0.25,
        near_blur: float = 10.0,
        far_blur: float = 18.0,
        depth_contrast: float = 1.0,
        haze_strength: float = 0.15,
        haze_r: float = 0.74,
        haze_g: float = 0.82,
        haze_b: float = 0.92,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        depth_map: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)

        comp_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
        ).unsqueeze(-1)

        depth_map_np = _mask_map_to_np_batch(depth_map, batch=int(b), h=int(h), w=int(w))
        out_np = np.empty_like(src_np)
        depth_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        mode = str(depth_mode).lower()
        focus = float(np.clip(focal_depth, 0.0, 1.0))
        d_range = float(max(0.02, depth_range))
        d_contrast = float(max(0.2, depth_contrast))
        near_r = float(max(0.0, near_blur))
        far_r = float(max(0.0, far_blur))
        haze = float(np.clip(haze_strength, 0.0, 1.0))
        haze_color = np.asarray([haze_r, haze_g, haze_b], dtype=np.float32)

        xx, yy = _centered_xy_grid(int(h), int(w))
        radial_depth = np.clip(np.sqrt((xx * xx) + (yy * yy)) / math.sqrt(2.0), 0.0, 1.0).astype(np.float32, copy=False)

        for idx in range(int(b)):
            src = src_np[idx]
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)

            if mode == "custom_map" and depth_map_np is not None:
                depth = depth_map_np[idx]
            elif mode == "inverted_luma":
                depth = 1.0 - luma
            elif mode == "radial":
                depth = radial_depth
            else:
                depth = luma

            depth = np.clip(((depth - 0.5) * d_contrast) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)
            depth_np[idx] = depth

            near_w = np.clip((focus - depth) / d_range, 0.0, 1.0)
            far_w = np.clip((depth - focus) / d_range, 0.0, 1.0)
            sharp_w = np.clip(1.0 - np.maximum(near_w, far_w), 0.0, 1.0)

            near_img = src if near_r <= 1e-6 else _rgb_float_from_pil(_pil_from_rgb_float(src).filter(ImageFilter.GaussianBlur(radius=near_r)))
            far_img = src if far_r <= 1e-6 else _rgb_float_from_pil(_pil_from_rgb_float(src).filter(ImageFilter.GaussianBlur(radius=far_r)))

            composed = (src * sharp_w[..., None]) + (near_img * near_w[..., None]) + (far_img * far_w[..., None])
            if haze > 1e-6:
                hz = haze * far_w[..., None]
                composed = (composed * (1.0 - hz)) + (haze_color[None, None, :] * hz)
            out_np[idx] = np.clip(composed, 0.0, 1.0).astype(np.float32, copy=False)

        fx_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - comp_mask)) + (fx_t * comp_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb
        depth_t = torch.from_numpy(np.clip(depth_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)

        coverage = float(comp_mask.mean().item()) * 100.0
        info = (
            "x1Depth: mode={}, focus={:.2f}, range={:.2f}, near={:.1f}px, far={:.1f}px, contrast={:.2f}, "
            "haze={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            mode,
            focus,
            d_range,
            near_r,
            far_r,
            d_contrast,
            haze,
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), depth_t.clamp(0.0, 1.0), info)
