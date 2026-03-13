# x1ClearcoatMap

Derives a grayscale clearcoat-strength map from bright, neutral, and relatively smooth surface regions.

## What It Does

1. Samples a scalar source from the chosen channel or mask.
2. In `combined_clearcoat` mode, favors bright low-saturation areas with less local noise.
3. Normalizes the result into a clean grayscale map for preview or packing workflows.

## Inputs

- `source_mode`: Choose `combined_clearcoat` for the built-in heuristic or use a direct scalar channel.
- `normalize_mode`, `gamma`, `contrast`: Shape the result into a useful working range.
- `detail_radius`, `detail_strength`: Control how strongly local texture breakup suppresses the clearcoat response.
- `mask`, `mask_feather`: Limit the output to a target region.

## Notes

- Use this when lacquer, varnish, or coated painted regions need a separate response from the base material.
- `x1ScalarMapAdjust` is the fastest follow-up when you want to soften or remap the result before preview/export.
- `x1PreviewMaterial` accepts this directly through its `clearcoat` input.
