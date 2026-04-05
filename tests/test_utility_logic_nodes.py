import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.utility_logic_nodes import MKRToggleSwitch  # noqa: E402


class UtilityLogicNodeTests(unittest.TestCase):
    def test_toggle_switch_defaults_to_enabled(self) -> None:
        node = MKRToggleSwitch()
        result = node.run()
        self.assertTrue(result["result"][0])
        self.assertTrue(result["ui"]["toggle_state"][0]["enabled"])
        self.assertEqual(result["ui"]["toggle_state"][0]["theme"], "lime")

    def test_toggle_switch_respects_saved_settings(self) -> None:
        node = MKRToggleSwitch()
        result = node.run(settings_json='{"enabled": false, "theme": "rose"}')
        self.assertFalse(result["result"][0])
        self.assertEqual(result["ui"]["toggle_state"][0]["theme"], "rose")

    def test_toggle_switch_input_overrides_saved_state(self) -> None:
        node = MKRToggleSwitch()
        result = node.run(settings_json='{"enabled": false, "theme": "amber"}', state_in=True)
        self.assertTrue(result["result"][0])
        self.assertTrue(result["ui"]["toggle_state"][0]["controlled_by_input"])
        self.assertEqual(result["ui"]["toggle_state"][0]["theme"], "amber")

    def test_toggle_switch_falls_back_to_default_theme(self) -> None:
        node = MKRToggleSwitch()
        result = node.run(settings_json='{"enabled": true, "theme": "ultraviolet"}')
        self.assertTrue(result["result"][0])
        self.assertEqual(result["ui"]["toggle_state"][0]["theme"], "lime")


if __name__ == "__main__":
    unittest.main()
