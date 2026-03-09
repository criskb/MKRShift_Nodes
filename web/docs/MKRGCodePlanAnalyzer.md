# MKRGCodePlanAnalyzer

Analyzes a `MKR_GCODE_PLAN` for printability, cost, material use, and common risk signals.

## Inputs

- `plan`: G-code plan from one of the generator nodes.
- `profile` (optional): Printer profile used for bed-fit and filament calculations.
- `max_volumetric_flow_mm3_s`: Warns when planned extrusion exceeds your flow ceiling.
- `min_feature_mm`: Flags very short extrude segments that may not print reliably.
- `min_layer_time_s`: Warns about layers that are likely to print too fast.
- `warn_travel_ratio_percent`: Flags plans with unusually high travel overhead.
- `filament_price_per_kg`, `material_density_g_cm3`, `printer_wattage_w`, `electricity_price_per_kwh`: Cost and usage assumptions.

## Outputs

- `plan`: Pass-through plan for continued graph use.
- `analysis_json`: Full report with layer summaries, flow estimate, bed fit, material estimate, and cost estimate.
- `warnings_json`: Flat warning list for routing or display.
- `summary`: Short human-readable analysis summary.

## Notes

- This node combines the intent of the old `failure-analyzer` and `print-time-cost-estimator` experiments into one ComfyUI-native report node.
