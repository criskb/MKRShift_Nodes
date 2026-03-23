from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .pose_studio_shared import CONTROL_SPECS, IMAGE_FIT_ANCHOR_GROUPS, IMAGE_FIT_ANCHOR_KEYS, LEFT_RIGHT_KEYS, POSE_BONES, POSE_PRESETS, apply_pose_preset, build_pose_points, project_pose_points


FIT_PRESET_KEYS = tuple(POSE_PRESETS.keys())
FIT_CONTROL_KEYS = (
    "root_yaw",
    "root_pitch",
    "root_roll",
    "spine_bend",
    "spine_twist",
    "head_yaw",
    "head_pitch",
    "head_roll",
    "arm_raise_l",
    "arm_forward_l",
    "arm_twist_l",
    "elbow_bend_l",
    "arm_raise_r",
    "arm_forward_r",
    "arm_twist_r",
    "elbow_bend_r",
    "hip_lift_l",
    "hip_side_l",
    "knee_bend_l",
    "foot_point_l",
    "hip_lift_r",
    "hip_side_r",
    "knee_bend_r",
    "foot_point_r",
)
FIT_STEP_SCHEDULE = (28.0, 14.0, 7.0)
FIT_VIEW = {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0}
FIT_CONTROL_ORDER = (
    "root_yaw",
    "root_pitch",
    "root_roll",
    "spine_bend",
    "spine_twist",
    "hip_lift_l",
    "hip_side_l",
    "knee_bend_l",
    "foot_point_l",
    "hip_lift_r",
    "hip_side_r",
    "knee_bend_r",
    "foot_point_r",
    "arm_raise_l",
    "arm_forward_l",
    "arm_twist_l",
    "elbow_bend_l",
    "wrist_twist_l",
    "arm_raise_r",
    "arm_forward_r",
    "arm_twist_r",
    "elbow_bend_r",
    "wrist_twist_r",
    "head_yaw",
    "head_pitch",
    "head_roll",
)
FIT_CONTROL_WEIGHTS = {
    "root_yaw": 0.8,
    "root_pitch": 0.7,
    "root_roll": 1.2,
    "spine_bend": 0.8,
    "spine_twist": 0.9,
    "head_yaw": 0.5,
    "head_pitch": 0.5,
    "head_roll": 0.8,
    "arm_raise_l": 0.4,
    "arm_forward_l": 0.5,
    "arm_twist_l": 0.85,
    "elbow_bend_l": 0.7,
    "wrist_twist_l": 0.95,
    "arm_raise_r": 0.4,
    "arm_forward_r": 0.5,
    "arm_twist_r": 0.85,
    "elbow_bend_r": 0.7,
    "wrist_twist_r": 0.95,
    "hip_lift_l": 0.8,
    "hip_side_l": 1.0,
    "knee_bend_l": 1.25,
    "foot_point_l": 1.1,
    "hip_lift_r": 0.8,
    "hip_side_r": 1.0,
    "knee_bend_r": 1.25,
    "foot_point_r": 1.1,
}
FIT_EXTRA_SEEDS = (
    (
        "dual_kneel",
        {
            "root_pitch": 16.0,
            "spine_bend": 20.0,
            "spine_twist": 8.0,
            "head_pitch": -8.0,
            "hip_lift_l": 24.0,
            "hip_side_l": 10.0,
            "knee_bend_l": 104.0,
            "foot_point_l": 20.0,
            "hip_lift_r": 18.0,
            "hip_side_r": -10.0,
            "knee_bend_r": 110.0,
            "foot_point_r": 18.0,
        },
    ),
    (
        "dual_kneel_overhead_l",
        {
            "root_yaw": 28.0,
            "root_pitch": 18.0,
            "root_roll": 6.0,
            "spine_bend": 22.0,
            "spine_twist": 18.0,
            "head_yaw": 18.0,
            "head_pitch": -6.0,
            "arm_raise_l": 118.0,
            "arm_forward_l": 18.0,
            "arm_twist_l": 18.0,
            "elbow_bend_l": 24.0,
            "arm_raise_r": 92.0,
            "arm_forward_r": -54.0,
            "arm_twist_r": 32.0,
            "elbow_bend_r": 78.0,
            "hip_lift_l": 18.0,
            "hip_side_l": 8.0,
            "knee_bend_l": 112.0,
            "foot_point_l": 16.0,
            "hip_lift_r": 22.0,
            "hip_side_r": -12.0,
            "knee_bend_r": 96.0,
            "foot_point_r": 12.0,
        },
    ),
    (
        "dual_kneel_overhead_r",
        {
            "root_yaw": -28.0,
            "root_pitch": 18.0,
            "root_roll": -6.0,
            "spine_bend": 22.0,
            "spine_twist": -18.0,
            "head_yaw": -18.0,
            "head_pitch": -6.0,
            "arm_raise_l": 92.0,
            "arm_forward_l": 54.0,
            "arm_twist_l": -32.0,
            "elbow_bend_l": 78.0,
            "arm_raise_r": 118.0,
            "arm_forward_r": -18.0,
            "arm_twist_r": -18.0,
            "elbow_bend_r": 24.0,
            "hip_lift_l": 22.0,
            "hip_side_l": 12.0,
            "knee_bend_l": 96.0,
            "foot_point_l": 12.0,
            "hip_lift_r": 18.0,
            "hip_side_r": -8.0,
            "knee_bend_r": 112.0,
            "foot_point_r": 16.0,
        },
    ),
    (
        "airborne_reach_l",
        {
            "root_yaw": 18.0,
            "root_pitch": 24.0,
            "root_roll": -10.0,
            "spine_bend": 18.0,
            "spine_twist": 12.0,
            "head_yaw": 10.0,
            "head_pitch": -4.0,
            "arm_raise_l": 98.0,
            "arm_forward_l": 36.0,
            "elbow_bend_l": 20.0,
            "arm_raise_r": 62.0,
            "arm_forward_r": -42.0,
            "elbow_bend_r": 40.0,
            "hip_lift_l": 70.0,
            "hip_side_l": 16.0,
            "knee_bend_l": 124.0,
            "foot_point_l": 26.0,
            "hip_lift_r": 20.0,
            "hip_side_r": -18.0,
            "knee_bend_r": 34.0,
            "foot_point_r": 10.0,
        },
    ),
    (
        "airborne_reach_r",
        {
            "root_yaw": -18.0,
            "root_pitch": 24.0,
            "root_roll": 10.0,
            "spine_bend": 18.0,
            "spine_twist": -12.0,
            "head_yaw": -10.0,
            "head_pitch": -4.0,
            "arm_raise_l": 62.0,
            "arm_forward_l": 42.0,
            "elbow_bend_l": 40.0,
            "arm_raise_r": 98.0,
            "arm_forward_r": -36.0,
            "elbow_bend_r": 20.0,
            "hip_lift_l": 20.0,
            "hip_side_l": 18.0,
            "knee_bend_l": 34.0,
            "foot_point_l": 10.0,
            "hip_lift_r": 70.0,
            "hip_side_r": -16.0,
            "knee_bend_r": 124.0,
            "foot_point_r": 26.0,
        },
    ),
)
POSE_MASS_WEIGHTS = {
    "pelvis": 2.0,
    "spine": 1.5,
    "chest": 1.7,
    "neck": 0.5,
    "head": 0.9,
    "shoulder_l": 0.3,
    "shoulder_r": 0.3,
    "elbow_l": 0.25,
    "elbow_r": 0.25,
    "wrist_l": 0.15,
    "wrist_r": 0.15,
    "hand_l": 0.1,
    "hand_r": 0.1,
    "hip_l": 0.8,
    "hip_r": 0.8,
    "knee_l": 0.7,
    "knee_r": 0.7,
    "ankle_l": 0.45,
    "ankle_r": 0.45,
    "toe_l": 0.2,
    "toe_r": 0.2,
}


