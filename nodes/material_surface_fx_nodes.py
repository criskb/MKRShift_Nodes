import json
from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_EFFECTS
from ..lib.image_shared import luma_np, rgb_to_hsv_np, smoothstep_np, to_image_batch
from ..lib.scalar_map_shared import blur_single_channel, mask_tensor_to_np, scalar_from_source
from ..lib.settings_bundle import parse_settings_payload
from ..lib.technical_art_shared import emit_masked_grayscale


def _local_detail(values: np.ndarray, radius: float) -> np.ndarray:
    base = np.clip(values, 0.0, 1.0).astype(np.float32, copy=False)
    blurred = blur_single_channel(base, max(0.0, radius))
    detail = np.abs(base - blurred).astype(np.float32, copy=False)
    peak = float(np.max(detail))
    if peak <= 1e-6:
      return np.zeros_like(detail, dtype=np.float32)
    return np.clip(detail / peak, 0.0, 1.0).astype(np.float32, copy=False)


def _apply_contrast(values: np.ndarray, contrast: float) -> np.ndarray:
    return np.clip(((values - 0.5) * contrast) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)


def _normalize_field(values: np.ndarray) -> np.ndarray:
    field = np.clip(values, 0.0, None).astype(np.float32, copy=False)
    peak = float(np.max(field))
    if peak <= 1e-6:
        return np.zeros_like(field, dtype=np.float32)
    return np.clip(field / peak, 0.0, 1.0).astype(np.float32, copy=False)


def _hue_band_field(hue: np.ndarray, target: float, width: float) -> np.ndarray:
    delta = np.abs(np.asarray(hue, dtype=np.float32) - float(target))
    wrapped = np.minimum(delta, 1.0 - delta).astype(np.float32, copy=False)
    band_width = max(1e-3, float(width))
    return np.clip(1.0 - (wrapped / band_width), 0.0, 1.0).astype(np.float32, copy=False)


