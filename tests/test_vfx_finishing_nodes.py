import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.vfx_finishing_nodes import x1AnamorphicStreaks, x1HeatHaze  # noqa: E402


class VfxFinishingNodeTests(unittest.TestCase):
    def test_anamorphic_streaks_respect_orientation(self) -> None:
        image = torch.zeros((1, 33, 65, 3), dtype=torch.float32)
        image[0, 16, 32] = 1.0

        node = x1AnamorphicStreaks()
        _, horizontal_mask, _ = node.run(
            image=image,
            orientation="horizontal",
            threshold=0.5,
            softness=0.05,
            length_px=36.0,
            strength=1.0,
            mix=1.0,
        )
        _, vertical_mask, _ = node.run(
            image=image,
            orientation="vertical",
            threshold=0.5,
            softness=0.05,
            length_px=36.0,
            strength=1.0,
            mix=1.0,
        )

        h_mask = horizontal_mask[0]
        v_mask = vertical_mask[0]
        horizontal_row = float(h_mask[16].sum().item())
        horizontal_col = float(h_mask[:, 32].sum().item())
        vertical_row = float(v_mask[16].sum().item())
        vertical_col = float(v_mask[:, 32].sum().item())

        self.assertGreater(horizontal_row, horizontal_col * 1.2)
        self.assertGreater(vertical_col, vertical_row * 1.2)

    def test_heat_haze_bypasses_at_zero_strength(self) -> None:
        x = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 1, 48, 1)
        image = x.repeat(1, 32, 1, 3)

        node = x1HeatHaze()
        output, mask, info = node.run(
            image=image,
            direction="up",
            strength_px=0.0,
            scale=3.0,
            phase_deg=0.0,
            chroma_split_px=0.0,
            mix=1.0,
        )

        self.assertTrue(torch.allclose(output, image))
        self.assertEqual(float(mask.max().item()), 0.0)
        self.assertIn("bypassed", info)

    def test_heat_haze_distorts_gradient_image(self) -> None:
        y = torch.linspace(0.0, 1.0, 40, dtype=torch.float32).view(1, 40, 1, 1)
        x = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 1, 64, 1)
        image = torch.cat((x.repeat(1, 40, 1, 1), y.repeat(1, 1, 64, 1), ((x + y) * 0.5)), dim=-1)

        node = x1HeatHaze()
        output, mask, info = node.run(
            image=image,
            direction="up",
            strength_px=10.0,
            scale=4.0,
            phase_deg=45.0,
            chroma_split_px=1.2,
            mix=1.0,
        )

        mean_diff = float(torch.mean(torch.abs(output - image)).item())
        self.assertGreater(mean_diff, 0.001)
        self.assertGreater(float(mask.mean().item()), 0.05)
        self.assertIn("x1HeatHaze", info)


if __name__ == "__main__":
    unittest.main()