def _largest_component(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    best = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            points = []
            while stack:
                cy, cx = stack.pop()
                points.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if len(points) > len(best):
                best = points
    out = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        out[y, x] = True
    return out


def _remove_border_connected(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    out = mask.copy()
    visited = np.zeros((h, w), dtype=bool)
    stack = []
    for x in range(w):
        if out[0, x]:
            stack.append((0, x))
        if out[h - 1, x]:
            stack.append((h - 1, x))
    for y in range(h):
        if out[y, 0]:
            stack.append((y, 0))
        if out[y, w - 1]:
            stack.append((y, w - 1))
    while stack:
        cy, cx = stack.pop()
        if not (0 <= cy < h and 0 <= cx < w):
            continue
        if visited[cy, cx] or not out[cy, cx]:
            continue
        visited[cy, cx] = True
        out[cy, cx] = False
        stack.extend(((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)))
    return out


def extract_pose_reference_mask(image: np.ndarray, target_size: int = 128) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float32)
    if arr.ndim == 4:
        arr = arr[0]
    if arr.ndim != 3:
        raise ValueError(f"Expected image array [H,W,C], got shape={arr.shape}")
    if arr.shape[-1] == 4:
        rgb = arr[..., :3]
        alpha = arr[..., 3]
    else:
        rgb = arr[..., :3]
        alpha = np.ones(arr.shape[:2], dtype=np.float32)

    rgb = np.clip(rgb, 0.0, 1.0)
    alpha = np.clip(alpha, 0.0, 1.0)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    sat = rgb.max(axis=-1) - rgb.min(axis=-1)

    border_mask = np.zeros(luma.shape, dtype=bool)
    border_mask[0, :] = True
    border_mask[-1, :] = True
    border_mask[:, 0] = True
    border_mask[:, -1] = True
    border_rgb = rgb[border_mask]
    border_luma = luma[border_mask]
    border_sat = sat[border_mask]
    bg_rgb = np.median(border_rgb, axis=0)
    bg_luma = float(np.median(border_luma))
    border_color_delta = np.linalg.norm(border_rgb - bg_rgb, axis=1)
    border_luma_delta = np.abs(border_luma - bg_luma)
    color_delta = np.linalg.norm(rgb - bg_rgb[None, None, :], axis=-1)
    luma_delta = np.abs(luma - bg_luma)
    color_threshold = max(0.06, float(np.quantile(border_color_delta, 0.92)) + 0.035)
    luma_threshold = max(0.055, float(np.quantile(border_luma_delta, 0.92)) + 0.035)
    sat_threshold = max(0.08, float(np.quantile(border_sat, 0.92)) + 0.05)

    foreground_mask = (
        (alpha > 0.05)
        & (
            ((color_delta >= color_threshold) & ((luma_delta >= luma_threshold * 0.65) | (sat >= sat_threshold)))
            | (luma_delta >= luma_threshold * 1.35)
            | (sat >= sat_threshold * 1.2)
        )
    )

    dark_mask = (luma <= np.quantile(luma, 0.38)) & (alpha > 0.05)
    light_mask = (luma >= np.quantile(luma, 0.72)) & (alpha > 0.05)

    yy, xx = np.mgrid[0 : luma.shape[0], 0 : luma.shape[1]]
    cy = (yy / max(1, luma.shape[0] - 1) - 0.52) ** 2
    cx = (xx / max(1, luma.shape[1] - 1) - 0.5) ** 2
    center_weight = np.exp(-(cx * 10.0 + cy * 7.0))

    def score(mask: np.ndarray) -> float:
      area = float(mask.mean())
      if area < 0.002 or area > 0.72:
          return -1e9
      return float((mask * center_weight).sum() / max(mask.sum(), 1.0)) - abs(area - 0.12) * 1.6

    foreground_mask = _largest_component(_remove_border_connected(foreground_mask))
    dark_mask = _largest_component(_remove_border_connected(dark_mask))
    light_mask = _largest_component(_remove_border_connected(light_mask))
    candidates = [foreground_mask, dark_mask, light_mask]
    mask = max(candidates, key=score)
    mask = _largest_component(mask)
    if not mask.any():
        return np.zeros((target_size, target_size), dtype=bool)

    ys, xs = np.where(mask)
    pad = 4
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + pad + 1, mask.shape[0])
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + pad + 1, mask.shape[1])
    crop = mask[y0:y1, x0:x1].astype(np.uint8) * 255
    pil = Image.fromarray(crop, mode="L").resize((target_size, target_size), Image.Resampling.BILINEAR)
    return np.asarray(pil, dtype=np.float32) >= 64.0


