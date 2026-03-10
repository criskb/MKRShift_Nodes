# MKRImageSplitGrid

Splits an image batch into equal grid tiles so each chunk can be processed independently and stitched back together later.

## Inputs

- `image`: Input image batch.
- `columns`, `rows`: Grid size for the split.
- `size_mode`: `pad` keeps the full image by padding to an even canvas, while `crop` trims to the largest evenly divisible window.
- `anchor`: Chooses where padding or crop offset is taken from.
- `overlap_px`: Extra context added around every tile to reduce seams after downstream processing.
- `pad_mode`, `pad_value`: Controls how padded regions and overlap context are filled.

## Outputs

- `tiles`: Flattened tile batch in row-major order for each source image.
- `split_info_json`: JSON metadata required by `MKRImageCombineGrid` to restore the canvas correctly.
- `summary`: Short split summary.

## Use Cases

- Tile large images for denoise, upscale, or stylize passes.
- Run batch processing on equal chunks without manual crop math.
- Preserve overlap metadata so tiles can be stitched back with seam-aware blending.
