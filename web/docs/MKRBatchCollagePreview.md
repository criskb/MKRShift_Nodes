# MKRBatchCollagePreview

Builds a labeled contact-sheet style preview from an image list or batch.

## What It Does

- Lays out incoming images into a grid or compact strip layout.
- Adds readable labels, optional XY labels, and optional resolution text.
- Outputs a labeled per-image batch plus a single collage image and JSON layout metadata.

## Typical Use

1. Feed in a batch or list of images from compare, aspect, or parameter sweep workflows.
2. Set `columns` or let the node auto-resolve a square-ish grid.
3. Use `labels`, `show_xy_labels`, and `theme` to make the sheet readable for review.
4. Save or pass the single `collage_image` to client-review or planning nodes.

## Notes

- The display name is now `XY:PRE / Batch Collage Preview`, so it is easier to find whether you remember the old or new name.
- `layout_json` records the generated grid shape and labels so the output can be traced later.
