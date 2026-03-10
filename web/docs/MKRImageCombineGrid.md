# MKRImageCombineGrid

Stitches a tile batch back into full images using metadata from `MKRImageSplitGrid`.

## Inputs

- `tiles`: Processed tile batch.
- `split_info_json`: Metadata emitted by `MKRImageSplitGrid`. Leave the manual size fields at defaults when this is connected.
- `columns`, `rows`, `size_mode`, `overlap_px`: Manual fallback settings when split metadata is unavailable.
- `canvas_width`, `canvas_height`, `original_width`, `original_height`, `content_x`, `content_y`: Manual restore controls for advanced recovery workflows.
- `blend_mode`: `feather` softens seams, `average` uses flat overlap blending, and `center_crop` keeps only each tile core.

## Outputs

- `image`: Reconstructed image batch.
- `combine_info_json`: JSON summary of the stitched canvas and output size.
- `summary`: Short combine summary.

## Use Cases

- Reassemble tiled image batches after upscaling or stylization.
- Blend overlapped chunks to avoid visible seams.
- Recover padded full-frame results from large-image tile workflows.
