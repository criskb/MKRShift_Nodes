# Aspect1XBatch

Builds a multi-aspect output set from one input image batch.

## What It Does

- Runs the pack's aspect preset list in portrait, horizontal, or both orientations.
- Returns image outputs as lists so the rest of the workflow can iterate over them.
- Emits both compact filename labels and longer description labels for downstream save or review steps.

## Typical Use

1. Feed in a final image batch.
2. Pick `orientation` and `mode`.
3. Send the list output into save nodes, review tools, or `MKRBatchCollagePreview`.

## Notes

- Duplicate aspect ratios are filtered so square-like outputs do not repeat unnecessarily.
- The batch node is best when you want deliverables, while `Aspect1X` is better for one-off framing.
