# MKRPreSave

## What It Does

`MKRPreSave` is a preview-first image output node. It gives you a larger in-node review UI before you commit files to disk.

## Typical Flow

1. Connect an `IMAGE` batch.
2. Leave `preview_only` enabled while reviewing crops, fit mode, split orientation, and filename settings.
3. Disable `preview_only` when you want to write files.
4. Optionally connect a `MASK` and enable `save_mask` to export the preview mask alongside the image output.

## Output Modes

- `png` for stills with metadata support
- `jpeg` for smaller review exports
- `webp` for compact stills or animation
- `gif` for lightweight motion previews

## Notes

- `animation_mode = auto` saves a single animation for `gif` and animated `webp` when the input contains multiple frames.
- `filename_labels` can provide per-frame names for batch exports.
- This is an output node, so it does not emit downstream data.
