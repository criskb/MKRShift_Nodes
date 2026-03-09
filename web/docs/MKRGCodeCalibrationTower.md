# MKRGCodeCalibrationTower

Injects stepped temperature, flow, speed, or fan commands into exported G-code at layer or Z intervals.

## Inputs

- `plan`: Source plan used to resolve layer heights.
- `gcode_text`: Exported G-code, typically from `MKRGCodeExport`.
- `axis`: Steps by actual Z height or by layer index.
- `target`: Which printer setting to change.
- `start_value`, `step_value`, `every`, `clamp_min`, `clamp_max`: Calibration step controls.
- `only_on_change`: Avoids repeating the same command on consecutive layers.

## Outputs

- `gcode_text`: Modified G-code with calibration commands injected after layer markers.
- `steps_json`: Structured list of injected commands and any warnings.
- `summary`: Short summary of the injected calibration steps.

## Notes

- Keep `include_comments` enabled in `MKRGCodeExport` so the node can target `; LAYER:` markers reliably.
