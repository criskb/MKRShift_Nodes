# x1NormalMap

Builds a tangent-space normal map from an image-derived height source or a supplied mask.

## Inputs

- `image`: Source image batch.
- `source_mode`: Height source. Choose from luma, RGB channels, `max_rgb`, `saturation`, `value`, `alpha`, or `mask`.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `gamma`: Shapes the normalized heightfield before normal generation.
- `blur_radius`: Optional blur applied before gradients are computed.
- `strength`: Surface slope multiplier for the generated normals.
- `convention`: Choose `opengl` or `directx` green-channel orientation.
- `invert_height`: Invert the heightfield before generating normals.
- `invert_x`: Flip the red channel direction.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode` is `mask`.
- `mask`: Optional mask that limits where the generated normals are emitted.

## Outputs

- `image`: Tangent-space normal map. Outside a masked region the node outputs a flat neutral normal.
- `mask`: Scalar height mask after normalization and output masking.
- `normal_info`: Summary string with the resolved settings and normalization range.

## Notes

- Use `x1Heightmap` first if you want to inspect or art-direct the heightfield before converting it to normals.
- `opengl` and `directx` differ only in the green channel orientation.
