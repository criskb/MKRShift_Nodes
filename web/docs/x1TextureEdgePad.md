# x1TextureEdgePad

Pads texture colors outward from valid regions to create UV bleed or atlas edge padding.

## Inputs

- `image`: Source texture batch.
- `source_mode`: Valid-source definition. Use `alpha`, `mask`, or `luma_nonzero`.
- `pad_pixels`: Maximum outward padding distance in pixels.
- `alpha_threshold`: Threshold used for `alpha`, `mask`, or `luma_nonzero` validity.
- `expand_alpha`: Expand the alpha channel into the padded region when the input has alpha.
- `source_mask`: Optional mask used when `source_mode=mask`.

## Outputs

- `image`: Edge-padded texture.
- `mask`: Fill mask showing the newly padded region.
- `edge_pad_info`: Summary string with the resolved settings.

## Notes

- Use this before packing textures into atlases or baking mip-safe decals.
- When `expand_alpha` is disabled, only the RGB padding grows; the original alpha stays intact.
