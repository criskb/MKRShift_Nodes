import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter
import torch
import torch.nn.functional as F

from ..categories import FX_PLAY
from ..lib.settings_bundle import parse_settings_payload


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

PALETTE_CHOICES = tuple(PALETTES.keys())


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
    dtype: torch.dtype,
) -> torch.Tensor:
    if mask is None:
        out = torch.ones((batch, h, w), dtype=dtype)
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
        raise ValueError(f"Mask batch {m.shape[0]} does not match target batch {batch}")

    out_np = np.zeros((batch, h, w), dtype=np.float32)
    feather = float(max(0.0, feather_radius))
    for idx in range(batch):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        pil = Image.fromarray((sample * 255.0).astype(np.uint8), mode="L")
        if pil.size != (w, h):
            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
        if feather > 1e-6:
            pil = pil.filter(ImageFilter.GaussianBlur(radius=feather))
        out_np[idx] = np.asarray(pil, dtype=np.float32) / 255.0

    out = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=device, dtype=dtype)
    if invert_mask:
        out = 1.0 - out
    return out


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
    glow: float,
    drift: float,
    seed: int,
) -> np.ndarray:
    x, y = _uv_grid(h, w)
    xx = (x - 0.5) * 2.0
    yy = (y - 0.5) * 2.0
    radius = np.sqrt(xx * xx + yy * yy)

    n_base = _fractal_noise(h, w, noise_scale, 5, seed)
    n_detail = _fractal_noise(h, w, max(2.0, noise_scale * 0.35), 4, seed + 947)
    drift_term = (xx * 1.2 - yy * 0.85) * max(0.0, float(drift))

    angle = np.arctan2(yy, xx)
    flow = np.sin(
        (xx * 1.8 + yy * 0.9 + drift_term + n_base * (4.0 + swirl * 3.2)) * math.pi
        + angle * swirl * 0.7
    )
    flow = 0.5 + 0.5 * flow

    band = np.clip((flow * 0.75) + (n_detail * 0.35), 0.0, 1.0)
    lift = np.clip(1.0 - np.power(np.clip(radius, 0.0, 1.6), 1.35), 0.0, 1.0)
    aura = np.clip((band * 0.70) + (lift * 0.30), 0.0, 1.0)

    low = np.asarray(palette.low, dtype=np.float32)
    mid = np.asarray(palette.mid, dtype=np.float32)
    high = np.asarray(palette.high, dtype=np.float32)
    glow_rgb = np.asarray(palette.glow, dtype=np.float32)

    base = _lerp3(low, mid, _smoothstep(0.12, 0.60, aura))
    hot = _lerp3(mid, high, _smoothstep(0.48, 0.92, aura))
    mix_hot = _smoothstep(0.28, 0.88, aura)
    rgb = _lerp3(base, hot, mix_hot)

    glow_mask = _smoothstep(0.58, 0.98, aura) * np.clip(1.15 - radius, 0.0, 1.0)
    rgb = np.clip(
        rgb + glow_rgb * (0.24 * glow_mask[..., None] * max(0.0, intensity) * max(0.0, glow)),
        0.0,
        1.0,
    )

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


def _shift_fill(src_rgb: np.ndarray, dx: int, dy: int) -> np.ndarray:
    h, w, c = src_rgb.shape
    out = np.zeros_like(src_rgb)

    src_x0 = max(0, -dx)
    src_x1 = min(w, w - dx) if dx >= 0 else w
    dst_x0 = max(0, dx)
    dst_x1 = min(w, w + dx) if dx <= 0 else w

    src_y0 = max(0, -dy)
    src_y1 = min(h, h - dy) if dy >= 0 else h
    dst_y0 = max(0, dy)
    dst_y1 = min(h, h + dy) if dy <= 0 else h

    if src_x1 <= src_x0 or src_y1 <= src_y0 or dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return out

    out[dst_y0:dst_y1, dst_x0:dst_x1, :] = src_rgb[src_y0:src_y1, src_x0:src_x1, :]
    return out


