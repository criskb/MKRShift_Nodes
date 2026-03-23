# MKRShift Nuke Plugin

This is the install-facing Nuke bridge package.

Expected contents:

- `menu.py`
- `MKRShiftBridgePanel.py`
- `MKRShiftBridge.gizmo`

Copy these into a folder on `NUKE_PATH`, or merge them into your existing `.nuke` pipeline package structure.

The bridge now supports:

- packet, read, image, and playback spec building
- image output spec building
- endpoint submit and poll helpers for live roundtrip workflows
- a bridge gizmo you can drop directly into the script as a visible handoff node
