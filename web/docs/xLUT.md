# xLUT

## What It Does

`xLUT` applies an existing LUT or generates a new one from a reference image. It can return both the graded image and a reusable LUT payload for downstream nodes.

## Typical Flow

1. Connect an `IMAGE`.
2. Pick an existing LUT from the pack or connect a `lut_image`.
3. Adjust `strength`.
4. Keep `apply_generated_lut` enabled if you want the generated LUT applied immediately.
5. Send the returned LUT object into `xLUTOutput`, `x1LUTBlend`, or other LUT-aware nodes.

## Outputs

1. `image`
2. `lut_info`
3. `lut`

## Notes

- `generated_lut_size` controls LUT resolution.
- Higher `generated_style_strength` pushes the generated LUT more aggressively.
- `xLUTOutput` is the companion node for saving the generated LUT to disk.
