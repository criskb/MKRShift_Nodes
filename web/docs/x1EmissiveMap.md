# x1EmissiveMap

Extracts an emissive map from bright or saturated regions and keeps the output ready for direct use in preview materials.

## Inputs

- `image`: Source image batch.
- `source_mode`: Emissive extraction mode. `combined_emissive` favors bright regions and boosts strongly saturated lights, while the other modes let you force bright-color, saturated-color, masked-color, or white-hotspot output.
- `threshold`: Brightness threshold for activating the emissive signal.
- `softness`: Softens the threshold edge so the emissive map rolls in instead of clipping hard.
- `saturation_gate`: Saturation threshold used by the combined and saturated modes.
- `intensity`: Brightness multiplier applied to the final emissive image.
- `blur_radius`: Optional blur on the emissive strength mask.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `source_mask`: Optional mask used by `mask_color`.
- `mask`: Optional mask that limits where the emissive map is emitted.

## Outputs

- `image`: Emissive color map.
- `mask`: Emissive strength mask after thresholding and output masking.
- `emissive_info`: Summary string with the resolved settings and mask coverage.

## Notes

- This pairs directly with the `emissive` slot on `x1PreviewMaterial`.
- `combined_emissive` is designed for neon, panel lights, screen graphics, and stylized glow regions, not for physically measured radiance.
