# MKRGCodePreview

Builds a standalone preview image from a G-code plan, raw G-code text/file, a mesh, or a split mesh-plus-plan view.

## Inputs

- `view_mode`: Auto-selects a source or forces plan, mesh, or split rendering.
- `preview_size`: Base preview canvas size.
- `plan` (optional): Existing `MKR_GCODE_PLAN`.
- `mesh` (optional): `MKR_GCODE_MESH` for wireframe preview.
- `profile` (optional): Helps parse raw G-code into a plan.
- `gcode_text`, `gcode_path` (optional): Raw G-code source when no plan input is connected.

## Outputs

- `preview`: Preview image.
- `preview_info_json`: Render mode, plan stats, mesh count, and warnings.
- `summary`: Short preview summary.
- `plan`: Pass-through or parsed `MKR_GCODE_PLAN`.
