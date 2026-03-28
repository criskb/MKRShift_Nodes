import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xcolor import x1ColorMatch, x1FalseColor, x1GamutMap, x1PaletteMap  # noqa: E402
from MKRShift_Nodes.nodes.xcolor_analyze_nodes import (  # noqa: E402
    x1GamutWarning,
    x1HistogramScope,
    x1SkinToneCheck,
    x1Vectorscope,
    x1WaveformScope,
)


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

    def test_palette_map_accepts_bundled_settings_and_changes_image(self) -> None:
        image = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        image[..., 0] = torch.linspace(0.1, 0.9, 16, dtype=torch.float32)[None, :]
        image[..., 1] = 0.3
        image[..., 2] = 0.6

        out, mask, info = x1PaletteMap().run(
            image=image,
            settings_json=json.dumps(
                {
                    "palette_preset": "neon_night",
                    "mapping_mode": "soft",
                    "softness": 1.2,
                    "preserve_luma": True,
                    "amount": 0.9,
                    "c1_r": 0.08,
                    "c1_g": 0.22,
                    "c1_b": 0.28,
                    "c2_r": 0.18,
                    "c2_g": 0.52,
                    "c2_b": 0.62,
                    "c3_r": 0.84,
                    "c3_g": 0.52,
                    "c3_b": 0.22,
                    "c4_r": 1.0,
                    "c4_g": 0.8,
                    "c4_b": 0.55,
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        self.assertEqual(tuple(mask.shape), (1, 16, 16))
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.02)
        self.assertIn("preset=neon_night", info)

    def test_color_match_accepts_bundled_settings(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[..., 0] = 0.2
        image[..., 1] = 0.4
        image[..., 2] = 0.7
        reference = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        reference[..., 0] = 0.9
        reference[..., 1] = 0.7
        reference[..., 2] = 0.2

        out, mask, info = x1ColorMatch().run(
            image=image,
            reference_image=reference,
            settings_json=json.dumps(
                {
                    "method": "mean_only",
                    "strength": 0.75,
                    "preserve_luma": True,
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        self.assertEqual(tuple(mask.shape), (1, 24, 24))
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.05)
        self.assertIn("method=mean_only", info)

    def test_false_color_accepts_legacy_widget_values(self) -> None:
        image = torch.tensor(
            [[
                [[0.01, 0.01, 0.01], [0.95, 0.95, 0.95]],
                [[0.40, 0.40, 0.40], [0.75, 0.75, 0.75]],
            ]],
            dtype=torch.float32,
        )

        out, mask, info = x1FalseColor().run(
            image=image,
            mode="clipping",
            overlay_opacity=1.0,
            zebra_threshold=0.90,
            low_clip=0.05,
            high_clip=0.90,
            show_zebra=True,
            mask_feather=0.0,
            invert_mask=False,
        )

        self.assertEqual(tuple(mask.shape), (1, 2, 2))
        self.assertGreater(float(mask[0, 0, 0].item()), 0.9)
        self.assertGreater(float(mask[0, 0, 1].item()), 0.9)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.1)
        self.assertIn("mode=clipping", info)

    def test_waveform_scope_produces_scope_image_and_mask(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 48, dtype=torch.float32)
        image = torch.zeros((1, 32, 48, 3), dtype=torch.float32)
        image[..., 0] = ramp[None, None, :]
        image[..., 1] = ramp.flip(0)[None, None, :]
        image[..., 2] = 0.5

        out, mask, info = x1WaveformScope().run(
            image=image,
            settings_json=json.dumps(
                {
                    "scope_mode": "rgb_parade",
                    "gain": 1.2,
                    "trace_strength": 0.9,
                    "graticule": 0.4,
                    "scope_resolution": 384,
                    "sample_step": 1,
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        self.assertEqual(tuple(out.shape), (1, 238, 384, 3))
        self.assertEqual(tuple(mask.shape), (1, 238, 384))
        self.assertGreater(float(mask.mean().item()), 0.002)
        self.assertIn("rgb_parade", info)

    def test_vectorscope_saturated_trace_is_stronger_than_gray(self) -> None:
        gray = torch.full((1, 48, 48, 3), 0.5, dtype=torch.float32)
        colorful = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        colorful[:, :, :24, 0] = 1.0
        colorful[:, :, :24, 1] = 0.15
        colorful[:, :, 24:, 1] = 0.85
        colorful[:, :, 24:, 2] = 1.0

        settings_json = json.dumps(
            {
                "scope_gain": 1.1,
                "trace_strength": 1.0,
                "graticule": 0.4,
                "scope_resolution": 320,
                "sample_step": 1,
                "show_skin_line": True,
                "show_targets": True,
                "mask_feather": 0.0,
                "invert_mask": False,
            }
        )

        _, gray_mask, _ = x1Vectorscope().run(image=gray, settings_json=settings_json)
        out, colorful_mask, info = x1Vectorscope().run(image=colorful, settings_json=settings_json)

        self.assertEqual(tuple(out.shape), (1, 320, 320, 3))
        self.assertGreater(float(colorful_mask.mean().item()), float(gray_mask.mean().item()))
        self.assertGreater(
            float(gray_mask[0, 150:170, 150:170].mean().item()),
            float(colorful_mask[0, 150:170, 150:170].mean().item()) + 0.001,
        )
        self.assertIn("targets=True", info)

    def test_gamut_warning_marks_problem_regions(self) -> None:
        image = torch.tensor(
            [[
                [[1.0, 1.0, 1.0], [1.0, 0.18, 0.05]],
                [[0.01, 0.01, 0.01], [0.45, 0.45, 0.45]],
            ]],
            dtype=torch.float32,
        )

        out, mask, info = x1GamutWarning().run(
            image=image,
            settings_json=json.dumps(
                {
                    "warning_mode": "combined",
                    "low_clip": 0.05,
                    "high_clip": 0.95,
                    "saturation_limit": 0.70,
                    "highlight_gate": 0.10,
                    "overlay_opacity": 1.0,
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        self.assertEqual(tuple(mask.shape), (1, 2, 2))
        self.assertGreater(float(mask[0, 0, 0].item()), 0.9)
        self.assertGreater(float(mask[0, 0, 1].item()), 0.9)
        self.assertGreater(float(mask[0, 1, 0].item()), 0.9)
        self.assertLess(float(mask[0, 1, 1].item()), 0.1)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.05)
        self.assertIn("combined", info)

    def test_waveform_scope_accepts_legacy_widget_values(self) -> None:
        image = torch.rand((1, 24, 24, 3), dtype=torch.float32)
        out, mask, info = x1WaveformScope().run(
            image=image,
            scope_mode="luma",
            gain=1.25,
            trace_strength=0.7,
            graticule=0.2,
            scope_resolution=300,
            sample_step=3,
            mask_feather=0.0,
            invert_mask=False,
        )

        self.assertEqual(tuple(out.shape), (1, 186, 300, 3))
        self.assertEqual(tuple(mask.shape), (1, 186, 300))
        self.assertIn("sample_step=3", info)

    def test_histogram_scope_renders_histogram_image(self) -> None:
        image = torch.zeros((1, 32, 64, 3), dtype=torch.float32)
        image[..., 0] = torch.linspace(0.0, 1.0, 64, dtype=torch.float32)[None, None, :]
        image[..., 1] = 0.4
        image[..., 2] = torch.linspace(1.0, 0.0, 64, dtype=torch.float32)[None, None, :]

        out, mask, info = x1HistogramScope().run(
            image=image,
            settings_json=json.dumps(
                {
                    "histogram_mode": "rgb_overlay",
                    "bins": 96,
                    "contrast": 1.35,
                    "fill_opacity": 0.30,
                    "normalize_mode": "peak",
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        self.assertEqual(tuple(out.shape), (1, 360, 640, 3))
        self.assertEqual(tuple(mask.shape), (1, 360, 640))
        self.assertGreater(float(mask.mean().item()), 0.01)
        self.assertIn("rgb_overlay", info)

    def test_skin_tone_check_flags_skin_like_patch_more_than_blue_patch(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, 0] = 0.82
        image[:, :, :16, 1] = 0.58
        image[:, :, :16, 2] = 0.44
        image[:, :, 16:, 0] = 0.18
        image[:, :, 16:, 1] = 0.42
        image[:, :, 16:, 2] = 0.94

        out, mask, info = x1SkinToneCheck().run(
            image=image,
            settings_json=json.dumps(
                {
                    "target_hue": 28.0,
                    "hue_width": 54.0,
                    "sat_min": 0.08,
                    "sat_max": 0.90,
                    "val_min": 0.10,
                    "line_tolerance": 0.16,
                    "overlay_opacity": 0.85,
                    "show_isolation": False,
                    "mask_feather": 0.0,
                    "invert_mask": False,
                }
            ),
        )

        left = float(mask[0, :, :16].mean().item())
        right = float(mask[0, :, 16:].mean().item())
        self.assertGreater(left, right + 0.20)
        self.assertGreater(float(torch.mean(torch.abs(out - image)).item()), 0.02)
        self.assertIn("target_hue=28.0", info)


if __name__ == "__main__":
    unittest.main()
