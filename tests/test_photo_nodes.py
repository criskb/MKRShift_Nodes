import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xphoto import x1FlashPop, x1OrtonGlow, x1PhotoMatte, x1VignettePro  # noqa: E402


class PhotoNodeTests(unittest.TestCase):
    def test_vignette_pro_darkens_edges_more_than_center(self) -> None:
        image = torch.ones((1, 64, 64, 3), dtype=torch.float32)
        image *= torch.tensor([0.80, 0.72, 0.66], dtype=torch.float32)

        node = x1VignettePro()
        out, mask, info = node.run(
            image=image,
            amount=0.55,
            midpoint=0.52,
            feather=0.28,
            roundness=0.82,
            center_x=0.50,
            center_y=0.50,
            highlight_protect=0.10,
            saturation_shift=-0.04,
            mix=1.0,
            mask_feather=0.0,
        )

        center_luma = float(torch.mean(out[:, 28:36, 28:36, :]).item())
        edge_luma = float(torch.mean(torch.cat([
            out[:, :8, :, :].reshape(1, -1, 3),
            out[:, -8:, :, :].reshape(1, -1, 3),
        ], dim=1)).item())

        self.assertLess(edge_luma, center_luma)
        self.assertLess(float(mask[0, 32, 32].item()), float(mask[0, 2, 2].item()))
        self.assertIn("x1VignettePro", info)

    def test_orton_glow_spreads_bright_regions(self) -> None:
        image = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        image[:, 26:38, 26:38, :] = torch.tensor([0.95, 0.90, 0.84], dtype=torch.float32)

        node = x1OrtonGlow()
        out, mask, info = node.run(
            image=image,
            blur_radius=16.0,
            glow_strength=0.70,
            contrast_softness=0.26,
            detail_preserve=0.40,
            highlight_bias=0.42,
            black_lift=0.04,
            mix=1.0,
            mask_feather=0.0,
        )

        source_ring = float(torch.mean(image[:, 22:26, 22:26, :]).item())
        output_ring = float(torch.mean(out[:, 22:26, 22:26, :]).item())

        self.assertGreater(output_ring, source_ring + 0.002)
        self.assertGreater(float(mask[0, 32, 32].item()), float(mask[0, 4, 4].item()))
        self.assertIn("x1OrtonGlow", info)

    def test_flash_pop_brightens_center_more_than_edges(self) -> None:
        image = torch.full((1, 64, 64, 3), 0.24, dtype=torch.float32)
        image[:, 20:44, 20:44, :] = torch.tensor([0.38, 0.36, 0.34], dtype=torch.float32)

        node = x1FlashPop()
        out, mask, info = node.run(
            image=image,
            amount=0.62,
            edge_falloff=0.44,
            center_x=0.50,
            center_y=0.50,
            shadow_lift=0.42,
            highlight_rolloff=0.18,
            warmth=0.10,
            clarity=0.20,
            mix=1.0,
            mask_feather=0.0,
        )

        center_mean = float(torch.mean(out[:, 28:36, 28:36, :]).item())
        edge_mean = float(torch.mean(out[:, :8, :, :]).item())

        self.assertGreater(center_mean, edge_mean + 0.04)
        self.assertGreater(float(mask[0, 32, 32].item()), float(mask[0, 3, 3].item()))
        self.assertIn("x1FlashPop", info)

    def test_photo_matte_lifts_blacks_and_softens_highlights(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 64, dtype=torch.float32)
        image = ramp.view(1, 1, 64, 1).repeat(1, 64, 1, 3)

        node = x1PhotoMatte()
        out, mask, info = node.run(
            image=image,
            black_lift=0.14,
            white_compress=0.18,
            contrast_softness=0.28,
            saturation_soften=0.18,
            warmth=0.06,
            mix=1.0,
            mask_feather=0.0,
        )

        self.assertGreater(float(torch.mean(out[:, :, :6, :]).item()), float(torch.mean(image[:, :, :6, :]).item()))
        self.assertLess(float(torch.mean(out[:, :, -6:, :]).item()), float(torch.mean(image[:, :, -6:, :]).item()) + 0.005)
        self.assertGreater(float(mask.mean().item()), 0.01)
        self.assertIn("x1PhotoMatte", info)


if __name__ == "__main__":
    unittest.main()
