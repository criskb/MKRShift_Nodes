# x1HeatHaze

Applies shimmering heat-distortion style refraction with optional chromatic separation.

## Inputs

- `image`: Source image batch.
- `direction`: Main flow direction for the shimmer field.
- `strength_px`: Maximum distortion amplitude in pixels.
- `scale`: Spatial frequency of the distortion pattern.
- `phase_deg`: Phase offset for animation or look variation.
- `chroma_split_px`: Additional red/blue separation for refractive shimmer.
- `mix`: Blend between the original image and the distorted result.
- `mask_feather`: Feather radius for the optional mask.
- `invert_mask`: Invert the optional mask.
- `mask`: Optional mask to localize the effect.

## Outputs

- `image`: Distorted image.
- `mask`: Distortion matte derived from displacement magnitude.
- `heat_haze_info`: Summary string with the resolved settings.

## Notes

- Animate `phase_deg` over time for moving air, exhaust, or desert shimmer.
- Pair this with a hand-painted or tracked mask for fire, engines, weapons, or atmospheric composites.
