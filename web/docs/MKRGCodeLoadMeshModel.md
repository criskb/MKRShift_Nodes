# MKRGCodeLoadMeshModel

Loads an STL or OBJ mesh from disk, applies simple placement transforms, and renders a quick preview.

## Inputs

- `model_path`: Local path to an `.stl` or `.obj`.
- `center_xy`, `bed_align`: Recenter the model and drop it to Z=0.
- `scale`, `rotate_*`, `translate_*`: Basic transform controls.
- `preview_view`, `preview_size`: Preview camera and output size.

## Outputs

- `mesh`: `MKR_GCODE_MESH` triangle payload for preview or slicing nodes.
- `preview`: Rendered mesh preview image.
- `mesh_info_json`: Source path, triangle count, bounds, and metadata.
- `summary`: Short mesh-load summary.
