import json
import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.social_pack import MKRshiftSocialPackBuilder  # noqa: E402
from MKRShift_Nodes.xmask import x1MaskGen  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
