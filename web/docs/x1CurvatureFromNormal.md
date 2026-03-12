# x1CurvatureFromNormal

Extracts curvature-style masks from a normal map for wear, edge, and cavity workflows.

## Inputs

- `image`: Source tangent-space normal map.
- `mode`: `combined`, `convex`, or `concave`.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `blur_radius`: Optional blur before curvature extraction.
- `strength`: Curvature intensity multiplier.
- `gamma`: Shapes the normalized curvature output.
- `invert_values`: Invert the curvature values.
- `mask_feather`: Feather radius for the optional `mask`.
- `invert_mask`: Invert the optional `mask`.
- `mask`: Optional mask that limits where the curvature map is emitted.

## Outputs

- `image`: Grayscale curvature map.
- `mask`: Scalar curvature mask after normalization and optional masking.
- `curvature_info`: Summary string with the resolved settings and normalization range.

## Notes

- `convex` is useful for edge wear masks and `concave` is useful for dirt/cavity buildup.
