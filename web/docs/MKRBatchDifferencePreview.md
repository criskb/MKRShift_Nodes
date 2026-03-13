# MKRBatchDifferencePreview

Builds a technical compare sheet for two image batches with an optional per-pair difference tile.

## What It Does

- Pairs `image_a` and `image_b` across the batch and renders them into a grouped inspect board.
- Generates a heat or grayscale delta tile so changes pop immediately during review.
- Emits JSON with mean and peak difference per pair for quick triage.

## Typical Use

1. Feed in two matching batches from before/after or A/B workflows.
2. Choose `A | B | Diff`, `A | Diff`, or `Diff Only`.
3. Save the `difference_preview` image or route it into presentation/review nodes.

## Notes

- If batch lengths differ, the node uses the shortest batch and records a warning in `layout_json`.
- This is an inspect node, not a polished client board; use `MKRStudioCompareBoard` when you want a presentation-style layout.
