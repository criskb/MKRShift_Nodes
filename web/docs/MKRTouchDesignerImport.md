# MKRTouchDesignerImport

`MKRTouchDesignerImport` normalizes a TouchDesigner bridge packet into stable JSON blocks for downstream ComfyUI work.

Outputs:

- `td_packet_json`
- `controls_json`
- `texture_manifest_json`
- `summary_json`

Use this after a TouchDesigner `.tox` / extension bridge emits a packet from TOPs, controls, or transport state.
