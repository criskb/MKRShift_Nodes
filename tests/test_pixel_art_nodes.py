import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.pixel_art_nodes import MKRPixelPaletteReduce, MKRSpriteSheetExtract  # noqa: E402


class PixelArtNodeTests(unittest.TestCase):
    def test_pixel_palette_reduce_limits_colors_and_preserves_alpha(self) -> None:
        image = torch.tensor(
            [
                [
                    [[1.0, 0.0, 0.0, 1.0], [0.9, 0.1, 0.1, 1.0], [0.0, 1.0, 0.0, 1.0], [0.0, 0.9, 0.1, 1.0]],
                    [[0.0, 0.0, 1.0, 1.0], [0.1, 0.1, 0.9, 1.0], [1.0, 1.0, 0.0, 1.0], [0.95, 0.95, 0.1, 1.0]],
                    [[1.0, 0.0, 1.0, 0.0], [0.8, 0.2, 0.8, 0.0], [0.0, 1.0, 1.0, 1.0], [0.1, 0.8, 0.8, 1.0]],
                    [[0.2, 0.2, 0.2, 1.0], [0.8, 0.8, 0.8, 1.0], [0.4, 0.4, 0.4, 1.0], [0.6, 0.6, 0.6, 1.0]],
                ]
            ],
            dtype=torch.float32,
        )

        node = MKRPixelPaletteReduce()
        output, palette_json, summary_json = node.run(
            image=image,
            palette_mode="adaptive",
            color_count=4,
            dither_mode="none",
            preserve_alpha=True,
        )

        palette = json.loads(palette_json)
        summary = json.loads(summary_json)
        unique = torch.unique(torch.round(output[0, ..., :3] * 255.0).to(torch.int32).reshape(-1, 3), dim=0)

        self.assertLessEqual(int(unique.shape[0]), 4)
        self.assertEqual(float(output[0, 2, 0, 3].item()), 0.0)
        self.assertEqual(len(palette), summary["frames"][0]["color_count"])
        self.assertEqual(summary["palette_mode"], "adaptive")

    def test_pixel_palette_reduce_supports_custom_palette(self) -> None:
        image = torch.tensor(
            [[[[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]], [[0.1, 0.1, 0.8], [0.8, 0.8, 0.1]]]],
            dtype=torch.float32,
        )
        node = MKRPixelPaletteReduce()
        output, palette_json, summary_json = node.run(
            image=image,
            palette_mode="custom_json",
            color_count=4,
            dither_mode="none",
            palette_json='["#000000", "#ffffff", "#ff0000"]',
        )

        palette = {tuple(color) for color in json.loads(palette_json)}
        summary = json.loads(summary_json)
        unique = torch.unique(torch.round(output[0, ..., :3] * 255.0).to(torch.int32).reshape(-1, 3), dim=0)
        self.assertTrue(all(tuple(color.tolist()) in palette for color in unique))
        self.assertEqual(summary["warnings"], [])

    def test_sprite_sheet_extract_finds_alpha_sprites(self) -> None:
        image = torch.zeros((1, 10, 14, 4), dtype=torch.float32)
        image[:, 1:4, 1:4, 0] = 1.0
        image[:, 1:4, 1:4, 3] = 1.0
        image[:, 5:8, 8:12, 1] = 1.0
        image[:, 5:8, 8:12, 3] = 1.0

        node = MKRSpriteSheetExtract()
        sprites, sprite_map_json, summary_json = node.run(
            image=image,
            source_mode="alpha",
            alpha_threshold=0.1,
            min_sprite_pixels=3,
            padding=1,
            sort_mode="top_left",
        )

        sprite_map = json.loads(sprite_map_json)
        summary = json.loads(summary_json)
        self.assertEqual(tuple(sprites.shape), (2, 5, 6, 4))
        self.assertEqual(sprite_map["count"], 2)
        self.assertEqual(sprite_map["sprites"][0]["x"], 1)
        self.assertEqual(sprite_map["sprites"][1]["x"], 8)
        self.assertEqual(summary["count"], 2)

    def test_sprite_sheet_extract_supports_color_key_background(self) -> None:
        image = torch.ones((1, 8, 8, 3), dtype=torch.float32)
        image[..., 0] = 1.0
        image[..., 1] = 0.0
        image[..., 2] = 1.0
        image[:, 2:6, 2:6, :] = torch.tensor([0.1, 0.8, 0.2], dtype=torch.float32)

        node = MKRSpriteSheetExtract()
        sprites, sprite_map_json, summary_json = node.run(
            image=image,
            source_mode="color_key",
            key_color="#ff00ff",
            key_threshold=0.02,
            min_sprite_pixels=4,
            padding=0,
        )

        sprite_map = json.loads(sprite_map_json)
        summary = json.loads(summary_json)
        self.assertEqual(sprite_map["count"], 1)
        self.assertEqual(tuple(sprites.shape), (1, 4, 4, 4))
        self.assertAlmostEqual(float(torch.mean(sprites[0, :, :, 3]).item()), 1.0, places=4)
        self.assertEqual(summary["warnings"], [])


if __name__ == "__main__":
    unittest.main()
