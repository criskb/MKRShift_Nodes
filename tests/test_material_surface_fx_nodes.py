import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.material_surface_fx_nodes import (  # noqa: E402
    x1SurfaceDustMask,
    x1SurfaceRustBloomMask,
    x1SurfaceStreakMask,
    x1SurfaceWaterlineMask,
)


class MaterialSurfaceFxNodeTests(unittest.TestCase):
    def test_surface_dust_mask_biases_toward_top(self) -> None:
        image = torch.full((1, 64, 64, 3), 0.55, dtype=torch.float32)

        node = x1SurfaceDustMask()
        out, mask, info = node.run(
            image=image,
            source_mode="combined_dust",
            top_bias=0.84,
            cavity_bias=0.12,
            breakup=0.0,
            amount=1.0,
            coverage=0.52,
            contrast=1.0,
            gamma=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        top_mean = float(mask[:, :10, :].mean().item())
        bottom_mean = float(mask[:, -10:, :].mean().item())

        self.assertGreater(top_mean, bottom_mean + 0.08)
        self.assertGreater(float(out.mean().item()), 0.0)
        self.assertIn("x1SurfaceDustMask", info)

    def test_surface_streak_mask_travels_down_from_source_mask(self) -> None:
        image = torch.full((1, 64, 64, 3), 0.52, dtype=torch.float32)
        source_mask = torch.zeros((1, 64, 64), dtype=torch.float32)
        source_mask[:, 5:10, 30:34] = 1.0

        node = x1SurfaceStreakMask()
        out, mask, info = node.run(
            image=image,
            source_mode="mask",
            direction="down",
            streak_length=0.92,
            anchor_bias=0.80,
            breakup=0.0,
            coverage=0.40,
            contrast=1.0,
            gamma=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
            source_mask=source_mask,
        )

        downstream = float(mask[:, 12:24, 30:34].mean().item())
        upstream = float(mask[:, :4, 30:34].mean().item())
        off_axis = float(mask[:, 12:24, 8:12].mean().item())

        self.assertGreater(downstream, upstream + 0.08)
        self.assertGreater(downstream, off_axis + 0.08)
        self.assertGreater(float(out.mean().item()), 0.0)
        self.assertIn("x1SurfaceStreakMask", info)

    def test_surface_rust_bloom_favors_dark_warm_edge_regions(self) -> None:
        image = torch.full((1, 64, 64, 3), 0.58, dtype=torch.float32)
        image[:, 18:48, 28:36, :] = 0.14
        image[:, 20:46, 36:46, 0] = 0.72
        image[:, 20:46, 36:46, 1] = 0.30
        image[:, 20:46, 36:46, 2] = 0.14

        node = x1SurfaceRustBloomMask()
        out, mask, info = node.run(
            image=image,
            source_mode="combined_rust",
            cavity_bias=0.54,
            edge_bias=0.72,
            warm_bias=0.48,
            bloom_spread=0.42,
            breakup=0.0,
            amount=1.0,
            coverage=0.34,
            contrast=1.0,
            gamma=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        seam_mean = float(mask[:, 18:48, 30:44].mean().item())
        flat_mean = float(mask[:, 6:18, 6:18].mean().item())

        self.assertGreater(seam_mean, flat_mean + 0.12)
        self.assertGreater(float(out.mean().item()), 0.0)
        self.assertIn("x1SurfaceRustBloomMask", info)

    def test_surface_waterline_forms_horizontal_band_near_level(self) -> None:
        image = torch.full((1, 64, 64, 3), 0.56, dtype=torch.float32)

        node = x1SurfaceWaterlineMask()
        out, mask, info = node.run(
            image=image,
            source_mode="combined_waterline",
            orientation="bottom",
            line_height=0.70,
            band_width=0.16,
            capillary_rise=0.22,
            cavity_bias=0.44,
            breakup=0.0,
            amount=1.0,
            coverage=0.42,
            contrast=1.0,
            gamma=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        band_mean = float(mask[:, 40:50, :].mean().item())
        top_mean = float(mask[:, :12, :].mean().item())

        self.assertGreater(band_mean, top_mean + 0.12)
        self.assertGreater(float(out.mean().item()), 0.0)
        self.assertIn("x1SurfaceWaterlineMask", info)


if __name__ == "__main__":
    unittest.main()
