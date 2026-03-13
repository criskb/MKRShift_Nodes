from typing import Optional

import numpy as np

from .image_shared import luma_np, rgb_to_hsv_np, smoothstep_np
from .scalar_map_shared import blur_single_channel, scalar_from_source


def detail_scalar(rgb: np.ndarray, radius: float) -> np.ndarray:
    base = np.mean(np.clip(rgb[..., :3], 0.0, 1.0), axis=-1).astype(np.float32, copy=False)
    blurred = blur_single_channel(base, radius)
    return np.abs(base - blurred).astype(np.float32, copy=False)


def soft_gate(values: np.ndarray, threshold: float, softness: float) -> np.ndarray:
    gate_threshold = float(np.clip(threshold, 0.0, 1.0))
    gate_softness = float(max(0.0, softness))
    if gate_softness <= 1e-6:
        return (values >= gate_threshold).astype(np.float32)
    return smoothstep_np(
        max(0.0, gate_threshold - gate_softness),
        min(1.0, gate_threshold + gate_softness),
        values,
    )


def apply_contrast(values: np.ndarray, contrast: float) -> np.ndarray:
    contrast_value = float(max(0.0, contrast))
    if abs(contrast_value - 1.0) <= 1e-6:
        return np.clip(values, 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip(((values - 0.5) * contrast_value) + 0.5, 0.0, 1.0).astype(np.float32, copy=False)


def resolve_surface_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode == "detail":
        return detail_scalar(src[..., :3], detail_radius), mode
    if mode == "inverse_luma":
        return (1.0 - luma_np(src[..., :3])).astype(np.float32, copy=False), mode
    return scalar_from_source(src, mode, source_mask_np, True)


def resolve_clearcoat_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_clearcoat":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    base_luma = luma_np(src[..., :3])
    detail = detail_scalar(src[..., :3], detail_radius)
    _, sat, val = rgb_to_hsv_np(np.clip(src[..., :3], 0.0, 1.0))

    bright_gate = np.clip((val - 0.24) / 0.76, 0.0, 1.0).astype(np.float32, copy=False)
    neutral_gate = np.clip((0.75 - sat) / 0.75, 0.0, 1.0).astype(np.float32, copy=False)
    smooth_gate = np.clip(1.0 - (detail * (1.20 + (float(max(0.0, detail_strength)) * 0.85))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    scalar = np.clip(
        (bright_gate * 0.48)
        + (neutral_gate * 0.30)
        + (smooth_gate * 0.22)
        + (np.clip(base_luma - 0.30, 0.0, 1.0) * 0.08),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    return apply_contrast(scalar, contrast), mode


def resolve_transmission_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_transmission":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    if src.shape[-1] >= 4:
        scalar = np.clip(1.0 - src[..., 3], 0.0, 1.0).astype(np.float32, copy=False)
        return apply_contrast(scalar, contrast), "combined_transmission(alpha_inv)"

    detail = detail_scalar(src[..., :3], detail_radius)
    _, sat, val = rgb_to_hsv_np(np.clip(src[..., :3], 0.0, 1.0))
    bright_gate = np.clip((val - 0.30) / 0.70, 0.0, 1.0).astype(np.float32, copy=False)
    neutral_gate = np.clip((0.82 - sat) / 0.82, 0.0, 1.0).astype(np.float32, copy=False)
    smooth_gate = np.clip(1.0 - (detail * (1.10 + (float(max(0.0, detail_strength)) * 0.90))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    scalar = np.clip(
        (bright_gate * 0.42)
        + (smooth_gate * 0.33)
        + (neutral_gate * 0.25),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    if source_mask_np is not None:
        scalar = np.maximum(scalar, np.clip(source_mask_np, 0.0, 1.0) * 0.85).astype(np.float32, copy=False)
    return apply_contrast(scalar, contrast), mode


def resolve_thickness_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode == "combined_thickness":
        inverse_luma = (1.0 - luma_np(src[..., :3])).astype(np.float32, copy=False)
        detail = detail_scalar(src[..., :3], detail_radius)
        scalar = np.clip(
            (inverse_luma * 0.72)
            + (detail * (0.20 + (float(max(0.0, detail_strength)) * 0.20))),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)
        if src.shape[-1] >= 4:
            scalar = np.clip((scalar * 0.55) + (src[..., 3].astype(np.float32, copy=False) * 0.45), 0.0, 1.0)
            return apply_contrast(scalar, contrast), "combined_thickness(alpha_mix)"
        return apply_contrast(scalar, contrast), mode

    if mode == "inverse_luma":
        scalar = (1.0 - luma_np(src[..., :3])).astype(np.float32, copy=False)
        return apply_contrast(scalar, contrast), mode

    scalar, resolved = resolve_surface_scalar(src, mode, source_mask_np, detail_radius)
    return apply_contrast(scalar, contrast), resolved


def resolve_clearcoat_roughness_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_clearcoat_roughness":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    base_luma = luma_np(rgb)
    detail = detail_scalar(rgb, detail_radius)
    _, sat, val = rgb_to_hsv_np(rgb)

    bright_gate = np.clip((val - 0.24) / 0.76, 0.0, 1.0).astype(np.float32, copy=False)
    neutral_gate = np.clip((0.76 - sat) / 0.76, 0.0, 1.0).astype(np.float32, copy=False)
    polish_gate = np.clip(
        1.0 - (detail * (1.10 + (float(max(0.0, detail_strength)) * 0.90))),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)

    polished = np.clip(
        (bright_gate * 0.34)
        + (neutral_gate * 0.24)
        + (polish_gate * 0.42),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    scalar = np.clip(
        ((1.0 - polished) * 0.72)
        + (detail * (0.18 + (float(max(0.0, detail_strength)) * 0.42)))
        + (sat * 0.10)
        + (np.clip(0.52 - base_luma, 0.0, 0.52) * 0.16),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    return apply_contrast(scalar, contrast), mode


def resolve_sheen_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_sheen":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    base_luma = luma_np(rgb)
    detail = detail_scalar(rgb, detail_radius)
    _, sat, val = rgb_to_hsv_np(rgb)

    color_gate = np.clip((sat - 0.06) / 0.94, 0.0, 1.0).astype(np.float32, copy=False)
    light_gate = np.clip((val - 0.10) / 0.90, 0.0, 1.0).astype(np.float32, copy=False)
    fiber_gate = np.clip(1.0 - (detail * (1.00 + (float(max(0.0, detail_strength)) * 0.85))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    scalar = np.clip(
        (color_gate * 0.40)
        + (light_gate * 0.28)
        + (fiber_gate * 0.24)
        + (np.clip(base_luma - 0.18, 0.0, 1.0) * 0.08),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    if source_mask_np is not None:
        scalar = np.maximum(scalar, np.clip(source_mask_np, 0.0, 1.0) * 0.25).astype(np.float32, copy=False)
    return apply_contrast(scalar, contrast), mode


def resolve_iridescence_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_iridescence":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    detail = detail_scalar(rgb, detail_radius)
    _, sat, val = rgb_to_hsv_np(rgb)

    sat_gate = np.clip((sat - 0.10) / 0.90, 0.0, 1.0).astype(np.float32, copy=False)
    bright_gate = np.clip((val - 0.16) / 0.84, 0.0, 1.0).astype(np.float32, copy=False)
    smooth_gate = np.clip(1.0 - (detail * (1.12 + (float(max(0.0, detail_strength)) * 0.92))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    scalar = np.clip(
        (sat_gate * 0.42)
        + (bright_gate * 0.24)
        + ((sat_gate * bright_gate) * 0.18)
        + (smooth_gate * 0.16),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    if src.shape[-1] >= 4:
        alpha_mix = np.clip(1.0 - src[..., 3].astype(np.float32, copy=False), 0.0, 1.0)
        scalar = np.clip((scalar * 0.82) + (alpha_mix * 0.18), 0.0, 1.0).astype(np.float32, copy=False)
    if source_mask_np is not None:
        scalar = np.maximum(scalar, np.clip(source_mask_np, 0.0, 1.0) * 0.30).astype(np.float32, copy=False)
    return apply_contrast(scalar, contrast), mode


def resolve_anisotropy_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_anisotropy":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    base_luma = luma_np(rgb)
    detail = detail_scalar(rgb, detail_radius)
    _, sat, val = rgb_to_hsv_np(rgb)

    bright_gate = np.clip((val - 0.16) / 0.84, 0.0, 1.0).astype(np.float32, copy=False)
    neutral_gate = np.clip((0.70 - sat) / 0.70, 0.0, 1.0).astype(np.float32, copy=False)
    textile_gate = np.clip((sat - 0.08) / 0.92, 0.0, 1.0).astype(np.float32, copy=False)
    smooth_gate = np.clip(1.0 - (detail * (1.10 + (float(max(0.0, detail_strength)) * 0.90))), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    metal_like = np.clip((bright_gate * 0.40) + (neutral_gate * 0.28) + (smooth_gate * 0.32), 0.0, 1.0)
    fiber_like = np.clip((textile_gate * 0.38) + (bright_gate * 0.18) + (smooth_gate * 0.24) + (detail * 0.20), 0.0, 1.0)
    scalar = np.clip(np.maximum(metal_like, fiber_like * 0.92) + (np.clip(base_luma - 0.20, 0.0, 1.0) * 0.05), 0.0, 1.0)
    if source_mask_np is not None:
        scalar = np.maximum(scalar, np.clip(source_mask_np, 0.0, 1.0) * 0.20).astype(np.float32, copy=False)
    return apply_contrast(scalar.astype(np.float32, copy=False), contrast), mode


def resolve_edge_wear_scalar(
    src: np.ndarray,
    source_mode: str,
    source_mask_np: Optional[np.ndarray],
    edge_radius: float,
    detail_radius: float,
    detail_strength: float,
    contrast: float,
) -> tuple[np.ndarray, str]:
    mode = str(source_mode).lower()
    if mode != "combined_edge_wear":
        return resolve_surface_scalar(src, mode, source_mask_np, detail_radius)

    rgb = np.clip(src[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    base_luma = luma_np(rgb)
    blurred = blur_single_channel(base_luma, radius=max(0.1, edge_radius))
    detail = detail_scalar(rgb, detail_radius)
    _, sat, val = rgb_to_hsv_np(rgb)

    convex = np.clip(base_luma - blurred, 0.0, 1.0).astype(np.float32, copy=False)
    bright_gate = np.clip((val - 0.22) / 0.78, 0.0, 1.0).astype(np.float32, copy=False)
    neutral_gate = np.clip((0.84 - sat) / 0.84, 0.0, 1.0).astype(np.float32, copy=False)

    scalar = np.clip(
        (convex * 0.54)
        + (detail * (0.18 + (float(max(0.0, detail_strength)) * 0.34)))
        + (bright_gate * 0.18)
        + (neutral_gate * 0.10),
        0.0,
        1.0,
    ).astype(np.float32, copy=False)
    if source_mask_np is not None:
        scalar = np.clip(np.maximum(scalar, np.clip(source_mask_np, 0.0, 1.0) * 0.35), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    return apply_contrast(scalar, contrast), mode
