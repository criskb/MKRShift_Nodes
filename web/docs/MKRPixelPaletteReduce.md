# MKRPixelPaletteReduce

Reduces an image to a smaller, pixel-art-friendly palette and returns the palette colors as JSON.

## Inputs

- `image`: Source image batch.
- `palette_mode`: `adaptive`, `uniform`, or `custom_json`.
- `color_count`: Target palette size.
- `dither_mode`: `none` or `bayer_4x4`.
- `dither_strength`: Ordered dither strength when `bayer_4x4` is enabled.
- `preserve_alpha`: Keeps the original alpha channel when present.
- `palette_json`: Optional custom palette JSON array of hex colors or RGB triplets.

## Outputs

- `image`: Quantized image batch.
- `palette_json`: Exported palette colors for the first frame.
- `summary_json`: Mode, warnings, and per-frame palette details.

## Notes

- `custom_json` is useful when you want a locked handheld-console or brand palette.
- `adaptive` is usually the fastest way to make noisy renders read more like intentional sprite work.
- Pair this with `MKRSpriteSheetExtract` and `MKRImageCombineGrid` for a simple atlas cleanup workflow.
