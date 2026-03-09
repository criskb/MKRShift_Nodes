import importlib
import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.mask_nodes import x1MaskGen  # noqa: E402
from MKRShift_Nodes.nodes.presave_media_nodes import MKRPresaveVideo  # noqa: E402
from MKRShift_Nodes.nodes.social_nodes import MKRshiftSocialPackBuilder  # noqa: E402
from MKRShift_Nodes.nodes.studio_nodes import MKRStudioContactSheet, MKRStudioReviewFrame, MKRStudioSlate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
