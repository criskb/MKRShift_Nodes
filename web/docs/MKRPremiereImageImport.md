# MKRPremiereImageImport

Loads a Premiere still/graphic payload into ComfyUI as `IMAGE` and `MASK`.

Use it to roundtrip graphics, freeze frames, poster art, or still plates between Premiere and ComfyUI.

## Inputs

- `payload_json`
- `preferred_slot` (optional)

## Outputs

- `image`
- `mask`
- `payload_json`
- `asset_path`
- `summary_json`
