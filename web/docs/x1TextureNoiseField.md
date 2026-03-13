# x1TextureNoiseField

Generates a seamless grayscale procedural noise texture for surfacing, masks, breakup, and height-style inputs.

## Inputs

- `width`, `height`: Output texture resolution.
- `variant`: Noise style. `fbm` is the general-purpose default, `turbulence` and `ridged` are stronger for wear or rock breakup, and `value` gives a simpler base field.
- `scale_px`: Broad size of the primary noise features.
- `octaves`, `lacunarity`, `gain`: Fractal layering controls.
- `contrast`, `balance`, `invert`: Final shaping controls for the scalar field.
- `seed`: Keeps the output deterministic.

## Outputs

- `image`: The grayscale field expanded to RGB.
- `mask`: The same scalar field as a reusable mask.
- `noise_info`: Summary string with the resolved settings.

## Notes

- The field is tileable by design, so it can feed `x1TextureTilePreview`, `x1TextureDetileBlend`, or material-map nodes without needing an extra seamless pass.
- `ridged` is a good starting point for chipped roughness or broken height masks.
- `fbm` is the most neutral option when you want one field to drive several material channels together.
