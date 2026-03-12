# MKRFacePerformanceEyeMotion

Synthesizes blink, gaze, and lightweight facial expression motion from an audio-feature frame stream.

## Inputs

- `audio_frames_json`: JSON array of per-frame audio features such as `articulation`, `energy`, `pitch_slope`, `pause`, `prosody_valley`, `phrase_boundary`, and `smile`.
- `seed`: Random seed for deterministic blink and gaze generation. Use `-1` for non-deterministic output.
- `target_fps`: Frame rate used for blink timing and gaze drift.
- `mean_blink_interval_s`: Average time between blinks.
- `blink_interval_jitter_s`: Random variation around the blink interval.
- `include_squint`: Adds a `squint` channel to each frame.
- `settings_json`: Optional advanced overrides for any `EyeMotionSynthConfig` field.

## Outputs

- `eye_frames_json`: JSON array with `blink_l`, `blink_r`, `gaze_yaw`, `gaze_pitch`, brow motion, eyelid openness, cheek raise, and `expr_confidence`.
- `summary`: Short execution summary.

## Notes

- Use this before `MKRFacePerformanceLipRefine` when you want eye motion to inform ROI stabilization.
- The output frame count matches the input frame count.
