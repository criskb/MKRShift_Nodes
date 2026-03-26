import json
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
import torch

from ..categories import COLOR_ANALYZE, COLOR_GRADE, COLOR_LUT, COLOR_TOOLS
from .xlut import NO_LUT_SELECTED, _load_cube, _lut_options, _resolve_lut_path, _trilinear_lookup


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


def _rgb_to_hsv_np(rgb: np.ndarray):
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    h = np.zeros_like(maxc, dtype=np.float32)
    s = np.where(maxc > 1e-8, delta / np.maximum(maxc, 1e-8), 0.0).astype(np.float32, copy=False)
    v = maxc.astype(np.float32, copy=False)

    mask = delta > 1e-8
    rmax = (maxc == r) & mask
    gmax = (maxc == g) & mask
    bmax = (maxc == b) & mask

    h[rmax] = ((g[rmax] - b[rmax]) / delta[rmax]) % 6.0
    h[gmax] = ((b[gmax] - r[gmax]) / delta[gmax]) + 2.0
    h[bmax] = ((r[bmax] - g[bmax]) / delta[bmax]) + 4.0
    h = (h / 6.0) % 1.0
    return h.astype(np.float32, copy=False), s, v


def _hsv_to_rgb_np(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    h = np.mod(h, 1.0).astype(np.float32, copy=False)
    s = np.clip(s, 0.0, 1.0).astype(np.float32, copy=False)
    v = np.clip(v, 0.0, 1.0).astype(np.float32, copy=False)

    i = np.floor(h * 6.0).astype(np.int32)
    f = (h * 6.0) - i
    i = i % 6

    p = v * (1.0 - s)
    q = v * (1.0 - (f * s))
    t = v * (1.0 - ((1.0 - f) * s))

    out = np.zeros(h.shape + (3,), dtype=np.float32)
    idx = i == 0
    out[idx] = np.stack([v[idx], t[idx], p[idx]], axis=-1)
    idx = i == 1
    out[idx] = np.stack([q[idx], v[idx], p[idx]], axis=-1)
    idx = i == 2
    out[idx] = np.stack([p[idx], v[idx], t[idx]], axis=-1)
    idx = i == 3
    out[idx] = np.stack([p[idx], q[idx], v[idx]], axis=-1)
    idx = i == 4
    out[idx] = np.stack([t[idx], p[idx], v[idx]], axis=-1)
    idx = i == 5
    out[idx] = np.stack([v[idx], p[idx], q[idx]], axis=-1)
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= edge1).astype(np.float32)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32, copy=False)


