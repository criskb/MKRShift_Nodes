import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.material_pack_nodes import x1PBRPack  # noqa: E402


class MaterialPackNodeTests(unittest.TestCase):
    def test_pbr_pack_supports_gloss_input_and_alpha_output(self) -> None:
        gloss = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
        gloss[:, :, :8, :] = 0.9
        gloss[:, :, 8:, :] = 0.2

        metal_mask = torch.zeros((1, 16, 16), dtype=torch.float32)
        metal_mask[:, 4:12, 4:12] = 1.0

        alpha_mask = torch.zeros((1, 16, 16), dtype=torch.float32)
        alpha_mask[:, :, 8:] = 1.0

        node = x1PBRPack()
        packed, info = node.run(
            layout="orma",
            roughness_source="glossiness",
            fill_ao=0.85,
            fill_roughness=1.0,
            fill_metalness=0.0,
            fill_alpha=1.0,
            roughness_image=gloss,
            metalness_mask=metal_mask,
            alpha_mask=alpha_mask,
        )

        self.assertEqual(tuple(packed.shape), (1, 16, 16, 4))
        self.assertAlmostEqual(float(packed[0, 8, 2, 0].item()), 0.85, places=4)
        self.assertLess(float(packed[0, 8, 2, 1].item()), 0.2)
        self.assertGreater(float(packed[0, 8, 12, 1].item()), 0.7)
        self.assertGreater(float(packed[0, 8, 8, 2].item()), 0.9)
        self.assertLess(float(packed[0, 8, 2, 2].item()), 0.1)
        self.assertLess(float(packed[0, 8, 2, 3].item()), 0.1)
        self.assertGreater(float(packed[0, 8, 12, 3].item()), 0.9)
        self.assertIn("x1PBRPack", info)
        self.assertIn("gloss->roughness", info)


if __name__ == "__main__":
    unittest.main()
