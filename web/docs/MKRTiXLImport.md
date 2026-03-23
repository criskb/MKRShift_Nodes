# MKRTiXLImport

`MKRTiXLImport` normalizes a TiXL / Tooll bridge packet into layer, timing, and summary JSON.

Outputs:

- `tixl_packet_json`
- `layer_manifest_json`
- `timing_json`
- `summary_json`

This is designed for packet-first TiXL workflows where a host operator or tool exports graph/layer state into ComfyUI.
