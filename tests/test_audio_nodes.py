import json
import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.nodes.media_batch_transform_nodes import (  # noqa: E402
    MKRAudioGainPan,
    MKRAudioLimiter,
    MKRAudioTempoPitch,
)
from MKRShift_Nodes.nodes.media_batch_video_nodes import MKRLoadAudioMetadata  # noqa: E402
from MKRShift_Nodes.nodes.media_batch_watermark_audio_nodes import (  # noqa: E402
    MKRAudioEQ3Band,
    MKRAudioBitcrush,
    MKRAudioChannelRouter,
    MKRAudioPadTrimDuration,
    MKRAudioStereoWidth,
)
from MKRShift_Nodes.nodes.media_extra_nodes import MKRAudioConcat, MKRAudioMix  # noqa: E402


def _audio_payload(waveform: np.ndarray, sample_rate: int) -> dict:
    return {
        "kind": "audio",
        "waveform": waveform.astype(np.float32, copy=False),
        "sample_rate": int(sample_rate),
    }


class AudioNodeTests(unittest.TestCase):
    def test_load_audio_metadata_reads_waveform_payload(self) -> None:
        stereo = np.zeros((2, 160), dtype=np.float32)
        stereo[0, 10] = 0.5
        stereo[1, 20] = -0.5

        payload, sample_rate, channels, duration, metadata_json = MKRLoadAudioMetadata().run(audio=_audio_payload(stereo, 160))
        metadata = json.loads(metadata_json)

        self.assertEqual(payload["kind"], "audio")
        self.assertEqual(sample_rate, 160)
        self.assertEqual(channels, 2)
        self.assertAlmostEqual(duration, 1.0, places=5)
        self.assertEqual(metadata["sample_rate"], 160)
        self.assertEqual(metadata["channels"], 2)

    def test_audio_mix_supports_secondary_offset(self) -> None:
        sr = 100
        a = np.zeros((1, sr), dtype=np.float32)
        b = np.zeros((1, sr), dtype=np.float32)
        a[0, 0] = 1.0
        b[0, 0] = 1.0

        payload, _, duration, summary_json = MKRAudioMix().run(
            audio_a=_audio_payload(a, sr),
            audio_b=_audio_payload(b, sr),
            gain_a_db=0.0,
            gain_b_db=0.0,
            offset_b_ms=250,
            normalize_peak=False,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="mix_offset",
        )
        summary = json.loads(summary_json)
        out = payload["waveform"].detach().cpu().numpy()

        self.assertAlmostEqual(duration, 1.25, places=2)
        self.assertEqual(summary["offset_b_ms"], 250)
        self.assertGreater(float(out[0, 0]), 0.9)
        self.assertGreater(float(out[0, 25]), 0.9)

    def test_audio_concat_stacks_waveforms_in_order(self) -> None:
        sr = 80
        a = np.ones((1, sr), dtype=np.float32) * 0.25
        b = np.ones((1, sr), dtype=np.float32) * -0.25

        payload, _, duration, summary_json = MKRAudioConcat().run(
            audio_a=_audio_payload(a, sr),
            audio_b=_audio_payload(b, sr),
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="concat_wave",
            stream_copy_if_possible=False,
        )
        summary = json.loads(summary_json)
        out = payload["waveform"].detach().cpu().numpy()

        self.assertAlmostEqual(duration, 2.0, places=3)
        self.assertEqual(summary["source_count"], 2)
        self.assertAlmostEqual(float(out[0, 0]), 0.25, places=4)
        self.assertAlmostEqual(float(out[0, sr]), -0.25, places=4)

    def test_audio_gain_pan_can_force_stereo_and_pan_right(self) -> None:
        sr = 160
        mono = np.ones((1, sr), dtype=np.float32) * 0.25

        payload, _, _, _ = MKRAudioGainPan().run(
            audio=_audio_payload(mono, sr),
            gain_db=0.0,
            pan=0.75,
            force_stereo=True,
            normalize_peak=False,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="gain_pan",
        )
        out = payload["waveform"].detach().cpu().numpy()

        self.assertEqual(out.shape[0], 2)
        self.assertGreater(float(np.mean(np.abs(out[1]))), float(np.mean(np.abs(out[0]))))

    def test_audio_limiter_reduces_hot_signal_peak(self) -> None:
        sr = 200
        x = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
        hot = (np.sin(2.0 * np.pi * 6.0 * x) * 1.4).astype(np.float32)[None, :]

        payload, _, _, _ = MKRAudioLimiter().run(
            audio=_audio_payload(hot, sr),
            threshold_db=-6.0,
            ceiling_db=-10.0,
            release_ms=10.0,
            makeup_db=0.0,
            soft_clip=False,
            normalize_peak=False,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="limiter",
        )
        out = payload["waveform"].detach().cpu().numpy()

        self.assertLessEqual(float(np.max(np.abs(out))), 0.55)

    def test_audio_eq3band_supports_output_gain_and_peak_normalize(self) -> None:
        sr = 160
        x = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
        stereo = np.stack(
            [
                np.sin(2.0 * np.pi * 4.0 * x).astype(np.float32),
                np.sin(2.0 * np.pi * 12.0 * x).astype(np.float32),
            ],
            axis=0,
        )

        payload, _, _, summary_json = MKRAudioEQ3Band().run(
            audio=_audio_payload(stereo, sr),
            low_gain_db=6.0,
            mid_gain_db=0.0,
            high_gain_db=-6.0,
            output_gain_db=3.0,
            low_mid_hz=6.0,
            mid_high_hz=18.0,
            normalize_peak=True,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="eq3band",
        )
        summary = json.loads(summary_json)
        out = payload["waveform"].detach().cpu().numpy()

        self.assertTrue(summary["normalize_peak"])
        self.assertEqual(summary["output_gain_db"], 3.0)
        self.assertLessEqual(float(np.max(np.abs(out))), 0.981)

    def test_audio_tempo_pitch_changes_duration(self) -> None:
        sr = 160
        x = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
        mono = np.sin(2.0 * np.pi * 4.0 * x).astype(np.float32)[None, :]

        _, _, duration, _ = MKRAudioTempoPitch().run(
            audio=_audio_payload(mono, sr),
            tempo=2.0,
            pitch_semitones=0.0,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="tempo_pitch",
        )

        self.assertAlmostEqual(duration, 0.5, places=2)

    def test_audio_stereo_width_zero_collapses_to_mid(self) -> None:
        sr = 160
        x = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
        stereo = np.stack(
            [
                np.sin(2.0 * np.pi * 3.0 * x).astype(np.float32),
                np.cos(2.0 * np.pi * 3.0 * x).astype(np.float32),
            ],
            axis=0,
        )

        payload, _, _, _ = MKRAudioStereoWidth().run(
            audio=_audio_payload(stereo, sr),
            width=0.0,
            normalize_peak=False,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="stereo_width",
        )
        out = payload["waveform"].detach().cpu().numpy()

        self.assertLess(float(np.max(np.abs(out[0] - out[1]))), 1e-5)

    def test_audio_pad_trim_duration_supports_loop_padding_and_center_trim(self) -> None:
        sr = 4
        short = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)

        padded_payload, _, padded_duration, padded_summary_json = MKRAudioPadTrimDuration().run(
            audio=_audio_payload(short, sr),
            target_duration_sec=2.0,
            pad_position="end",
            pad_mode="loop",
            trim_anchor="end",
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="pad_loop",
        )
        padded = padded_payload["waveform"].detach().cpu().numpy()
        padded_summary = json.loads(padded_summary_json)

        self.assertAlmostEqual(padded_duration, 2.0, places=5)
        self.assertEqual(padded_summary["pad_mode"], "loop")
        self.assertTrue(np.allclose(padded[0], np.asarray([0.1, 0.2, 0.3, 0.4, 0.1, 0.2, 0.3, 0.4], dtype=np.float32)))

        long = np.asarray([[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]], dtype=np.float32)
        trimmed_payload, _, trimmed_duration, trimmed_summary_json = MKRAudioPadTrimDuration().run(
            audio=_audio_payload(long, sr),
            target_duration_sec=1.0,
            pad_position="end",
            pad_mode="silence",
            trim_anchor="center",
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="trim_center",
        )
        trimmed = trimmed_payload["waveform"].detach().cpu().numpy()
        trimmed_summary = json.loads(trimmed_summary_json)

        self.assertAlmostEqual(trimmed_duration, 1.0, places=5)
        self.assertEqual(trimmed_summary["trim_anchor"], "center")
        self.assertTrue(np.allclose(trimmed[0], np.asarray([0.2, 0.3, 0.4, 0.5], dtype=np.float32)))

    def test_audio_channel_router_and_bitcrush_transform_waveform(self) -> None:
        sr = 128
        stereo = np.stack(
            [
                np.linspace(-1.0, 1.0, sr, dtype=np.float32),
                np.linspace(1.0, -1.0, sr, dtype=np.float32),
            ],
            axis=0,
        )

        routed_payload, _, _, _ = MKRAudioChannelRouter().run(
            audio=_audio_payload(stereo, sr),
            mode="mono_mix",
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="router",
        )
        routed = routed_payload["waveform"].detach().cpu().numpy()
        self.assertEqual(routed.shape[0], 1)
        self.assertLess(float(np.max(np.abs(routed))), 1e-5)

        ms_encoded_payload, _, _, _ = MKRAudioChannelRouter().run(
            audio=_audio_payload(stereo, sr),
            mode="mid_side_encode",
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="router_ms_encode",
        )
        ms_encoded = ms_encoded_payload["waveform"].detach().cpu().numpy()

        ms_decoded_payload, _, _, _ = MKRAudioChannelRouter().run(
            audio=_audio_payload(ms_encoded, sr),
            mode="mid_side_decode",
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="router_ms_decode",
        )
        ms_decoded = ms_decoded_payload["waveform"].detach().cpu().numpy()
        self.assertLess(float(np.max(np.abs(ms_decoded - stereo))), 1e-5)

        mono = np.asarray([np.linspace(-1.0, 1.0, sr, dtype=np.float32)], dtype=np.float32)
        crushed_payload, _, _, _ = MKRAudioBitcrush().run(
            audio=_audio_payload(mono, sr),
            bit_depth=4,
            sample_hold=8,
            mix=1.0,
            output_format="wav",
            subfolder=".temp/audio_tests",
            overwrite=True,
            filename_label="bitcrush",
        )
        crushed = crushed_payload["waveform"].detach().cpu().numpy()
        unique_levels = np.unique(np.round(crushed[0], 4))
        self.assertLessEqual(len(unique_levels), 16)


if __name__ == "__main__":
    unittest.main()
