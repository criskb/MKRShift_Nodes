import json
from typing import Any, Dict, List, Tuple

import numpy as np
import torch

from ..categories import UTILITY_PIXEL
from ..lib.image_shared import to_image_batch
from ..lib.pixel_art_shared import (
    adaptive_palette,
    find_connected_components,
    hex_color_to_unit_rgb,
    nearest_palette_map,
    parse_palette_json,
    uniform_palette,
)


def _palette_to_json(palette: np.ndarray) -> List[List[int]]:
    pal = np.clip(np.asarray(palette, dtype=np.float32), 0.0, 1.0)
    return np.clip(np.round(pal * 255.0), 0.0, 255.0).astype(np.uint8).tolist()


class MKRPixelPaletteReduce:
    SEARCH_ALIASES = ["pixel art palette", "indexed color", "palette reduce", "pixel quantize"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette_mode": (["adaptive", "uniform", "custom_json"], {"default": "adaptive"}),
                "color_count": ("INT", {"default": 16, "min": 2, "max": 256, "step": 1}),
                "dither_mode": (["none", "bayer_4x4"], {"default": "none"}),
                "dither_strength": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_alpha": ("BOOLEAN", {"default": True}),
                "palette_json": ("STRING", {"default": "[]", "multiline": True}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "palette_json", "summary_json")
    FUNCTION = "run"
    CATEGORY = UTILITY_PIXEL

    def run(
        self,
        image: torch.Tensor,
        palette_mode: str = "adaptive",
        color_count: int = 16,
        dither_mode: str = "none",
        dither_strength: float = 0.35,
        preserve_alpha: bool = True,
        palette_json: str = "[]",
    ) -> Tuple[torch.Tensor, str, str]:
        batch = to_image_batch(image)
        batch_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        output = np.zeros_like(batch_np, dtype=np.float32)
        warnings: List[str] = []
        frame_palettes: List[Dict[str, Any]] = []

        custom_palette_u8, palette_warnings = parse_palette_json(palette_json)
        warnings.extend(palette_warnings)
        custom_palette = (np.asarray(custom_palette_u8, dtype=np.float32) / 255.0).astype(np.float32, copy=False) if custom_palette_u8 else None

        for idx in range(batch_np.shape[0]):
            sample = batch_np[idx]
            rgb = sample[..., :3]
            alpha = sample[..., 3:4] if sample.shape[-1] == 4 else None

            if str(palette_mode).lower() == "custom_json":
                palette = custom_palette
                if palette is None or palette.shape[0] == 0:
                    warnings.append("custom_json palette_mode requested without valid palette_json; adaptive palette was used")
                    palette = adaptive_palette(rgb, int(color_count))
            elif str(palette_mode).lower() == "uniform":
                palette = uniform_palette(int(color_count))
            else:
                palette = adaptive_palette(rgb, int(color_count))

            mapped = nearest_palette_map(
                rgb,
                palette,
                dither_mode=str(dither_mode),
                dither_strength=float(dither_strength),
            )

            if alpha is not None and bool(preserve_alpha):
                output[idx] = np.concatenate([mapped, alpha], axis=-1).astype(np.float32, copy=False)
            elif output.shape[-1] == 4:
                full_alpha = np.ones_like(rgb[..., :1], dtype=np.float32)
                output[idx] = np.concatenate([mapped, full_alpha], axis=-1).astype(np.float32, copy=False)
            else:
                output[idx] = mapped.astype(np.float32, copy=False)

            unique_colors = np.unique(np.clip(np.round(mapped.reshape(-1, 3) * 255.0), 0.0, 255.0).astype(np.uint8), axis=0)
            frame_palettes.append(
                {
                    "frame": int(idx),
                    "color_count": int(unique_colors.shape[0]),
                    "colors": unique_colors.tolist(),
                }
            )

        summary = {
            "palette_mode": str(palette_mode).lower(),
            "target_color_count": int(color_count),
            "dither_mode": str(dither_mode).lower(),
            "preserve_alpha": bool(preserve_alpha),
            "warnings": warnings,
            "frames": frame_palettes,
        }
        exported_palette = frame_palettes[0]["colors"] if frame_palettes else []
        return (
            torch.from_numpy(np.clip(output, 0.0, 1.0).astype(np.float32, copy=False)),
            json.dumps(exported_palette, ensure_ascii=False, indent=2),
            json.dumps(summary, ensure_ascii=False, indent=2),
        )


class MKRSpriteSheetExtract:
    SEARCH_ALIASES = ["extract sprites", "sprite atlas extract", "pixel art atlas", "shoebox sprite extract"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["alpha", "color_key"], {"default": "alpha"}),
                "alpha_threshold": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "key_color": ("STRING", {"default": "#ff00ff"}),
                "key_threshold": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01}),
                "min_sprite_pixels": ("INT", {"default": 4, "min": 1, "max": 4096, "step": 1}),
                "padding": ("INT", {"default": 1, "min": 0, "max": 64, "step": 1}),
                "sort_mode": (["top_left", "left_to_right", "area_desc"], {"default": "top_left"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("sprites", "sprite_map_json", "summary_json")
    FUNCTION = "run"
    CATEGORY = UTILITY_PIXEL

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "alpha",
        alpha_threshold: float = 0.05,
        key_color: str = "#ff00ff",
        key_threshold: float = 0.08,
        min_sprite_pixels: int = 4,
        padding: int = 1,
        sort_mode: str = "top_left",
    ) -> Tuple[torch.Tensor, str, str]:
        batch = to_image_batch(image)
        batch_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        sprites: List[np.ndarray] = []
        records: List[Dict[str, Any]] = []
        warnings: List[str] = []
        key_rgb = np.asarray(hex_color_to_unit_rgb(key_color, (1.0, 0.0, 1.0)), dtype=np.float32)

        for frame_index in range(batch_np.shape[0]):
            sample = batch_np[frame_index]
            rgb = np.clip(sample[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
            alpha = sample[..., 3] if sample.shape[-1] == 4 else np.ones(sample.shape[:2], dtype=np.float32)

            if str(source_mode).lower() == "color_key":
                dist = np.sqrt(np.sum((rgb - key_rgb[None, None, :]) ** 2, axis=-1))
                mask = dist > float(max(0.0, key_threshold))
            else:
                if sample.shape[-1] == 4:
                    mask = alpha > float(alpha_threshold)
                else:
                    mask = np.max(rgb, axis=-1) > float(alpha_threshold)

            components = find_connected_components(mask, int(min_sprite_pixels))
            if str(sort_mode).lower() == "left_to_right":
                components.sort(key=lambda item: (item["x"], item["y"]))
            elif str(sort_mode).lower() == "area_desc":
                components.sort(key=lambda item: (-item["area"], item["y"], item["x"]))
            else:
                components.sort(key=lambda item: (item["y"], item["x"]))

            for sprite_index, item in enumerate(components):
                x0 = max(0, int(item["x"]))
                y0 = max(0, int(item["y"]))
                x1 = min(rgb.shape[1], x0 + int(item["width"]))
                y1 = min(rgb.shape[0], y0 + int(item["height"]))

                rgba = np.concatenate([rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1, None]], axis=-1).astype(np.float32, copy=False)
                pad = int(max(0, padding))
                if pad > 0:
                    rgba = np.pad(rgba, ((pad, pad), (pad, pad), (0, 0)), mode="constant", constant_values=0.0)

                sprites.append(rgba.astype(np.float32, copy=False))
                records.append(
                    {
                        "frame": int(frame_index),
                        "sprite_index": int(sprite_index),
                        "x": int(x0),
                        "y": int(y0),
                        "width": int(x1 - x0),
                        "height": int(y1 - y0),
                        "area": int(item["area"]),
                        "padding": int(pad),
                    }
                )

        if not sprites:
            warnings.append("no sprites were detected; returning a transparent 1x1 placeholder")
            sprites = [np.zeros((1, 1, 4), dtype=np.float32)]

        max_h = max(sprite.shape[0] for sprite in sprites)
        max_w = max(sprite.shape[1] for sprite in sprites)
        sprite_batch = np.zeros((len(sprites), max_h, max_w, 4), dtype=np.float32)
        for idx, sprite in enumerate(sprites):
            h, w = sprite.shape[:2]
            sprite_batch[idx, :h, :w, :] = sprite

        sprite_map = {
            "count": int(len(records)),
            "sprites": records,
            "batch_tile_height": int(max_h),
            "batch_tile_width": int(max_w),
        }
        summary = {
            "source_mode": str(source_mode).lower(),
            "count": int(len(records)),
            "sort_mode": str(sort_mode).lower(),
            "padding": int(max(0, padding)),
            "warnings": warnings,
        }
        return (
            torch.from_numpy(np.clip(sprite_batch, 0.0, 1.0).astype(np.float32, copy=False)),
            json.dumps(sprite_map, ensure_ascii=False, indent=2),
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
