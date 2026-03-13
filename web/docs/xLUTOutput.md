# xLUTOutput

Saves a LUT payload or builds one from an image and writes it out as a `.cube` file.

## What It Does

- Accepts the `lut` output from `xLUT` or generates a LUT from a connected `lut_image`.
- Saves the LUT into the chosen subfolder.
- Optionally renders a preview image so the saved LUT is easier to inspect later.

## Inputs

- `save_name`, `subfolder`, `overwrite`: Control the output path and overwrite behavior.
- `save_preview`, `preview_size`: Control the optional preview render.
- `generated_lut_size`, `generated_style_strength`: Used when generating a LUT from `lut_image`.

## Outputs

1. `lut`
2. `saved_path`
3. `save_info`

## Notes

- This is an output node and runs on every queue, even if its inputs are unchanged.
- The fastest path is `xLUT -> xLUTOutput`, but it also works as an image-to-LUT utility when no LUT payload is connected.