def _apply_slice_glitch(
    src_rgb: np.ndarray,
    slice_count: int,
    max_shift: int,
    direction: str,
    channel_split: float,
    scanline_jitter: float,
    grain: float,
    ghosting: float,
    luma_gate: float,
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
            out[y0 : y0 + band_h, :, :] = _shift_fill(out[y0 : y0 + band_h, :, :], shift, 0)
        else:
            band_w = int(rng.integers(max(1, w // 80), max(2, w // 8) + 1))
            x0 = int(rng.integers(0, max(1, w - band_w + 1)))
            shift = int(rng.integers(-max_shift_px, max_shift_px + 1)) if max_shift_px > 0 else 0
            out[:, x0 : x0 + band_w, :] = _shift_fill(out[:, x0 : x0 + band_w, :], 0, shift)

    split = max(0.0, float(channel_split))
    if split > 1e-6 and max_shift_px > 0:
        amp = max(1, int(round(max_shift_px * split)))
        r_shift = int(rng.integers(-amp, amp + 1))
        g_shift = int(rng.integers(-max(1, amp // 2), max(1, amp // 2) + 1))
        b_shift = int(rng.integers(-amp, amp + 1))
        red = _shift_fill(out[..., 0:1], r_shift, 0)[..., 0]
        green = _shift_fill(out[..., 1:2], 0, g_shift)[..., 0]
        blue = _shift_fill(out[..., 2:3], -b_shift, 0)[..., 0]
        out = np.stack([red, green, blue], axis=-1)

    jitter = max(0.0, float(scanline_jitter))
    if jitter > 1e-6:
        lines = int(round((h * 0.10) * min(1.0, jitter)))
        for _ in range(max(1, lines)):
            y = int(rng.integers(0, h))
            bright = float(0.70 + rng.random() * 0.75)
            out[y : y + 1, :, :] = np.clip(out[y : y + 1, :, :] * bright, 0.0, 1.0)

    ghost = max(0.0, float(ghosting))
    if ghost > 1e-6 and max_shift_px > 0:
        gdx = int(rng.integers(-max_shift_px, max_shift_px + 1))
        gdy = int(rng.integers(-(max_shift_px // 2), (max_shift_px // 2) + 1))
        ghost_rgb = _shift_fill(src_rgb, gdx, gdy)
        out = np.clip((out * (1.0 - ghost * 0.55)) + (ghost_rgb * ghost * 0.85), 0.0, 1.0)

    gate = max(0.0, min(1.0, float(luma_gate)))
    if gate > 1e-6:
        luma = (src_rgb[..., 0] * 0.2126) + (src_rgb[..., 1] * 0.7152) + (src_rgb[..., 2] * 0.0722)
        effect_mask = (1.0 - gate) + (gate * _smoothstep(0.35, 0.96, luma))
        out = np.clip((src_rgb * (1.0 - effect_mask[..., None])) + (out * effect_mask[..., None]), 0.0, 1.0)

    grain_amt = max(0.0, float(grain))
    if grain_amt > 1e-6:
        noise = rng.normal(0.0, grain_amt * 0.08, size=out.shape).astype(np.float32)
        out = np.clip(out + noise, 0.0, 1.0)

    return out.astype(np.float32, copy=False)


def _build_base_grid(h: int, w: int, device: torch.device, dtype: torch.dtype) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    ys = torch.linspace(-1.0, 1.0, int(h), device=device, dtype=dtype)
    xs = torch.linspace(-1.0, 1.0, int(w), device=device, dtype=dtype)
    grid_y, grid_x = torch.meshgrid(ys, xs, indexing="ij")
    base_grid = torch.stack([grid_x, grid_y], dim=-1)
    return grid_x, grid_y, base_grid


def _sample_grid(rgb_bchw: torch.Tensor, grid: torch.Tensor) -> torch.Tensor:
    return F.grid_sample(rgb_bchw, grid, mode="bilinear", padding_mode="border", align_corners=True)


def _screen_blend(base: torch.Tensor, blend: torch.Tensor) -> torch.Tensor:
    return 1.0 - ((1.0 - base) * (1.0 - blend))


def _overlay_blend(base: torch.Tensor, blend: torch.Tensor) -> torch.Tensor:
    return torch.where(base <= 0.5, 2.0 * base * blend, 1.0 - (2.0 * (1.0 - base) * (1.0 - blend)))


def _composite_mode(base: torch.Tensor, effect: torch.Tensor, mode: str) -> torch.Tensor:
    mode_key = str(mode or "replace")
    if mode_key == "screen":
        return torch.clamp(_screen_blend(base, effect), 0.0, 1.0)
    if mode_key == "add":
        return torch.clamp(base + effect, 0.0, 1.0)
    if mode_key == "overlay":
        return torch.clamp(_overlay_blend(base, effect), 0.0, 1.0)
    return torch.clamp(effect, 0.0, 1.0)


class x1Kaleido:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "segments": 6,
            "rotation": 0.0,
            "spin": 35.0,
            "zoom": 1.0,
            "center_x": 0.5,
            "center_y": 0.5,
            "source_angle": 0.0,
            "source_spread": 0.75,
            "source_orbit": 0.0,
            "prism_split": 0.08,
            "edge_fade": 0.18,
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
    RETURN_NAMES = ("image", "mask", "kaleido_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

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
                "segments": {"min": 2, "max": 32, "integer": True},
                "rotation": {"min": -180.0, "max": 180.0},
                "spin": {"min": -540.0, "max": 540.0},
                "zoom": {"min": 0.1, "max": 4.0},
                "center_x": {"min": 0.0, "max": 1.0},
                "center_y": {"min": 0.0, "max": 1.0},
                "source_angle": {"min": -180.0, "max": 180.0},
                "source_spread": {"min": 0.0, "max": 1.0},
                "source_orbit": {"min": 0.0, "max": 1.0},
                "prism_split": {"min": 0.0, "max": 1.0},
                "edge_fade": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape

        mix_clamped = float(min(1.0, max(0.0, settings["mix"])))
        seg = max(2, int(settings["segments"]))
        zoom_v = max(0.1, float(settings["zoom"]))
        prism_split = float(max(0.0, settings["prism_split"]))
        edge_fade = float(max(0.0, min(1.0, settings["edge_fade"])))
        center_x = float(settings["center_x"])
        center_y = float(settings["center_y"])
        source_angle_deg = float(settings["source_angle"])
        source_spread = float(max(0.0, min(1.0, settings["source_spread"])))
        source_orbit = float(max(0.0, min(1.0, settings["source_orbit"])))

        device = batch.device
        dtype = batch.dtype

        ys = torch.linspace(0.0, 1.0, int(h), device=device, dtype=dtype)
        xs = torch.linspace(0.0, 1.0, int(w), device=device, dtype=dtype)
        yy, xx = torch.meshgrid(ys, xs, indexing="ij")

        x = (xx - center_x) * 2.0
        y = (yy - center_y) * 2.0
        r = torch.sqrt((x * x) + (y * y) + 1e-12)
        theta = torch.atan2(y, x)

        theta = theta + math.radians(float(settings["rotation"])) + (r * math.radians(float(settings["spin"])))
        sector = (2.0 * math.pi) / float(seg)
        theta_wrapped = torch.remainder(theta + (2.0 * math.pi), 2.0 * math.pi)
        sector_index = torch.floor(theta_wrapped / sector)
        fold = torch.remainder(theta, sector)
        half_sector = sector * 0.5
        fold = torch.where(fold > half_sector, sector - fold, fold)

        source_angle = math.radians(source_angle_deg)
        source_theta = fold + source_angle + (sector_index * sector * source_spread)
        src_r = r / zoom_v
        orbit_radius = source_orbit * 0.35
        source_center_x = center_x + (math.cos(source_angle) * orbit_radius)
        source_center_y = center_y + (math.sin(source_angle) * orbit_radius)
        sx = torch.cos(source_theta) * src_r
        sy = torch.sin(source_theta) * src_r

        u = (sx * 0.5) + source_center_x
        v = (sy * 0.5) + source_center_y
        grid_x = (u * 2.0) - 1.0
        grid_y = (v * 2.0) - 1.0
        base_grid = torch.stack([grid_x, grid_y], dim=-1).unsqueeze(0).expand(int(b), -1, -1, -1)

        rgb = batch[..., :3]
        rgb_bchw = rgb.permute(0, 3, 1, 2)
        warped = _sample_grid(rgb_bchw, base_grid).permute(0, 2, 3, 1)

        if prism_split > 1e-6:
            split_uv = prism_split * 0.025
            tangent_x = -torch.sin(fold)
            tangent_y = torch.cos(fold)
            split_grid = torch.stack(
                [
                    base_grid[..., 0] + (tangent_x.unsqueeze(0) * split_uv * 2.0),
                    base_grid[..., 1] + (tangent_y.unsqueeze(0) * split_uv * 2.0),
                ],
                dim=-1,
            )
            inv_split_grid = torch.stack(
                [
                    base_grid[..., 0] - (tangent_x.unsqueeze(0) * split_uv * 2.0),
                    base_grid[..., 1] - (tangent_y.unsqueeze(0) * split_uv * 2.0),
                ],
                dim=-1,
            )
            red = _sample_grid(rgb_bchw[:, 0:1, :, :], split_grid).permute(0, 2, 3, 1)
            green = _sample_grid(rgb_bchw[:, 1:2, :, :], base_grid).permute(0, 2, 3, 1)
            blue = _sample_grid(rgb_bchw[:, 2:3, :, :], inv_split_grid).permute(0, 2, 3, 1)
            warped = torch.cat([red, green, blue], dim=-1)

        edge_ramp = torch.clamp((r - 0.62) / 0.38, 0.0, 1.0).unsqueeze(0).unsqueeze(-1)
        local_mix = mix_clamped * (1.0 - (edge_fade * edge_ramp))
        fx_rgb = torch.clamp((rgb * (1.0 - local_mix)) + (warped * local_mix), 0.0, 1.0)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
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
            "center=({:.3f},{:.3f}), source_angle={:.1f}deg, source_spread={:.2f}, source_orbit={:.2f}, "
            "prism_split={:.2f}, edge_fade={:.2f}, mix={:.2f}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            seg,
            float(settings["rotation"]),
            float(settings["spin"]),
            zoom_v,
            center_x,
            center_y,
            source_angle_deg,
            source_spread,
            source_orbit,
            prism_split,
            edge_fade,
            mix_clamped,
            float(max(0.0, settings["mask_feather"])),
            coverage * 100.0,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (out, mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1Glitch:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "slice_count": 28,
            "max_shift": 80,
            "direction": "both",
            "channel_split": 0.35,
            "scanline_jitter": 0.25,
            "grain": 0.08,
            "ghosting": 0.16,
            "luma_gate": 0.0,
            "mix": 1.0,
            "seed": 1337,
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
    RETURN_NAMES = ("image", "mask", "glitch_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

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
                "slice_count": {"min": 1, "max": 512, "integer": True},
                "max_shift": {"min": 0, "max": 1024, "integer": True},
                "channel_split": {"min": 0.0, "max": 1.0},
                "scanline_jitter": {"min": 0.0, "max": 1.0},
                "grain": {"min": 0.0, "max": 0.5},
                "ghosting": {"min": 0.0, "max": 1.0},
                "luma_gate": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "seed": {"min": 0, "max": 99999999, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )

        direction = str(settings["direction"])
        if direction not in {"horizontal", "vertical", "both"}:
            direction = "both"

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb_np = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(rgb_np)
        mix_clamped = float(max(0.0, min(1.0, settings["mix"])))

        for idx in range(int(b)):
            glitched = _apply_slice_glitch(
                src_rgb=rgb_np[idx],
                slice_count=int(settings["slice_count"]),
                max_shift=int(settings["max_shift"]),
                direction=direction,
                channel_split=float(settings["channel_split"]),
                scanline_jitter=float(settings["scanline_jitter"]),
                grain=float(settings["grain"]),
                ghosting=float(settings["ghosting"]),
                luma_gate=float(settings["luma_gate"]),
                seed=int(settings["seed"]) + idx * 7919,
            )
            out_np[idx] = np.clip((rgb_np[idx] * (1.0 - mix_clamped)) + (glitched * mix_clamped), 0.0, 1.0)

        fx_rgb = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
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
            "x1Glitch: slices={}, shift={}px, direction={}, channel_split={:.2f}, scanline_jitter={:.2f}, "
            "grain={:.2f}, ghosting={:.2f}, luma_gate={:.2f}, mix={:.2f}, seed={}, mask_feather={:.1f}px, "
            "mask_coverage={:.2f}%{}"
        ).format(
            int(max(1, settings["slice_count"])),
            int(max(0, settings["max_shift"])),
            direction,
            float(max(0.0, min(1.0, settings["channel_split"]))),
            float(max(0.0, min(1.0, settings["scanline_jitter"]))),
            float(max(0.0, settings["grain"])),
            float(max(0.0, settings["ghosting"])),
            float(max(0.0, settings["luma_gate"])),
            mix_clamped,
            int(max(0, settings["seed"])),
            float(max(0.0, settings["mask_feather"])),
            coverage * 100.0,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1AuraFlow:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "batch_size": 1,
            "palette": "aurora",
            "intensity": 1.0,
            "contrast": 1.1,
            "noise_scale": 92.0,
            "swirl": 1.1,
            "sparkle": 0.35,
            "glow": 0.45,
            "drift": 0.15,
            "composite_mode": "replace",
            "mix": 1.0,
            "seed": 2024,
            "mask_feather": 12.0,
            "invert_mask": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
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
        settings_json: str = "{}",
        image: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width": {"min": 64, "max": 4096, "integer": True},
                "height": {"min": 64, "max": 4096, "integer": True},
                "batch_size": {"min": 1, "max": 24, "integer": True},
                "intensity": {"min": 0.0, "max": 2.0},
                "contrast": {"min": 0.2, "max": 3.0},
                "noise_scale": {"min": 2.0, "max": 512.0},
                "swirl": {"min": 0.0, "max": 3.0},
                "sparkle": {"min": 0.0, "max": 1.5},
                "glow": {"min": 0.0, "max": 2.0},
                "drift": {"min": -1.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "seed": {"min": 0, "max": 99999999, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )

        w = int(max(64, settings["width"]))
        h = int(max(64, settings["height"]))
        b = int(max(1, settings["batch_size"]))
        target_device = None
        target_dtype = torch.float32
        ref = None

        if image is not None and torch.is_tensor(image):
            ref = _to_image_batch(image)
            _, h, w, _ = ref.shape
            b = int(ref.shape[0])
            target_device = ref.device
            target_dtype = ref.dtype

        palette_key = str(settings["palette"]) if str(settings["palette"]) in PALETTES else "aurora"
        palette_set = PALETTES[palette_key]
        composite_mode = str(settings["composite_mode"])
        if composite_mode not in {"replace", "screen", "add", "overlay"}:
            composite_mode = "replace"
        mix_clamped = float(max(0.0, min(1.0, settings["mix"])))

        out_np = np.empty((b, h, w, 3), dtype=np.float32)
        for idx in range(b):
            out_np[idx] = _render_aura(
                h=h,
                w=w,
                palette=palette_set,
                intensity=float(settings["intensity"]),
                contrast=float(settings["contrast"]),
                noise_scale=float(settings["noise_scale"]),
                swirl=float(settings["swirl"]),
                sparkle=float(settings["sparkle"]),
                glow=float(settings["glow"]),
                drift=float(settings["drift"]),
                seed=int(settings["seed"]) + idx * 3571,
            )

        aura = torch.from_numpy(out_np)
        if target_device is not None:
            aura = aura.to(device=target_device, dtype=target_dtype)

        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=aura.device,
            dtype=aura.dtype,
        ).unsqueeze(-1)

        if ref is not None:
            base_rgb = ref[..., :3]
            fx_rgb = _composite_mode(base_rgb, aura, composite_mode)
            blend = mask_batch * mix_clamped
            out_rgb = torch.clamp((base_rgb * (1.0 - blend)) + (fx_rgb * blend), 0.0, 1.0)
            if ref.shape[-1] == 4:
                out_rgb = torch.cat([out_rgb, ref[..., 3:4]], dim=-1)
        else:
            out_rgb = torch.clamp(aura * (mask_batch * mix_clamped), 0.0, 1.0)

        coverage = float(mask_batch.mean().item())
        info = (
            "x1AuraFlow: {}x{} x{}, palette={}, intensity={:.2f}, contrast={:.2f}, noise_scale={:.1f}, "
            "swirl={:.2f}, sparkle={:.2f}, glow={:.2f}, drift={:.2f}, mode={}, mix={:.2f}, seed={}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            w,
            h,
            b,
            palette_key,
            float(max(0.0, settings["intensity"])),
            float(max(0.2, settings["contrast"])),
            float(max(2.0, settings["noise_scale"])),
            float(max(0.0, settings["swirl"])),
            float(max(0.0, settings["sparkle"])),
            float(max(0.0, settings["glow"])),
            float(settings["drift"]),
            composite_mode,
            mix_clamped,
            int(max(0, settings["seed"])),
            float(max(0.0, settings["mask_feather"])),
            coverage * 100.0,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (out_rgb.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1PrismEcho:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "echoes": 4,
            "distance": 36.0,
            "angle": 24.0,
            "decay": 0.62,
            "chroma_split": 0.45,
            "glow": 0.28,
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
    RETURN_NAMES = ("image", "mask", "prism_echo_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

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
                "echoes": {"min": 1, "max": 8, "integer": True},
                "distance": {"min": 0.0, "max": 512.0},
                "angle": {"min": -180.0, "max": 180.0},
                "decay": {"min": 0.0, "max": 1.0},
                "chroma_split": {"min": 0.0, "max": 1.0},
                "glow": {"min": 0.0, "max": 2.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        base_rgb = batch[..., :3]
        rgb_bchw = base_rgb.permute(0, 3, 1, 2)
        _, _, base_grid = _build_base_grid(int(h), int(w), batch.device, batch.dtype)
        base_grid = base_grid.unsqueeze(0).expand(int(b), -1, -1, -1)

        echoes = max(1, int(settings["echoes"]))
        distance = float(max(0.0, settings["distance"]))
        angle_rad = math.radians(float(settings["angle"]))
        decay = float(max(0.0, min(1.0, settings["decay"])))
        chroma_split = float(max(0.0, settings["chroma_split"]))
        mix_clamped = float(max(0.0, min(1.0, settings["mix"])))
        dx_unit = math.cos(angle_rad)
        dy_unit = math.sin(angle_rad)
        trail = torch.zeros_like(base_rgb)
        weight_sum = 0.0

        for index in range(1, echoes + 1):
            t = index / float(echoes)
            shift_px = distance * t
            shift_x = (2.0 * (dx_unit * shift_px)) / max(float(w - 1), 1.0)
            shift_y = (2.0 * (dy_unit * shift_px)) / max(float(h - 1), 1.0)
            perp_px = distance * chroma_split * 0.12 * t
            perp_x = (2.0 * (-dy_unit * perp_px)) / max(float(w - 1), 1.0)
            perp_y = (2.0 * (dx_unit * perp_px)) / max(float(h - 1), 1.0)

            base_shift = base_grid.clone()
            base_shift[..., 0] -= shift_x
            base_shift[..., 1] -= shift_y

            red_grid = base_shift.clone()
            red_grid[..., 0] += perp_x
            red_grid[..., 1] += perp_y
            blue_grid = base_shift.clone()
            blue_grid[..., 0] -= perp_x
            blue_grid[..., 1] -= perp_y

            red = _sample_grid(rgb_bchw[:, 0:1, :, :], red_grid).permute(0, 2, 3, 1)
            green = _sample_grid(rgb_bchw[:, 1:2, :, :], base_shift).permute(0, 2, 3, 1)
            blue = _sample_grid(rgb_bchw[:, 2:3, :, :], blue_grid).permute(0, 2, 3, 1)
            echo = torch.cat([red, green, blue], dim=-1)
            weight = decay ** (index - 1) if echoes > 1 else 1.0
            trail = trail + (echo * weight)
            weight_sum += weight

        if weight_sum > 1e-8:
            trail = trail / weight_sum

        trail_screen = _screen_blend(base_rgb, trail)
        fx_rgb = torch.clamp(trail_screen + (trail * float(max(0.0, settings["glow"])) * 0.18), 0.0, 1.0)
        fx_rgb = torch.clamp((base_rgb * (1.0 - mix_clamped)) + (fx_rgb * mix_clamped), 0.0, 1.0)

        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        ).unsqueeze(-1)
        out_rgb = torch.clamp((base_rgb * (1.0 - mask_batch)) + (fx_rgb * mask_batch), 0.0, 1.0)

        if c == 4:
            out = torch.cat([out_rgb, batch[..., 3:4]], dim=-1)
        else:
            out = out_rgb

        coverage = float(mask_batch.mean().item())
        info = (
            "x1PrismEcho: echoes={}, distance={:.1f}px, angle={:.1f}deg, decay={:.2f}, chroma_split={:.2f}, "
            "glow={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            echoes,
            distance,
            float(settings["angle"]),
            decay,
            chroma_split,
            float(max(0.0, settings["glow"])),
            mix_clamped,
            float(max(0.0, settings["mask_feather"])),
            coverage * 100.0,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)


class x1RippleWarp:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "amplitude": 28.0,
            "frequency": 6.0,
            "phase": 0.0,
            "twist": 0.35,
            "center_x": 0.5,
            "center_y": 0.5,
            "falloff": 0.45,
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
    RETURN_NAMES = ("image", "mask", "ripple_info")
    FUNCTION = "run"
    CATEGORY = FX_PLAY

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
                "amplitude": {"min": 0.0, "max": 256.0},
                "frequency": {"min": 0.5, "max": 24.0},
                "phase": {"min": -360.0, "max": 360.0},
                "twist": {"min": -2.0, "max": 2.0},
                "center_x": {"min": 0.0, "max": 1.0},
                "center_y": {"min": 0.0, "max": 1.0},
                "falloff": {"min": 0.0, "max": 1.0},
                "mix": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        base_rgb = batch[..., :3]
        rgb_bchw = base_rgb.permute(0, 3, 1, 2)

        ys = torch.linspace(0.0, 1.0, int(h), device=batch.device, dtype=batch.dtype)
        xs = torch.linspace(0.0, 1.0, int(w), device=batch.device, dtype=batch.dtype)
        yy, xx = torch.meshgrid(ys, xs, indexing="ij")
        center_x = float(settings["center_x"])
        center_y = float(settings["center_y"])
        dx = xx - center_x
        dy = yy - center_y
        radius = torch.sqrt((dx * dx) + (dy * dy) + 1e-8)
        angle = torch.atan2(dy, dx)
        phase = math.radians(float(settings["phase"]))
        wave = torch.sin((radius * float(settings["frequency"]) * math.pi * 2.0) + phase + (angle * float(settings["twist"])))
        attenuation = torch.pow(torch.clamp(1.0 - (radius / 0.85), 0.0, 1.0), 0.55 + (float(settings["falloff"]) * 2.25))
        disp = (float(settings["amplitude"]) / max(float(min(h, w)), 1.0)) * wave * attenuation
        norm_x = dx / torch.clamp(radius, min=1e-6)
        norm_y = dy / torch.clamp(radius, min=1e-6)
        u = xx + (norm_x * disp)
        v = yy + (norm_y * disp)
        grid = torch.stack([(u * 2.0) - 1.0, (v * 2.0) - 1.0], dim=-1).unsqueeze(0).expand(int(b), -1, -1, -1)
        warped = _sample_grid(rgb_bchw, grid).permute(0, 2, 3, 1)
        mix_clamped = float(max(0.0, min(1.0, settings["mix"])))
        fx_rgb = torch.clamp((base_rgb * (1.0 - mix_clamped)) + (warped * mix_clamped), 0.0, 1.0)

        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, settings["mask_feather"])),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
            dtype=batch.dtype,
        ).unsqueeze(-1)
        out_rgb = torch.clamp((base_rgb * (1.0 - mask_batch)) + (fx_rgb * mask_batch), 0.0, 1.0)

        if c == 4:
            out = torch.cat([out_rgb, batch[..., 3:4]], dim=-1)
        else:
            out = out_rgb

        coverage = float(mask_batch.mean().item())
        info = (
            "x1RippleWarp: amplitude={:.1f}px, frequency={:.2f}, phase={:.1f}deg, twist={:.2f}, center=({:.3f},{:.3f}), "
            "falloff={:.2f}, mix={:.2f}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            float(settings["amplitude"]),
            float(settings["frequency"]),
            float(settings["phase"]),
            float(settings["twist"]),
            center_x,
            center_y,
            float(settings["falloff"]),
            mix_clamped,
            float(max(0.0, settings["mask_feather"])),
            coverage * 100.0,
            " (inverted)" if settings["invert_mask"] else "",
        )
        return (out.clamp(0.0, 1.0), mask_batch.squeeze(-1).clamp(0.0, 1.0), info)
