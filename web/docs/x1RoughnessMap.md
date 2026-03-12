# x1RoughnessMap

Builds a grayscale roughness map from image content or a supplied mask.

## Inputs

- `image`: Source image batch.
- `source_mode`: Roughness source. `combined_roughness` mixes luma, fine detail, and saturation for a better default starting point.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `detail_radius`: Radius used to isolate local surface detail.
- `detail_strength`: Extra weighting for detail in the roughness solve.
- `gamma`: Shapes the normalized scalar before output.
- `contrast`: Expands or compresses the roughness range around mid-gray.
- `blur_radius`: Optional blur after normalization.
- `invert_values`: Invert the roughness values.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `mask`: Optional mask that limits where the roughness map is emitted.

## Outputs

- `image`: Grayscale roughness map.
- `mask`: Scalar roughness mask after normalization and output masking.
- `roughness_info`: Summary string with the resolved settings and normalization range.

## Notes

- Higher values mean rougher, less mirror-like surfaces.
- `combined_roughness` is intended as a practical lookdev default, not a physically measured surface solve.
