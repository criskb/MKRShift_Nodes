import sys
import unittest
from pathlib import Path

import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.xplay import x1AuraFlow, x1Kaleido  # noqa: E402
from MKRShift_Nodes.nodes.xprocess import x1Film, x1Focus  # noqa: E402


class PlayProcessNodeTests(unittest.TestCase):
    def test_kaleido_redistributes_off_center_source_detail(self) -> None:
        image = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        image[0, 12:20, 42:50] = 1.0

        out, mask, info = x1Kaleido().run(
            image=image,
            segments=7,
            spin=0.0,
            source_spread=0.8,
            source_orbit=0.2,
            prism_split=0.1,
            edge_fade=0.0,
            mix=1.0,
        )

        mean_diff = float(torch.mean(torch.abs(out - image)).item())
        self.assertGreater(mean_diff, 0.01)
        self.assertEqual(tuple(mask.shape), (1, 64, 64))
        self.assertIn("source_spread=0.80", info)

    def test_aura_flow_screens_generated_aura_over_input_image(self) -> None:
        base = torch.full((1, 48, 48, 3), 0.15, dtype=torch.float32)

        out, mask, info = x1AuraFlow().run(
            image=base,
            palette="cyber",
            intensity=1.0,
            contrast=1.2,
            noise_scale=48.0,
            swirl=1.5,
            sparkle=0.4,
            glow=0.4,
            drift=0.2,
            composite_mode="screen",
            mix=0.8,
        )

        mean_diff = float(torch.mean(torch.abs(out - base)).item())
        self.assertGreater(mean_diff, 0.2)
        self.assertEqual(tuple(mask.shape), (1, 48, 48))
        self.assertIn("mode=screen", info)

    def test_film_node_adds_chromatic_grain(self) -> None:
        base = torch.full((1, 48, 48, 3), 0.5, dtype=torch.float32)

        out, mask, info = x1Film().run(
            image=base,
            film_grain_strength=0.8,
            film_grain_size=12.0,
            film_grain_seed=7,
            film_grain_chroma=1.0,
            vignette_strength=0.2,
        )

        mean_diff = float(torch.mean(torch.abs(out - base)).item())
        rg_delta = float(torch.mean(torch.abs(out[..., 0] - out[..., 1])).item())
        self.assertGreater(mean_diff, 0.04)
        self.assertGreater(rg_delta, 0.002)
        self.assertEqual(tuple(mask.shape), (1, 48, 48))
        self.assertIn("x1Film", info)

    def test_focus_node_blurs_hard_edges(self) -> None:
        base = torch.zeros((1, 48, 48, 3), dtype=torch.float32)
        base[:, 16:32, 16:32, :] = 1.0

        out, mask, info = x1Focus().run(
            image=base,
            blur_radius=4.0,
            sharpen=0.0,
        )

        mean_diff = float(torch.mean(torch.abs(out - base)).item())
        self.assertGreater(mean_diff, 0.05)
        self.assertEqual(tuple(mask.shape), (1, 48, 48))
        self.assertIn("blur=4.0px", info)


if __name__ == "__main__":
    unittest.main()
