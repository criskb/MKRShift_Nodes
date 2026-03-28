import json
from typing import Optional

import numpy as np
import torch

from ..categories import COLOR_ANALYZE
from .xcolor import _mask_to_batch, _parse_color_settings_payload, _rgb_to_hsv_np, _smoothstep, _to_image_batch


def _parse_analyze_settings(
    settings_json: str,
    defaults: dict,
    numeric_specs: dict,
    boolean_keys: set[str],
    enum_specs: dict[str, tuple[str, ...]],
    legacy: Optional[dict] = None,
) -> dict:
    settings = _parse_color_settings_payload(
        settings_json=settings_json,
        defaults=defaults,
        numeric_specs=numeric_specs,
        boolean_keys=boolean_keys,
        legacy=legacy,
    )

    payload = {}
    try:
        parsed = json.loads(str(settings_json or "{}"))
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}

    if isinstance(legacy, dict):
        for key, value in legacy.items():
            if key not in payload:
                payload[key] = value

    for key, options in enum_specs.items():
        token = str(payload.get(key, defaults[key]))
        settings[key] = token if token in options else defaults[key]
    return settings


def _add_colored_trace(
    accum: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    colors: np.ndarray,
    weights: np.ndarray,
) -> None:
    if x.size == 0 or y.size == 0 or weights.size == 0:
        return

    h, w, _ = accum.shape

    def deposit(y_offset: int, scale: float) -> None:
        yy = np.clip(y + y_offset, 0, h - 1)
        valid = (x >= 0) & (x < w) & np.isfinite(weights) & (weights > 1e-6)
        if not np.any(valid):
            return
        vv = valid.ravel()
        xx = x[vv]
        yyy = yy[vv]
        ww = (weights[vv] * scale).astype(np.float32, copy=False)
        cols = colors[vv]
        for channel in range(3):
            np.add.at(accum[..., channel], (yyy, xx), ww * cols[:, channel])

    deposit(0, 1.0)
    deposit(-1, 0.55)
    deposit(1, 0.55)


def _build_scope_background(height: int, width: int, graticule: float) -> np.ndarray:
    bg = np.zeros((height, width, 3), dtype=np.float32)
    yy = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    xx = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
    bg[:] = np.asarray([0.050, 0.056, 0.068], dtype=np.float32)
    bg += (1.0 - yy) * 0.035
    bg += np.abs(xx - 0.5) * 0.010

    line_strength = float(np.clip(graticule, 0.0, 1.0))
    for stop in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = int(round((height - 1) * stop))
        bg[max(0, y - 1): min(height, y + 2), :, :] += line_strength * np.asarray([0.055, 0.060, 0.072], dtype=np.float32)

    for frac in [0.25, 0.5, 0.75]:
        x = int(round((width - 1) * frac))
        bg[:, max(0, x - 1): min(width, x + 2), :] += line_strength * np.asarray([0.040, 0.045, 0.055], dtype=np.float32)

    return np.clip(bg, 0.0, 1.0)


def _finalize_scope(accum: np.ndarray, background: np.ndarray, gain: float) -> tuple[np.ndarray, np.ndarray]:
    positive = accum[accum > 0.0]
    peak = float(np.percentile(positive, 96.0)) if positive.size else 0.0
    if peak <= 1e-6:
        mask = np.zeros(accum.shape[:2], dtype=np.float32)
        return np.clip(background, 0.0, 1.0).astype(np.float32, copy=False), mask

    normalized = np.clip((accum * float(max(0.05, gain))) / max(peak, 1e-6), 0.0, None).astype(np.float32, copy=False)
    trace = (1.0 - np.exp(-normalized * 2.25)).astype(np.float32, copy=False)
    mask = np.clip(np.max(trace, axis=-1), 0.0, 1.0).astype(np.float32, copy=False)
    image = np.clip(background + (trace * 0.96), 0.0, 1.0).astype(np.float32, copy=False)
    return image, mask


def _build_vectorscope_background(
    size: int,
    graticule: float,
    show_skin_line: bool,
    show_targets: bool,
) -> np.ndarray:
    bg = np.zeros((size, size, 3), dtype=np.float32)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    center = (size - 1) * 0.5
    radius = size * 0.39
    nx = (xx - center) / max(radius, 1.0)
    ny = (yy - center) / max(radius, 1.0)
    rr = np.sqrt((nx * nx) + (ny * ny))

    base = np.asarray([0.045, 0.050, 0.060], dtype=np.float32)
    bg[:] = base
    vignette = np.clip(1.0 - (rr * 0.75), 0.0, 1.0)[..., None]
    bg += vignette * 0.050

    line_strength = float(np.clip(graticule, 0.0, 1.0))
    for ring in [0.25, 0.50, 0.75, 1.0]:
        band = np.abs(rr - ring) <= (1.4 / max(radius, 1.0))
        bg[band] += line_strength * np.asarray([0.055, 0.060, 0.070], dtype=np.float32)

    axes = (np.abs(xx - center) <= 1.0) | (np.abs(yy - center) <= 1.0)
    bg[axes] += line_strength * np.asarray([0.050, 0.055, 0.070], dtype=np.float32)

    if show_targets:
        target_angles = np.deg2rad(np.asarray([0, 60, 120, 180, 240, 300], dtype=np.float32))
        for angle in target_angles:
            tx = center + (np.cos(angle) * radius * 0.82)
            ty = center - (np.sin(angle) * radius * 0.82)
            target = ((xx - tx) ** 2 + (yy - ty) ** 2) <= 10.0
            bg[target] += np.asarray([0.075, 0.080, 0.090], dtype=np.float32)

    if show_skin_line:
        skin_angle = np.deg2rad(123.0)
        line = np.abs((yy - center) - (-(np.tan(skin_angle)) * (xx - center))) <= 1.2
        line &= rr <= 1.0
        bg[line] += np.asarray([0.120, 0.090, 0.045], dtype=np.float32) * max(0.45, line_strength)

    edge = np.abs(rr - 1.0) <= (1.6 / max(radius, 1.0))
    bg[edge] += np.asarray([0.080, 0.085, 0.095], dtype=np.float32)
    return np.clip(bg, 0.0, 1.0)


def _sample_rgb_and_mask(src: np.ndarray, matte: np.ndarray, step: int) -> tuple[np.ndarray, np.ndarray]:
    rgb = src[::step, ::step].reshape(-1, 3).astype(np.float32, copy=False)
    mask = matte[::step, ::step].reshape(-1).astype(np.float32, copy=False)
    return rgb, mask


