# x1ThicknessMap

Builds a grayscale thickness guide for transmission and volume preview work.

## What It Does

1. Samples thickness from `inverse_luma`, `alpha`, `mask`, or other scalar channels.
2. In `combined_thickness` mode, biases toward darker and denser-looking regions while mixing in local breakup.
3. Emits a normalized grayscale thickness map for preview/export use.

## Inputs

- `source_mode`: `combined_thickness` is a good default for quick glass/plastic lookdev, while `inverse_luma` and `mask` are useful for directed control.
- `normalize_mode`, `gamma`, `contrast`: Shape the thickness map into the desired response range.
- `detail_radius`, `detail_strength`: Control how much micro-detail contributes to thicker-looking regions.
- `mask`, `mask_feather`: Limit the effect spatially.

## Notes

- Thickness only matters in preview when the material is also using transmission/volume behavior.
- `x1PreviewMaterial` accepts this directly through its `thickness` input.
