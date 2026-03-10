# AxBCompare

## What It Does

`AxBCompare` is a viewer node for side-by-side image review. It is meant for visual inspection rather than data transformation.

## Typical Flow

1. Connect `image_a` and `image_b`.
2. Choose `horizontal` or `vertical`.
3. Use the custom compare UI to inspect framing, grade, detail, and compositing differences.

## Notes

- This is an output-style inspection node and does not emit downstream data.
- Use it when tuning masks, LUTs, or look variants and you want a larger comparison surface than the stock preview.
- The viewer is resolution-aware: it does not upscale the smaller input to fake equal definition, so upscale comparisons keep their true relative detail footprint.
