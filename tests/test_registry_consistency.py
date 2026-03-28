import sys
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

import MKRShift_Nodes as pack  # noqa: E402


class RegistryConsistencyTests(unittest.TestCase):
    def test_registry_does_not_register_same_class_twice(self) -> None:
        counts = Counter(pack.NODE_CLASS_MAPPINGS.values())
        duplicates = {cls.__name__: count for cls, count in counts.items() if count > 1}
        self.assertEqual(duplicates, {})

    def test_display_names_are_unique(self) -> None:
        counts = Counter(pack.NODE_DISPLAY_NAME_MAPPINGS.values())
        duplicates = {name: count for name, count in counts.items() if count > 1}
        self.assertEqual(duplicates, {})


if __name__ == "__main__":
    unittest.main()
