import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.heatmap_nodes import x1Heatmap  # noqa: E402


class HeatmapNodeTests(unittest.TestCase):
    def test_heatmap_luma_generates_colorized_output(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 1, 48, 1)
        image = ramp.repeat(1, 24, 1, 3)

        node = x1Heatmap()
        output, mask, info = node.run(
            image=image,
            source_mode="luma",
            palette="inferno",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            overlay_opacity=1.0,
        )

        self.assertGreater(float(torch.mean(torch.abs(output - image)).item()), 0.01)
        self.assertLess(float(mask[0, 0, 0].item()), float(mask[0, 0, -1].item()))
        self.assertIn("x1Heatmap", info)

    def test_heatmap_source_mask_mode_uses_source_mask(self) -> None:
        image = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        source_mask = torch.linspace(0.0, 1.0, 16, dtype=torch.float32).view(1, 1, 16).repeat(1, 16, 1)

        node = x1Heatmap()
        _, mask, _ = node.run(
            image=image,
            source_mode="mask",
            palette="viridis",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            overlay_opacity=1.0,
            source_mask=source_mask,
        )

        self.assertAlmostEqual(float(mask[0, 0, 0].item()), 0.0, places=4)
        self.assertGreater(float(mask[0, 0, -1].item()), 0.9)

    def test_heatmap_effect_mask_limits_application(self) -> None:
        image = torch.ones((1, 32, 32, 3), dtype=torch.float32) * 0.4
        image[:, :, 16:, :] = 0.9
        effect_mask = torch.zeros((1, 32, 32), dtype=torch.float32)
        effect_mask[:, 8:24, 8:24] = 1.0

        node = x1Heatmap()
        output, mask, _ = node.run(
            image=image,
            source_mode="luma",
            palette="turbo",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            overlay_opacity=1.0,
            effect_mask=effect_mask,
            mask_feather=0.0,
        )

        outside_diff = float(torch.mean(torch.abs(output[:, :6, :6, :] - image[:, :6, :6, :])).item())
        inside_diff = float(torch.mean(torch.abs(output[:, 12:20, 12:20, :] - image[:, 12:20, 12:20, :])).item())

        self.assertLess(outside_diff, 1e-5)
        self.assertGreater(inside_diff, 0.01)
        self.assertEqual(float(mask[0, 0, 0].item()), 0.0)

    def test_heatmap_auto_percentile_and_palette_variation(self) -> None:
        image = torch.linspace(0.0, 1.0, 1 * 20 * 20 * 3, dtype=torch.float32).reshape(1, 20, 20, 3)

        node = x1Heatmap()
        out_a, _, _ = node.run(
            image=image,
            source_mode="value",
            palette="plasma",
            normalize_mode="auto_percentile",
            percentile_low=5.0,
            percentile_high=95.0,
            gamma=1.0,
            overlay_opacity=1.0,
        )
        out_b, _, _ = node.run(
            image=image,
            source_mode="value",
            palette="icefire",
            normalize_mode="auto_percentile",
            percentile_low=5.0,
            percentile_high=95.0,
            gamma=1.0,
            overlay_opacity=1.0,
        )

        self.assertGreater(float(torch.mean(torch.abs(out_a - out_b)).item()), 0.01)


if __name__ == "__main__":
    unittest.main()
