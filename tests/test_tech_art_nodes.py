import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.tech_art_nodes import (  # noqa: E402
    x1ChannelBreakout,
    x1ChannelPack,
    x1CurvatureFromNormal,
    x1NormalBlend,
    x1UVCheckerOverlay,
)


class TechArtNodeTests(unittest.TestCase):
    def test_channel_pack_and_breakout_roundtrip(self) -> None:
        red = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        red[..., :] = 0.2
        green_mask = torch.ones((1, 8, 8), dtype=torch.float32) * 0.4
        blue = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        blue[..., :] = 0.8
        alpha_mask = torch.ones((1, 8, 8), dtype=torch.float32) * 0.6

        pack_node = x1ChannelPack()
        packed, info = pack_node.run(
            output_mode="rgba",
            fill_missing=0.0,
            red_image=red,
            green_mask=green_mask,
            blue_image=blue,
            alpha_mask=alpha_mask,
        )

        breakout_node = x1ChannelBreakout()
        _, _, _, _, red_mask, green_out, blue_mask, alpha_out, breakout_info = breakout_node.run(
            image=packed,
            alpha_fallback="zero",
        )

        self.assertAlmostEqual(float(red_mask[0, 0, 0].item()), 0.2, places=3)
        self.assertAlmostEqual(float(green_out[0, 0, 0].item()), 0.4, places=3)
        self.assertAlmostEqual(float(blue_mask[0, 0, 0].item()), 0.8, places=3)
        self.assertAlmostEqual(float(alpha_out[0, 0, 0].item()), 0.6, places=3)
        self.assertIn("x1ChannelPack", info)
        self.assertIn("x1ChannelBreakout", breakout_info)

    def test_normal_blend_changes_masked_region(self) -> None:
        base = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        base[..., 0] = 0.5
        base[..., 1] = 0.5
        base[..., 2] = 1.0

        detail = base.clone()
        detail[:, :, 8:, 0] = 0.8
        detail[:, :, 8:, 1] = 0.3

        mask = torch.zeros((1, 16, 16), dtype=torch.float32)
        mask[:, :, 8:] = 1.0

        node = x1NormalBlend()
        output, matte, info = node.run(
            base_normal=base,
            detail_normal=detail,
            blend_mode="whiteout",
            strength=1.0,
            mask=mask,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(output[:, :, :8, :], base[:, :, :8, :], atol=1e-5))
        self.assertGreater(float(torch.mean(torch.abs(output[:, :, 10:, :] - base[:, :, 10:, :])).item()), 0.01)
        self.assertLess(float(matte[0, 4, 4].item()), 1e-5)
        self.assertGreater(float(matte[0, 4, 12].item()), 0.9)
        self.assertIn("x1NormalBlend", info)

    def test_curvature_from_normal_detects_surface_change(self) -> None:
        x = torch.linspace(0.0, 1.0, 32, dtype=torch.float32)
        nx = torch.sin((x - 0.5) * 3.14159).view(1, 1, 32).repeat(1, 32, 1)
        ny = torch.zeros_like(nx)
        nz = torch.sqrt(torch.clamp(1.0 - (nx * nx), min=0.0))
        normal = torch.stack([(nx * 0.5) + 0.5, (ny * 0.5) + 0.5, (nz * 0.5) + 0.5], dim=-1)

        node = x1CurvatureFromNormal()
        output, mask, info = node.run(
            image=normal,
            mode="combined",
            normalize_mode="auto_range",
            blur_radius=0.0,
            strength=2.0,
            gamma=1.0,
            mask_feather=0.0,
        )

        center_value = float(mask[0, 16, 16].item())
        edge_value = float(mask[0, 16, 1].item())

        self.assertGreater(center_value, edge_value)
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertIn("x1CurvatureFromNormal", info)

    def test_uv_checker_overlay_generates_pattern(self) -> None:
        image = torch.ones((1, 16, 16, 3), dtype=torch.float32) * 0.5

        node = x1UVCheckerOverlay()
        output, mask, info = node.run(
            image=image,
            mode="generate",
            palette="uv",
            cells_x=4,
            cells_y=4,
            line_width=1.0,
            mix=1.0,
            mask_feather=0.0,
        )

        self.assertGreater(float(torch.mean(torch.abs(output[:, 1:3, 1:3, :] - output[:, 1:3, 5:7, :])).item()), 0.05)
        self.assertGreater(float(mask[0, 4, 4].item()), 0.5)
        self.assertIn("x1UVCheckerOverlay", info)


if __name__ == "__main__":
    unittest.main()
