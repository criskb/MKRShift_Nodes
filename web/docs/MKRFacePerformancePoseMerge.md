# MKRFacePerformancePoseMerge

Merges body pose, face pose, and facial-expression streams into a stabilized pose payload.

## Inputs

- `body_frames_json`: JSON array for body and neck pose.
- `face_frames_json`: JSON array for face pose and optional head offsets.
- `facial_frames_json`: JSON array for lips, eyelids, and brows.
- `max_delta_per_frame`: Maximum allowed per-frame change after smoothing.
- `divergence_threshold`: Threshold for emitting diagnostic warnings when streams disagree.
- `settings_json`: Optional advanced overrides for any `CombinePoseDataConfig` field.

## Outputs

- `pose_frames_json`: JSON array with merged head, neck, lip, eye, and brow channels.
- `diagnostics_json`: JSON array of divergence diagnostics.
- `summary`: Short execution summary.

## Notes

- Facial channels prioritize higher-confidence sources.
- Diagnostics are useful when body and face trackers disagree or when head offsets spike.
