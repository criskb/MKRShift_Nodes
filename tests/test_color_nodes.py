import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xcolor import x1GamutMap  # noqa: E402


def _luma(image: torch.Tensor) -> torch.Tensor:
    return (0.2126 * image[..., 0]) + (0.7152 * image[..., 1]) + (0.0722 * image[..., 2])


def _chroma_span(image: torch.Tensor) -> torch.Tensor:
    return torch.max(image, dim=-1).values - torch.min(image, dim=-1).values


class ColorNodeTests(unittest.TestCase):
    def test_gamut_map_is_identity_at_neutral_settings(self) -> None:
        image = torch.tensor(
            [[
                [[1.0, 0.2, 0.05], [0.2, 0.7, 1.0]],
                [[0.4, 0.4, 0.4], [0.9, 0.8, 0.2]],
            ]],
            dtype=torch.float32,
        )

        settings_json = json.dumps(
            {
                "compression": 0.0,
                "rolloff": 0.35,
                "saturation": 1.0,
                "highlight_protect": 0.0,
                "neutral_protect": 0.0,
                "preserve_luma": True,
                "mix": 1.0,
                "mask_feather": 12.0,
                "invert_mask": False,
            }
        )

        out, mask, info = x1GamutMap().run(image=image, settings_json=settings_json)

        self.assertLess(float(torch.max(torch.abs(out - image)).item()), 1e-5)
        self.assertEqual(tuple(mask.shape), (1, 2, 2))
        self.assertIn("neutral_protect=0.00", info)

    def test_gamut_map_compression_reduces_high_chroma(self) -> None:
        image = torch.full((1, 24, 24, 3), 0.0, dtype=torch.float32)
        image[..., 0] = 1.0
        image[..., 1] = 0.20
        image[..., 2] = 0.05

        settings_json = json.dumps(
            {
                "compression": 0.8,
                "rolloff": 0.6,
                "saturation": 1.0,
                "highlight_protect": 0.0,
                "neutral_protect": 0.0,
                "preserve_luma": False,
                "mix": 1.0,
                "mask_feather": 12.0,
                "invert_mask": False,
            }
        )

        out, _, _ = x1GamutMap().run(image=image, settings_json=settings_json)

        src_span = float(_chroma_span(image).mean().item())
        out_span = float(_chroma_span(out).mean().item())
        self.assertLess(out_span, src_span - 0.05)

    def test_gamut_map_preserve_luma_reduces_luminance_drift(self) -> None:
        image = torch.full((1, 24, 24, 3), 0.0, dtype=torch.float32)
        image[..., 0] = 1.0
        image[..., 1] = 0.35
        image[..., 2] = 0.10

        base_settings = {
            "compression": 0.85,
            "rolloff": 0.75,
            "saturation": 0.9,
            "highlight_protect": 0.2,
            "neutral_protect": 0.2,
            "mix": 1.0,
            "mask_feather": 12.0,
            "invert_mask": False,
        }

        out_no_luma, _, _ = x1GamutMap().run(
            image=image,
            settings_json=json.dumps({**base_settings, "preserve_luma": False}),
        )
        out_keep_luma, _, _ = x1GamutMap().run(
            image=image,
            settings_json=json.dumps({**base_settings, "preserve_luma": True}),
        )

        src_luma = _luma(image)
        drift_without = float(torch.mean(torch.abs(_luma(out_no_luma) - src_luma)).item())
        drift_with = float(torch.mean(torch.abs(_luma(out_keep_luma) - src_luma)).item())
        self.assertLess(drift_with, drift_without)

    def test_gamut_map_accepts_legacy_widget_values(self) -> None:
        image = torch.full((1, 12, 12, 3), 0.5, dtype=torch.float32)
        image[..., 0] = 0.95
        image[..., 1] = 0.20
        image[..., 2] = 0.12

        out, mask, info = x1GamutMap().run(
            image=image,
            compression=0.5,
            rolloff=0.4,
            saturation=0.95,
            highlight_protect=0.3,
            neutral_protect=0.45,
            preserve_luma=True,
            mix=0.8,
        )

        self.assertEqual(tuple(mask.shape), (1, 12, 12))
        self.assertIn("mix=0.80", info)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.005)


if __name__ == "__main__":
    unittest.main()
