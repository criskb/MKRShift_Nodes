# x1SlopeMaskFromNormal

Builds directional slope masks from a tangent-space normal map.

## Inputs

- `image`: Source normal map.
- `mode`: Choose a directional hemisphere (`+x`, `-x`, `+y`, `-y`, `+z`, `-z`) or `rim`.
- `strength`: Multiplier for the directional response.
- `gamma`: Shapes the final mask.
- `invert_values`: Invert the generated slope mask.
- `mask_feather`: Feather radius for the optional `mask`.
- `invert_mask`: Invert the optional `mask`.
- `mask`: Optional mask that limits where the generated slope map is emitted.

## Outputs

- `image`: Grayscale slope mask.
- `mask`: Scalar slope mask after optional masking.
- `slope_info`: Summary string with the resolved settings.

## Notes

- `+z` is a useful starting point for broad outward-facing selection. `rim` is useful for edge breakup and stylized wear masks.
