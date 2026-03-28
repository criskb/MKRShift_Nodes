import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xcine import (  # noqa: E402
    x1FilmPrint,
    x1HighlightRollOff,
    x1SkinToneProtect,
)


class CineFinishNodeTests(unittest.TestCase):
    def test_film_print_supports_bundled_settings(self) -> None:
        x = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 1, 48, 1)
        y = torch.linspace(0.0, 1.0, 48, dtype=torch.float32).view(1, 48, 1, 1)
        image = torch.cat((x.repeat(1, 48, 1, 1), y.repeat(1, 1, 48, 1), ((x + y) * 0.5)), dim=-1)

        settings_json = json.dumps(
            {
                "stock": "bleach_bypass",
                "density": 0.12,
                "contrast": 1.18,
                "saturation": 0.62,
                "warmth": -0.04,
                "toe": 0.14,
                "shoulder": 0.30,
                "fade": 0.02,
                "mix": 1.0,
                "mask_feather": 8.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1FilmPrint().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 48, 48, 3))
        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("stock=bleach_bypass", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.01)

    def test_highlight_rolloff_supports_bundled_settings(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[:, :, :20, :] = 0.18
        image[:, :, 20:36, :] = 0.72
        image[:, :, 36:, :] = 1.0

        settings_json = json.dumps(
            {
                "pivot": 0.64,
                "softness": 0.12,
                "amount": 0.74,
                "preserve_color": True,
                "mix": 1.0,
                "mask_feather": 6.0,
                "invert_mask": False,
            }
        )

        out, mask_out, info = x1HighlightRollOff().run(image=image, settings_json=settings_json)

        self.assertEqual(tuple(mask_out.shape), (1, 48, 48))
        self.assertIn("pivot=0.64", info)
        self.assertLess(float(out[:, :, 40:, :].mean().item()), float(image[:, :, 40:, :].mean().item()))

    def test_skin_tone_protect_supports_reference_restore_and_legacy(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[..., 0] = 0.74
        image[..., 1] = 0.52
        image[..., 2] = 0.38

        reference = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        reference[..., 0] = 0.64
        reference[..., 1] = 0.48
        reference[..., 2] = 0.36

        settings_json = json.dumps(
            {
                "mode": "reference_restore",
                "protect_strength": 0.92,
                "hue_center": 28.0,
                "hue_width": 46.0,
                "sat_min": 0.08,
                "sat_max": 0.90,
                "val_min": 0.08,
                "val_max": 1.0,
                "softness": 18.0,
                "saturation_limit": 0.76,
                "warmth_balance": 0.0,
                "mix": 1.0,
                "mask_feather": 8.0,
                "invert_mask": False,
            }
        )

        out, skin_mask, info = x1SkinToneProtect().run(
            image=image,
            settings_json=settings_json,
            reference_image=reference,
        )

        self.assertEqual(tuple(skin_mask.shape), (1, 48, 48))
        self.assertIn("mode=reference_restore", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)

        legacy_out, legacy_mask, legacy_info = x1SkinToneProtect().run(
            image=image,
            mode="naturalize",
            protect_strength=0.70,
            hue_center=28.0,
            hue_width=40.0,
            sat_min=0.10,
            sat_max=0.80,
            val_min=0.08,
            val_max=1.0,
            softness=16.0,
            saturation_limit=0.72,
            warmth_balance=0.08,
            mix=1.0,
        )
        self.assertEqual(tuple(legacy_mask.shape), (1, 48, 48))
        self.assertIn("mode=naturalize", legacy_info)
        self.assertGreater(float(torch.mean(torch.abs(legacy_out - image)).item()), 0.001)


if __name__ == "__main__":
    unittest.main()
