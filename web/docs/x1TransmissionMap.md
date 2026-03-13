# x1TransmissionMap

Builds a grayscale transmission mask for glass, plastic, and other light-passing materials.

## What It Does

1. Reads a scalar source from alpha, luma, value, detail, or mask inputs.
2. In `combined_transmission` mode, prefers existing alpha when available and otherwise biases toward bright smooth glass-like regions.
3. Outputs a grayscale transmission map plus a matching scalar mask.

## Inputs

- `source_mode`: `combined_transmission` is the practical default for lookdev. Direct channel modes are useful for manual control.
- `normalize_mode`, `gamma`, `contrast`: Remap the transmission signal into the range you want.
- `detail_radius`, `detail_strength`: Tune how much fine breakup reduces the inferred transmission response.
- `mask`, `mask_feather`: Constrain the result to a region.

## Notes

- This is not the same as cutout opacity. Use `x1OpacityMap` for binary/soft alpha and `x1TransmissionMap` for physically light-passing material response.
- `x1PreviewMaterial` accepts this directly through its `transmission` input.
