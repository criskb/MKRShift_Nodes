# x1CavityMap

Builds a short-range cavity mask from albedo, grayscale, height-like, or mask inputs.

## What It Does

1. Samples a grayscale source from the chosen channel or mask.
2. Compares each pixel against a blurred local average.
3. Extracts concave detail, convex detail, or unsigned micro-detail as a grayscale output.

## Inputs

- `source_mode`: Choose which channel drives the cavity extraction.
- `polarity`: `concave` favors dark creases, `convex` favors bright ridges, and `both` gives unsigned fine detail.
- `radius`: Local neighborhood size used for the cavity comparison.
- `normalize_mode`, `gamma`, `contrast`: Shape the extracted mask into a usable map range.
- `mask`, `mask_feather`: Limit the effect to a region.

## Notes

- This is tighter and more detail-focused than `x1AOFromHeight`.
- It works well as a roughness driver, a wear mask seed, or an extra channel into `x1PBRPack`.
