import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.lib.image_shared import gaussian_blur_rgb_np, resize_rgb_np  # noqa: E402


class ImageSharedTests(unittest.TestCase):
    def test_resize_rgb_preserves_low_energy_signal(self) -> None:
        src = np.zeros((33, 65, 3), dtype=np.float32)
        src[16, 32] = 1.0

        reduced = resize_rgb_np(src, 8, 65)
        self.assertGreater(float(reduced.max()), 0.01)

        blurred = gaussian_blur_rgb_np(reduced, radius=2.2)
        restored = resize_rgb_np(blurred, 33, 65)

        self.assertGreater(float(restored.max()), 1e-4)
        self.assertGreater(float(restored[..., 0].sum()), 0.01)


if __name__ == "__main__":
    unittest.main()
