# MKRShift Fusion 360 Addon

This scaffold targets a Fusion 360 Python add-in.

Files:

- `MKRShiftFusionBridge.py`
- `MKRShiftFusionBridge.manifest`

First-use direction:

- export view/material/body snapshots
- export image payloads for viewport or render captures
- emit packet JSON to ComfyUI-side bridge nodes
- re-import generated textures, preview sheets, or live image outputs
- submit payloads to endpoint plans
- poll endpoint jobs for live roundtrip state
