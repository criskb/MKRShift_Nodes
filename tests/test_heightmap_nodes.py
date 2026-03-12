import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.heatmap_nodes import x1Heightmap  # noqa: E402


class HeightmapNodeTests(unittest.TestCase):
    def test_heightmap_luma_outputs_grayscale_ramp(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 1, 32, 1)
        image = ramp.repeat(1, 20, 1, 3)

        node = x1Heightmap()
        output, mask, info = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
        )

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1]))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2]))
        self.assertLess(float(mask[0, 0, 0].item()), float(mask[0, 0, -1].item()))
        self.assertIn("x1Heightmap", info)

    def test_heightmap_source_mask_mode_uses_source_mask(self) -> None:
        image = torch.zeros((1, 18, 18, 3), dtype=torch.float32)
        source_mask = torch.linspace(0.0, 1.0, 18, dtype=torch.float32).view(1, 1, 18).repeat(1, 18, 1)

        node = x1Heightmap()
        output, mask, _ = node.run(
            image=image,
            source_mode="mask",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            source_mask=source_mask,
        )

        self.assertAlmostEqual(float(mask[0, 0, 0].item()), 0.0, places=4)
        self.assertGreater(float(mask[0, 0, -1].item()), 0.9)
        self.assertGreater(float(output[0, 0, -1, 0].item()), float(output[0, 0, 0, 0].item()))

    def test_heightmap_blur_softens_hard_edge(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[:, :, 12:, :] = 1.0

        node = x1Heightmap()
        sharp_out, _, _ = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            blur_radius=0.0,
        )
        blur_out, _, _ = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            blur_radius=2.0,
        )

        self.assertLess(float(sharp_out[0, 12, 11, 0].item()), 0.01)
        self.assertGreater(float(blur_out[0, 12, 11, 0].item()), 0.05)

    def test_heightmap_output_mask_limits_emission(self) -> None:
        image = torch.ones((1, 20, 20, 3), dtype=torch.float32)
        mask = torch.zeros((1, 20, 20), dtype=torch.float32)
        mask[:, 5:15, 5:15] = 1.0

        node = x1Heightmap()
        output, out_mask, _ = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            blur_radius=0.0,
            mask=mask,
            mask_feather=0.0,
        )

        self.assertEqual(float(output[0, 0, 0, 0].item()), 0.0)
        self.assertGreater(float(output[0, 10, 10, 0].item()), 0.9)
        self.assertEqual(float(out_mask[0, 0, 0].item()), 0.0)


if __name__ == "__main__":
    unittest.main()
