# x1MetalnessMap

Builds a grayscale metalness map from image content or a supplied mask.

## Inputs

- `image`: Source image batch.
- `source_mode`: Metalness source. `combined_metalness` biases toward bright chrome-like or colored-metal-like regions and adds optional detail.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `detail_radius`: Radius used to isolate local surface detail.
- `detail_strength`: Extra weighting for detail in the metalness solve.
- `gamma`: Shapes the normalized scalar before output.
- `contrast`: Expands or compresses the metalness range around mid-gray.
- `blur_radius`: Optional blur after normalization.
- `invert_values`: Invert the metalness values.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `mask`: Optional mask that limits where the metalness map is emitted.

## Outputs

- `image`: Grayscale metalness map.
- `mask`: Scalar metalness mask after normalization and output masking.
- `metalness_info`: Summary string with the resolved settings and normalization range.

## Notes

- Higher values mean more metallic surface response.
- `combined_metalness` is an artist-driven starting point for lookdev, not a measured scanner-based metalness solve.
