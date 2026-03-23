# MKRShift Blender Bridge

This folder contains the Blender add-on for the first MKRShift bridge pass.

## What It Does

- Exports the active Blender camera as a JSON payload.
- Exports the selected armature pose as a JSON payload.
- Exports the active material as a JSON payload.
- Exports the active image/texture context as a JSON payload.
- Exports a combined scene packet with camera, pose, material, and frame metadata.
- Copies payloads to the clipboard or saves them to disk for `MKRBlenderSceneImport`.
- Applies a material return-plan JSON back onto a Blender material slot.
- Applies image output-plan JSON back into Blender.
- Can now submit live scene/camera/pose/material/image payloads directly to an endpoint plan and poll job status back.
- Can now load a dynamic workflow-interface JSON and build grouped host controls from it.

## Install

1. In Blender, open `Edit > Preferences > Add-ons`.
2. Click `Install...`.
3. Install the packaged zip at `blender_extension/dist/mkrshift_blender_bridge.zip`.
4. Enable `MKRShift Blender Bridge`.

After install, the bridge appears in both:
- `View3D > Sidebar > MKRShift`
- `Shader Editor > Sidebar > MKRShift`

## Rebuild The Install Zip

If you update the add-on source and need a fresh install archive:

```bash
python3 blender_extension/build_addon_zip.py
```

That rebuilds:

```text
blender_extension/dist/mkrshift_blender_bridge.zip
```

## Current Scope

- Blender add-on emits a stable `mkrshift_blender_bridge_v1` packet format.
- MKRShift bridge nodes normalize that payload inside ComfyUI.
- Material and image output-plan JSON can be built in ComfyUI and applied back inside Blender.
- Endpoint-plan driven live submit/poll is now available in the sidebar and shader bridge panels.
- `MKRAddonWorkflowInterface` JSON can now drive a dynamic Blender-side form.

## Dynamic Workflow Interface

To use a workflow-driven host form:

1. Build a workflow interface JSON from ComfyUI with `MKRAddonWorkflowInterface`.
2. Save that JSON somewhere Blender can read.
3. In the Blender `MKRShift` panel, set `Workflow Interface`.
4. Click `Load`.

The Blender panel will create grouped controls from the interface fields and include these values in live submits:

- `workflow_interface_name`
- `workflow_id`
- `workflow_inputs`
