# MKRGCodeConditionalInjector

Injects custom G-code blocks at the start, on matching layer changes, or at the end of an exported file.

## Inputs

- `plan`: Source plan used for layer and Z-aware rule matching.
- `gcode_text`: Exported G-code to modify.
- `rules_json`: JSON rule list describing when and what to inject.

## Outputs

- `gcode_text`: Modified G-code with your injected blocks.
- `applied_json`: Applied rule events and warnings.
- `summary`: Short summary of the injection pass.

## Rule Format

```json
[
  {"label":"announce-start","when":"start","inject":"M117 START {mode}"},
  {"label":"fan-boost","when":"layer_change","layer_min":2,"every_layers":2,"inject":"M106 S255"},
  {"label":"announce-end","when":"end","inject":"M118 DONE {mode}"}
]
```

Layer-change rules support `layer`, `layer_min`, `layer_max`, `every_layers`, `z_min`, `z_max`, and `mode` filters. Templates can reference `{layer}`, `{z}`, and `{mode}`.
