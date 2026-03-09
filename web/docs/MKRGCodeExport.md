# MKRGCodeExport

Converts a generated `MKR_GCODE_PLAN` and `MKR_GCODE_PROFILE` into printable `.gcode`.

## Inputs

- `plan`: Toolpath plan from `MKRGCodeHeightmapPlate`, `MKRGCodeSpiralVase`, or future G-code generators.
- `profile`: Printer/material profile from `MKRGCodePrinterProfile`.
- `filename_prefix`, `subfolder`, `save_file`, `overwrite`, `filename_label`: Output file controls.
- `include_comments`: Adds layer and metadata comments into the generated G-code.

## Outputs

- `gcode_text`: Full generated G-code.
- `output_path`: Saved file path when `save_file` is enabled.
- `summary`: Export metadata including line count, extrusion, and estimated time.

## Notes

- Export places the object on the printer bed using the profile origin mode.
- Start/end G-code come from the printer profile, with a fallback startup sequence when those fields are blank.
