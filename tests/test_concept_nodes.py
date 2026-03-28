import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xconcepts import (  # noqa: E402
    x1CRTScan,
    x1Depth,
    x1GlowEdges,
    x1LensDistort,
    x1LightLeak,
    x1SelectiveColor,
    x1SplitTone,
    x1WarpDisplace,
)


class ConceptNodeTests(unittest.TestCase):
    def test_light_leak_node_supports_bundled_settings(self) -> None:
        xs = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        ys = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        grid_x = xs.view(1, 1, 48, 1).expand(1, 48, 48, 1)
        grid_y = ys.view(1, 48, 1, 1).expand(1, 48, 48, 1)
        image = torch.cat([grid_x, grid_y, torch.flip(grid_x, dims=[2])], dim=-1)

        settings_json = json.dumps(
            {
                "strength": 0.9,
                "angle": 48.0,
                "scale": 1.35,
                "softness": 1.6,
                "seed": 42,
                "ramp_preset": "sunset",
                "blend_mode": "screen",
                "mask_feather": 6.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1LightLeak().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 48, 48, 3))
        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("ramp=sunset", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.01)

    def test_depth_node_supports_bundled_settings(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[:, :, :24, :] = 0.2
        image[:, :, 24:, :] = 0.9

        settings_json = json.dumps(
            {
                "depth_mode": "inverted_luma",
                "focal_depth": 0.42,
                "depth_range": 0.18,
                "near_blur": 12.0,
                "far_blur": 22.0,
                "depth_contrast": 1.4,
                "haze_strength": 0.2,
                "haze_r": 0.72,
                "haze_g": 0.8,
                "haze_b": 0.9,
                "mask_feather": 12.0,
                "invert_mask": False,
            }
        )

        out, depth_mask, info = x1Depth().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 48, 48, 3))
        self.assertEqual(tuple(depth_mask.shape), (1, 48, 48))
        self.assertIn("mode=inverted_luma", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.01)

    def test_depth_node_uses_custom_depth_map_and_legacy_args(self) -> None:
        image = torch.full((1, 48, 48, 3), 0.5, dtype=torch.float32)
        depth_map = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).repeat(48, 1).unsqueeze(0)

        out, depth_mask, info = x1Depth().run(
            image=image,
            depth_mode="custom_map",
            focal_depth=0.55,
            depth_range=0.16,
            near_blur=6.0,
            far_blur=26.0,
            depth_contrast=1.0,
            haze_strength=0.1,
            haze_r=0.75,
            haze_g=0.82,
            haze_b=0.9,
            depth_map=depth_map,
        )

        self.assertEqual(tuple(depth_mask.shape), (1, 48, 48))
        self.assertLess(float(depth_mask[0, 0, 0].item()), float(depth_mask[0, 0, -1].item()))
        self.assertIn("mode=custom_map", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)

    def test_split_tone_node_supports_bundled_settings(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 1, 48, 1).expand(1, 48, 48, 1)
        image = ramp.repeat(1, 1, 1, 3)

        settings_json = json.dumps(
            {
                "shadow_hue": 225.0,
                "shadow_sat": 0.42,
                "highlight_hue": 32.0,
                "highlight_sat": 0.38,
                "balance": -0.1,
                "pivot": 0.46,
                "mix": 0.84,
                "mask_feather": 8.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1SplitTone().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("mix=0.84", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.01)

    def test_selective_color_node_supports_legacy_args(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[..., 2] = 0.8
        image[..., 1] = 0.35

        out, mask_out, info = x1SelectiveColor().run(
            image=image,
            range_mode="blues",
            custom_hue_center=220.0,
            custom_hue_width=40.0,
            hue_shift=-12.0,
            sat_shift=0.35,
            value_shift=0.08,
            softness=28.0,
            amount=0.9,
            preserve_luma=True,
        )

        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("range=blues", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)

    def test_lens_distort_node_supports_bundled_settings(self) -> None:
        xs = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        ys = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        grid_x = xs.view(1, 1, 48, 1).expand(1, 48, 48, 1)
        grid_y = ys.view(1, 48, 1, 1).expand(1, 48, 48, 1)
        image = torch.cat([grid_x, torch.flip(grid_y, dims=[1]), grid_y], dim=-1)

        settings_json = json.dumps(
            {
                "distortion": 0.26,
                "chroma_aberration": 0.12,
                "edge_vignette": 0.34,
                "zoom_compensation": True,
                "mask_feather": 10.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1LensDistort().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("zoom_comp=True", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)

    def test_crt_scan_node_supports_bundled_settings(self) -> None:
        xs = torch.linspace(0.0, 1.0, 64, dtype=torch.float32)
        ys = torch.linspace(0.0, 1.0, 64, dtype=torch.float32)
        grid_x = xs.view(1, 1, 64, 1).expand(1, 64, 64, 1)
        grid_y = ys.view(1, 64, 1, 1).expand(1, 64, 64, 1)
        image = torch.cat([grid_x, grid_y, torch.flip(grid_x, dims=[2])], dim=-1)

        settings_json = json.dumps(
            {
                "scanline_strength": 0.46,
                "scanline_density": 1.55,
                "phosphor_strength": 0.58,
                "bloom_bleed": 0.34,
                "warp_strength": 0.20,
                "curvature": 0.26,
                "noise_strength": 0.08,
                "seed": 12,
                "mask_feather": 10.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1CRTScan().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 64, 64, 3))
        self.assertEqual(tuple(mask_out.shape), (1, 64, 64))
        self.assertIn("seed=12", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.01)

    def test_warp_displace_node_supports_bundled_settings(self) -> None:
        xs = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        ys = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        grid_x = xs.view(1, 1, 48, 1).expand(1, 48, 48, 1)
        grid_y = ys.view(1, 48, 1, 1).expand(1, 48, 48, 1)
        image = torch.cat([grid_x, torch.flip(grid_y, dims=[1]), grid_y], dim=-1)
        strength_map = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).repeat(48, 1).unsqueeze(0)

        settings_json = json.dumps(
            {
                "displace_strength": 18.0,
                "base_direction": 42.0,
                "noise_scale": 72.0,
                "noise_mix": 0.64,
                "seed": 99,
                "mask_feather": 6.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1WarpDisplace().run(
            image=image,
            settings_json=settings_json,
            strength_map=strength_map,
        )

        self.assertEqual(tuple(out.shape), (1, 48, 48, 3))
        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("strength_map=yes", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.003)

    def test_glow_edges_node_supports_legacy_args(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[:, 10:38, 10:38, :] = 0.75
        image[:, 18:30, 18:30, :] = 0.18

        out, mask_out, info = x1GlowEdges().run(
            image=image,
            edge_threshold=0.14,
            edge_softness=1.4,
            glow_spread=10.0,
            glow_strength=1.3,
            tint_r=0.30,
            tint_g=0.86,
            tint_b=1.0,
            composite_mode="add",
            ink_amount=0.40,
        )

        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("mode=add", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)


if __name__ == "__main__":
    unittest.main()
