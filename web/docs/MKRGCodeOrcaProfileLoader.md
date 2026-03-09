# MKRGCodeOrcaProfileLoader

Loads OrcaSlicer preset bundles or exported JSON files and maps them into a printer profile plus slicer settings payload.

## Inputs

- `source_path`: File or directory containing `.orca_printer`, `.orca_filament`, `.orca_process`, `.json`, or `.zip` exports.
- `printer_match`, `filament_match`, `process_match`: Optional preset selectors by id or name.
- `selection_mode`: Chooses exact or substring matching when a selector is provided.
- `recursive`: Scans subfolders when `source_path` is a directory.

## Outputs

- `profile`: `MKR_GCODE_PROFILE` mapped from the selected Orca machine, filament, and process presets.
- `slicer_settings`: `MKR_GCODE_SLICER_SETTINGS` payload for the external slicer node.
- `bundle_json`: Counts, selected preset names, source path, and warnings.
- `summary`: Short load summary.

## Notes

- This is based on the earlier `Orca Preset` experiment from `G-code-Studio`, but implemented as a filesystem loader instead of a browser-local importer.
