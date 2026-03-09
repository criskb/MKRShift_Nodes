# MKRGCodeHeightmapPlate

Turns an image into a layered raster toolpath plan for a 3D-printed relief plate.

## Inputs

- `image`: Source image. The first image in the batch is used.
- `width_mm`, `height_mm`: Physical footprint of the print.
- `base_layers`: Solid foundation layers before relief variation starts.
- `relief_height_mm`: Extra height generated from the image luminance.
- `layer_height_mm`, `line_width_mm`: Toolpath resolution.
- `fill_mode`: `alternate_xy`, `x_only`, or `y_only` raster direction.
- `invert_heightmap`, `mirror_x`, `mirror_y`: Heightmap transforms.
- `print_speed_mm_s`, `travel_speed_mm_s`: Motion speeds when no profile defaults are used.
- `use_profile_defaults`, `profile` (optional): Pulls path geometry and speeds from `MKR_GCODE_PROFILE`.

## Outputs

- `plan`: Custom `MKR_GCODE_PLAN` payload.
- `preview`: Top-view image preview of the generated raster path.
- `plan_info_json`: Bounds, stats, and plan metadata.
- `summary`: Short path summary.
