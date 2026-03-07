import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

import MKRShift_Nodes as pack  # noqa: E402


class NodePackSmokeTests(unittest.TestCase):
    def test_registry_and_display_names_stay_in_sync(self) -> None:
        node_keys = set(pack.NODE_CLASS_MAPPINGS)
        display_keys = set(pack.NODE_DISPLAY_NAME_MAPPINGS)

        self.assertGreaterEqual(len(node_keys), 100)
        self.assertEqual(node_keys, display_keys)

    def test_web_directory_exists(self) -> None:
        web_dir = (REPO_ROOT / pack.WEB_DIRECTORY).resolve()
        self.assertTrue(web_dir.is_dir(), f"Missing web directory: {web_dir}")

    def test_nodes_expose_required_comfy_metadata(self) -> None:
        for name, cls in pack.NODE_CLASS_MAPPINGS.items():
            with self.subTest(node=name):
                self.assertTrue(callable(getattr(cls, "INPUT_TYPES", None)))

                input_types = cls.INPUT_TYPES()
                self.assertIsInstance(input_types, dict)
                self.assertTrue(
                    any(section in input_types for section in ("required", "optional", "hidden")),
                    "INPUT_TYPES should expose at least one input section",
                )

                category = getattr(cls, "CATEGORY", "")
                self.assertIsInstance(category, str)
                self.assertTrue(category.strip())

                function_name = getattr(cls, "FUNCTION", "")
                self.assertIsInstance(function_name, str)
                self.assertTrue(function_name.strip())
                self.assertTrue(callable(getattr(cls, function_name, None)))

                return_types = getattr(cls, "RETURN_TYPES", ())
                self.assertIsInstance(return_types, tuple)
                if len(return_types) == 0:
                    self.assertTrue(bool(getattr(cls, "OUTPUT_NODE", False)))
                else:
                    self.assertGreater(len(return_types), 0)

                display_name = pack.NODE_DISPLAY_NAME_MAPPINGS.get(name, "")
                self.assertIsInstance(display_name, str)
                self.assertTrue(display_name.strip())


if __name__ == "__main__":
    unittest.main()
