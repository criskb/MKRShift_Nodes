# x1OpacityMap

Builds a grayscale opacity map for cutouts, decals, cards, and soft transparency workflows.

## Inputs

- `image`: Source image batch.
- `source_mode`: Opacity source. `combined_opacity` prefers the input alpha channel when present, falls back to a supplied `source_mask`, and otherwise treats the surface as fully opaque.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `detail_radius`, `detail_strength`: Optional detail controls when using `detail` as the source.
- `gamma`, `contrast`, `blur_radius`: Shape and soften the resulting opacity map.
- `invert_values`: Invert the opacity values.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask` or as the fallback for `combined_opacity`.
- `mask`: Optional mask that limits where the opacity map is emitted.

## Outputs

- `image`: Grayscale opacity map where white is more opaque.
- `mask`: Scalar opacity mask after normalization and output masking.
- `opacity_info`: Summary string with the resolved settings and normalization range.

## Notes

- This is a good companion for the `opacity` slot on `x1PreviewMaterial`.
- If the source image does not contain alpha, `combined_opacity` intentionally stays conservative instead of guessing transparency from color alone.
