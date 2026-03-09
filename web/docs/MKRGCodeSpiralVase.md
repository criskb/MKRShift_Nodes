# MKRGCodeSpiralVase

Generates a procedural spiral-vase style toolpath plan inspired by the earlier G-code Studio procedural experiments.

## Inputs

- `height_mm`, `base_radius_mm`, `top_radius_mm`: Vase silhouette.
- `bottom_layers`: Spiral base-disc layers before the wall rises.
- `layer_height_mm`, `line_width_mm`: Toolpath geometry.
- `segments_per_turn`: Curve smoothness.
- `wave_amplitude_mm`, `wave_frequency`: Radial modulation for more expressive forms.
- `print_speed_mm_s`, `travel_speed_mm_s`: Motion speeds when no profile defaults are used.
- `use_profile_defaults`, `profile` (optional): Pulls line width, layer height, and speeds from `MKR_GCODE_PROFILE`.

## Outputs

- `plan`: Custom `MKR_GCODE_PLAN` payload.
- `preview`: Top-view image preview of the vase path.
- `plan_info_json`: Bounds, stats, and generator metadata.
- `summary`: Short plan summary.
