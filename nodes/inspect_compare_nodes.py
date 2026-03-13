import json
import math
from typing import Any, Dict, List

import numpy as np
from PIL import Image, ImageDraw
import torch

from ..categories import INSPECT_COMPARE
from .preview_nodes import (
    _comfy_batch_to_pil_list,
    _draw_label_with_separator_accent,
    _fit_tile,
    _fit_font_to_width,
    _load_font,
    _pil_to_comfy_image,
    _resolve_palette,
    _text_size,
)


def _safe_resize_for_preview(image: Image.Image, max_side: int) -> Image.Image:
    cap = int(max(0, max_side))
    if cap <= 0:
        return image
    width, height = image.size
    if max(width, height) <= cap:
        return image
    scale = float(cap) / float(max(width, height))
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, resample=Image.Resampling.LANCZOS)


def _difference_image(image_a: Image.Image, image_b: Image.Image, style: str, gain: float) -> Dict[str, Any]:
    arr_a = np.asarray(image_a.convert("RGB"), dtype=np.float32) / 255.0
    arr_b = np.asarray(image_b.convert("RGB"), dtype=np.float32) / 255.0
    delta = np.abs(arr_a - arr_b)
    magnitude = np.clip(delta.mean(axis=2) * float(max(0.05, gain)), 0.0, 1.0)

    if str(style or "heat").strip().lower() == "gray":
        preview = np.repeat(magnitude[..., None], 3, axis=2)
    else:
        peak = np.clip(delta.max(axis=2) * 1.15, 0.0, 1.0)
        preview = np.stack(
            (
                np.clip(magnitude * 1.2 + peak * 0.35, 0.0, 1.0),
                np.clip(np.sqrt(magnitude) * 0.92, 0.0, 1.0),
                np.clip(magnitude * 0.16, 0.0, 1.0),
            ),
            axis=2,
        )

    diff_image = Image.fromarray(np.round(preview * 255.0).astype(np.uint8), mode="RGB")
    return {
        "image": diff_image,
        "mean_delta": float(magnitude.mean()),
        "peak_delta": float(magnitude.max()),
    }


