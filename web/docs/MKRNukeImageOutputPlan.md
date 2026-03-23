# MKRNukeImageOutputPlan

Builds a live image handoff plan for Nuke.

Use it to return a generated plate, still, matte, or texture from ComfyUI back into a Nuke bridge panel or read/write automation.

## Inputs

- `asset_path`
- `image_role`
- `target_name`
- `apply_mode`
- `colorspace` (optional)
- `target_script_name` (optional)
- `transport_plan_json` (optional)

## Outputs

- `image_output_plan_json`
- `manifest_line`
- `summary_json`
