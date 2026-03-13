# x1ColorRegionMask

Builds a grayscale mask for a selected color family inside a texture or painted map.

## What It Does

- Selects a hue region such as red, green, blue, or a custom hue center.
- Suppresses low-saturation or near-black pixels so neutral shading does not flood the result.
- Outputs a grayscale `IMAGE`, a scalar `MASK`, and an info string.

## Typical Use

1. Feed in a painted, scanned, or baked texture.
2. Choose `color_preset` or switch to `custom` and dial `hue_center`.
3. Narrow `hue_width` for tighter isolation or raise `softness` for gentler falloff.
4. Use the mask to split material zones before roughness, metalness, wear, or packing passes.

## Notes

- This is useful when a source is too messy for `x1IDMapQuantize` or `x1IDMaskExtract`.
- `x1ScalarMapAdjust` is a good follow-up if you want a harder or softer final mask.
