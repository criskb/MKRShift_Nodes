import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.studio_nodes import (  # noqa: E402
    MKRStudioContactSheet,
    MKRStudioDeliveryPlan,
    MKRStudioReviewFrame,
    MKRStudioSlate,
)
from MKRShift_Nodes.nodes.studio_handoff_nodes import MKRStudioDeliverySheet, MKRStudioReviewNotes  # noqa: E402
from MKRShift_Nodes.nodes.studio_selection_nodes import MKRStudioSelectionSet  # noqa: E402


class StudioNodeUpgradeTests(unittest.TestCase):
    def test_studio_slate_exposes_version_badge_and_department_metadata(self) -> None:
        node = MKRStudioSlate()
        image, slate_json, summary = node.build(
            width=640,
            height=360,
            theme="Carbon",
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v014",
            department="Lighting",
            badge="CLIENT",
        )

        slate = json.loads(slate_json)
        self.assertEqual(tuple(image.shape), (1, 360, 640, 3))
        self.assertEqual(slate["version_tag"], "v014")
        self.assertEqual(slate["department"], "Lighting")
        self.assertEqual(slate["badge"], "CLIENT")
        self.assertIn("v014", summary)

    def test_studio_slate_can_inherit_delivery_plan_defaults(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        slate_node = MKRStudioSlate()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v008",
            deliverable="Review",
            department="Lighting",
            artist="Ada",
            client="Northstar",
            task="Relight finals",
            round_label="R4",
            reviewer="Jules",
            custom_badge="CLIENT NOTES",
            date_text="2026-03-11",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        image, slate_json, _ = slate_node.build(
            width=640,
            height=360,
            theme="Signal",
            project="",
            sequence="",
            shot="",
            take="",
            version_tag="",
            department="",
            badge="",
            artist="",
            date_text="",
            notes="",
            delivery_plan_json=delivery_plan_json,
        )

        slate = json.loads(slate_json)
        self.assertEqual(tuple(image.shape), (1, 360, 640, 3))
        self.assertEqual(slate["project"], "Studio Test")
        self.assertEqual(slate["version_tag"], "v008")
        self.assertEqual(slate["department"], "Lighting")
        self.assertEqual(slate["badge"], "CLIENT NOTES")
        self.assertIn("Relight finals", slate["notes"])

    def test_studio_slate_keeps_metadata_inside_panel_with_thumbnail(self) -> None:
        node = MKRStudioSlate()

        image, slate_json, _ = node.build(
            width=640,
            height=360,
            theme="Carbon",
            project="MKRShift Production",
            sequence="SEQ_01",
            shot="A001",
            take="1",
            thumbnail=torch.ones((1, 1080, 1623, 3), dtype=torch.float32) * 0.5,
        )

        slate = json.loads(slate_json)
        layout = slate["layout"]
        right_box = layout["right_box"]
        self.assertEqual(tuple(image.shape), (1, 360, 640, 3))
        self.assertLessEqual(layout["metadata_bottom"], right_box[3] - layout["right_inner_padding"])
        if slate["has_thumbnail"]:
            self.assertGreater(layout["thumbnail_height"], 0)
            self.assertTrue(layout["thumbnail_box"])
        else:
            self.assertIn("thumbnail hidden to keep metadata inside the right panel", slate["warnings"])

    def test_delivery_plan_emits_round_task_and_reviewer_labels(self) -> None:
        node = MKRStudioDeliveryPlan()
        filename_prefix, subfolder, review_title, manifest_notes_json, delivery_plan_json = node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v003",
            deliverable="Review",
            department="Comp",
            artist="Ada",
            client="Northstar",
            task="Edge cleanup",
            round_label="R2",
            reviewer="Jules",
            custom_badge="CLIENT NOTES",
            date_text="2026-03-10",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        manifest = json.loads(manifest_notes_json)
        delivery = json.loads(delivery_plan_json)

        self.assertIn("edge_cleanup", filename_prefix)
        self.assertIn("r2", filename_prefix)
        self.assertEqual(review_title, "Studio Test | SEQ_07 | B012 | v003")
        self.assertEqual(manifest["delivery"]["task"], "Edge cleanup")
        self.assertEqual(manifest["delivery"]["round_label"], "R2")
        self.assertEqual(manifest["delivery"]["reviewer"], "Jules")
        self.assertEqual(manifest["labels"]["badge"], "CLIENT NOTES")
        self.assertIn("R2", manifest["labels"]["review_subtitle"])
        self.assertIn("Edge cleanup", manifest["labels"]["footer_left"])
        self.assertIn("R2", manifest["labels"]["footer_right"])
        self.assertIn("compare_board", manifest["suggested_files"])
        self.assertIn("selection_manifest", manifest["suggested_files"])
        self.assertIn("review_notes", manifest["suggested_files"])
        self.assertIn("delivery_sheet", manifest["suggested_files"])
        self.assertEqual(delivery["manifest_notes"]["labels"]["reviewer"], "Jules")
        self.assertEqual(subfolder, "studio_test/seq_07/b012/review/v003")

    def test_review_frame_inherits_delivery_plan_labels(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        review_node = MKRStudioReviewFrame()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v005",
            deliverable="Review",
            department="Lookdev",
            artist="Ada",
            client="",
            task="Shader polish",
            round_label="R3",
            reviewer="Jules",
            custom_badge="SUP NOTES",
            date_text="2026-03-10",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        image, info_json = review_node.frame(
            image=torch.zeros((2, 64, 96, 3), dtype=torch.float32),
            title="Client Review",
            subtitle="Lookdev pass",
            badge="IN REVIEW",
            footer_left="MKRShift Nodes",
            footer_right="",
            version_tag="v005",
            show_safe_area=False,
            show_frame_index=False,
            delivery_plan_json=delivery_plan_json,
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape), (2, 400, 240, 3))
        self.assertEqual(info["labels"]["title"], "Studio Test | SEQ_07 | B012 | v005")
        self.assertIn("Shader polish", info["labels"]["subtitle"])
        self.assertEqual(info["labels"]["badge"], "SUP NOTES")
        self.assertEqual(info["labels"]["footer_left"], "Lookdev • Ada • Shader polish")
        self.assertFalse(info["show_frame_index"])

    def test_contact_sheet_inherits_plan_and_marks_selected_frames(self) -> None:
        delivery_node = MKRStudioDeliveryPlan()
        board_node = MKRStudioContactSheet()

        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v004",
            deliverable="Client Selects",
            department="Comp",
            artist="Ada",
            client="Northstar",
            task="Comp polish",
            round_label="R2",
            reviewer="Jules",
            custom_badge="SELECTS",
            date_text="2026-03-10",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
        )

        frames = torch.zeros((4, 48, 64, 3), dtype=torch.float32)
        image, info_json = board_node.board(
            images=frames,
            title="Daily Selects",
            subtitle="Batch review board",
            badge="CONTACT SHEET",
            theme="Signal",
            columns=2,
            cell_width=80,
            gap_px=12,
            margin_px=24,
            header_px=72,
            footer_px=48,
            label_prefix="SHOT",
            start_index=12,
            show_ratio=True,
            show_resolution=True,
            delivery_plan_json=delivery_plan_json,
            selection_json='{"12":"HERO","14":{"status":"HOLD","note":"Alt expression"}}',
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape)[0], 1)
        self.assertEqual(tuple(image.shape)[2], 220)
        self.assertEqual(tuple(image.shape)[3], 3)
        self.assertIn("Client Selects", info["title"])
        self.assertEqual(info["badge"], "SELECTS")
        self.assertEqual(info["board_size"][0], 220)
        self.assertEqual(info["footer_layout"], "stacked")
        self.assertGreaterEqual(info["footer_height"], 48)
        self.assertEqual(info["selection_count"], 2)
        self.assertEqual(info["selection_status_counts"]["HERO"], 1)
        self.assertEqual(info["selection_status_counts"]["HOLD"], 1)
        self.assertEqual(info["frames"][0]["selection"]["status"], "HERO")
        self.assertEqual(info["frames"][2]["selection"]["status"], "HOLD")
        self.assertEqual(info["frames"][2]["selection"]["note"], "Alt expression")

    def test_contact_sheet_stacks_footer_on_single_card_board(self) -> None:
        node = MKRStudioContactSheet()

        image, info_json = node.board(
            images=torch.zeros((1, 1080, 1623, 3), dtype=torch.float32),
            title="Daily Selects",
            subtitle="Batch review board",
            theme="Carbon",
            badge="CONTACT SHEET",
            columns=1,
            cell_width=360,
            gap_px=24,
            margin_px=40,
            header_px=112,
            footer_px=56,
            label_prefix="SHOT",
            start_index=1,
            show_ratio=True,
            show_resolution=True,
            selection_json='{"1":{"status":"HERO","note":"Primary client pick with extra long note"}}',
        )

        info = json.loads(info_json)
        self.assertEqual(tuple(image.shape)[0], 1)
        self.assertEqual(tuple(image.shape)[2], 440)
        self.assertEqual(info["footer_layout"], "stacked")
        self.assertGreaterEqual(info["footer_height"], 56)
        self.assertEqual(info["board_size"][1], int(image.shape[1]))

    def test_delivery_plan_can_embed_selection_manifest_metadata(self) -> None:
        selection_node = MKRStudioSelectionSet()
        delivery_node = MKRStudioDeliveryPlan()

        selection_json, selection_manifest_json, _, _, _ = selection_node.build(
            marked_frames="12:hero|best light\n14-15:select",
            default_status="SELECT",
            reviewer="Jules",
            round_label="R2",
        )

        _, _, _, manifest_notes_json, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v004",
            deliverable="Client Selects",
            department="Comp",
            artist="Ada",
            client="Northstar",
            date_text="2026-03-10",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
            selection_manifest_json=selection_manifest_json,
            notes_json=json.dumps({"selection_json": json.loads(selection_json)}),
        )

        manifest = json.loads(manifest_notes_json)
        delivery = json.loads(delivery_plan_json)

        self.assertEqual(manifest["source_counts"]["selection_frames"], 3)
        self.assertEqual(manifest["selection"]["frames_csv"], "12,14,15")
        self.assertEqual(manifest["selection"]["status_counts"]["HERO"], 1)
        self.assertIn("3 selected", delivery["summary"])

    def test_studio_review_notes_and_delivery_sheet_build_handoff_outputs(self) -> None:
        selection_node = MKRStudioSelectionSet()
        delivery_node = MKRStudioDeliveryPlan()
        notes_node = MKRStudioReviewNotes()
        sheet_node = MKRStudioDeliverySheet()

        _, selection_manifest_json, _, _, _ = selection_node.build(
            marked_frames="12:hero|best lighting\n18:revise|cleanup edge chatter",
            default_status="SELECT",
            reviewer="Jules",
            round_label="R5",
        )
        _, _, _, _, delivery_plan_json = delivery_node.plan(
            project="Studio Test",
            sequence="SEQ_07",
            shot="B012",
            take="3",
            version_tag="v009",
            deliverable="Client Selects",
            department="Lookdev",
            artist="Ada",
            client="Northstar",
            task="Shader polish",
            round_label="R5",
            reviewer="Jules",
            date_text="2026-03-12",
            naming_mode="Editorial",
            extension="png",
            include_take=True,
            include_date=True,
            include_artist=False,
            include_client=False,
            selection_manifest_json=selection_manifest_json,
        )

        review_notes_md, review_notes_json, summary = notes_node.build(
            delivery_plan_json=delivery_plan_json,
            headline="",
            next_steps="Update shader edges\nPrepare selects package",
            include_suggested_files=True,
            include_frame_notes=True,
            include_status_breakdown=True,
            selection_manifest_json=selection_manifest_json,
            extra_notes="Send to client after internal signoff.",
        )
        rows_json, delivery_sheet_md, summary_json, row_count = sheet_node.build(
            delivery_plan_json=delivery_plan_json,
            root_folder="/show/review",
            include_optional_files=True,
            include_selection_context=True,
            selection_manifest_json=selection_manifest_json,
        )

        review_notes = json.loads(review_notes_json)
        rows = json.loads(rows_json)
        sheet_summary = json.loads(summary_json)

        self.assertIn("## Selected Frames", review_notes_md)
        self.assertIn("cleanup edge chatter", review_notes_md)
        self.assertIn("selection_manifest", review_notes["suggested_files"])
        self.assertIn("2 selections", summary)
        self.assertGreaterEqual(row_count, 6)
        self.assertTrue(any(row["role"] == "review_notes" for row in rows))
        self.assertIn("| review_notes |", delivery_sheet_md)
        self.assertEqual(sheet_summary["selection_count"], 2)


if __name__ == "__main__":
    unittest.main()
