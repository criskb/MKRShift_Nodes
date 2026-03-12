# x1NormalBlend

Blends a detail normal map into a base normal map for layered surfacing work.

## Inputs

- `base_normal`: Base tangent-space normal map.
- `detail_normal`: Detail tangent-space normal map.
- `blend_mode`: `whiteout`, `add`, or `lerp`.
- `strength`: Blend intensity for the detail normal.
- `mask_feather`: Feather radius for the optional `mask`.
- `invert_mask`: Invert the optional `mask`.
- `mask`: Optional mask that limits where the detail normal is applied.

## Outputs

- `image`: Blended normal map.
- `mask`: Effective blend mask after optional masking.
- `normal_blend_info`: Summary string with the resolved settings.

## Notes

- `whiteout` is the most practical default for stacking broad and fine detail normals.
