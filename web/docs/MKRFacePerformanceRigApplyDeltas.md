# MKRFacePerformanceRigApplyDeltas

Applies jaw, lip, and blink deltas onto a neutral face rig to produce retargeted landmark frames.

## Inputs

- `neutral_rig_json`: JSON object from `MKRFacePerformanceRigBuildNeutral` or compatible data.
- `motion_frames_json`: JSON array of motion frames. Typical fields are `jaw_open`, `lip_open`, `lip_wide`, `blink_l`, `blink_r`, `intensity`, and `smoothing`.
- `settings_json`: Optional advanced overrides for any `FaceRigRetargetConfig` field.

## Outputs

- `retargeted_frames_json`: JSON array of landmark frames with `landmarks`, `landmarks_2d`, and the resolved motion payload.
- `summary`: Short execution summary.

## Notes

- This node preserves the rig's identity geometry and layers motion on top of it.
- Per-frame `smoothing` values override the config default when present.
