# MKRShift Nuke Addon

This scaffold uses the Nuke plugin/gizmo direction instead of inventing a custom binary plugin up front.

Reference:

- Foundry documents `.gizmo` and plugin-folder workflows for extending Nuke:
  [Creating and Accessing Gizmos](https://learn.foundry.com/nuke/16.0/content/comp_environment/configuring_nuke/creating_sourcing_gizmos.html)

Files:

- `menu.py`
- `MKRShiftBridgePanel.py`
- `MKRShiftBridge.gizmo`

The intended first version is a panel-driven roundtrip bridge for:

- reading Comfy packet JSON
- pushing file paths back into Read nodes
- building image output and playback specs
- submitting payloads to endpoint plans
- polling job status from endpoint plans
- using `MKRShiftBridge.gizmo` as a graph-visible bridge anchor inside the script
