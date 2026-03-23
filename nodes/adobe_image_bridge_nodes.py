from ..categories import ADDONS_AFTER_EFFECTS, ADDONS_PHOTOSHOP, ADDONS_PREMIERE_PRO
from ..lib.host_bridge_shared import clean_text
from .host_image_node_shared import BaseHostImageImport, build_host_image_output_result


class MKRPhotoshopImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["photoshop image import", "photoshop layer import", "photoshop plate import", "photoshop image bridge"]
    CATEGORY = ADDONS_PHOTOSHOP
    SUMMARY_HOST = "photoshop"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRAfterEffectsImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["after effects image import", "ae frame import", "ae plate import", "after effects still import"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    SUMMARY_HOST = "after_effects"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRPremiereImageImport(BaseHostImageImport):
    SEARCH_ALIASES = ["premiere image import", "premiere frame import", "premiere still import", "premiere plate import"]
    CATEGORY = ADDONS_PREMIERE_PRO
    SUMMARY_HOST = "premiere_pro"
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "payload_json", "asset_path", "summary_json")
    FUNCTION = "build"

    def build(self, payload_json: str, preferred_slot: str = ""):
        return self._build(payload_json, preferred_slot)


class MKRPhotoshopImageOutputPlan:
    SEARCH_ALIASES = ["photoshop image output", "photoshop layer output", "photoshop live image", "photoshop texture output"]
    CATEGORY = ADDONS_PHOTOSHOP
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "layer_art"}),
                "target_name": ("STRING", {"default": "MKRShift Result"}),
                "apply_mode": (["new_layer", "replace_layer_pixels", "smart_object"], {"default": "new_layer"}),
            },
            "optional": {
                "blend_mode": ("STRING", {"default": "normal"}),
                "target_document_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "layer_art",
        target_name: str = "MKRShift Result",
        apply_mode: str = "new_layer",
        blend_mode: str = "normal",
        target_document_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_photoshop_image_output_plan_v1",
            "photoshop",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {
                "blend_mode": clean_text(blend_mode) or "normal",
                "target_document_name": clean_text(target_document_name),
            },
        )


class MKRAfterEffectsImageOutputPlan:
    SEARCH_ALIASES = ["after effects image output", "ae still output", "ae plate output", "after effects live image"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "footage"}),
                "target_name": ("STRING", {"default": "MKRShift Plate"}),
                "apply_mode": (["import_footage", "replace_layer_source", "background_plate"], {"default": "import_footage"}),
            },
            "optional": {
                "target_comp_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "footage",
        target_name: str = "MKRShift Plate",
        apply_mode: str = "import_footage",
        target_comp_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_after_effects_image_output_plan_v1",
            "after_effects",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {"target_comp_name": clean_text(target_comp_name)},
        )


class MKRPremiereImageOutputPlan:
    SEARCH_ALIASES = ["premiere image output", "premiere still output", "premiere graphic output", "premiere live image"]
    CATEGORY = ADDONS_PREMIERE_PRO
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_output_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "image_role": ("STRING", {"default": "graphic"}),
                "target_name": ("STRING", {"default": "MKRShift Graphic"}),
                "apply_mode": (["new_graphic", "replace_clip", "bin_import"], {"default": "new_graphic"}),
            },
            "optional": {
                "target_sequence_name": ("STRING", {"default": ""}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        asset_path: str,
        image_role: str = "graphic",
        target_name: str = "MKRShift Graphic",
        apply_mode: str = "new_graphic",
        target_sequence_name: str = "",
        transport_plan_json: str = "",
    ):
        return build_host_image_output_result(
            "mkrshift_premiere_image_output_plan_v1",
            "premiere_pro",
            asset_path,
            image_role,
            target_name,
            apply_mode,
            transport_plan_json,
            {"target_sequence_name": clean_text(target_sequence_name)},
        )
