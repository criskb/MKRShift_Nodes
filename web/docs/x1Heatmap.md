# x1Heatmap

Generates a heatmap from image channels or an input mask for diagnostics, lookdev, and VFX debugging.

## Inputs

- `image`: Source image batch.
- `source_mode`: Heatmap source. Choose from luma, RGB channels, `max_rgb`, `saturation`, `value`, `alpha`, or `mask`.
- `palette`: Heatmap palette preset.
- `normalize_mode`: Use `manual_range`, `auto_range`, or `auto_percentile`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `gamma`: Contrast shaping for the normalized scalar map.
- `invert_values`: Invert the normalized values before color mapping.
- `overlay_opacity`: Blend between the original image and the heatmap.
- `mask_feather`: Feather radius for the optional `effect_mask`.
- `invert_mask`: Invert the optional `effect_mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `effect_mask`: Optional mask that limits where the heatmap is applied.

## Outputs

- `image`: Heatmap image.
- `mask`: Scalar heatmap mask after normalization and effect masking.
- `heatmap_info`: Summary string with the resolved settings and normalization range.

## Notes

- `source_mask` defines the values when `source_mode=mask`; `effect_mask` controls where the visualization is applied.
- If `source_mode` is `mask` or `alpha` and that source is unavailable, the node falls back to luma.