def render_pose_mask(settings: Dict[str, Any], width: int = 128, height: int = 128) -> np.ndarray:
    points = build_pose_points(settings)
    screen = project_pose_points(points, width, height, FIT_VIEW)
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    for start, end in POSE_BONES:
        draw.line([screen[start], screen[end]], fill=255, width=9)
    for point in screen.values():
        draw.ellipse([(point[0] - 6, point[1] - 6), (point[0] + 6, point[1] + 6)], fill=255)
    return np.asarray(img, dtype=np.uint8) >= 96


def _mask_score(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    union = float(np.logical_or(a, b).sum())
    if union <= 1e-5:
        return -1.0
    return inter / union


def _upper_mask_score(a: np.ndarray, b: np.ndarray) -> float:
    cutoff = max(1, int(a.shape[0] * 0.62))
    return _mask_score(a[:cutoff], b[:cutoff])


def _lower_mask_score(a: np.ndarray, b: np.ndarray) -> float:
    cutoff = max(1, int(a.shape[0] * 0.5))
    return _mask_score(a[cutoff:], b[cutoff:])


def _mask_bbox(mask: np.ndarray) -> Tuple[float, float, float, float]:
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return 0.5, 0.5, 0.0, 0.0
    height, width = mask.shape
    x0 = float(xs.min())
    x1 = float(xs.max())
    y0 = float(ys.min())
    y1 = float(ys.max())
    cx = ((x0 + x1) * 0.5) / max(1.0, float(width - 1))
    cy = ((y0 + y1) * 0.5) / max(1.0, float(height - 1))
    bw = (x1 - x0 + 1.0) / max(1.0, float(width))
    bh = (y1 - y0 + 1.0) / max(1.0, float(height))
    return cx, cy, bw, bh


def _frame_hint(mask: np.ndarray) -> Dict[str, float]:
    cx, cy, bw, bh = _mask_bbox(mask)
    return {
        "cx": round(float(cx), 4),
        "cy": round(float(cy), 4),
        "bw": round(float(bw), 4),
        "bh": round(float(bh), 4),
    }


def _bbox_alignment_score(a: np.ndarray, b: np.ndarray) -> float:
    acx, acy, aw, ah = _mask_bbox(a)
    bcx, bcy, bw, bh = _mask_bbox(b)
    if aw <= 1e-6 or ah <= 1e-6 or bw <= 1e-6 or bh <= 1e-6:
        return -1.0
    center_dx = abs(acx - bcx)
    center_dy = abs(acy - bcy)
    span_dw = abs(aw - bw)
    span_dh = abs(ah - bh)
    penalty = (center_dx * 1.05) + (center_dy * 1.2) + (span_dw * 0.8) + (span_dh * 0.95)
    return max(-1.0, 1.0 - penalty * 1.6)


def _airborne_score(mask: np.ndarray) -> float:
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return 0.0
    y0 = int(ys.min())
    y1 = int(ys.max())
    x0 = int(xs.min())
    x1 = int(xs.max())
    body_h = max(1, y1 - y0 + 1)
    body_w = max(1, x1 - x0 + 1)
    bottom_start = max(y0, y1 - max(2, int(body_h * 0.08)))
    bottom_band = mask[bottom_start : y1 + 1, x0 : x1 + 1]
    if bottom_band.size == 0:
        return 0.0
    row_widths = bottom_band.sum(axis=1).astype(np.float32)
    max_bottom_width = float(row_widths.max()) if row_widths.size else 0.0
    bottom_ratio = max_bottom_width / max(1.0, float(body_w))
    side_margin = min(
        abs(float(xs.min()) - float(x0)),
        abs(float(x1) - float(xs.max())),
    ) / max(1.0, float(body_w))
    airborne = (0.28 - bottom_ratio) * 3.4 + side_margin * 0.8
    return float(max(0.0, min(1.0, airborne)))


def extract_pose_reference_anchors(mask: np.ndarray) -> Dict[str, Dict[str, float]]:
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return {}

    height, width = mask.shape
    y0 = int(ys.min())
    y1 = int(ys.max())
    x0 = int(xs.min())
    x1 = int(xs.max())
    body_h = max(1, y1 - y0 + 1)

    row_bounds: Dict[int, Tuple[int, int]] = {}
    for row in range(y0, y1 + 1):
        row_xs = np.where(mask[row])[0]
        if len(row_xs):
            row_bounds[row] = (int(row_xs.min()), int(row_xs.max()))

    def _band_points(start_frac: float, end_frac: float, side: str | None = None) -> list[tuple[int, int]]:
        start = y0 + int(body_h * start_frac)
        end = y0 + int(body_h * end_frac)
        points: list[tuple[int, int]] = []
        center_x = (x0 + x1) * 0.5
        for row in range(max(y0, start), min(y1, end) + 1):
            if row not in row_bounds:
                continue
            left, right = row_bounds[row]
            row_xs = np.where(mask[row])[0]
            if side == "l":
                row_xs = row_xs[row_xs <= center_x]
            elif side == "r":
                row_xs = row_xs[row_xs >= center_x]
            for x in row_xs:
                points.append((int(x), row))
        return points

    def _centroid(points: list[tuple[int, int]]) -> tuple[float, float] | None:
        if not points:
            return None
        xs_local = [p[0] for p in points]
        ys_local = [p[1] for p in points]
        return float(sum(xs_local) / len(xs_local)), float(sum(ys_local) / len(ys_local))

    def _norm(point: tuple[float, float] | None) -> Dict[str, float] | None:
        if point is None:
            return None
        return {
            "x": float(point[0] / max(1.0, width - 1)),
            "y": float(point[1] / max(1.0, height - 1)),
        }

    centerline_points = []
    for row in range(y0 + int(body_h * 0.18), y0 + int(body_h * 0.82)):
        if row not in row_bounds:
            continue
        left, right = row_bounds[row]
        centerline_points.append((left + right) * 0.5)
    center_x = float(sum(centerline_points) / len(centerline_points)) if centerline_points else float((x0 + x1) * 0.5)

    anchors: Dict[str, Dict[str, float]] = {}
    top_rows = [row for row in range(y0, min(y1, y0 + max(4, int(body_h * 0.06))) + 1) if row in row_bounds]
    if top_rows:
        top_xs = []
        for row in top_rows:
            left, right = row_bounds[row]
            top_xs.extend(range(left, right + 1))
        if top_xs:
            anchors["head"] = _norm((float(sum(top_xs) / len(top_xs)), float(min(top_rows)))) or anchors.get("head")

    for key, band, side in (
        ("chest", (0.2, 0.38), None),
        ("pelvis", (0.5, 0.66), None),
        ("knee_l", (0.62, 0.8), "l"),
        ("knee_r", (0.62, 0.8), "r"),
        ("ankle_l", (0.8, 0.96), "l"),
        ("ankle_r", (0.8, 0.96), "r"),
    ):
        point = _centroid(_band_points(band[0], band[1], side))
        norm_point = _norm(point)
        if norm_point:
            anchors[key] = norm_point

    shoulder_band = _band_points(0.18, 0.34, None)
    if shoulder_band:
        left_points = [point for point in shoulder_band if point[0] <= center_x]
        right_points = [point for point in shoulder_band if point[0] >= center_x]
        if left_points:
            leftmost = min(left_points, key=lambda point: point[0])
            anchors["shoulder_l"] = _norm((float(leftmost[0]), float(leftmost[1]))) or anchors.get("shoulder_l")
        if right_points:
            rightmost = max(right_points, key=lambda point: point[0])
            anchors["shoulder_r"] = _norm((float(rightmost[0]), float(rightmost[1]))) or anchors.get("shoulder_r")

    hand_band = _band_points(0.08, 0.58, None)
    if hand_band:
        left_points = [point for point in hand_band if point[0] <= center_x]
        right_points = [point for point in hand_band if point[0] >= center_x]
        if left_points:
            leftmost = min(left_points, key=lambda point: point[0])
            anchors["hand_l"] = _norm((float(leftmost[0]), float(leftmost[1]))) or anchors.get("hand_l")
        if right_points:
            rightmost = max(right_points, key=lambda point: point[0])
            anchors["hand_r"] = _norm((float(rightmost[0]), float(rightmost[1]))) or anchors.get("hand_r")

    foot_band = _band_points(0.84, 1.0, None)
    if foot_band:
        left_points = [point for point in foot_band if point[0] <= center_x]
        right_points = [point for point in foot_band if point[0] >= center_x]
        if left_points:
            left_toe = max(left_points, key=lambda point: (point[1], -point[0]))
            anchors["toe_l"] = _norm((float(left_toe[0]), float(left_toe[1]))) or anchors.get("toe_l")
        if right_points:
            right_toe = max(right_points, key=lambda point: (point[1], point[0]))
            anchors["toe_r"] = _norm((float(right_toe[0]), float(right_toe[1]))) or anchors.get("toe_r")

    return {
        key: value
        for key, value in anchors.items()
        if key in IMAGE_FIT_ANCHOR_KEYS and isinstance(value, dict)
    }


def _normalize_anchor_points(points: Dict[str, Tuple[float, float]]) -> Dict[str, Tuple[float, float]]:
    if not points:
        return {}
    xs = [point[0] for point in points.values()]
    ys = [point[1] for point in points.values()]
    x0 = min(xs)
    x1 = max(xs)
    y0 = min(ys)
    y1 = max(ys)
    span_x = max(1e-6, x1 - x0)
    span_y = max(1e-6, y1 - y0)
    return {
        key: ((point[0] - x0) / span_x, (point[1] - y0) / span_y)
        for key, point in points.items()
    }


def _anchor_alignment_score(settings: Dict[str, Any], anchors: Dict[str, Dict[str, float]] | None) -> float:
    if not anchors:
        return 0.0
    active_anchors = {
        key: entry
        for key, entry in anchors.items()
        if key in IMAGE_FIT_ANCHOR_KEYS and isinstance(entry, dict)
    }
    if not active_anchors:
        return 0.0

    screen = project_pose_points(build_pose_points(settings), 128, 128, FIT_VIEW)
    model_points = {
        key: screen[key]
        for key in active_anchors.keys()
        if key in screen
    }
    if not model_points:
        return 0.0

    reference_points = {
        key: (float(active_anchors[key].get("x", 0.5)), float(active_anchors[key].get("y", 0.5)))
        for key in model_points.keys()
    }
    norm_model = _normalize_anchor_points(model_points)
    norm_reference = _normalize_anchor_points(reference_points)
    if not norm_model or not norm_reference:
        return 0.0

    distances = []
    for key in norm_model.keys():
        if key not in norm_reference:
            continue
        dx = norm_model[key][0] - norm_reference[key][0]
        dy = norm_model[key][1] - norm_reference[key][1]
        distances.append((dx * dx + dy * dy) ** 0.5)
    if not distances:
        return 0.0
    mean_distance = float(sum(distances) / len(distances))
    return max(-1.0, 1.0 - mean_distance * 1.55)


def filter_anchors_by_groups(
    anchors: Dict[str, Dict[str, float]] | None,
    enabled_groups: Dict[str, bool] | None,
) -> Dict[str, Dict[str, float]] | None:
    if not anchors:
        return anchors
    group_map = {}
    for group, keys in IMAGE_FIT_ANCHOR_GROUPS.items():
        for key in keys:
            group_map[key] = group
    return {
        key: entry
        for key, entry in anchors.items()
        if bool((enabled_groups or {}).get(group_map.get(key, "body"), True))
    }


def merge_pose_reference_anchors(
    mask: np.ndarray,
    anchors: Dict[str, Dict[str, float]] | None,
) -> Dict[str, Dict[str, float]]:
    merged = extract_pose_reference_anchors(mask)
    for key, entry in (anchors or {}).items():
        if key in IMAGE_FIT_ANCHOR_KEYS and isinstance(entry, dict):
            merged[key] = {
                "x": float(entry.get("x", 0.5)),
                "y": float(entry.get("y", 0.5)),
            }
    return merged


def _pose_regularization(settings: Dict[str, Any]) -> float:
    penalty = 0.0
    controls = settings.get("controls", {})
    for key, spec in CONTROL_SPECS.items():
        value = float(controls.get(key, spec["default"]))
        span = max(1e-6, float(spec["max"]) - float(spec["min"]))
        deviation = abs(value - float(spec["default"])) / span
        penalty += deviation * FIT_CONTROL_WEIGHTS.get(key, 0.6)
    return penalty


def _support_penalty(settings: Dict[str, Any], target_mask: np.ndarray | None = None) -> float:
    points = build_pose_points(settings)
    ground_keys = ("knee_l", "ankle_l", "toe_l", "knee_r", "ankle_r", "toe_r")
    ground_y = min(points[key][1] for key in ground_keys)

    total_weight = sum(POSE_MASS_WEIGHTS.values())
    com_x = sum(points[key][0] * weight for key, weight in POSE_MASS_WEIGHTS.items()) / max(total_weight, 1e-6)
    com_z = sum(points[key][2] * weight for key, weight in POSE_MASS_WEIGHTS.items()) / max(total_weight, 1e-6)

    support_contacts = [
        points[key]
        for key in ground_keys
        if points[key][1] <= ground_y + 0.16
    ]
    if len(support_contacts) < 2:
        support_contacts = [points[key] for key in ("ankle_l", "toe_l", "ankle_r", "toe_r")]

    xs = [point[0] for point in support_contacts]
    zs = [point[2] for point in support_contacts]
    x_min = min(xs) - 0.08
    x_max = max(xs) + 0.08
    z_min = min(zs) - 0.06
    z_max = max(zs) + 0.1

    penalty = 0.0
    if com_x < x_min:
        penalty += (x_min - com_x) * 2.6
    elif com_x > x_max:
        penalty += (com_x - x_max) * 2.6
    if com_z < z_min:
        penalty += (z_min - com_z) * 1.8
    elif com_z > z_max:
        penalty += (com_z - z_max) * 1.8

    controls = settings.get("controls", {})
    for side in ("l", "r"):
        bend = float(controls.get(f"knee_bend_{side}", 0.0))
        contact_clearance = min(points[f"knee_{side}"][1], points[f"ankle_{side}"][1], points[f"toe_{side}"][1]) - ground_y
        if bend >= 90.0 and contact_clearance > 0.14:
            penalty += (contact_clearance - 0.14) * 3.0
        elif bend >= 60.0 and contact_clearance > 0.2:
            penalty += (contact_clearance - 0.2) * 1.8
    airborne = _airborne_score(target_mask) if target_mask is not None else 0.0
    return penalty * (1.0 - airborne * 0.82)


def _fit_score(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    settings: Dict[str, Any],
    anchors: Dict[str, Dict[str, float]] | None = None,
    mode: str = "fit_from_image",
) -> float:
    full = _mask_score(mask_a, mask_b)
    upper = _upper_mask_score(mask_a, mask_b)
    lower = _lower_mask_score(mask_a, mask_b)
    bbox = _bbox_alignment_score(mask_a, mask_b)
    anchor = _anchor_alignment_score(settings, anchors)
    structured = str(mode or "fit_from_image").strip().lower() == "fit_from_image_structured"
    upper_w = 0.32 if structured else 0.42
    lower_w = 0.22 if structured else 0.24
    full_w = 0.14 if structured else 0.18
    bbox_w = 0.14 if structured else 0.16
    anchor_w = 0.44 if structured else 0.22
    reg_w = 0.06 if structured else 0.085
    support_w = 0.08 if structured else 0.12
    return (
        (upper * upper_w)
        + (lower * lower_w)
        + (full * full_w)
        + (bbox * bbox_w)
        + (anchor * anchor_w)
        - (_pose_regularization(settings) * reg_w)
        - (_support_penalty(settings, mask_b) * support_w)
    )


def _flip_mask(mask: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(mask[:, ::-1])


def _mirror_pose_sides(settings: Dict[str, Any]) -> Dict[str, Any]:
    mirrored = deepcopy(settings)
    controls = mirrored.get("controls", {})
    for left_key, right_key, mode in LEFT_RIGHT_KEYS:
        left_value = float(controls.get(left_key, CONTROL_SPECS[left_key]["default"]))
        right_value = float(controls.get(right_key, CONTROL_SPECS[right_key]["default"]))
        controls[left_key] = right_value if mode == "same" else -right_value
        controls[right_key] = left_value if mode == "same" else -left_value
    mirrored["controls"] = controls
    return mirrored


def _coarse_candidates(key: str, current: float) -> Tuple[float, ...]:
    spec = CONTROL_SPECS[key]
    groups = {
        "root_yaw": (-120.0, -75.0, -40.0, 0.0, 40.0, 75.0, 120.0),
        "root_pitch": (-18.0, -8.0, 0.0, 10.0, 20.0, 30.0),
        "root_roll": (-18.0, -8.0, 0.0, 8.0, 18.0),
        "spine_bend": (-18.0, -8.0, 0.0, 12.0, 24.0, 34.0),
        "spine_twist": (-40.0, -20.0, 0.0, 20.0, 40.0),
        "head_yaw": (-35.0, -18.0, 0.0, 18.0, 35.0),
        "head_pitch": (-20.0, -8.0, 0.0, 10.0, 20.0),
        "head_roll": (-18.0, -8.0, 0.0, 8.0, 18.0),
    }
    if key.startswith("arm_raise_"):
        raw = (-12.0, 18.0, 45.0, 72.0, 98.0, 124.0)
    elif key.startswith("arm_forward_"):
        raw = (-85.0, -48.0, -20.0, 0.0, 20.0, 48.0, 85.0)
    elif key.startswith("arm_twist_") or key.startswith("wrist_twist_"):
        raw = (-72.0, -36.0, 0.0, 36.0, 72.0)
    elif key.startswith("elbow_bend_"):
        raw = (0.0, 20.0, 48.0, 78.0, 108.0, 135.0)
    elif key.startswith("hip_lift_"):
        raw = (-24.0, -8.0, 8.0, 22.0, 40.0, 60.0)
    elif key.startswith("hip_side_"):
        raw = (-24.0, -12.0, 0.0, 12.0, 24.0)
    elif key.startswith("knee_bend_"):
        raw = (0.0, 20.0, 48.0, 82.0, 110.0, 138.0)
    elif key.startswith("foot_point_"):
        raw = (-18.0, 0.0, 12.0, 24.0, 42.0)
    else:
        raw = groups.get(key, (spec["default"],))
    candidates = {float(max(spec["min"], min(spec["max"], value))) for value in raw}
    candidates.add(float(max(spec["min"], min(spec["max"], current))))
    candidates.add(float(spec["default"]))
    return tuple(sorted(candidates))


def _apply_seed_overrides(base_settings: Dict[str, Any], seed_name: str, overrides: Dict[str, float]) -> Dict[str, Any]:
    settings = deepcopy(base_settings)
    settings["pose_preset"] = seed_name
    for key, value in overrides.items():
        spec = CONTROL_SPECS[key]
        settings["controls"][key] = max(spec["min"], min(spec["max"], float(value)))
    return settings


def _coarse_fit_pass(
    target_mask: np.ndarray,
    settings: Dict[str, Any],
    anchors: Dict[str, Dict[str, float]] | None = None,
    mode: str = "fit_from_image",
) -> Tuple[float, Dict[str, Any]]:
    best_settings = deepcopy(settings)
    best_score = _fit_score(render_pose_mask(best_settings, *target_mask.shape[::-1]), target_mask, best_settings, anchors, mode)
    for _ in range(2):
        improved = False
        for key in FIT_CONTROL_ORDER:
            current = float(best_settings["controls"].get(key, CONTROL_SPECS[key]["default"]))
            local_best_score = best_score
            local_best_value = current
            for candidate in _coarse_candidates(key, current):
                if abs(candidate - current) < 1e-6:
                    continue
                trial = deepcopy(best_settings)
                trial["controls"][key] = candidate
                score = _fit_score(render_pose_mask(trial, *target_mask.shape[::-1]), target_mask, trial, anchors, mode)
                if score > local_best_score:
                    local_best_score = score
                    local_best_value = candidate
            if abs(local_best_value - current) > 1e-6:
                best_settings["controls"][key] = local_best_value
                best_score = local_best_score
                improved = True
        if not improved:
            break
    return best_score, best_settings


def _fit_single_seed(
    target_mask: np.ndarray,
    seed_name: str,
    base_settings: Dict[str, Any],
    anchors: Dict[str, Dict[str, float]] | None = None,
    mode: str = "fit_from_image",
) -> Tuple[float, Dict[str, Any]]:
    settings = deepcopy(base_settings)
    apply_pose_preset(settings, seed_name)
    best_score, settings = _coarse_fit_pass(target_mask, settings, anchors, mode)

    for step in FIT_STEP_SCHEDULE:
        improved = True
        while improved:
            improved = False
            for key in FIT_CONTROL_KEYS:
                spec = CONTROL_SPECS[key]
                current = float(settings["controls"].get(key, spec["default"]))
                local_best_score = best_score
                local_best_value = current
                for candidate in (current - step, current + step):
                    candidate = max(spec["min"], min(spec["max"], candidate))
                    if abs(candidate - current) < 1e-6:
                        continue
                    trial = deepcopy(settings)
                    trial["controls"][key] = candidate
                    score = _fit_score(render_pose_mask(trial, *target_mask.shape[::-1]), target_mask, trial, anchors, mode)
                    if score > local_best_score:
                        local_best_score = score
                        local_best_value = candidate
                if local_best_value != current:
                    settings["controls"][key] = local_best_value
                    best_score = local_best_score
                    improved = True
    return best_score, settings


def _fit_from_seed_variants(
    target_mask: np.ndarray,
    base_settings: Dict[str, Any],
    anchors: Dict[str, Dict[str, float]] | None = None,
    mode: str = "fit_from_image",
) -> Tuple[float, str, Dict[str, Any]]:
    best_score = -1.0
    best_name = "neutral"
    best_settings = deepcopy(base_settings)

    for seed_name in FIT_PRESET_KEYS:
        score, fitted = _fit_single_seed(target_mask, seed_name, base_settings, anchors, mode)
        if score > best_score:
            best_score = score
            best_name = seed_name
            best_settings = fitted

    for seed_name, overrides in FIT_EXTRA_SEEDS:
        seeded = _apply_seed_overrides(base_settings, seed_name, overrides)
        score, fitted = _coarse_fit_pass(target_mask, seeded, anchors, mode)
        for step in FIT_STEP_SCHEDULE:
            improved = True
            while improved:
                improved = False
                for key in FIT_CONTROL_KEYS:
                    spec = CONTROL_SPECS[key]
                    current = float(fitted["controls"].get(key, spec["default"]))
                    local_best_score = score
                    local_best_value = current
                    for candidate in (current - step, current + step):
                        candidate = max(spec["min"], min(spec["max"], candidate))
                        if abs(candidate - current) < 1e-6:
                            continue
                        trial = deepcopy(fitted)
                        trial["controls"][key] = candidate
                        probe_score = _fit_score(render_pose_mask(trial, *target_mask.shape[::-1]), target_mask, trial, anchors, mode)
                        if probe_score > local_best_score:
                            local_best_score = probe_score
                            local_best_value = candidate
                    if abs(local_best_value - current) > 1e-6:
                        fitted["controls"][key] = local_best_value
                        score = local_best_score
                        improved = True
        if score > best_score:
            best_score = score
            best_name = seed_name
            best_settings = fitted

    return best_score, best_name, best_settings


def blend_pose_settings(base_settings: Dict[str, Any], fitted_settings: Dict[str, Any], strength: float) -> Dict[str, Any]:
    out = deepcopy(base_settings)
    t = max(0.0, min(1.0, float(strength)))
    for key, spec in CONTROL_SPECS.items():
        base_v = float(base_settings["controls"].get(key, spec["default"]))
        fit_v = float(fitted_settings["controls"].get(key, base_v))
        out["controls"][key] = max(spec["min"], min(spec["max"], base_v * (1.0 - t) + fit_v * t))
    out["pose_preset"] = str(fitted_settings.get("pose_preset") or out.get("pose_preset") or "neutral")
    if isinstance(fitted_settings.get("image_fit"), dict):
        out["image_fit"] = deepcopy(fitted_settings["image_fit"])
    return out


def fit_pose_settings_from_image(
    image: np.ndarray,
    base_settings: Dict[str, Any],
    strength: float = 1.0,
    anchors: Dict[str, Dict[str, float]] | None = None,
    mode: str = "fit_from_image",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    target_mask = extract_pose_reference_mask(image, target_size=128)
    if float(target_mask.mean()) < 0.002:
        return deepcopy(base_settings), {"applied": False, "reason": "no_pose_mask"}
    merged_anchors = merge_pose_reference_anchors(target_mask, anchors)

    best_score = -1.0
    best_seed = "neutral"
    best_settings = deepcopy(base_settings)
    best_orientation = "direct"
    fit_targets = [("direct", target_mask), ("mirrored", _flip_mask(target_mask))]
    for orientation, fit_target in fit_targets:
        oriented_anchors = merged_anchors
        if merged_anchors and orientation == "mirrored":
            oriented_anchors = {
                key: {"x": 1.0 - float(entry.get("x", 0.5)), "y": float(entry.get("y", 0.5))}
                for key, entry in merged_anchors.items()
                if isinstance(entry, dict)
            }
        score, seed_name, fitted = _fit_from_seed_variants(fit_target, base_settings, oriented_anchors, mode)
        if score > best_score:
            best_score = score
            best_seed = seed_name
            best_orientation = orientation
            best_settings = fitted

    if best_orientation == "mirrored":
        best_settings = _mirror_pose_sides(best_settings)

    target_frame_hint = _frame_hint(target_mask)
    image_fit_settings = best_settings.get("image_fit") if isinstance(best_settings.get("image_fit"), dict) else {}
    best_settings["image_fit"] = {
        **deepcopy(image_fit_settings),
        "fit_mode": str(mode or "fit_from_image"),
        "frame_hint": target_frame_hint,
    }

    blended = blend_pose_settings(base_settings, best_settings, strength=strength)
    return blended, {
        "applied": True,
        "best_seed": best_seed,
        "fit_orientation": best_orientation,
        "fit_score": round(float(best_score), 4),
        "mask_area_ratio": round(float(target_mask.mean()), 4),
        "fit_mode": str(mode or "fit_from_image"),
        "anchor_count": len(merged_anchors),
        "manual_anchor_count": len(anchors or {}),
        "auto_anchor_count": max(0, len(merged_anchors) - len(anchors or {})),
        "strength": round(float(strength), 3),
        "frame_hint": target_frame_hint,
    }
