# AngleShift Director (v3)

## Typical flow
1. Connect an `IMAGE` input to `AngleShift`.
2. Orbit in the preview or use sliders (`rotation`, `tilt`, `zoom`).
3. Tune `Warp`, `Background`, and sheet options.
4. Enable `12-angle batch` to emit a full turntable set.

## Outputs
1. `angle_string` (`STRING`)
2. `angles_12_string` (`STRING`)
3. `shifted_image` (`IMAGE`)
4. `angles_12_batch` (`IMAGE`)
5. `angles_12_sheet` (`IMAGE`)
6. `metadata_json` (`STRING`)

## v3 behavior
- Uses `settings_json.angle` as the canonical source of angle settings.
- Still writes legacy top-level keys for old graphs.
- Metadata schema updated to `mkr_angle_shift_v3`.
- 12-view mode now varies tilt slightly for more useful review sheets.
