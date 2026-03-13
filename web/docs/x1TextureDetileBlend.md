# x1TextureDetileBlend

Blends a half-tile offset sample back into the texture using a low-frequency mask to reduce obvious repetition.

## What It Does

- Generates a deterministic irregular blend field from `macro_scale_px` and `seed`.
- Mixes the original texture with a half-offset version to break visible repeats.
- Optionally color-matches the offset sample before blending and preserves original micro detail.

## Typical Use

1. Feed in a tileable texture after cleanup or delighting.
2. Tune `macro_scale_px` to the size of the repetition you want to hide.
3. Raise `blend_strength` for stronger detiling and `detail_preserve` to keep the original surface crisp.
4. Use the emitted mask to drive follow-up roughness, dirt, or breakup passes.

## Notes

- This works best after `x1TextureSeamless` and before `x1TextureTilePreview`.
- `x1TextureMacroVariation` is complementary: it shifts hue/value/contrast, while this node spatially re-blends the tile.
- Alpha is preserved unchanged when present.
