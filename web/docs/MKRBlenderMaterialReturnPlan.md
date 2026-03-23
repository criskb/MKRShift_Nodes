# MKRBlenderMaterialReturnPlan

`MKRBlenderMaterialReturnPlan` builds a JSON handoff packet for the Blender add-on so generated textures can be applied back onto a Blender material slot.

## Inputs

- `material_name`
- `base_color_path`
- `normal_path`
- `roughness_path`
- `metallic_path`
- `emission_path`
- `alpha_path`
- `target_object_name`
- `target_material_slot`
- `notes`

## Outputs

- `material_return_plan_json`: Blender-facing return packet
- `manifest_line`: one-line CSV-style summary
- `summary_json`: compact counts / routing info

## Notes

- Use this after generating or refining texture maps in ComfyUI.
- The Blender add-on can read this plan and wire the referenced images onto a Principled material setup.
