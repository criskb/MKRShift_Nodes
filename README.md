<p align="center">
  <img src="assets/readme/mkrshift-nodes-banner.svg" alt="MKRShift Nodes" width="920" />
</p>

<p align="center">
  Creative direction, look development, masking, media finishing, and publish/output nodes for ComfyUI.
</p>

<p align="center">
  Built for day-to-day production workflows: fast iteration, stronger previews, and practical utility nodes that reduce graph clutter.
</p>

## Overview

MKRShift Nodes is a broad ComfyUI node pack focused on image craft and workflow speed. It combines creative tools, utility nodes, custom frontend helpers, and publish/output nodes in one pack instead of splitting related tasks across multiple small installs.

## Node Areas

| Area | Example Nodes | Focus |
| --- | --- | --- |
| Direction | `MKRCharacterCustomizer`, `MKRCharacterState`, `MKROutfitSet`, `MKRPoseStudio`, `AngleShift`, `Aspect1X`, `AxBCompare` | Character setup, persistent identity state, outfit variation, 3D pose blockout, angle exploration, compare views, and framing |
| Blender Bridge | `MKRBlenderSceneImport`, `MKRBlenderCameraShot`, `MKRBlenderImageImport`, `MKRBlenderImageOutputPlan`, `MKRBlenderMaterialImport`, `MKRBlenderMaterialReturnPlan`, `MKRBlenderReturnPlan` | Import Blender camera, armature, image, and material payloads, derive shot/material metadata, and build return plans for roundtrip workflows |
| Host Addons | `MKRBlenderSceneImport`, `MKRTouchDesignerImport`, `MKRTiXLImport`, `MKRNukeScriptImport`, `MKRPhotoshopDocumentImport`, `MKRAfterEffectsCompImport`, `MKRPremiereSequenceImport`, `MKRAffinityDocumentImport`, `MKRAffinityPhotoshopPluginPlan`, `MKRFusion360SceneImport`, `MKRFusion360ImageImport`, `MKRMayaSceneImport`, `MKRMayaImageImport`, `MKRNodeExtensionBuilderPlan` | Packet-first host integrations with per-application addon scaffolds under `addons/` and matching ComfyUI nodes under `Addons/...`, including image/texture handoff lanes for the 3D hosts, an Affinity route based on Photoshop-plugin compatibility, plus extension-builder manifest planning with optional expert JSON for repository/license metadata and skill-driven packaging command output |
| Network Transport | `MKRAddonEndpointPlan`, `MKROSCMessagePlan`, `MKRNDIStreamPlan`, `MKRSpoutSenderPlan`, `MKRSyphonSenderPlan`, `MKRTCPBridgePlan`, `MKRHTTPWebhookPlan`, `MKRWatchFolderPlan`, `MKRWebSocketBridgePlan` | Reusable endpoint and transport plans for host add-ons, including HTTP endpoint jobs, OSC, NDI, Spout, Syphon, TCP, watch-folder, and WebSocket workflows |
| Surface + Material | `x1PreviewMaterial`, `x1PBRPack`, `x1ClearcoatMap`, `x1ClearcoatRoughnessMap`, `x1EdgeWearMask`, `x1TextureDetileBlend` | Practical PBR map derivation, material preview, packing, wear masking, and anti-tiling texture cleanup |
| Color + Lookdev | `xLUT`, `xLUTOutput`, `x1ColorWheels`, `x1Curves`, `x1ColorWarpHueSat`, `x1ColorWarpChromaLuma`, `x1PaletteMap` | LUT authoring, grading, color matching, mesh-based warping, and look building |
| Image Processing | `x1Bloom`, `x1Film`, `x1Stylize`, `x1LocalContrast`, `x1SharpenPro`, `x1LightWrapComposite`, `x1EdgeAberration` | Finishing, texture, stylization, polish, and practical comp/VFX passes |
| Inspect + Review | `AxBCompare`, `MKRBatchCollagePreview`, `MKRStudioReviewFrame`, `MKRStudioCompareBoard` | Fast side-by-side checks, labeled batch sheets, and review-ready boards |
| Mask + Utility | `x1MaskGen`, `AdvResize`, `MKRImageSplitGrid`, `MKRImageCombineGrid`, `xShader`, `x1DenoiseDetail` | Mask generation, resize work, tiled image workflows, shader utilities, and cleanup |
| PreSave + Media | `MKRPreSave`, `MKRPresaveVideo`, `MKRPresaveAudio`, `MKRMuxVideoAudio`, `MKRTrimVideoByTime` | Preview-first export helpers plus audio/video utility work |
| Publish + Output | `MKRPublishPromoFrame`, `MKRPublishEndCard`, `MKRPublishAssetManifest`, `MKRPublishManifestAtIndex`, `MKRPublishCopyDeck`, `MKRPublishCopyAtIndex` | Promo-card framing, end cards, asset manifests, and copy extraction helpers for real export/delivery work |
| G-code | `MKRGCodePrinterProfile`, `MKRGCodeOrcaProfileLoader`, `MKRGCodeLoadMeshModel`, `MKRGCodeHeightmapPlate`, `MKRGCodeSpiralVase`, `MKRGCodePlanAnalyzer`, `MKRGCodeBedMeshCompensate`, `MKRGCodeCalibrationTower`, `MKRGCodeConditionalInjector`, `MKRGCodePreview`, `MKRGCodeExternalSlicer`, `MKRGCodeExport` | 3D-print printer profiles, Orca preset import, mesh/model loading, generators, plan analysis, bed compensation, calibration macros, preview, external slicing, and direct `.gcode` export |
| Studio Review + Delivery | `MKRStudioSlate`, `MKRStudioReviewFrame`, `MKRStudioReviewBurnIn`, `MKRStudioCompareBoard`, `MKRStudioContactSheet`, `MKRStudioDeliveryPlan` | Branded slates, quick burn-ins, compare boards, review frames, contact sheets, and naming/handoff planning for internal or client-facing review |