class x1WaveformScope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "scope_mode": "rgb_parade",
            "gain": 1.15,
            "trace_strength": 0.90,
            "graticule": 0.38,
            "scope_resolution": 560,
            "sample_step": 2,
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
    RETURN_NAMES = ("image", "mask", "waveform_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "gain": {"min": 0.25, "max": 4.0},
                "trace_strength": {"min": 0.05, "max": 2.0},
                "graticule": {"min": 0.0, "max": 1.0},
                "scope_resolution": {"min": 256, "max": 1024, "integer": True},
                "sample_step": {"min": 1, "max": 8, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            enum_specs={"scope_mode": ("luma", "rgb_overlay", "rgb_parade")},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        scope_w = int(settings["scope_resolution"])
        scope_h = int(round(scope_w * 0.62))
        mode = str(settings["scope_mode"])
        step = int(settings["sample_step"])
        gain = float(settings["gain"])
        trace_strength = float(settings["trace_strength"])
        graticule = float(settings["graticule"])

        out_images = []
        out_masks = []

        for idx in range(int(b)):
            src = rgb[idx]
            matte = np.clip(mask_batch[idx], 0.0, 1.0)
            src_sub = src[::step, ::step]
            matte_sub = matte[::step, ::step]
            sh, sw, _ = src_sub.shape
            x_map = np.round(np.linspace(0, scope_w - 1, sw, dtype=np.float32)).astype(np.int32)
            x_grid = np.broadcast_to(x_map[None, :], (sh, sw)).reshape(-1)
            weights = (matte_sub.reshape(-1) * trace_strength).astype(np.float32, copy=False)

            background = _build_scope_background(scope_h, scope_w, graticule)
            accum = np.zeros((scope_h, scope_w, 3), dtype=np.float32)

            if mode == "luma":
                values = (0.2126 * src_sub[..., 0] + 0.7152 * src_sub[..., 1] + 0.0722 * src_sub[..., 2]).reshape(-1)
                y = np.clip(scope_h - 1 - np.round(values * (scope_h - 1)).astype(np.int32), 0, scope_h - 1)
                colors = np.repeat(np.asarray([[0.92, 0.94, 0.98]], dtype=np.float32), y.shape[0], axis=0)
                _add_colored_trace(accum, x_grid, y, colors, weights)
            elif mode == "rgb_overlay":
                for channel, color in enumerate(
                    (
                        np.asarray([1.00, 0.28, 0.24], dtype=np.float32),
                        np.asarray([0.28, 0.96, 0.42], dtype=np.float32),
                        np.asarray([0.24, 0.58, 1.00], dtype=np.float32),
                    )
                ):
                    values = src_sub[..., channel].reshape(-1)
                    y = np.clip(scope_h - 1 - np.round(values * (scope_h - 1)).astype(np.int32), 0, scope_h - 1)
                    colors = np.repeat(color[None, :], y.shape[0], axis=0)
                    _add_colored_trace(accum, x_grid, y, colors, weights)
            else:
                gap = max(14, scope_w // 30)
                segment = max(12, (scope_w - (gap * 2)) // 3)
                for channel, color in enumerate(
                    (
                        np.asarray([1.00, 0.30, 0.26], dtype=np.float32),
                        np.asarray([0.30, 0.96, 0.44], dtype=np.float32),
                        np.asarray([0.26, 0.62, 1.00], dtype=np.float32),
                    )
                ):
                    values = src_sub[..., channel].reshape(-1)
                    y = np.clip(scope_h - 1 - np.round(values * (scope_h - 1)).astype(np.int32), 0, scope_h - 1)
                    local_x = np.round(np.linspace(0, segment - 1, sw, dtype=np.float32)).astype(np.int32)
                    x_local = np.broadcast_to(local_x[None, :], (sh, sw)).reshape(-1)
                    x = x_local + (channel * (segment + gap))
                    colors = np.repeat(color[None, :], y.shape[0], axis=0)
                    _add_colored_trace(accum, x, y, colors, weights)

                for split in [segment, segment + gap + segment]:
                    background[:, max(0, split - 1): min(scope_w, split + gap + 1), :] *= 0.75

            scope_image, scope_mask = _finalize_scope(accum, background, gain)
            out_images.append(scope_image)
            out_masks.append(scope_mask)

        info = "x1WaveformScope: mode={}, resolution={}x{}, sample_step={}, gain={:.2f}, trace_strength={:.2f}, graticule={:.2f}".format(
            mode,
            scope_w,
            scope_h,
            step,
            gain,
            trace_strength,
            graticule,
        )

        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1Vectorscope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "scope_gain": 1.00,
            "trace_strength": 0.95,
            "graticule": 0.42,
            "scope_resolution": 440,
            "sample_step": 2,
            "show_skin_line": True,
            "show_targets": True,
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
    RETURN_NAMES = ("image", "mask", "vectorscope_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "scope_gain": {"min": 0.25, "max": 3.0},
                "trace_strength": {"min": 0.05, "max": 2.0},
                "graticule": {"min": 0.0, "max": 1.0},
                "scope_resolution": {"min": 256, "max": 960, "integer": True},
                "sample_step": {"min": 1, "max": 8, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"show_skin_line", "show_targets", "invert_mask"},
            enum_specs={},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        scope_size = int(settings["scope_resolution"])
        step = int(settings["sample_step"])
        scope_gain = float(settings["scope_gain"])
        trace_strength = float(settings["trace_strength"])
        graticule = float(settings["graticule"])
        show_skin_line = bool(settings["show_skin_line"])
        show_targets = bool(settings["show_targets"])

        out_images = []
        out_masks = []

        for idx in range(int(b)):
            src = rgb[idx]
            matte = np.clip(mask_batch[idx], 0.0, 1.0)
            rgb_flat, mask_flat = _sample_rgb_and_mask(src, matte, step)

            if rgb_flat.shape[0] == 0:
                background = _build_vectorscope_background(scope_size, graticule, show_skin_line, show_targets)
                out_images.append(background)
                out_masks.append(np.zeros((scope_size, scope_size), dtype=np.float32))
                continue

            luma = (0.2126 * rgb_flat[:, 0] + 0.7152 * rgb_flat[:, 1] + 0.0722 * rgb_flat[:, 2]).astype(np.float32, copy=False)
            u = ((rgb_flat[:, 2] - luma) / 1.772).astype(np.float32, copy=False)
            v = ((rgb_flat[:, 0] - luma) / 1.402).astype(np.float32, copy=False)

            center = (scope_size - 1) * 0.5
            radius = scope_size * 0.39
            x = np.round(center + (u * scope_gain * radius * 1.9)).astype(np.int32)
            y = np.round(center - (v * scope_gain * radius * 1.9)).astype(np.int32)
            colors = np.clip((rgb_flat * 0.82) + 0.10, 0.0, 1.0).astype(np.float32, copy=False)
            weights = (mask_flat * trace_strength).astype(np.float32, copy=False)

            background = _build_vectorscope_background(scope_size, graticule, show_skin_line, show_targets)
            accum = np.zeros((scope_size, scope_size, 3), dtype=np.float32)
            _add_colored_trace(accum, x, y, colors, weights)
            scope_image, scope_mask = _finalize_scope(accum, background, 1.0)
            out_images.append(scope_image)
            out_masks.append(scope_mask)

        info = "x1Vectorscope: resolution={}x{}, gain={:.2f}, trace_strength={:.2f}, targets={}, skin_line={}, sample_step={}".format(
            scope_size,
            scope_size,
            scope_gain,
            trace_strength,
            show_targets,
            show_skin_line,
            step,
        )

        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1GamutWarning:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "warning_mode": "combined",
            "low_clip": 0.02,
            "high_clip": 0.98,
            "saturation_limit": 0.90,
            "highlight_gate": 0.55,
            "overlay_opacity": 0.82,
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
    RETURN_NAMES = ("image", "mask", "gamut_warning_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "low_clip": {"min": 0.0, "max": 1.0},
                "high_clip": {"min": 0.0, "max": 1.0},
                "saturation_limit": {"min": 0.0, "max": 1.0},
                "highlight_gate": {"min": 0.0, "max": 1.0},
                "overlay_opacity": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            enum_specs={"warning_mode": ("broadcast_safe", "chroma_stress", "combined")},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
        ).unsqueeze(-1)

        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        warning_mode = str(settings["warning_mode"])
        low_clip = float(settings["low_clip"])
        high_clip = float(settings["high_clip"])
        saturation_limit = float(settings["saturation_limit"])
        highlight_gate = float(settings["highlight_gate"])
        overlay_opacity = float(settings["overlay_opacity"])

        for idx in range(int(b)):
            src = src_np[idx]
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
            _, sat, _ = _rgb_to_hsv_np(src)
            hi = (np.max(src, axis=-1) >= high_clip).astype(np.float32, copy=False)
            lo = (np.min(src, axis=-1) <= low_clip).astype(np.float32, copy=False)
            chroma = ((sat >= saturation_limit) & (luma >= highlight_gate)).astype(np.float32, copy=False)

            warn_rgb = np.zeros_like(src, dtype=np.float32)
            warn_mask = np.zeros((int(h), int(w)), dtype=np.float32)

            if warning_mode in {"broadcast_safe", "combined"}:
                warn_rgb += hi[..., None] * np.asarray([1.00, 0.18, 0.14], dtype=np.float32)[None, None, :]
                warn_rgb += lo[..., None] * np.asarray([0.18, 0.56, 1.00], dtype=np.float32)[None, None, :]
                warn_mask = np.maximum(warn_mask, np.clip(hi + lo, 0.0, 1.0))

            if warning_mode in {"chroma_stress", "combined"}:
                warn_rgb += chroma[..., None] * np.asarray([1.00, 0.84, 0.18], dtype=np.float32)[None, None, :]
                warn_mask = np.maximum(warn_mask, chroma)

            stripes = (((np.indices((int(h), int(w))).sum(axis=0) // 6) % 2).astype(np.float32) * 0.14) + 0.86
            warn_rgb *= stripes[..., None]
            overlay = np.clip((src * (1.0 - (warn_mask[..., None] * overlay_opacity * 0.42))) + (warn_rgb * overlay_opacity), 0.0, 1.0)
            out_np[idx] = overlay.astype(np.float32, copy=False)
            matte_np[idx] = warn_mask

        fx_t = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        matte_t = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype).unsqueeze(-1)
        final_mask = (matte_t * mask_batch).clamp(0.0, 1.0)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        coverage = float(final_mask.mean().item()) * 100.0
        info = "x1GamutWarning: mode={}, low_clip={:.2f}, high_clip={:.2f}, saturation_limit={:.2f}, highlight_gate={:.2f}, overlay={:.2f}, mask_coverage={:.2f}%{}".format(
            warning_mode,
            low_clip,
            high_clip,
            saturation_limit,
            highlight_gate,
            overlay_opacity,
            coverage,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


class x1HistogramScope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "histogram_mode": "rgb_overlay",
            "bins": 128,
            "contrast": 1.25,
            "fill_opacity": 0.30,
            "normalize_mode": "peak",
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
    RETURN_NAMES = ("image", "mask", "histogram_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "bins": {"min": 32, "max": 512, "integer": True},
                "contrast": {"min": 0.25, "max": 3.0},
                "fill_opacity": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            enum_specs={
                "histogram_mode": ("luma", "rgb_overlay", "rgb_stack"),
                "normalize_mode": ("peak", "area"),
            },
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        bins = int(settings["bins"])
        contrast = float(settings["contrast"])
        fill_opacity = float(settings["fill_opacity"])
        histogram_mode = str(settings["histogram_mode"])
        normalize_mode = str(settings["normalize_mode"])
        scope_w = 640
        scope_h = 360

        out_images = []
        out_masks = []

        for idx in range(int(b)):
            src = rgb[idx]
            matte = np.clip(mask_batch[idx], 0.0, 1.0)
            weights = matte.reshape(-1).astype(np.float32, copy=False)
            flat = src.reshape(-1, 3)
            luma = (0.2126 * flat[:, 0] + 0.7152 * flat[:, 1] + 0.0722 * flat[:, 2]).astype(np.float32, copy=False)

            histograms = []
            if histogram_mode == "luma":
                histograms.append(np.histogram(luma, bins=bins, range=(0.0, 1.0), weights=weights)[0].astype(np.float32))
            else:
                for channel in range(3):
                    histograms.append(
                        np.histogram(flat[:, channel], bins=bins, range=(0.0, 1.0), weights=weights)[0].astype(np.float32)
                    )

            if normalize_mode == "area":
                histograms = [hist / max(float(np.sum(hist)), 1e-6) for hist in histograms]

            peak = max(float(np.max(hist)) for hist in histograms) if histograms else 1.0
            peak = max(peak, 1e-6)
            histograms = [np.power(np.clip(hist / peak, 0.0, 1.0), 1.0 / max(contrast, 1e-6)).astype(np.float32) for hist in histograms]

            canvas = np.zeros((scope_h, scope_w, 3), dtype=np.float32)
            yy = np.linspace(0.0, 1.0, scope_h, dtype=np.float32)[:, None, None]
            canvas[:] = np.asarray([0.045, 0.050, 0.060], dtype=np.float32)
            canvas += (1.0 - yy) * 0.05

            for stop in [0.25, 0.5, 0.75]:
                y = int(round((scope_h - 1) * (1.0 - stop)))
                canvas[max(0, y - 1): min(scope_h, y + 2), :, :] += np.asarray([0.04, 0.045, 0.05], dtype=np.float32)

            bin_edges = np.round(np.linspace(0, scope_w, bins + 1)).astype(np.int32)
            channels = (
                (histograms[0], np.asarray([0.95, 0.95, 0.97], dtype=np.float32)),
            ) if histogram_mode == "luma" else (
                (histograms[0], np.asarray([1.00, 0.30, 0.24], dtype=np.float32)),
                (histograms[1], np.asarray([0.30, 0.96, 0.42], dtype=np.float32)),
                (histograms[2], np.asarray([0.24, 0.58, 1.00], dtype=np.float32)),
            )

            if histogram_mode == "rgb_stack":
                stack_height = scope_h / 3.0
                for channel_idx, (hist, color) in enumerate(channels):
                    top = int(round(channel_idx * stack_height))
                    bottom = int(round((channel_idx + 1) * stack_height))
                    band_h = max(1, bottom - top)
                    for bin_index, value in enumerate(hist):
                        x0 = int(bin_edges[bin_index])
                        x1 = max(x0 + 1, int(bin_edges[bin_index + 1]))
                        bar_h = int(round(value * (band_h - 6)))
                        y0 = max(top, bottom - bar_h)
                        canvas[y0:bottom, x0:x1, :] += color[None, None, :] * fill_opacity
                        line_y = max(top, min(bottom - 1, y0))
                        canvas[max(top, line_y - 1): min(bottom, line_y + 2), x0:x1, :] += color[None, None, :] * 0.92
                    canvas[max(top, top + 1): min(scope_h, top + 2), :, :] += np.asarray([0.05, 0.055, 0.065], dtype=np.float32)
            else:
                for hist, color in channels:
                    for bin_index, value in enumerate(hist):
                        x0 = int(bin_edges[bin_index])
                        x1 = max(x0 + 1, int(bin_edges[bin_index + 1]))
                        bar_h = int(round(value * (scope_h - 10)))
                        y0 = max(0, scope_h - bar_h)
                        canvas[y0:scope_h, x0:x1, :] += color[None, None, :] * fill_opacity
                        line_y = max(0, min(scope_h - 1, y0))
                        canvas[max(0, line_y - 1): min(scope_h, line_y + 2), x0:x1, :] += color[None, None, :] * 0.88

            image_out = np.clip(canvas, 0.0, 1.0).astype(np.float32, copy=False)
            mask_out = np.clip(np.max(image_out - 0.10, axis=-1), 0.0, 1.0).astype(np.float32, copy=False)
            out_images.append(image_out)
            out_masks.append(mask_out)

        info = "x1HistogramScope: mode={}, bins={}, contrast={:.2f}, fill={:.2f}, normalize={}, mask_coverage={:.2f}%{}".format(
            histogram_mode,
            bins,
            contrast,
            fill_opacity,
            normalize_mode,
            float(mask_batch.mean()) * 100.0,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1SkinToneCheck:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "target_hue": 28.0,
            "hue_width": 52.0,
            "sat_min": 0.10,
            "sat_max": 0.82,
            "val_min": 0.15,
            "line_tolerance": 0.18,
            "overlay_opacity": 0.82,
            "show_isolation": False,
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
    RETURN_NAMES = ("image", "mask", "skin_tone_check_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "target_hue": {"min": 0.0, "max": 360.0},
                "hue_width": {"min": 5.0, "max": 160.0},
                "sat_min": {"min": 0.0, "max": 1.0},
                "sat_max": {"min": 0.0, "max": 1.0},
                "val_min": {"min": 0.0, "max": 1.0},
                "line_tolerance": {"min": 0.01, "max": 0.6},
                "overlay_opacity": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"show_isolation", "invert_mask"},
            enum_specs={},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
        ).unsqueeze(-1)

        target_h = (float(settings["target_hue"]) % 360.0) / 360.0
        width_h = max(5.0, float(settings["hue_width"])) * 0.5 / 360.0
        sat_min = float(min(settings["sat_min"], settings["sat_max"]))
        sat_max = float(max(settings["sat_min"], settings["sat_max"]))
        val_min = float(settings["val_min"])
        tolerance = float(settings["line_tolerance"])
        overlay_opacity = float(settings["overlay_opacity"])
        show_isolation = bool(settings["show_isolation"])

        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        confidence_values = []

        for idx in range(int(b)):
            src = src_np[idx]
            hue, sat, val = _rgb_to_hsv_np(src)
            dist = np.abs(((hue - target_h + 0.5) % 1.0) - 0.5)
            hue_conf = 1.0 - _smoothstep(width_h, width_h + tolerance, dist)
            sv_gate = _smoothstep(sat_min - 0.06, sat_min + 0.06, sat) * (1.0 - _smoothstep(sat_max - 0.06, sat_max + 0.06, sat))
            val_gate = _smoothstep(val_min - 0.10, val_min + 0.10, val)
            matte = np.clip(hue_conf * sv_gate * val_gate, 0.0, 1.0).astype(np.float32, copy=False)

            good = np.asarray([0.28, 0.98, 0.56], dtype=np.float32)
            warn = np.asarray([1.00, 0.74, 0.22], dtype=np.float32)
            bad = np.asarray([1.00, 0.26, 0.22], dtype=np.float32)
            mix_warn = np.clip((dist - (width_h * 0.35)) / max(width_h * 0.65, 1e-6), 0.0, 1.0)[..., None]
            heat = (good[None, None, :] * (1.0 - mix_warn)) + (warn[None, None, :] * mix_warn)
            off = np.clip((dist - width_h) / max(tolerance, 1e-6), 0.0, 1.0)[..., None]
            heat = np.clip((heat * (1.0 - off)) + (bad[None, None, :] * off), 0.0, 1.0)

            if show_isolation:
                out = np.clip((heat * matte[..., None]) + ((1.0 - matte[..., None]) * 0.04), 0.0, 1.0)
            else:
                overlay = np.clip((src * (1.0 - (matte[..., None] * overlay_opacity * 0.42))) + (heat * matte[..., None] * overlay_opacity), 0.0, 1.0)
                out = overlay

            out_np[idx] = out.astype(np.float32, copy=False)
            matte_np[idx] = matte
            if np.any(matte > 1e-4):
                confidence_values.append(float((hue_conf * matte).sum() / max(float(matte.sum()), 1e-6)))
            else:
                confidence_values.append(0.0)

        fx_t = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        matte_t = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype).unsqueeze(-1)
        final_mask = (matte_t * mask_batch).clamp(0.0, 1.0)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        info = "x1SkinToneCheck: target_hue={:.1f}, hue_width={:.1f}, sat=[{:.2f},{:.2f}], val_min={:.2f}, tolerance={:.2f}, overlay={:.2f}, confidence={:.2f}, mask_coverage={:.2f}%{}".format(
            float(settings["target_hue"]),
            float(settings["hue_width"]),
            sat_min,
            sat_max,
            val_min,
            tolerance,
            overlay_opacity,
            float(np.mean(confidence_values)) if confidence_values else 0.0,
            float(final_mask.mean().item()) * 100.0,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


def _weighted_rgb_mean(rgb: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, float]:
    total = float(np.sum(weights))
    if total <= 1e-6:
        return np.asarray([0.5, 0.5, 0.5], dtype=np.float32), 0.0
    mean = np.sum(rgb * weights[:, None], axis=0) / total
    return np.clip(mean.astype(np.float32, copy=False), 0.0, 1.0), total


def _build_balance_scope_background(
    height: int,
    width: int,
    neutral_tolerance: float,
    show_reference: bool,
    segment_count: int,
) -> np.ndarray:
    bg = np.zeros((height, width, 3), dtype=np.float32)
    yy = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    xx = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
    bg[:] = np.asarray([0.050, 0.054, 0.064], dtype=np.float32)
    bg += (1.0 - yy) * 0.045
    bg += np.abs(xx - 0.5) * 0.012

    center_y = int(round((height - 1) * 0.5))
    bg[max(0, center_y - 1): min(height, center_y + 2), :, :] += np.asarray([0.080, 0.084, 0.094], dtype=np.float32)

    if show_reference:
        tol_px = max(4, int(round(height * np.clip(neutral_tolerance, 0.02, 0.25) * 0.90)))
        for direction in (-1, 1):
            y = int(np.clip(center_y + (direction * tol_px), 0, height - 1))
            bg[max(0, y - 1): min(height, y + 2), :, :] += np.asarray([0.050, 0.055, 0.065], dtype=np.float32)

    for stop in [0.15, 0.30, 0.70, 0.85]:
        y = int(round((height - 1) * stop))
        bg[max(0, y - 1): min(height, y + 1), :, :] += np.asarray([0.028, 0.032, 0.038], dtype=np.float32)

    for idx in range(1, segment_count):
        x = int(round((width / segment_count) * idx))
        bg[:, max(0, x - 1): min(width, x + 1), :] += np.asarray([0.035, 0.040, 0.048], dtype=np.float32)

    return np.clip(bg, 0.0, 1.0)


def _render_balance_scope(
    section_ratios: list[np.ndarray],
    response_gain: float,
    neutral_tolerance: float,
    show_reference: bool,
) -> tuple[np.ndarray, np.ndarray]:
    height = 360
    width = 720
    segment_count = max(1, len(section_ratios))
    background = _build_balance_scope_background(height, width, neutral_tolerance, show_reference, segment_count)
    canvas = background.copy()
    center_y = int(round((height - 1) * 0.5))
    gap = 6 if segment_count >= 8 else 10
    usable_w = width - (gap * (segment_count + 1))
    segment_w = max(20, int(round(usable_w / segment_count)))
    colors = (
        np.asarray([1.00, 0.34, 0.26], dtype=np.float32),
        np.asarray([0.30, 0.96, 0.42], dtype=np.float32),
        np.asarray([0.26, 0.62, 1.00], dtype=np.float32),
    )

    for idx, ratios in enumerate(section_ratios):
        x0 = gap + (idx * (segment_w + gap))
        x1 = min(width, x0 + segment_w)
        if x1 <= x0:
            continue

        shade = 0.020 if idx % 2 == 0 else 0.0
        canvas[:, x0:x1, :] += shade

        lane_gap = max(4, int(round((x1 - x0) * 0.04)))
        lane_w = max(4, int(round(((x1 - x0) - (lane_gap * 4)) / 3)))

        for channel, color in enumerate(colors):
            lane_x0 = x0 + lane_gap + (channel * (lane_w + lane_gap))
            lane_x1 = min(x1, lane_x0 + lane_w)
            if lane_x1 <= lane_x0:
                continue

            offset = float(np.clip((float(ratios[channel]) - 1.0) * response_gain, -0.48, 0.48))
            bar_h = max(2, int(round(abs(offset) * height * 0.74)))
            if offset >= 0.0:
                y0 = max(0, center_y - bar_h)
                y1 = center_y
            else:
                y0 = center_y
                y1 = min(height, center_y + bar_h)

            canvas[y0:y1, lane_x0:lane_x1, :] += color[None, None, :] * 0.42
            edge_y = y0 if offset >= 0.0 else max(0, y1 - 2)
            canvas[max(0, edge_y - 1): min(height, edge_y + 2), lane_x0:lane_x1, :] += color[None, None, :] * 0.88
            canvas[:, lane_x0: min(width, lane_x0 + 1), :] += color[None, None, :] * 0.08

    image_out = np.clip(canvas, 0.0, 1.0).astype(np.float32, copy=False)
    mask_out = np.clip(np.max(image_out - background, axis=-1) * 1.45, 0.0, 1.0).astype(np.float32, copy=False)
    return image_out, mask_out


class x1RGBBalanceScope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "analysis_mode": "zones",
            "shadow_point": 0.22,
            "highlight_point": 0.78,
            "zone_softness": 0.12,
            "response_gain": 1.15,
            "neutral_tolerance": 0.08,
            "show_reference": True,
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
    RETURN_NAMES = ("image", "mask", "rgb_balance_scope_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "shadow_point": {"min": 0.0, "max": 1.0},
                "highlight_point": {"min": 0.0, "max": 1.0},
                "zone_softness": {"min": 0.02, "max": 0.35},
                "response_gain": {"min": 0.25, "max": 3.0},
                "neutral_tolerance": {"min": 0.02, "max": 0.25},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"show_reference", "invert_mask"},
            enum_specs={"analysis_mode": ("zones", "columns")},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        analysis_mode = str(settings["analysis_mode"])
        shadow_point = float(settings["shadow_point"])
        highlight_point = max(shadow_point + 0.06, float(settings["highlight_point"]))
        zone_softness = float(settings["zone_softness"])
        response_gain = float(settings["response_gain"])
        neutral_tolerance = float(settings["neutral_tolerance"])
        show_reference = bool(settings["show_reference"])

        out_images = []
        out_masks = []
        info_sections = []

        for idx in range(int(b)):
            src = rgb[idx]
            matte = np.clip(mask_batch[idx], 0.0, 1.0)
            flat_rgb = src.reshape(-1, 3)
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)

            section_means = []
            section_ratios = []

            if analysis_mode == "columns":
                columns = 12
                for column in range(columns):
                    x0 = int(round((column / columns) * w))
                    x1 = max(x0 + 1, int(round(((column + 1) / columns) * w)))
                    weights = matte[:, x0:x1].reshape(-1).astype(np.float32, copy=False)
                    mean, _ = _weighted_rgb_mean(flat_rgb.reshape(h, w, 3)[:, x0:x1, :].reshape(-1, 3), weights)
                    base = max(float(np.mean(mean)), 1e-4)
                    section_means.append(mean)
                    section_ratios.append((mean / base).astype(np.float32, copy=False))
                dominant = np.mean(np.stack(section_ratios, axis=0), axis=0)
                info_sections.append(
                    "global=[{:+.2f},{:+.2f},{:+.2f}]".format(
                        float(dominant[0] - 1.0),
                        float(dominant[1] - 1.0),
                        float(dominant[2] - 1.0),
                    )
                )
            else:
                shadow_gate = 1.0 - _smoothstep(shadow_point - zone_softness, shadow_point + zone_softness, luma)
                highlight_gate = _smoothstep(highlight_point - zone_softness, highlight_point + zone_softness, luma)
                mid_gate = np.clip((1.0 - shadow_gate) * (1.0 - highlight_gate), 0.0, 1.0)
                section_weights = (
                    ("shadows", (matte * shadow_gate).reshape(-1).astype(np.float32, copy=False)),
                    ("mids", (matte * mid_gate).reshape(-1).astype(np.float32, copy=False)),
                    ("highs", (matte * highlight_gate).reshape(-1).astype(np.float32, copy=False)),
                )
                for label, weights in section_weights:
                    mean, _ = _weighted_rgb_mean(flat_rgb, weights)
                    base = max(float(np.mean(mean)), 1e-4)
                    ratios = (mean / base).astype(np.float32, copy=False)
                    section_means.append(mean)
                    section_ratios.append(ratios)
                    info_sections.append(
                        "{}=[{:+.2f},{:+.2f},{:+.2f}]".format(
                            label,
                            float(ratios[0] - 1.0),
                            float(ratios[1] - 1.0),
                            float(ratios[2] - 1.0),
                        )
                    )

            image_out, mask_out = _render_balance_scope(section_ratios, response_gain, neutral_tolerance, show_reference)
            out_images.append(image_out)
            out_masks.append(mask_out)

        info = "x1RGBBalanceScope: mode={}, shadow_point={:.2f}, highlight_point={:.2f}, response_gain={:.2f}, neutral_tolerance={:.2f}, show_reference={}{}".format(
            analysis_mode,
            shadow_point,
            highlight_point,
            response_gain,
            neutral_tolerance,
            show_reference,
            ", " + "; ".join(info_sections[:3]) if info_sections else "",
        )
        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1NeutralityMap:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "sat_ceiling": 0.18,
            "luma_floor": 0.10,
            "luma_ceiling": 0.92,
            "cast_gain": 1.35,
            "warmth_bias": 0.0,
            "overlay_opacity": 0.82,
            "show_isolation": False,
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
    RETURN_NAMES = ("image", "mask", "neutrality_map_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "sat_ceiling": {"min": 0.02, "max": 0.60},
                "luma_floor": {"min": 0.0, "max": 1.0},
                "luma_ceiling": {"min": 0.0, "max": 1.0},
                "cast_gain": {"min": 0.2, "max": 3.0},
                "warmth_bias": {"min": -0.35, "max": 0.35},
                "overlay_opacity": {"min": 0.0, "max": 1.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"show_isolation", "invert_mask"},
            enum_specs={},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        rgb = batch[..., :3]
        alpha = batch[..., 3:4] if c == 4 else None
        src_np = rgb.detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=batch.device,
        ).unsqueeze(-1)

        sat_ceiling = float(settings["sat_ceiling"])
        luma_floor = float(settings["luma_floor"])
        luma_ceiling = max(luma_floor + 0.08, float(settings["luma_ceiling"]))
        cast_gain = float(settings["cast_gain"])
        warmth_bias = float(settings["warmth_bias"])
        overlay_opacity = float(settings["overlay_opacity"])
        show_isolation = bool(settings["show_isolation"])

        warm = np.asarray([1.00, 0.72, 0.28], dtype=np.float32)
        cool = np.asarray([0.34, 0.70, 1.00], dtype=np.float32)
        magenta = np.asarray([1.00, 0.42, 0.82], dtype=np.float32)
        green = np.asarray([0.42, 1.00, 0.56], dtype=np.float32)
        neutral = np.asarray([0.78, 0.81, 0.86], dtype=np.float32)

        out_np = np.empty_like(src_np)
        matte_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        temp_values = []
        tint_values = []
        cast_values = []

        for idx in range(int(b)):
            src = src_np[idx]
            _, sat, val = _rgb_to_hsv_np(src)
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)
            sat_gate = 1.0 - _smoothstep(sat_ceiling * 0.55, sat_ceiling, sat)
            low_gate = _smoothstep(luma_floor - 0.08, luma_floor + 0.08, luma)
            high_gate = 1.0 - _smoothstep(luma_ceiling - 0.08, luma_ceiling + 0.08, luma)
            matte = np.clip(sat_gate * low_gate * high_gate, 0.0, 1.0).astype(np.float32, copy=False)

            temp = ((src[..., 0] - src[..., 2]) - warmth_bias).astype(np.float32, copy=False)
            tint = (((src[..., 0] + src[..., 2]) * 0.5) - src[..., 1]).astype(np.float32, copy=False)
            cast_mag = np.sqrt(np.maximum((temp * temp) + (tint * tint), 0.0)).astype(np.float32, copy=False)
            cast_mix = np.clip(cast_mag * cast_gain * 2.4, 0.0, 1.0)[..., None]

            heat = np.repeat(neutral[None, None, :], int(h), axis=0)
            heat = np.repeat(heat, int(w), axis=1).astype(np.float32, copy=False)

            temp_dom = np.abs(temp) >= np.abs(tint)
            heat[temp_dom & (temp >= 0.0)] = warm
            heat[temp_dom & (temp < 0.0)] = cool
            heat[(~temp_dom) & (tint >= 0.0)] = magenta
            heat[(~temp_dom) & (tint < 0.0)] = green
            heat = np.clip((neutral[None, None, :] * (1.0 - cast_mix)) + (heat * cast_mix), 0.0, 1.0)

            if show_isolation:
                out = np.clip((heat * matte[..., None]) + ((1.0 - matte[..., None]) * 0.05), 0.0, 1.0)
            else:
                out = np.clip(
                    (src * (1.0 - (matte[..., None] * overlay_opacity * 0.42))) + (heat * matte[..., None] * overlay_opacity),
                    0.0,
                    1.0,
                )

            out_np[idx] = out.astype(np.float32, copy=False)
            matte_np[idx] = matte
            total = float(np.sum(matte))
            if total > 1e-6:
                temp_values.append(float(np.sum(temp * matte) / total))
                tint_values.append(float(np.sum(tint * matte) / total))
                cast_values.append(float(np.sum(cast_mag * matte) / total))
            else:
                temp_values.append(0.0)
                tint_values.append(0.0)
                cast_values.append(0.0)

        fx_t = torch.from_numpy(out_np).to(device=batch.device, dtype=batch.dtype)
        matte_t = torch.from_numpy(np.clip(matte_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype).unsqueeze(-1)
        final_mask = (matte_t * mask_batch).clamp(0.0, 1.0)
        out_rgb = torch.clamp((rgb * (1.0 - final_mask)) + (fx_t * final_mask), 0.0, 1.0)
        out = torch.cat([out_rgb, alpha], dim=-1) if alpha is not None else out_rgb

        info = "x1NeutralityMap: sat_ceiling={:.2f}, luma=[{:.2f},{:.2f}], cast_gain={:.2f}, warmth_bias={:.2f}, overlay={:.2f}, avg_temp={:+.3f}, avg_tint={:+.3f}, avg_cast={:.3f}, mask_coverage={:.2f}%{}".format(
            sat_ceiling,
            luma_floor,
            luma_ceiling,
            cast_gain,
            warmth_bias,
            overlay_opacity,
            float(np.mean(temp_values)) if temp_values else 0.0,
            float(np.mean(tint_values)) if tint_values else 0.0,
            float(np.mean(cast_values)) if cast_values else 0.0,
            float(final_mask.mean().item()) * 100.0,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out.clamp(0.0, 1.0), final_mask.squeeze(-1).clamp(0.0, 1.0), info)


def _hue_to_rgb_np(hue: np.ndarray) -> np.ndarray:
    return np.clip(
        np.stack(
            [
                np.abs((hue * 6.0) - 3.0) - 1.0,
                2.0 - np.abs((hue * 6.0) - 2.0),
                2.0 - np.abs((hue * 6.0) - 4.0),
            ],
            axis=-1,
        ),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)


def _build_hue_band_background(height: int, width: int, graticule: float) -> np.ndarray:
    hue = np.linspace(0.0, 1.0, width, dtype=np.float32)
    spectrum = _hue_to_rgb_np(hue)[None, :, :]
    bg = np.repeat(spectrum, height, axis=0)
    shade = np.linspace(0.28, 0.08, height, dtype=np.float32)[:, None, None]
    bg = (bg * shade) + np.asarray([0.040, 0.044, 0.052], dtype=np.float32)

    line = float(np.clip(graticule, 0.0, 1.0))
    for stop in [0.25, 0.5, 0.75]:
        y = int(round((height - 1) * (1.0 - stop)))
        bg[max(0, y - 1): min(height, y + 2), :, :] += line * np.asarray([0.045, 0.048, 0.054], dtype=np.float32)

    for frac in np.linspace(0.0, 1.0, 7, dtype=np.float32):
        x = int(round((width - 1) * float(frac)))
        bg[:, max(0, x - 1): min(width, x + 1), :] += line * np.asarray([0.035, 0.038, 0.045], dtype=np.float32)

    return np.clip(bg, 0.0, 1.0)


def _build_sat_luma_background(size: int, graticule: float) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    sat = xx / max(size - 1, 1)
    luma = 1.0 - (yy / max(size - 1, 1))
    cool = np.asarray([0.12, 0.18, 0.28], dtype=np.float32)
    warm = np.asarray([0.28, 0.24, 0.16], dtype=np.float32)
    bg = (cool[None, None, :] * (1.0 - sat[..., None])) + (warm[None, None, :] * sat[..., None])
    bg = (bg * (0.34 + (luma[..., None] * 0.24))) + np.asarray([0.032, 0.035, 0.042], dtype=np.float32)

    line = float(np.clip(graticule, 0.0, 1.0))
    for stop in [0.25, 0.5, 0.75]:
        x = int(round((size - 1) * stop))
        y = int(round((size - 1) * stop))
        bg[:, max(0, x - 1): min(size, x + 2), :] += line * np.asarray([0.040, 0.044, 0.050], dtype=np.float32)
        bg[max(0, y - 1): min(size, y + 2), :, :] += line * np.asarray([0.040, 0.044, 0.050], dtype=np.float32)

    edge = (
        (np.abs(xx) <= 1.0)
        | (np.abs(xx - (size - 1)) <= 1.0)
        | (np.abs(yy) <= 1.0)
        | (np.abs(yy - (size - 1)) <= 1.0)
    )
    bg[edge] += np.asarray([0.055, 0.058, 0.065], dtype=np.float32)
    return np.clip(bg, 0.0, 1.0)


class x1HueBandScope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "bins": 192,
            "density_gain": 1.10,
            "sat_floor": 0.08,
            "val_floor": 0.10,
            "graticule": 0.34,
            "sample_step": 2,
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
    RETURN_NAMES = ("image", "mask", "hue_band_scope_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "bins": {"min": 48, "max": 512, "integer": True},
                "density_gain": {"min": 0.2, "max": 3.0},
                "sat_floor": {"min": 0.0, "max": 1.0},
                "val_floor": {"min": 0.0, "max": 1.0},
                "graticule": {"min": 0.0, "max": 1.0},
                "sample_step": {"min": 1, "max": 8, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            enum_specs={},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        bins = int(settings["bins"])
        density_gain = float(settings["density_gain"])
        sat_floor = float(settings["sat_floor"])
        val_floor = float(settings["val_floor"])
        graticule = float(settings["graticule"])
        sample_step = int(settings["sample_step"])
        scope_w = 720
        scope_h = 240

        out_images = []
        out_masks = []
        peak_hues = []

        for idx in range(int(b)):
            src = rgb[idx][::sample_step, ::sample_step]
            matte = np.clip(mask_batch[idx][::sample_step, ::sample_step], 0.0, 1.0)
            hue, sat, val = _rgb_to_hsv_np(src)
            weights = (
                matte
                * _smoothstep(sat_floor - 0.06, sat_floor + 0.06, sat)
                * _smoothstep(val_floor - 0.08, val_floor + 0.08, val)
            ).reshape(-1).astype(np.float32, copy=False)

            hist = np.histogram(hue.reshape(-1), bins=bins, range=(0.0, 1.0), weights=weights)[0].astype(np.float32)
            peak_idx = int(np.argmax(hist)) if hist.size else 0
            peak_hues.append((peak_idx + 0.5) / max(bins, 1))

            peak = max(float(np.max(hist)), 1e-6)
            curve = np.power(np.clip((hist / peak) * density_gain, 0.0, 1.0), 0.84).astype(np.float32, copy=False)

            canvas = _build_hue_band_background(scope_h, scope_w, graticule)
            edges = np.round(np.linspace(0, scope_w, bins + 1)).astype(np.int32)
            for bin_index, value in enumerate(curve):
                x0 = int(edges[bin_index])
                x1 = max(x0 + 1, int(edges[bin_index + 1]))
                bar_h = int(round(value * (scope_h - 16)))
                y0 = max(0, scope_h - bar_h)
                hue_mid = ((bin_index + 0.5) / max(bins, 1))
                color = _hue_to_rgb_np(np.asarray([hue_mid], dtype=np.float32))[0]
                canvas[y0:scope_h, x0:x1, :] += color[None, None, :] * 0.36
                canvas[max(0, y0 - 1): min(scope_h, y0 + 2), x0:x1, :] += color[None, None, :] * 0.78

            image_out = np.clip(canvas, 0.0, 1.0).astype(np.float32, copy=False)
            mask_out = np.clip(np.max(image_out - 0.08, axis=-1), 0.0, 1.0).astype(np.float32, copy=False)
            out_images.append(image_out)
            out_masks.append(mask_out)

        info = "x1HueBandScope: bins={}, density_gain={:.2f}, sat_floor={:.2f}, val_floor={:.2f}, sample_step={}, peak_hue={:.1f}deg{}".format(
            bins,
            density_gain,
            sat_floor,
            val_floor,
            sample_step,
            float(np.mean(peak_hues) * 360.0) if peak_hues else 0.0,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1SatLumaScope:
    @staticmethod
    def _default_settings() -> dict:
        return {
            "density_gain": 1.00,
            "sat_floor": 0.04,
            "graticule": 0.40,
            "sample_step": 2,
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
    RETURN_NAMES = ("image", "mask", "sat_luma_scope_info")
    FUNCTION = "run"
    CATEGORY = COLOR_ANALYZE

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = _parse_analyze_settings(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "density_gain": {"min": 0.2, "max": 3.0},
                "sat_floor": {"min": 0.0, "max": 0.5},
                "graticule": {"min": 0.0, "max": 1.0},
                "sample_step": {"min": 1, "max": 8, "integer": True},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_mask"},
            enum_specs={},
            legacy=legacy_settings,
        )

        batch = _to_image_batch(image)
        b, h, w, _ = batch.shape
        rgb = batch[..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _mask_to_batch(
            mask=mask,
            batch=int(b),
            h=int(h),
            w=int(w),
            feather_radius=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
            device=torch.device("cpu"),
        ).numpy().astype(np.float32, copy=False)

        density_gain = float(settings["density_gain"])
        sat_floor = float(settings["sat_floor"])
        graticule = float(settings["graticule"])
        sample_step = int(settings["sample_step"])
        size = 420

        out_images = []
        out_masks = []
        density_values = []

        for idx in range(int(b)):
            src = rgb[idx][::sample_step, ::sample_step]
            matte = np.clip(mask_batch[idx][::sample_step, ::sample_step], 0.0, 1.0)
            _, sat, _ = _rgb_to_hsv_np(src)
            luma = (0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]).astype(np.float32, copy=False)

            x = np.clip(np.round(sat.reshape(-1) * (size - 1)).astype(np.int32), 0, size - 1)
            y = np.clip(np.round((1.0 - luma.reshape(-1)) * (size - 1)).astype(np.int32), 0, size - 1)
            colors = np.clip((src.reshape(-1, 3) * 0.78) + 0.12, 0.0, 1.0).astype(np.float32, copy=False)
            weights = (
                matte.reshape(-1)
                * _smoothstep(sat_floor - 0.04, sat_floor + 0.04, sat.reshape(-1))
                * density_gain
            ).astype(np.float32, copy=False)

            background = _build_sat_luma_background(size, graticule)
            accum = np.zeros((size, size, 3), dtype=np.float32)
            _add_colored_trace(accum, x, y, colors, weights)
            scope_image, scope_mask = _finalize_scope(accum, background, 1.0)
            out_images.append(scope_image)
            out_masks.append(scope_mask)
            density_values.append(float(np.mean(weights > 1e-5)))

        info = "x1SatLumaScope: density_gain={:.2f}, sat_floor={:.2f}, sample_step={}, active_density={:.2f}%{}".format(
            density_gain,
            sat_floor,
            sample_step,
            (float(np.mean(density_values)) * 100.0) if density_values else 0.0,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (
            torch.from_numpy(np.stack(out_images, axis=0)).to(device=batch.device, dtype=batch.dtype),
            torch.from_numpy(np.stack(out_masks, axis=0)).to(device=batch.device, dtype=batch.dtype),
            info,
        )
