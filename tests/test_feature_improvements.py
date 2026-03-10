import importlib
import json
import sys
import unittest
import zipfile
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.mask_nodes import x1MaskGen  # noqa: E402
from MKRShift_Nodes.nodes.core_nodes import AxBCompare  # noqa: E402
from MKRShift_Nodes.nodes.presave_media_nodes import MKRPresaveVideo  # noqa: E402
from MKRShift_Nodes.nodes.social_nodes import MKRshiftSocialPackBuilder  # noqa: E402
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

    def test_social_pack_mixed_mode_cycles_pack_ratios(self) -> None:
        node = MKRshiftSocialPackBuilder()
        image = torch.zeros((1, 8, 8, 3), dtype=torch.float32)

        result = node.build(
            image=image,
            pack="After Hours Dump (pack_social_dump)",
            output_mode="Mixed",
            count=5,
            aspect="Auto",
            branding="Off",
            caption_tone="Clean",
            platform="Instagram",
            objective="Engagement",
            hook_style="Question",
            cta_mode="Soft",
            hashtag_mode="Lite",
        )

        plan_json = result["result"][1]
        plan = json.loads(plan_json)

        ratios = [item.get("ratio") for item in plan.get("shot_plan", [])]
        self.assertEqual(ratios[:5], ["4:5", "1:1", "9:16", "4:5", "1:1"])
        self.assertEqual(plan["generation"]["aspect_strategy"], "per_asset_cycle")
        self.assertEqual(plan["generation"]["ratios_used"], ["4:5", "1:1", "9:16"])

        asset = plan["assets"][0]
        self.assertIn("ratio", asset)
        self.assertIn("role", asset)
        self.assertIn("publish_at_local", asset)

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

    def test_legacy_module_aliases_resolve_to_new_package_paths(self) -> None:
        expected = {
            "social_pack": "MKRShift_Nodes.nodes.social_nodes",
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
