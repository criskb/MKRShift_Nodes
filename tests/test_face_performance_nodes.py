import json
import math
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

import MKRShift_Nodes as pack  # noqa: E402
from MKRShift_Nodes.nodes.face_performance_nodes import (  # noqa: E402
    MKRFacePerformanceEvaluate,
    MKRFacePerformanceEyeMotion,
    MKRFacePerformanceLipRefine,
    MKRFacePerformancePoseMerge,
    MKRFacePerformanceRigApplyDeltas,
    MKRFacePerformanceRigBuildNeutral,
)


FPS = 60


def _generate_audio_clip(frame_count: int, phase: float) -> list[dict[str, float | int]]:
    frames: list[dict[str, float | int]] = []
    for index in range(frame_count):
        t = index / FPS
        articulation = 0.45 + 0.3 * math.sin(2.0 * math.pi * 1.9 * t + phase)
        articulation += 0.08 * math.sin(2.0 * math.pi * 5.1 * t + 0.3 * phase)
        articulation = max(0.0, min(1.0, articulation))

        energy = 0.4 + 0.35 * (0.5 + 0.5 * math.sin(2.0 * math.pi * 0.6 * t + phase * 0.7))
        pitch_slope = math.sin(2.0 * math.pi * 0.8 * t + 0.5 * phase)
        pause = 0.35 if (index % 150) > 140 else 0.05
        prosody_valley = -0.45 if (index % 170) > 164 else -0.1
        phrase_boundary = 1.0 if pause > 0.25 or prosody_valley < -0.35 else 0.0

        frames.append(
            {
                "frame_index": index,
                "articulation": articulation,
                "energy": energy,
                "pitch_slope": pitch_slope,
                "pause": pause,
                "prosody_valley": prosody_valley,
                "phrase_boundary": phrase_boundary,
                "plosive": max(0.0, min(1.0, 0.3 + 0.5 * math.sin(2 * math.pi * 1.2 * t + phase))),
                "smile": max(0.0, min(1.0, 0.3 + 0.25 * math.sin(2 * math.pi * 0.35 * t + 0.2))),
            }
        )
    return frames


def _build_sample_clip(phase: float, seed: int) -> tuple[list[dict[str, float | int]], list[dict], list[dict], list[dict]]:
    audio = _generate_audio_clip(frame_count=420, phase=phase)
    eye_node = MKRFacePerformanceEyeMotion()
    eye_json, _ = eye_node.run(
        audio_frames_json=json.dumps(audio),
        seed=seed,
        target_fps=FPS,
        mean_blink_interval_s=4.2,
        blink_interval_jitter_s=1.6,
        include_squint=False,
    )
    eye = json.loads(eye_json)

    base = []
    lag_frames = 2
    for index, frame in enumerate(audio):
        lag_source = audio[max(0, index - lag_frames)]
        eye_frame = eye[index]
        articulation = float(lag_source["articulation"])
        base.append(
            {
                "frame_index": index,
                "jaw_open": max(0.0, min(1.0, 0.1 + 0.85 * articulation)),
                "mouth_press": max(0.0, 0.45 - 0.4 * articulation),
                "blink_l": eye_frame["blink_l"],
                "blink_r": eye_frame["blink_r"],
                "gaze_yaw": eye_frame["gaze_yaw"],
                "gaze_pitch": eye_frame["gaze_pitch"],
            }
        )

    refine_node = MKRFacePerformanceLipRefine()
    refined_json, _ = refine_node.run(
        base_frames_json=json.dumps(base),
        audio_frames_json=json.dumps(audio),
        mode="quality",
    )
    refined = json.loads(refined_json)

    body = []
    face = []
    facial = []
    for index, eye_frame in enumerate(eye):
        t = index / FPS
        body.append(
            {
                "frame_index": index,
                "confidence": 0.9,
                "head_yaw": 0.15 * math.sin(2 * math.pi * 0.5 * t + phase),
                "head_pitch": 0.12 * math.sin(2 * math.pi * 0.42 * t + phase),
                "head_roll": 0.08 * math.sin(2 * math.pi * 0.36 * t + phase),
                "neck_yaw": 0.1 * math.sin(2 * math.pi * 0.4 * t),
                "neck_pitch": 0.07 * math.sin(2 * math.pi * 0.44 * t),
                "neck_roll": 0.06 * math.sin(2 * math.pi * 0.31 * t),
            }
        )
        face.append({"frame_index": index, "confidence": 0.7})
        facial.append(
            {
                "frame_index": index,
                "expr_confidence": eye_frame["expr_confidence"],
                "jaw_open": refined[index]["refined_jaw_open"],
                "blink_l": eye_frame["blink_l"],
                "blink_r": eye_frame["blink_r"],
                "eyelid_open_l": eye_frame["eyelid_open_l"],
                "eyelid_open_r": eye_frame["eyelid_open_r"],
                "brow_inner_up": eye_frame["brow_inner_up"],
                "brow_outer_up_l": eye_frame["brow_outer_up_l"],
                "brow_outer_up_r": eye_frame["brow_outer_up_r"],
            }
        )

    combine_node = MKRFacePerformancePoseMerge()
    pose_json, diagnostics_json, _ = combine_node.run(
        body_frames_json=json.dumps(body),
        face_frames_json=json.dumps(face),
        facial_frames_json=json.dumps(facial),
    )
    pose = json.loads(pose_json)
    _ = json.loads(diagnostics_json)
    return audio, eye, refined, pose


