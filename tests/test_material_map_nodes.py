import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.material_map_nodes import (  # noqa: E402
    x1CavityMap,
    x1ClearcoatMap,
    x1ClearcoatRoughnessMap,
    x1ColorRegionMask,
    x1EdgeWearMask,
    x1EmissiveMap,
    x1AnisotropyMap,
    x1IridescenceMap,
    x1MetalnessMap,
    x1NormalMap,
    x1OpacityMap,
    x1RoughnessMap,
    x1ScalarMapAdjust,
    x1SheenMap,
    x1SpecularMap,
    x1ThicknessMap,
    x1TransmissionMap,
)


class MaterialMapNodeTests(unittest.TestCase):
    def test_cavity_map_separates_concave_and_convex_detail(self) -> None:
        image = torch.ones((1, 32, 32, 3), dtype=torch.float32) * 0.5
        image[:, :, 8:12, :] = 0.1
        image[:, :, 20:24, :] = 0.9

        node = x1CavityMap()
        concave_out, concave_mask, concave_info = node.run(
            image=image,
            source_mode="luma",
            polarity="concave",
            normalize_mode="auto_range",
            radius=2.5,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )
        convex_out, convex_mask, _ = node.run(
            image=image,
            source_mode="luma",
            polarity="convex",
            normalize_mode="auto_range",
            radius=2.5,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(concave_out[..., 0], concave_out[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(concave_out[..., 1], concave_out[..., 2], atol=1e-5))
        self.assertGreater(float(concave_mask[0, 16, 9].item()), float(concave_mask[0, 16, 2].item()) + 0.2)
        self.assertGreater(float(convex_mask[0, 16, 21].item()), float(convex_mask[0, 16, 9].item()) + 0.2)
        self.assertIn("x1CavityMap", concave_info)

    def test_metalness_map_prefers_bright_metal_like_regions(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[:, :, :8, :] = torch.tensor([0.92, 0.92, 0.92], dtype=torch.float32)
        image[:, :, 8:16, :] = torch.tensor([0.92, 0.76, 0.12], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.35, 0.28, 0.24], dtype=torch.float32)

        node = x1MetalnessMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_metalness",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        chrome_value = float(mask[0, 12, 4].item())
        gold_value = float(mask[0, 12, 12].item())
        diffuse_value = float(mask[0, 12, 20].item())

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2], atol=1e-5))
        self.assertGreater(chrome_value, diffuse_value)
        self.assertGreater(gold_value, diffuse_value)
        self.assertIn("x1MetalnessMap", info)

    def test_roughness_map_outputs_grayscale_and_tracks_detail(self) -> None:
        image = torch.ones((1, 32, 32, 3), dtype=torch.float32) * 0.35
        image[:, :, 16:, :] = 0.65
        image[:, 8:24, 20:28, :] = torch.tensor([0.9, 0.2, 0.2], dtype=torch.float32)

        node = x1RoughnessMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_roughness",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.5,
            detail_strength=0.8,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2], atol=1e-5))
        self.assertGreater(float(mask[0, 12, 22].item()), float(mask[0, 12, 10].item()))
        self.assertIn("x1RoughnessMap", info)

    def test_specular_map_prefers_bright_low_saturation_regions(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[:, :, :12, :] = torch.tensor([0.95, 0.95, 0.95], dtype=torch.float32)
        image[:, :, 12:, :] = torch.tensor([0.95, 0.05, 0.05], dtype=torch.float32)

        node = x1SpecularMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_specular",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            saturation_suppress=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        white_value = float(mask[0, 12, 6].item())
        red_value = float(mask[0, 12, 18].item())

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2], atol=1e-5))
        self.assertGreater(white_value, red_value)
        self.assertIn("x1SpecularMap", info)

    def test_opacity_map_prefers_alpha_when_present(self) -> None:
        image = torch.ones((1, 24, 24, 4), dtype=torch.float32)
        image[:, :, :, :3] *= torch.tensor([0.4, 0.7, 0.8], dtype=torch.float32)
        image[:, :, :12, 3] = 1.0
        image[:, :, 12:, 3] = 0.15

        node = x1OpacityMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_opacity",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        opaque_value = float(mask[0, 12, 6].item())
        transparent_value = float(mask[0, 12, 18].item())

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2], atol=1e-5))
        self.assertGreater(opaque_value, transparent_value + 0.5)
        self.assertIn("x1OpacityMap", info)

    def test_clearcoat_map_prefers_bright_neutral_smooth_regions(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.88, 0.88, 0.87], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.88, 0.22, 0.14], dtype=torch.float32)
        image[:, 4::2, 16::2, :] = torch.tensor([0.15, 0.95, 0.18], dtype=torch.float32)

        node = x1ClearcoatMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_clearcoat",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.5,
            detail_strength=0.35,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        smooth_value = float(mask[0, 16, 8].item())
        noisy_value = float(mask[0, 16, 24].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(smooth_value, noisy_value + 0.2)
        self.assertIn("x1ClearcoatMap", info)

    def test_clearcoat_roughness_map_prefers_scuffed_regions(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.90, 0.90, 0.89], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.72, 0.62, 0.56], dtype=torch.float32)
        image[:, 4::2, 16::2, :] = torch.tensor([0.96, 0.22, 0.18], dtype=torch.float32)

        node = x1ClearcoatRoughnessMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_clearcoat_roughness",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.5,
            detail_strength=0.45,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        smooth_value = float(mask[0, 16, 8].item())
        scuffed_value = float(mask[0, 16, 24].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(scuffed_value, smooth_value + 0.2)
        self.assertIn("x1ClearcoatRoughnessMap", info)

    def test_sheen_map_outputs_tinted_sheen_for_fabric_like_regions(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.18, 0.36, 0.82], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.72, 0.72, 0.72], dtype=torch.float32)
        image[:, 4::2, 16::2, :] = torch.tensor([0.95, 0.30, 0.24], dtype=torch.float32)

        node = x1SheenMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_sheen",
            tint_mode="source_color",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.5,
            detail_strength=0.25,
            tint_strength=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        cloth_value = float(mask[0, 16, 8].item())
        rough_value = float(mask[0, 16, 25].item())
        self.assertGreater(cloth_value, rough_value + 0.05)
        self.assertGreater(float(output[0, 16, 8, 2].item()), float(output[0, 16, 8, 0].item()))
        self.assertIn("x1SheenMap", info)

    def test_iridescence_map_prefers_bright_saturated_smooth_regions(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.92, 0.52, 0.88], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.34, 0.34, 0.34], dtype=torch.float32)
        image[:, 4::2, 16::2, :] = torch.tensor([0.08, 0.92, 0.16], dtype=torch.float32)

        node = x1IridescenceMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_iridescence",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.5,
            detail_strength=0.15,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        film_value = float(mask[0, 16, 8].item())
        diffuse_value = float(mask[0, 16, 25].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(film_value, diffuse_value + 0.1)
        self.assertIn("x1IridescenceMap", info)

    def test_anisotropy_map_outputs_preview_ready_direction_texture(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :16, :] = torch.tensor([0.82, 0.82, 0.82], dtype=torch.float32)
        image[:, :, 16:, :] = torch.tensor([0.22, 0.22, 0.22], dtype=torch.float32)

        node = x1AnisotropyMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_anisotropy",
            direction_mode="vertical",
            direction_angle_deg=0.0,
            center_x=0.5,
            center_y=0.5,
            gradient_radius=2.0,
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        strong_value = float(mask[0, 16, 8].item())
        weak_value = float(mask[0, 16, 24].item())
        self.assertGreater(strong_value, weak_value + 0.1)
        self.assertAlmostEqual(float(output[0, 16, 8, 0].item()), 0.5, places=2)
        self.assertGreater(float(output[0, 16, 8, 1].item()), 0.95)
        self.assertAlmostEqual(float(output[0, 16, 8, 2].item()), strong_value, places=4)
        self.assertIn("x1AnisotropyMap", info)

    def test_transmission_map_prefers_low_alpha_regions(self) -> None:
        image = torch.ones((1, 24, 24, 4), dtype=torch.float32)
        image[:, :, :, :3] = torch.tensor([0.72, 0.86, 0.95], dtype=torch.float32)
        image[:, :, :12, 3] = 1.0
        image[:, :, 12:, 3] = 0.08

        node = x1TransmissionMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_transmission",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        opaque_value = float(mask[0, 12, 6].item())
        glass_value = float(mask[0, 12, 18].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(glass_value, opaque_value + 0.6)
        self.assertIn("x1TransmissionMap", info)

    def test_thickness_map_handles_inverse_luma_and_source_mask(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[:, :, :12, :] = 0.12
        image[:, :, 12:, :] = 0.82
        source_mask = torch.zeros((1, 24, 24), dtype=torch.float32)
        source_mask[:, 6:18, 6:18] = 1.0

        node = x1ThicknessMap()
        output, mask, info = node.run(
            image=image,
            source_mode="inverse_luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )
        _, mask_driven, _ = node.run(
            image=image,
            source_mode="mask",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            detail_strength=0.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
            source_mask=source_mask,
        )

        thick_dark = float(mask[0, 12, 6].item())
        thin_bright = float(mask[0, 12, 18].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(thick_dark, thin_bright + 0.5)
        self.assertGreater(float(mask_driven[0, 12, 12].item()), 0.9)
        self.assertLess(float(mask_driven[0, 2, 2].item()), 0.1)
        self.assertIn("x1ThicknessMap", info)

    def test_scalar_map_adjust_remaps_inverts_and_respects_mask(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 1, 32, 1)
        image = ramp.repeat(1, 32, 1, 3)
        mask = torch.zeros((1, 32, 32), dtype=torch.float32)
        mask[:, :, 16:] = 1.0

        node = x1ScalarMapAdjust()
        output, out_mask, info = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            detail_radius=1.0,
            gamma=1.0,
            contrast=1.0,
            blur_radius=1.0,
            invert_values=True,
            mask=mask,
            mask_feather=0.0,
        )

        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertLess(float(out_mask[0, 16, 8].item()), 1e-5)
        self.assertGreater(float(out_mask[0, 16, 24].item()), 0.1)
        self.assertLess(float(output[0, 16, 30, 0].item()), float(output[0, 16, 18, 0].item()))
        self.assertIn("x1ScalarMapAdjust", info)

    def test_emissive_map_isolates_bright_saturated_regions(self) -> None:
        image = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        image[:, :, :, :] = torch.tensor([0.2, 0.2, 0.2], dtype=torch.float32)
        image[:, 10:22, 10:22, :] = torch.tensor([0.1, 0.9, 1.0], dtype=torch.float32)

        node = x1EmissiveMap()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_emissive",
            threshold=0.45,
            softness=0.08,
            saturation_gate=0.35,
            intensity=1.8,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        emissive_patch = output[0, 16, 16, :3]
        base_patch = output[0, 4, 4, :3]

        self.assertGreater(float(mask[0, 16, 16].item()), 0.6)
        self.assertLess(float(mask[0, 4, 4].item()), 0.1)
        self.assertGreater(float(emissive_patch[1].item()), float(base_patch[1].item()) + 0.4)
        self.assertGreater(float(emissive_patch[2].item()), float(emissive_patch[0].item()))
        self.assertIn("x1EmissiveMap", info)

    def test_color_region_mask_isolates_selected_hue(self) -> None:
        image = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        image[:, :, :12, :] = torch.tensor([0.92, 0.12, 0.10], dtype=torch.float32)
        image[:, :, 12:, :] = torch.tensor([0.12, 0.22, 0.92], dtype=torch.float32)

        node = x1ColorRegionMask()
        output, mask, info = node.run(
            image=image,
            color_preset="red",
            hue_width=0.08,
            saturation_min=0.2,
            value_min=0.05,
            softness=0.03,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        red_value = float(mask[0, 12, 6].item())
        blue_value = float(mask[0, 12, 18].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertTrue(torch.allclose(output[..., 1], output[..., 2], atol=1e-5))
        self.assertGreater(red_value, blue_value + 0.7)
        self.assertIn("x1ColorRegionMask", info)

    def test_edge_wear_mask_favors_bright_convex_edges(self) -> None:
        image = torch.ones((1, 36, 36, 3), dtype=torch.float32) * 0.34
        image[:, :, 17:19, :] = 0.95
        image[:, 8:28, 24:32, :] = torch.tensor([0.55, 0.18, 0.16], dtype=torch.float32)

        node = x1EdgeWearMask()
        output, mask, info = node.run(
            image=image,
            source_mode="combined_edge_wear",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            edge_radius=5.0,
            detail_radius=1.5,
            detail_strength=0.45,
            gamma=1.0,
            contrast=1.0,
            blur_radius=0.0,
            mask_feather=0.0,
        )

        edge_value = float(mask[0, 18, 18].item())
        flat_value = float(mask[0, 18, 8].item())
        colored_patch_value = float(mask[0, 18, 28].item())
        self.assertTrue(torch.allclose(output[..., 0], output[..., 1], atol=1e-5))
        self.assertGreater(edge_value, flat_value + 0.2)
        self.assertGreater(edge_value, colored_patch_value)
        self.assertIn("x1EdgeWearMask", info)

    def test_normal_map_respects_mask_and_convention(self) -> None:
        ramp = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 32, 1, 1)
        image = ramp.repeat(1, 1, 32, 3)
        mask = torch.zeros((1, 32, 32), dtype=torch.float32)
        mask[:, :, 16:] = 1.0

        node = x1NormalMap()
        out_gl, matte_gl, info = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            blur_radius=0.0,
            strength=8.0,
            convention="opengl",
            mask=mask,
            mask_feather=0.0,
        )
        out_dx, _, _ = node.run(
            image=image,
            source_mode="luma",
            normalize_mode="manual_range",
            value_min=0.0,
            value_max=1.0,
            gamma=1.0,
            blur_radius=0.0,
            strength=8.0,
            convention="directx",
            mask=mask,
            mask_feather=0.0,
        )

        flat_region = out_gl[0, 8, 8, :3]
        masked_region = out_gl[0, 8, 24, :3]

        self.assertTrue(torch.allclose(flat_region, torch.tensor([0.5, 0.5, 1.0]), atol=1e-4))
        self.assertGreater(float(masked_region[2].item()), 0.7)
        self.assertLess(float(matte_gl[0, 8, 8].item()), 1e-5)
        self.assertNotAlmostEqual(float(out_gl[0, 24, 24, 1].item()), float(out_dx[0, 24, 24, 1].item()), places=4)
        self.assertIn("x1NormalMap", info)


if __name__ == "__main__":
    unittest.main()
