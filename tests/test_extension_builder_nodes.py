import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.extension_builder_nodes import MKRNodeExtensionBuilderPlan  # noqa: E402


class ExtensionBuilderNodeTests(unittest.TestCase):
    def test_builder_plan_generates_manifest_and_command(self) -> None:
        node = MKRNodeExtensionBuilderPlan()
        manifest_text, command, summary_text = node.build(
            extension_name="MKRShift Utility Pack",
            publisher="MKR Shift",
            version="1.2.3",
            entry_file="nodes/__init__.py",
            node_list_json='["x1SharpenPro", "x1HeatHaze", "x1HeatHaze"]',
            advanced_options_json=json.dumps(
                {
                    "repository": "https://github.com/criskb/MKRShift_Nodes",
                    "tags": ["comfyui", "lookdev"],
                    "web_directory": "web",
                }
            ),
        )

        manifest = json.loads(manifest_text)
        summary = json.loads(summary_text)

        self.assertEqual(manifest["package"], "mkr-shift.mkrshift-utility-pack")
        self.assertEqual(manifest["nodes"], ["x1SharpenPro", "x1HeatHaze"])
        self.assertIn("install-skill-from-github.py", command)
        self.assertEqual(summary["node_count"], 2)
        self.assertEqual(summary["warnings"], [])

    def test_builder_plan_emits_warning_on_bad_json(self) -> None:
        node = MKRNodeExtensionBuilderPlan()
        manifest_text, _, summary_text = node.build(
            extension_name="",
            publisher="",
            version="",
            entry_file="",
            node_list_json="{bad}",
            advanced_options_json="[]",
        )

        manifest = json.loads(manifest_text)
        summary = json.loads(summary_text)

        self.assertEqual(manifest["name"], "MKRShift Nodes")
        self.assertEqual(manifest["nodes"], [])
        self.assertIn("node_list_json is not valid JSON", summary["warnings"])
        self.assertIn("advanced_options_json must be a JSON object", summary["warnings"])

    def test_builder_plan_supports_object_node_entries_and_semver_guard(self) -> None:
        node = MKRNodeExtensionBuilderPlan()
        manifest_text, _, summary_text = node.build(
            extension_name="Pack",
            publisher="pub",
            version="version-one",
            entry_file="entry.txt",
            node_list_json=json.dumps(
                [
                    {"name": "x1SharpenPro", "enabled": True},
                    {"name": "x1HeatHaze", "enabled": False},
                    {"name": ""},
                ]
            ),
            advanced_options_json=json.dumps({"skill_url": "https://github.com/criskb/comfyui-node-extension-builder"}),
        )
        manifest = json.loads(manifest_text)
        summary = json.loads(summary_text)

        self.assertEqual(manifest["nodes"], ["x1SharpenPro"])
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertTrue(summary["skill_requested"])
        self.assertIn("version did not match semver", " ".join(summary["warnings"]))
        self.assertIn("entry_file should usually point to a Python file", summary["warnings"])

    def test_builder_plan_allows_custom_builder_command(self) -> None:
        node = MKRNodeExtensionBuilderPlan()
        _, command, summary_text = node.build(
            extension_name="Pack",
            publisher="pub",
            version="1.0.0",
            entry_file="__init__.py",
            node_list_json='["x1SharpenPro"]',
            advanced_options_json=json.dumps({"builder_cli_command": "custom-builder --config extension.builder.json"}),
        )
        summary = json.loads(summary_text)
        self.assertEqual(command, "custom-builder --config extension.builder.json")
        self.assertIn("next_step", summary)


if __name__ == "__main__":
    unittest.main()
