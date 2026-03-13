# Aspect1X

Reshapes an image batch to one chosen output aspect for social, delivery, or review framing.

## What It Does

- Pads or crops to a selected preset aspect.
- Supports portrait and horizontal orientation from the same preset list.
- Outputs the reframed image plus a filename label string you can reuse in save nodes.

## Main Controls

- `aspect_1x`: Target aspect preset.
- `orientation`: Portrait or horizontal version of that preset.
- `mode`: `pad` keeps the full frame, `crop` fills the frame.
- Optional offsets and `Position` let you bias the framing without building another graph step.
- `background_mode` controls how padded space is filled.

## Notes

- Use `Aspect1XBatch` when you want a full export set across many ratios in one pass.
- Pair it with `MKRBatchCollagePreview` to review multiple aspect outputs at once.
