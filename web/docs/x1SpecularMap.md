# x1SpecularMap

Builds a grayscale specular map from image content or a supplied mask.

## Inputs

- `image`: Source image batch.
- `source_mode`: Specular source. `combined_specular` favors bright, low-saturation highlights plus local detail.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `detail_radius`: Radius used to isolate local highlight detail.
- `detail_strength`: Extra weighting for detail in the specular solve.
- `saturation_suppress`: Reduces the specular response on strongly saturated areas.
- `gamma`: Shapes the normalized scalar before output.
- `contrast`: Expands or compresses the specular range around mid-gray.
- `blur_radius`: Optional blur after normalization.
- `invert_values`: Invert the specular values.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `mask`: Optional mask that limits where the specular map is emitted.

## Outputs

- `image`: Grayscale specular map.
- `mask`: Scalar specular mask after normalization and output masking.
- `specular_info`: Summary string with the resolved settings and normalization range.

## Notes

- Higher values mean a stronger, cleaner specular response.
- `combined_specular` is best treated as a fast lookdev helper for relighting and material blocking.
