import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.texture_tool_nodes import (  # noqa: E402
    x1TextureEdgePad,
    x1TextureOffset,
    x1TextureSeamless,
    x1TextureTilePreview,
)


class TextureToolNodeTests(unittest.TestCase):
    def test_texture_offset_half_tile_moves_content_and_marks_seam(self) -> None:
        image = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        image[:, :, :2, :] = 1.0

        node = x1TextureOffset()
        output, mask, info = node.run(image=image, mode="half_tile", seam_width=1.0)

        self.assertGreater(float(torch.mean(output[:, :, 4:6, :]).item()), 0.9)
        self.assertGreater(float(mask[0, 4, 4].item()), 0.5)
        self.assertIn("x1TextureOffset", info)

    def test_texture_seamless_reduces_edge_mismatch(self) -> None:
        x = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 1, 32, 1)
        y = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 32, 1, 1)
        image = torch.cat(
            [
                x.repeat(1, 32, 1, 1),
                y.repeat(1, 1, 32, 1),
                torch.full((1, 32, 32, 1), 0.25, dtype=torch.float32),
            ],
            dim=-1,
        )

        base_delta = float(torch.mean(torch.abs(image[:, :, 0, :] - image[:, :, -1, :])).item())
        node = x1TextureSeamless()
        output, mask, info = node.run(
            image=image,
            blend_width=10.0,
            edge_match_strength=1.0,
            edge_match_blur=10.0,
            detail_preserve=0.5,
            seam_blur=8.0,
        )
        out_delta = float(torch.mean(torch.abs(output[:, :, 0, :] - output[:, :, -1, :])).item())

        self.assertLess(out_delta, base_delta)
        self.assertGreater(float(mask[0, 0, 0].item()), 0.4)
        self.assertIn("x1TextureSeamless", info)

    def test_texture_tile_preview_repeats_pattern(self) -> None:
        image = torch.tensor(
            [[[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0], [1.0, 1.0, 0.0]]]],
            dtype=torch.float32,
        )

        node = x1TextureTilePreview()
        output, mask, info = node.run(image=image, tiles_x=2, tiles_y=3, show_seams=False, seam_width=1.0)

        self.assertEqual(tuple(output.shape), (1, 6, 4, 3))
        self.assertTrue(torch.allclose(output[:, :2, :2, :], output[:, 2:4, :2, :], atol=1e-5))
        self.assertGreater(float(mask[0, 2, 1].item()), 0.3)
        self.assertIn("x1TextureTilePreview", info)

    def test_texture_edge_pad_fills_transparent_neighbors(self) -> None:
        image = torch.zeros((1, 9, 9, 4), dtype=torch.float32)
        image[:, 4, 4, :3] = torch.tensor([0.8, 0.2, 0.1], dtype=torch.float32)
        image[:, 4, 4, 3] = 1.0

        node = x1TextureEdgePad()
        output, mask, info = node.run(
            image=image,
            source_mode="alpha",
            pad_pixels=2,
            alpha_threshold=0.5,
            expand_alpha=True,
        )

        self.assertGreater(float(torch.mean(output[:, 3:6, 3:6, 0]).item()), 0.1)
        self.assertGreater(float(mask[0, 4, 5].item()), 0.5)
        self.assertGreater(float(output[0, 4, 5, 3].item()), 0.5)
        self.assertIn("x1TextureEdgePad", info)


if __name__ == "__main__":
    unittest.main()
