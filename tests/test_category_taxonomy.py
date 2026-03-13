import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from MKRShift_Nodes.categories import (  # noqa: E402
    COLOR_ANALYZE,
    INSPECT_COMPARE,
    FX_DISTORT,
    FX_OPTICS,
    INSPECT_PREVIEW,
    SOCIAL_UTILS,
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
from MKRShift_Nodes.nodes.heatmap_nodes import x1Heatmap, x1Heightmap  # noqa: E402
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
from MKRShift_Nodes.nodes.social_campaign_nodes import MKRshiftSocialCampaignLinks  # noqa: E402
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
from MKRShift_Nodes.nodes.xcine import x1LensBreathing  # noqa: E402
from MKRShift_Nodes.nodes.xconcepts import x1LensDistort, x1WarpDisplace  # noqa: E402


class CategoryTaxonomyTests(unittest.TestCase):
    def test_surface_aliases_point_at_surface_taxonomy(self) -> None:
        self.assertEqual(UTILITY_MAPS, SURFACE_MAPS)
        self.assertEqual(UTILITY_TEXTURE, SURFACE_TEXTURE)
        self.assertEqual(UTILITY_TECH_ART, SURFACE_TECH_ART)

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

    def test_social_utilities_stay_under_social_utils(self) -> None:
        self.assertEqual(MKRshiftSocialCampaignLinks.CATEGORY, SOCIAL_UTILS)

    def test_vfx_nodes_are_grouped_by_optics_and_distortion(self) -> None:
        self.assertEqual(x1AnamorphicStreaks.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensDirtBloom.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensDistort.CATEGORY, FX_OPTICS)
        self.assertEqual(x1LensBreathing.CATEGORY, FX_OPTICS)
        self.assertEqual(x1HeatHaze.CATEGORY, FX_DISTORT)
        self.assertEqual(x1ShockwaveDistort.CATEGORY, FX_DISTORT)
        self.assertEqual(x1WarpDisplace.CATEGORY, FX_DISTORT)


if __name__ == "__main__":
    unittest.main()
