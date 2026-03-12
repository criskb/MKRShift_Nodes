# MKRFacePerformanceEvaluate

Evaluates a generated facial-motion clip for sync lag, blink behavior, landmark smoothness, and pose jitter.

## Inputs

- `clip_id`: Identifier stored in the metrics payload.
- `audio_frames_json`: JSON array of source audio features.
- `refined_frames_json`: JSON array from `MKRFacePerformanceLipRefine` or compatible data.
- `eye_frames_json`: JSON array from `MKRFacePerformanceEyeMotion`.
- `pose_frames_json`: JSON array from `MKRFacePerformancePoseMerge`.
- `fps`: Frame rate used for timing-based metrics.
- `thresholds_json`: Optional advanced overrides for any `RegressionThresholds` field.

## Outputs

- `metrics_json`: JSON object with sync, blink, motion-outlier, and pose-jitter metrics.
- `failures_json`: JSON array of threshold violations.
- `lag_frames`: Best lip/audio lag estimate in frames.
- `blink_rate_per_minute`: Estimated blink rate.
- `pose_jitter_score`: Mean per-frame pose delta across head and neck channels.
- `summary`: Short execution summary.

## Notes

- Leave `thresholds_json` as `{}` to use the built-in defaults.
- This node is useful for regression testing or comparing different retarget settings inside a workflow.
