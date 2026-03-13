import json
import shutil
import struct
import sys
from io import BytesIO
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.lib.material_preview_export import _build_sphere, resolve_material_preview_output_path  # noqa: E402
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


def _read_glb_json(model_path: Path) -> dict:
    payload = model_path.read_bytes()
    if len(payload) < 20:
        raise AssertionError(f"GLB payload was unexpectedly short: {model_path}")

    magic, version, total_length = struct.unpack_from("<III", payload, 0)
    if magic != 0x46546C67:
        raise AssertionError(f"Unexpected GLB magic for {model_path}: {magic:#x}")
    if version != 2:
        raise AssertionError(f"Unexpected GLB version for {model_path}: {version}")
    if total_length != len(payload):
        raise AssertionError(f"GLB length header mismatch for {model_path}")

    json_length, json_chunk_type = struct.unpack_from("<II", payload, 12)
    if json_chunk_type != 0x4E4F534A:
        raise AssertionError(f"First GLB chunk was not JSON for {model_path}")

    json_start = 20
    json_end = json_start + json_length
    return json.loads(payload[json_start:json_end].decode("utf-8"))


def _read_glb_image(model_path: Path, image_index: int) -> np.ndarray:
    payload = model_path.read_bytes()
    json_length, _ = struct.unpack_from("<II", payload, 12)
    json_start = 20
    json_end = json_start + json_length
    gltf = json.loads(payload[json_start:json_end].decode("utf-8"))

    bin_header = json_end
    bin_length, bin_chunk_type = struct.unpack_from("<II", payload, bin_header)
    if bin_chunk_type != 0x004E4942:
        raise AssertionError(f"Second GLB chunk was not BIN for {model_path}")
    bin_start = bin_header + 8
    bin_payload = payload[bin_start : bin_start + bin_length]

    image_entry = gltf["images"][int(image_index)]
    view = gltf["bufferViews"][int(image_entry["bufferView"])]
    byte_offset = int(view.get("byteOffset", 0))
    byte_length = int(view["byteLength"])
    png_bytes = bin_payload[byte_offset : byte_offset + byte_length]
    return (np.asarray(Image.open(BytesIO(png_bytes)).convert("RGB"), dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def _read_glb_accessor(model_path: Path, accessor_index: int) -> np.ndarray:
    payload = model_path.read_bytes()
    json_length, _ = struct.unpack_from("<II", payload, 12)
    json_start = 20
    json_end = json_start + json_length
    gltf = json.loads(payload[json_start:json_end].decode("utf-8"))

    bin_header = json_end
    bin_length, bin_chunk_type = struct.unpack_from("<II", payload, bin_header)
    if bin_chunk_type != 0x004E4942:
        raise AssertionError(f"Second GLB chunk was not BIN for {model_path}")
    bin_start = bin_header + 8
    bin_payload = payload[bin_start : bin_start + bin_length]

    accessor = gltf["accessors"][int(accessor_index)]
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    component_type = int(accessor["componentType"])
    accessor_type = str(accessor["type"])
    count = int(accessor["count"])
    components = {
        "SCALAR": 1,
        "VEC2": 2,
        "VEC3": 3,
        "VEC4": 4,
    }[accessor_type]
    dtype = {
        5123: np.uint16,
        5126: np.float32,
    }[component_type]

    byte_offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    itemsize = np.dtype(dtype).itemsize
    byte_length = count * components * itemsize
    raw = bin_payload[byte_offset : byte_offset + byte_length]
    return np.frombuffer(raw, dtype=dtype).reshape(count, components)


class MaterialPreviewNodeTests(unittest.TestCase):
    def test_preview_shader_ball_winding_matches_exported_normals(self) -> None:
        positions, normals, _, indices = _build_sphere(uv_scale=1.0)
        self.assertGreaterEqual(int(positions.shape[0]), 8000)
        triangles = indices.reshape(-1, 3)

        sampled = triangles[:: max(1, len(triangles) // 64)]
        alignment = []
        for tri in sampled:
            a, b, c = positions[int(tri[0])], positions[int(tri[1])], positions[int(tri[2])]
            face_normal = np.cross(b - a, c - a)
            face_length = float(np.linalg.norm(face_normal))
            if face_length <= 1e-8:
                continue
            face_normal = face_normal / face_length
            vertex_normal = np.mean(normals[[int(tri[0]), int(tri[1]), int(tri[2])]], axis=0)
            vertex_length = float(np.linalg.norm(vertex_normal))
            if vertex_length <= 1e-8:
                continue
            vertex_normal = vertex_normal / vertex_length
            alignment.append(float(np.dot(face_normal, vertex_normal)))

        self.assertTrue(alignment)
        self.assertGreater(min(alignment), 0.5)

    def test_native_3d_bridge_resolves_load3d_asset(self) -> None:
        assets = resolve_native_3d_assets()
        self.assertIn("load3d_component_asset", assets)
        self.assertIn("use_load3d_asset", assets)
        self.assertTrue(str(assets["load3d_component_asset"]).startswith("/assets/Load3D-"))
        self.assertTrue(str(assets["use_load3d_asset"]).startswith("/assets/useLoad3d-"))

    def test_preview_material_builds_previewable_glb_with_expected_maps(self) -> None:
        base = torch.ones((1, 24, 24, 4), dtype=torch.float32) * torch.tensor([0.72, 0.25, 0.12, 1.0], dtype=torch.float32)
        base[:, 6:18, 6:18, 3] = 0.4
        roughness = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.65
        metalness = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        metalness[:, :, :12, :] = 0.9
        specular = torch.ones((1, 24, 24, 3), dtype=torch.float32) * torch.tensor([0.95, 0.82, 0.55], dtype=torch.float32)
        height = torch.linspace(0.0, 1.0, 24, dtype=torch.float32).view(1, 24, 1, 1).repeat(1, 1, 24, 3)
        ao = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.55
        emissive = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        emissive[:, 8:16, 8:16, :] = torch.tensor([0.0, 0.65, 1.0], dtype=torch.float32)
        clearcoat = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.8
        clearcoat_roughness = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.2
        anisotropy = torch.ones((1, 24, 24, 3), dtype=torch.float32) * torch.tensor([1.0, 0.5, 0.82], dtype=torch.float32)
        sheen_color = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        sheen_color[:, :, :, :] = torch.tensor([0.18, 0.36, 0.82], dtype=torch.float32)
        sheen_roughness = torch.ones((1, 24, 24, 3), dtype=torch.float32) * 0.42
        transmission = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        transmission[:, :, 12:, :] = 0.85
        thickness = torch.linspace(0.1, 0.9, 24, dtype=torch.float32).view(1, 24, 1, 1).repeat(1, 1, 24, 3)
        iridescence = torch.zeros((1, 24, 24, 3), dtype=torch.float32)
        iridescence[:, 4:20, 4:20, :] = 0.78
        iridescence_thickness = torch.linspace(0.0, 1.0, 24, dtype=torch.float32).view(1, 1, 24, 1).repeat(1, 24, 1, 3)

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
            advanced_settings_json='{"ior": 1.33, "attenuation_distance": 0.45, "attenuation_color": [0.72, 0.9, 1.0], "anisotropy_rotation": 0.25, "sheen_roughness_default": 0.35, "iridescence_ior": 1.22, "iridescence_thickness_min": 120.0, "iridescence_thickness_max": 650.0}',
            base_color=base,
            roughness=roughness,
            metalness=metalness,
            specular=specular,
            height=height,
            ao=ao,
            emissive=emissive,
            clearcoat=clearcoat,
            clearcoat_roughness=clearcoat_roughness,
            anisotropy=anisotropy,
            sheen_color=sheen_color,
            sheen_roughness=sheen_roughness,
            transmission=transmission,
            thickness=thickness,
            iridescence=iridescence,
            iridescence_thickness=iridescence_thickness,
        )

        model_path = resolve_material_preview_output_path(model_file)
        self.addCleanup(_cleanup_preview_family, model_path)

        self.assertTrue(model_file.endswith(".glb"))
        self.assertTrue(model_path.is_file())
        self.assertEqual(model_path.suffix, ".glb")
        self.assertIn("height->normal", info)
        self.assertIn("specular->roughness", info)

        payload = _read_glb_json(model_path)
        material = payload["materials"][0]
        pbr = material["pbrMetallicRoughness"]
        extensions = material.get("extensions", {})

        self.assertEqual(material["alphaMode"], "BLEND")
        self.assertIn("baseColorTexture", pbr)
        self.assertIn("metallicRoughnessTexture", pbr)
        self.assertIn("normalTexture", material)
        self.assertIn("occlusionTexture", material)
        self.assertIn("emissiveTexture", material)
        self.assertIn("TANGENT", payload["meshes"][0]["primitives"][0]["attributes"])
        self.assertIn("KHR_materials_specular", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_clearcoat", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_anisotropy", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_sheen", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_transmission", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_volume", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_iridescence", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_ior", payload.get("extensionsUsed", []))
        self.assertIn("KHR_materials_specular", extensions)
        self.assertIn("KHR_materials_clearcoat", extensions)
        self.assertIn("KHR_materials_anisotropy", extensions)
        self.assertIn("KHR_materials_sheen", extensions)
        self.assertIn("KHR_materials_transmission", extensions)
        self.assertIn("KHR_materials_volume", extensions)
        self.assertIn("KHR_materials_iridescence", extensions)
        self.assertEqual(extensions["KHR_materials_ior"]["ior"], 1.33)
        self.assertIn("specularTexture", extensions["KHR_materials_specular"])
        self.assertIn("specularColorTexture", extensions["KHR_materials_specular"])
        self.assertIn("clearcoatTexture", extensions["KHR_materials_clearcoat"])
        self.assertIn("clearcoatRoughnessTexture", extensions["KHR_materials_clearcoat"])
        self.assertIn("anisotropyTexture", extensions["KHR_materials_anisotropy"])
        self.assertEqual(extensions["KHR_materials_anisotropy"]["anisotropyRotation"], 0.25)
        self.assertIn("sheenColorTexture", extensions["KHR_materials_sheen"])
        self.assertIn("sheenRoughnessTexture", extensions["KHR_materials_sheen"])
        self.assertIn("transmissionTexture", extensions["KHR_materials_transmission"])
        self.assertIn("thicknessTexture", extensions["KHR_materials_volume"])
        self.assertIn("iridescenceTexture", extensions["KHR_materials_iridescence"])
        self.assertIn("iridescenceThicknessTexture", extensions["KHR_materials_iridescence"])
        self.assertEqual(extensions["KHR_materials_iridescence"]["iridescenceIor"], 1.22)
        self.assertEqual(extensions["KHR_materials_iridescence"]["iridescenceThicknessMinimum"], 120.0)
        self.assertEqual(extensions["KHR_materials_iridescence"]["iridescenceThicknessMaximum"], 650.0)
        self.assertGreaterEqual(len(payload["images"]), 16)
        self.assertNotIn("uri", payload["buffers"][0])

        for image_entry in payload["images"]:
            self.assertEqual(image_entry.get("mimeType"), "image/png")
            self.assertIn("bufferView", image_entry)
            self.assertNotIn("uri", image_entry)

        self.assertFalse(list(model_path.parent.glob(f"{model_path.stem}_*.png")))

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

        payload = _read_glb_json(model_path)
        self.assertEqual(payload["meshes"][0]["primitives"][0]["material"], 0)
        self.assertEqual(len(payload["textures"]), 3)
        self.assertNotIn("extensionsUsed", payload)
        self.assertNotIn("extensions", payload["materials"][0])
        self.assertNotIn("uri", payload["buffers"][0])
        self.assertTrue(all("bufferView" in image for image in payload["images"]))

    def test_preview_material_converts_directx_normals_for_gltf_preview(self) -> None:
        normal = torch.ones((1, 8, 8, 3), dtype=torch.float32) * torch.tensor([0.5, 0.25, 1.0], dtype=torch.float32)
        node = x1PreviewMaterial()

        directx_file, _ = node.build(
            preview_mesh="plane",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            normal_convention="directx",
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="dx_normals",
            normal=normal,
        )
        directx_path = resolve_material_preview_output_path(directx_file)
        self.addCleanup(_cleanup_preview_family, directx_path)

        opengl_file, _ = node.build(
            preview_mesh="plane",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            normal_convention="opengl",
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="gl_normals",
            normal=normal,
        )
        opengl_path = resolve_material_preview_output_path(opengl_file)
        self.addCleanup(_cleanup_preview_family, opengl_path)

        directx_normal_image = _read_glb_image(directx_path, 1)
        opengl_normal_image = _read_glb_image(opengl_path, 1)

        self.assertGreater(float(directx_normal_image[..., 1].mean()), 0.70)
        self.assertLess(float(opengl_normal_image[..., 1].mean()), 0.30)

    def test_preview_material_height_displaces_preview_mesh_geometry(self) -> None:
        node = x1PreviewMaterial()
        height = torch.linspace(0.0, 1.0, 32, dtype=torch.float32).view(1, 32, 1, 1).repeat(1, 1, 32, 3)

        displaced_file, displaced_info = node.build(
            preview_mesh="shader_ball",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            height_to_normal_strength=6.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="height_displacement",
            height=height,
        )
        displaced_path = resolve_material_preview_output_path(displaced_file)
        self.addCleanup(_cleanup_preview_family, displaced_path)

        flat_file, _ = node.build(
            preview_mesh="shader_ball",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="height_flat",
        )
        flat_path = resolve_material_preview_output_path(flat_file)
        self.addCleanup(_cleanup_preview_family, flat_path)

        displaced_positions = _read_glb_accessor(displaced_path, 0).astype(np.float32)
        flat_positions = _read_glb_accessor(flat_path, 0).astype(np.float32)
        displaced_radius = np.linalg.norm(displaced_positions, axis=1)

        self.assertIn("height->displacement", displaced_info)
        self.assertGreater(float(displaced_radius.max() - displaced_radius.min()), 0.05)
        self.assertGreater(float(np.mean(np.abs(displaced_positions - flat_positions))), 0.01)

    def test_preview_material_supports_normal_driven_displacement(self) -> None:
        node = x1PreviewMaterial()
        normal = torch.ones((1, 24, 24, 3), dtype=torch.float32) * torch.tensor([0.85, 0.50, 0.85], dtype=torch.float32)

        displaced_file, displaced_info = node.build(
            preview_mesh="shader_ball",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            normal_convention="opengl",
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="normal_displacement",
            advanced_settings_json='{"displacement_mode": "normal", "normal_displacement_strength": 0.08}',
            normal=normal,
        )
        displaced_path = resolve_material_preview_output_path(displaced_file)
        self.addCleanup(_cleanup_preview_family, displaced_path)

        flat_file, _ = node.build(
            preview_mesh="shader_ball",
            uv_scale=1.0,
            roughness_default=0.5,
            metalness_default=0.0,
            normal_strength=1.0,
            normal_convention="opengl",
            height_to_normal_strength=0.0,
            emissive_strength=1.0,
            alpha_mode="auto",
            asset_label="normal_flat",
            normal=normal,
        )
        flat_path = resolve_material_preview_output_path(flat_file)
        self.addCleanup(_cleanup_preview_family, flat_path)

        displaced_positions = _read_glb_accessor(displaced_path, 0).astype(np.float32)
        flat_positions = _read_glb_accessor(flat_path, 0).astype(np.float32)

        self.assertIn("normal->displacement", displaced_info)
        self.assertGreater(float(np.mean(np.abs(displaced_positions - flat_positions))), 0.002)


if __name__ == "__main__":
    unittest.main()
