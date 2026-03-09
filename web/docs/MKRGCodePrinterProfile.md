# MKRGCodePrinterProfile

Builds a reusable FDM printer/material profile for the `G-code` category.

## Inputs

- `printer_name`, `bed_width_mm`, `bed_depth_mm`, `bed_height_mm`: Machine identity and build volume.
- `origin`: Bed placement mode for exported plans.
- `nozzle_diameter_mm`, `line_width_mm`, `layer_height_mm`, `filament_diameter_mm`: Core extrusion geometry.
- `extrusion_multiplier`, `nozzle_temp_c`, `bed_temp_c`: Material and process settings.
- `print_speed_mm_s`, `travel_speed_mm_s`, `retraction_mm`, `retraction_speed_mm_s`, `travel_z_mm`: Motion settings.
- `home_before_print`, `prime_line`, `start_gcode`, `end_gcode`: Startup and shutdown behavior.

## Outputs

- `profile`: Custom `MKR_GCODE_PROFILE` payload for downstream G-code nodes.
- `profile_json`: JSON version of the same profile for logging or debugging.
- `summary`: Compact printer summary string.
