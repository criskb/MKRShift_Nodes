# x1PreviewMaterial

Builds a previewable PBR material asset and shows it directly in-node through ComfyUI's built-in 3D viewer.

## What It Does

1. Plug in any combination of `base_color`, `normal`, `roughness`, `metalness`, `specular`, `height`, `ao`, `opacity`, `emissive`, `clearcoat`, `clearcoat_roughness`, `anisotropy`, `sheen_color`, `sheen_roughness`, `transmission`, `thickness`, `iridescence`, and `iridescence_thickness`.
2. The node writes a self-contained previewable `.glb` asset into `ComfyUI/output/mkrshift/material_preview`.
3. The native `Load3D` viewer is mounted inside the node so you can orbit and inspect the material without leaving the graph.

## Inputs

- `preview_mesh`: Preview on a shader ball, flat plane, or cube.
- `uv_scale`: Repeats the texture coordinates on the preview mesh.
- `roughness_default`, `metalness_default`: Fallback values when those maps are not connected.
- `normal_strength`: Multiplies tangent-space normal intensity before export.
- `normal_convention`: `directx` flips the incoming green channel into glTF/OpenGL space before export. `opengl` passes the normal map through as-is.
- `height_to_normal_strength`: Converts an optional height map into supplemental preview normals.
- `emissive_strength`: Brightness multiplier for the emissive map preview.
- `alpha_mode`: `auto` chooses `blend` for soft transparency and `mask` for mostly binary cutouts.
- `asset_label`: Prefix used for the exported preview files.
- `advanced_settings_json`: Optional JSON overrides for physical material defaults without adding more dedicated widgets.

## Advanced Settings JSON

- Supported keys: `specular_default`, `specular_color_default`, `clearcoat_default`, `clearcoat_roughness_default`, `anisotropy_default`, `anisotropy_rotation`, `anisotropy_rotation_deg`, `sheen_color_default`, `sheen_roughness_default`, `transmission_default`, `thickness_default`, `iridescence_default`, `iridescence_ior`, `iridescence_thickness_min`, `iridescence_thickness_max`, `ior`, `attenuation_distance`, `attenuation_color`, `displacement_mode`, `height_displacement_strength`, `normal_displacement_strength`, `displacement_midlevel`.
- `displacement_mode` supports `auto`, `off`, `height`, `normal`, and `height_normal`.
- Leave it empty to preserve the current core-PBR behavior.
- Example: `{"ior": 1.33, "attenuation_distance": 0.45, "attenuation_color": [0.72, 0.9, 1.0], "anisotropy_rotation_deg": 18.0, "iridescence_ior": 1.22, "iridescence_thickness_min": 120.0, "iridescence_thickness_max": 650.0}`
- Displacement example: `{"displacement_mode": "height_normal", "height_displacement_strength": 0.12, "normal_displacement_strength": 0.05, "displacement_midlevel": 0.5}`

## Notes

- `x1OpacityMap`, `x1EmissiveMap`, `x1ClearcoatMap`, `x1ClearcoatRoughnessMap`, `x1AnisotropyMap`, `x1SheenMap`, `x1TransmissionMap`, `x1ThicknessMap`, and `x1IridescenceMap` are the fastest way to derive missing material slots before sending the result into preview export.
- `x1PBRPack` is the follow-up step when you want to turn the previewed loose maps into engine-style packed textures for export.
- `x1ScalarMapAdjust` is useful for shaping `clearcoat_roughness`, transmission, or thickness inputs before preview, and `x1EdgeWearMask` is a practical upstream mask source when you want to break the material into worn versus coated regions.
- The preview path expects glTF/OpenGL tangent-space normals. Leave `normal_convention` on `directx` for most external engine-style normal maps, and switch it to `opengl` when feeding a map that already matches glTF or the output of `x1NormalMap` in OpenGL mode.
- `specular` is still approximated into the preview roughness response for legacy/spec workflows, and it now also exports `KHR_materials_specular` when the map or defaults are actually in use.
- `height` now displaces the preview mesh geometry by default with a conservative strength, then also contributes to the preview normals.
- `normal` can optionally drive extra mesh displacement through `advanced_settings_json` when you want the preview sphere to feel more embossed than a pure shading-only normal map.
- The preview exporter now emits standard glTF material extensions for specular, clearcoat, anisotropy, sheen, transmission, volume, iridescence, and IOR only when those inputs or advanced defaults are actually in use.
- The node also outputs the generated `model_file` path, and the exported `.glb` is self-contained so it can be handed directly to `Preview3D`.
