import json
import shutil
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.lib.material_preview_export import resolve_material_preview_output_path  # noqa: E402
from MKRShift_Nodes.lib.native_3d_bridge import resolve_native_3d_assets  # noqa: E402
from MKRShift_Nodes.nodes.material_preview_nodes import x1PreviewMaterial  # noqa: E402


def _cleanup_preview_family(model_path: Path) -> None:
    stem = model_path.stem
    for sibling in model_path.parent.glob(f"{stem}*"):
        try:
            sibling.unlink()
        except Exception:
            pass
    try:
        relative = model_path.parent.relative_to(model_path.parents[2])
    except Exception:
        relative = None
    if relative and str(relative).replace("\\", "/") == "mkrshift/material_preview":
        try:
            shutil.rmtree(model_path.parent)
        except Exception:
            pass


class MaterialPreviewNodeTests(unittest.TestCase):
    def test_native_3d_bridge_resolves_load3d_asset(self) -> None:
        assets = resolve_native_3d_assets()
        self.assertIn("load3d_component_asset", assets)
        self.assertTrue(str(assets["load3d_component_asset"]).startswith("/assets/Load3D-"))

    def test_preview_material_builds_previewable_gltf_with_expected_maps(self) -> None:
        base = torch.ones((1, 24, 24, 4), dtype=torch.float32) * torch.tensor([0.72, 0.25, 0.12, 1.0], dtype=torch.float32)
        base[:, 6:18, 6:18, 3] = 0.4
        roughness = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.65
        metalness = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        metalness[:, :, :12, :] = 0.9
        specular = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.75
        height = torch.linspace(0.0, 1.0, 24, dtype=torch.float32).view(1, 24, 1, 1).repeat(1, 1, 24, 3)
        ao = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.55
        emissive = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        emissive[:, 8:16, 8:16, :] = torch.tensor([0.0, 0.65, 1.0], dtype=torch.float32)

        node = x1PreviewMaterial()
        model_file, info = node.build(
            preview_mesh="shader_ball",
            uv_scale=2.0,
            roughness_default=0.55,
            metalness_default=0.0,
            normal_strength=1.35,
            height_to_normal_strength=8.0,
            emissive_strength=1.5,
            alpha_mode="auto",
            asset_label="lookdev_test",
            base_color=base,
            roughness=roughness,
            metalness=metalness,
            specular=specular,
            height=height,
            ao=ao,
            emissive=emissive,
        )

        model_path = resolve_material_preview_output_path(model_file)
        self.addCleanup(_cleanup_preview_family, model_path)

        self.assertTrue(model_file.endswith("[output]"))
        self.assertTrue(model_path.is_file())
        self.assertIn("height->normal", info)
        self.assertIn("specular->roughness", info)

        payload = json.loads(model_path.read_text(encoding="utf-8"))
        material = payload["materials"][0]
        pbr = material["pbrMetallicRoughness"]

        self.assertEqual(material["alphaMode"], "BLEND")
        self.assertIn("baseColorTexture", pbr)
        self.assertIn("metallicRoughnessTexture", pbr)
        self.assertIn("normalTexture", material)
        self.assertIn("occlusionTexture", material)
        self.assertIn("emissiveTexture", material)
        self.assertGreaterEqual(len(payload["images"]), 5)

        for image_entry in payload["images"]:
            image_path = model_path.parent / image_entry["uri"]
            self.assertTrue(image_path.is_file(), f"Missing preview texture: {image_path}")

    def test_preview_material_supports_defaults_only_export(self) -> None:
        node = x1PreviewMaterial()
        model_file, info = node.build(
            preview_mesh="cube",
            uv_scale=1.0,
            roughness_default=0.35,
            metalness_default=0.15,
            normal_strength=1.0,
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="defaults_only",
        )

        model_path = resolve_material_preview_output_path(model_file)
        self.addCleanup(_cleanup_preview_family, model_path)

        self.assertTrue(model_path.is_file())
        self.assertIn("defaults_only", model_file)
        self.assertIn("defaults_only", info or "")

        payload = json.loads(model_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["meshes"][0]["primitives"][0]["material"], 0)
        self.assertEqual(len(payload["textures"]), 3)


if __name__ == "__main__":
    unittest.main()
