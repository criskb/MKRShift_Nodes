# MKRBlenderMaterialImport

`MKRBlenderMaterialImport` ingests an active Blender material payload from the MKRShift Blender Bridge and turns it into reusable JSON inside ComfyUI.

## Input

- `material_payload_json`: JSON copied from the Blender add-on `Copy Material Payload` action.

## Outputs

- `material_json`: normalized material payload
- `material_prompt`: short material matching prompt
- `texture_manifest_json`: normalized texture list
- `summary_json`: compact material summary

## Notes

- This is meant for bridge workflows, lookdev planning, or turning a Blender material into a ComfyUI-side material reference packet.
- Texture entries are preserved with slot names, file paths, and color space tags.
