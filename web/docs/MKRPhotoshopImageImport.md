# MKRPhotoshopImageImport

Loads a Photoshop layer/image payload into ComfyUI as `IMAGE` and `MASK`.

This is useful for layer roundtrips, retouch workflows, texture paintovers, and plugin-driven document exchange.

## Inputs

- `payload_json`
- `preferred_slot` (optional)

## Outputs

- `image`
- `mask`
- `payload_json`
- `asset_path`
- `summary_json`
