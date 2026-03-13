# x1AnisotropyMap

Builds a preview-ready anisotropy texture for brushed metal, satin, fiber, and directional composite materials.

## Inputs

- `image`: Source texture batch.
- `source_mode`: `combined_anisotropy` looks for smoother metallic or fiber-like regions that benefit from directional highlights.
- `direction_mode`: Picks the tangent-space flow direction. Use `horizontal`, `vertical`, `angle`, `gradient_tangent`, `gradient_normal`, `radial`, or `tangential`.
- `direction_angle_deg`: Angle override when `direction_mode` is `angle`.
- `center_x`, `center_y`: Origin for `radial` and `tangential` flow modes.
- `gradient_radius`: Blur radius for gradient-based flow directions.
- `normalize_mode`, `value_min`, `value_max`, `percentile_low`, `percentile_high`: Strength remapping controls.
- `detail_radius`, `detail_strength`: Strength heuristic controls.
- `gamma`, `contrast`, `blur_radius`: Final strength shaping controls.
- `source_mask`, `mask`, `mask_feather`: Upstream source gating and final output masking.

## Outputs

- `image`: Anisotropy texture encoded for preview/export, with `R/G` holding direction and `B` holding strength.
- `mask`: Scalar anisotropy-strength mask.
- `anisotropy_info`: Summary string with the resolved settings.

## Notes

- Feed the `image` output directly into `x1PreviewMaterial`'s `anisotropy` input.
- `gradient_tangent` is a strong default when you want flow to follow stripes, brushing, or weave-like features already present in the texture.
- `x1TextureStrata` and `x1TextureWeavePattern` are practical upstream sources for more intentional directional anisotropy.
