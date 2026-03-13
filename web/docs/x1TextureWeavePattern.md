# x1TextureWeavePattern

Generates a seamless woven textile pattern for cloth, carbon-fiber style materials, basket weaves, and composite-surface breakup.

## Inputs

- `width`, `height`: Output texture resolution.
- `style`: Weave structure. `plain` is balanced, `twill` gives a directional drift, and `basket` groups threads into chunkier blocks.
- `warp_scale_px`, `weft_scale_px`: Density of the vertical and horizontal thread lanes.
- `thread_width`: Relative width of each strand inside its lane.
- `relief`: How strongly the over-under weave depth is expressed.
- `contrast`, `balance`, `invert`: Final shaping controls.
- `seed`: Keeps the subtle strand irregularity deterministic.

## Outputs

- `image`: The grayscale pattern expanded to RGB.
- `mask`: The same scalar field as a reusable mask.
- `weave_info`: Summary string with the resolved settings.

## Notes

- This is strong as a height, roughness, or anisotropic-guide style source for cloth and composite materials.
- `twill` is the most useful starting point when you want a carbon-fiber-like directional weave.
- Search aliases include `fabric`, `cloth`, and `carbon fiber`.
