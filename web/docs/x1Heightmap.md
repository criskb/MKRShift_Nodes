# x1Heightmap

Generates a grayscale heightmap from image channels or an input mask.

## Inputs

- `image`: Source image batch.
- `source_mode`: Height source. Choose from luma, RGB channels, `max_rgb`, `saturation`, `value`, `alpha`, or `mask`.
- `normalize_mode`: Use `manual_range`, `auto_range`, or `auto_percentile`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `gamma`: Shapes the normalized scalar map before output.
- `contrast`: Expands or compresses the height range around mid-gray.
- `blur_radius`: Optional blur applied after normalization.
- `invert_values`: Invert the height values.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `mask`: Optional mask that limits where the generated heightmap is emitted.

## Outputs

- `image`: Grayscale heightmap image.
- `mask`: Scalar height mask after normalization and output masking.
- `heightmap_info`: Summary string with the resolved settings and normalization range.

## Notes

- `source_mask` defines the sampled values when `source_mode=mask`; `mask` limits where the final heightmap is present.
- If `source_mode` is `mask` or `alpha` and that source is unavailable, the node falls back to luma.
