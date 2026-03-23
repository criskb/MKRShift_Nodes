# MKRPhotoshopImageOutputPlan

Builds a live image/layer output plan for Photoshop.

Use it to place a generated result into a target layer, smart object, or document handoff path.

## Inputs

- `asset_path`
- `image_role`
- `target_name`
- `apply_mode`
- `blend_mode` (optional)
- `target_document_name` (optional)
- `transport_plan_json` (optional)

## Outputs

- `image_output_plan_json`
- `manifest_line`
- `summary_json`
