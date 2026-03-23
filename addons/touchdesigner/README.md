# MKRShift TouchDesigner Addon

This addon scaffold is based on the official TouchDesigner component-extension workflow.

Reference:

- TouchDesigner officially recommends using the Component Editor to create Python extensions for custom components:
  [Derivative Extensions](https://derivative.ca/UserGuide/Extensions)

Files:

- `MKRShiftBridgeExt.py`

Recommended host shape:

- a bridge `baseCOMP` or `.tox`
- one DAT storing packet JSON
- one DAT storing transport plan JSON
- one extension class for payload import/export
- optional TOP/CHOP/parameter bindings for live use

Suggested ComfyUI-side pairings:

- `MKRTouchDesignerImport`
- `MKRTouchDesignerFramePlan`
- `MKROSCMessagePlan`
- `MKRNDIStreamPlan`
- `MKRSpoutSenderPlan`
- `MKRWebSocketBridgePlan`