## Frontend Extensions

This pack ships custom `WEB_DIRECTORY` extensions for nodes that benefit from a better UI:

- `MKRCharacterCustomizer`
- `MKRCharacterState`
- `AngleShift`
- `MKRPoseStudio`
- `AxBCompare`
- `MKRPreSave`
- `MKRPresaveVideo`
- `MKRPresaveAudio`
- `MKRPublishPromoFrame`
- `x1ColorWheels`
- `x1Curves`
- `x1ColorWarpHueSat`
- `x1ColorWarpChromaLuma`
- `xLUT`
- `x1MaskGen`

Markdown help pages for these nodes live in `web/docs/`.

If you publish/maintain a GitHub wiki, use `web/docs/Home.md` as the landing page and `web/docs/_Sidebar.md` for wiki navigation. Those pages are organized to mirror the current in-app taxonomy, including the refreshed Surface and Inspect branches.

The Blender add-on scaffold for the bridge lives in `blender_extension/mkrshift_blender_bridge/`.

This pack now also exposes an initial V3 schema companion lane through:

- [v3_extension.py](/Users/crisbjorndal/ComfyUI/custom_nodes/MKRShift_Nodes/v3_extension.py)

That V3 lane currently focuses on the newer addon/network transport nodes where V3 schema definitions are low-risk and useful.

Additional host integration scaffolds now live in `addons/`:

- `addons/blender/`
- `addons/touchdesigner/`
- `addons/tixl/`
- `addons/nuke/`
- `addons/photoshop/`
- `addons/after_effects/`
- `addons/premiere_pro/`
- `addons/affinity/`
- `addons/fusion360/`
- `addons/maya/`

Subgraph blueprints for the addon/network lane live in `subgraphs/`.

## Installation

1. Clone or copy this folder into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI.
3. Install `ffmpeg` if you plan to use the video/audio export and muxing nodes.
4. Install `OrcaSlicer`, `PrusaSlicer`, or `CuraEngine` if you plan to use the external G-code slicer node.

## Extension Builder Quickstart

This repo now includes a starter builder config at `extension.builder.json` and a minimal example workflow at `example_workflows/mkrshift_extension_builder_plan.json` for `MKRNodeExtensionBuilderPlan`.

Suggested build command:

```bash
python3 /opt/codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo criskb/comfyui-node-extension-builder --path . --name comfyui-node-extension-builder
```

Then write the `builder_manifest_json` output from `MKRNodeExtensionBuilderPlan` to `extension.builder.json` and run your preferred builder CLI (or pass `builder_cli_command` in `advanced_options_json`).

## Notes

- `pyproject.toml` is included so the pack has a stable package identity.
- `pyproject.toml` now includes repository and Comfy registry metadata for packaging/distribution readiness.
- The code uses relative imports and does not rely on the install folder matching the repo name.
- Package internals are split by concern under `nodes/` and `lib/`, with legacy root import aliases preserved for backward compatibility.
- The `G-code` category is inspired by the earlier `G-code-Studio` experiment, but implemented here as ComfyUI-native nodes.
- The external slicer node can run in `dry_run` mode to validate commands/config text even when a slicer CLI is not installed yet.
- G-code post-processing nodes expect exported layer comments for the strongest results, so keep `include_comments` enabled on `MKRGCodeExport` when you plan to inject calibration or conditional macros later in the graph.

## Verification

Run the test suite with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The current checks cover:

- pack importability
- exported node metadata
- `WEB_DIRECTORY` presence
- docs and packaging assets
- publish/output and mask feature regressions
- studio review node coverage and legacy import aliases

This extension/addon was created using Codex skill designed by Cris K B https://github.com/criskb/comfyui-node-extension-builder
