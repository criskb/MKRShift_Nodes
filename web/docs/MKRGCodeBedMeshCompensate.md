# MKRGCodeBedMeshCompensate

Applies a bed mesh offset field to a `MKR_GCODE_PLAN` before export.

## Inputs

- `plan`: Toolpath plan to correct.
- `mesh_json`: Bed mesh JSON with an `offsets` 2D array and optional bed size fields.
- `max_compensation_mm`: Clamp limit for the applied Z correction.
- `warn_if_over_mm`: Warns when compensation exceeds this amount.
- `fade_height_mm`: Fades the correction out over the first layers.
- `use_profile_bed_size`, `profile` (optional): Uses the printer profile bed size and placement offset when mapping the mesh.

## Outputs

- `plan`: Corrected plan with updated Z moves.
- `report_json`: Mesh usage report, max compensation, and warnings.
- `summary`: Short summary of the applied correction.

## Mesh Format

```json
{
  "bed_width_mm": 220,
  "bed_depth_mm": 220,
  "offsets": [[0.00, 0.02, 0.01], [0.03, 0.00, -0.01], [0.05, 0.01, -0.02]]
}
```
