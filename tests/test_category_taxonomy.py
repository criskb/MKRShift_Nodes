import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.categories import (  # noqa: E402
    ADDONS_AFFINITY,
    ADDONS_AFTER_EFFECTS,
    ADDONS_FUSION360,
    ADDONS_MAYA,
    ADDONS_NUKE,
    ADDONS_NETWORK,
    ADDONS_PHOTOSHOP,
    ADDONS_PREMIERE_PRO,
    ADDONS_TIXL,
    ADDONS_TOUCHDESIGNER,
    BRIDGE_BLENDER,
    COLOR_ANALYZE,
    CORE_CHARACTER,
    INSPECT_COMPARE,
    FX_DISTORT,
    FX_OPTICS,
    INSPECT_PREVIEW,
    PUBLISH_BUILD,
    PUBLISH_UTILS,
    STUDIO_BOARDS,
    STUDIO_DELIVERY,
    STUDIO_REVIEW,
    SURFACE_MAPS,
    SURFACE_PREVIEW,
    SURFACE_TECH_ART,
    SURFACE_TEXTURE,
    UTILITY_MAPS,
    UTILITY_TECH_ART,
    UTILITY_TEXTURE,
)
from MKRShift_Nodes.nodes.bridge_nodes import (  # noqa: E402
    MKRBlenderCameraShot,
    MKRBlenderMaterialImport,
    MKRBlenderMaterialReturnPlan,
    MKRBlenderReturnPlan,
    MKRBlenderSceneImport,
)
from MKRShift_Nodes.nodes.host_3d_image_bridge_nodes import (  # noqa: E402
    MKRBlenderImageImport,
    MKRBlenderImageOutputPlan,
    MKRFusion360ImageImport,
    MKRFusion360ImageOutputPlan,
    MKRMayaImageImport,
    MKRMayaImageOutputPlan,
)
from MKRShift_Nodes.nodes.host_image_runtime_nodes import (  # noqa: E402
    MKRAfterEffectsImageOutput,
    MKRBlenderImageOutput,
    MKRFusion360ImageOutput,
    MKRMayaImageOutput,
    MKRNukeImageOutput,
    MKRPhotoshopImageOutput,
    MKRPremiereImageOutput,
)
from MKRShift_Nodes.nodes.touchdesigner_bridge_nodes import MKRTouchDesignerFramePlan, MKRTouchDesignerImport  # noqa: E402
from MKRShift_Nodes.nodes.tixl_bridge_nodes import MKRTiXLFramePlan, MKRTiXLImport  # noqa: E402
from MKRShift_Nodes.nodes.nuke_bridge_nodes import MKRNukeReadPlan, MKRNukeScriptImport  # noqa: E402
from MKRShift_Nodes.nodes.host_2d_image_bridge_nodes import (  # noqa: E402
    MKRAfterEffectsImageImport,
    MKRAfterEffectsImageOutputPlan,
    MKRNukeImageImport,
    MKRNukeImageOutputPlan,
    MKRPhotoshopImageImport,
    MKRPhotoshopImageOutputPlan,
    MKRPremiereImageImport,
    MKRPremiereImageOutputPlan,
)
from MKRShift_Nodes.nodes.adobe_bridge_nodes import (  # noqa: E402
    MKRAfterEffectsCompImport,
    MKRAfterEffectsRenderPlan,
    MKRPhotoshopDocumentImport,
    MKRPhotoshopExportPlan,
    MKRPremiereExportPlan,
    MKRPremiereSequenceImport,
)
from MKRShift_Nodes.nodes.dcc_bridge_nodes import (  # noqa: E402
    MKRAffinityDocumentImport,
    MKRAffinityExportPlan,
    MKRAffinityPhotoshopPluginPlan,
    MKRFusion360SceneImport,
    MKRFusion360TexturePlan,
    MKRMayaMaterialPlan,
    MKRMayaSceneImport,
)
from MKRShift_Nodes.nodes.host_plan_runtime_nodes import (  # noqa: E402
    MKRAffinityExportOutput,
    MKRAfterEffectsRenderOutput,
    MKRBlenderReturnOutput,
    MKRFusion360TextureOutput,
    MKRMayaMaterialOutput,
    MKRNukeReadOutput,
    MKRPhotoshopExportOutput,
    MKRPremiereExportOutput,
)
from MKRShift_Nodes.nodes.network_addon_nodes import (  # noqa: E402
    MKRAddonEndpointPlan,
    MKRHTTPWebhookPlan,
    MKRNDIStreamPlan,
    MKROSCMessagePlan,
    MKRSpoutSenderPlan,
    MKRSyphonSenderPlan,
    MKRTCPBridgePlan,
    MKRWatchFolderPlan,
    MKRWebSocketBridgePlan,
)
from MKRShift_Nodes.nodes.network_addon_runtime_nodes import (  # noqa: E402
    MKRAddonEndpointPoll,
    MKRAddonEndpointSubmit,
    MKRHTTPWebhookSend,
    MKROSCSend,
    MKRTCPBridgeSend,
    MKRWatchFolderWrite,
)
from MKRShift_Nodes.nodes.character_state_nodes import MKRCharacterState, MKROutfitSet  # noqa: E402
from MKRShift_Nodes.nodes.pose_studio_nodes import MKRPoseStudio  # noqa: E402
from MKRShift_Nodes.nodes.heatmap_nodes import x1Heatmap, x1Heightmap  # noqa: E402
from MKRShift_Nodes.nodes.publish_manifest_nodes import (  # noqa: E402
    MKRPublishAssetManifest,
    MKRPublishCopyAtIndex,
    MKRPublishCopyDeck,
    MKRPublishManifestAtIndex,
)
from MKRShift_Nodes.nodes.publish_nodes import MKRPublishEndCard, MKRPublishPromoFrame  # noqa: E402
from MKRShift_Nodes.nodes.material_map_nodes import (  # noqa: E402
    x1CavityMap,
    x1AnisotropyMap,
    x1ClearcoatMap,
    x1ClearcoatRoughnessMap,
    x1ColorRegionMask,
    x1EdgeWearMask,
    x1EmissiveMap,
    x1IridescenceMap,
    x1MetalnessMap,
    x1NormalMap,
    x1OpacityMap,
    x1SheenMap,
    x1ScalarMapAdjust,
    x1ThicknessMap,
    x1TransmissionMap,
)
from MKRShift_Nodes.nodes.material_pack_nodes import x1PBRPack  # noqa: E402
from MKRShift_Nodes.nodes.material_preview_nodes import x1PreviewMaterial  # noqa: E402
from MKRShift_Nodes.nodes.inspect_compare_nodes import MKRBatchDifferencePreview  # noqa: E402
from MKRShift_Nodes.nodes.preview_nodes import MKRBatchCollagePreview  # noqa: E402
from MKRShift_Nodes.nodes.studio_nodes import (  # noqa: E402
    MKRStudioCompareBoard,
    MKRStudioContactSheet,
    MKRStudioReviewBurnIn,
    MKRStudioReviewFrame,
)
from MKRShift_Nodes.nodes.studio_handoff_nodes import MKRStudioDeliverySheet, MKRStudioReviewNotes  # noqa: E402
from MKRShift_Nodes.nodes.studio_selection_nodes import MKRStudioSelectionSet  # noqa: E402
from MKRShift_Nodes.nodes.tech_art_surface_nodes import x1IDMaskExtract, x1NormalTweak, x1SlopeMaskFromNormal  # noqa: E402
from MKRShift_Nodes.nodes.texture_tool_nodes import (  # noqa: E402
    x1TextureAlbedoSafe,
    x1TextureCellPattern,
    x1TextureDetileBlend,
    x1TextureDelight,
    x1TextureHexTiles,
    x1TextureMacroVariation,
    x1TextureNoiseField,
    x1TextureSeamless,
    x1TextureStrata,
    x1TextureWeavePattern,
)
from MKRShift_Nodes.nodes.vfx_finishing_nodes import x1AnamorphicStreaks, x1HeatHaze  # noqa: E402
from MKRShift_Nodes.nodes.vfx_optics_nodes import x1LensDirtBloom, x1ShockwaveDistort  # noqa: E402
from MKRShift_Nodes.nodes.vfx_composite_nodes import x1EdgeAberration, x1LightWrapComposite  # noqa: E402
from MKRShift_Nodes.nodes.xcine import x1LensBreathing  # noqa: E402
from MKRShift_Nodes.nodes.xconcepts import x1LensDistort, x1WarpDisplace  # noqa: E402


