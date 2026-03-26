import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ExtensionBuilderAssetTests(unittest.TestCase):
    def test_extension_builder_config_exists_and_has_required_keys(self) -> None:
        path = REPO_ROOT / "extension.builder.json"
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("schema"), "comfyui_node_extension_builder_v1")
        self.assertTrue(payload.get("package"))
        self.assertTrue(payload.get("entry"))
        self.assertIsInstance(payload.get("nodes"), list)

    def test_example_workflow_for_builder_node_exists(self) -> None:
        path = REPO_ROOT / "example_workflows" / "mkrshift_extension_builder_plan.json"
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding="utf-8"))
        node_types = {node.get("type") for node in payload.get("nodes", []) if isinstance(node, dict)}
        self.assertIn("MKRNodeExtensionBuilderPlan", node_types)


if __name__ == "__main__":
    unittest.main()
