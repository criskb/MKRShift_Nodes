# MKRBlenderReturnPlan

`MKRBlenderReturnPlan` builds a small JSON contract for sending generated outputs back into Blender later.

## Inputs

- `generated_asset_path`: Path to the rendered image, sequence, or video.
- `asset_kind`: What kind of asset Blender should expect.
- `apply_mode`: Suggested import target, such as image plane, camera background, compositor image, or texture image.
- `target_name`: Friendly name for the imported result inside Blender.
- `colorspace`: Suggested colorspace for the Blender-side import.
- `scene_packet_json`: Optional original scene packet to preserve scene/frame context.
- `notes`: Optional roundtrip notes.

## Outputs

- `return_plan_json`: Full return-plan payload.
- `manifest_line`: Compact CSV-style summary line.
- `summary_json`: Quick metadata summary.

## Notes

- This node does not import anything into Blender by itself yet.
- It gives the bridge add-on a clean return contract for the next roundtrip pass.
