from ..categories import ADDONS_FUSION360, ADDONS_MAYA
from ..lib.host_bridge_shared import clean_text
from .host_image_node_shared import BaseHostImageImport, build_host_image_output_result


class MKRFusion360ImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["fusion 360 image import", "fusion render import", "fusion texture import", "fusion viewport import"]
    CATEGORY = ADDONS_FUSION360
    SUMMARY_HOST = "fusion360"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRMayaImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["maya image import", "maya texture import", "maya render import", "maya viewport import"]
    CATEGORY = ADDONS_MAYA
    SUMMARY_HOST = "maya"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRFusion360ImageOutputPlan:
    SEARCH_ALIASES = ["fusion 360 image output", "fusion custom texture", "fusion decal output", "fusion live image"]
    CATEGORY = ADDONS_FUSION360
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "decal"}),
                "target_name": ("STRING", {"default": "MKRShift Appearance"}),
                "apply_mode": (["decal", "appearance_texture", "canvas_reference"], {"default": "decal"}),
            },
            "optional": {
                "target_component_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "decal",
        target_name: str = "MKRShift Appearance",
        apply_mode: str = "decal",
        target_component_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_fusion360_image_output_plan_v1",
            "fusion360",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {"target_component_name": clean_text(target_component_name)},
        )


class MKRMayaImageOutputPlan:
    SEARCH_ALIASES = ["maya image output", "maya custom texture", "maya texture output", "maya live texture"]
    CATEGORY = ADDONS_MAYA
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "base_color"}),
                "target_name": ("STRING", {"default": "MKRShiftShader"}),
                "apply_mode": (["file_texture", "aiImage", "viewport_preview"], {"default": "file_texture"}),
            },
            "optional": {
                "target_object_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "base_color",
        target_name: str = "MKRShiftShader",
        apply_mode: str = "file_texture",
        target_object_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_maya_image_output_plan_v1",
            "maya",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {"target_object_name": clean_text(target_object_name)},
        )
