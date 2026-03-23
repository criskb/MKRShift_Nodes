from ..categories import ADDONS_BLENDER
from ..lib.host_bridge_shared import clean_text
from .host_image_node_shared import BaseHostImageImport, build_host_image_output_result


class MKRBlenderImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["blender image import", "blender texture import", "blender render import", "blender pass import"]
    CATEGORY = ADDONS_BLENDER
    SUMMARY_HOST = "blender"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRBlenderImageOutputPlan:
    SEARCH_ALIASES = ["blender image output", "blender texture output", "blender live texture", "blender custom texture"]
    CATEGORY = ADDONS_BLENDER
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "base_color"}),
                "target_name": ("STRING", {"default": "MKRShift Result"}),
                "apply_mode": (["texture_image", "image_plane", "camera_background", "compositor_image"], {"default": "texture_image"}),
            },
            "optional": {
                "target_material_name": ("STRING", {"default": ""}),
                "target_object_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "base_color",
        target_name: str = "MKRShift Result",
        apply_mode: str = "texture_image",
        target_material_name: str = "",
        target_object_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_blender_image_output_plan_v1",
            "blender",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {
                "target_material_name": clean_text(target_material_name),
                "target_object_name": clean_text(target_object_name),
            },
        )
