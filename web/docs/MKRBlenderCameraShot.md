# MKRBlenderCameraShot

`MKRBlenderCameraShot` turns imported Blender camera data into a reusable shot recipe and prompt fragment.

## Inputs

- `camera_json`: Camera payload from `MKRBlenderSceneImport`.
- `subject_name`: Optional subject label.
- `intent_hint`: Optional creative note like `hero portrait`, `over-shoulder`, or `establishing frame`.

## Outputs

- `camera_prompt`: Compact camera-match text.
- `shot_recipe_json`: Normalized camera metadata with lens bucket, framing ratio, transform, and prompt.
- `summary_json`: Short metadata summary.

## Notes

- This node is useful when you want Blender-authored framing but still want prompt-friendly camera language downstream.
