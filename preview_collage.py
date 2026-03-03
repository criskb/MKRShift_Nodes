import json
import math
import re
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

from .categories import INSPECT_PREVIEW

MKRSHIFT_ACCENT_GREEN = (210, 253, 81)  # #d2fd51
MKRSHIFT_COLLAGE_FOOTER = "MADE WITH COMFYUI | MKRSHIFT NODES | XY:PRE"


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    return default


def _first_value(value, default):
    current = value
    while True:
        if isinstance(current, (list, tuple)):
            if not current:
                return default
            current = current[0]
            continue

        if torch.is_tensor(current):
            if current.numel() < 1:
                return default
            if current.numel() == 1:
                try:
                    return current.detach().cpu().item()
                except Exception:
                    return default
            current = current.detach().cpu().reshape(-1)[0]
            continue

        if isinstance(current, np.ndarray):
            if current.size < 1:
                return default
            if current.size == 1:
                try:
                    return current.reshape(-1)[0].item()
                except Exception:
                    return default
            current = current.reshape(-1)[0]
            continue

        return current


def _pil_to_comfy_image(img: Image.Image) -> torch.Tensor:
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _pil_list_to_comfy_batch(images: List[Image.Image]) -> torch.Tensor:
    if not images:
        blank = np.zeros((1, 64, 64, 3), dtype=np.float32)
        return torch.from_numpy(blank)
    arr = np.stack([np.array(im.convert("RGB"), dtype=np.float32) / 255.0 for im in images], axis=0)
    return torch.from_numpy(arr)


def _comfy_batch_to_pil_list(image: torch.Tensor) -> List[Image.Image]:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")

    t = image.detach().cpu().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor with 4 dims [B,H,W,C], got shape={tuple(t.shape)}")

    if t.shape[-1] == 4:
        t = t[..., :3]
    if t.shape[-1] != 3:
        raise ValueError(f"Expected IMAGE tensor channel dimension 3 or 4, got shape={tuple(t.shape)}")

    t = t.clamp(0.0, 1.0)
    arr = (t.numpy() * 255.0).astype(np.uint8)
    return [Image.fromarray(sample, mode="RGB") for sample in arr]


def _load_font(size: int) -> ImageFont.ImageFont:
    px = max(11, int(size))
    try:
        return ImageFont.truetype("DejaVuSans.ttf", px)
    except Exception:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return max(0, right - left), max(0, bottom - top)
    except Exception:
        try:
            width, height = draw.textsize(text, font=font)
            return int(width), int(height)
        except Exception:
            return (len(text) * 7, 12)


def _draw_label_with_separator_accent(
    draw: ImageDraw.ImageDraw,
    text_x: int,
    text_y: int,
    label: str,
    font: ImageFont.ImageFont,
    label_color: Tuple[int, int, int],
    separator_color: Tuple[int, int, int],
) -> None:
    parts = [part for part in re.split(r"(\|)", str(label or "")) if part]
    if not parts:
        return

    cursor_x = int(text_x)
    for part in parts:
        color = separator_color if part == "|" else label_color
        draw.text(
            (cursor_x, text_y),
            part,
            font=font,
            fill=color,
        )
        part_w, _ = _text_size(draw, part, font)
        cursor_x += part_w


def _text_x_for_alignment(
    box_x: int,
    box_w: int,
    text_w: int,
    align: str,
    pad: int = 10,
) -> int:
    mode = str(align or "left").strip().lower()
    if mode == "center":
        return box_x + max(0, (box_w - text_w) // 2)
    if mode == "right":
        return box_x + max(0, box_w - text_w - max(0, int(pad)))
    return box_x + max(0, int(pad))


def _fit_font_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    preferred_size: int,
    min_size: int = 9,
) -> ImageFont.ImageFont:
    size = max(min_size, int(preferred_size))
    while size >= min_size:
        font = _load_font(size)
        text_w, _ = _text_size(draw, text, font)
        if text_w <= max_w:
            return font
        size -= 1
    return _load_font(min_size)


