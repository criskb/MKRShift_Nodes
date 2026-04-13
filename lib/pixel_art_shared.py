import json
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from .host_bridge_shared import clean_text


_BAYER_4X4 = (
    np.asarray(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        dtype=np.float32,
    )
    / 16.0
)


def parse_palette_json(palette_json: str) -> Tuple[List[List[int]], List[str]]:
    text = clean_text(palette_json)
    if not text:
        return ([], [])
    warnings: List[str] = []
    try:
        payload = json.loads(text)
    except Exception:
        return ([], ["palette_json is not valid JSON"])
    if not isinstance(payload, list):
        return ([], ["palette_json must be a JSON array"])

    parsed: List[List[int]] = []
    seen = set()
    for index, item in enumerate(payload):
        rgb = _parse_color_value(item)
        if rgb is None:
            warnings.append(f"palette entry {index} is invalid")
            continue
        key = tuple(rgb)
        if key in seen:
            continue
        seen.add(key)
        parsed.append(list(rgb))
    return (parsed, warnings)


def _parse_color_value(value: Any) -> Tuple[int, int, int] | None:
    if isinstance(value, str):
        token = clean_text(value).lstrip("#")
        if len(token) == 6:
            try:
                return (int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16))
            except ValueError:
                return None
        parts = [part.strip() for part in value.split(",")]
        if len(parts) == 3:
            try:
                nums = [max(0, min(255, int(round(float(part))))) for part in parts]
            except ValueError:
                return None
            return (nums[0], nums[1], nums[2])
        return None
    if isinstance(value, Sequence) and len(value) >= 3:
        try:
            nums = [max(0, min(255, int(round(float(value[idx]))))) for idx in range(3)]
        except Exception:
            return None
        return (nums[0], nums[1], nums[2])
    return None


def uniform_palette(color_count: int) -> np.ndarray:
    count = int(max(2, color_count))
    levels = max(2, int(np.ceil(count ** (1.0 / 3.0))))
    axis = np.linspace(0.0, 1.0, levels, dtype=np.float32)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    if grid.shape[0] <= count:
        return grid.astype(np.float32, copy=False)
    idx = np.linspace(0, grid.shape[0] - 1, count, dtype=np.int32)
    return grid[idx].astype(np.float32, copy=False)


def adaptive_palette(rgb: np.ndarray, color_count: int) -> np.ndarray:
    pixels = np.clip(rgb.reshape(-1, 3), 0.0, 1.0)
    if pixels.shape[0] == 0:
        return uniform_palette(color_count)

    pixels_u8 = np.unique(np.clip(np.round(pixels * 255.0), 0.0, 255.0).astype(np.uint8), axis=0)
    if pixels_u8.shape[0] <= int(color_count):
        return (pixels_u8.astype(np.float32) / 255.0).astype(np.float32, copy=False)

    sample = pixels_u8
    if sample.shape[0] > 4096:
        step = max(1, sample.shape[0] // 4096)
        sample = sample[::step]
    sample_f = (sample.astype(np.float32) / 255.0).astype(np.float32, copy=False)

    init_idx = np.linspace(0, sample_f.shape[0] - 1, int(color_count), dtype=np.int32)
    centers = sample_f[init_idx].copy()
    for _ in range(10):
        dist = np.sum((sample_f[:, None, :] - centers[None, :, :]) ** 2, axis=-1)
        labels = np.argmin(dist, axis=1)
        updated = centers.copy()
        for idx in range(centers.shape[0]):
            members = sample_f[labels == idx]
            if members.shape[0] > 0:
                updated[idx] = np.mean(members, axis=0)
        if np.allclose(updated, centers, atol=1.0e-5):
            centers = updated
            break
        centers = updated
    order = np.argsort(np.dot(centers, np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)))
    return np.clip(centers[order], 0.0, 1.0).astype(np.float32, copy=False)


def nearest_palette_map(
    rgb: np.ndarray,
    palette: np.ndarray,
    *,
    dither_mode: str = "none",
    dither_strength: float = 0.0,
) -> np.ndarray:
    src = np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)
    pal = np.clip(np.asarray(palette, dtype=np.float32), 0.0, 1.0)
    if pal.ndim != 2 or pal.shape[1] != 3:
        raise ValueError("palette must have shape [N,3]")

    work = src
    if str(dither_mode).lower() == "bayer_4x4" and float(dither_strength) > 1.0e-6:
        threshold = (_BAYER_4X4 - 0.5).astype(np.float32, copy=False)
        tiled = np.tile(
            threshold,
            (
                int(np.ceil(src.shape[0] / 4.0)),
                int(np.ceil(src.shape[1] / 4.0)),
            ),
        )[: src.shape[0], : src.shape[1]]
        jitter = tiled[..., None] * float(np.clip(dither_strength, 0.0, 1.0))
        work = np.clip(src + (jitter / max(1.0, float(len(pal)))), 0.0, 1.0).astype(np.float32, copy=False)

    flat = work.reshape(-1, 3)
    dist = np.sum((flat[:, None, :] - pal[None, :, :]) ** 2, axis=-1)
    idx = np.argmin(dist, axis=1)
    return pal[idx].reshape(src.shape).astype(np.float32, copy=False)


def hex_color_to_unit_rgb(value: str, fallback: Tuple[float, float, float]) -> Tuple[float, float, float]:
    parsed = _parse_color_value(value)
    if parsed is None:
        return fallback
    return (parsed[0] / 255.0, parsed[1] / 255.0, parsed[2] / 255.0)


def find_connected_components(mask: np.ndarray, min_pixels: int) -> List[Dict[str, int]]:
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2:
        raise ValueError("mask must be 2D")
    h, w = binary.shape
    visited = np.zeros((h, w), dtype=bool)
    components: List[Dict[str, int]] = []

    for y in range(h):
        for x in range(w):
            if not binary[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            min_y = max_y = y
            min_x = max_x = x
            area = 0

            while stack:
                cy, cx = stack.pop()
                area += 1
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if ny < 0 or nx < 0 or ny >= h or nx >= w:
                        continue
                    if visited[ny, nx] or not binary[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    stack.append((ny, nx))

            if area >= int(max(1, min_pixels)):
                components.append(
                    {
                        "x": int(min_x),
                        "y": int(min_y),
                        "width": int(max_x - min_x + 1),
                        "height": int(max_y - min_y + 1),
                        "area": int(area),
                    }
                )

    return components
