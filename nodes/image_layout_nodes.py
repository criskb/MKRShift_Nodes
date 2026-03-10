import json
import math
from typing import Any, Dict, Tuple

import numpy as np
import torch

from ..categories import UTILITY_LAYOUT


_ANCHOR_FACTORS = {
    "top_left": (0.0, 0.0),
    "top": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}


def _to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")
    batch = image.detach().float()
    if batch.ndim == 3:
        batch = batch.unsqueeze(0)
    if batch.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(batch.shape)}")
    if batch.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(batch.shape)}")
    return batch.clamp(0.0, 1.0)


def _json_text(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _resolve_anchor(anchor: str) -> Tuple[float, float]:
    return _ANCHOR_FACTORS.get(str(anchor).lower(), _ANCHOR_FACTORS["center"])


def _safe_pad(
    image: np.ndarray,
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
    mode: str,
    pad_value: float,
) -> np.ndarray:
    if left == 0 and right == 0 and top == 0 and bottom == 0:
        return image

    pad_spec = ((int(top), int(bottom)), (int(left), int(right)), (0, 0))
    mode_key = str(mode or "edge").strip().lower()
    if mode_key == "constant":
        return np.pad(image, pad_spec, mode="constant", constant_values=float(np.clip(pad_value, 0.0, 1.0)))

    try:
        return np.pad(image, pad_spec, mode=mode_key)
    except ValueError:
        return np.pad(image, pad_spec, mode="edge")


def _build_canvas(
    sample: np.ndarray,
    *,
    columns: int,
    rows: int,
    size_mode: str,
    anchor: str,
    pad_mode: str,
    pad_value: float,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    height, width, _ = sample.shape
    ax, ay = _resolve_anchor(anchor)
    mode_key = str(size_mode or "pad").strip().lower()

    if mode_key == "crop" and (width < int(columns) or height < int(rows)):
        raise ValueError("Crop mode requires image width >= columns and image height >= rows")

    if mode_key == "crop":
        tile_width = max(1, int(math.floor(width / float(columns))))
        tile_height = max(1, int(math.floor(height / float(rows))))
    else:
        tile_width = max(1, int(math.ceil(width / float(columns))))
        tile_height = max(1, int(math.ceil(height / float(rows))))

    canvas_width = int(tile_width * int(columns))
    canvas_height = int(tile_height * int(rows))

    if mode_key == "crop":
        extra_x = max(0, int(width) - int(canvas_width))
        extra_y = max(0, int(height) - int(canvas_height))
        crop_x = int(round(extra_x * ax))
        crop_y = int(round(extra_y * ay))
        canvas = sample[crop_y : crop_y + canvas_height, crop_x : crop_x + canvas_width, :]
        meta = {
            "original_width": int(width),
            "original_height": int(height),
            "canvas_width": int(canvas_width),
            "canvas_height": int(canvas_height),
            "content_x": 0,
            "content_y": 0,
            "source_window": [int(crop_x), int(crop_y), int(crop_x + canvas_width), int(crop_y + canvas_height)],
            "tile_width": int(tile_width),
            "tile_height": int(tile_height),
            "size_mode": "crop",
        }
        return canvas.astype(np.float32, copy=False), meta

    extra_x = max(0, int(canvas_width) - int(width))
    extra_y = max(0, int(canvas_height) - int(height))
    left = int(round(extra_x * ax))
    top = int(round(extra_y * ay))
    right = int(extra_x - left)
    bottom = int(extra_y - top)
    canvas = _safe_pad(
        sample,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        mode=str(pad_mode),
        pad_value=float(pad_value),
    )
    meta = {
        "original_width": int(width),
        "original_height": int(height),
        "canvas_width": int(canvas_width),
        "canvas_height": int(canvas_height),
        "content_x": int(left),
        "content_y": int(top),
        "source_window": [0, 0, int(width), int(height)],
        "tile_width": int(tile_width),
        "tile_height": int(tile_height),
        "size_mode": "pad",
    }
    return canvas.astype(np.float32, copy=False), meta


def _parse_split_info(split_info_json: str) -> Dict[str, Any]:
    text = str(split_info_json or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("split_info_json must decode to an object")
    return data


def _normalize_source_window(value: Any, *, fallback_width: int, fallback_height: int) -> Tuple[int, int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            x0 = int(value[0])
            y0 = int(value[1])
            x1 = int(value[2])
            y1 = int(value[3])
        except (TypeError, ValueError):
            x0, y0, x1, y1 = 0, 0, int(fallback_width), int(fallback_height)
    else:
        x0, y0, x1, y1 = 0, 0, int(fallback_width), int(fallback_height)

    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = max(x0 + 1, x1)
    y1 = max(y0 + 1, y1)
    return (int(x0), int(y0), int(x1), int(y1))


def _weight_axis(length: int, overlap: int, mode: str) -> np.ndarray:
    axis = np.ones(int(length), dtype=np.float32)
    if int(overlap) <= 0 or str(mode).lower() in {"average", "center_crop"}:
        return axis
    ramp = (np.arange(int(overlap), dtype=np.float32) + 1.0) / float(int(overlap) + 1)
    axis[: int(overlap)] *= ramp
    axis[-int(overlap) :] *= ramp[::-1]
    return np.clip(axis, 1.0e-4, None)


def _weight_map(full_height: int, full_width: int, tile_height: int, tile_width: int, overlap: int, mode: str) -> np.ndarray:
    mode_key = str(mode or "feather").strip().lower()
    if mode_key == "center_crop" and int(overlap) > 0:
        weight = np.zeros((int(full_height), int(full_width)), dtype=np.float32)
        weight[int(overlap) : int(overlap) + int(tile_height), int(overlap) : int(overlap) + int(tile_width)] = 1.0
        return weight

    y_weight = _weight_axis(int(full_height), int(overlap), mode_key)
    x_weight = _weight_axis(int(full_width), int(overlap), mode_key)
    return np.outer(y_weight, x_weight).astype(np.float32, copy=False)


class MKRImageSplitGrid:
    SEARCH_ALIASES = ["image split", "tile split", "grid split", "image chunks", "tile image"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "columns": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "rows": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "size_mode": (["pad", "crop"], {"default": "pad"}),
                "anchor": (
                    [
                        "center",
                        "top_left",
                        "top",
                        "top_right",
                        "left",
                        "right",
                        "bottom_left",
                        "bottom",
                        "bottom_right",
                    ],
                    {"default": "center"},
                ),
                "overlap_px": ("INT", {"default": 32, "min": 0, "max": 2048, "step": 1}),
                "pad_mode": (["edge", "reflect", "constant"], {"default": "edge"}),
                "pad_value": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("tiles", "split_info_json", "summary")
    FUNCTION = "split"
    CATEGORY = UTILITY_LAYOUT

    def split(
        self,
        image: torch.Tensor,
        columns: int = 2,
        rows: int = 2,
        size_mode: str = "pad",
        anchor: str = "center",
        overlap_px: int = 32,
        pad_mode: str = "edge",
        pad_value: float = 0.0,
    ):
        batch = _to_image_batch(image)
        batch_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        batch_size, height, width, channels = batch_np.shape

        canvas_sample, canvas_meta = _build_canvas(
            batch_np[0],
            columns=int(columns),
            rows=int(rows),
            size_mode=str(size_mode),
            anchor=str(anchor),
            pad_mode=str(pad_mode),
            pad_value=float(pad_value),
        )
        tile_width = int(canvas_meta["tile_width"])
        tile_height = int(canvas_meta["tile_height"])
        canvas_width = int(canvas_meta["canvas_width"])
        canvas_height = int(canvas_meta["canvas_height"])
        overlap = max(0, int(overlap_px))
        full_width = int(tile_width + overlap * 2)
        full_height = int(tile_height + overlap * 2)

        tiles = []
        for index in range(int(batch_size)):
            canvas, current_meta = _build_canvas(
                batch_np[index],
                columns=int(columns),
                rows=int(rows),
                size_mode=str(size_mode),
                anchor=str(anchor),
                pad_mode=str(pad_mode),
                pad_value=float(pad_value),
            )
            if (
                int(current_meta["tile_width"]) != tile_width
                or int(current_meta["tile_height"]) != tile_height
                or int(current_meta["canvas_width"]) != canvas_width
                or int(current_meta["canvas_height"]) != canvas_height
            ):
                raise ValueError("Image batch contains inconsistent dimensions for split_grid")

            expanded = _safe_pad(
                canvas,
                left=overlap,
                right=overlap,
                top=overlap,
                bottom=overlap,
                mode=str(pad_mode),
                pad_value=float(pad_value),
            )
            for row_index in range(int(rows)):
                y0 = int(row_index * tile_height)
                y1 = int(y0 + full_height)
                for column_index in range(int(columns)):
                    x0 = int(column_index * tile_width)
                    x1 = int(x0 + full_width)
                    tiles.append(expanded[y0:y1, x0:x1, :])

        tile_batch = np.stack(tiles, axis=0).astype(np.float32, copy=False)
        split_info = {
            "schema": "mkr_image_split_grid_v1",
            "source_batch": int(batch_size),
            "source_channels": int(channels),
            "rows": int(rows),
            "columns": int(columns),
            "tile_count_per_image": int(rows * columns),
            "tile_width": int(tile_width),
            "tile_height": int(tile_height),
            "tile_full_width": int(full_width),
            "tile_full_height": int(full_height),
            "overlap_px": int(overlap),
            "size_mode": str(canvas_meta["size_mode"]),
            "anchor": str(anchor),
            "pad_mode": str(pad_mode),
            "pad_value": float(np.clip(pad_value, 0.0, 1.0)),
            "original_width": int(width),
            "original_height": int(height),
            "canvas_width": int(canvas_width),
            "canvas_height": int(canvas_height),
            "content_x": int(canvas_meta["content_x"]),
            "content_y": int(canvas_meta["content_y"]),
            "source_window": list(canvas_meta["source_window"]),
        }
        summary = (
            f"Split {int(batch_size)} image(s) into {int(tile_batch.shape[0])} equal tiles "
            f"| {int(columns)}x{int(rows)} grid | core {tile_width}x{tile_height} | overlap {overlap}px"
        )
        return (torch.from_numpy(tile_batch), _json_text(split_info), summary)


class MKRImageCombineGrid:
    SEARCH_ALIASES = ["image combine", "tile combine", "stitch tiles", "grid combine", "rebuild image"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tiles": ("IMAGE",),
                "split_info_json": ("STRING", {"default": "", "multiline": True}),
                "columns": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "rows": ("INT", {"default": 2, "min": 1, "max": 64, "step": 1}),
                "size_mode": (["pad", "crop"], {"default": "pad"}),
                "overlap_px": ("INT", {"default": 32, "min": 0, "max": 2048, "step": 1}),
                "canvas_width": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "canvas_height": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "original_width": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "original_height": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "content_x": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "content_y": ("INT", {"default": 0, "min": 0, "max": 65535, "step": 1}),
                "blend_mode": (["feather", "average", "center_crop"], {"default": "feather"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "combine_info_json", "summary")
    FUNCTION = "combine"
    CATEGORY = UTILITY_LAYOUT

    def combine(
        self,
        tiles: torch.Tensor,
        split_info_json: str = "",
        columns: int = 2,
        rows: int = 2,
        size_mode: str = "pad",
        overlap_px: int = 32,
        canvas_width: int = 0,
        canvas_height: int = 0,
        original_width: int = 0,
        original_height: int = 0,
        content_x: int = 0,
        content_y: int = 0,
        blend_mode: str = "feather",
    ):
        tile_batch = _to_image_batch(tiles)
        meta = _parse_split_info(split_info_json)
        tile_np = tile_batch.detach().cpu().numpy().astype(np.float32, copy=False)
        tile_count, full_height, full_width, channels = tile_np.shape

        columns = int(meta.get("columns", columns))
        rows = int(meta.get("rows", rows))
        size_mode = str(meta.get("size_mode", size_mode))
        overlap = int(meta.get("overlap_px", overlap_px))
        canvas_width = int(meta.get("canvas_width", canvas_width))
        canvas_height = int(meta.get("canvas_height", canvas_height))
        original_width = int(meta.get("original_width", original_width))
        original_height = int(meta.get("original_height", original_height))
        content_x = int(meta.get("content_x", content_x))
        content_y = int(meta.get("content_y", content_y))
        tile_width = int(meta.get("tile_width", max(1, int(full_width) - overlap * 2)))
        tile_height = int(meta.get("tile_height", max(1, int(full_height) - overlap * 2)))
        source_window = _normalize_source_window(
            meta.get("source_window"),
            fallback_width=int(original_width if original_width > 0 else canvas_width),
            fallback_height=int(original_height if original_height > 0 else canvas_height),
        )
        tiles_per_image = int(rows * columns)

        if tiles_per_image <= 0:
            raise ValueError("rows and columns must describe at least one tile")
        if int(tile_count) % tiles_per_image != 0:
            raise ValueError(
                f"Tile batch size {int(tile_count)} is not divisible by rows*columns ({tiles_per_image}) for combine_grid"
            )

        expected_full_width = int(tile_width + overlap * 2)
        expected_full_height = int(tile_height + overlap * 2)
        if int(full_width) != expected_full_width or int(full_height) != expected_full_height:
            raise ValueError(
                "Tile size does not match split metadata. "
                f"Expected {expected_full_width}x{expected_full_height}, got {int(full_width)}x{int(full_height)}."
            )

        if canvas_width <= 0:
            canvas_width = int(tile_width * columns)
        if canvas_height <= 0:
            canvas_height = int(tile_height * rows)
        if original_width <= 0:
            original_width = int(canvas_width)
        if original_height <= 0:
            original_height = int(canvas_height)

        source_batch = int(meta.get("source_batch", int(tile_count) // tiles_per_image))
        if int(source_batch) * tiles_per_image != int(tile_count):
            raise ValueError("split_info_json source_batch does not match the incoming tile batch")

        weights = _weight_map(
            full_height=int(full_height),
            full_width=int(full_width),
            tile_height=int(tile_height),
            tile_width=int(tile_width),
            overlap=int(overlap),
            mode=str(blend_mode),
        )[..., None]

        reconstructed = []
        for batch_index in range(int(source_batch)):
            accum = np.zeros((int(canvas_height), int(canvas_width), int(channels)), dtype=np.float32)
            weight_accum = np.zeros((int(canvas_height), int(canvas_width), 1), dtype=np.float32)
            base_index = int(batch_index * tiles_per_image)

            for tile_index in range(tiles_per_image):
                grid_y = int(tile_index // columns)
                grid_x = int(tile_index % columns)
                start_x = int(grid_x * tile_width - overlap)
                start_y = int(grid_y * tile_height - overlap)
                end_x = int(start_x + full_width)
                end_y = int(start_y + full_height)

                dst_x0 = max(0, start_x)
                dst_y0 = max(0, start_y)
                dst_x1 = min(int(canvas_width), end_x)
                dst_y1 = min(int(canvas_height), end_y)
                if dst_x0 >= dst_x1 or dst_y0 >= dst_y1:
                    continue

                src_x0 = int(dst_x0 - start_x)
                src_y0 = int(dst_y0 - start_y)
                src_x1 = int(src_x0 + (dst_x1 - dst_x0))
                src_y1 = int(src_y0 + (dst_y1 - dst_y0))
                current_tile = tile_np[base_index + tile_index]
                current_weights = weights[src_y0:src_y1, src_x0:src_x1, :]
                accum[dst_y0:dst_y1, dst_x0:dst_x1, :] += current_tile[src_y0:src_y1, src_x0:src_x1, :] * current_weights
                weight_accum[dst_y0:dst_y1, dst_x0:dst_x1, :] += current_weights

            canvas = accum / np.maximum(weight_accum, 1.0e-8)
            if str(size_mode).lower() == "pad":
                crop_x = int(min(max(content_x, 0), max(0, canvas_width - 1)))
                crop_y = int(min(max(content_y, 0), max(0, canvas_height - 1)))
                crop_w = int(min(max(original_width, 1), canvas_width - crop_x))
                crop_h = int(min(max(original_height, 1), canvas_height - crop_y))
                canvas = canvas[crop_y : crop_y + crop_h, crop_x : crop_x + crop_w, :]
            reconstructed.append(np.clip(canvas, 0.0, 1.0))

        output = np.stack(reconstructed, axis=0).astype(np.float32, copy=False)
        combine_info = {
            "schema": "mkr_image_split_grid_v1",
            "source_batch": int(source_batch),
            "rows": int(rows),
            "columns": int(columns),
            "tile_count_per_image": int(tiles_per_image),
            "tile_width": int(tile_width),
            "tile_height": int(tile_height),
            "tile_full_width": int(full_width),
            "tile_full_height": int(full_height),
            "overlap_px": int(overlap),
            "blend_mode": str(blend_mode),
            "size_mode": str(size_mode),
            "canvas_width": int(canvas_width),
            "canvas_height": int(canvas_height),
            "output_width": int(output.shape[2]),
            "output_height": int(output.shape[1]),
            "original_width": int(original_width),
            "original_height": int(original_height),
            "content_x": int(content_x),
            "content_y": int(content_y),
            "source_window": [int(source_window[0]), int(source_window[1]), int(source_window[2]), int(source_window[3])],
        }
        summary = (
            f"Combined {int(tile_count)} tiles into {int(source_batch)} image(s) "
            f"| {int(columns)}x{int(rows)} grid | {str(blend_mode)} blend"
        )
        if str(size_mode).lower() == "crop":
            summary += (
                f" | crop window {int(source_window[0])},{int(source_window[1])}"
                f" -> {int(source_window[2])},{int(source_window[3])}"
            )
        return (torch.from_numpy(output), _json_text(combine_info), summary)
