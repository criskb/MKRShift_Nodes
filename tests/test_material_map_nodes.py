import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.material_map_nodes import x1MetalnessMap, x1NormalMap, x1RoughnessMap, x1SpecularMap  # noqa: E402


class MaterialMapNodeTests(unittest.TestCase):
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
