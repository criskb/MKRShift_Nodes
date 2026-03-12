# x1PreviewMaterial

Builds a previewable PBR material asset and shows it directly in-node through ComfyUI's built-in 3D viewer.

## What It Does

1. Plug in any combination of `base_color`, `normal`, `roughness`, `metalness`, `specular`, `height`, `ao`, `opacity`, and `emissive`.
2. The node writes a previewable `.gltf` package into `ComfyUI/output/mkrshift/material_preview`.
3. The native `Load3D` viewer is mounted inside the node so you can orbit and inspect the material without leaving the graph.

## Inputs

- `preview_mesh`: Preview on a shader ball, flat plane, or cube.
- `uv_scale`: Repeats the texture coordinates on the preview mesh.
- `roughness_default`, `metalness_default`: Fallback values when those maps are not connected.
- `normal_strength`: Multiplies tangent-space normal intensity before export.
- `height_to_normal_strength`: Converts an optional height map into supplemental preview normals.
- `emissive_strength`: Brightness multiplier for the emissive map preview.
- `alpha_mode`: `auto` chooses `blend` for soft transparency and `mask` for mostly binary cutouts.
- `asset_label`: Prefix used for the exported preview files.

## Notes

- `specular` is approximated into the preview roughness response so legacy/spec workflows still read in the shader-ball preview.
- `height` is baked into preview normals because glTF preview materials do not expose a native displacement slot.
- The node also outputs the generated `model_file` path, so you can pass it to other 3D preview or export tools if needed.
