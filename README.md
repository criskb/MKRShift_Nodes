<p align="center">
  <img src="assets/readme/mkrshift-nodes-banner.svg" alt="MKRShift Nodes" width="920" />
</p>

<p align="center">
  Creative direction, look development, masking, media finishing, and social planning nodes for ComfyUI.
</p>

<p align="center">
  Built for day-to-day production workflows: fast iteration, stronger previews, and practical utility nodes that reduce graph clutter.
</p>

## Overview

MKRShift Nodes is a broad ComfyUI node pack focused on image craft and workflow speed. It combines creative tools, utility nodes, custom frontend helpers, and social-planning nodes in one pack instead of splitting related tasks across multiple small installs.

## Node Areas

| Area | Example Nodes | Focus |
| --- | --- | --- |
| Direction | `MKRCharacterCustomizer`, `AngleShift`, `Aspect1X`, `AxBCompare` | Character setup, angle exploration, compare views, and framing |
| Color + Lookdev | `xLUT`, `xLUTOutput`, `x1ColorWheels`, `x1Curves`, `x1PaletteMap` | LUT authoring, grading, color matching, and look building |
| Image Processing | `x1Bloom`, `x1Film`, `x1Stylize`, `x1LocalContrast`, `x1SharpenPro` | Finishing, texture, stylization, and polish |
| Mask + Utility | `x1MaskGen`, `AdvResize`, `MKRImageSplitGrid`, `MKRImageCombineGrid`, `xShader`, `x1DenoiseDetail` | Mask generation, resize work, tiled image workflows, shader utilities, and cleanup |
| PreSave + Media | `MKRPreSave`, `MKRPresaveVideo`, `MKRPresaveAudio`, `MKRMuxVideoAudio`, `MKRTrimVideoByTime` | Preview-first export helpers plus audio/video utility work |
| Social Planning | `MKRshiftSocialPackBuilder`, `MKRshiftSocialPackAssets`, `MKRshiftSocialPromptAtIndex`, `MKRshiftSocialPackCatalog` | Pack-driven captions, prompts, scheduling, and social asset planning |
| G-code | `MKRGCodePrinterProfile`, `MKRGCodeOrcaProfileLoader`, `MKRGCodeLoadMeshModel`, `MKRGCodeHeightmapPlate`, `MKRGCodeSpiralVase`, `MKRGCodePlanAnalyzer`, `MKRGCodeBedMeshCompensate`, `MKRGCodeCalibrationTower`, `MKRGCodeConditionalInjector`, `MKRGCodePreview`, `MKRGCodeExternalSlicer`, `MKRGCodeExport` | 3D-print printer profiles, Orca preset import, mesh/model loading, generators, plan analysis, bed compensation, calibration macros, preview, external slicing, and direct `.gcode` export |
| Studio Review + Delivery | `MKRStudioSlate`, `MKRStudioReviewFrame`, `MKRStudioReviewBurnIn`, `MKRStudioCompareBoard`, `MKRStudioContactSheet`, `MKRStudioDeliveryPlan` | Branded slates, quick burn-ins, compare boards, review frames, contact sheets, and naming/handoff planning for internal or client-facing review |

## Frontend Extensions

This pack ships custom `WEB_DIRECTORY` extensions for nodes that benefit from a better UI:

- `MKRCharacterCustomizer`
- `AngleShift`
- `AxBCompare`
- `MKRPreSave`
- `MKRPresaveVideo`
- `MKRPresaveAudio`
- `MKRshiftSocialPackBuilder`
- `xLUT`
- `x1MaskGen`

Markdown help pages for these nodes live in `web/docs/`.

## Installation

1. Clone or copy this folder into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI.
3. Install `ffmpeg` if you plan to use the video/audio export and muxing nodes.
4. Install `OrcaSlicer`, `PrusaSlicer`, or `CuraEngine` if you plan to use the external G-code slicer node.

## Notes

- `pyproject.toml` is included so the pack has a stable package identity.
- Repository URL, license, and `PublisherId` are intentionally still unset until real publishing details exist.
- The code uses relative imports and does not rely on the install folder matching the repo name.
- Package internals are split by concern under `nodes/` and `lib/`, with legacy root import aliases preserved for backward compatibility.
- The `G-code` category is inspired by the earlier `G-code-Studio` experiment, but implemented here as ComfyUI-native nodes.
- The external slicer node can run in `dry_run` mode to validate commands/config text even when a slicer CLI is not installed yet.
- Social pack presets are loaded from `packs/`.
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
- social and mask feature regressions
- studio review node coverage and legacy import aliases