class FacePerformanceNodeTests(unittest.TestCase):
    def test_face_performance_nodes_are_registered(self) -> None:
        expected = {
            "MKRFacePerformanceEyeMotion",
            "MKRFacePerformanceLipRefine",
            "MKRFacePerformanceRigBuildNeutral",
            "MKRFacePerformanceRigApplyDeltas",
            "MKRFacePerformancePoseMerge",
            "MKRFacePerformanceEvaluate",
        }
        self.assertTrue(expected.issubset(set(pack.NODE_CLASS_MAPPINGS)))

    def test_eye_motion_and_lip_refine_outputs_align(self) -> None:
        audio = [{"frame_index": index, "articulation": 0.4, "energy": 0.7, "smile": 0.3} for index in range(60)]
        eye_node = MKRFacePerformanceEyeMotion()
        eye_json, _ = eye_node.run(
            audio_frames_json=json.dumps(audio),
            seed=11,
            target_fps=60,
            mean_blink_interval_s=1.0,
            blink_interval_jitter_s=0.1,
            include_squint=True,
        )
        eye = json.loads(eye_json)
        self.assertEqual(len(eye), len(audio))
        self.assertTrue(all("squint" in frame for frame in eye))

        base = [
            {
                "frame_index": index,
                "jaw_open": 0.3 + 0.4 * ((index % 8) / 7.0),
                "blink_l": eye[index]["blink_l"],
                "blink_r": eye[index]["blink_r"],
                "gaze_yaw": eye[index]["gaze_yaw"],
                "gaze_pitch": eye[index]["gaze_pitch"],
            }
            for index in range(len(audio))
        ]
        refine_node = MKRFacePerformanceLipRefine()
        realtime_json, _ = refine_node.run(
            base_frames_json=json.dumps(base),
            audio_frames_json=json.dumps(audio),
            mode="realtime",
        )
        quality_json, _ = refine_node.run(
            base_frames_json=json.dumps(base),
            audio_frames_json=json.dumps(audio),
            mode="quality",
        )
        realtime = json.loads(realtime_json)
        quality = json.loads(quality_json)
        self.assertEqual(len(quality), len(base))
        self.assertGreater(quality[0]["composite_mask_feather_px"], realtime[0]["composite_mask_feather_px"])

    def test_face_rig_nodes_roundtrip_reference_and_motion(self) -> None:
        build_node = MKRFacePerformanceRigBuildNeutral()
        neutral_json, _ = build_node.build(
            reference_landmarks_json='{"left_eye": [192, 216], "right_eye": [448, 216]}',
            image_width=640,
            image_height=1080,
        )
        neutral = json.loads(neutral_json)
        self.assertEqual(neutral["identity_mode"], "reference")
        self.assertAlmostEqual(neutral["landmarks"]["left_eye"][0], 0.3, places=6)

        apply_node = MKRFacePerformanceRigApplyDeltas()
        frames_json, _ = apply_node.retarget(
            neutral_rig_json=neutral_json,
            motion_frames_json=json.dumps(
                [
                    {"frame_index": 0, "jaw_open": 0.0},
                    {"frame_index": 1, "jaw_open": 1.0, "smoothing": 0.8},
                ]
            ),
        )
        frames = json.loads(frames_json)
        self.assertEqual(len(frames), 2)
        self.assertIn("landmarks_2d", frames[0])
        self.assertLess(frames[1]["motion"]["jaw_open"], 0.5)

    def test_pose_merge_emits_diagnostics(self) -> None:
        node = MKRFacePerformancePoseMerge()
        pose_json, diagnostics_json, _ = node.run(
            body_frames_json='[{"frame_index": 0, "head_pitch": 0.0, "head_yaw": 0.2, "confidence": 1.0}]',
            face_frames_json='[{"frame_index": 0, "head_pitch": 1.0, "head_yaw_offset": 1.0, "head_pitch_offset": 0.3, "confidence": 1.0}]',
            facial_frames_json='[{"frame_index": 0, "jaw_open": 0.4, "expr_confidence": 0.8}]',
            max_delta_per_frame=0.22,
            divergence_threshold=0.2,
        )
        pose = json.loads(pose_json)
        diagnostics = json.loads(diagnostics_json)
        self.assertAlmostEqual(pose[0]["head_yaw"], 0.55, places=6)
        self.assertAlmostEqual(pose[0]["jaw_open"], 0.4, places=6)
        self.assertTrue(any(item["type"] == "body_face_divergence" for item in diagnostics))
        self.assertTrue(any(item["type"] == "head_offset_divergence" for item in diagnostics))

    def test_evaluate_clip_matches_regression_defaults(self) -> None:
        audio, eye, refined, pose = _build_sample_clip(phase=0.2, seed=11)
        node = MKRFacePerformanceEvaluate()
        metrics_json, failures_json, lag_frames, blink_rate, pose_jitter, _ = node.run(
            clip_id="clip_alpha",
            audio_frames_json=json.dumps(audio),
            refined_frames_json=json.dumps(refined),
            eye_frames_json=json.dumps(eye),
            pose_frames_json=json.dumps(pose),
            fps=FPS,
            thresholds_json="{}",
        )
        metrics = json.loads(metrics_json)
        failures = json.loads(failures_json)

        self.assertEqual(metrics["clip_id"], "clip_alpha")
        self.assertEqual(failures, [])
        self.assertEqual(lag_frames, 2)
        self.assertGreater(blink_rate, 6.0)
        self.assertLess(pose_jitter, 0.055)


if __name__ == "__main__":
    unittest.main()