class CategoryTaxonomyTests(unittest.TestCase):
    def test_surface_aliases_point_at_surface_taxonomy(self) -> None:
        self.assertEqual(UTILITY_MAPS, SURFACE_MAPS)
        self.assertEqual(UTILITY_TEXTURE, SURFACE_TEXTURE)
        self.assertEqual(UTILITY_TECH_ART, SURFACE_TECH_ART)

    def test_character_state_nodes_live_under_character_branch(self) -> None:
        self.assertEqual(MKRCharacterState.CATEGORY, CORE_CHARACTER)
        self.assertEqual(MKROutfitSet.CATEGORY, CORE_CHARACTER)
        self.assertEqual(MKRPoseStudio.CATEGORY, CORE_CHARACTER)

    def test_blender_bridge_nodes_live_under_bridge_branch(self) -> None:
        self.assertEqual(MKRBlenderSceneImport.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderCameraShot.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderImageImport.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderImageOutputPlan.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderImageOutput.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderMaterialImport.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderMaterialReturnPlan.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderReturnPlan.CATEGORY, BRIDGE_BLENDER)
        self.assertEqual(MKRBlenderReturnOutput.CATEGORY, BRIDGE_BLENDER)

    def test_touchdesigner_bridge_nodes_live_under_bridge_branch(self) -> None:
        self.assertEqual(MKRTouchDesignerImport.CATEGORY, ADDONS_TOUCHDESIGNER)
        self.assertEqual(MKRTouchDesignerFramePlan.CATEGORY, ADDONS_TOUCHDESIGNER)

    def test_tixl_bridge_nodes_live_under_bridge_branch(self) -> None:
        self.assertEqual(MKRTiXLImport.CATEGORY, ADDONS_TIXL)
        self.assertEqual(MKRTiXLFramePlan.CATEGORY, ADDONS_TIXL)

    def test_other_addon_nodes_live_under_host_branches(self) -> None:
        self.assertEqual(MKRAddonEndpointPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKROSCMessagePlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRNDIStreamPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRSpoutSenderPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRSyphonSenderPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRTCPBridgePlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRHTTPWebhookPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRWatchFolderPlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRWebSocketBridgePlan.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRAddonEndpointSubmit.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRAddonEndpointPoll.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRHTTPWebhookSend.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRTCPBridgeSend.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKROSCSend.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRWatchFolderWrite.CATEGORY, ADDONS_NETWORK)
        self.assertEqual(MKRNukeScriptImport.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRNukeReadPlan.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRNukeReadOutput.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRNukeImageImport.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRNukeImageOutputPlan.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRNukeImageOutput.CATEGORY, ADDONS_NUKE)
        self.assertEqual(MKRPhotoshopDocumentImport.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRPhotoshopExportPlan.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRPhotoshopExportOutput.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRPhotoshopImageImport.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRPhotoshopImageOutputPlan.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRPhotoshopImageOutput.CATEGORY, ADDONS_PHOTOSHOP)
        self.assertEqual(MKRAfterEffectsCompImport.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRAfterEffectsRenderPlan.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRAfterEffectsRenderOutput.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRAfterEffectsImageImport.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRAfterEffectsImageOutputPlan.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRAfterEffectsImageOutput.CATEGORY, ADDONS_AFTER_EFFECTS)
        self.assertEqual(MKRPremiereSequenceImport.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRPremiereExportPlan.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRPremiereExportOutput.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRPremiereImageImport.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRPremiereImageOutputPlan.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRPremiereImageOutput.CATEGORY, ADDONS_PREMIERE_PRO)
        self.assertEqual(MKRAffinityDocumentImport.CATEGORY, ADDONS_AFFINITY)
        self.assertEqual(MKRAffinityExportPlan.CATEGORY, ADDONS_AFFINITY)
        self.assertEqual(MKRAffinityExportOutput.CATEGORY, ADDONS_AFFINITY)
        self.assertEqual(MKRAffinityPhotoshopPluginPlan.CATEGORY, ADDONS_AFFINITY)
        self.assertEqual(MKRFusion360SceneImport.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRFusion360TexturePlan.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRFusion360TextureOutput.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRFusion360ImageImport.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRFusion360ImageOutputPlan.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRFusion360ImageOutput.CATEGORY, ADDONS_FUSION360)
        self.assertEqual(MKRMayaSceneImport.CATEGORY, ADDONS_MAYA)
        self.assertEqual(MKRMayaMaterialPlan.CATEGORY, ADDONS_MAYA)
        self.assertEqual(MKRMayaMaterialOutput.CATEGORY, ADDONS_MAYA)
        self.assertEqual(MKRMayaImageImport.CATEGORY, ADDONS_MAYA)
        self.assertEqual(MKRMayaImageOutputPlan.CATEGORY, ADDONS_MAYA)
        self.assertEqual(MKRMayaImageOutput.CATEGORY, ADDONS_MAYA)

    def test_surface_nodes_live_under_surface_branch(self) -> None:
        self.assertEqual(x1Heatmap.CATEGORY, COLOR_ANALYZE)
        self.assertEqual(x1Heightmap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1MetalnessMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1CavityMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1AnisotropyMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1OpacityMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1ClearcoatMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1ClearcoatRoughnessMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1SheenMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1TransmissionMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1ThicknessMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1IridescenceMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1ScalarMapAdjust.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1ColorRegionMask.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1EmissiveMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1EdgeWearMask.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1NormalMap.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1PBRPack.CATEGORY, SURFACE_MAPS)
        self.assertEqual(x1PreviewMaterial.CATEGORY, SURFACE_PREVIEW)
        self.assertEqual(x1TextureDelight.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureAlbedoSafe.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureMacroVariation.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureDetileBlend.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureNoiseField.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureCellPattern.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureHexTiles.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureStrata.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureWeavePattern.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1TextureSeamless.CATEGORY, SURFACE_TEXTURE)
        self.assertEqual(x1IDMaskExtract.CATEGORY, SURFACE_TECH_ART)
        self.assertEqual(x1SlopeMaskFromNormal.CATEGORY, SURFACE_TECH_ART)
        self.assertEqual(x1NormalTweak.CATEGORY, SURFACE_TECH_ART)

    def test_studio_boards_are_split_from_review_overlays(self) -> None:
        self.assertEqual(MKRStudioReviewFrame.CATEGORY, STUDIO_REVIEW)
        self.assertEqual(MKRStudioReviewBurnIn.CATEGORY, STUDIO_REVIEW)
        self.assertEqual(MKRStudioSelectionSet.CATEGORY, STUDIO_REVIEW)
        self.assertEqual(MKRStudioContactSheet.CATEGORY, STUDIO_BOARDS)
        self.assertEqual(MKRStudioCompareBoard.CATEGORY, STUDIO_BOARDS)

    def test_studio_delivery_nodes_live_under_delivery_branch(self) -> None:
        self.assertEqual(MKRStudioReviewNotes.CATEGORY, STUDIO_DELIVERY)
        self.assertEqual(MKRStudioDeliverySheet.CATEGORY, STUDIO_DELIVERY)

    def test_preview_nodes_stay_under_inspect_preview(self) -> None:
        self.assertEqual(MKRBatchCollagePreview.CATEGORY, INSPECT_PREVIEW)
        self.assertEqual(MKRBatchDifferencePreview.CATEGORY, INSPECT_COMPARE)

    def test_publish_nodes_live_under_publish_branch(self) -> None:
        self.assertEqual(MKRPublishPromoFrame.CATEGORY, PUBLISH_BUILD)
        self.assertEqual(MKRPublishEndCard.CATEGORY, PUBLISH_BUILD)
        self.assertEqual(MKRPublishAssetManifest.CATEGORY, PUBLISH_BUILD)
        self.assertEqual(MKRPublishManifestAtIndex.CATEGORY, PUBLISH_UTILS)
        self.assertEqual(MKRPublishCopyDeck.CATEGORY, PUBLISH_UTILS)
        self.assertEqual(MKRPublishCopyAtIndex.CATEGORY, PUBLISH_UTILS)

    def test_vfx_nodes_are_grouped_by_optics_and_distortion(self) -> None:
        self.assertEqual(x1AnamorphicStreaks.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensDirtBloom.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensDistort.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensBreathing.CATEGORY, FX_OPTICS)
        self.assertEqual(x1HeatHaze.CATEGORY, FX_DISTORT)
        self.assertEqual(x1ShockwaveDistort.CATEGORY, FX_DISTORT)
        self.assertEqual(x1WarpDisplace.CATEGORY, FX_DISTORT)
        self.assertEqual(x1LightWrapComposite.CATEGORY, FX_OPTICS)
        self.assertEqual(x1EdgeAberration.CATEGORY, FX_DISTORT)


if __name__ == "__main__":
    unittest.main()
