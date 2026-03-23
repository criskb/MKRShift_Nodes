import importlib
import json
import socketserver
import sys
import tempfile
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import torch
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.mask_nodes import x1MaskGen  # noqa: E402
from MKRShift_Nodes.nodes.bridge_nodes import (  # noqa: E402
    MKRBlenderCameraShot,
    MKRBlenderMaterialImport,
    MKRBlenderMaterialReturnPlan,
    MKRBlenderReturnPlan,
    MKRBlenderSceneImport,
)
from MKRShift_Nodes.nodes.touchdesigner_bridge_nodes import MKRTouchDesignerFramePlan, MKRTouchDesignerImport  # noqa: E402
from MKRShift_Nodes.nodes.tixl_bridge_nodes import MKRTiXLFramePlan, MKRTiXLImport  # noqa: E402
from MKRShift_Nodes.nodes.nuke_bridge_nodes import MKRNukeReadPlan, MKRNukeScriptImport  # noqa: E402
from MKRShift_Nodes.nodes.adobe_bridge_nodes import (  # noqa: E402
    MKRAfterEffectsCompImport,
    MKRAfterEffectsRenderPlan,
    MKRPhotoshopDocumentImport,
    MKRPhotoshopExportPlan,
    MKRPremiereExportPlan,
    MKRPremiereSequenceImport,
)
from MKRShift_Nodes.nodes.dcc_bridge_nodes import (  # noqa: E402
    MKRAffinityDocumentImport,
    MKRAffinityExportPlan,
    MKRAffinityPhotoshopPluginPlan,
    MKRFusion360SceneImport,
    MKRFusion360TexturePlan,
    MKRMayaMaterialPlan,
    MKRMayaSceneImport,
)
from MKRShift_Nodes.nodes.host_3d_image_bridge_nodes import (  # noqa: E402
    MKRBlenderImageImport,
    MKRBlenderImageOutputPlan,
    MKRFusion360ImageImport,
    MKRFusion360ImageOutputPlan,
    MKRMayaImageImport,
    MKRMayaImageOutputPlan,
)
from MKRShift_Nodes.nodes.host_image_runtime_nodes import (  # noqa: E402
    MKRAfterEffectsImageOutput,
    MKRBlenderImageOutput,
    MKRFusion360ImageOutput,
    MKRMayaImageOutput,
    MKRNukeImageOutput,
    MKRPhotoshopImageOutput,
    MKRPremiereImageOutput,
)
from MKRShift_Nodes.nodes.host_plan_runtime_nodes import (  # noqa: E402
    MKRAffinityExportOutput,
    MKRAfterEffectsRenderOutput,
    MKRBlenderReturnOutput,
    MKRFusion360TextureOutput,
    MKRMayaMaterialOutput,
    MKRNukeReadOutput,
    MKRPhotoshopExportOutput,
    MKRPremiereExportOutput,
)
from MKRShift_Nodes.nodes.host_2d_image_bridge_nodes import (  # noqa: E402
    MKRAfterEffectsImageImport,
    MKRAfterEffectsImageOutputPlan,
    MKRNukeImageImport,
    MKRNukeImageOutputPlan,
    MKRPhotoshopImageImport,
    MKRPhotoshopImageOutputPlan,
    MKRPremiereImageImport,
    MKRPremiereImageOutputPlan,
)
from MKRShift_Nodes.nodes.network_addon_nodes import (  # noqa: E402
    MKRAddonEndpointPlan,
    MKRHTTPWebhookPlan,
    MKRNDIStreamPlan,
    MKROSCMessagePlan,
    MKRSpoutSenderPlan,
    MKRSyphonSenderPlan,
    MKRTCPBridgePlan,
    MKRWatchFolderPlan,
    MKRWebSocketBridgePlan,
)
from MKRShift_Nodes.nodes.network_addon_runtime_nodes import (  # noqa: E402
    MKRAddonEndpointPoll,
    MKRAddonEndpointSubmit,
    MKRHTTPWebhookSend,
    MKROSCSend,
    MKRTCPBridgeSend,
    MKRWatchFolderWrite,
)
from MKRShift_Nodes.nodes.character_state_nodes import MKRCharacterState, MKROutfitSet  # noqa: E402
from MKRShift_Nodes.nodes.pose_studio_nodes import MKRPoseStudio  # noqa: E402
from MKRShift_Nodes.nodes.core_nodes import AxBCompare  # noqa: E402
from MKRShift_Nodes.nodes.inspect_compare_nodes import MKRBatchDifferencePreview  # noqa: E402
from MKRShift_Nodes.nodes.presave_media_nodes import MKRPresaveVideo  # noqa: E402
from MKRShift_Nodes.nodes.publish_manifest_nodes import (  # noqa: E402
    MKRPublishAssetManifest,
    MKRPublishCopyAtIndex,
    MKRPublishCopyDeck,
    MKRPublishManifestAtIndex,
)
from MKRShift_Nodes.nodes.publish_nodes import MKRPublishEndCard, MKRPublishPromoFrame  # noqa: E402
from MKRShift_Nodes.nodes.vfx_composite_nodes import x1EdgeAberration, x1LightWrapComposite  # noqa: E402
from MKRShift_Nodes.nodes.gcode_analysis_nodes import MKRGCodePlanAnalyzer  # noqa: E402
from MKRShift_Nodes.nodes.gcode_input_nodes import MKRGCodeLoadMeshModel, MKRGCodeOrcaProfileLoader  # noqa: E402
from MKRShift_Nodes.nodes.gcode_modify_nodes import (  # noqa: E402
    MKRGCodeBedMeshCompensate,
    MKRGCodeCalibrationTower,
    MKRGCodeConditionalInjector,
)
from MKRShift_Nodes.nodes.gcode_nodes import (  # noqa: E402
    MKRGCodeExport,
    MKRGCodeHeightmapPlate,
    MKRGCodePrinterProfile,
    MKRGCodeSpiralVase,
)
from MKRShift_Nodes.nodes.gcode_preview_nodes import MKRGCodePreview  # noqa: E402
from MKRShift_Nodes.nodes.gcode_slicer_nodes import MKRGCodeExternalSlicer  # noqa: E402
from MKRShift_Nodes.nodes.image_layout_nodes import MKRImageCombineGrid, MKRImageSplitGrid  # noqa: E402
from MKRShift_Nodes.nodes.studio_nodes import (  # noqa: E402
    MKRStudioCompareBoard,
    MKRStudioContactSheet,
    MKRStudioDeliveryPlan,
    MKRStudioReviewBurnIn,
    MKRStudioReviewFrame,
    MKRStudioSlate,
)
from MKRShift_Nodes.nodes.studio_selection_nodes import MKRStudioSelectionSet  # noqa: E402


class FeatureImprovementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = REPO_ROOT / ".temp"
        self._before = {path.name for path in self._temp_dir.glob("*")} if self._temp_dir.is_dir() else set()

    def tearDown(self) -> None:
        if not self._temp_dir.is_dir():
            return
        for path in self._temp_dir.glob("*"):
            if path.name in self._before:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue

    def _write_temp_text(self, name: str, text: str) -> Path:
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        path = self._temp_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def _write_temp_orca_bundle(self, name: str = "orca_bundle.zip") -> Path:
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        path = self._temp_dir / name
        machine = {
            "id": "printer_alpha",
            "name": "Printer Alpha",
            "type": "machine",
            "printable_area": [[0, 0], [220, 0], [220, 220], [0, 220]],
            "printable_height": 250,
            "nozzle_diameter": 0.4,
            "machine_start_gcode": "G28",
            "machine_end_gcode": "M84",
        }
        filament = {
            "id": "pla_std",
            "name": "PLA Standard",
            "type": "filament",
            "filament_diameter": 1.75,
            "temperature": 215,
            "bed_temperature": 60,
        }
        process = {
            "id": "draft_028",
            "name": "Draft 0.28",
            "type": "process",
            "layer_height": 0.28,
            "print_speed": 60,
            "travel_speed": 180,
            "retraction_length": 0.8,
            "retraction_speed": 35,
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("machine.orca_printer", json.dumps(machine))
            archive.writestr("filament.orca_filament", json.dumps(filament))
            archive.writestr("process.json", json.dumps(process))
        return path

    def test_publish_asset_manifest_builds_rows_from_batch(self) -> None:
        manifest_node = MKRPublishAssetManifest()
        pick_node = MKRPublishManifestAtIndex()
        frames = torch.zeros((3, 48, 64, 3), dtype=torch.float32)

        manifest_json, manifest_csv, manifest_md, summary_json, count = manifest_node.build(
            images=frames,
            project="Studio Test",
            asset_prefix="hero-launch",
            channel="release",
            extension="jpg",
            start_index=12,
            title_prefix="Drop",
            tags_csv="mkrshift,launch",
            alt_template="{project} | {title} | {filename} | {ratio}",
            titles_csv="Hero\nDetail\nProcess",
            shot_labels_csv="wide,detail,process",
        )
        row_json, filename, title, alt_text, tags_csv = pick_node.pick(
            manifest_json=manifest_json,
            index=13,
            index_mode="Display Index",
        )

        manifest = json.loads(manifest_json)
        summary = json.loads(summary_json)
        row = json.loads(row_json)

        self.assertEqual(count, 3)
        self.assertEqual(summary["ratio"], "4:3")
        self.assertEqual(manifest["rows"][0]["filename"], "hero-launch_012.jpg")
        self.assertIn("Hero", manifest_md)
        self.assertIn("hero-launch_013.jpg", manifest_csv)
        self.assertEqual(filename, "hero-launch_013.jpg")
        self.assertEqual(title, "Detail")
        self.assertIn("Studio Test", alt_text)
        self.assertEqual(row["shot_label"], "detail")
        self.assertEqual(tags_csv, "mkrshift, launch")

    def test_character_state_and_outfit_set_build_persistent_character_record(self) -> None:
        state_node = MKRCharacterState()
        outfit_node = MKROutfitSet()

        state_json, positive_anchor, negative_anchor, summary_json = state_node.build(
            character_name="Kaia Vale",
            core_identity_prompt="athletic sci-fi courier heroine",
            body_notes="long-limbed, agile runner silhouette",
            face_notes="sharp eyes, asymmetrical fringe",
            style_anchor="cinematic concept art",
            consistency_tokens_csv="orange streak hair, split jacket, courier harness",
            avoid_tokens_csv="helmet, bulky armor",
            default_negative="off-model face, unstable proportions",
            notes="Keep the profile read strong.",
        )

        updated_state_json, outfit_json, resolved_prompt, outfit_summary_json = outfit_node.build(
            character_state_json=state_json,
            outfit_name="Field Jacket",
            outfit_prompt="weathered field jacket over utility bodysuit",
            silhouette_notes="broad shoulders tapering to compact waist kit",
            material_notes="waxed fabric, matte armor inserts, worn straps",
            accessories_csv="satchel, forearm radio",
            palette_csv="burnt orange, charcoal, dust gray",
            mood_hint="ready for a hard run",
            match_strength=0.88,
            set_as_default=True,
        )

        state = json.loads(updated_state_json)
        outfit = json.loads(outfit_json)
        summary = json.loads(summary_json)
        outfit_summary = json.loads(outfit_summary_json)

        self.assertEqual(summary["character_slug"], "kaia-vale")
        self.assertIn("athletic sci-fi courier heroine", positive_anchor)
        self.assertIn("helmet", negative_anchor)
        self.assertEqual(state["default_outfit"], "Field Jacket")
        self.assertEqual(len(state["outfits"]), 1)
        self.assertEqual(outfit["accessories"], ["satchel", "forearm radio"])
        self.assertIn("weathered field jacket", resolved_prompt)
        self.assertEqual(outfit_summary["match_strength"], 0.88)

    def test_outfit_set_updates_existing_named_outfit(self) -> None:
        state_node = MKRCharacterState()
        outfit_node = MKROutfitSet()

        state_json, _, _, _ = state_node.build(
            character_name="Kaia Vale",
            core_identity_prompt="athletic sci-fi courier heroine",
            body_notes="runner silhouette",
            face_notes="sharp eyes",
            style_anchor="cinematic concept art",
        )
        state_json, _, _, _ = outfit_node.build(
            character_state_json=state_json,
            outfit_name="Field Jacket",
            outfit_prompt="first pass jacket",
            silhouette_notes="clear torso read",
            material_notes="matte textiles",
            accessories_csv="satchel",
            palette_csv="orange, gray",
            mood_hint="focused",
            match_strength=0.8,
            set_as_default=True,
        )
        state_json, outfit_json, _, _ = outfit_node.build(
            character_state_json=state_json,
            outfit_name="Field Jacket",
            outfit_prompt="updated jacket with reinforced collar",
            silhouette_notes="strong upper body read",
            material_notes="reinforced canvas and matte plating",
            accessories_csv="satchel, radio",
            palette_csv="orange, charcoal",
            mood_hint="alert",
            match_strength=0.91,
            set_as_default=False,
        )

        state = json.loads(state_json)
        outfit = json.loads(outfit_json)
        self.assertEqual(len(state["outfits"]), 1)
        self.assertEqual(outfit["prompt"], "updated jacket with reinforced collar")
        self.assertEqual(outfit["accessories"], ["satchel", "radio"])
        self.assertEqual(state["default_outfit"], "Field Jacket")

    def test_blender_scene_import_normalizes_camera_and_pose_payloads(self) -> None:
        scene_node = MKRBlenderSceneImport()
        payload = {
            "scene_name": "Shot010",
            "frame_current": 48,
            "camera": {
                "name": "RenderCam",
                "lens_mm": 85,
                "resolution": {"x": 2048, "y": 858},
                "location": [1.2, -3.4, 1.8],
                "rotation_euler_deg": [82.0, 0.0, 17.0],
            },
            "pose": {
                "armature_name": "HeroRig",
                "bones": [
                    {"name": "root", "location": [0, 0, 0], "rotation_euler_deg": [0, 0, 0], "scale": [1, 1, 1]},
                    {"name": "spine", "parent": "root", "location": [0, 0.1, 0], "rotation_euler_deg": [5, 0, 0], "scale": [1, 1, 1]},
                ],
            },
        }

        scene_json, camera_json, pose_json, camera_prompt, summary_json = scene_node.build(
            bridge_payload_json=json.dumps(payload),
            character_state_json=json.dumps({"character_name": "Kaia Vale"}),
        )

        scene = json.loads(scene_json)
        camera = json.loads(camera_json)
        pose = json.loads(pose_json)
        summary = json.loads(summary_json)

        self.assertEqual(scene["scene_name"], "Shot010")
        self.assertEqual(camera["lens_mm"], 85.0)
        self.assertEqual(camera["resolution"]["ratio"], "1024:429")
        self.assertEqual(pose["bone_count"], 2)
        self.assertIn("Kaia Vale", camera_prompt)
        self.assertEqual(summary["pose_bone_count"], 2)

    def test_blender_camera_shot_builds_shot_recipe(self) -> None:
        node = MKRBlenderCameraShot()
        camera_prompt, shot_recipe_json, summary_json = node.build(
            camera_json=json.dumps(
                {
                    "name": "CloseCam",
                    "lens_mm": 35,
                    "resolution": {"x": 1920, "y": 1080},
                    "location": [0.2, -2.1, 1.5],
                    "rotation_euler_deg": [78.0, 0.0, 4.0],
                }
            ),
            subject_name="Kaia Vale",
            intent_hint="hero portrait",
        )

        recipe = json.loads(shot_recipe_json)
        summary = json.loads(summary_json)

        self.assertIn("Kaia Vale", camera_prompt)
        self.assertIn("35mm", camera_prompt)
        self.assertEqual(recipe["lens_bucket"], "normal")
        self.assertEqual(summary["ratio"], "16:9")

    def test_blender_return_plan_keeps_scene_context(self) -> None:
        node = MKRBlenderReturnPlan()
        return_plan_json, manifest_line, summary_json = node.build(
            generated_asset_path="/tmp/render/shot010_comp.png",
            asset_kind="image",
            apply_mode="image_plane",
            target_name="Shot010 Comp",
            colorspace="sRGB",
            scene_packet_json=json.dumps({"scene_name": "Shot010", "frame_current": 48}),
            notes="Apply as the review comp",
        )

        plan = json.loads(return_plan_json)
        summary = json.loads(summary_json)

        self.assertEqual(plan["scene_name"], "Shot010")
        self.assertEqual(plan["frame_current"], 48)
        self.assertEqual(plan["asset"]["apply_mode"], "image_plane")
        self.assertIn("Shot010", manifest_line)
        self.assertTrue(summary["has_path"])

    def test_blender_material_import_builds_manifest(self) -> None:
        node = MKRBlenderMaterialImport()
        material_json, material_prompt, texture_manifest_json, summary_json = node.build(
            material_payload_json=json.dumps(
                {
                    "name": "Courier_Jacket",
                    "blend_method": "BLEND",
                    "roughness": 0.62,
                    "metallic": 0.08,
                    "textures": [
                        {"slot": "base_color", "path": "/tmp/jacket_base.png", "colorspace": "sRGB"},
                        {"slot": "normal", "path": "/tmp/jacket_normal.png", "colorspace": "Non-Color"},
                    ],
                }
            )
        )

        material = json.loads(material_json)
        manifest = json.loads(texture_manifest_json)
        summary = json.loads(summary_json)

        self.assertEqual(material["name"], "Courier_Jacket")
        self.assertEqual(manifest["texture_count"], 2)
        self.assertEqual(summary["texture_count"], 2)
        self.assertIn("Courier_Jacket", material_prompt)

    def test_blender_material_return_plan_collects_texture_paths(self) -> None:
        node = MKRBlenderMaterialReturnPlan()
        plan_json, manifest_line, summary_json = node.build(
            material_name="Courier_Jacket",
            base_color_path="/tmp/jacket_base.png",
            normal_path="/tmp/jacket_normal.png",
            roughness_path="/tmp/jacket_roughness.png",
            metallic_path="",
            emission_path="",
            alpha_path="",
            target_object_name="HeroMesh",
            target_material_slot="Courier_Jacket",
            notes="apply generated set",
        )

        plan = json.loads(plan_json)
        summary = json.loads(summary_json)

        self.assertEqual(plan["material_name"], "Courier_Jacket")
        self.assertEqual(plan["target_object_name"], "HeroMesh")
        self.assertEqual(plan["textures"]["normal"], "/tmp/jacket_normal.png")
        self.assertEqual(summary["texture_count"], 3)
        self.assertIn("Courier_Jacket", manifest_line)

    def test_3d_host_image_import_nodes_load_image_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "bridge_texture.png"
            Image.new("RGBA", (8, 6), (128, 64, 255, 200)).save(image_path)
            payload = json.dumps({"textures": [{"slot": "base_color", "path": str(image_path)}]})

            blender_node = MKRBlenderImageImport()
            fusion_node = MKRFusion360ImageImport()
            maya_node = MKRMayaImageImport()

            blender_image, blender_mask, _, blender_path, blender_summary = blender_node.build(payload, "base_color")
            fusion_image, fusion_mask, _, fusion_path, fusion_summary = fusion_node.build(payload, "base_color")
            maya_image, maya_mask, _, maya_path, maya_summary = maya_node.build(payload, "base_color")

            self.assertEqual(tuple(blender_image.shape), (1, 6, 8, 3))
            self.assertEqual(tuple(blender_mask.shape), (1, 6, 8))
            self.assertEqual(blender_path, str(image_path))
            self.assertEqual(fusion_path, str(image_path))
            self.assertEqual(maya_path, str(image_path))
            self.assertEqual(json.loads(blender_summary)["host"], "blender")
            self.assertEqual(json.loads(fusion_summary)["host"], "fusion360")
            self.assertEqual(json.loads(maya_summary)["host"], "maya")
            self.assertTrue(torch.allclose(blender_image, fusion_image, atol=1e-6))
            self.assertTrue(torch.allclose(blender_mask, fusion_mask, atol=1e-6))
            self.assertTrue(torch.allclose(maya_mask, fusion_mask, atol=1e-6))

    def test_3d_host_image_output_plans_build_live_texture_handoffs(self) -> None:
        transport_plan = json.dumps({"protocol": "websocket", "url": "ws://127.0.0.1:8188/mkrshift"})

        blender_node = MKRBlenderImageOutputPlan()
        fusion_node = MKRFusion360ImageOutputPlan()
        maya_node = MKRMayaImageOutputPlan()

        blender_plan, _, blender_summary = blender_node.build("/tmp/base.png", "base_color", "Hero Result", "texture_image", "Hero_MAT", "HeroMesh", transport_plan)
        fusion_plan, _, fusion_summary = fusion_node.build("/tmp/decal.png", "decal", "Hero Appearance", "decal", "HeroComponent", transport_plan)
        maya_plan, _, maya_summary = maya_node.build("/tmp/albedo.png", "base_color", "HeroShader", "file_texture", "HeroMesh", transport_plan)

        self.assertEqual(json.loads(blender_plan)["schema"], "mkrshift_blender_image_output_plan_v1")
        self.assertEqual(json.loads(fusion_plan)["schema"], "mkrshift_fusion360_image_output_plan_v1")
        self.assertEqual(json.loads(maya_plan)["schema"], "mkrshift_maya_image_output_plan_v1")
        self.assertTrue(json.loads(blender_summary)["has_transport_plan"])
        self.assertTrue(json.loads(fusion_summary)["has_transport_plan"])
        self.assertTrue(json.loads(maya_summary)["has_transport_plan"])

    def test_2d_host_image_import_nodes_load_image_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "bridge_plate.png"
            Image.new("RGBA", (7, 9), (255, 200, 64, 180)).save(image_path)
            payload = json.dumps({"layers": [{"slot": "plate", "path": str(image_path)}]})

            nuke_node = MKRNukeImageImport()
            photoshop_node = MKRPhotoshopImageImport()
            ae_node = MKRAfterEffectsImageImport()
            premiere_node = MKRPremiereImageImport()

            nuke_image, nuke_mask, _, nuke_path, nuke_summary = nuke_node.build(payload, "plate")
            ps_image, ps_mask, _, ps_path, ps_summary = photoshop_node.build(payload, "plate")
            ae_image, ae_mask, _, ae_path, ae_summary = ae_node.build(payload, "plate")
            pr_image, pr_mask, _, pr_path, pr_summary = premiere_node.build(payload, "plate")

            self.assertEqual(tuple(nuke_image.shape), (1, 9, 7, 3))
            self.assertEqual(tuple(nuke_mask.shape), (1, 9, 7))
            self.assertEqual(nuke_path, str(image_path))
            self.assertEqual(ps_path, str(image_path))
            self.assertEqual(ae_path, str(image_path))
            self.assertEqual(pr_path, str(image_path))
            self.assertEqual(json.loads(nuke_summary)["host"], "nuke")
            self.assertEqual(json.loads(ps_summary)["host"], "photoshop")
            self.assertEqual(json.loads(ae_summary)["host"], "after_effects")
            self.assertEqual(json.loads(pr_summary)["host"], "premiere_pro")
            self.assertTrue(torch.allclose(nuke_image, ps_image, atol=1e-6))
            self.assertTrue(torch.allclose(ae_mask, pr_mask, atol=1e-6))

    def test_2d_host_image_output_plans_build_live_handoffs(self) -> None:
        transport_plan = json.dumps({"protocol": "http", "base_url": "http://127.0.0.1:8188"})

        nuke_node = MKRNukeImageOutputPlan()
        photoshop_node = MKRPhotoshopImageOutputPlan()
        ae_node = MKRAfterEffectsImageOutputPlan()
        premiere_node = MKRPremiereImageOutputPlan()

        nuke_plan, _, nuke_summary = nuke_node.build("/tmp/plate.exr", "plate", "Read_MKRShift", "read_node", "default", "comp.nk", transport_plan)
        ps_plan, _, ps_summary = photoshop_node.build("/tmp/layer.png", "layer_art", "Result Layer", "new_layer", "screen", "hero.psd", transport_plan)
        ae_plan, _, ae_summary = ae_node.build("/tmp/still.png", "footage", "Result Plate", "import_footage", "Comp 1", transport_plan)
        pr_plan, _, pr_summary = premiere_node.build("/tmp/graphic.png", "graphic", "Result Graphic", "new_graphic", "Sequence 01", transport_plan)

        self.assertEqual(json.loads(nuke_plan)["schema"], "mkrshift_nuke_image_output_plan_v1")
        self.assertEqual(json.loads(ps_plan)["schema"], "mkrshift_photoshop_image_output_plan_v1")
        self.assertEqual(json.loads(ae_plan)["schema"], "mkrshift_after_effects_image_output_plan_v1")
        self.assertEqual(json.loads(pr_plan)["schema"], "mkrshift_premiere_image_output_plan_v1")
        self.assertTrue(json.loads(nuke_summary)["has_transport_plan"])
        self.assertTrue(json.loads(ps_summary)["has_transport_plan"])
        self.assertTrue(json.loads(ae_summary)["has_transport_plan"])
        self.assertTrue(json.loads(pr_summary)["has_transport_plan"])

    def test_touchdesigner_bridge_nodes_normalize_packet_and_plan(self) -> None:
        import_node = MKRTouchDesignerImport()
        plan_node = MKRTouchDesignerFramePlan()
        payload = {
            "project_name": "TD Session",
            "tox_name": "MKRShiftBridge",
            "operator_path": "/project1/mkrshift_bridge1",
            "transport": "spout",
            "top_name": "outTOP",
            "controls": {"exposure": 0.75, "strobe": False},
            "textures": [{"name": "beauty", "path": "/tmp/beauty.png", "type": "TOP"}],
        }
        packet_json, controls_json, manifest_json, summary_json = import_node.build(json.dumps(payload))
        plan_json, manifest_line, plan_summary_json = plan_node.build(
            asset_path="/tmp/output.mov",
            transport="ndi",
            top_name="mkrOut",
            operator_path="/project1/mkrshift_bridge1",
            asset_kind="video",
            colorspace="sRGB",
        )

        packet = json.loads(packet_json)
        controls = json.loads(controls_json)
        manifest = json.loads(manifest_json)
        summary = json.loads(summary_json)
        plan = json.loads(plan_json)
        plan_summary = json.loads(plan_summary_json)

        self.assertEqual(packet["schema"], "mkrshift_touchdesigner_bridge_v1")
        self.assertEqual(packet["transport"], "spout")
        self.assertEqual(controls["exposure"], 0.75)
        self.assertEqual(manifest["texture_count"], 1)
        self.assertEqual(summary["tox_name"], "MKRShiftBridge")
        self.assertEqual(plan["asset"]["kind"], "video")
        self.assertIn("mkrOut", manifest_line)
        self.assertEqual(plan_summary["transport"], "ndi")

    def test_tixl_bridge_nodes_normalize_packet_and_plan(self) -> None:
        import_node = MKRTiXLImport()
        plan_node = MKRTiXLFramePlan()
        payload = {
            "project_name": "TiXL Show",
            "graph_name": "BridgeGraph",
            "operator_name": "MKRShiftComfyBridge",
            "transport": "osc",
            "layers": [{"name": "Beauty", "path": "/tmp/beauty.exr", "kind": "texture", "blend_mode": "Screen"}],
        }
        packet_json, manifest_json, timing_json, summary_json = import_node.build(json.dumps(payload))
        plan_json, manifest_line, plan_summary_json = plan_node.build(
            asset_path="/tmp/beauty.exr",
            transport="ndi",
            source_kind="texture",
            layer_name="Beauty",
            graph_name="BridgeGraph",
            blend_mode="Screen",
        )

        packet = json.loads(packet_json)
        manifest = json.loads(manifest_json)
        timing = json.loads(timing_json)
        summary = json.loads(summary_json)
        plan = json.loads(plan_json)
        plan_summary = json.loads(plan_summary_json)

        self.assertEqual(packet["schema"], "mkrshift_tixl_bridge_v1")
        self.assertEqual(packet["transport"], "osc")
        self.assertEqual(manifest["layer_count"], 1)
        self.assertEqual(timing["transport"], "osc")
        self.assertEqual(summary["graph_name"], "BridgeGraph")
        self.assertEqual(plan["layer"]["blend_mode"], "Screen")
        self.assertIn("BridgeGraph", manifest_line)
        self.assertEqual(plan_summary["transport"], "ndi")

    def test_other_addon_bridge_nodes_build_packets_and_plans(self) -> None:
        nuke_import = MKRNukeScriptImport()
        nuke_plan = MKRNukeReadPlan()
        ps_import = MKRPhotoshopDocumentImport()
        ps_plan = MKRPhotoshopExportPlan()
        ae_import = MKRAfterEffectsCompImport()
        ae_plan = MKRAfterEffectsRenderPlan()
        pr_import = MKRPremiereSequenceImport()
        pr_plan = MKRPremiereExportPlan()
        aff_import = MKRAffinityDocumentImport()
        aff_plan = MKRAffinityExportPlan()
        aff_plugin_plan = MKRAffinityPhotoshopPluginPlan()
        fusion_import = MKRFusion360SceneImport()
        fusion_plan = MKRFusion360TexturePlan()
        maya_import = MKRMayaSceneImport()
        maya_plan = MKRMayaMaterialPlan()

        transport_plan = json.dumps({"protocol": "osc", "host": "127.0.0.1", "port": 9001})
        nuke_packet, _, _, _ = nuke_import.build(json.dumps({"script_name": "shot010.nk", "reads": [{"name": "Read1", "path": "/tmp/a.exr"}]}))
        nuke_read_plan, _, nuke_summary = nuke_plan.build("/tmp/comp.exr", "Read_MKR", "ACEScg", "single", "", transport_plan)
        ps_packet, _, _ = ps_import.build(json.dumps({"document_name": "lookdev.psd", "layers": [{"name": "Beauty"}]}))
        ps_export_plan, _, ps_summary = ps_plan.build("/tmp/beauty.png", "MKR Result", "new_layer", transport_plan)
        ae_packet, _, _ = ae_import.build(json.dumps({"project_name": "shot.aep", "comp_name": "Main", "fps": 24}))
        ae_render_plan, _, ae_summary = ae_plan.build("/tmp/render.mov", "footage", "Main", transport_plan)
        pr_packet, _, _ = pr_import.build(json.dumps({"project_name": "edit.prproj", "sequence_name": "Main Seq", "clips": [{"name": "Shot010"}]}))
        pr_export_plan, _, pr_summary = pr_plan.build("/tmp/review.mov", "new_track_item", "Main Seq", transport_plan)
        aff_packet, _, _ = aff_import.build(json.dumps({"document_name": "poster.afphoto", "layers": [{"name": "Base"}]}))
        aff_export_plan, _, aff_summary = aff_plan.build("/tmp/base.png", "Result", "replace_layer", transport_plan)
        affinity_plugin_plan, _, affinity_plugin_summary = aff_plugin_plan.build("MKRShift Photoshop Filter", "filter", "/Library/Application Support/Plugins", "/Library/Application Support/PluginSupport", "/tmp/base.png", "ps_plugin_filter", transport_plan)
        fusion_packet, _, _ = fusion_import.build(json.dumps({"document_name": "concept.f3d", "camera_name": "Iso"}))
        fusion_texture_plan, _, fusion_summary = fusion_plan.build("/tmp/decal.png", "Hero Appearance", "decal", transport_plan)
        maya_packet, _, _, _ = maya_import.build(json.dumps({"scene_name": "rig.ma", "materials": [{"name": "Body_MAT"}], "camera": {"name": "renderCam"}}))
        maya_material_plan, _, maya_summary = maya_plan.build("/tmp/albedo.png", "Body_MAT", "HeroMesh", "file_texture", transport_plan)

        self.assertEqual(json.loads(nuke_packet)["schema"], "mkrshift_nuke_bridge_v1")
        self.assertEqual(json.loads(nuke_read_plan)["schema"], "mkrshift_nuke_read_plan_v1")
        self.assertEqual(json.loads(ps_packet)["schema"], "mkrshift_photoshop_bridge_v1")
        self.assertEqual(json.loads(ps_export_plan)["schema"], "mkrshift_photoshop_export_plan_v1")
        self.assertEqual(json.loads(ae_packet)["schema"], "mkrshift_after_effects_bridge_v1")
        self.assertEqual(json.loads(ae_render_plan)["schema"], "mkrshift_after_effects_render_plan_v1")
        self.assertEqual(json.loads(pr_packet)["schema"], "mkrshift_premiere_bridge_v1")
        self.assertEqual(json.loads(pr_export_plan)["schema"], "mkrshift_premiere_export_plan_v1")
        self.assertEqual(json.loads(aff_packet)["schema"], "mkrshift_affinity_bridge_v1")
        self.assertEqual(json.loads(aff_export_plan)["schema"], "mkrshift_affinity_export_plan_v1")
        self.assertEqual(json.loads(affinity_plugin_plan)["schema"], "mkrshift_affinity_photoshop_plugin_plan_v1")
        self.assertEqual(json.loads(fusion_packet)["schema"], "mkrshift_fusion360_bridge_v1")
        self.assertEqual(json.loads(fusion_texture_plan)["schema"], "mkrshift_fusion360_texture_plan_v1")
        self.assertEqual(json.loads(maya_packet)["schema"], "mkrshift_maya_bridge_v1")
        self.assertEqual(json.loads(maya_material_plan)["schema"], "mkrshift_maya_material_plan_v1")
        self.assertTrue(json.loads(nuke_summary)["has_transport_plan"])
        self.assertTrue(json.loads(ps_summary)["has_transport_plan"])
        self.assertTrue(json.loads(ae_summary)["has_transport_plan"])
        self.assertTrue(json.loads(pr_summary)["has_transport_plan"])
        self.assertTrue(json.loads(aff_summary)["has_transport_plan"])
        self.assertTrue(json.loads(affinity_plugin_summary)["has_transport_plan"])
        self.assertTrue(json.loads(fusion_summary)["has_transport_plan"])
        self.assertTrue(json.loads(maya_summary)["has_transport_plan"])

    def test_network_transport_plan_nodes_build_packets(self) -> None:
        endpoint = MKRAddonEndpointPlan()
        osc = MKROSCMessagePlan()
        ndi = MKRNDIStreamPlan()
        spout = MKRSpoutSenderPlan()
        syphon = MKRSyphonSenderPlan()
        tcp = MKRTCPBridgePlan()
        http = MKRHTTPWebhookPlan()
        watch = MKRWatchFolderPlan()
        ws = MKRWebSocketBridgePlan()

        endpoint_json, _, endpoint_summary = endpoint.build("http://127.0.0.1:8188", "/mkrshift/submit", "/mkrshift/status/{job_id}", "/mkrshift/result/{job_id}", "bearer", "Authorization", "abc123", 15000, json.dumps({"X-Test": "1"}), "touchdesigner-live")
        osc_json, _, _ = osc.build("/mkrshift/test", "127.0.0.1", 9000, json.dumps({"value": 1}))
        ndi_json, _, _ = ndi.build("MKRShift NDI", "/tmp/out.mov", "video", "ignore")
        spout_json, _, _ = spout.build("MKRShift Spout", "/tmp/out.exr", "texture")
        syphon_json, _, _ = syphon.build("MKRShift Syphon", "/tmp/out.exr", "texture")
        tcp_json, _, _ = tcp.build("127.0.0.1", 7700, "json_line", json.dumps({"value": 2}))
        http_json, _, _ = http.build("http://127.0.0.1:8188/mkrshift", "POST", json.dumps({"path": "/tmp/out.png"}), json.dumps({"Authorization": "Bearer x"}))
        watch_json, _, _ = watch.build("/tmp/mkrshift/watch", "*.png", "latest")
        ws_json, _, _ = ws.build("ws://127.0.0.1:8188/mkrshift", "frame", json.dumps({"path": "/tmp/out.png"}))

        self.assertEqual(json.loads(endpoint_json)["schema"], "mkrshift_addon_endpoint_plan_v1")
        self.assertEqual(json.loads(endpoint_summary)["auth_mode"], "bearer")
        self.assertEqual(json.loads(osc_json)["schema"], "mkrshift_osc_plan_v1")
        self.assertEqual(json.loads(ndi_json)["schema"], "mkrshift_ndi_plan_v1")
        self.assertEqual(json.loads(spout_json)["schema"], "mkrshift_spout_plan_v1")
        self.assertEqual(json.loads(syphon_json)["schema"], "mkrshift_syphon_plan_v1")
        self.assertEqual(json.loads(tcp_json)["schema"], "mkrshift_tcp_plan_v1")
        self.assertEqual(json.loads(http_json)["schema"], "mkrshift_http_plan_v1")
        self.assertEqual(json.loads(watch_json)["schema"], "mkrshift_watch_folder_plan_v1")
        self.assertEqual(json.loads(ws_json)["schema"], "mkrshift_websocket_plan_v1")

    def test_network_runtime_nodes_execute_transport_actions(self) -> None:
        requests = {"submit": None, "status": None, "webhook": None}

        class _Handler(BaseHTTPRequestHandler):
            def _read_json(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw.decode("utf-8"))

            def do_POST(self):  # noqa: N802
                if self.path == "/submit":
                    requests["submit"] = self._read_json()
                    response = {"job_id": "job-123", "state": "queued"}
                elif self.path == "/webhook":
                    requests["webhook"] = self._read_json()
                    response = {"ok": True, "received": True}
                else:
                    response = {"ok": False}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))

            def do_GET(self):  # noqa: N802
                if self.path == "/status/job-123":
                    requests["status"] = {"polled": True}
                    response = {"job_id": "job-123", "state": "completed"}
                elif self.path == "/result/job-123":
                    response = {"image_path": "/tmp/result.png"}
                else:
                    response = {"ok": False}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A003
                return

        class _TCPHandler(socketserver.BaseRequestHandler):
            payload = b""

            def handle(self):
                _TCPHandler.payload = self.request.recv(4096)

        http_server = HTTPServer(("127.0.0.1", 0), _Handler)
        http_thread = Thread(target=http_server.serve_forever, daemon=True)
        http_thread.start()

        tcp_server = socketserver.TCPServer(("127.0.0.1", 0), _TCPHandler)
        tcp_thread = Thread(target=tcp_server.serve_forever, daemon=True)
        tcp_thread.start()

        try:
            endpoint_plan_json, _, _ = MKRAddonEndpointPlan().build(
                f"http://127.0.0.1:{http_server.server_port}",
                "/submit",
                "/status/{job_id}",
                "/result/{job_id}",
                "none",
                "Authorization",
                "",
                15000,
                "{}",
                "runtime-test",
            )
            http_plan_json, _, _ = MKRHTTPWebhookPlan().build(
                f"http://127.0.0.1:{http_server.server_port}/webhook",
                "POST",
                json.dumps({"kind": "webhook"}),
                "{}",
            )
            tcp_plan_json, _, _ = MKRTCPBridgePlan().build(
                "127.0.0.1",
                tcp_server.server_address[1],
                "json_line",
                json.dumps({"kind": "tcp"}),
            )
            watch_dir = tempfile.mkdtemp(prefix="mkrshift-watch-")
            watch_plan_json, _, _ = MKRWatchFolderPlan().build(watch_dir, "*.json", "latest")
            osc_plan_json, _, _ = MKROSCMessagePlan().build("/mkrshift/test", "127.0.0.1", 9010, json.dumps({"value": 1}))

            submit_response, job_id, submit_summary = MKRAddonEndpointSubmit().run(endpoint_plan_json, json.dumps({"kind": "submit"}))
            status_response, result_response, poll_summary = MKRAddonEndpointPoll().run(endpoint_plan_json, job_id)
            webhook_response, webhook_status, _ = MKRHTTPWebhookSend().run(http_plan_json, json.dumps({"kind": "hook"}))
            tcp_payload_json, tcp_bytes, _ = MKRTCPBridgeSend().run(tcp_plan_json, json.dumps({"kind": "socket"}))
            written_path, written_payload_json, _ = MKRWatchFolderWrite().run(watch_plan_json, json.dumps({"kind": "file"}), "payload.json")
            osc_payload_json, osc_bytes, osc_summary = MKROSCSend().run(osc_plan_json, json.dumps({"args": [1, 2.0, "hi"]}))
            for _ in range(20):
                if _TCPHandler.payload:
                    break
                time.sleep(0.01)

            self.assertEqual(json.loads(submit_response)["job_id"], "job-123")
            self.assertEqual(job_id, "job-123")
            self.assertEqual(json.loads(status_response)["state"], "completed")
            self.assertEqual(json.loads(result_response)["image_path"], "/tmp/result.png")
            self.assertEqual(webhook_status, 200)
            self.assertTrue(json.loads(webhook_response)["received"])
            self.assertIn(b"socket", _TCPHandler.payload)
            self.assertGreater(tcp_bytes, 0)
            self.assertEqual(json.loads(tcp_payload_json)["kind"], "socket")
            self.assertTrue(Path(written_path).is_file())
            self.assertEqual(json.loads(written_payload_json)["kind"], "file")
            self.assertGreater(osc_bytes, 0)
            self.assertIn("ifs", json.loads(osc_summary).get("type_tags", ""))
            self.assertEqual(json.loads(osc_payload_json)["args"][2], "hi")
            self.assertEqual(requests["submit"]["kind"], "submit")
            self.assertEqual(requests["webhook"]["kind"], "hook")
            self.assertEqual(json.loads(submit_summary)["job_id"], "job-123")
            self.assertEqual(json.loads(poll_summary)["state"], "completed")
        finally:
            http_server.shutdown()
            http_server.server_close()
            tcp_server.shutdown()
            tcp_server.server_close()

    def test_host_image_output_runtime_nodes_write_images(self) -> None:
        image = torch.full((1, 12, 10, 3), 0.5, dtype=torch.float32)
        out_dir = Path(tempfile.mkdtemp(prefix="mkrshift-host-out-"))

        blender_plan_json, _, _ = MKRBlenderImageOutputPlan().build(str(out_dir / "blender.png"), "base_color", "MKR", "texture_image")
        photoshop_plan_json, _, _ = MKRPhotoshopImageOutputPlan().build(str(out_dir / "photoshop.png"), "layer_art", "MKR", "new_layer")
        ae_plan_json, _, _ = MKRAfterEffectsImageOutputPlan().build(str(out_dir / "ae.png"), "footage", "MKR", "import_footage")
        premiere_plan_json, _, _ = MKRPremiereImageOutputPlan().build(str(out_dir / "premiere.png"), "graphic", "MKR", "new_graphic")
        nuke_plan_json, _, _ = MKRNukeImageOutputPlan().build(str(out_dir / "nuke.png"), "plate", "MKR", "read_node")
        fusion_plan_json, _, _ = MKRFusion360ImageOutputPlan().build(str(out_dir / "fusion.png"), "decal", "MKR", "decal")
        maya_plan_json, _, _ = MKRMayaImageOutputPlan().build(str(out_dir / "maya.png"), "base_color", "MKR", "file_texture")

        nodes = [
            (MKRBlenderImageOutput(), blender_plan_json, "blender.png"),
            (MKRPhotoshopImageOutput(), photoshop_plan_json, "photoshop.png"),
            (MKRAfterEffectsImageOutput(), ae_plan_json, "ae.png"),
            (MKRPremiereImageOutput(), premiere_plan_json, "premiere.png"),
            (MKRNukeImageOutput(), nuke_plan_json, "nuke.png"),
            (MKRFusion360ImageOutput(), fusion_plan_json, "fusion.png"),
            (MKRMayaImageOutput(), maya_plan_json, "maya.png"),
        ]

        for node, plan_json, expected_name in nodes:
            written_paths_json, primary_path, summary_json = node.run(image, plan_json)
            self.assertEqual(Path(primary_path).name, expected_name)
            self.assertTrue(Path(primary_path).is_file())
            self.assertEqual(json.loads(summary_json)["count"], 1)
            self.assertEqual(Path(json.loads(written_paths_json)["paths"][0]).name, expected_name)

    def test_host_plan_runtime_nodes_write_assets(self) -> None:
        image = torch.full((1, 14, 14, 3), 0.25, dtype=torch.float32)
        out_dir = Path(tempfile.mkdtemp(prefix="mkrshift-plan-out-"))

        blender_plan_json, _, _ = MKRBlenderReturnPlan().build(str(out_dir / "blender_return.png"), "image", "image_plane", "MKR")
        nuke_plan_json, _, _ = MKRNukeReadPlan().build(str(out_dir / "nuke_read.png"), "Read_MKR", "default", "single")
        ps_plan_json, _, _ = MKRPhotoshopExportPlan().build(str(out_dir / "photoshop_export.png"), "MKR", "new_layer")
        ae_plan_json, _, _ = MKRAfterEffectsRenderPlan().build(str(out_dir / "ae_render.png"), "footage", "Comp 1")
        pr_plan_json, _, _ = MKRPremiereExportPlan().build(str(out_dir / "premiere_export.png"), "new_track_item", "Seq 1")
        aff_plan_json, _, _ = MKRAffinityExportPlan().build(str(out_dir / "affinity_export.png"), "MKR", "new_layer")
        fusion_plan_json, _, _ = MKRFusion360TexturePlan().build(str(out_dir / "fusion_texture.png"), "MKR", "decal")
        maya_plan_json, _, _ = MKRMayaMaterialPlan().build(str(out_dir / "maya_material.png"), "MKR", "", "file_texture")

        nodes = [
            (MKRBlenderReturnOutput(), {"return_plan_json": blender_plan_json}, "blender_return.png"),
            (MKRNukeReadOutput(), {"nuke_read_plan_json": nuke_plan_json}, "nuke_read.png"),
            (MKRPhotoshopExportOutput(), {"photoshop_export_plan_json": ps_plan_json}, "photoshop_export.png"),
            (MKRAfterEffectsRenderOutput(), {"ae_render_plan_json": ae_plan_json}, "ae_render.png"),
            (MKRPremiereExportOutput(), {"premiere_export_plan_json": pr_plan_json}, "premiere_export.png"),
            (MKRAffinityExportOutput(), {"affinity_export_plan_json": aff_plan_json}, "affinity_export.png"),
            (MKRFusion360TextureOutput(), {"fusion_texture_plan_json": fusion_plan_json}, "fusion_texture.png"),
            (MKRMayaMaterialOutput(), {"maya_material_plan_json": maya_plan_json}, "maya_material.png"),
        ]

        for node, kwargs, expected_name in nodes:
            written_paths_json, primary_path, summary_json = node.run(image, **kwargs)
            self.assertEqual(Path(primary_path).name, expected_name)
            self.assertTrue(Path(primary_path).is_file())
            self.assertEqual(json.loads(summary_json)["count"], 1)
            self.assertEqual(Path(json.loads(written_paths_json)["paths"][0]).name, expected_name)

    def test_vfx_composite_nodes_run(self) -> None:
        fg = torch.full((1, 32, 32, 3), 0.8, dtype=torch.float32)
        bg = torch.zeros((1, 32, 32, 3), dtype=torch.float32)
        matte = torch.zeros((1, 32, 32), dtype=torch.float32)
        matte[:, 8:24, 8:24] = 1.0

        wrap_node = x1LightWrapComposite()
        ab_node = x1EdgeAberration()

        wrapped, wrap_mask, wrap_info = wrap_node.run(
            foreground=fg,
            background=bg,
            matte=matte,
            wrap_radius=8.0,
            wrap_strength=0.9,
            edge_bias=0.5,
            inside_holdout=0.7,
            mix=1.0,
        )
        ab_image, ab_mask, ab_info = ab_node.run(
            image=wrapped,
            strength_px=2.0,
            edge_threshold=0.05,
            edge_softness=0.1,
            radial_bias=0.5,
            mix=1.0,
        )

        self.assertEqual(tuple(wrapped.shape), (1, 32, 32, 3))
        self.assertEqual(tuple(wrap_mask.shape), (1, 32, 32))
        self.assertIn("x1LightWrapComposite", wrap_info)
        self.assertEqual(tuple(ab_image.shape), (1, 32, 32, 3))
        self.assertEqual(tuple(ab_mask.shape), (1, 32, 32))
        self.assertIn("x1EdgeAberration", ab_info)

    def test_publish_copy_deck_emits_composed_variants(self) -> None:
        node = MKRPublishCopyDeck()
        pick_node = MKRPublishCopyAtIndex()

        deck_json, deck_md, first_caption, summary_json, variant_count = node.build(
            headline="New drop",
            subhead="Built for fast iteration",
            body="Refined previews and cleaner output cards.",
            cta="Save this for later",
            hashtags_csv="mkrshift, lookdev",
            hook_lines="Clean first look\nCloser detail pass",
            tone="Bold",
            platform_hint="release",
        )

        deck = json.loads(deck_json)
        summary = json.loads(summary_json)

        self.assertEqual(variant_count, 2)
        self.assertEqual(summary["platform_hint"], "release")
        self.assertIn("Big swing:", first_caption)
        self.assertIn("#mkrshift", first_caption)
        self.assertIn("Variant 2", deck_md)
        self.assertEqual(deck["variants"][1]["headline"], "Closer detail pass")

        variant_json, headline, caption, hashtags_csv = pick_node.pick(deck_json=deck_json, index=1)
        variant = json.loads(variant_json)
        self.assertEqual(headline, "Closer detail pass")
        self.assertIn("Closer detail pass", caption)
        self.assertEqual(variant["index"], 2)
        self.assertEqual(hashtags_csv, "#mkrshift, #lookdev")

    def test_pose_studio_emits_pose_json_and_guide(self) -> None:
        node = MKRPoseStudio()
        pose_json, pose_guide, pose_prompt, summary_json = node.build(
            settings_json=json.dumps(
                {
                    "pose_name": "Hero blockout",
                    "pose_preset": "contrapposto",
                    "view": {"yaw": 40, "pitch": 10, "zoom": 1.1},
                    "controls": {"head_yaw": 22, "arm_raise_l": 52, "knee_bend_l": 28},
                }
            ),
            capture_w=768,
            capture_h=896,
            character_state_json=json.dumps({"character_name": "Kaia Vale"}),
        )

        pose = json.loads(pose_json)
        summary = json.loads(summary_json)

        self.assertEqual(pose["schema"], "mkr_pose_studio_v1")
        self.assertEqual(pose["pose_name"], "Hero blockout")
        self.assertIn("joints_world", pose)
        for key in ("eye_l", "eye_r", "chin", "thumb_l", "index_l", "heel_l"):
            self.assertIn(key, pose["joints_world"])
        self.assertIn(["head", "eye_l"], pose["bones"])
        self.assertIn(["hand_l", "thumb_l"], pose["bones"])
        self.assertIn(["ankle_l", "heel_l"], pose["bones"])
        self.assertIn("raised arm", pose_prompt)
        self.assertEqual(summary["character_name"], "Kaia Vale")
        self.assertEqual(tuple(pose_guide.shape), (1, 896, 768, 3))

    def test_pose_studio_mirror_right_to_left_overrides_left_controls(self) -> None:
        node = MKRPoseStudio()
        pose_json, _, _, _ = node.build(
            settings_json=json.dumps(
                {
                    "controls": {
                        "arm_raise_l": 10,
                        "arm_raise_r": 74,
                        "arm_forward_l": 12,
                        "arm_forward_r": -33,
                        "hip_side_l": 4,
                        "hip_side_r": -15,
                    }
                }
            ),
            capture_w=512,
            capture_h=512,
            mirror_mode="right_to_left",
        )

        pose = json.loads(pose_json)
        controls = pose["controls"]
        self.assertEqual(controls["arm_raise_l"], 74.0)
        self.assertEqual(controls["arm_forward_l"], 33.0)
        self.assertEqual(controls["hip_side_l"], 15.0)

    def test_pose_studio_accepts_new_preset_names(self) -> None:
        node = MKRPoseStudio()
        pose_json, _, pose_prompt, summary_json = node.build(
            pose_preset="pinup_sway",
            capture_w=640,
            capture_h=640,
        )

        pose = json.loads(pose_json)
        summary = json.loads(summary_json)

        self.assertEqual(pose["pose_preset"], "pinup_sway")
        self.assertEqual(summary["pose_preset"], "pinup_sway")
        self.assertGreater(pose["controls"]["spine_twist"], 0.0)
        self.assertGreater(pose["controls"]["arm_raise_l"], pose["controls"]["arm_raise_r"])
        self.assertIn("pinup sway", pose_prompt)

    def test_pose_studio_can_fit_pose_from_reference_image(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=640,
            capture_h=640,
        )

        pose_json, _, _, summary_json = node.build(
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image",
            pose_image_strength=0.9,
            capture_w=640,
            capture_h=640,
        )

        pose = json.loads(pose_json)
        summary = json.loads(summary_json)
        self.assertTrue(summary["image_fit"]["applied"])
        self.assertIn(summary["image_fit"]["fit_orientation"], {"direct", "mirrored"})
        self.assertGreater(summary["image_fit"]["fit_score"], 0.2)
        self.assertGreaterEqual(summary["image_fit"]["anchor_count"], summary["image_fit"]["manual_anchor_count"])

    def test_pose_studio_image_fit_defaults(self) -> None:
        optional = MKRPoseStudio.INPUT_TYPES()["optional"]
        self.assertNotIn("pose_from_image_mode", optional)
        self.assertNotIn("pose_image_strength", optional)

    def test_pose_studio_fit_from_image_uses_reference_size_for_output(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=768,
            capture_h=480,
        )

        pose_json, output_guide, _, summary_json = node.build(
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image",
            pose_image_strength=1.0,
            capture_w=640,
            capture_h=640,
        )

        pose = json.loads(pose_json)
        summary = json.loads(summary_json)
        self.assertEqual(summary["capture_size"], [768, 480])
        self.assertEqual(tuple(output_guide.shape)[1:3], (480, 768))
        self.assertTrue(summary["image_fit"]["applied"])
        self.assertIn(pose["pose_name"], {"Image Fit", "Reach Up", "Neutral"})
        self.assertIn("frame_hint", summary["image_fit"])
        self.assertIsInstance(summary["image_fit"]["frame_hint"], dict)
        self.assertIn("image_fit", pose)
        self.assertEqual(pose["image_fit"]["fit_mode"], "fit_from_image")

    def test_pose_studio_fit_from_image_structured_emits_fit_mode_and_frame_hint(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=640,
            capture_h=640,
        )

        pose_json, _, _, summary_json = node.build(
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image_structured",
            pose_image_strength=1.0,
            capture_w=640,
            capture_h=640,
        )

        pose = json.loads(pose_json)
        summary = json.loads(summary_json)
        self.assertEqual(summary["image_fit"]["fit_mode"], "fit_from_image_structured")
        self.assertIn("frame_hint", summary["image_fit"])
        self.assertIn("frame_hint", pose["image_fit"])
        self.assertEqual(pose["image_fit"]["fit_mode"], "fit_from_image_structured")

    def test_pose_studio_fit_from_image_accepts_saved_anchor_hints(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=640,
            capture_h=640,
        )

        settings_json = json.dumps(
            {
                "image_fit": {
                    "selected_anchor": "head",
                    "anchors": {
                        "head": {"x": 0.52, "y": 0.08},
                        "pelvis": {"x": 0.5, "y": 0.58},
                        "wrist_l": {"x": 0.33, "y": 0.24},
                    },
                }
            }
        )

        _, _, _, summary_json = node.build(
            settings_json=settings_json,
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image",
            pose_image_strength=1.0,
            capture_w=640,
            capture_h=640,
        )

        summary = json.loads(summary_json)
        self.assertTrue(summary["image_fit"]["applied"])
        self.assertEqual(summary["image_fit"]["manual_anchor_count"], 3)
        self.assertGreaterEqual(summary["image_fit"]["anchor_count"], 3)

    def test_pose_studio_fit_from_image_can_disable_anchor_groups(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=640,
            capture_h=640,
        )

        settings_json = json.dumps(
            {
                "image_fit": {
                    "selected_anchor": "hand_l",
                    "anchors": {
                        "head": {"x": 0.52, "y": 0.08},
                        "hand_l": {"x": 0.18, "y": 0.18},
                        "toe_l": {"x": 0.34, "y": 0.92},
                    },
                    "enabled_groups": {
                        "face": True,
                        "body": True,
                        "hands": False,
                        "feet": False,
                    },
                }
            }
        )

        _, _, _, summary_json = node.build(
            settings_json=settings_json,
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image",
            pose_image_strength=1.0,
            capture_w=640,
            capture_h=640,
        )

        summary = json.loads(summary_json)
        self.assertTrue(summary["image_fit"]["applied"])
        self.assertEqual(summary["image_fit"]["manual_anchor_count"], 1)
        self.assertGreaterEqual(summary["image_fit"]["anchor_count"], 1)

    def test_pose_studio_fit_from_image_supports_fine_anchor_groups(self) -> None:
        node = MKRPoseStudio()
        _, pose_guide, _, _ = node.build(
            pose_preset="reach_up",
            capture_w=640,
            capture_h=640,
        )

        settings_json = json.dumps(
            {
                "image_fit": {
                    "selected_anchor": "hand_l",
                    "anchors": {
                        "head": {"x": 0.52, "y": 0.08},
                        "wrist_l": {"x": 0.22, "y": 0.20},
                        "hand_l": {"x": 0.18, "y": 0.16},
                        "ankle_l": {"x": 0.32, "y": 0.88},
                        "toe_l": {"x": 0.36, "y": 0.94},
                    },
                    "enabled_groups": {
                        "head_face": True,
                        "torso": False,
                        "arms": False,
                        "hands": False,
                        "fingers": True,
                        "legs": False,
                        "feet": False,
                        "toes": True,
                    },
                }
            }
        )

        _, _, _, summary_json = node.build(
            settings_json=settings_json,
            pose_preset="neutral",
            pose_reference_image=pose_guide,
            pose_from_image_mode="fit_from_image",
            pose_image_strength=1.0,
            capture_w=640,
            capture_h=640,
        )

        summary = json.loads(summary_json)
        self.assertTrue(summary["image_fit"]["applied"])
        self.assertEqual(summary["image_fit"]["manual_anchor_count"], 3)
        self.assertGreaterEqual(summary["image_fit"]["anchor_count"], 3)

    def test_publish_promo_frame_preserves_batch_count(self) -> None:
        node = MKRPublishPromoFrame()
        frames = torch.zeros((2, 64, 96, 3), dtype=torch.float32)

        image, info_json = node.frame(
            image=frames,
            title="Launch Frames",
            subtitle="Quick publish wrappers",
            body="Built to turn raw outputs into cleaner promo cards.",
            badge="DROP",
            cta="See the set",
            footer="MKRShift",
            theme="Signal",
            margin_px=20,
            header_px=56,
            copy_height_px=96,
            show_index=True,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape)[0], 2)
        self.assertEqual(info["count"], 2)
        self.assertEqual(info["badge"], "DROP")
        self.assertEqual(info["frames"][0]["output_size"], [136, 256])

    def test_publish_end_card_can_render_with_background(self) -> None:
        node = MKRPublishEndCard()
        background = torch.ones((1, 32, 32, 3), dtype=torch.float32) * 0.5

        image, info_json = node.render(
            width=640,
            height=960,
            title="Thanks for watching",
            subtitle="See the full breakdown next",
            body="One clean closing card for launch posts, carousels, or reels.",
            cta="Follow for the next drop",
            footer="MKRShift",
            theme="Carbon",
            margin_px=40,
            background_image=background,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (1, 960, 640, 3))
        self.assertTrue(info["has_background"])

    def test_maskgen_skin_tones_prefers_warm_skin_like_pixels(self) -> None:
        node = x1MaskGen()
        image = torch.tensor(
            [
                [
                    [[0.78, 0.60, 0.50], [0.12, 0.22, 0.92]],
                    [[0.72, 0.52, 0.42], [0.08, 0.78, 0.22]],
                ]
            ],
            dtype=torch.float32,
        )

        result = node.run(image=image, mode="skin_tones")
        mask = result["result"][0][0]

        warm_mean = float(mask[0, 0] + mask[1, 0]) / 2.0
        cool_mean = float(mask[0, 1] + mask[1, 1]) / 2.0

        self.assertGreater(warm_mean, 0.45)
        self.assertLess(cool_mean, 0.35)
        self.assertGreater(warm_mean, cool_mean + 0.2)

    def test_presave_video_frame_preview_marks_image_media_kind(self) -> None:
        node = MKRPresaveVideo()
        frames = torch.zeros((3, 8, 8, 3), dtype=torch.float32)

        result = node.run(video=frames, preview_only=True)
        state = result["ui"]["presave_media_state"][0]
        preview = result["ui"]["presave_video_preview"][0]

        self.assertEqual(state["preview_media_kind"], "image")
        self.assertEqual(preview["media_kind"], "image")
        self.assertEqual(preview["format"], "webp")

    def test_axb_compare_preserves_definition_aware_preview_metadata(self) -> None:
        node = AxBCompare()
        image_a = torch.zeros((1, 800, 1200, 3), dtype=torch.float32)
        image_b = torch.zeros((1, 400, 600, 3), dtype=torch.float32)

        result = node.run(image_a=image_a, image_b=image_b, orientation="horizontal")
        compare_state = result["ui"]["compare_state"][0]
        preview_a = result["ui"]["a_preview"][0]
        preview_b = result["ui"]["b_preview"][0]

        self.assertEqual(compare_state["display_mode"], "actual_definition")
        self.assertEqual(compare_state["preview_max_size"], 4096)
        self.assertEqual(compare_state["image_a_size"], [1200, 800])
        self.assertEqual(compare_state["image_b_size"], [600, 400])
        self.assertEqual(compare_state["compare_canvas_size"], [1200, 800])
        self.assertEqual(preview_a["width"], 1200)
        self.assertEqual(preview_a["height"], 800)
        self.assertFalse(preview_a["downscaled"])
        self.assertEqual(preview_b["width"], 600)
        self.assertEqual(preview_b["height"], 400)
        self.assertFalse(preview_b["downscaled"])

    def test_axb_compare_reports_downscaled_preview_when_preview_cap_is_smaller(self) -> None:
        node = AxBCompare()
        image_a = torch.zeros((1, 1600, 2400, 3), dtype=torch.float32)
        image_b = torch.zeros((1, 400, 600, 3), dtype=torch.float32)

        result = node.run(
            image_a=image_a,
            image_b=image_b,
            orientation="horizontal",
            preview_max_size=1024,
        )
        preview_a = result["ui"]["a_preview"][0]
        compare_state = result["ui"]["compare_state"][0]

        self.assertEqual(compare_state["preview_max_size"], 1024)
        self.assertTrue(preview_a["downscaled"])
        self.assertEqual(preview_a["source_width"], 2400)
        self.assertEqual(preview_a["source_height"], 1600)
        self.assertLessEqual(preview_a["width"], 1024)
        self.assertLessEqual(preview_a["height"], 1024)

    def test_image_split_grid_returns_equal_tiles_and_metadata(self) -> None:
        split_node = MKRImageSplitGrid()
        image = torch.linspace(0.0, 1.0, 1 * 5 * 7 * 3, dtype=torch.float32).reshape(1, 5, 7, 3)

        tiles, split_info_json, summary = split_node.split(
            image=image,
            columns=3,
            rows=2,
            size_mode="pad",
            anchor="center",
            overlap_px=1,
            pad_mode="edge",
            pad_value=0.0,
        )

        info = json.loads(split_info_json)
        self.assertEqual(tuple(tiles.shape), (6, 5, 5, 3))
        self.assertEqual(info["columns"], 3)
        self.assertEqual(info["rows"], 2)
        self.assertEqual(info["tile_width"], 3)
        self.assertEqual(info["tile_height"], 3)
        self.assertEqual(info["tile_full_width"], 5)
        self.assertEqual(info["tile_full_height"], 5)
        self.assertEqual(info["canvas_width"], 9)
        self.assertEqual(info["canvas_height"], 6)
        self.assertEqual(info["source_window"], [0, 0, 7, 5])
        self.assertIn("equal tiles", summary)

    def test_image_split_and_combine_roundtrip_with_overlap(self) -> None:
        split_node = MKRImageSplitGrid()
        combine_node = MKRImageCombineGrid()

        y = torch.linspace(0.0, 1.0, 5, dtype=torch.float32).view(5, 1).expand(5, 7)
        x = torch.linspace(0.0, 1.0, 7, dtype=torch.float32).view(1, 7).expand(5, 7)
        image = torch.stack((x, y, (x + y) * 0.5), dim=-1).unsqueeze(0)

        tiles, split_info_json, _ = split_node.split(
            image=image,
            columns=3,
            rows=2,
            size_mode="pad",
            anchor="center",
            overlap_px=1,
            pad_mode="edge",
            pad_value=0.0,
        )
        combined, combine_info_json, summary = combine_node.combine(
            tiles=tiles,
            split_info_json=split_info_json,
            columns=3,
            rows=2,
            size_mode="pad",
            overlap_px=1,
            canvas_width=0,
            canvas_height=0,
            original_width=0,
            original_height=0,
            content_x=0,
            content_y=0,
            blend_mode="feather",
        )

        info = json.loads(combine_info_json)
        self.assertEqual(tuple(combined.shape), tuple(image.shape))
        self.assertTrue(torch.allclose(combined, image, atol=1e-6))
        self.assertEqual(info["output_width"], 7)
        self.assertEqual(info["output_height"], 5)
        self.assertEqual(info["blend_mode"], "feather")
        self.assertIn("Combined", summary)

    def test_image_split_and_combine_crop_mode_returns_source_window(self) -> None:
        split_node = MKRImageSplitGrid()
        combine_node = MKRImageCombineGrid()
        image = torch.linspace(0.0, 1.0, 1 * 5 * 7 * 3, dtype=torch.float32).reshape(1, 5, 7, 3)

        tiles, split_info_json, _ = split_node.split(
            image=image,
            columns=3,
            rows=2,
            size_mode="crop",
            anchor="center",
            overlap_px=1,
            pad_mode="edge",
            pad_value=0.0,
        )
        split_info = json.loads(split_info_json)
        combined, combine_info_json, summary = combine_node.combine(
            tiles=tiles,
            split_info_json=split_info_json,
            columns=3,
            rows=2,
            size_mode="crop",
            overlap_px=1,
            canvas_width=0,
            canvas_height=0,
            original_width=0,
            original_height=0,
            content_x=0,
            content_y=0,
            blend_mode="feather",
        )

        info = json.loads(combine_info_json)
        x0, y0, x1, y1 = split_info["source_window"]
        expected = image[:, y0:y1, x0:x1, :]
        self.assertEqual(tuple(combined.shape), tuple(expected.shape))
        self.assertTrue(torch.allclose(combined, expected, atol=1e-6))
        self.assertEqual(info["source_window"], split_info["source_window"])
        self.assertIn(f"crop window {x0},{y0} -> {x1},{y1}", summary)

    def test_image_combine_supports_manual_restore_without_split_metadata(self) -> None:
        split_node = MKRImageSplitGrid()
        combine_node = MKRImageCombineGrid()
        image = torch.linspace(0.0, 1.0, 1 * 5 * 7 * 3, dtype=torch.float32).reshape(1, 5, 7, 3)

        tiles, split_info_json, _ = split_node.split(
            image=image,
            columns=3,
            rows=2,
            size_mode="pad",
            anchor="center",
            overlap_px=1,
            pad_mode="edge",
            pad_value=0.0,
        )
        info = json.loads(split_info_json)
        combined, combine_info_json, _ = combine_node.combine(
            tiles=tiles,
            split_info_json="",
            columns=info["columns"],
            rows=info["rows"],
            size_mode=info["size_mode"],
            overlap_px=info["overlap_px"],
            canvas_width=info["canvas_width"],
            canvas_height=info["canvas_height"],
            original_width=info["original_width"],
            original_height=info["original_height"],
            content_x=info["content_x"],
            content_y=info["content_y"],
            blend_mode="feather",
        )

        combine_info = json.loads(combine_info_json)
        self.assertEqual(tuple(combined.shape), tuple(image.shape))
        self.assertTrue(torch.allclose(combined, image, atol=1e-6))
        self.assertEqual(combine_info["source_window"], [0, 0, 7, 5])

    def test_legacy_module_aliases_resolve_to_new_package_paths(self) -> None:
        expected = {
            "xpresave_media": "MKRShift_Nodes.nodes.presave_media_nodes",
            "xmask": "MKRShift_Nodes.nodes.mask_nodes",
            "xcolor": "MKRShift_Nodes.nodes.xcolor",
            "xcine": "MKRShift_Nodes.nodes.xcine",
            "xshared": "MKRShift_Nodes.lib.image_shared",
        }

        for alias, target in expected.items():
            with self.subTest(alias=alias):
                module = importlib.import_module(f"MKRShift_Nodes.{alias}")
                self.assertEqual(module.__name__, target)

    def test_studio_slate_returns_expected_canvas_and_metadata(self) -> None:
        node = MKRStudioSlate()
        image, slate_json, summary = node.build(
            width=640,
            height=360,
            theme="Signal",
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            notes="Check parallax and edge detail.",
        )

        slate = json.loads(slate_json)
        self.assertEqual(tuple(image.shape), (1, 360, 640, 3))
        self.assertEqual(slate["project"], "Studio Test")
        self.assertEqual(slate["size"], [640, 360])
        self.assertEqual(slate["theme"], "Signal")
        self.assertIn("B012", summary)

    def test_studio_review_frame_preserves_batch_count_and_reports_layout(self) -> None:
        node = MKRStudioReviewFrame()
        frames = torch.zeros((2, 64, 96, 3), dtype=torch.float32)

        image, info_json = node.frame(
            image=frames,
            theme="Paper",
            margin_px=20,
            header_px=48,
            footer_px=32,
            show_safe_area=False,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (2, 184, 136, 3))
        self.assertEqual(info["count"], 2)
        self.assertFalse(info["show_safe_area"])
        self.assertEqual(info["frames"][0]["output_size"], [136, 184])

    def test_studio_contact_sheet_builds_labeled_review_board(self) -> None:
        node = MKRStudioContactSheet()
        frames = torch.zeros((5, 48, 64, 3), dtype=torch.float32)

        image, info_json = node.board(
            images=frames,
            title="Daily Selects",
            subtitle="Five options",
            theme="Blueprint",
            columns=3,
            cell_width=80,
            gap_px=12,
            margin_px=24,
            header_px=72,
            footer_px=48,
            label_prefix="SHOT",
            start_index=12,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (1, 388, 312, 3))
        self.assertEqual(info["count"], 5)
        self.assertEqual(info["rows"], 2)
        self.assertEqual(info["columns"], 3)
        self.assertEqual(info["board_size"], [312, 388])
        self.assertEqual(info["frames"][0]["label"], "SHOT 12")
        self.assertEqual(info["footer_layout"], "stacked")

    def test_studio_contact_sheet_clips_card_content_to_rounded_shape(self) -> None:
        node = MKRStudioContactSheet()
        frames = torch.ones((1, 48, 64, 3), dtype=torch.float32)

        image, info_json = node.board(
            images=frames,
            title="Daily Selects",
            subtitle="Rounded crop check",
            theme="Carbon",
            columns=1,
            cell_width=96,
            gap_px=12,
            margin_px=24,
            header_px=72,
            footer_px=48,
            label_prefix="SHOT",
            start_index=1,
        )

        info = json.loads(info_json)
        card_x = 24
        card_y = 24 + 72
        card_w, card_h = info["card_size"]
        corner_pixel = image[0, card_y + 4, card_x + 4]
        center_pixel = image[0, card_y + 28, card_x + 28]
        bottom_corner_pixel = image[0, card_y + card_h - 5, card_x + 4]
        label_fill_pixel = image[0, card_y + card_h - 8, card_x + (card_w // 2)]

        self.assertEqual(info["board_size"][0], int(image.shape[2]))
        self.assertLess(float(corner_pixel.mean()), 0.95)
        self.assertGreater(float(center_pixel.mean()), 0.95)
        self.assertLess(float(bottom_corner_pixel.mean()), 0.13)
        self.assertGreater(float(label_fill_pixel.mean()), float(bottom_corner_pixel.mean()) + 0.03)

    def test_studio_delivery_plan_builds_save_ready_naming_bundle(self) -> None:
        slate_node = MKRStudioSlate()
        review_node = MKRStudioReviewFrame()
        delivery_node = MKRStudioDeliveryPlan()

        _, slate_json, _ = slate_node.build(
            width=640,
            height=360,
            theme="Carbon",
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            artist="Ada",
            date_text="2026-03-09",
        )
        _, review_info = review_node.frame(image=torch.zeros((1, 64, 96, 3), dtype=torch.float32), version_tag="v003")

        filename_prefix, subfolder, review_title, manifest_notes_json, delivery_plan_json = delivery_node.plan(
            project="",
            sequence="",
            shot="",
            take="",
            version_tag="v003",
            deliverable="Review",
            department="Lookdev",
            artist="Ada",
            client="Northstar",
            date_text="2026-03-09",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=True,
            include_client=False,
            slate_json=slate_json,
            review_frame_info=review_info,
            notes_json='{"priority":"client"}',
        )

        manifest_notes = json.loads(manifest_notes_json)
        delivery_plan = json.loads(delivery_plan_json)

        self.assertEqual(filename_prefix, "studio_test_seq_07_b012_t03_v003_lookdev_review_2026_03_09_ada")
        self.assertEqual(subfolder, "studio_test/seq_07/b012/review/v003")
        self.assertEqual(review_title, "Studio Test | SEQ_07 | B012 | v003")
        self.assertEqual(manifest_notes["delivery"]["aspect"], "16:9")
        self.assertEqual(manifest_notes["labels"]["badge"], "IN REVIEW")
        self.assertEqual(manifest_notes["suggested_files"]["manifest"], f"{filename_prefix}_manifest.json")
        self.assertEqual(delivery_plan["manifest_notes"]["source_counts"]["review_frames"], 1)

    def test_studio_review_burnin_uses_delivery_plan_labels(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        burnin_node = MKRStudioReviewBurnIn()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v003",
            deliverable="Review",
            department="Lookdev",
            artist="Ada",
            client="",
            date_text="2026-03-09",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        frames = torch.zeros((2, 64, 96, 3), dtype=torch.float32)
        image, info_json = burnin_node.burn_in(
            image=frames,
            title="",
            subtitle="",
            badge="",
            theme="Signal",
            footer_left="",
            footer_right="",
            inset_px=10,
            band_height_px=28,
            accent_width_px=6,
            opacity=0.85,
            show_frame_index=True,
            delivery_plan_json=delivery_plan_json,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (2, 64, 96, 3))
        self.assertEqual(info["labels"]["title"], "Studio Test | SEQ_07 | B012 | v003")
        self.assertEqual(info["labels"]["badge"], "IN REVIEW")
        self.assertTrue(float(image.mean()) > 0.01)

    def test_studio_compare_board_builds_exportable_pair_layout(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        compare_node = MKRStudioCompareBoard()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v004",
            deliverable="Review",
            department="Comp",
            artist="Ada",
            client="Northstar",
            date_text="2026-03-09",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=False,
            include_artist=False,
            include_client=False,
        )

        image_a = torch.zeros((1, 64, 96, 3), dtype=torch.float32)
        image_b = torch.ones((1, 64, 96, 3), dtype=torch.float32)
        image, info_json = compare_node.board(
            image_a=image_a,
            image_b=image_b,
            title="",
            subtitle="",
            label_a="Before",
            label_b="After",
            theme="Paper",
            orientation="Horizontal",
            footer_left="",
            footer_right="",
            margin_px=20,
            gutter_px=12,
            header_px=48,
            footer_px=32,
            shadow_strength=0.2,
            show_index=True,
            delivery_plan_json=delivery_plan_json,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (1, 184, 244, 3))
        self.assertEqual(info["orientation"], "horizontal")
        self.assertEqual(info["title"], "Studio Test | SEQ_07 | B012 | v004")
        self.assertEqual(info["rows"][0]["label_a"], "Before")
        self.assertEqual(info["rows"][0]["output_size"], [244, 184])
        self.assertTrue(float(image.mean()) > 0.05)

    def test_studio_selection_set_builds_contact_sheet_ready_selection_json(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        selection_node = MKRStudioSelectionSet()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v003",
            deliverable="Client Selects",
            department="Lookdev",
            artist="Ada",
            client="Northstar",
            task="Beauty Pass",
            round_label="Round 2",
            reviewer="Jules",
            date_text="2026-03-09",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        selection_json, manifest_json, frames_csv, summary, count = selection_node.build(
            marked_frames="12:hero|best lighting\n14-15:select\n18:revise|hair cleanup",
            default_status="SELECT",
            delivery_plan_json=delivery_plan_json,
            reviewer="Jules",
            round_label="Round 2",
        )

        selections = json.loads(selection_json)
        manifest = json.loads(manifest_json)

        self.assertEqual(count, 4)
        self.assertEqual(frames_csv, "12,14,15,18")
        self.assertEqual(selections["12"]["status"], "HERO")
        self.assertEqual(selections["18"]["note"], "hair cleanup")
        self.assertEqual(manifest["status_counts"]["SELECT"], 2)
        self.assertEqual(manifest["reviewer"], "Jules")
        self.assertIn("Round 2", summary)

    def test_batch_difference_preview_reports_pair_deltas(self) -> None:
        node = MKRBatchDifferencePreview()
        image_a = torch.zeros((1, 12, 12, 3), dtype=torch.float32)
        image_b = torch.ones((1, 12, 12, 3), dtype=torch.float32)

        image_out, preview, layout_json = node.run(
            image_a=image_a,
            image_b=image_b,
            columns=1,
            layout_mode="A | B | Diff",
            difference_style="heat",
            difference_gain=2.0,
            tile_fit_mode="contain",
            panel_padding=8,
            panel_gap=8,
            label_height=28,
            show_resolution=True,
            theme="dark",
            max_collage_side=512,
        )

        layout = json.loads(layout_json)
        self.assertEqual(tuple(image_out.shape), tuple(image_a.shape))
        self.assertEqual(preview.shape[0], 1)
        self.assertEqual(layout["count"], 1)
        self.assertEqual(layout["layout_mode"], "A | B | Diff")
        self.assertGreater(layout["rows_meta"][0]["mean_delta"], 0.95)

    def test_gcode_printer_profile_uses_gcode_studio_style_fields(self) -> None:
        node = MKRGCodePrinterProfile()
        profile, profile_json, summary = node.build(
            printer_name="Ender Test",
            bed_width_mm=235,
            bed_depth_mm=235,
            nozzle_diameter_mm=0.4,
            line_width_mm=0.48,
            layer_height_mm=0.24,
            filament_diameter_mm=1.75,
            print_speed_mm_s=35,
            travel_speed_mm_s=120,
        )

        payload = json.loads(profile_json)
        self.assertEqual(profile["name"], "Ender Test")
        self.assertEqual(payload["bedW"], 235.0)
        self.assertEqual(payload["lineWidth"], 0.48)
        self.assertEqual(payload["speedPrint"], 2100.0)
        self.assertIn("Ender Test", summary)

    def test_gcode_orca_profile_loader_maps_exported_presets(self) -> None:
        bundle_path = self._write_temp_orca_bundle()
        node = MKRGCodeOrcaProfileLoader()

        profile, slicer_settings, bundle_json, summary = node.load(
            source_path=str(bundle_path),
            printer_match="Printer Alpha",
            filament_match="PLA Standard",
            process_match="Draft 0.28",
            selection_mode="auto",
            recursive=True,
        )

        payload = json.loads(bundle_json)
        self.assertEqual(profile["name"], "Printer Alpha")
        self.assertEqual(profile["bedW"], 220.0)
        self.assertEqual(profile["layerHeight"], 0.28)
        self.assertEqual(profile["tempNozzle"], 215)
        self.assertEqual(slicer_settings["config"]["layer_height"], 0.28)
        self.assertEqual(payload["counts"]["printers"], 1)
        self.assertIn("Orca loader", summary)

    def test_gcode_load_mesh_model_reads_stl_and_renders_preview(self) -> None:
        stl_path = self._write_temp_text(
            "triangle.stl",
            "\n".join(
                [
                    "solid tri",
                    "facet normal 0 0 0",
                    "outer loop",
                    "vertex 0 0 2",
                    "vertex 20 0 2",
                    "vertex 0 20 2",
                    "endloop",
                    "endfacet",
                    "endsolid tri",
                ]
            ),
        )
        node = MKRGCodeLoadMeshModel()

        mesh, preview, mesh_info_json, summary = node.load(
            model_path=str(stl_path),
            center_xy=False,
            bed_align=True,
            scale=1.0,
            rotate_x_deg=0.0,
            rotate_y_deg=0.0,
            rotate_z_deg=0.0,
            translate_x_mm=0.0,
            translate_y_mm=0.0,
            translate_z_mm=0.0,
            preview_view="isometric",
            preview_size=256,
        )

        info = json.loads(mesh_info_json)
        self.assertEqual(mesh["tri_count"], 1)
        self.assertEqual(tuple(preview.shape), (1, 256, 256, 3))
        self.assertEqual(info["bounds"]["min_z"], 0.0)
        self.assertIn("triangle.stl", summary)

    def test_gcode_heightmap_plate_generates_plan_and_preview(self) -> None:
        node = MKRGCodeHeightmapPlate()
        image = torch.tensor(
            [[
                [[0.0, 0.0, 0.0], [0.33, 0.33, 0.33], [0.66, 0.66, 0.66], [1.0, 1.0, 1.0]],
                [[0.0, 0.0, 0.0], [0.33, 0.33, 0.33], [0.66, 0.66, 0.66], [1.0, 1.0, 1.0]],
                [[0.0, 0.0, 0.0], [0.33, 0.33, 0.33], [0.66, 0.66, 0.66], [1.0, 1.0, 1.0]],
                [[0.0, 0.0, 0.0], [0.33, 0.33, 0.33], [0.66, 0.66, 0.66], [1.0, 1.0, 1.0]],
            ]],
            dtype=torch.float32,
        )

        plan, preview, info_json, summary = node.build(
            image=image,
            width_mm=24.0,
            height_mm=24.0,
            base_layers=2,
            relief_height_mm=0.8,
            layer_height_mm=0.2,
            line_width_mm=0.8,
            fill_mode="alternate_xy",
            invert_heightmap=False,
            print_speed_mm_s=20.0,
            travel_speed_mm_s=80.0,
        )

        info = json.loads(info_json)
        self.assertEqual(plan["mode"], "heightmap_plate")
        self.assertGreater(plan["stats"]["print_moves"], 10)
        self.assertEqual(tuple(preview.shape), (1, 768, 768, 3))
        self.assertEqual(info["meta"]["base_layers"], 2)
        self.assertIn("Heightmap plate", summary)

    def test_gcode_spiral_vase_exports_printable_gcode(self) -> None:
        profile_node = MKRGCodePrinterProfile()
        plan_node = MKRGCodeSpiralVase()
        export_node = MKRGCodeExport()

        profile, _, _ = profile_node.build(printer_name="Vase Rig", print_speed_mm_s=22.0, travel_speed_mm_s=120.0)
        plan, _, info_json, _ = plan_node.build(
            height_mm=30.0,
            base_radius_mm=10.0,
            top_radius_mm=8.0,
            bottom_layers=2,
            layer_height_mm=0.2,
            line_width_mm=0.45,
            segments_per_turn=24,
            wave_amplitude_mm=1.0,
            wave_frequency=3.0,
            print_speed_mm_s=18.0,
            travel_speed_mm_s=100.0,
        )

        gcode_text, output_path, summary_json = export_node.run(
            plan=plan,
            profile=profile,
            filename_prefix="test_vase",
            subfolder="",
            save_file=False,
            overwrite=False,
            include_comments=True,
        )

        summary = json.loads(summary_json)
        info = json.loads(info_json)
        self.assertEqual(plan["mode"], "spiral_vase")
        self.assertIn("G21", gcode_text)
        self.assertIn("M82", gcode_text)
        self.assertIn("; LAYER:", gcode_text)
        self.assertIn("G1 X", gcode_text)
        self.assertEqual(output_path, "")
        self.assertGreater(summary["line_count"], 20)
        self.assertGreater(info["stats"]["print_length_mm"], 50.0)

    def test_gcode_preview_parses_raw_gcode_into_plan(self) -> None:
        node = MKRGCodePreview()
        gcode_text = "\n".join(
            [
                "G21",
                "G90",
                "M82",
                "; LAYER:0",
                "G0 X0 Y0 Z0.2 F6000",
                "G1 X10 Y0 Z0.2 E0.500 F1800",
                "; LAYER:1",
                "G1 X10 Y10 Z0.4 E1.000 F1800",
            ]
        )

        preview, info_json, summary, plan = node.run(
            view_mode="auto",
            preview_size=256,
            gcode_text=gcode_text,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(preview.shape), (1, 256, 256, 3))
        self.assertEqual(plan["mode"], "imported_gcode")
        self.assertTrue(info["gcode_loaded"])
        self.assertGreater(plan["stats"]["print_moves"], 0)
        self.assertIn("G-code preview", summary)

    def test_gcode_plan_analyzer_reports_costs_and_risks(self) -> None:
        profile_node = MKRGCodePrinterProfile()
        plan_node = MKRGCodeHeightmapPlate()
        analyzer_node = MKRGCodePlanAnalyzer()

        profile, _, _ = profile_node.build(
            printer_name="Mini Bed",
            bed_width_mm=50.0,
            bed_depth_mm=50.0,
            bed_height_mm=10.0,
            print_speed_mm_s=40.0,
        )
        image = torch.linspace(0.0, 1.0, 16, dtype=torch.float32).reshape(1, 4, 4, 1).repeat(1, 1, 1, 3)
        plan, _, _, _ = plan_node.build(
            image=image,
            width_mm=64.0,
            height_mm=64.0,
            base_layers=2,
            relief_height_mm=1.0,
            layer_height_mm=0.2,
            line_width_mm=0.4,
            print_speed_mm_s=40.0,
            travel_speed_mm_s=120.0,
        )

        _, analysis_json, warnings_json, summary = analyzer_node.analyze(
            plan=plan,
            max_volumetric_flow_mm3_s=2.0,
            min_feature_mm=5.0,
            min_layer_time_s=30.0,
            warn_travel_ratio_percent=5.0,
            filament_price_per_kg=28.0,
            material_density_g_cm3=1.24,
            printer_wattage_w=150.0,
            electricity_price_per_kwh=0.25,
            profile=profile,
        )

        analysis = json.loads(analysis_json)
        warnings = json.loads(warnings_json)["warnings"]
        self.assertGreater(analysis["material_estimate"]["mass_g"], 0.0)
        self.assertGreater(analysis["cost_estimate"]["total_cost"], 0.0)
        self.assertFalse(analysis["bed_fit"]["fits_xy"])
        self.assertGreaterEqual(len(warnings), 2)
        self.assertIn("warnings", analysis)
        self.assertIn("Analyzer", summary)

    def test_gcode_bed_mesh_compensation_offsets_plan_z_values(self) -> None:
        profile_node = MKRGCodePrinterProfile()
        plan_node = MKRGCodeSpiralVase()
        mesh_node = MKRGCodeBedMeshCompensate()

        profile, _, _ = profile_node.build(printer_name="Mesh Rig")
        plan, _, _, _ = plan_node.build(
            height_mm=12.0,
            base_radius_mm=8.0,
            top_radius_mm=8.0,
            bottom_layers=1,
            layer_height_mm=0.2,
            line_width_mm=0.45,
            segments_per_turn=16,
            print_speed_mm_s=18.0,
            travel_speed_mm_s=100.0,
        )
        original_first_z = plan["moves"][0]["z"]

        adjusted_plan, report_json, summary = mesh_node.apply(
            plan=plan,
            mesh_json='{"bed_width_mm":220,"bed_depth_mm":220,"offsets":[[0.12,0.12],[0.12,0.12]]}',
            max_compensation_mm=0.2,
            warn_if_over_mm=0.05,
            fade_height_mm=10.0,
            use_profile_bed_size=True,
            profile=profile,
        )

        report = json.loads(report_json)
        adjusted_first_z = adjusted_plan["moves"][0]["z"]
        self.assertGreater(adjusted_first_z, original_first_z)
        self.assertGreater(report["max_applied_compensation_mm"], 0.0)
        self.assertIn("bed_mesh_compensation", adjusted_plan["meta"])
        self.assertIn("Bed mesh", summary)

    def test_gcode_calibration_tower_injects_layer_commands(self) -> None:
        profile_node = MKRGCodePrinterProfile()
        plan_node = MKRGCodeSpiralVase()
        export_node = MKRGCodeExport()
        calibration_node = MKRGCodeCalibrationTower()

        profile, _, _ = profile_node.build(printer_name="Tower Rig")
        plan, _, _, _ = plan_node.build(
            height_mm=12.0,
            base_radius_mm=9.0,
            top_radius_mm=8.0,
            bottom_layers=1,
            layer_height_mm=0.2,
            line_width_mm=0.45,
            segments_per_turn=16,
            print_speed_mm_s=18.0,
            travel_speed_mm_s=100.0,
        )
        gcode_text, _, _ = export_node.run(
            plan=plan,
            profile=profile,
            filename_prefix="tower_test",
            save_file=False,
            include_comments=True,
        )

        calibrated_text, steps_json, summary = calibration_node.apply(
            plan=plan,
            gcode_text=gcode_text,
            axis="layer_index",
            target="temp",
            start_value=220.0,
            step_value=-5.0,
            every=1.0,
            clamp_min=190.0,
            clamp_max=240.0,
            only_on_change=True,
        )

        steps = json.loads(steps_json)
        self.assertIn("M104 S220", calibrated_text)
        self.assertIn("M104 S210", calibrated_text)
        self.assertGreaterEqual(steps["step_count"], 2)
        self.assertIn("Calibration tower", summary)

    def test_gcode_conditional_injector_applies_start_layer_and_end_rules(self) -> None:
        profile_node = MKRGCodePrinterProfile()
        plan_node = MKRGCodeSpiralVase()
        export_node = MKRGCodeExport()
        injector_node = MKRGCodeConditionalInjector()

        profile, _, _ = profile_node.build(printer_name="Inject Rig")
        plan, _, _, _ = plan_node.build(
            height_mm=12.0,
            base_radius_mm=9.0,
            top_radius_mm=8.0,
            bottom_layers=1,
            layer_height_mm=0.2,
            line_width_mm=0.45,
            segments_per_turn=16,
            print_speed_mm_s=18.0,
            travel_speed_mm_s=100.0,
        )
        gcode_text, _, _ = export_node.run(
            plan=plan,
            profile=profile,
            filename_prefix="inject_test",
            save_file=False,
            include_comments=True,
        )

        injected_text, applied_json, summary = injector_node.apply(
            plan=plan,
            gcode_text=gcode_text,
            rules_json='[{"label":"announce-start","when":"start","inject":"M117 START {mode}"},{"label":"note-layer","when":"layer_change","layer":2,"inject":"M117 LAYER {layer} Z{z:.2f}"},{"label":"announce-end","when":"end","inject":"M118 DONE {mode}"}]',
        )

        applied = json.loads(applied_json)
        self.assertIn("M117 START spiral_vase", injected_text)
        self.assertIn("M117 LAYER 2 Z", injected_text)
        self.assertIn("M118 DONE spiral_vase", injected_text)
        self.assertEqual(applied["applied_count"], 3)
        self.assertIn("Conditional injector", summary)

    def test_gcode_external_slicer_builds_orca_dry_run_command(self) -> None:
        node = MKRGCodeExternalSlicer()
        mesh = {
            "schema": "mkr_gcode_mesh_v1",
            "format": "tris",
            "tris": [0.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 20.0, 0.0],
            "tri_count": 1,
            "bounds": {"min_x": 0.0, "max_x": 20.0, "min_y": 0.0, "max_y": 20.0, "min_z": 0.0, "max_z": 0.0},
            "meta": {},
        }
        slicer_settings = {
            "schema": "mkr_gcode_slicer_settings_v1",
            "source": "orca",
            "engine_family": "prusa_orca",
            "config": {"layer_height": 0.28, "perimeter_speed": 55},
        }

        gcode_text, plan, output_path, summary_json = node.run(
            mesh=mesh,
            engine="orca",
            engine_path="",
            engine_args_text="",
            filename_prefix="dry_run",
            subfolder="",
            save_file=False,
            overwrite=False,
            dry_run=True,
            profile=None,
            slicer_settings=slicer_settings,
            settings_json='{"fill_density":15}',
        )

        summary = json.loads(summary_json)
        self.assertEqual(gcode_text, "")
        self.assertEqual(plan, {})
        self.assertEqual(output_path, "")
        self.assertIn("--export-gcode", summary["command"])
        self.assertIn("layer_height = 0.28", summary["config_text"])
        self.assertIn("fill_density = 15", summary["config_text"])
        self.assertTrue(any("dry_run" in warning for warning in summary["warnings"]))


if __name__ == "__main__":
    unittest.main()
