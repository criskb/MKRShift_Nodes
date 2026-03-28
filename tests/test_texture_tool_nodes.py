import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.texture_tool_nodes import (  # noqa: E402
    x1TextureAlbedoSafe,
    x1TextureCellPattern,
    x1TextureDetileBlend,
    x1TextureDelight,
    x1TextureEdgePad,
    x1TextureHexTiles,
    x1TextureMacroVariation,
    x1TextureNoiseField,
    x1TextureOffset,
    x1TextureSeamless,
    x1TextureStrata,
    x1TextureTilePreview,
    x1TextureWeavePattern,
)


class TextureToolNodeTests(unittest.TestCase):
    def test_texture_offset_half_tile_moves_content_and_marks_seam(self) -> None:
        image = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        image[:, :, :2, :] = 1.0

        node = x1TextureOffset()
        output, mask, info = node.run(image=image, mode="half_tile", seam_width=1.0)

        self.assertGreater(float(torch.mean(output[:, :, 4:6, :]).item()), 0.9)
        self.assertGreater(float(mask[0, 4, 4].item()), 0.5)
        self.assertIn("x1TextureOffset", info)

    def test_texture_seamless_reduces_edge_mismatch(self) -> None:
        x = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 1, 32, 1)
        y = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 32, 1, 1)
        image = torch.cat(
            [
                x.repeat(1, 32, 1, 1),
                y.repeat(1, 1, 32, 1),
                torch.full((1, 32, 32, 1), 0.25, dtype=torch.float32),
            ],
            dim=-1,
        )

        base_delta = float(torch.mean(torch.abs(image[:, :, 0, :] - image[:, :, -1, :])).item())
        node = x1TextureSeamless()
        output, mask, info = node.run(
            image=image,
            blend_width=10.0,
            edge_match_strength=1.0,
            edge_match_blur=10.0,
            detail_preserve=0.5,
            seam_blur=8.0,
        )
        out_delta = float(torch.mean(torch.abs(output[:, :, 0, :] - output[:, :, -1, :])).item())

        self.assertLess(out_delta, base_delta)
        self.assertGreater(float(mask[0, 0, 0].item()), 0.4)
        self.assertIn("x1TextureSeamless", info)

    def test_texture_seamless_respects_optional_mask(self) -> None:
        x = torch.linspace(0.0, 1.0, 40, dtype=torch.float32).view(1, 1, 40, 1)
        y = torch.linspace(0.0, 1.0, 40, dtype=torch.float32).view(1, 40, 1, 1)
        image = torch.cat(
            [
                x.repeat(1, 40, 1, 1),
                y.repeat(1, 1, 40, 1),
                torch.full((1, 40, 40, 1), 0.25, dtype=torch.float32),
            ],
            dim=-1,
        )
        mask = torch.zeros((1, 40, 40), dtype=torch.float32)
        mask[:, :, :20] = 1.0

        node = x1TextureSeamless()
        output, seam_mask, info = node.run(
            image=image,
            blend_width=12.0,
            edge_match_strength=0.9,
            edge_match_blur=8.0,
            detail_preserve=0.6,
            seam_blur=6.0,
            seam_softness=8.0,
            mask_feather=0.0,
            invert_mask=False,
            mask=mask,
        )

        left_change = float(torch.mean(torch.abs(output[:, :, :20, :] - image[:, :, :20, :])).item())
        right_change = float(torch.mean(torch.abs(output[:, :, 20:, :] - image[:, :, 20:, :])).item())

        self.assertGreater(left_change, right_change * 4.0)
        self.assertGreater(float(torch.mean(seam_mask[:, :, :20]).item()), float(torch.mean(seam_mask[:, :, 20:]).item()) * 4.0)
        self.assertIn("mask_coverage", info)

    def test_texture_tile_preview_repeats_pattern(self) -> None:
        image = torch.tensor(
            [[[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0], [1.0, 1.0, 0.0]]]],
            dtype=torch.float32,
        )

        node = x1TextureTilePreview()
        output, mask, info = node.run(image=image, tiles_x=2, tiles_y=3, show_seams=False, seam_width=1.0)

        self.assertEqual(tuple(output.shape), (1, 6, 4, 3))
        self.assertTrue(torch.allclose(output[:, :2, :2, :], output[:, 2:4, :2, :], atol=1e-5))
        self.assertGreater(float(mask[0, 2, 1].item()), 0.3)
        self.assertIn("x1TextureTilePreview", info)

    def test_texture_edge_pad_fills_transparent_neighbors(self) -> None:
        image = torch.zeros((1, 9, 9, 4), dtype=torch.float32)
        image[:, 4, 4, :3] = torch.tensor([0.8, 0.2, 0.1], dtype=torch.float32)
        image[:, 4, 4, 3] = 1.0

        node = x1TextureEdgePad()
        output, mask, info = node.run(
            image=image,
            source_mode="alpha",
            pad_pixels=2,
            alpha_threshold=0.5,
            expand_alpha=True,
        )

        self.assertGreater(float(torch.mean(output[:, 3:6, 3:6, 0]).item()), 0.1)
        self.assertGreater(float(mask[0, 4, 5].item()), 0.5)
        self.assertGreater(float(output[0, 4, 5, 3].item()), 0.5)
        self.assertIn("x1TextureEdgePad", info)

    def test_texture_delight_flattens_low_frequency_lighting(self) -> None:
        base = torch.ones((1, 48, 48, 3), dtype=torch.float32)
        base *= torch.tensor([0.55, 0.38, 0.22], dtype=torch.float32)
        gradient = torch.linspace(0.6, 1.45, 48, dtype=torch.float32).view(1, 1, 48, 1)
        image = torch.clamp(base * gradient, 0.0, 1.0)

        node = x1TextureDelight()
        output, mask, info = node.run(
            image=image,
            blur_radius=10.0,
            flatten_strength=1.0,
            detail_preserve=0.85,
            shadow_lift=0.4,
            highlight_compress=0.3,
            mask_feather=0.0,
        )

        before_delta = float(torch.mean(torch.abs(image[:, :, :8, :] - image[:, :, -8:, :])).item())
        after_delta = float(torch.mean(torch.abs(output[:, :, :8, :] - output[:, :, -8:, :])).item())
        before_ratio = float(image[0, 24, 24, 0].item() / max(image[0, 24, 24, 1].item(), 1e-6))
        after_ratio = float(output[0, 24, 24, 0].item() / max(output[0, 24, 24, 1].item(), 1e-6))

        self.assertLess(after_delta, before_delta * 0.7)
        self.assertAlmostEqual(before_ratio, after_ratio, places=2)
        self.assertGreater(float(mask.mean().item()), 0.05)
        self.assertIn("x1TextureDelight", info)

    def test_texture_delight_respects_optional_mask(self) -> None:
        base = torch.ones((1, 40, 40, 3), dtype=torch.float32)
        base *= torch.tensor([0.42, 0.42, 0.42], dtype=torch.float32)
        vertical = torch.linspace(0.55, 1.5, 40, dtype=torch.float32).view(1, 40, 1, 1)
        image = torch.clamp(base * vertical, 0.0, 1.0)
        mask = torch.zeros((1, 40, 40), dtype=torch.float32)
        mask[:, :, :20] = 1.0

        node = x1TextureDelight()
        output, _, _ = node.run(
            image=image,
            blur_radius=8.0,
            flatten_strength=1.0,
            detail_preserve=0.75,
            shadow_lift=0.5,
            highlight_compress=0.4,
            mask_feather=0.0,
            mask=mask,
        )

        left_change = float(torch.mean(torch.abs(output[:, :, :20, :] - image[:, :, :20, :])).item())
        right_change = float(torch.mean(torch.abs(output[:, :, 20:, :] - image[:, :, 20:, :])).item())

        self.assertGreater(left_change, right_change * 4.0)

    def test_texture_albedo_safe_reduces_extremes_while_preserving_hue_bias(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.02, 0.01, 0.005], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([1.0, 0.20, 0.10], dtype=torch.float32)

        node = x1TextureAlbedoSafe()
        output, mask, info = node.run(
            image=image,
            target_black=0.04,
            target_white=0.82,
            saturation_limit=0.75,
            shadow_lift=0.45,
            highlight_rolloff=0.65,
            mask_feather=0.0,
        )

        before_dark = float(image[0, 16, 8, 0].item())
        after_dark = float(output[0, 16, 8, 0].item())
        before_bright = float(image[0, 16, 24, 0].item())
        after_bright = float(output[0, 16, 24, 0].item())
        before_ratio = float(image[0, 16, 24, 0].item() / max(image[0, 16, 24, 1].item(), 1e-6))
        after_ratio = float(output[0, 16, 24, 0].item() / max(output[0, 16, 24, 1].item(), 1e-6))

        self.assertGreater(after_dark, before_dark)
        self.assertLess(after_bright, before_bright)
        self.assertAlmostEqual(before_ratio, after_ratio, places=1)
        self.assertGreater(float(mask.mean().item()), 0.05)
        self.assertIn("x1TextureAlbedoSafe", info)

    def test_texture_macro_variation_is_deterministic_for_a_fixed_seed(self) -> None:
        image = torch.ones((1, 40, 40, 3), dtype=torch.float32)
        image *= torch.tensor([0.46, 0.40, 0.32], dtype=torch.float32)

        node = x1TextureMacroVariation()
        output_a, mask_a, info = node.run(
            image=image,
            macro_scale_px=96.0,
            strength=0.65,
            hue_variation=0.03,
            value_variation=0.16,
            contrast_variation=0.18,
            seed=123,
            mask_feather=0.0,
        )
        output_b, mask_b, _ = node.run(
            image=image,
            macro_scale_px=96.0,
            strength=0.65,
            hue_variation=0.03,
            value_variation=0.16,
            contrast_variation=0.18,
            seed=123,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(output_a, output_b, atol=1e-6))
        self.assertTrue(torch.allclose(mask_a, mask_b, atol=1e-6))
        self.assertGreater(float(mask_a.mean().item()), 0.05)
        self.assertGreater(float(torch.mean(torch.abs(output_a - image)).item()), 0.01)
        self.assertIn("x1TextureMacroVariation", info)

    def test_texture_detile_blend_is_deterministic_and_changes_macro_pattern(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[:, :, :24, :] = torch.tensor([0.62, 0.48, 0.34], dtype=torch.float32)
        image[:, :, 24:, :] = torch.tensor([0.48, 0.34, 0.22], dtype=torch.float32)
        image[:, 12:20, :, :] += torch.tensor([0.08, 0.02, 0.01], dtype=torch.float32)
        image = torch.clamp(image, 0.0, 1.0)

        node = x1TextureDetileBlend()
        output_a, mask_a, info = node.run(
            image=image,
            macro_scale_px=96.0,
            blend_strength=0.60,
            color_match_blur=12.0,
            detail_preserve=0.78,
            seed=77,
            mask_feather=0.0,
        )
        output_b, mask_b, _ = node.run(
            image=image,
            macro_scale_px=96.0,
            blend_strength=0.60,
            color_match_blur=12.0,
            detail_preserve=0.78,
            seed=77,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(output_a, output_b, atol=1e-6))
        self.assertTrue(torch.allclose(mask_a, mask_b, atol=1e-6))
        self.assertGreater(float(mask_a.mean().item()), 0.05)
        self.assertGreater(float(torch.mean(torch.abs(output_a - image)).item()), 0.01)
        self.assertIn("x1TextureDetileBlend", info)

    def test_texture_noise_field_is_deterministic_and_tileable(self) -> None:
        node = x1TextureNoiseField()
        output_a, mask_a, info = node.run(
            width=72,
            height=64,
            variant="ridged",
            scale_px=18.0,
            octaves=4,
            lacunarity=2.0,
            gain=0.55,
            contrast=1.3,
            balance=0.0,
            invert=False,
            seed=99,
        )
        output_b, mask_b, _ = node.run(
            width=72,
            height=64,
            variant="ridged",
            scale_px=18.0,
            octaves=4,
            lacunarity=2.0,
            gain=0.55,
            contrast=1.3,
            balance=0.0,
            invert=False,
            seed=99,
        )

        self.assertEqual(tuple(output_a.shape), (1, 64, 72, 3))
        self.assertTrue(torch.allclose(output_a, output_b, atol=1e-6))
        self.assertTrue(torch.allclose(mask_a, mask_b, atol=1e-6))
        self.assertTrue(torch.allclose(output_a[0, :, :, 0], mask_a[0], atol=1e-6))
        self.assertTrue(torch.allclose(mask_a[0, :, 0], mask_a[0, :, -1], atol=1e-6))
        self.assertTrue(torch.allclose(mask_a[0, 0, :], mask_a[0, -1, :], atol=1e-6))
        self.assertGreater(float(mask_a.std().item()), 0.08)
        self.assertIn("x1TextureNoiseField", info)

    def test_texture_cell_pattern_emits_distinct_crack_structure(self) -> None:
        node = x1TextureCellPattern()
        fill_output, fill_mask, info = node.run(
            width=64,
            height=64,
            pattern_mode="fill",
            cell_scale_px=12.0,
            jitter=0.85,
            edge_width=0.16,
            contrast=1.1,
            balance=0.0,
            invert=False,
            seed=7,
        )
        crack_output, crack_mask, _ = node.run(
            width=64,
            height=64,
            pattern_mode="cracks",
            cell_scale_px=12.0,
            jitter=0.85,
            edge_width=0.16,
            contrast=1.1,
            balance=0.0,
            invert=False,
            seed=7,
        )

        self.assertTrue(torch.allclose(fill_mask[0, :, 0], fill_mask[0, :, -1], atol=1e-6))
        self.assertTrue(torch.allclose(fill_mask[0, 0, :], fill_mask[0, -1, :], atol=1e-6))
        self.assertGreater(float(fill_mask.std().item()), 0.05)
        self.assertLess(float(crack_mask.mean().item()), float(fill_mask.mean().item()))
        self.assertGreater(float(crack_mask.max().item()), 0.9)
        self.assertTrue(torch.allclose(fill_output[0, :, :, 0], fill_mask[0], atol=1e-6))
        self.assertTrue(torch.allclose(crack_output[0, :, :, 0], crack_mask[0], atol=1e-6))
        self.assertIn("x1TextureCellPattern", info)

    def test_texture_strata_respects_directional_profile(self) -> None:
        node = x1TextureStrata()
        output, mask, info = node.run(
            width=80,
            height=64,
            profile="veins",
            band_scale_px=18.0,
            direction_deg=90.0,
            warp_strength=0.25,
            breakup_scale_px=20.0,
            breakup_strength=0.35,
            contrast=1.2,
            balance=0.0,
            invert=False,
            seed=1234,
        )

        row_delta = float(torch.mean(torch.abs(mask[0, 1:, :] - mask[0, :-1, :])).item())
        col_delta = float(torch.mean(torch.abs(mask[0, :, 1:] - mask[0, :, :-1])).item())

        self.assertTrue(torch.allclose(mask[0, :, 0], mask[0, :, -1], atol=1e-6))
        self.assertTrue(torch.allclose(mask[0, 0, :], mask[0, -1, :], atol=1e-6))
        self.assertGreater(row_delta, col_delta * 1.15)
        self.assertGreater(float(mask.std().item()), 0.06)
        self.assertTrue(torch.allclose(output[0, :, :, 0], mask[0], atol=1e-6))
        self.assertIn("x1TextureStrata", info)

    def test_texture_hex_tiles_are_tileable_and_mode_distinct(self) -> None:
        node = x1TextureHexTiles()
        fill_output, fill_mask, info = node.run(
            width=96,
            height=96,
            pattern_mode="fill",
            hex_scale_px=18.0,
            line_width=0.16,
            contrast=1.1,
            balance=0.0,
            invert=False,
            seed=21,
        )
        line_output, line_mask, _ = node.run(
            width=96,
            height=96,
            pattern_mode="lines",
            hex_scale_px=18.0,
            line_width=0.16,
            contrast=1.1,
            balance=0.0,
            invert=False,
            seed=21,
        )

        self.assertTrue(torch.allclose(fill_mask[0, :, 0], fill_mask[0, :, -1], atol=1e-6))
        self.assertTrue(torch.allclose(fill_mask[0, 0, :], fill_mask[0, -1, :], atol=1e-6))
        self.assertGreater(float(fill_mask.std().item()), 0.05)
        self.assertLess(float(line_mask.mean().item()), float(fill_mask.mean().item()))
        self.assertGreater(float(line_mask.max().item()), 0.9)
        self.assertTrue(torch.allclose(fill_output[0, :, :, 0], fill_mask[0], atol=1e-6))
        self.assertTrue(torch.allclose(line_output[0, :, :, 0], line_mask[0], atol=1e-6))
        self.assertIn("x1TextureHexTiles", info)

    def test_texture_weave_pattern_is_tileable_and_style_changes_output(self) -> None:
        node = x1TextureWeavePattern()
        plain_output, plain_mask, info = node.run(
            width=96,
            height=96,
            style="plain",
            warp_scale_px=12.0,
            weft_scale_px=12.0,
            thread_width=0.72,
            relief=0.85,
            contrast=1.15,
            balance=0.0,
            invert=False,
            seed=55,
        )
        basket_output, basket_mask, _ = node.run(
            width=96,
            height=96,
            style="basket",
            warp_scale_px=12.0,
            weft_scale_px=12.0,
            thread_width=0.72,
            relief=0.85,
            contrast=1.15,
            balance=0.0,
            invert=False,
            seed=55,
        )

        row_delta = float(torch.mean(torch.abs(plain_mask[0, 1:, :] - plain_mask[0, :-1, :])).item())
        col_delta = float(torch.mean(torch.abs(plain_mask[0, :, 1:] - plain_mask[0, :, :-1])).item())

        self.assertTrue(torch.allclose(plain_mask[0, :, 0], plain_mask[0, :, -1], atol=1e-6))
        self.assertTrue(torch.allclose(plain_mask[0, 0, :], plain_mask[0, -1, :], atol=1e-6))
        self.assertGreater(row_delta, 0.03)
        self.assertGreater(col_delta, 0.03)
        self.assertGreater(float(plain_mask.std().item()), 0.08)
        self.assertGreater(float(torch.mean(torch.abs(plain_output - basket_output)).item()), 0.01)
        self.assertTrue(torch.allclose(plain_output[0, :, :, 0], plain_mask[0], atol=1e-6))
        self.assertIn("x1TextureWeavePattern", info)


if __name__ == "__main__":
    unittest.main()
