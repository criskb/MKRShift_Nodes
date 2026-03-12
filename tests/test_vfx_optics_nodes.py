import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.vfx_optics_nodes import x1LensDirtBloom, x1ShockwaveDistort  # noqa: E402


class VfxOpticsNodeTests(unittest.TestCase):
    def test_lens_dirt_bloom_reacts_to_highlights(self) -> None:
        image = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        image[:, 20:28, 20:28, :] = 1.0

        node = x1LensDirtBloom()
        output, mask, info = node.run(
            image=image,
            threshold=0.5,
            softness=0.05,
            bloom_radius=10.0,
            bloom_strength=1.0,
            dirt_amount=0.8,
            dirt_scale=24.0,
            dirt_contrast=1.4,
            seed=13,
            mix=1.0,
        )

        self.assertGreater(float(torch.mean(torch.abs(output - image)).item()), 0.001)
        self.assertGreater(float(mask.max().item()), 0.05)
        self.assertIn("x1LensDirtBloom", info)

    def test_lens_dirt_bloom_seed_is_deterministic_and_variant(self) -> None:
        image = torch.zeros((1, 40, 40, 3), dtype=torch.float32)
        image[:, 10:30, 10:30, :] = 0.9

        node = x1LensDirtBloom()
        out_a, _, _ = node.run(image=image, seed=21, dirt_amount=0.9, dirt_scale=18.0, bloom_radius=8.0, mix=1.0)
        out_b, _, _ = node.run(image=image, seed=21, dirt_amount=0.9, dirt_scale=18.0, bloom_radius=8.0, mix=1.0)
        out_c, _, _ = node.run(image=image, seed=22, dirt_amount=0.9, dirt_scale=18.0, bloom_radius=8.0, mix=1.0)

        self.assertTrue(torch.allclose(out_a, out_b))
        self.assertGreater(float(torch.mean(torch.abs(out_a - out_c)).item()), 0.0001)

    def test_shockwave_distort_targets_ring_band(self) -> None:
        y = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 64, 1, 1)
        x = torch.linspace(0.0, 1.0, 64, dtype=torch.float32).view(1, 1, 64, 1)
        image = torch.cat((x.repeat(1, 64, 1, 1), y.repeat(1, 1, 64, 1), ((x + y) * 0.5)), dim=-1)

        node = x1ShockwaveDistort()
        output, mask, info = node.run(
            image=image,
            center_x=0.5,
            center_y=0.5,
            radius=0.23,
            width=0.06,
            amplitude_px=12.0,
            ring_hardness=1.8,
            chroma_split_px=1.2,
            mix=1.0,
        )

        self.assertGreater(float(torch.mean(torch.abs(output - image)).item()), 0.001)
        ring_sample = float(mask[0, 32, 46].item())
        center_sample = float(mask[0, 32, 32].item())
        self.assertGreater(ring_sample, center_sample + 0.1)
        self.assertIn("x1ShockwaveDistort", info)

    def test_shockwave_distort_bypasses_at_zero_amplitude(self) -> None:
        image = torch.linspace(0.0, 1.0, 1 * 24 * 24 * 3, dtype=torch.float32).reshape(1, 24, 24, 3)
        node = x1ShockwaveDistort()
        output, mask, info = node.run(image=image, amplitude_px=0.0, mix=1.0)

        self.assertTrue(torch.allclose(output, image))
        self.assertEqual(float(mask.max().item()), 0.0)
        self.assertIn("bypassed", info)


if __name__ == "__main__":
    unittest.main()
