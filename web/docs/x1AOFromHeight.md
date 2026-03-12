# x1AOFromHeight

Approximates ambient occlusion or cavity from a height source.

## Inputs

- `image`: Source height image.
- `source_mode`: Height source. Choose from luma, RGB channels, `value`, `alpha`, or `mask`.
- `output_mode`: `ao` outputs a bright-open / dark-occluded map. `cavity` outputs the cavity signal directly.
- `normalize_mode`: Use `auto_percentile`, `manual_range`, or `auto_range`.
- `value_min`, `value_max`: Manual normalization range when `manual_range` is selected.
- `percentile_low`, `percentile_high`: Percentile range when `auto_percentile` is selected.
- `radius`: Main neighborhood radius used for the occlusion solve.
- `intensity`: Occlusion strength multiplier.
- `gamma`: Shapes the normalized output.
- `invert_height`: Invert the source height before the solve.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used when `source_mode=mask`.
- `mask`: Optional mask that limits where the generated AO/cavity map is emitted.

## Outputs

- `image`: Grayscale AO or cavity map.
- `mask`: Scalar output map after normalization and optional masking.
- `ao_info`: Summary string with the resolved settings and normalization range.

## Notes

- This is a fast artist-driven approximation, not a physically accurate ray-traced AO solve.
