# x1AnamorphicStreaks

Creates highlight-driven anamorphic streaks for lens-flare style finishing.

## Inputs

- `image`: Source image batch.
- `orientation`: Choose `horizontal` for classic widescreen streaks or `vertical` for stylized vertical flares.
- `threshold`: Highlight threshold used to seed the streaks.
- `softness`: Soft rolloff around the threshold.
- `length_px`: Approximate streak length in pixels.
- `strength`: Brightness of the streak contribution.
- `tint_r`, `tint_g`, `tint_b`: Streak tint.
- `mix`: Blend between the original image and the streak-treated image.
- `mask_feather`: Feather radius for the optional mask.
- `invert_mask`: Invert the optional mask.
- `mask`: Optional mask to localize the effect.

## Outputs

- `image`: Image with anamorphic streaks applied.
- `mask`: Effect mask showing where the streak contribution landed.
- `anamorphic_streaks_info`: Summary string with the resolved settings.

## Notes

- This works best on bright practicals, specular highlights, neon, and emissive VFX plates.
- Use `horizontal` for more photographic flare behavior and `vertical` for stylized sci-fi looks.
