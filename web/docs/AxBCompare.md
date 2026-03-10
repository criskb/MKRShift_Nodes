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
- The viewer uses a shared compare frame derived from the connected image sizes, so either side can be the upscale and still align correctly in the split view.
- AxB previews keep high source resolution metadata, and split dragging stays stable when the Comfy canvas is zoomed.