def _resolve_dust_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    top_bias: float,
    cavity_bias: float,
    breakup: float,
    amount: float,
    coverage: float,
    contrast: float,
    gamma: float,
    blur_radius: float,
    invert_values: bool,
) -> tuple[np.ndarray, str]:
    resolved_mode = str(source_mode or "combined_dust").strip().lower()
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, w = rgb.shape[:2]
    luma = luma_np(rgb)
    _, sat, _ = rgb_to_hsv_np(rgb)

    if resolved_mode == "combined_dust":
        darks = np.clip(1.0 - luma, 0.0, 1.0).astype(np.float32, copy=False)
        cavities = np.clip((darks * 0.72) + (_local_detail(darks, 2.6) * 0.48), 0.0, 1.0).astype(np.float32, copy=False)
        neutral = np.clip(1.0 - (sat * 0.82), 0.0, 1.0).astype(np.float32, copy=False)
        top_gradient = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]
        x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        stripe = (0.5 + (0.5 * np.sin((x * 13.0) + (top_gradient * 7.5)))).astype(np.float32, copy=False)
        breakup_field = np.clip((1.0 - breakup) + (stripe * breakup), 0.0, 1.0).astype(np.float32, copy=False)
        base = (
            (top_gradient * (0.26 + (top_bias * 0.74)))
            + (cavities * (0.28 + (cavity_bias * 0.72)))
            + (neutral * 0.20)
        ) / (1.10 + (top_bias * 0.30) + (cavity_bias * 0.40))
        scalar = np.clip(base * breakup_field, 0.0, 1.0).astype(np.float32, copy=False)
    else:
        raw, resolved_mode = scalar_from_source(rgb, resolved_mode, source_mask_np, True)
        top_gradient = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]
        scalar = np.clip((raw * (1.0 - (top_bias * 0.35))) + (top_gradient * top_bias * 0.35), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    if source_mask_np is not None and resolved_mode != "mask":
        scalar = np.clip(scalar * np.clip(source_mask_np, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)

    threshold = 1.0 - float(np.clip(coverage, 0.0, 1.0))
    softness = 0.10 + (breakup * 0.18)
    scalar = smoothstep_np(max(0.0, threshold - softness), min(1.0, threshold + softness), scalar).astype(
        np.float32,
        copy=False,
    )
    scalar = _apply_contrast(scalar, max(0.1, float(contrast)))
    scalar = np.power(np.clip(scalar, 0.0, 1.0), max(0.1, float(gamma))).astype(np.float32, copy=False)
    scalar = blur_single_channel(scalar, max(0.0, float(blur_radius)))
    scalar = np.clip(scalar * float(np.clip(amount, 0.0, 1.0)), 0.0, 1.0).astype(np.float32, copy=False)
    if bool(invert_values):
        scalar = (1.0 - scalar).astype(np.float32, copy=False)
    return scalar, resolved_mode


def _resolve_streak_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    direction: str,
    streak_length: float,
    anchor_bias: float,
    breakup: float,
    coverage: float,
    contrast: float,
    gamma: float,
    blur_radius: float,
    invert_values: bool,
) -> tuple[np.ndarray, str]:
    resolved_mode = str(source_mode or "combined_streak").strip().lower()
    resolved_direction = str(direction or "down").strip().lower()
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, w = rgb.shape[:2]
    luma = luma_np(rgb)
    grad_x = np.abs(np.gradient(luma, axis=1)).astype(np.float32, copy=False)
    detail = _local_detail(luma, 2.0)

    if resolved_mode == "combined_streak":
        darkness = np.clip(1.0 - luma, 0.0, 1.0).astype(np.float32, copy=False)
        anchors = np.clip(
            (darkness * (0.30 + (anchor_bias * 0.35)))
            + (grad_x * (0.32 + (anchor_bias * 0.55)))
            + (detail * 0.38),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)
    else:
        anchors, resolved_mode = scalar_from_source(rgb, resolved_mode, source_mask_np, True)

    if source_mask_np is not None and resolved_mode != "mask":
        anchors = np.clip(anchors * np.clip(source_mask_np, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)

    decay = 0.82 + (float(np.clip(streak_length, 0.0, 1.0)) * 0.17)
    trail = anchors.astype(np.float32, copy=True)
    if resolved_direction == "up":
        for row in range(h - 2, -1, -1):
            trail[row] = np.maximum(trail[row], trail[row + 1] * decay)
        travel = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    else:
        for row in range(1, h):
            trail[row] = np.maximum(trail[row], trail[row - 1] * decay)
        travel = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]

    column_edge = np.mean(grad_x, axis=0, keepdims=True).astype(np.float32, copy=False)
    if float(np.max(column_edge)) > 1e-6:
        column_edge = column_edge / float(np.max(column_edge))
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    stripe = (0.5 + (0.5 * np.sin((x * 16.0) + (column_edge * 5.5)))).astype(np.float32, copy=False)
    breakup_field = np.clip((1.0 - breakup) + (stripe * breakup), 0.0, 1.0).astype(np.float32, copy=False)

    scalar = np.clip(
        (trail * (0.60 + (anchor_bias * 0.25)))
        * (0.55 + (travel * 0.45))
        * breakup_field,
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    threshold = 1.0 - float(np.clip(coverage, 0.0, 1.0))
    softness = 0.08 + (breakup * 0.16)
    scalar = smoothstep_np(max(0.0, threshold - softness), min(1.0, threshold + softness), scalar).astype(
        np.float32,
        copy=False,
    )
    scalar = _apply_contrast(scalar, max(0.1, float(contrast)))
    scalar = np.power(np.clip(scalar, 0.0, 1.0), max(0.1, float(gamma))).astype(np.float32, copy=False)
    scalar = blur_single_channel(scalar, max(0.0, float(blur_radius)))
    if bool(invert_values):
        scalar = (1.0 - scalar).astype(np.float32, copy=False)
    return scalar, f"{resolved_mode}:{resolved_direction}"


def _resolve_rust_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    cavity_bias: float,
    edge_bias: float,
    warm_bias: float,
    bloom_spread: float,
    breakup: float,
    amount: float,
    coverage: float,
    contrast: float,
    gamma: float,
    blur_radius: float,
    invert_values: bool,
) -> tuple[np.ndarray, str]:
    resolved_mode = str(source_mode or "combined_rust").strip().lower()
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, w = rgb.shape[:2]
    luma = luma_np(rgb)
    hue, sat, _ = rgb_to_hsv_np(rgb)

    if resolved_mode == "combined_rust":
        darks = np.clip(1.0 - luma, 0.0, 1.0).astype(np.float32, copy=False)
        cavities = np.clip((darks * 0.64) + (_local_detail(darks, 2.4) * 0.56), 0.0, 1.0).astype(np.float32, copy=False)
        grad_y = np.gradient(luma, axis=0).astype(np.float32, copy=False)
        grad_x = np.gradient(luma, axis=1).astype(np.float32, copy=False)
        edges = _normalize_field(np.sqrt((grad_x * grad_x) + (grad_y * grad_y)).astype(np.float32, copy=False))
        warm = np.clip(_hue_band_field(hue, 0.075, 0.13) * (0.30 + (sat * 0.70)), 0.0, 1.0).astype(np.float32, copy=False)
        seed = (
            (cavities * (0.28 + (cavity_bias * 0.72)))
            + (edges * (0.22 + (edge_bias * 0.78)))
            + (warm * (0.14 + (warm_bias * 0.86)))
        ) / (1.02 + (cavity_bias * 0.36) + (edge_bias * 0.34) + (warm_bias * 0.28))
        spread_radius = 0.4 + (float(np.clip(bloom_spread, 0.0, 1.0)) * 11.0)
        bloom = blur_single_channel(np.clip(seed, 0.0, 1.0).astype(np.float32, copy=False), spread_radius)
        x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        breakup_field = (
            0.52
            + (0.28 * np.sin((x * 14.0) + (y * 8.5)))
            + (0.20 * np.cos((x * 23.0) - (y * 5.5)))
        ).astype(np.float32, copy=False)
        breakup_field = np.clip((1.0 - breakup) + (_normalize_field(breakup_field) * breakup), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
        scalar = np.clip(((seed * 0.44) + (bloom * 0.56)) * breakup_field, 0.0, 1.0).astype(np.float32, copy=False)
    else:
        raw, resolved_mode = scalar_from_source(rgb, resolved_mode, source_mask_np, True)
        spread_radius = 0.25 + (float(np.clip(bloom_spread, 0.0, 1.0)) * 9.0)
        spread = blur_single_channel(np.clip(raw, 0.0, 1.0).astype(np.float32, copy=False), spread_radius)
        scalar = np.clip((raw * 0.46) + (spread * 0.54), 0.0, 1.0).astype(np.float32, copy=False)

    scalar = _normalize_field(scalar)

    if source_mask_np is not None and resolved_mode != "mask":
        scalar = np.clip(scalar * np.clip(source_mask_np, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)

    threshold = 1.0 - float(np.clip(coverage, 0.0, 1.0))
    softness = 0.08 + (breakup * 0.16)
    scalar = smoothstep_np(max(0.0, threshold - softness), min(1.0, threshold + softness), scalar).astype(
        np.float32,
        copy=False,
    )
    scalar = _apply_contrast(scalar, max(0.1, float(contrast)))
    scalar = np.power(np.clip(scalar, 0.0, 1.0), max(0.1, float(gamma))).astype(np.float32, copy=False)
    scalar = blur_single_channel(scalar, max(0.0, float(blur_radius)))
    scalar = np.clip(scalar * float(np.clip(amount, 0.0, 1.0)), 0.0, 1.0).astype(np.float32, copy=False)
    if bool(invert_values):
        scalar = (1.0 - scalar).astype(np.float32, copy=False)
    return scalar, resolved_mode


def _resolve_waterline_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    orientation: str,
    line_height: float,
    band_width: float,
    capillary_rise: float,
    cavity_bias: float,
    breakup: float,
    amount: float,
    coverage: float,
    contrast: float,
    gamma: float,
    blur_radius: float,
    invert_values: bool,
) -> tuple[np.ndarray, str]:
    resolved_mode = str(source_mode or "combined_waterline").strip().lower()
    resolved_orientation = str(orientation or "bottom").strip().lower()
    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    h, w = rgb.shape[:2]
    luma = luma_np(rgb)

    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    line_base = float(np.clip(line_height, 0.04, 0.96))
    band = max(0.04, float(band_width))
    wobble = (
        np.sin((x * 8.0) + (breakup * 7.5)) * (0.012 + (breakup * 0.035))
        + np.cos((x * 19.0) - 0.6) * (0.006 + (breakup * 0.018))
    ).astype(np.float32, copy=False)
    line_field = np.clip(line_base + wobble, 0.02, 0.98).astype(np.float32, copy=False)

    if resolved_mode == "combined_waterline":
        darks = np.clip(1.0 - luma, 0.0, 1.0).astype(np.float32, copy=False)
        cavities = np.clip((darks * 0.62) + (_local_detail(darks, 2.8) * 0.58), 0.0, 1.0).astype(np.float32, copy=False)
        detail = _local_detail(luma, 1.8)
        base = np.clip((cavities * (0.56 + (cavity_bias * 0.44))) + (detail * 0.22), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    else:
        base, resolved_mode = scalar_from_source(rgb, resolved_mode, source_mask_np, True)

    capillary_extent = max(0.04, 0.03 + (float(np.clip(capillary_rise, 0.0, 1.0)) * 0.24))
    band_core = np.clip(1.0 - (np.abs(y - line_field) / max(0.02, band * 0.55)), 0.0, 1.0).astype(np.float32, copy=False)

    if resolved_orientation == "top":
        settled = np.clip((line_field - y) / max(0.04, (band * 1.25) + 0.04), 0.0, 1.0).astype(np.float32, copy=False)
        capillary_zone = np.clip((y - (line_field - capillary_extent)) / capillary_extent, 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    else:
        settled = np.clip((y - line_field) / max(0.04, (band * 1.25) + 0.04), 0.0, 1.0).astype(np.float32, copy=False)
        capillary_zone = np.clip(((line_field + capillary_extent) - y) / capillary_extent, 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    scalar = np.clip(
        (band_core * 0.54)
        + (settled * 0.20)
        + (base * capillary_zone * (0.22 + (cavity_bias * 0.48))),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    breakup_field = (
        0.56
        + (0.24 * np.sin((x * 15.0) + (y * 5.0)))
        + (0.20 * np.cos((x * 27.0) + (y * 9.0)))
    ).astype(np.float32, copy=False)
    breakup_field = np.clip((1.0 - breakup) + (_normalize_field(breakup_field) * breakup), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )
    scalar = np.clip(scalar * breakup_field, 0.0, 1.0).astype(np.float32, copy=False)

    if source_mask_np is not None and resolved_mode != "mask":
        scalar = np.clip(scalar * np.clip(source_mask_np, 0.0, 1.0), 0.0, 1.0).astype(np.float32, copy=False)

    threshold = 1.0 - float(np.clip(coverage, 0.0, 1.0))
    softness = 0.08 + (breakup * 0.14)
    scalar = smoothstep_np(max(0.0, threshold - softness), min(1.0, threshold + softness), scalar).astype(
        np.float32,
        copy=False,
    )
    scalar = _apply_contrast(scalar, max(0.1, float(contrast)))
    scalar = np.power(np.clip(scalar, 0.0, 1.0), max(0.1, float(gamma))).astype(np.float32, copy=False)
    scalar = blur_single_channel(scalar, max(0.0, float(blur_radius)))
    scalar = np.clip(scalar * float(np.clip(amount, 0.0, 1.0)), 0.0, 1.0).astype(np.float32, copy=False)
    if bool(invert_values):
        scalar = (1.0 - scalar).astype(np.float32, copy=False)
    return scalar, f"{resolved_mode}:{resolved_orientation}"


class x1SurfaceDustMask:
    SEARCH_ALIASES = ["surface dust", "dust mask", "dust accumulation", "weathering dust"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_dust",
            "top_bias": 0.52,
            "cavity_bias": 0.44,
            "breakup": 0.30,
            "amount": 0.82,
            "coverage": 0.54,
            "contrast": 1.20,
            "gamma": 1.0,
            "blur_radius": 1.2,
            "invert_values": False,
            "mask_feather": 8.0,
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
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "dust_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_EFFECTS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "top_bias": {"min": 0.0, "max": 1.0},
                "cavity_bias": {"min": 0.0, "max": 1.0},
                "breakup": {"min": 0.0, "max": 1.0},
                "amount": {"min": 0.0, "max": 1.0},
                "coverage": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_mode = str(settings["source_mode"]).lower()

        for idx in range(int(b)):
            scalar_np[idx], resolved_mode = _resolve_dust_scalar(
                src=src_np[idx],
                source_mode=str(settings["source_mode"]),
                source_mask_np=source_mask_np[idx] if source_mask_np is not None else None,
                top_bias=float(settings["top_bias"]),
                cavity_bias=float(settings["cavity_bias"]),
                breakup=float(settings["breakup"]),
                amount=float(settings["amount"]),
                coverage=float(settings["coverage"]),
                contrast=float(settings["contrast"]),
                gamma=float(settings["gamma"]),
                blur_radius=float(settings["blur_radius"]),
                invert_values=bool(settings["invert_values"]),
            )

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=scalar_np,
            mask=mask,
            mask_feather=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
        )
        info = (
            "x1SurfaceDustMask: source={}, top_bias={:.2f}, cavity_bias={:.2f}, breakup={:.2f}, "
            "amount={:.2f}, coverage={:.2f}, contrast={:.2f}, gamma={:.2f}, blur_radius={:.1f}px, "
            "invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_mode,
            float(settings["top_bias"]),
            float(settings["cavity_bias"]),
            float(settings["breakup"]),
            float(settings["amount"]),
            float(settings["coverage"]),
            float(settings["contrast"]),
            float(settings["gamma"]),
            float(settings["blur_radius"]),
            bool(settings["invert_values"]),
            float(settings["mask_feather"]),
            coverage,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out, out_mask, info)


class x1SurfaceStreakMask:
    SEARCH_ALIASES = ["surface streak", "leak streak", "grime streak", "drip streak mask"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_streak",
            "direction": "down",
            "streak_length": 0.62,
            "anchor_bias": 0.56,
            "breakup": 0.42,
            "coverage": 0.46,
            "contrast": 1.25,
            "gamma": 1.0,
            "blur_radius": 1.0,
            "invert_values": False,
            "mask_feather": 8.0,
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
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "surface_streak_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_EFFECTS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "streak_length": {"min": 0.0, "max": 1.0},
                "anchor_bias": {"min": 0.0, "max": 1.0},
                "breakup": {"min": 0.0, "max": 1.0},
                "coverage": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_mode = str(settings["source_mode"]).lower()

        for idx in range(int(b)):
            scalar_np[idx], resolved_mode = _resolve_streak_scalar(
                src=src_np[idx],
                source_mode=str(settings["source_mode"]),
                source_mask_np=source_mask_np[idx] if source_mask_np is not None else None,
                direction=str(settings["direction"]),
                streak_length=float(settings["streak_length"]),
                anchor_bias=float(settings["anchor_bias"]),
                breakup=float(settings["breakup"]),
                coverage=float(settings["coverage"]),
                contrast=float(settings["contrast"]),
                gamma=float(settings["gamma"]),
                blur_radius=float(settings["blur_radius"]),
                invert_values=bool(settings["invert_values"]),
            )

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=scalar_np,
            mask=mask,
            mask_feather=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
        )
        info = (
            "x1SurfaceStreakMask: source={}, streak_length={:.2f}, anchor_bias={:.2f}, breakup={:.2f}, "
            "coverage={:.2f}, contrast={:.2f}, gamma={:.2f}, blur_radius={:.1f}px, invert_values={}, "
            "mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_mode,
            float(settings["streak_length"]),
            float(settings["anchor_bias"]),
            float(settings["breakup"]),
            float(settings["coverage"]),
            float(settings["contrast"]),
            float(settings["gamma"]),
            float(settings["blur_radius"]),
            bool(settings["invert_values"]),
            float(settings["mask_feather"]),
            coverage,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out, out_mask, info)


class x1SurfaceRustBloomMask:
    SEARCH_ALIASES = ["surface rust", "rust bloom", "oxidation mask", "corrosion bloom"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_rust",
            "cavity_bias": 0.48,
            "edge_bias": 0.60,
            "warm_bias": 0.34,
            "bloom_spread": 0.52,
            "breakup": 0.34,
            "amount": 0.86,
            "coverage": 0.48,
            "contrast": 1.28,
            "gamma": 1.0,
            "blur_radius": 1.2,
            "invert_values": False,
            "mask_feather": 8.0,
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
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "surface_rust_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_EFFECTS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "cavity_bias": {"min": 0.0, "max": 1.0},
                "edge_bias": {"min": 0.0, "max": 1.0},
                "warm_bias": {"min": 0.0, "max": 1.0},
                "bloom_spread": {"min": 0.0, "max": 1.0},
                "breakup": {"min": 0.0, "max": 1.0},
                "amount": {"min": 0.0, "max": 1.0},
                "coverage": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_mode = str(settings["source_mode"]).lower()

        for idx in range(int(b)):
            scalar_np[idx], resolved_mode = _resolve_rust_scalar(
                src=src_np[idx],
                source_mode=str(settings["source_mode"]),
                source_mask_np=source_mask_np[idx] if source_mask_np is not None else None,
                cavity_bias=float(settings["cavity_bias"]),
                edge_bias=float(settings["edge_bias"]),
                warm_bias=float(settings["warm_bias"]),
                bloom_spread=float(settings["bloom_spread"]),
                breakup=float(settings["breakup"]),
                amount=float(settings["amount"]),
                coverage=float(settings["coverage"]),
                contrast=float(settings["contrast"]),
                gamma=float(settings["gamma"]),
                blur_radius=float(settings["blur_radius"]),
                invert_values=bool(settings["invert_values"]),
            )

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=scalar_np,
            mask=mask,
            mask_feather=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
        )
        info = (
            "x1SurfaceRustBloomMask: source={}, cavity_bias={:.2f}, edge_bias={:.2f}, warm_bias={:.2f}, "
            "bloom_spread={:.2f}, breakup={:.2f}, amount={:.2f}, coverage={:.2f}, contrast={:.2f}, "
            "gamma={:.2f}, blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_mode,
            float(settings["cavity_bias"]),
            float(settings["edge_bias"]),
            float(settings["warm_bias"]),
            float(settings["bloom_spread"]),
            float(settings["breakup"]),
            float(settings["amount"]),
            float(settings["coverage"]),
            float(settings["contrast"]),
            float(settings["gamma"]),
            float(settings["blur_radius"]),
            bool(settings["invert_values"]),
            float(settings["mask_feather"]),
            coverage,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out, out_mask, info)


class x1SurfaceWaterlineMask:
    SEARCH_ALIASES = ["surface waterline", "waterline mask", "tide line", "mineral ring"]

    @staticmethod
    def _default_settings() -> dict:
        return {
            "source_mode": "combined_waterline",
            "orientation": "bottom",
            "line_height": 0.72,
            "band_width": 0.18,
            "capillary_rise": 0.22,
            "cavity_bias": 0.44,
            "breakup": 0.26,
            "amount": 0.84,
            "coverage": 0.50,
            "contrast": 1.20,
            "gamma": 1.0,
            "blur_radius": 1.0,
            "invert_values": False,
            "mask_feather": 8.0,
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
                "source_mask": ("MASK",),
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "surface_waterline_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_EFFECTS

    def run(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        source_mask: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "line_height": {"min": 0.0, "max": 1.0},
                "band_width": {"min": 0.04, "max": 0.50},
                "capillary_rise": {"min": 0.0, "max": 1.0},
                "cavity_bias": {"min": 0.0, "max": 1.0},
                "breakup": {"min": 0.0, "max": 1.0},
                "amount": {"min": 0.0, "max": 1.0},
                "coverage": {"min": 0.0, "max": 1.0},
                "contrast": {"min": 0.1, "max": 4.0},
                "gamma": {"min": 0.1, "max": 4.0},
                "blur_radius": {"min": 0.0, "max": 128.0},
                "mask_feather": {"min": 0.0, "max": 256.0},
            },
            boolean_keys={"invert_values", "invert_mask"},
            legacy=legacy_settings,
        )

        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        scalar_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        resolved_mode = str(settings["source_mode"]).lower()

        for idx in range(int(b)):
            scalar_np[idx], resolved_mode = _resolve_waterline_scalar(
                src=src_np[idx],
                source_mode=str(settings["source_mode"]),
                source_mask_np=source_mask_np[idx] if source_mask_np is not None else None,
                orientation=str(settings["orientation"]),
                line_height=float(settings["line_height"]),
                band_width=float(settings["band_width"]),
                capillary_rise=float(settings["capillary_rise"]),
                cavity_bias=float(settings["cavity_bias"]),
                breakup=float(settings["breakup"]),
                amount=float(settings["amount"]),
                coverage=float(settings["coverage"]),
                contrast=float(settings["contrast"]),
                gamma=float(settings["gamma"]),
                blur_radius=float(settings["blur_radius"]),
                invert_values=bool(settings["invert_values"]),
            )

        out, out_mask, coverage = emit_masked_grayscale(
            base=batch,
            scalar_np=scalar_np,
            mask=mask,
            mask_feather=float(settings["mask_feather"]),
            invert_mask=bool(settings["invert_mask"]),
        )
        info = (
            "x1SurfaceWaterlineMask: source={}, line_height={:.2f}, band_width={:.2f}, capillary_rise={:.2f}, "
            "cavity_bias={:.2f}, breakup={:.2f}, amount={:.2f}, coverage={:.2f}, contrast={:.2f}, gamma={:.2f}, "
            "blur_radius={:.1f}px, invert_values={}, mask_feather={:.1f}px, mask_coverage={:.2f}%{}"
        ).format(
            resolved_mode,
            float(settings["line_height"]),
            float(settings["band_width"]),
            float(settings["capillary_rise"]),
            float(settings["cavity_bias"]),
            float(settings["breakup"]),
            float(settings["amount"]),
            float(settings["coverage"]),
            float(settings["contrast"]),
            float(settings["gamma"]),
            float(settings["blur_radius"]),
            bool(settings["invert_values"]),
            float(settings["mask_feather"]),
            coverage,
            " (inverted)" if bool(settings["invert_mask"]) else "",
        )
        return (out, out_mask, info)
