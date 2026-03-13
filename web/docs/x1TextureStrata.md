# x1TextureStrata

Generates a seamless directional band pattern for layered rock, sediment, wood grain, brushed breakup, or stylized streaking.

## Inputs

- `width`, `height`: Output texture resolution.
- `profile`: Band shape. `soft` is smoother, `veins` gives sharper layered streaks, and `terrace` creates stepped strata.
- `band_scale_px`: Overall spacing of the bands.
- `direction_deg`: Direction of the layer flow.
- `warp_strength`: How much the bands are bent by a low-frequency warp field.
- `breakup_scale_px`, `breakup_strength`: Secondary breakup that keeps the pattern from feeling too uniform.
- `contrast`, `balance`, `invert`: Final shaping controls.
- `seed`: Keeps the output deterministic.

## Outputs

- `image`: The grayscale pattern expanded to RGB.
- `mask`: The same scalar field as a reusable mask.
- `strata_info`: Summary string with the resolved settings.

## Notes

- This is useful for rock layers, wood-like streaks, brushed anisotropic breakup guides, and directional weathering masks.
- `veins` plus moderate `warp_strength` is a strong starting point for stylized wood or mineral textures.
- Pair it with `x1TextureMacroVariation` when you want both directional structure and broader low-frequency detiling in the same material build.
