# x1TextureDelight

Flattens broad baked lighting in scan and albedo textures while keeping hue and local surface detail intact.

## Inputs

- `image`: Source texture batch.
- `blur_radius`: Scale used to estimate the low-frequency lighting field.
- `flatten_strength`: Overall strength of the de-lighting solve.
- `detail_preserve`: How much original micro-contrast is reintroduced after the low-frequency correction.
- `shadow_lift`: Extra lift bias for darker regions.
- `highlight_compress`: Extra compression bias for hot spots and bright falloff.
- `mask_feather`: Feather radius for the optional effect mask.
- `invert_mask`: Invert the optional effect mask.
- `mask`: Optional mask for limiting the correction to a specific region.

## Outputs

- `image`: Delighted texture with alpha preserved when present.
- `mask`: Adjustment-strength mask showing where the texture changed most.
- `delight_info`: Summary string with the resolved settings and mask coverage.

## Notes

- This is best for scanner falloff, soft shading gradients, and uneven bounce-light baked into albedo.
- It will not fully remove sharp cast shadows or mirror-like specular highlights.
- A good order is `x1TextureDelight` -> `x1TextureSeamless` -> `x1PreviewMaterial` when preparing lookdev surfaces.
