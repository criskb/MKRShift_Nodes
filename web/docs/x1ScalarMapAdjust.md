# x1ScalarMapAdjust

Normalizes, remaps, inverts, and softens any scalar image or mask into a clean grayscale working map.

## What It Does

1. Samples a scalar source from a channel, alpha, value, saturation, detail, or optional mask input.
2. Applies the same normalization vocabulary used by the other surface-map nodes.
3. Emits a grayscale image plus scalar mask so the adjusted result can be previewed, packed, or reused downstream.

## Inputs

- `source_mode`: Choose the source channel or use `detail` / `mask` for utility workflows.
- `normalize_mode`, `value_min`, `value_max`, `percentile_low`, `percentile_high`: Control the normalization range.
- `gamma`, `contrast`, `blur_radius`: Shape the scalar response after normalization.
- `mask`, `mask_feather`: Limit where the adjusted scalar is emitted.

## Notes

- This is a good bridge node between extraction nodes like `x1CavityMap` and packing/preview nodes like `x1PBRPack` and `x1PreviewMaterial`.
- It is also useful for preparing `clearcoat_roughness` or transmission-thickness guide maps without building a separate custom node.
