import sys
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

import MKRShift_Nodes as pack  # noqa: E402


class PackAssetTests(unittest.TestCase):
    def test_readme_and_pyproject_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "README.md").is_file())
        self.assertTrue((REPO_ROOT / "pyproject.toml").is_file())
        self.assertTrue((REPO_ROOT / "v3_extension.py").is_file())
        self.assertTrue((REPO_ROOT / "subgraphs").is_dir())

    def test_pyproject_has_basic_identity(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib not available")

        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data.get("project", {})
        comfy = data.get("tool", {}).get("comfy", {})

        self.assertEqual(project.get("name"), "mkrshift-nodes")
        self.assertEqual(project.get("readme"), "README.md")
        self.assertEqual(project.get("requires-python"), ">=3.10")
        self.assertIsInstance(project.get("version"), str)
        self.assertTrue(project.get("version"))
        self.assertEqual(comfy.get("DisplayName"), "MKRShift Nodes")
        self.assertIn("v3", project.get("optional-dependencies", {}))

    def test_help_docs_exist_for_documented_nodes(self) -> None:
        docs_root = REPO_ROOT / "web" / "docs"
        expected = {
            "AngleShift.md",
            "Aspect1X.md",
            "Aspect1XBatch.md",
            "MKRCharacterCustomizer.md",
            "MKRCharacterState.md",
            "MKROutfitSet.md",
            "MKRCLIPTextEncodePrompt.md",
            "MKRAddonWorkflowInterface.md",
            "MKRJSONDiff.md",
            "MKRAddonStats.md",
            "MKRBlenderSceneImport.md",
            "MKRBlenderCameraShot.md",
            "MKRBlenderImageImport.md",
            "MKRBlenderImageOutputPlan.md",
            "MKRBlenderImageOutput.md",
            "MKRBlenderMaterialImport.md",
            "MKRBlenderMaterialReturnPlan.md",
            "MKRBlenderReturnPlan.md",
            "MKRBlenderReturnOutput.md",
            "MKRTouchDesignerImport.md",
            "MKRTouchDesignerFramePlan.md",
            "MKRTiXLImport.md",
            "MKRTiXLFramePlan.md",
            "MKROSCMessagePlan.md",
            "MKRAddonEndpointPlan.md",
            "MKRNDIStreamPlan.md",
            "MKRSpoutSenderPlan.md",
            "MKRSyphonSenderPlan.md",
            "MKRTCPBridgePlan.md",
            "MKRHTTPWebhookPlan.md",
            "MKRWatchFolderPlan.md",
            "MKRWebSocketBridgePlan.md",
            "MKRAddonEndpointSubmit.md",
            "MKRAddonEndpointPoll.md",
            "MKRHTTPWebhookSend.md",
            "MKRTCPBridgeSend.md",
            "MKROSCSend.md",
            "MKRWatchFolderWrite.md",
            "MKRNukeScriptImport.md",
            "MKRNukeReadPlan.md",
            "MKRNukeReadOutput.md",
            "MKRNukeImageImport.md",
            "MKRNukeImageOutputPlan.md",
            "MKRNukeImageOutput.md",
            "MKRPhotoshopDocumentImport.md",
            "MKRPhotoshopExportPlan.md",
            "MKRPhotoshopExportOutput.md",
            "MKRPhotoshopImageImport.md",
            "MKRPhotoshopImageOutputPlan.md",
            "MKRPhotoshopImageOutput.md",
            "MKRAfterEffectsCompImport.md",
            "MKRAfterEffectsRenderPlan.md",
            "MKRAfterEffectsRenderOutput.md",
            "MKRAfterEffectsImageImport.md",
            "MKRAfterEffectsImageOutputPlan.md",
            "MKRAfterEffectsImageOutput.md",
            "MKRPremiereSequenceImport.md",
            "MKRPremiereExportPlan.md",
            "MKRPremiereExportOutput.md",
            "MKRPremiereImageImport.md",
            "MKRPremiereImageOutputPlan.md",
            "MKRPremiereImageOutput.md",
            "MKRAffinityDocumentImport.md",
            "MKRAffinityExportPlan.md",
            "MKRAffinityExportOutput.md",
            "MKRAffinityPhotoshopPluginPlan.md",
            "MKRFusion360SceneImport.md",
            "MKRFusion360TexturePlan.md",
            "MKRFusion360TextureOutput.md",
            "MKRFusion360ImageImport.md",
            "MKRFusion360ImageOutputPlan.md",
            "MKRFusion360ImageOutput.md",
            "MKRMayaSceneImport.md",
            "MKRMayaMaterialPlan.md",
            "MKRMayaMaterialOutput.md",
            "MKRMayaImageImport.md",
            "MKRMayaImageOutputPlan.md",
            "MKRMayaImageOutput.md",
            "MKRPoseStudio.md",
            "MKRBatchCollagePreview.md",
            "MKRPreSave.md",
            "MKRPresaveVideo.md",
            "MKRPresaveAudio.md",
            "MKRGCodePrinterProfile.md",
            "MKRGCodeOrcaProfileLoader.md",
            "MKRGCodeLoadMeshModel.md",
            "MKRGCodeHeightmapPlate.md",
            "MKRGCodeSpiralVase.md",
            "MKRGCodePlanAnalyzer.md",
            "MKRGCodeBedMeshCompensate.md",
            "MKRGCodeCalibrationTower.md",
            "MKRGCodeConditionalInjector.md",
            "MKRGCodePreview.md",
            "MKRGCodeExternalSlicer.md",
            "MKRGCodeExport.md",
            "MKRImageSplitGrid.md",
            "MKRImageCombineGrid.md",
            "MKRStudioSlate.md",
            "MKRStudioReviewFrame.md",
            "MKRStudioReviewBurnIn.md",
            "MKRStudioCompareBoard.md",
            "MKRStudioContactSheet.md",
            "MKRStudioDeliveryPlan.md",
            "MKRStudioSelectionSet.md",
            "MKRStudioReviewNotes.md",
            "MKRStudioDeliverySheet.md",
            "MKRPublishPromoFrame.md",
            "MKRPublishEndCard.md",
            "MKRPublishAssetManifest.md",
            "MKRPublishManifestAtIndex.md",
            "MKRPublishCopyDeck.md",
            "MKRPublishCopyAtIndex.md",
            "MKRBatchDifferencePreview.md",
            "MKRFacePerformanceEyeMotion.md",
            "MKRFacePerformanceLipRefine.md",
            "MKRFacePerformanceRigBuildNeutral.md",
            "MKRFacePerformanceRigApplyDeltas.md",
            "MKRFacePerformancePoseMerge.md",
            "MKRFacePerformanceEvaluate.md",
            "xLUT.md",
            "xLUTOutput.md",
            "x1MaskGen.md",
            "x1Heatmap.md",
            "x1Heightmap.md",
            "x1RoughnessMap.md",
            "x1SpecularMap.md",
            "x1TextureDelight.md",
            "x1TextureAlbedoSafe.md",
            "x1TextureDetileBlend.md",
            "x1TextureMacroVariation.md",
            "x1TextureNoiseField.md",
            "x1TextureCellPattern.md",
            "x1TextureHexTiles.md",
            "x1TextureStrata.md",
            "x1TextureWeavePattern.md",
            "x1MetalnessMap.md",
            "x1CavityMap.md",
            "x1AnisotropyMap.md",
            "x1ColorRegionMask.md",
            "x1OpacityMap.md",
            "x1ClearcoatMap.md",
            "x1ClearcoatRoughnessMap.md",
            "x1SheenMap.md",
            "x1TransmissionMap.md",
            "x1ThicknessMap.md",
            "x1IridescenceMap.md",
            "x1ScalarMapAdjust.md",
            "x1EmissiveMap.md",
            "x1EdgeWearMask.md",
            "x1NormalMap.md",
            "x1PBRPack.md",
            "x1PreviewMaterial.md",
            "x1ChannelPack.md",
            "x1ChannelBreakout.md",
            "x1NormalBlend.md",
            "x1CurvatureFromNormal.md",
            "x1UVCheckerOverlay.md",
            "x1SlopeMaskFromNormal.md",
            "x1AOFromHeight.md",
            "x1IDMapQuantize.md",
            "x1IDMaskExtract.md",
            "x1NormalTweak.md",
            "x1TextureOffset.md",
            "x1TextureSeamless.md",
            "x1TextureTilePreview.md",
            "x1TextureEdgePad.md",
            "x1AnamorphicStreaks.md",
            "x1HeatHaze.md",
            "x1LensDirtBloom.md",
            "x1ShockwaveDistort.md",
            "x1LightWrapComposite.md",
            "x1EdgeAberration.md",
            "MKRLayerStackComposite.md",
            "AxBCompare.md",
        }
        existing = {path.name for path in docs_root.glob("*.md")}
        self.assertTrue(expected.issubset(existing))

    def test_documented_nodes_are_exported(self) -> None:
        documented_nodes = {
            "AngleShift",
            "Aspect1X",
            "Aspect1XBatch",
            "MKRCharacterCustomizer",
            "MKRCharacterState",
            "MKROutfitSet",
            "MKRAddonWorkflowInterface",
            "MKRJSONDiff",
            "MKRAddonStats",
            "MKRBlenderSceneImport",
            "MKRBlenderCameraShot",
            "MKRBlenderImageImport",
            "MKRBlenderImageOutputPlan",
            "MKRBlenderImageOutput",
            "MKRBlenderMaterialImport",
            "MKRBlenderMaterialReturnPlan",
            "MKRBlenderReturnPlan",
            "MKRBlenderReturnOutput",
            "MKRTouchDesignerImport",
            "MKRTouchDesignerFramePlan",
            "MKRTiXLImport",
            "MKRTiXLFramePlan",
            "MKROSCMessagePlan",
            "MKRAddonEndpointPlan",
            "MKRNDIStreamPlan",
            "MKRSpoutSenderPlan",
            "MKRSyphonSenderPlan",
            "MKRTCPBridgePlan",
            "MKRHTTPWebhookPlan",
            "MKRWatchFolderPlan",
            "MKRWebSocketBridgePlan",
            "MKRAddonEndpointSubmit",
            "MKRAddonEndpointPoll",
            "MKRHTTPWebhookSend",
            "MKRTCPBridgeSend",
            "MKROSCSend",
            "MKRWatchFolderWrite",
            "MKRNukeScriptImport",
            "MKRNukeReadPlan",
            "MKRNukeReadOutput",
            "MKRNukeImageImport",
            "MKRNukeImageOutputPlan",
            "MKRNukeImageOutput",
            "MKRPhotoshopDocumentImport",
            "MKRPhotoshopExportPlan",
            "MKRPhotoshopExportOutput",
            "MKRPhotoshopImageImport",
            "MKRPhotoshopImageOutputPlan",
            "MKRPhotoshopImageOutput",
            "MKRAfterEffectsCompImport",
            "MKRAfterEffectsRenderPlan",
            "MKRAfterEffectsRenderOutput",
            "MKRAfterEffectsImageImport",
            "MKRAfterEffectsImageOutputPlan",
            "MKRAfterEffectsImageOutput",
            "MKRPremiereSequenceImport",
            "MKRPremiereExportPlan",
            "MKRPremiereExportOutput",
            "MKRPremiereImageImport",
            "MKRPremiereImageOutputPlan",
            "MKRPremiereImageOutput",
            "MKRAffinityDocumentImport",
            "MKRAffinityExportPlan",
            "MKRAffinityExportOutput",
            "MKRAffinityPhotoshopPluginPlan",
            "MKRFusion360SceneImport",
            "MKRFusion360TexturePlan",
            "MKRFusion360TextureOutput",
            "MKRFusion360ImageImport",
            "MKRFusion360ImageOutputPlan",
            "MKRFusion360ImageOutput",
            "MKRMayaSceneImport",
            "MKRMayaMaterialPlan",
            "MKRMayaMaterialOutput",
            "MKRMayaImageImport",
            "MKRMayaImageOutputPlan",
            "MKRMayaImageOutput",
            "MKRPoseStudio",
            "MKRBatchCollagePreview",
            "MKRPreSave",
            "MKRPresaveVideo",
            "MKRPresaveAudio",
            "MKRGCodePrinterProfile",
            "MKRGCodeOrcaProfileLoader",
            "MKRGCodeLoadMeshModel",
            "MKRGCodeHeightmapPlate",
            "MKRGCodeSpiralVase",
            "MKRGCodePlanAnalyzer",
            "MKRGCodeBedMeshCompensate",
            "MKRGCodeCalibrationTower",
            "MKRGCodeConditionalInjector",
            "MKRGCodePreview",
            "MKRGCodeExternalSlicer",
            "MKRGCodeExport",
            "MKRImageSplitGrid",
            "MKRImageCombineGrid",
            "MKRStudioSlate",
            "MKRStudioReviewFrame",
            "MKRStudioReviewBurnIn",
            "MKRStudioCompareBoard",
            "MKRStudioContactSheet",
            "MKRStudioDeliveryPlan",
            "MKRStudioSelectionSet",
            "MKRStudioReviewNotes",
            "MKRStudioDeliverySheet",
            "MKRPublishPromoFrame",
            "MKRPublishEndCard",
            "MKRPublishAssetManifest",
            "MKRPublishManifestAtIndex",
            "MKRPublishCopyDeck",
            "MKRPublishCopyAtIndex",
            "MKRBatchDifferencePreview",
            "MKRFacePerformanceEyeMotion",
            "MKRFacePerformanceLipRefine",
            "MKRFacePerformanceRigBuildNeutral",
            "MKRFacePerformanceRigApplyDeltas",
            "MKRFacePerformancePoseMerge",
            "MKRFacePerformanceEvaluate",
            "xLUT",
            "xLUTOutput",
            "x1MaskGen",
            "x1Heatmap",
            "x1Heightmap",
            "x1RoughnessMap",
            "x1SpecularMap",
            "x1TextureDelight",
            "x1TextureAlbedoSafe",
            "x1TextureDetileBlend",
            "x1TextureMacroVariation",
            "x1TextureNoiseField",
            "x1TextureCellPattern",
            "x1TextureHexTiles",
            "x1TextureStrata",
            "x1TextureWeavePattern",
            "x1MetalnessMap",
            "x1CavityMap",
            "x1AnisotropyMap",
            "x1ColorRegionMask",
            "x1OpacityMap",
            "x1ClearcoatMap",
            "x1ClearcoatRoughnessMap",
            "x1SheenMap",
            "x1TransmissionMap",
            "x1ThicknessMap",
            "x1IridescenceMap",
            "x1ScalarMapAdjust",
            "x1EmissiveMap",
            "x1EdgeWearMask",
            "x1NormalMap",
            "x1PBRPack",
            "x1PreviewMaterial",
            "x1ChannelPack",
            "x1ChannelBreakout",
            "x1NormalBlend",
            "x1CurvatureFromNormal",
            "x1UVCheckerOverlay",
            "x1SlopeMaskFromNormal",
            "x1AOFromHeight",
            "x1IDMapQuantize",
            "x1IDMaskExtract",
            "x1NormalTweak",
            "x1TextureOffset",
            "x1TextureSeamless",
            "x1TextureTilePreview",
            "x1TextureEdgePad",
            "x1AnamorphicStreaks",
            "x1HeatHaze",
            "x1LensDirtBloom",
            "x1ShockwaveDistort",
            "x1LightWrapComposite",
            "x1EdgeAberration",
            "AxBCompare",
        }
        self.assertTrue(documented_nodes.issubset(set(pack.NODE_CLASS_MAPPINGS)))

    def test_blender_bridge_extension_files_exist(self) -> None:
        bridge_root = REPO_ROOT / "blender_extension" / "mkrshift_blender_bridge"
        expected = {"__init__.py", "operators.py", "payloads.py", "ui.py"}
        self.assertTrue((REPO_ROOT / "blender_extension" / "README.md").is_file())
        self.assertTrue(bridge_root.is_dir())
        self.assertTrue(expected.issubset({path.name for path in bridge_root.glob("*.py")}))

    def test_host_addon_scaffolds_exist(self) -> None:
        addons_root = REPO_ROOT / "addons"
        self.assertTrue((addons_root / "README.md").is_file())
        self.assertTrue((addons_root / "common" / "README.md").is_file())
        self.assertTrue((addons_root / "common" / "python_endpoint_client.py").is_file())
        self.assertTrue((addons_root / "common" / "js_endpoint_client.js").is_file())
        self.assertTrue((addons_root / "blender" / "README.md").is_file())
        self.assertTrue((addons_root / "touchdesigner" / "README.md").is_file())
        self.assertTrue((addons_root / "touchdesigner" / "MKRShiftBridgeExt.py").is_file())
        self.assertTrue((addons_root / "tixl" / "README.md").is_file())
        self.assertTrue((addons_root / "tixl" / "MKRShiftComfyBridgeOperator.cs").is_file())
        self.assertTrue((addons_root / "nuke" / "README.md").is_file())
        self.assertTrue((addons_root / "nuke" / "menu.py").is_file())
        self.assertTrue((addons_root / "photoshop" / "README.md").is_file())
        self.assertTrue((addons_root / "photoshop" / "manifest.json").is_file())
        self.assertTrue((addons_root / "after_effects" / "README.md").is_file())
        self.assertTrue((addons_root / "after_effects" / "MKRShift_AE_Bridge.jsx").is_file())
        self.assertTrue((addons_root / "premiere_pro" / "README.md").is_file())
        self.assertTrue((addons_root / "premiere_pro" / "manifest.json").is_file())
        self.assertTrue((addons_root / "affinity" / "README.md").is_file())
        self.assertTrue((addons_root / "fusion360" / "README.md").is_file())
        self.assertTrue((addons_root / "fusion360" / "MKRShiftFusionBridge.py").is_file())
        self.assertTrue((addons_root / "maya" / "README.md").is_file())
        self.assertTrue((addons_root / "maya" / "MKRShiftMayaBridge.py").is_file())

    def test_legacy_plugin_scaffolds_exist(self) -> None:
        plugins_root = REPO_ROOT / "plugins"
        self.assertTrue((plugins_root / "README.md").is_file())
        self.assertTrue((plugins_root / "install_plugins.py").is_file())
        self.assertTrue((plugins_root / "common" / "README.md").is_file())
        self.assertTrue((plugins_root / "common" / "python_endpoint_client.py").is_file())
        self.assertTrue((plugins_root / "blender" / "README.md").is_file())
        self.assertTrue((plugins_root / "touchdesigner" / "README.md").is_file())
        self.assertTrue((plugins_root / "touchdesigner" / "MKRShiftBridgeExt.py").is_file())
        self.assertTrue((plugins_root / "tixl" / "README.md").is_file())
        self.assertTrue((plugins_root / "tixl" / "MKRShiftComfyBridgeOperator.cs").is_file())
        self.assertTrue((plugins_root / "nuke" / "README.md").is_file())
        self.assertTrue((plugins_root / "nuke" / "menu.py").is_file())
        self.assertTrue((plugins_root / "photoshop" / "README.md").is_file())
        self.assertTrue((plugins_root / "photoshop" / "manifest.json").is_file())
        self.assertTrue((plugins_root / "after_effects" / "README.md").is_file())
        self.assertTrue((plugins_root / "after_effects" / "MKRShift_AE_Bridge.jsx").is_file())
        self.assertTrue((plugins_root / "premiere_pro" / "README.md").is_file())
        self.assertTrue((plugins_root / "premiere_pro" / "manifest.json").is_file())
        self.assertTrue((plugins_root / "affinity" / "README.md").is_file())
        self.assertTrue((plugins_root / "fusion360" / "README.md").is_file())
        self.assertTrue((plugins_root / "fusion360" / "MKRShiftFusionBridge.py").is_file())
        self.assertTrue((plugins_root / "maya" / "README.md").is_file())
        self.assertTrue((plugins_root / "maya" / "MKRShiftMayaBridge.py").is_file())

    def test_subgraph_blueprints_exist(self) -> None:
        subgraphs_root = REPO_ROOT / "subgraphs"
        self.assertTrue((subgraphs_root / "README.md").is_file())
        self.assertTrue(subgraphs_root.is_dir())


if __name__ == "__main__":
    unittest.main()
