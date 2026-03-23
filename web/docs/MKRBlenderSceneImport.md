# MKRBlenderSceneImport

`MKRBlenderSceneImport` ingests a JSON payload exported by the MKRShift Blender Bridge add-on and breaks it into reusable scene, camera, and pose packets.

## Inputs

- `bridge_payload_json`: Full scene packet copied from Blender.
- `character_state_json`: Optional `MKRCharacterState` payload so the imported camera prompt can include the current character name.

## Outputs

- `scene_packet_json`: Normalized bridge packet for downstream bridge nodes.
- `camera_json`: Camera-only payload.
- `pose_json`: Pose/armature-only payload.
- `camera_prompt`: A compact camera-match prompt string.
- `summary_json`: Quick counts and warnings.

## Notes

- The expected payload schema is `mkrshift_blender_bridge_v1`.
- This first pass is file/clipboard based; a later round can add live HTTP roundtrips.