class MKRBatchDifferencePreview:
    SEARCH_ALIASES = [
        "batch difference preview",
        "difference sheet",
        "delta preview",
        "compare grid diff",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
            },
            "optional": {
                "columns": ("INT", {"default": 0, "min": 0, "max": 32, "step": 1}),
                "layout_mode": (["A | B | Diff", "A | Diff", "Diff Only"], {"default": "A | B | Diff"}),
                "difference_style": (["heat", "gray"], {"default": "heat"}),
                "difference_gain": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 8.0, "step": 0.05}),
                "tile_fit_mode": (["contain", "crop", "stretch"], {"default": "contain"}),
                "panel_padding": ("INT", {"default": 14, "min": 4, "max": 96, "step": 1}),
                "panel_gap": ("INT", {"default": 18, "min": 0, "max": 128, "step": 1}),
                "label_height": ("INT", {"default": 44, "min": 20, "max": 160, "step": 1}),
                "show_resolution": ("BOOLEAN", {"default": True}),
                "theme": (["dark", "light", "studio"], {"default": "dark"}),
                "max_collage_side": ("INT", {"default": 0, "min": 0, "max": 32768, "step": 64}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image_out", "difference_preview", "layout_json")
    FUNCTION = "run"
    CATEGORY = INSPECT_COMPARE

    def run(
        self,
        image_a: torch.Tensor,
        image_b: torch.Tensor,
        columns: int = 0,
        layout_mode: str = "A | B | Diff",
        difference_style: str = "heat",
        difference_gain: float = 2.0,
        tile_fit_mode: str = "contain",
        panel_padding: int = 14,
        panel_gap: int = 18,
        label_height: int = 44,
        show_resolution: bool = True,
        theme: str = "dark",
        max_collage_side: int = 0,
    ):
        batch_a = _comfy_batch_to_pil_list(image_a)
        batch_b = _comfy_batch_to_pil_list(image_b)
        if not batch_a or not batch_b:
            blank = Image.new("RGB", (256, 256), (0, 0, 0))
            return (image_a, _pil_to_comfy_image(blank), json.dumps({"schema": "mkr_batch_difference_preview_v1", "count": 0}))

        pair_count = min(len(batch_a), len(batch_b))
        warnings: List[str] = []
        if len(batch_a) != len(batch_b):
            warnings.append("image_a and image_b batch counts differ; using shortest batch")

        slot_w = max(max(im.size[0] for im in batch_a[:pair_count]), max(im.size[0] for im in batch_b[:pair_count]))
        slot_h = max(max(im.size[1] for im in batch_a[:pair_count]), max(im.size[1] for im in batch_b[:pair_count]))
        tile_keys = ["A", "B", "DIFF"]
        mode = str(layout_mode or "A | B | Diff").strip()
        if mode == "A | Diff":
            tile_keys = ["A", "DIFF"]
        elif mode == "Diff Only":
            tile_keys = ["DIFF"]

        columns_used = int(columns or 0)
        if columns_used <= 0:
            columns_used = max(1, int(math.ceil(math.sqrt(pair_count))))
        columns_used = max(1, min(columns_used, pair_count))
        rows_used = int(math.ceil(float(pair_count) / float(columns_used)))

        gap = max(0, int(panel_gap))
        pad = max(4, int(panel_padding))
        label_h = max(20, int(label_height))
        palette = _resolve_palette(theme)

        panel_inner_w = (slot_w * len(tile_keys)) + (gap * max(0, len(tile_keys) - 1))
        panel_w = panel_inner_w + (pad * 2)
        panel_h = slot_h + label_h + (pad * 2)
        sheet_w = (pad * 2) + (columns_used * panel_w) + (gap * max(0, columns_used - 1))
        sheet_h = (pad * 2) + (rows_used * panel_h) + (gap * max(0, rows_used - 1))

        sheet = Image.new("RGB", (sheet_w, sheet_h), palette["bg"])
        draw = ImageDraw.Draw(sheet)
        label_font = _load_font(max(11, int(label_h * 0.34)))
        chip_font = _fit_font_to_width(draw, "DIFF", max(26, slot_w // 3), preferred_size=max(12, int(slot_h * 0.08)), min_size=10)
        rows_meta: List[Dict[str, Any]] = []

        for idx in range(pair_count):
            row = idx // columns_used
            col = idx % columns_used
            panel_x = pad + col * (panel_w + gap)
            panel_y = pad + row * (panel_h + gap)
            panel_box = (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h)

            draw.rounded_rectangle(panel_box, radius=max(16, pad), fill=palette["tile_bg"])
            a_fit = _fit_tile(batch_a[idx], slot_w, slot_h, palette["tile_bg"], tile_fit_mode)
            b_fit = _fit_tile(batch_b[idx], slot_w, slot_h, palette["tile_bg"], tile_fit_mode)
            diff_meta = _difference_image(a_fit, b_fit, difference_style, difference_gain)
            diff_fit = diff_meta["image"]

            panel_tiles = {
                "A": a_fit,
                "B": b_fit,
                "DIFF": diff_fit,
            }
            for tile_index, key in enumerate(tile_keys):
                tile_x = panel_x + pad + tile_index * (slot_w + gap)
                tile_y = panel_y + pad
                tile_box = (tile_x, tile_y, tile_x + slot_w, tile_y + slot_h)
                draw.rounded_rectangle(tile_box, radius=12, fill=palette["label_bg"])
                sheet.paste(panel_tiles[key], (tile_x, tile_y))
                draw.rounded_rectangle(tile_box, radius=12, outline=palette["label_sep"], width=1)

                chip_w, chip_h = _text_size(draw, key, chip_font)
                chip_box = (
                    tile_x + 8,
                    tile_y + 8,
                    tile_x + chip_w + 22,
                    tile_y + chip_h + 16,
                )
                draw.rounded_rectangle(chip_box, radius=10, fill=palette["label_bg"])
                draw.text((chip_box[0] + 8, chip_box[1] + 4), key, font=chip_font, fill=palette["label_fg"])

            label_y = panel_y + pad + slot_h + max(4, (label_h - _text_size(draw, "PAIR", label_font)[1]) // 2)
            delta_label = f"PAIR {idx + 1:02d} | mean {diff_meta['mean_delta']:.3f}"
            if bool(show_resolution):
                delta_label += f" | {slot_w}x{slot_h}"
            _draw_label_with_separator_accent(
                draw,
                panel_x + pad,
                label_y,
                delta_label,
                label_font,
                palette["label_fg"],
                palette["label_sep"],
            )

            rows_meta.append(
                {
                    "index": idx + 1,
                    "source_a_size": [batch_a[idx].size[0], batch_a[idx].size[1]],
                    "source_b_size": [batch_b[idx].size[0], batch_b[idx].size[1]],
                    "slot_size": [slot_w, slot_h],
                    "mean_delta": round(float(diff_meta["mean_delta"]), 6),
                    "peak_delta": round(float(diff_meta["peak_delta"]), 6),
                }
            )

        preview = _safe_resize_for_preview(sheet, max_collage_side)
        metadata = {
            "schema": "mkr_batch_difference_preview_v1",
            "count": pair_count,
            "columns": columns_used,
            "rows": rows_used,
            "layout_mode": mode,
            "difference_style": difference_style,
            "difference_gain": float(difference_gain),
            "preview_size": [preview.size[0], preview.size[1]],
            "sheet_size": [sheet.size[0], sheet.size[1]],
            "rows_meta": rows_meta,
            "warnings": warnings,
        }
        return (image_a, _pil_to_comfy_image(preview), json.dumps(metadata, ensure_ascii=False, indent=2))
