# MKRGCodeExternalSlicer

Runs an external slicer CLI against a loaded mesh and returns G-code plus a parsed previewable plan.

## Inputs

- `mesh`: `MKR_GCODE_MESH` from `MKRGCodeLoadMeshModel`.
- `engine`: `orca`, `prusa`, or `cura`.
- `engine_path`: Optional explicit CLI binary path.
- `engine_args_text`: Optional newline-delimited arg template. Supports `{input}`, `{output}`, and `{config}` placeholders.
- `profile`, `slicer_settings`, `settings_json` (optional): Settings sources merged into the slicer invocation.
- `filename_prefix`, `subfolder`, `save_file`, `overwrite`: Output controls.
- `dry_run`: Builds the command/config without executing the slicer.

## Outputs

- `gcode_text`: Slicer output when the command ran successfully.
- `plan`: Parsed `MKR_GCODE_PLAN` built from the returned G-code.
- `output_path`: Saved `.gcode` path when file saving is enabled.
- `summary`: Command/config summary and warnings.

## Notes

- The default Orca path and argument style is handled as a Prusa-style CLI compatibility path. If your Orca build differs, set `engine_path` and `engine_args_text` explicitly.