def _blend_mode(src: np.ndarray, fx: np.ndarray, mode: str) -> np.ndarray:
    m = str(mode).lower()
    if m == "screen":
        return (1.0 - (1.0 - src) * (1.0 - fx)).astype(np.float32)
    if m == "overlay":
        return np.where(src <= 0.5, 2.0 * src * fx, 1.0 - 2.0 * (1.0 - src) * (1.0 - fx)).astype(np.float32)
    if m == "soft_light":
        g = np.sqrt(np.clip(src, 0.0, 1.0))
        return np.where(
            fx <= 0.5,
            src - (1.0 - (2.0 * fx)) * src * (1.0 - src),
            src + ((2.0 * fx) - 1.0) * (g - src),
        ).astype(np.float32)
    if m == "add":
        return np.clip(src + fx, 0.0, 1.0).astype(np.float32)
    return np.clip(fx, 0.0, 1.0).astype(np.float32)


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
    rgb = batch[..., :3]
    alpha = batch[..., 3:4] if c == 4 else None

    mask_batch = _mask_to_batch(
        mask=mask,
        batch=int(b),
        h=int(h),
        w=int(w),
        feather_radius=float(max(0.0, mask_feather)),
        invert_mask=bool(invert_mask),
        device=batch.device,
    ).unsqueeze(-1)

    src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
    fx_np = np.empty_like(src_np)
    matte_np = np.ones((int(b), int(h), int(w)), dtype=np.float32)

    for idx in range(int(b)):
        fx_result = fx_fn(src_np[idx], idx)
        if isinstance(fx_result, tuple):
            fx_np[idx] = np.clip(fx_result[0], 0.0, 1.0)
            matte_np[idx] = np.clip(fx_result[1], 0.0, 1.0)
        else:
            fx_np[idx] = np.clip(fx_result, 0.0, 1.0)

    fx_t = torch.from_numpy(np.clip(fx_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
    matte_t = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype).unsqueeze(-1)
    final_mask = (mask_batch * matte_t).clamp(0.0, 1.0)

    out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
    out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

    coverage = float(final_mask.mean().item()) * 100.0
    info = "{}: {}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}".format(
        label,
        detail,
        float(max(0.0, mask_feather)),
        coverage,
        " (inverted)" if invert_mask else "",
    )
    return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1LUTBlend:
    @classmethod
    def INPUT_TYPES(cls):
        lut_choices = _lut_options()
        return {
            "required": {
                "image": ("IMAGE",),
                "lut_a": (lut_choices, {"default": NO_LUT_SELECTED}),
                "mix_a": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "lut_b": (lut_choices, {"default": NO_LUT_SELECTED}),
                "mix_b": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "lut_c": (lut_choices, {"default": NO_LUT_SELECTED}),
                "mix_c": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "blend_mode": (["normal", "screen", "overlay", "soft_light", "add"],),
                "intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                **{
                    "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                    "invert_mask": ("BOOLEAN", {"default": False}),
                },
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "lut_blend_info")
    FUNCTION = "run"
    CATEGORY = COLOR_LUT

    def run(
        self,
        image: torch.Tensor,
        lut_a: str = NO_LUT_SELECTED,
        mix_a: float = 1.0,
        lut_b: str = NO_LUT_SELECTED,
        mix_b: float = 0.0,
        lut_c: str = NO_LUT_SELECTED,
        mix_c: float = 0.0,
        blend_mode: str = "normal",
        intensity: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        luts = [(str(lut_a), float(max(0.0, mix_a))), (str(lut_b), float(max(0.0, mix_b))), (str(lut_c), float(max(0.0, mix_c)))]
        loaded = []
        warnings = []
        for lut_name, lut_mix in luts:
            if lut_mix <= 1e-6 or lut_name == NO_LUT_SELECTED:
                continue
            resolved, resolve_info = _resolve_lut_path(lut_name=lut_name)
            if resolve_info:
                warnings.append(resolve_info)
            if not resolved:
                continue
            try:
                cube = _load_cube(resolved)
                loaded.append((cube, lut_mix))
            except Exception as exc:
                warnings.append(f"Failed to load {lut_name}: {exc}")

        mode = str(blend_mode).lower()
        inten = float(np.clip(intensity, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            if not loaded:
                return src
            acc = np.zeros_like(src, dtype=np.float32)
            wsum = 0.0
            for cube, lut_mix in loaded:
                mapped = _trilinear_lookup(src, cube)
                acc += mapped * float(lut_mix)
                wsum += float(lut_mix)
            target = src if wsum <= 1e-8 else np.clip(acc / wsum, 0.0, 1.0)
            blended = _blend_mode(src, target, mode)
            return np.clip((src * (1.0 - inten)) + (blended * inten), 0.0, 1.0).astype(np.float32, copy=False)

        lut_info = "none" if not loaded else ", ".join([f"{cube.title}@{w:.2f}" for cube, w in loaded])
        warn = "" if not warnings else f", warnings={'; '.join(warnings)}"
        detail = "luts=[{}], blend={}, intensity={:.2f}{}".format(lut_info, mode, inten, warn)
        return _run_masked_rgb_node(
            label="x1LUTBlend",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1ColorWheels:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "lift_r": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "lift_g": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "lift_b": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "gamma_r": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "gamma_g": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "gamma_b": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "gain_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "gain_g": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "gain_b": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "offset_r": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "offset_g": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "offset_b": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "balance": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                **{
                    "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                    "invert_mask": ("BOOLEAN", {"default": False}),
                },
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "color_wheels_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        lift_r: float = 0.0,
        lift_g: float = 0.0,
        lift_b: float = 0.0,
        gamma_r: float = 1.0,
        gamma_g: float = 1.0,
        gamma_b: float = 1.0,
        gain_r: float = 1.0,
        gain_g: float = 1.0,
        gain_b: float = 1.0,
        offset_r: float = 0.0,
        offset_g: float = 0.0,
        offset_b: float = 0.0,
        balance: float = 0.0,
        saturation: float = 1.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        lift = np.asarray([lift_r, lift_g, lift_b], dtype=np.float32)
        gamma = np.asarray([max(0.1, gamma_r), max(0.1, gamma_g), max(0.1, gamma_b)], dtype=np.float32)
        gain = np.asarray([max(0.0, gain_r), max(0.0, gain_g), max(0.0, gain_b)], dtype=np.float32)
        offset = np.asarray([offset_r, offset_g, offset_b], dtype=np.float32)
        bal = float(np.clip(balance, -1.0, 1.0))
        sat = float(max(0.0, saturation))
        m = float(np.clip(mix, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
            sh_pivot = np.clip(0.55 + (bal * 0.20), 0.2, 0.9)
            hi_pivot = np.clip(0.45 + (bal * 0.20), 0.1, 0.8)

            shadow_w = np.clip((sh_pivot - luma) / max(1e-6, sh_pivot), 0.0, 1.0)
            shadow_w = np.power(shadow_w, 1.35).astype(np.float32, copy=False)
            highlight_w = np.clip((luma - hi_pivot) / max(1e-6, 1.0 - hi_pivot), 0.0, 1.0)
            highlight_w = np.power(highlight_w, 1.35).astype(np.float32, copy=False)

            out = src.copy()
            out = out + (shadow_w[..., None] * lift[None, None, :])
            out = np.clip(out, 0.0, 1.0)
            out = np.power(np.clip(out, 0.0, 1.0), 1.0 / gamma[None, None, :]).astype(np.float32, copy=False)
            out = out * (1.0 + (highlight_w[..., None] * (gain[None, None, :] - 1.0)))
            out = out + offset[None, None, :]
            out = np.clip(out, 0.0, 1.0)

            out_luma = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
            out = out_luma + ((out - out_luma) * sat)
            out = np.clip(out, 0.0, 1.0)
            return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "lift=({:.2f},{:.2f},{:.2f}), gamma=({:.2f},{:.2f},{:.2f}), gain=({:.2f},{:.2f},{:.2f}), offset=({:.2f},{:.2f},{:.2f}), balance={:.2f}, sat={:.2f}, mix={:.2f}".format(
            float(lift[0]),
            float(lift[1]),
            float(lift[2]),
            float(gamma[0]),
            float(gamma[1]),
            float(gamma[2]),
            float(gain[0]),
            float(gain[1]),
            float(gain[2]),
            float(offset[0]),
            float(offset[1]),
            float(offset[2]),
            bal,
            sat,
            m,
        )
        return _run_masked_rgb_node(
            label="x1ColorWheels",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1HSLQualifier:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "hue_center": ("FLOAT", {"default": 220.0, "min": 0.0, "max": 360.0, "step": 1.0}),
                "hue_width": ("FLOAT", {"default": 40.0, "min": 1.0, "max": 180.0, "step": 1.0}),
                "sat_min": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sat_max": ("FLOAT", {"default": 1.00, "min": 0.0, "max": 1.0, "step": 0.01}),
                "val_min": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "val_max": ("FLOAT", {"default": 1.00, "min": 0.0, "max": 1.0, "step": 0.01}),
                "feather": ("FLOAT", {"default": 18.0, "min": 0.0, "max": 120.0, "step": 0.5}),
                "hue_shift": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 0.5}),
                "sat_shift": ("FLOAT", {"default": 0.25, "min": -1.0, "max": 1.0, "step": 0.01}),
                "val_shift": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "show_matte": ("BOOLEAN", {"default": False}),
                **{
                    "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                    "invert_mask": ("BOOLEAN", {"default": False}),
                },
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "hsl_qualifier_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        hue_center: float = 220.0,
        hue_width: float = 40.0,
        sat_min: float = 0.08,
        sat_max: float = 1.00,
        val_min: float = 0.05,
        val_max: float = 1.00,
        feather: float = 18.0,
        hue_shift: float = 0.0,
        sat_shift: float = 0.25,
        val_shift: float = 0.0,
        amount: float = 1.0,
        show_matte: bool = False,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        hc = (float(hue_center) % 360.0) / 360.0
        hw = max(1.0, float(hue_width)) * 0.5 / 360.0
        feather_h = max(0.0, float(feather)) / 360.0
        smin = float(np.clip(min(sat_min, sat_max), 0.0, 1.0))
        smax = float(np.clip(max(sat_min, sat_max), 0.0, 1.0))
        vmin = float(np.clip(min(val_min, val_max), 0.0, 1.0))
        vmax = float(np.clip(max(val_min, val_max), 0.0, 1.0))
        amt = float(np.clip(amount, 0.0, 1.0))
        hs = float(hue_shift) / 360.0
        ss = float(sat_shift)
        vs = float(val_shift)
        matte_view = bool(show_matte)

        def fx_fn(src: np.ndarray, _: int):
            h, s, v = _rgb_to_hsv_np(src)

            dist = np.abs(((h - hc + 0.5) % 1.0) - 0.5)
            hsel = 1.0 - _smoothstep(hw, hw + feather_h, dist)

            sfeather = min(0.5, max(0.001, feather_h * 2.2))
            vfeather = min(0.5, max(0.001, feather_h * 2.2))
            ssel = _smoothstep(smin - sfeather, smin + sfeather, s) * (1.0 - _smoothstep(smax - sfeather, smax + sfeather, s))
            vsel = _smoothstep(vmin - vfeather, vmin + vfeather, v) * (1.0 - _smoothstep(vmax - vfeather, vmax + vfeather, v))

            matte = np.clip(hsel * ssel * vsel * amt, 0.0, 1.0).astype(np.float32, copy=False)
            hh = np.mod(h + (matte * hs), 1.0)
            ss_out = np.clip(s + (matte * ss), 0.0, 1.0)
            vv_out = np.clip(v + (matte * vs), 0.0, 1.0)
            graded = _hsv_to_rgb_np(hh, ss_out, vv_out)

            if matte_view:
                matte_rgb = np.repeat(matte[..., None], 3, axis=-1)
                return matte_rgb.astype(np.float32, copy=False), matte
            out = np.clip((src * (1.0 - matte[..., None])) + (graded * matte[..., None]), 0.0, 1.0)
            return out.astype(np.float32, copy=False), matte

        detail = "center={:.1f}, width={:.1f}, sat=[{:.2f},{:.2f}], val=[{:.2f},{:.2f}], feather={:.1f}, shift=(h{:.1f},s{:.2f},v{:.2f}), amount={:.2f}, matte_view={}".format(
            float(hue_center % 360.0),
            float(max(1.0, hue_width)),
            smin,
            smax,
            vmin,
            vmax,
            float(max(0.0, feather)),
            float(hue_shift),
            ss,
            vs,
            amt,
            matte_view,
        )
        return _run_masked_rgb_node(
            label="x1HSLQualifier",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


def _apply_stack_look(src: np.ndarray, look: str, strength: float) -> np.ndarray:
    m = float(np.clip(strength, 0.0, 1.0))
    if m <= 1e-6:
        return src
    key = str(look).lower()
    out = src.copy()
    luma = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]).astype(np.float32, copy=False)
    sh = np.clip((0.55 - luma) / 0.55, 0.0, 1.0)[..., None]
    hi = np.clip((luma - 0.45) / 0.55, 0.0, 1.0)[..., None]

    if key == "teal_orange":
        out = out * (1.0 - (0.20 * sh)) + np.asarray([0.12, 0.68, 0.78], dtype=np.float32)[None, None, :] * (0.20 * sh)
        out = out * (1.0 - (0.24 * hi)) + np.asarray([1.0, 0.58, 0.20], dtype=np.float32)[None, None, :] * (0.24 * hi)
    elif key == "warm_fade":
        out = np.power(np.clip(out, 0.0, 1.0), 0.88).astype(np.float32, copy=False)
        out = out * 0.92 + 0.08
        out[..., 0] *= 1.08
        out[..., 1] *= 1.03
    elif key == "cool_fade":
        out = np.power(np.clip(out, 0.0, 1.0), 0.92).astype(np.float32, copy=False)
        out = out * 0.94 + 0.06
        out[..., 2] *= 1.10
        out[..., 1] *= 1.02
    elif key == "cross_process":
        out[..., 0] = np.clip(np.power(np.clip(out[..., 0], 0.0, 1.0), 0.82), 0.0, 1.0)
        out[..., 1] = np.clip(np.power(np.clip(out[..., 1], 0.0, 1.0), 1.10), 0.0, 1.0)
        out[..., 2] = np.clip(np.power(np.clip(out[..., 2], 0.0, 1.0), 1.18), 0.0, 1.0)
    elif key == "bleach_bypass":
        gray = luma[..., None]
        out = np.clip((out * 0.62) + (gray * 0.38), 0.0, 1.0)
        out = np.clip((out - 0.5) * 1.15 + 0.5, 0.0, 1.0)
    elif key == "print_film":
        out = np.clip((out - 0.5) * 1.08 + 0.5, 0.0, 1.0)
        out[..., 0] *= 1.03
        out[..., 1] *= 1.00
        out[..., 2] *= 0.97
    else:
        return src

    out = np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)


def _curve_basis(x: np.ndarray):
    shadows = np.power(1.0 - x, 2.0)
    mids = 4.0 * x * (1.0 - x)
    highs = np.power(x, 2.0)
    return shadows, mids, highs


def _apply_curve_triplet(x: np.ndarray, s: float, m: float, h: float, amount: float = 0.5) -> np.ndarray:
    bs, bm, bh = _curve_basis(x)
    out = x + (amount * ((s * bs) + (m * bm) + (h * bh)))
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def _parse_warp_points(raw: str, mode: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    text = str(raw or "").strip()
    if not text:
        return ([], warnings)
    try:
        payload = json.loads(text)
    except Exception:
        return ([], ["warp_points_json is not valid JSON"])
    if not isinstance(payload, list):
        return ([], ["warp_points_json must be a JSON array"])
    points: list[dict] = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            warnings.append(f"warp point {idx} is not an object")
            continue
        src_x = float(np.clip(item.get("src_x", 0.5), 0.0, 1.0))
        src_y = float(np.clip(item.get("src_y", 0.5), 0.0, 1.0))
        dst_x = float(np.clip(item.get("dst_x", src_x), 0.0, 1.0))
        dst_y = float(np.clip(item.get("dst_y", src_y), 0.0, 1.0))
        radius = float(np.clip(item.get("radius", 0.16), 0.02, 0.6))
        weight = float(np.clip(item.get("weight", 1.0), 0.0, 2.0))
        points.append(
            {
                "src_x": src_x,
                "src_y": src_y,
                "dst_x": dst_x,
                "dst_y": dst_y,
                "radius": radius,
                "weight": weight,
            }
        )
    return (points, warnings)


def _apply_warp_field(
    base_x: np.ndarray,
    base_y: np.ndarray,
    points: list[dict],
    strength: float,
) -> tuple[np.ndarray, np.ndarray]:
    dx = np.zeros_like(base_x, dtype=np.float32)
    dy = np.zeros_like(base_y, dtype=np.float32)
    wsum = np.zeros_like(base_x, dtype=np.float32)
    for point in points:
        sx = point["src_x"]
        sy = point["src_y"]
        tx = point["dst_x"]
        ty = point["dst_y"]
        radius = max(1e-4, float(point["radius"]))
        weight = float(point["weight"])

        dist = np.sqrt(((base_x - sx) ** 2) + ((base_y - sy) ** 2)).astype(np.float32, copy=False)
        norm = np.clip(1.0 - (dist / radius), 0.0, 1.0)
        influence = np.power(norm, 2.0).astype(np.float32, copy=False) * weight

        dx += (tx - sx) * influence
        dy += (ty - sy) * influence
        wsum += influence

    mask = wsum > 1e-6
    out_x = base_x.copy()
    out_y = base_y.copy()
    out_x[mask] = np.clip(base_x[mask] + ((dx[mask] / wsum[mask]) * strength), 0.0, 1.0)
    out_y[mask] = np.clip(base_y[mask] + ((dy[mask] / wsum[mask]) * strength), 0.0, 1.0)
    return (out_x, out_y)


def _palette_from_preset(
    preset: str,
    custom: np.ndarray,
) -> np.ndarray:
    presets = {
        "teal_orange": np.asarray(
            [
                [0.08, 0.22, 0.28],
                [0.18, 0.52, 0.62],
                [0.84, 0.52, 0.22],
                [1.00, 0.80, 0.55],
            ],
            dtype=np.float32,
        ),
        "pastel_pop": np.asarray(
            [
                [0.62, 0.74, 0.94],
                [0.94, 0.68, 0.74],
                [0.86, 0.90, 0.62],
                [0.94, 0.86, 0.72],
            ],
            dtype=np.float32,
        ),
        "neon_night": np.asarray(
            [
                [0.05, 0.07, 0.12],
                [0.00, 0.86, 0.92],
                [0.88, 0.18, 1.00],
                [0.98, 0.96, 0.42],
            ],
            dtype=np.float32,
        ),
        "earth_film": np.asarray(
            [
                [0.18, 0.14, 0.11],
                [0.42, 0.34, 0.25],
                [0.66, 0.54, 0.38],
                [0.88, 0.76, 0.58],
            ],
            dtype=np.float32,
        ),
        "mono_tint": np.asarray(
            [
                [0.12, 0.12, 0.12],
                [0.36, 0.40, 0.44],
                [0.62, 0.68, 0.74],
                [0.92, 0.95, 0.98],
            ],
            dtype=np.float32,
        ),
    }
    if str(preset).lower() == "custom":
        return np.clip(custom, 0.0, 1.0).astype(np.float32, copy=False)
    return presets.get(str(preset).lower(), presets["teal_orange"]).astype(np.float32, copy=False)


def _resize_rgb_np(rgb: np.ndarray, h: int, w: int) -> np.ndarray:
    if rgb.shape[0] == h and rgb.shape[1] == w:
        return rgb.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


class x1LUTStack:
    @classmethod
    def INPUT_TYPES(cls):
        looks = ["none", "teal_orange", "warm_fade", "cool_fade", "cross_process", "bleach_bypass", "print_film"]
        return {
            "required": {
                "image": ("IMAGE",),
                "look_a": (looks,),
                "strength_a": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
                "look_b": (looks,),
                "strength_b": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "look_c": (looks,),
                "strength_c": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.2, "max": 2.5, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.5, "step": 0.01}),
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
    RETURN_NAMES = ("image", "mask", "lut_stack_info")
    FUNCTION = "run"
    CATEGORY = COLOR_LUT

    def run(
        self,
        image: torch.Tensor,
        look_a: str = "teal_orange",
        strength_a: float = 0.75,
        look_b: str = "none",
        strength_b: float = 0.0,
        look_c: str = "none",
        strength_c: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        fade: float = 0.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        c = float(max(0.2, contrast))
        s = float(max(0.0, saturation))
        f = float(np.clip(fade, 0.0, 0.6))
        m = float(np.clip(mix, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            out = src.copy()
            for lk, st in ((look_a, strength_a), (look_b, strength_b), (look_c, strength_c)):
                out = _apply_stack_look(out, lk, float(st))
            out = np.clip((out - 0.5) * c + 0.5, 0.0, 1.0)
            luma = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
            out = luma + ((out - luma) * s)
            if f > 1e-6:
                out = np.clip((out * (1.0 - f)) + f, 0.0, 1.0)
            return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "a={}@{:.2f}, b={}@{:.2f}, c={}@{:.2f}, contrast={:.2f}, sat={:.2f}, fade={:.2f}, mix={:.2f}".format(
            str(look_a),
            float(np.clip(strength_a, 0.0, 1.0)),
            str(look_b),
            float(np.clip(strength_b, 0.0, 1.0)),
            str(look_c),
            float(np.clip(strength_c, 0.0, 1.0)),
            c,
            s,
            f,
            m,
        )
        return _run_masked_rgb_node(
            label="x1LUTStack",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1Curves:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "master_shadows": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "master_midtones": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "master_highlights": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "red_curve": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "green_curve": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "blue_curve": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.3, "max": 2.5, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "curves_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        master_shadows: float = 0.0,
        master_midtones: float = 0.0,
        master_highlights: float = 0.0,
        red_curve: float = 0.0,
        green_curve: float = 0.0,
        blue_curve: float = 0.0,
        contrast: float = 1.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        c = float(max(0.3, contrast))
        m = float(np.clip(mix, 0.0, 1.0))

        ms = float(np.clip(master_shadows, -1.0, 1.0))
        mm = float(np.clip(master_midtones, -1.0, 1.0))
        mh = float(np.clip(master_highlights, -1.0, 1.0))
        rc = float(np.clip(red_curve, -1.0, 1.0))
        gc = float(np.clip(green_curve, -1.0, 1.0))
        bc = float(np.clip(blue_curve, -1.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            out = _apply_curve_triplet(src, ms, mm, mh, amount=0.45)
            out_r = _apply_curve_triplet(out[..., 0], rc, rc * 0.25, -rc, amount=0.30)
            out_g = _apply_curve_triplet(out[..., 1], gc, gc * 0.25, -gc, amount=0.30)
            out_b = _apply_curve_triplet(out[..., 2], bc, bc * 0.25, -bc, amount=0.30)
            out = np.stack([out_r, out_g, out_b], axis=-1).astype(np.float32, copy=False)
            out = np.clip((out - 0.5) * c + 0.5, 0.0, 1.0)
            return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "master=({:.2f},{:.2f},{:.2f}), rgb=({:.2f},{:.2f},{:.2f}), contrast={:.2f}, mix={:.2f}".format(
            ms,
            mm,
            mh,
            rc,
            gc,
            bc,
            c,
            m,
        )
        return _run_masked_rgb_node(
            label="x1Curves",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1ColorBalance:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "slope_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "slope_g": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "slope_b": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "offset_r": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "offset_g": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "offset_b": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "power_r": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "power_g": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "power_b": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": True}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "color_balance_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        slope_r: float = 1.0,
        slope_g: float = 1.0,
        slope_b: float = 1.0,
        offset_r: float = 0.0,
        offset_g: float = 0.0,
        offset_b: float = 0.0,
        power_r: float = 1.0,
        power_g: float = 1.0,
        power_b: float = 1.0,
        saturation: float = 1.0,
        mix: float = 1.0,
        preserve_luma: bool = True,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        slope = np.asarray([max(0.0, slope_r), max(0.0, slope_g), max(0.0, slope_b)], dtype=np.float32)
        offset = np.asarray([offset_r, offset_g, offset_b], dtype=np.float32)
        power = np.asarray([max(0.1, power_r), max(0.1, power_g), max(0.1, power_b)], dtype=np.float32)
        sat = float(max(0.0, saturation))
        m = float(np.clip(mix, 0.0, 1.0))
        keep_luma = bool(preserve_luma)

        def fx_fn(src: np.ndarray, _: int):
            out = (src * slope[None, None, :]) + offset[None, None, :]
            out = np.power(np.clip(out, 0.0, 1.0), power[None, None, :]).astype(np.float32, copy=False)
            luma = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
            out = luma + ((out - luma) * sat)
            out = np.clip(out, 0.0, 1.0)
            if keep_luma:
                src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])[..., None]
                out_l = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
                out = np.clip(out * (src_l / np.maximum(out_l, 1e-6)), 0.0, 1.0)
            return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "slope=({:.2f},{:.2f},{:.2f}), offset=({:.2f},{:.2f},{:.2f}), power=({:.2f},{:.2f},{:.2f}), sat={:.2f}, mix={:.2f}, preserve_luma={}".format(
            float(slope[0]),
            float(slope[1]),
            float(slope[2]),
            float(offset[0]),
            float(offset[1]),
            float(offset[2]),
            float(power[0]),
            float(power[1]),
            float(power[2]),
            sat,
            m,
            keep_luma,
        )
        return _run_masked_rgb_node(
            label="x1ColorBalance",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1ColorWarpHueSat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "warp_points_json": ("STRING", {"default": "[]", "multiline": True}),
                "strength": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "falloff": ("FLOAT", {"default": 1.0, "min": 0.4, "max": 2.5, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "color_warp_huesat_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        warp_points_json: str = "[]",
        strength: float = 0.7,
        falloff: float = 1.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        points, warnings = _parse_warp_points(warp_points_json, mode="huesat")
        st = float(max(0.0, strength))
        fo = float(max(0.4, falloff))
        m = float(np.clip(mix, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            h, s, v = _rgb_to_hsv_np(src)
            target_h, target_s = _apply_warp_field(h, s, points, st)
            blend = np.clip(np.power(np.maximum(s, 1e-5), 1.0 / fo), 0.0, 1.0).astype(np.float32, copy=False)
            h_out = (h * (1.0 - blend)) + (target_h * blend)
            s_out = np.clip((s * (1.0 - blend)) + (target_s * blend), 0.0, 1.0)
            warped = _hsv_to_rgb_np(np.mod(h_out, 1.0), s_out, v)
            return np.clip((src * (1.0 - m)) + (warped * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "points={}, strength={:.2f}, falloff={:.2f}, mix={:.2f}{}".format(
            len(points),
            st,
            fo,
            m,
            f", warnings={'; '.join(warnings)}" if warnings else "",
        )
        return _run_masked_rgb_node(
            label="x1ColorWarpHueSat",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1ColorWarpChromaLuma:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "warp_points_json": ("STRING", {"default": "[]", "multiline": True}),
                "strength": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 2.0, "step": 0.01}),
                "falloff": ("FLOAT", {"default": 1.0, "min": 0.4, "max": 2.5, "step": 0.01}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "color_warp_chromaluma_info")
    FUNCTION = "run"
    CATEGORY = COLOR_GRADE

    def run(
        self,
        image: torch.Tensor,
        warp_points_json: str = "[]",
        strength: float = 0.65,
        falloff: float = 1.0,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        points, warnings = _parse_warp_points(warp_points_json, mode="chromaluma")
        st = float(max(0.0, strength))
        fo = float(max(0.4, falloff))
        m = float(np.clip(mix, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            h, s, v = _rgb_to_hsv_np(src)
            target_s, target_v = _apply_warp_field(s, v, points, st)
            blend = np.clip(np.power(np.maximum(v, 1e-5), 1.0 / fo), 0.0, 1.0).astype(np.float32, copy=False)
            s_out = np.clip((s * (1.0 - blend)) + (target_s * blend), 0.0, 1.0)
            v_out = np.clip((v * (1.0 - blend)) + (target_v * blend), 0.0, 1.0)
            warped = _hsv_to_rgb_np(h, s_out, v_out)
            return np.clip((src * (1.0 - m)) + (warped * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "points={}, strength={:.2f}, falloff={:.2f}, mix={:.2f}{}".format(
            len(points),
            st,
            fo,
            m,
            f", warnings={'; '.join(warnings)}" if warnings else "",
        )
        return _run_masked_rgb_node(
            label="x1ColorWarpChromaLuma",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1PaletteMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette_preset": (["teal_orange", "pastel_pop", "neon_night", "earth_film", "mono_tint", "custom"],),
                "mapping_mode": (["nearest", "soft"],),
                "softness": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 4.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": True}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c1_r": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c1_g": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c1_b": ("FLOAT", {"default": 0.28, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c2_r": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c2_g": ("FLOAT", {"default": 0.52, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c2_b": ("FLOAT", {"default": 0.62, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c3_r": ("FLOAT", {"default": 0.84, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c3_g": ("FLOAT", {"default": 0.52, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c3_b": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c4_r": ("FLOAT", {"default": 1.00, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c4_g": ("FLOAT", {"default": 0.80, "min": 0.0, "max": 1.0, "step": 0.01}),
                "c4_b": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "palette_map_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        palette_preset: str = "teal_orange",
        mapping_mode: str = "soft",
        softness: float = 0.5,
        preserve_luma: bool = True,
        amount: float = 1.0,
        c1_r: float = 0.08,
        c1_g: float = 0.22,
        c1_b: float = 0.28,
        c2_r: float = 0.18,
        c2_g: float = 0.52,
        c2_b: float = 0.62,
        c3_r: float = 0.84,
        c3_g: float = 0.52,
        c3_b: float = 0.22,
        c4_r: float = 1.00,
        c4_g: float = 0.80,
        c4_b: float = 0.55,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        custom = np.asarray(
            [
                [c1_r, c1_g, c1_b],
                [c2_r, c2_g, c2_b],
                [c3_r, c3_g, c3_b],
                [c4_r, c4_g, c4_b],
            ],
            dtype=np.float32,
        )
        palette = _palette_from_preset(str(palette_preset), custom)
        mode = str(mapping_mode).lower()
        soft = float(max(0.01, softness))
        amt = float(np.clip(amount, 0.0, 1.0))
        keep_luma = bool(preserve_luma)

        def fx_fn(src: np.ndarray, _: int):
            flat = src.reshape(-1, 3)
            dist = np.sum((flat[:, None, :] - palette[None, :, :]) ** 2, axis=-1)
            if mode == "nearest":
                idx = np.argmin(dist, axis=1)
                mapped = palette[idx]
            else:
                weights = np.exp(-dist * (soft * 8.0)).astype(np.float32, copy=False)
                weights_sum = np.maximum(np.sum(weights, axis=1, keepdims=True), 1e-6)
                mapped = (weights[..., None] * palette[None, :, :]).sum(axis=1) / weights_sum
            mapped = mapped.reshape(src.shape).astype(np.float32, copy=False)
            if keep_luma:
                src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])[..., None]
                map_l = (0.2126 * mapped[..., 0] + 0.7152 * mapped[..., 1] + 0.0722 * mapped[..., 2])[..., None]
                mapped = np.clip(mapped * (src_l / np.maximum(map_l, 1e-6)), 0.0, 1.0)
            return np.clip((src * (1.0 - amt)) + (mapped * amt), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "preset={}, mode={}, softness={:.2f}, preserve_luma={}, amount={:.2f}".format(
            str(palette_preset),
            mode,
            soft,
            keep_luma,
            amt,
        )
        return _run_masked_rgb_node(
            label="x1PaletteMap",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1ColorMatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "reference_image": ("IMAGE",),
                "method": (["mean_std", "mean_only"],),
                "strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": False}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "color_match_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        reference_image: torch.Tensor,
        method: str = "mean_std",
        strength: float = 0.85,
        preserve_luma: bool = False,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        ref_batch = _to_image_batch(reference_image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        ref_np = ref_batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)

        comp_mask = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(max(0.0, mask_feather)),
            invert_mask=bool(invert_mask),
            device=batch.device,
        ).unsqueeze(-1)

        out_np = np.empty_like(src_np)
        m = str(method).lower()
        amt = float(np.clip(strength, 0.0, 1.0))
        keep_luma = bool(preserve_luma)

        for idx in range(int(b)):
            src = src_np[idx]
            ref = ref_np[idx if idx < ref_np.shape[0] else (ref_np.shape[0] - 1)]
            ref = _resize_rgb_np(ref, int(h), int(w))

            src_mean = src.reshape(-1, 3).mean(axis=0)
            ref_mean = ref.reshape(-1, 3).mean(axis=0)

            if m == "mean_only":
                matched = src + (ref_mean[None, None, :] - src_mean[None, None, :])
            else:
                src_std = src.reshape(-1, 3).std(axis=0)
                ref_std = ref.reshape(-1, 3).std(axis=0)
                matched = ((src - src_mean[None, None, :]) / np.maximum(src_std[None, None, :], 1e-6))
                matched = matched * ref_std[None, None, :] + ref_mean[None, None, :]

            matched = np.clip(matched, 0.0, 1.0).astype(np.float32, copy=False)
            if keep_luma:
                src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])[..., None]
                mat_l = (0.2126 * matched[..., 0] + 0.7152 * matched[..., 1] + 0.0722 * matched[..., 2])[..., None]
                matched = np.clip(matched * (src_l / np.maximum(mat_l, 1e-6)), 0.0, 1.0)

            out_np[idx] = np.clip((src * (1.0 - amt)) + (matched * amt), 0.0, 1.0).astype(np.float32, copy=False)

        fx_t = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        out_rgb = torch.clamp((rgb * (1.0 - comp_mask)) + (fx_t * comp_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb
        coverage = float(comp_mask.mean().item()) * 100.0

        info = "x1ColorMatch: method={}, strength={:.2f}, preserve_luma={}, ref_batch={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}".format(
            m,
            amt,
            keep_luma,
            int(ref_np.shape[0]),
            float(max(0.0, mask_feather)),
            coverage,
            " (inverted)" if invert_mask else "",
        )
        return (out.clamp(0.0, 1.0), comp_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1GamutMap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "compression": ("FLOAT", {"default": 0.25, "min": -1.0, "max": 1.0, "step": 0.01}),
                "rolloff": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "highlight_protect": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_luma": ("BOOLEAN", {"default": True}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "gamut_map_info")
    FUNCTION = "run"
    CATEGORY = COLOR_TOOLS

    def run(
        self,
        image: torch.Tensor,
        compression: float = 0.25,
        rolloff: float = 0.35,
        saturation: float = 1.0,
        highlight_protect: float = 0.25,
        preserve_luma: bool = True,
        mix: float = 1.0,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        comp = float(np.clip(compression, -1.0, 1.0))
        ro = float(np.clip(rolloff, 0.0, 1.0))
        sat = float(max(0.0, saturation))
        hp = float(np.clip(highlight_protect, 0.0, 1.0))
        keep_luma = bool(preserve_luma)
        m = float(np.clip(mix, 0.0, 1.0))

        def fx_fn(src: np.ndarray, _: int):
            if comp >= 0.0:
                scale = 1.0 - (0.88 * comp)
            else:
                scale = 1.0 + (1.10 * abs(comp))
            out = 0.5 + ((src - 0.5) * scale)

            if ro > 1e-6:
                over = np.maximum(out - 1.0, 0.0)
                under = np.maximum(-out, 0.0)
                out = out - (over * ro) + (under * ro)

            out = np.clip(out, 0.0, 1.0)
            out_l = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
            out = out_l + ((out - out_l) * sat)
            out = np.clip(out, 0.0, 1.0)

            if hp > 1e-6:
                src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])
                protect = _smoothstep(1.0 - hp, 1.0, src_l)[..., None]
                out = (out * (1.0 - protect)) + (src * protect)

            if keep_luma:
                src_l = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2])[..., None]
                out_l = (0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2])[..., None]
                out = np.clip(out * (src_l / np.maximum(out_l, 1e-6)), 0.0, 1.0)

            return np.clip((src * (1.0 - m)) + (out * m), 0.0, 1.0).astype(np.float32, copy=False)

        detail = "compression={:.2f}, rolloff={:.2f}, saturation={:.2f}, highlight_protect={:.2f}, preserve_luma={}, mix={:.2f}".format(
            comp,
            ro,
            sat,
            hp,
            keep_luma,
            m,
        )
        return _run_masked_rgb_node(
            label="x1GamutMap",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )


class x1FalseColor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["luma_ramp", "exposure_zones", "clipping"],),
                "overlay_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "zebra_threshold": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "low_clip": ("FLOAT", {"default": 0.02, "min": 0.0, "max": 1.0, "step": 0.01}),
                "high_clip": ("FLOAT", {"default": 0.98, "min": 0.0, "max": 1.0, "step": 0.01}),
                "show_zebra": ("BOOLEAN", {"default": True}),
                "mask_feather": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "invert_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "false_color_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        mode: str = "luma_ramp",
        overlay_opacity: float = 1.0,
        zebra_threshold: float = 0.95,
        low_clip: float = 0.02,
        high_clip: float = 0.98,
        show_zebra: bool = True,
        mask_feather: float = 12.0,
        invert_mask: bool = False,
        mask: Optional[torch.Tensor] = None,
    ):
        op = float(np.clip(overlay_opacity, 0.0, 1.0))
        zb = float(np.clip(zebra_threshold, 0.0, 1.0))
        lo = float(np.clip(low_clip, 0.0, 1.0))
        hi = float(np.clip(high_clip, 0.0, 1.0))
        zebra_on = bool(show_zebra)
        m = str(mode).lower()

        stops = np.asarray([0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00], dtype=np.float32)
        ramp_cols = np.asarray(
            [
                [0.00, 0.00, 0.00],
                [0.00, 0.00, 0.80],
                [0.00, 0.70, 1.00],
                [0.00, 1.00, 0.00],
                [1.00, 1.00, 0.00],
                [1.00, 0.45, 0.00],
                [1.00, 0.00, 0.00],
            ],
            dtype=np.float32,
        )
        zone_cols = np.asarray(
            [
                [0.00, 0.00, 0.00],
                [0.10, 0.10, 0.55],
                [0.10, 0.35, 0.90],
                [0.10, 0.70, 0.95],
                [0.05, 0.90, 0.35],
                [0.45, 0.95, 0.10],
                [0.95, 0.95, 0.10],
                [0.95, 0.70, 0.05],
                [0.95, 0.35, 0.05],
                [0.95, 0.05, 0.05],
            ],
            dtype=np.float32,
        )

        def fx_fn(src: np.ndarray, _: int):
            h, w, _ = src.shape
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
            matte = np.zeros((h, w), dtype=np.float32)

            if m == "exposure_zones":
                zones = np.clip((luma * 10.0).astype(np.int32), 0, 9)
                false = zone_cols[zones]
                matte = np.ones((h, w), dtype=np.float32)
            elif m == "clipping":
                gray = np.repeat(luma[..., None], 3, axis=-1)
                low_m = luma <= lo
                hi_m = luma >= hi
                false = gray
                false[low_m] = np.asarray([0.0, 0.25, 1.0], dtype=np.float32)
                false[hi_m] = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
                matte = np.where(low_m | hi_m, 1.0, 0.35).astype(np.float32, copy=False)
            else:
                false = np.empty_like(src, dtype=np.float32)
                for ch in range(3):
                    false[..., ch] = np.interp(luma, stops, ramp_cols[:, ch]).astype(np.float32, copy=False)
                matte = np.ones((h, w), dtype=np.float32)

            if zebra_on:
                zmask = luma >= zb
                yy = np.arange(h, dtype=np.int32)[:, None]
                xx = np.arange(w, dtype=np.int32)[None, :]
                stripes = ((xx + yy) % 12) < 6
                zebra = zmask & stripes
                false[zebra] = np.asarray([1.0, 1.0, 1.0], dtype=np.float32)
                matte = np.maximum(matte, zmask.astype(np.float32))

            out = np.clip((src * (1.0 - op)) + (false * op), 0.0, 1.0).astype(np.float32, copy=False)
            return out, np.clip(matte, 0.0, 1.0).astype(np.float32, copy=False)

        detail = "mode={}, opacity={:.2f}, zebra={}@{:.2f}, clip=[{:.2f},{:.2f}]".format(
            m,
            op,
            zebra_on,
            zb,
            lo,
            hi,
        )
        return _run_masked_rgb_node(
            label="x1FalseColor",
            detail=detail,
            image=image,
            mask_feather=mask_feather,
            invert_mask=invert_mask,
            mask=mask,
            fx_fn=fx_fn,
        )
