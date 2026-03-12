# x1ShockwaveDistort

Applies a radial shockwave-style distortion ring with optional chromatic split.

## Inputs

- `image`: Source image batch.
- `center_x`, `center_y`: Normalized shockwave center.
- `radius`: Normalized radius of the ring.
- `width`: Normalized width of the shockwave band.
- `amplitude_px`: Radial distortion amplitude in pixels. Negative values invert the displacement.
- `ring_hardness`: Shapes how soft or sharp the ring is.
- `chroma_split_px`: Extra red/blue separation around the wave front.
- `mix`: Blend between the original image and the distorted result.
- `mask_feather`: Feather radius for the optional mask.
- `invert_mask`: Invert the optional mask.
- `mask`: Optional mask to localize the effect.

## Outputs

- `image`: Distorted image.
- `mask`: Shockwave matte derived from the ring profile.
- `shockwave_info`: Summary string with the resolved settings.

## Notes

- Animate `radius` over time to push the shockwave through a shot.
- Useful for impacts, force fields, explosions, sonic rings, and stylized portal pulses.
