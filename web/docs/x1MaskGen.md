# x1MaskGen

## What It Does

`x1MaskGen` builds a soft mask from luminance, channels, hue, saturation, value, chroma keying, skin detection, edge detail, or a radial falloff.

## Typical Flow

1. Connect an `IMAGE`.
2. Pick a `mode` that matches the selection problem you are solving.
3. Refine the selection with threshold, softness, ranges, or radial controls.
4. Use `combine_mode`, `expand_pixels`, and `blur_radius` to finalize the mask shape.

## Outputs

1. `mask`
2. `preview`
3. `mask_info`

## Notes

- `channel` mode is useful for simple luma or single-channel extractions.
- `chroma_key` is the fastest way to isolate a known target color.
- `skin_tones` is a quick portrait starting point when you want a soft subject skin isolation without dialing a manual key color.
- `edge` mode is useful for stylized mattes or line-driven compositing.
