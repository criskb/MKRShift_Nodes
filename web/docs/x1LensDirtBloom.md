# x1LensDirtBloom

Adds highlight-driven bloom modulated by generated lens dirt, smudges, and fine scratch texture.

## Inputs

- `image`: Source image batch.
- `threshold`: Highlight threshold used to seed the bloom.
- `softness`: Soft rolloff around the threshold.
- `bloom_radius`: Blur radius used for the bloom halo.
- `bloom_strength`: Brightness of the bloom contribution.
- `dirt_amount`: How strongly the generated dirt texture modulates the bloom.
- `dirt_scale`: Overall size of the generated dirt features.
- `dirt_contrast`: Contrast shaping for the dirt pattern.
- `tint_r`, `tint_g`, `tint_b`: Bloom tint.
- `seed`: Random seed for the generated dirt texture.
- `mix`: Blend between the original image and the effect.
- `mask_feather`: Feather radius for the optional mask.
- `invert_mask`: Invert the optional mask.
- `mask`: Optional mask to localize the effect.

## Outputs

- `image`: Image with lens-dirt bloom applied.
- `mask`: Effect mask showing where bloom contribution landed.
- `lens_dirt_bloom_info`: Summary string with the resolved settings.

## Notes

- This is useful for dirty-glass bloom, practical lights, headlights, street lamps, and atmospheric night shots.
- Change `seed` for a different dirt layout without rebuilding the rest of the graph.
