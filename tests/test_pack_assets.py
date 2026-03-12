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

    def test_help_docs_exist_for_documented_nodes(self) -> None:
        docs_root = REPO_ROOT / "web" / "docs"
        expected = {
            "AngleShift.md",
            "MKRCharacterCustomizer.md",
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
            "MKRshiftSocialPackBuilder.md",
            "MKRFacePerformanceEyeMotion.md",
            "MKRFacePerformanceLipRefine.md",
            "MKRFacePerformanceRigBuildNeutral.md",
            "MKRFacePerformanceRigApplyDeltas.md",
            "MKRFacePerformancePoseMerge.md",
            "MKRFacePerformanceEvaluate.md",
            "xLUT.md",
            "x1MaskGen.md",
            "x1Heatmap.md",
            "x1Heightmap.md",
            "x1RoughnessMap.md",
            "x1SpecularMap.md",
            "x1MetalnessMap.md",
            "x1NormalMap.md",
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
            "AxBCompare.md",
        }
        existing = {path.name for path in docs_root.glob("*.md")}
        self.assertTrue(expected.issubset(existing))

    def test_documented_nodes_are_exported(self) -> None:
        documented_nodes = {
            "AngleShift",
            "MKRCharacterCustomizer",
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
            "MKRshiftSocialPackBuilder",
            "MKRFacePerformanceEyeMotion",
            "MKRFacePerformanceLipRefine",
            "MKRFacePerformanceRigBuildNeutral",
            "MKRFacePerformanceRigApplyDeltas",
            "MKRFacePerformancePoseMerge",
            "MKRFacePerformanceEvaluate",
            "xLUT",
            "x1MaskGen",
            "x1Heatmap",
            "x1Heightmap",
            "x1RoughnessMap",
            "x1SpecularMap",
            "x1MetalnessMap",
            "x1NormalMap",
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
            "AxBCompare",
        }
        self.assertTrue(documented_nodes.issubset(set(pack.NODE_CLASS_MAPPINGS)))


if __name__ == "__main__":
    unittest.main()
