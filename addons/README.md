# MKRShift Host Addons

This is the canonical home for host-application integrations that sit beside ComfyUI.

Current targets:

- `common/`
- `blender/`
- `touchdesigner/`
- `tixl/`
- `nuke/`
- `photoshop/`
- `after_effects/`
- `premiere_pro/`
- `affinity/`
- `fusion360/`
- `maya/`

The structure is intentionally host-first:

- each subfolder contains the bridge package or host integration surface for one DCC/app
- `common/` contains shared endpoint/transport helper contracts for host add-ons
- ComfyUI-side packet nodes live under `nodes/`
- shared packet schema helpers live under `lib/`

Legacy compatibility note:

- the existing Blender packaging folder under `blender_extension/` remains in place so current install/build paths do not break
- new host integrations should be added here under `addons/`
- the older `plugins/` folder remains the install-facing compatibility lane, while `addons/` stays the canonical development tree
