# MKR Shift v3

## Included nodes
- `MKRCharacterCustomizer` (`MKR • Character Direction Studio`)
- `AngleShift` (`MKR • AngleShift Director`)

## Character Direction Studio

### What changed in v3
- Full panel redesign with shared component system and realtime 3D preview.
- Unified settings schema (`schema_version: 3`) with legacy key mirrors for old workflows.
- Stronger prompt composition and richer metadata output.

### Inputs
Required:
- `settings_json`
- `model_path`
- `capture_w`
- `capture_h`

Optional:
- `subject_prompt`
- `outfit_prompt`
- `style_preset`
- `shot_type`
- `mood`
- `add_quality_tags`
- `negative_prompt_base`

### Outputs
Backward-compatible first outputs are unchanged:
1. `image` (`IMAGE`)
2. `camera_desc` (`STRING`)
3. `light_desc` (`STRING`)
4. `settings_out` (`STRING`)

Extended outputs:
5. `positive_prompt` (`STRING`)
6. `negative_prompt` (`STRING`)
7. `director_prompt` (`STRING`)
8. `pose_guide` (`IMAGE`)
9. `metadata_json` (`STRING`)

### `settings_json` shape (v3)
```json
{
  "schema_version": 3,
  "camera": { "pos": [0.0, 2.0, 1.4] },
  "light": { "pos": [1.2, 2.2, 2.0] },
  "gizmos": {
    "camera": { "mode": "procedural", "glb_url": "" },
    "light": { "mode": "procedural", "glb_url": "" }
  },
  "angle": {
    "rotation": 45,
    "tilt": -30,
    "zoom": 0,
    "strength": 0.85,
    "background_mode": "blur",
    "sheet_columns": 4,
    "label_overlay": true,
    "multi12": false
  },
  "params": {}
}
```

Legacy top-level angle keys (`rotation`, `tilt`, `zoom`, etc.) are still mirrored automatically for compatibility.

### Custom GLB gizmos
Use extension paths like:
- `/extensions/<your_extension>/assets/camera_gizmo.glb`
- `/extensions/<your_extension>/assets/light_gizmo.glb`
