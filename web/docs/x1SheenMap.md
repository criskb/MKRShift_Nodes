# x1SheenMap

Derives a sheen-color map for cloth, velvet, coated fabric, and other fiber-heavy materials, then emits the scalar sheen mask alongside it.

## Inputs

- `image`: Source texture batch.
- `source_mode`: `combined_sheen` looks for colorful, moderately bright, smoother regions that read well as fabric sheen.
- `tint_mode`: Uses the source hue, a softened source tint, or neutral white variants for the final sheen color.
- `normalize_mode`, `value_min`, `value_max`, `percentile_low`, `percentile_high`: Scalar remapping controls.
- `detail_radius`, `detail_strength`: How strongly fine detail suppresses or preserves the sheen solve.
- `tint_strength`: How much the chosen tint mode influences the final sheen color.
- `gamma`, `contrast`, `blur_radius`: Final shaping controls.
- `source_mask`, `mask`, `mask_feather`: Upstream source gating and final output masking.

## Outputs

- `image`: Sheen color image, ready for `x1PreviewMaterial`'s `sheen_color` input.
- `mask`: Scalar sheen-strength mask.
- `sheen_info`: Summary string with the resolved settings.

## Notes

- Pair this with `x1TextureWeavePattern` or `x1TextureMacroVariation` for much more convincing fabric previews.
- `desaturated_source` is the safest default when you want cloth tint without over-coloring the sheen.
