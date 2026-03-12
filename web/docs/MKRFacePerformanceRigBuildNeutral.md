# MKRFacePerformanceRigBuildNeutral

Builds a stable neutral face rig from canonical defaults or sparse reference landmarks.

## Inputs

- `reference_landmarks_json`: JSON object keyed by landmark name. Each value should be a two-item array like `[x, y]`.
- `image_width`: Optional source width for pixel-space landmark normalization.
- `image_height`: Optional source height for pixel-space landmark normalization.
- `settings_json`: Optional advanced overrides for any `FaceRigRetargetConfig` field, including canonical landmark positions.

## Outputs

- `neutral_rig_json`: JSON object containing normalized landmarks, identity mode, landmark order, and reference completeness data.
- `summary`: Short execution summary.

## Notes

- Leave `image_width` and `image_height` at `0` when the reference landmarks are already normalized to `0..1`.
- Sparse references fall back to canonical landmarks for missing points.
