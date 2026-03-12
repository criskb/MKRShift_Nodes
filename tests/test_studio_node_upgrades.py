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
        self.assertEqual(tuple(image.shape), (1, 388, 220, 3))
        self.assertIn("Client Selects", info["title"])
        self.assertEqual(info["badge"], "SELECTS")
        self.assertEqual(info["selection_count"], 2)
        self.assertEqual(info["frames"][0]["selection"]["status"], "HERO")
        self.assertEqual(info["frames"][2]["selection"]["status"], "HOLD")
        self.assertEqual(info["frames"][2]["selection"]["note"], "Alt expression")


if __name__ == "__main__":
    unittest.main()
