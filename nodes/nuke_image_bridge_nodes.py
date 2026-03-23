from ..categories import ADDONS_NUKE
from ..lib.host_bridge_shared import clean_text
from .host_image_node_shared import BaseHostImageImport, build_host_image_output_result


class MKRNukeImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["nuke image import", "nuke read import", "nuke plate import", "nuke frame import"]
    CATEGORY = ADDONS_NUKE
    SUMMARY_HOST = "nuke"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRNukeImageOutputPlan:
    SEARCH_ALIASES = ["nuke image output", "nuke writeback image", "nuke plate output", "nuke live image"]
    CATEGORY = ADDONS_NUKE
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "plate"}),
                "target_name": ("STRING", {"default": "Read_MKRShift"}),
                "apply_mode": (["read_node", "deep_read", "viewer_input"], {"default": "read_node"}),
            },
            "optional": {
                "colorspace": ("STRING", {"default": "default"}),
                "target_script_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "plate",
        target_name: str = "Read_MKRShift",
        apply_mode: str = "read_node",
        colorspace: str = "default",
        target_script_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_nuke_image_output_plan_v1",
            "nuke",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {
                "colorspace": clean_text(colorspace) or "default",
                "target_script_name": clean_text(target_script_name),
            },
        )
