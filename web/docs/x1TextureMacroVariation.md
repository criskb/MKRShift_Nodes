# x1TextureMacroVariation

Applies deterministic low-frequency hue, value, and contrast variation to reduce obvious repetition in tiled textures.

## What It Does

1. Generates a seed-stable low-frequency variation field.
2. Uses that field to push broad hue, value, and contrast drift across the texture.
3. Emits the variation mask so the same breakup pattern can drive roughness, dirt, or wear downstream.

## Inputs

- `macro_scale_px`: Size of the low-frequency breakup pattern.
- `strength`: Overall blend amount.
- `hue_variation`, `value_variation`, `contrast_variation`: How strongly each channel of variation is applied.
- `seed`: Keeps the result deterministic for repeatable material builds.
- `mask`, `mask_feather`: Limit the effect to selected regions.

## Notes

- This is meant for broad tiling breakup, not fine noise.
- Reuse the emitted mask to keep base color, roughness, and cavity breakup visually in sync.