def _fit_contain(image: Image.Image, target_w: int, target_h: int, fill: Tuple[int, int, int]) -> Image.Image:
    src = image.convert("RGB")
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (target_w, target_h), fill)
    if sw == target_w and sh == target_h:
        return src

    scale = min(float(target_w) / float(sw), float(target_h) / float(sh))
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), resample=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), fill)
    dx = (target_w - nw) // 2
    dy = (target_h - nh) // 2
    canvas.paste(resized, (dx, dy))
    return canvas


def _fit_cover(image: Image.Image, target_w: int, target_h: int, fill: Tuple[int, int, int]) -> Image.Image:
    src = image.convert("RGB")
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (target_w, target_h), fill)
    if sw == target_w and sh == target_h:
        return src

    scale = max(float(target_w) / float(sw), float(target_h) / float(sh))
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), resample=Image.Resampling.LANCZOS)

    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _fit_stretch(image: Image.Image, target_w: int, target_h: int, fill: Tuple[int, int, int]) -> Image.Image:
    src = image.convert("RGB")
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (target_w, target_h), fill)
    if sw == target_w and sh == target_h:
        return src
    return src.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)


def _fit_tile(
    image: Image.Image,
    target_w: int,
    target_h: int,
    fill: Tuple[int, int, int],
    mode: str,
) -> Image.Image:
    fit_mode = str(mode or "contain").strip().lower()
    if fit_mode == "crop":
        return _fit_cover(image, target_w, target_h, fill)
    if fit_mode == "stretch":
        return _fit_stretch(image, target_w, target_h, fill)
    return _fit_contain(image, target_w, target_h, fill)


def _resize_to_height(image: Image.Image, target_h: int, fill: Tuple[int, int, int]) -> Image.Image:
    src = image.convert("RGB")
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (max(1, target_h), max(1, target_h)), fill)
    if sh == target_h:
        return src
    scale = float(target_h) / float(sh)
    nw = max(1, int(round(sw * scale)))
    return src.resize((nw, target_h), resample=Image.Resampling.LANCZOS)


def _resolve_palette(theme: str) -> Dict[str, Tuple[int, int, int]]:
    key = str(theme or "dark").strip().lower()
    if key == "light":
        return {
            "bg": (246, 247, 250),
            "tile_bg": (233, 235, 240),
            "label_bg": (224, 228, 236),
            "label_fg": (26, 34, 45),
            "label_sep": MKRSHIFT_ACCENT_GREEN,
        }
    if key == "studio":
        return {
            "bg": (0, 0, 0),
            "tile_bg": (31, 31, 31),
            "label_bg": (0, 0, 0),
            "label_fg": (220, 220, 220),
            "label_sep": MKRSHIFT_ACCENT_GREEN,
        }
    return {
        "bg": (12, 14, 20),
        "tile_bg": (20, 24, 32),
        "label_bg": (5, 7, 10),
        "label_fg": (228, 235, 248),
        "label_sep": MKRSHIFT_ACCENT_GREEN,
    }


def _build_labels(count: int, prefix: str, start_index: int, index_padding: int) -> List[str]:
    safe_prefix = (prefix or "img").strip() or "img"
    pad = max(1, min(int(index_padding), 8))
    return [f"{safe_prefix}_{start_index + i:0{pad}d}" for i in range(count)]


def _collect_custom_labels(value) -> List[str]:
    out: List[str] = []
    stack = [value]
    while stack:
        item = stack.pop(0)
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            stack[0:0] = list(item)
            continue
        if torch.is_tensor(item):
            if item.numel() < 1:
                continue
            if item.numel() == 1:
                try:
                    item = item.detach().cpu().item()
                except Exception:
                    continue
            else:
                stack[0:0] = item.detach().cpu().reshape(-1).tolist()
                continue
        if isinstance(item, np.ndarray):
            if item.size < 1:
                continue
            if item.size == 1:
                try:
                    item = item.reshape(-1)[0].item()
                except Exception:
                    continue
            else:
                stack[0:0] = item.reshape(-1).tolist()
                continue

        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        stack[0:0] = parsed
                        continue
                except Exception:
                    pass
            if "\n" in text:
                for part in text.splitlines():
                    token = part.strip()
                    if token:
                        out.append(token)
                continue
            out.append(text)
            continue

        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _flatten_input_images(image_input) -> List[Image.Image]:
    stack = [image_input]
    out: List[Image.Image] = []
    while stack:
        item = stack.pop(0)
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            stack[0:0] = list(item)
            continue
        if isinstance(item, Image.Image):
            out.append(item.convert("RGB"))
            continue
        if torch.is_tensor(item):
            out.extend(_comfy_batch_to_pil_list(item))
            continue
        raise TypeError(f"Unsupported image input type: {type(item)}")
    return out


class MKRBatchCollagePreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            },
            "optional": {
                "columns": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
                "x_count": ("INT", {"default": 0, "min": 0, "max": 256, "step": 1}),
                "layout_order": (["row_major", "column_major"], {"default": "row_major"}),
                "tile_fit_mode": (["contain", "crop", "stretch"], {"default": "contain"}),
                "Compact view": ("BOOLEAN", {"default": False}),
                "tile_padding": ("INT", {"default": 12, "min": 0, "max": 256, "step": 1}),
                "outer_padding": ("INT", {"default": 20, "min": 0, "max": 256, "step": 1}),
                "label_height": ("INT", {"default": 34, "min": 0, "max": 256, "step": 1}),
                "label_align": (["left", "center", "right"], {"default": "left"}),
                "label_prefix": ("STRING", {"default": "img"}),
                "labels": ("STRING", {"default": "", "multiline": True}),
                "start_index": ("INT", {"default": 1, "min": 0, "max": 1000000, "step": 1}),
                "index_padding": ("INT", {"default": 2, "min": 1, "max": 8, "step": 1}),
                "show_resolution": ("BOOLEAN", {"default": True}),
                "show_xy_labels": ("BOOLEAN", {"default": False}),
                "x_prefix": ("STRING", {"default": "x"}),
                "y_prefix": ("STRING", {"default": "y"}),
                "x_start": ("INT", {"default": 0, "min": -1000000, "max": 1000000, "step": 1}),
                "y_start": ("INT", {"default": 0, "min": -1000000, "max": 1000000, "step": 1}),
                "x_step": ("INT", {"default": 1, "min": -100000, "max": 100000, "step": 1}),
                "y_step": ("INT", {"default": 1, "min": -100000, "max": 100000, "step": 1}),
                "theme": (["dark", "light", "studio"], {"default": "dark"}),
                "max_collage_side": ("INT", {"default": 0, "min": 0, "max": 32768, "step": 64}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("image_out", "collage_image", "layout_json")
    FUNCTION = "run"
    INPUT_IS_LIST = True
    CATEGORY = INSPECT_PREVIEW

    def run(
        self,
        image,
        columns: int = 0,
        x_count: int = 0,
        layout_order: str = "row_major",
        tile_fit_mode: str = "contain",
        compact_view: bool = False,
        tile_padding: int = 12,
        outer_padding: int = 20,
        label_height: int = 34,
        label_align: str = "left",
        label_prefix: str = "img",
        labels: str = "",
        start_index: int = 1,
        index_padding: int = 2,
        show_resolution: bool = True,
        show_xy_labels: bool = False,
        x_prefix: str = "x",
        y_prefix: str = "y",
        x_start: int = 0,
        y_start: int = 0,
        x_step: int = 1,
        y_step: int = 1,
        theme: str = "dark",
        max_collage_side: int = 0,
        **kwargs,
    ):
        resolved_cols = _safe_int(_first_value(columns, 0), 0)
        resolved_x_count = _safe_int(_first_value(x_count, 0), 0)
        resolved_order = str(_first_value(layout_order, "row_major") or "row_major").strip().lower()
        if resolved_order not in {"row_major", "column_major"}:
            resolved_order = "row_major"
        resolved_tile_fit = str(_first_value(tile_fit_mode, "contain") or "contain").strip().lower()
        if resolved_tile_fit not in {"contain", "crop", "stretch"}:
            resolved_tile_fit = "contain"
        resolved_compact_view = _safe_bool(
            _first_value(kwargs.get("Compact view", kwargs.get("compact_view", compact_view)), compact_view),
            compact_view,
        )
        resolved_gap = _safe_int(_first_value(tile_padding, 12), 12)
        resolved_edge = _safe_int(_first_value(outer_padding, 20), 20)
        resolved_label_h = _safe_int(_first_value(label_height, 34), 34)
        resolved_label_align = str(_first_value(label_align, "left") or "left").strip().lower()
        if resolved_label_align not in {"left", "center", "right"}:
            resolved_label_align = "left"
        resolved_prefix = str(_first_value(label_prefix, "img") or "img")
        custom_labels = _collect_custom_labels(labels)
        resolved_start = _safe_int(_first_value(start_index, 1), 1)
        resolved_idx_pad = _safe_int(_first_value(index_padding, 2), 2)
        resolved_show_res = _safe_bool(_first_value(show_resolution, True), True)
        resolved_show_xy_labels = _safe_bool(_first_value(show_xy_labels, False), False)
        resolved_x_prefix = str(_first_value(x_prefix, "x") or "x").strip() or "x"
        resolved_y_prefix = str(_first_value(y_prefix, "y") or "y").strip() or "y"
        resolved_x_start = _safe_int(_first_value(x_start, 0), 0)
        resolved_y_start = _safe_int(_first_value(y_start, 0), 0)
        resolved_x_step = _safe_int(_first_value(x_step, 1), 1)
        resolved_y_step = _safe_int(_first_value(y_step, 1), 1)
        resolved_theme = str(_first_value(theme, "dark") or "dark")
        resolved_max_side = _safe_int(_first_value(max_collage_side, 0), 0)

        tiles = _flatten_input_images(image)
        if not tiles:
            blank = Image.new("RGB", (256, 256), (0, 0, 0))
            metadata = {"schema": "mkr_batch_collage_preview_v1", "count": 0}
            return (_pil_to_comfy_image(blank), _pil_to_comfy_image(blank), json.dumps(metadata, ensure_ascii=False))

        count = len(tiles)
        requested_cols = resolved_x_count if resolved_x_count > 0 else resolved_cols
        if requested_cols <= 0:
            cols = max(1, int(math.ceil(math.sqrt(count))))
        else:
            cols = max(1, min(requested_cols, count))
        rows = int(math.ceil(float(count) / float(cols)))

        gap = max(0, resolved_gap)
        edge = max(0, resolved_edge)
        label_h = max(0, resolved_label_h)
        palette = _resolve_palette(resolved_theme)

        base_labels = _build_labels(count, resolved_prefix, resolved_start, resolved_idx_pad)
        resolved_labels: List[str] = ["" for _ in range(count)]
        placement_rows: List[int] = [0 for _ in range(count)]
        placement_cols: List[int] = [0 for _ in range(count)]
        for idx in range(count):
            if resolved_order == "column_major":
                col = idx // rows
                row = idx % rows
            else:
                row = idx // cols
                col = idx % cols
            placement_rows[idx] = row
            placement_cols[idx] = col

        def _compose_label(idx: int) -> str:
            row = placement_rows[idx]
            col = placement_cols[idx]
            tile = tiles[idx]

            if idx < len(custom_labels) and str(custom_labels[idx]).strip():
                base_label = str(custom_labels[idx]).strip()
            else:
                base_label = base_labels[idx]
            if resolved_show_xy_labels:
                x_val = resolved_x_start + col * resolved_x_step
                y_val = resolved_y_start + row * resolved_y_step
                xy_label = f"{resolved_x_prefix}{x_val} {resolved_y_prefix}{y_val}"
                label = f"{base_label}  |  {xy_label}"
            else:
                label = base_label
            if resolved_show_res:
                label = f"{label}  |  {tile.size[0]}x{tile.size[1]}"
            resolved_labels[idx] = label
            return label

        font = _load_font(max(12, int(label_h * 0.46)))

        if resolved_compact_view:
            tile_h = max(1, max(im.size[1] for im in tiles))
            row_items: List[List[Tuple[int, int, Image.Image]]] = [[] for _ in range(rows)]
            for idx, tile in enumerate(tiles):
                fitted = _resize_to_height(tile, tile_h, palette["tile_bg"])
                row = placement_rows[idx]
                col = placement_cols[idx]
                row_items[row].append((col, idx, fitted))

            row_widths: List[int] = []
            for row in range(rows):
                row_items[row].sort(key=lambda entry: entry[0])
                widths = [item[2].size[0] for item in row_items[row]]
                row_w = sum(widths) + max(0, len(widths) - 1) * gap
                row_widths.append(max(1, row_w))

            inner_w = max(row_widths) if row_widths else 1
            sheet_w = edge * 2 + inner_w
            sheet_h = edge * 2 + rows * (tile_h + label_h) + max(0, rows - 1) * gap
            sheet = Image.new("RGB", (sheet_w, sheet_h), palette["bg"])
            draw = ImageDraw.Draw(sheet)

            for row in range(rows):
                y = edge + row * (tile_h + label_h + gap)
                row_w = row_widths[row]
                x_cursor = edge + max(0, (inner_w - row_w) // 2)
                for _, idx, fitted in row_items[row]:
                    fw, fh = fitted.size
                    sheet.paste(fitted, (x_cursor, y))
                    label = _compose_label(idx)
                    if label_h > 0:
                        draw.rectangle([x_cursor, y + fh, x_cursor + fw, y + fh + label_h], fill=palette["label_bg"])
                        text_w, text_h = _text_size(draw, label, font)
                        text_x = _text_x_for_alignment(x_cursor, fw, text_w, resolved_label_align, pad=10)
                        text_y = y + fh + max(0, (label_h - text_h) // 2)
                        _draw_label_with_separator_accent(
                            draw,
                            text_x,
                            text_y,
                            label,
                            font,
                            palette["label_fg"],
                            palette["label_sep"],
                        )
                    x_cursor += fw + gap
        else:
            tile_w = max(1, max(im.size[0] for im in tiles))
            tile_h = max(1, max(im.size[1] for im in tiles))
            sheet_w = edge * 2 + cols * tile_w + max(0, cols - 1) * gap
            sheet_h = edge * 2 + rows * (tile_h + label_h) + max(0, rows - 1) * gap
            sheet = Image.new("RGB", (sheet_w, sheet_h), palette["bg"])
            draw = ImageDraw.Draw(sheet)

            for idx, tile in enumerate(tiles):
                row = placement_rows[idx]
                col = placement_cols[idx]
                x = edge + col * (tile_w + gap)
                y = edge + row * (tile_h + label_h + gap)

                fitted = _fit_tile(tile, tile_w, tile_h, palette["tile_bg"], resolved_tile_fit)
                sheet.paste(fitted, (x, y))
                label = _compose_label(idx)
                if label_h > 0:
                    draw.rectangle([x, y + tile_h, x + tile_w, y + tile_h + label_h], fill=palette["label_bg"])
                    text_w, text_h = _text_size(draw, label, font)
                    text_x = _text_x_for_alignment(x, tile_w, text_w, resolved_label_align, pad=10)
                    text_y = y + tile_h + max(0, (label_h - text_h) // 2)
                    _draw_label_with_separator_accent(
                        draw,
                        text_x,
                        text_y,
                        label,
                        font,
                        palette["label_fg"],
                        palette["label_sep"],
                    )

        # Add a centered footer line below the collage area.
        footer_gap = 8
        footer_pad_y = 8
        footer_draw = ImageDraw.Draw(sheet)
        footer_font = _fit_font_to_width(
            footer_draw,
            MKRSHIFT_COLLAGE_FOOTER,
            max(20, sheet.size[0] - 20),
            preferred_size=max(11, int(label_h * 0.42) if label_h > 0 else 13),
            min_size=9,
        )
        footer_text_w, footer_text_h = _text_size(footer_draw, MKRSHIFT_COLLAGE_FOOTER, footer_font)
        footer_h = footer_gap + footer_pad_y * 2 + footer_text_h
        if footer_h > 0:
            base_h = sheet.size[1]
            with_footer = Image.new("RGB", (sheet.size[0], base_h + footer_h), palette["bg"])
            with_footer.paste(sheet, (0, 0))
            footer_draw = ImageDraw.Draw(with_footer)
            footer_x = _text_x_for_alignment(0, with_footer.size[0], footer_text_w, "center", pad=0)
            footer_y = base_h + footer_gap + footer_pad_y
            _draw_label_with_separator_accent(
                footer_draw,
                footer_x,
                footer_y,
                MKRSHIFT_COLLAGE_FOOTER,
                footer_font,
                palette["label_fg"],
                palette["label_sep"],
            )
            sheet = with_footer

        max_side = max(0, resolved_max_side)
        resized = False
        scale = 1.0
        if max_side > 0:
            longest = max(sheet.size)
            if longest > max_side:
                scale = float(max_side) / float(longest)
                out_w = max(1, int(round(sheet.size[0] * scale)))
                out_h = max(1, int(round(sheet.size[1] * scale)))
                sheet = sheet.resize((out_w, out_h), resample=Image.Resampling.LANCZOS)
                resized = True

        tile_size_meta = [tile_w, tile_h] if not resolved_compact_view else [0, tile_h]
        metadata = {
            "schema": "mkr_batch_collage_preview_v1",
            "count": count,
            "columns": cols,
            "rows": rows,
            "layout_order": resolved_order,
            "tile_fit_mode": resolved_tile_fit,
            "compact_view": resolved_compact_view,
            "label_mode": "index_plus_xy" if resolved_show_xy_labels else "index",
            "start_index": resolved_start,
            "index_padding": resolved_idx_pad,
            "custom_labels_count": len(custom_labels),
            "x_prefix": resolved_x_prefix,
            "y_prefix": resolved_y_prefix,
            "x_start": resolved_x_start,
            "y_start": resolved_y_start,
            "x_step": resolved_x_step,
            "y_step": resolved_y_step,
            "tile_size": tile_size_meta,
            "sheet_size": [sheet.size[0], sheet.size[1]],
            "label_height": label_h,
            "label_align": resolved_label_align,
            "theme": resolved_theme,
            "resized_to_max_side": resized,
            "resize_scale": round(scale, 6),
            "labels": resolved_labels,
        }

        # Regular image output: include labels and avoid contain bars by using cover fit.
        image_out_w = max(1, int(tiles[0].size[0]))
        image_out_h = max(1, int(tiles[0].size[1]))
        image_out_tiles: List[Image.Image] = []
        for idx, tile in enumerate(tiles):
            fitted = _fit_cover(tile, image_out_w, image_out_h, palette["tile_bg"])
            label = resolved_labels[idx] if idx < len(resolved_labels) else _compose_label(idx)

            if label_h > 0:
                out = Image.new("RGB", (image_out_w, image_out_h + label_h), palette["label_bg"])
                out.paste(fitted, (0, 0))
                out_draw = ImageDraw.Draw(out)
                text_w, text_h = _text_size(out_draw, label, font)
                text_x = _text_x_for_alignment(0, image_out_w, text_w, resolved_label_align, pad=10)
                text_y = image_out_h + max(0, (label_h - text_h) // 2)
                _draw_label_with_separator_accent(
                    out_draw,
                    text_x,
                    text_y,
                    label,
                    font,
                    palette["label_fg"],
                    palette["label_sep"],
                )
                image_out_tiles.append(out)
            else:
                image_out_tiles.append(fitted)

        image_out = _pil_list_to_comfy_batch(image_out_tiles)

        # Collage output is always one single IMAGE frame.
        collage_image = _pil_to_comfy_image(sheet)
        return (image_out, collage_image, json.dumps(metadata, ensure_ascii=False))
