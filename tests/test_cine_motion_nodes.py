import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xcine import x1FilmDamage, x1GateWeave, x1LensBreathing  # noqa: E402
from MKRShift_Nodes.nodes.vfx_optics_nodes import x1ShockwaveDistort  # noqa: E402


class CineMotionNodeTests(unittest.TestCase):
    def test_gate_weave_supports_bundled_settings(self) -> None:
        x = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 1, 64, 1)
        y = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 48, 1, 1)
        image = torch.cat((x.repeat(1, 48, 1, 1), y.repeat(1, 1, 64, 1), x.repeat(1, 48, 1, 1)), dim=-1)

        settings_json = json.dumps(
            {
                "shift_x_px": 4.0,
                "shift_y_px": 2.4,
                "rotation_deg": 0.8,
                "scale_jitter": 0.018,
                "jitter_mode": "uniform",
                "seed": 41,
                "mix": 1.0,
                "mask_feather": 8.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1GateWeave().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 48, 64, 3))
        self.assertEqual(tuple(mask_out.shape), (1, 48, 64))
        self.assertIn("mode=uniform", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.002)

    def test_film_damage_supports_bundled_settings(self) -> None:
        image = torch.full((1, 56, 56, 3), 0.45, dtype=torch.float32)

        settings_json = json.dumps(
            {
                "dust_amount": 0.52,
                "scratch_amount": 0.44,
                "burn_amount": 0.16,
                "flicker_amount": 0.12,
                "seed": 1977,
                "mix": 1.0,
                "mask_feather": 10.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1FilmDamage().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(mask_out.shape), (1, 56, 56))
        self.assertIn("seed=1977", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.002)

    def test_lens_breathing_supports_depth_map_with_bundled_settings(self) -> None:
        x = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 1, 64, 1)
        y = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 64, 1, 1)
        image = torch.cat((x.repeat(1, 64, 1, 1), y.repeat(1, 1, 64, 1), ((x + y) * 0.5)), dim=-1)
        depth_map = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).repeat(64, 1).unsqueeze(0)

        settings_json = json.dumps(
            {
                "breath_amount": 0.14,
                "edge_response": 0.82,
                "anisotropy": 0.16,
                "center_x": 0.46,
                "center_y": 0.52,
                "chroma": 0.24,
                "mix": 1.0,
                "mask_feather": 6.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1LensBreathing().run(
            image=image,
            settings_json=settings_json,
            depth_map=depth_map,
        )

        self.assertEqual(tuple(mask_out.shape), (1, 64, 64))
        self.assertIn("depth_map=yes", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.001)

    def test_shockwave_supports_bundled_settings_and_legacy_bypass(self) -> None:
        y = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 64, 1, 1)
        x = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 1, 64, 1)
        image = torch.cat((x.repeat(1, 64, 1, 1), y.repeat(1, 1, 64, 1), ((x + y) * 0.5)), dim=-1)

        settings_json = json.dumps(
            {
                "center_x": 0.48,
                "center_y": 0.54,
                "radius": 0.20,
                "width": 0.07,
                "amplitude_px": 18.0,
                "ring_hardness": 1.9,
                "chroma_split_px": 1.6,
                "mix": 1.0,
                "mask_feather": 4.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1ShockwaveDistort().run(image=image, settings_json=settings_json)
        self.assertEqual(tuple(mask_out.shape), (1, 64, 64))
        self.assertIn("amplitude=18.00px", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.001)

        legacy_out, legacy_mask, legacy_info = x1ShockwaveDistort().run(image=image, amplitude_px=0.0, mix=1.0)
        self.assertTrue(torch.allclose(legacy_out, image))
        self.assertEqual(float(legacy_mask.max().item()), 0.0)
        self.assertIn("bypassed", legacy_info)


if __name__ == "__main__":
    unittest.main()
