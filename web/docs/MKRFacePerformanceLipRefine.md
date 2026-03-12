# MKRFacePerformanceLipRefine

Refines mouth contact, ROI placement, and composite guidance from base facial motion plus audio features.

## Inputs

- `base_frames_json`: JSON array of base face frames. Common fields are `jaw_open`, `blink_l`, `blink_r`, `gaze_yaw`, `gaze_pitch`, and optional mouth pressure values.
- `audio_frames_json`: JSON array of audio frames aligned to the same frame indices.
- `mode`: `quality` for steadier finishing output or `realtime` for more responsive behavior.
- `settings_json`: Optional advanced overrides for any `LipRefineFaceConfig` field.

## Outputs

- `refined_frames_json`: JSON array with refined jaw openness, lip contact, teeth visibility, pupil targets, and composite guidance.
- `summary`: Short execution summary.

## Notes

- This node is intended for structured motion data, not raw images.
- `quality` mode uses a larger composite feather than `realtime`.
