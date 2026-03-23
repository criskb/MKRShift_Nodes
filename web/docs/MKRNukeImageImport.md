# MKRNukeImageImport

Loads a Nuke image/read payload into ComfyUI as `IMAGE` and `MASK`.

Use this when a Nuke-side bridge packet includes read nodes, plates, or rendered stills and you want to bring that image into a graph for paintover, texture work, cleanup, or lookdev.

## Inputs

- `payload_json`
- `preferred_slot` (optional)

## Outputs

- `image`
- `mask`
- `payload_json`
- `asset_path`
- `summary_json`
