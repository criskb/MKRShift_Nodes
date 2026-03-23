# MKRAfterEffectsImageImport

Loads an After Effects still/plate payload into ComfyUI as `IMAGE` and `MASK`.

Use it for frame touch-up, stylization, plate cleanup, or any roundtrip where AE is the host and ComfyUI is the image processor.

## Inputs

- `payload_json`
- `preferred_slot` (optional)

## Outputs

- `image`
- `mask`
- `payload_json`
- `asset_path`
- `summary_json`
