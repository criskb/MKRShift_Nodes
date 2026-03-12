import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.tech_art_surface_nodes import x1AOFromHeight, x1IDMapQuantize, x1IDMaskExtract, x1NormalTweak, x1SlopeMaskFromNormal  # noqa: E402


class TechArtSurfaceNodeTests(unittest.TestCase):
    def test_id_mask_extract_isolates_manual_target_color(self) -> None:
        image = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        image[:, :, :8, :] = torch.tensor([0.95, 0.10, 0.10], dtype=torch.float32)
        image[:, :, 8:, :] = torch.tensor([0.10, 0.85, 0.20], dtype=torch.float32)

        node = x1IDMaskExtract()
        output, mask, info = node.run(
            image=image,
            selection_mode="manual_color",
            color_space="rgb",
            target_r=0.95,
            target_g=0.10,
            target_b=0.10,
            tolerance=0.08,
            softness=0.02,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        self.assertGreater(float(mask[0, 8, 4].item()), 0.9)
        self.assertLess(float(mask[0, 8, 12].item()), 0.1)
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertIn("x1IDMaskExtract", info)

    def test_normal_tweak_scales_masked_strength_and_converts_convention(self) -> None:
        normal = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        normal[..., 0] = 0.5
        normal[..., 1] = 0.65
        normal[..., 2] = 0.95

        strength_mask = torch.zeros((1, 16, 16), dtype=torch.float32)
        strength_mask[:, :, 8:] = 1.0

        node = x1NormalTweak()
        output, mask, info = node.run(
            image=normal,
            strength=2.5,
            blur_radius=0.0,
            input_convention="opengl",
            output_convention="directx",
            strength_mask=strength_mask,
            mask_feather=0.0,
        )

        left_green = float(output[0, 8, 4, 1].item())
        right_green = float(output[0, 8, 12, 1].item())

        self.assertAlmostEqual(float(mask[0, 8, 4].item()), 0.0, places=4)
        self.assertGreater(float(mask[0, 8, 12].item()), 0.9)
        self.assertLess(right_green, left_green)
        self.assertIn("x1NormalTweak", info)

    def test_slope_mask_from_normal_tracks_requested_axis(self) -> None:
        normal = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        normal[..., 0] = 0.5
        normal[..., 1] = 0.5
        normal[..., 2] = 1.0
        normal[:, :, 8:, 0] = 1.0
        normal[:, :, 8:, 2] = 0.5

        node = x1SlopeMaskFromNormal()
        output, mask, info = node.run(image=normal, mode="+x", strength=1.0, gamma=1.0, mask_feather=0.0)

        self.assertLess(float(mask[0, 8, 4].item()), 0.05)
        self.assertGreater(float(mask[0, 8, 12].item()), 0.6)
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertIn("x1SlopeMaskFromNormal", info)

    def test_ao_from_height_darkens_valleys(self) -> None:
        image = torch.ones((1, 32, 32, 3), dtype=torch.float32) * 0.7
        image[:, 10:22, 10:22, :] = 0.2

        node = x1AOFromHeight()
        output, mask, info = node.run(
            image=image,
            source_mode="luma",
            output_mode="ao",
            normalize_mode="auto_range",
            radius=4.0,
            intensity=2.5,
            gamma=1.0,
            mask_feather=0.0,
        )

        self.assertLess(float(mask[0, 16, 16].item()), float(mask[0, 4, 4].item()))
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertIn("x1AOFromHeight", info)

    def test_id_map_quantize_outputs_region_edges(self) -> None:
        image = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        image[:, :, :8, :] = torch.tensor([0.9, 0.2, 0.2], dtype=torch.float32)
        image[:, :, 8:, :] = torch.tensor([0.2, 0.8, 0.3], dtype=torch.float32)

        node = x1IDMapQuantize()
        output, mask, info = node.run(
            image=image,
            color_space="rgb",
            levels=3,
            palette_mode="id_vivid",
            smoothing=0.0,
            edge_softness=0.0,
            mask_feather=0.0,
        )

        left_color = output[0, 8, 4, :3]
        right_color = output[0, 8, 12, :3]

        self.assertGreater(float(torch.mean(torch.abs(left_color - right_color)).item()), 0.1)
        self.assertGreater(float(mask[0, 8, 8].item()), 0.5)
        self.assertIn("x1IDMapQuantize", info)


if __name__ == "__main__":
    unittest.main()
