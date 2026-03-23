# MKRShift Plugins

This folder is the install-facing home for host plugins and plugin helpers that sit beside ComfyUI.

## What Is Here

- `common/`
  - shared endpoint helpers for Python, JS/UXP, JSX, and C#
- `touchdesigner/`
  - TouchDesigner extension bridge package
- `tixl/`
  - TiXL / Tooll C# operator bridge package
- `nuke/`
  - Nuke Python panel/menu bridge package
- `photoshop/`
  - Photoshop UXP bridge package
- `after_effects/`
  - After Effects ScriptUI bridge package
- `premiere_pro/`
  - Premiere UXP bridge package
- `affinity/`
  - Affinity bridge notes and Photoshop-plugin route package notes
- `fusion360/`
  - Fusion 360 Python add-in bridge package
- `maya/`
  - Maya Python plugin/script bridge package
- `blender/`
  - Blender install notes and handoff to the packaged add-on zip

## Quick Install

Run:

```bash
python3 /Users/crisbjorndal/ComfyUI/custom_nodes/MKRShift_Nodes/plugins/install_plugins.py
```

This opens a small installer window where you can:

- select which host plugins to install
- review the suggested install folder per host
- override the folder if your setup is custom
- copy the plugin/package into the chosen plugin directory

The installer is conservative:

- it copies files, it does not patch the host app itself
- it will create the destination folder if needed
- it writes into a timestamped `mkrshift_*` folder when a host expects a folder-style package

## Install Notes By Host

### Blender

- Uses the packaged zip from:
  - `/Users/crisbjorndal/ComfyUI/custom_nodes/MKRShift_Nodes/blender_extension/dist/mkrshift_blender_bridge.zip`
- Install from Blender:
  - `Edit > Preferences > Add-ons > Install...`

### TouchDesigner

- Copy `MKRShiftBridgeExt.py` into your bridge COMP / project support area.
- Add it as a component extension on the bridge COMP.

### TiXL

- Use the C# operator scaffold as a starting point inside your TiXL project/plugin workflow.

### Nuke

- Copy the Nuke folder contents into a directory on `NUKE_PATH`, or merge the files into your existing `.nuke` package structure.

### Photoshop / Premiere Pro

- These are UXP-style scaffolds.
- Copy into your UXP development/plugin location and load with your normal Adobe development workflow.

### After Effects

- Copy the JSX file into your ScriptUI Panels or scripts location, depending on how you want to load it.

### Affinity

- Current best route is still packet exchange plus Photoshop-plugin compatibility where supported.
- Use this together with the ComfyUI nodes:
  - `MKRAffinityDocumentImport`
  - `MKRAffinityExportPlan`
  - `MKRAffinityPhotoshopPluginPlan`

### Fusion 360

- Copy the add-in folder into your Fusion 360 add-ins location and register/load it there.

### Maya

- Copy the Maya plugin/script scaffold into your Maya scripts/plugins area and source/load it from your pipeline startup.

## ComfyUI Side

These plugin folders pair with the ComfyUI nodes under:

- `MKRShift Nodes/Addons/...`
- especially `MKRShift Nodes/Addons/Network`

Useful network nodes include:

- `MKRAddonEndpointPlan`
- `MKROSCMessagePlan`
- `MKRNDIStreamPlan`
- `MKRSpoutSenderPlan`
- `MKRSyphonSenderPlan`
- `MKRTCPBridgePlan`
- `MKRHTTPWebhookPlan`
- `MKRWatchFolderPlan`
- `MKRWebSocketBridgePlan`

## Notes

- `addons/` remains the canonical development tree for host integrations.
- `plugins/` is the install-oriented surface and legacy compatibility lane.
