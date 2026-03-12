# x1IDMaskExtract

Extracts a clean grayscale mask from an ID map by matching a target color or sampling a color from the image.

## Inputs

- `image`: Source ID map or color-coded region map.
- `selection_mode`: Use `manual_color` or `sample_position`.
- `color_space`: Match in `rgb` or `hsv`.
- `target_r`, `target_g`, `target_b`: Manual target color when `selection_mode=manual_color`.
- `sample_x`, `sample_y`: Normalized sample position when `selection_mode=sample_position`.
- `tolerance`: Match threshold around the picked color.
- `softness`: Falloff width around the tolerance threshold.
- `blur_radius`: Optional blur after extraction.
- `invert_values`: Invert the extracted mask.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `mask`: Optional mask that limits where the extracted result is emitted.

## Outputs

- `image`: Grayscale selection image.
- `mask`: Extracted selection mask after optional output masking.
- `id_mask_info`: Summary string with the resolved target color and match settings.

## Notes

- `rgb` works well for clean flat ID maps.
- `hsv` is useful when hue separation matters more than brightness shifts.
