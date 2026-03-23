import json
from typing import Tuple

import torch

from ..categories import ADDONS_AFFINITY, ADDONS_AFTER_EFFECTS, ADDONS_FUSION360, ADDONS_MAYA, ADDONS_NUKE, ADDONS_PHOTOSHOP, ADDONS_PREMIERE_PRO, BRIDGE_BLENDER
from ..lib.host_bridge_shared import clean_text, parse_json_object
from ..lib.host_image_bridge_shared import save_image_output_assets


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


class _BaseSingleAssetPlanRuntime:
    CATEGORY = ""
    HOST_NAME = ""
    PLAN_FIELD = "plan_json"
    SEARCH_ALIASES = []

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                cls.PLAN_FIELD: ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "filename_override": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("written_paths_json", "primary_path", "summary_json")
    FUNCTION = "run"

    def run(self, images: torch.Tensor, filename_override: str = "", **kwargs) -> Tuple[str, str, str]:
        raw_plan = kwargs.get(self.PLAN_FIELD, "{}")
        plan, warnings = parse_json_object(raw_plan, self.PLAN_FIELD)
        asset_info = plan.get("asset") if isinstance(plan.get("asset"), dict) else {}
        asset_path = clean_text(plan.get("asset_path")) or clean_text(asset_info.get("path"))
        paths, write_warnings = save_image_output_assets(images, asset_path, filename_override)
        warnings.extend(write_warnings)
        summary = {
            "host": self.HOST_NAME,
            "schema": clean_text(plan.get("schema")),
            "target_name": clean_text(
                plan.get("target_name")
                or plan.get("node_name")
                or plan.get("target_layer_name")
                or plan.get("target_comp_name")
                or plan.get("target_sequence_name")
                or plan.get("target_appearance_name")
                or plan.get("target_shader_name")
            ),
            "count": len(paths),
            "primary_path": paths[0] if paths else "",
            "warnings": warnings,
        }
        return (_json({"paths": paths, "plan": plan}), paths[0] if paths else "", _json(summary))


class MKRBlenderReturnOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["blender return output", "blender return apply", "blender roundtrip output"]
    CATEGORY = BRIDGE_BLENDER
    HOST_NAME = "blender"
    PLAN_FIELD = "return_plan_json"


class MKRNukeReadOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["nuke read output", "nuke read apply", "nuke read write"]
    CATEGORY = ADDONS_NUKE
    HOST_NAME = "nuke"
    PLAN_FIELD = "nuke_read_plan_json"


class MKRPhotoshopExportOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["photoshop export output", "photoshop export apply", "photoshop write result"]
    CATEGORY = ADDONS_PHOTOSHOP
    HOST_NAME = "photoshop"
    PLAN_FIELD = "photoshop_export_plan_json"


class MKRAfterEffectsRenderOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["after effects render output", "ae render apply", "after effects write result"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    HOST_NAME = "after_effects"
    PLAN_FIELD = "ae_render_plan_json"


class MKRPremiereExportOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["premiere export output", "premiere apply output", "premiere write result"]
    CATEGORY = ADDONS_PREMIERE_PRO
    HOST_NAME = "premiere_pro"
    PLAN_FIELD = "premiere_export_plan_json"


class MKRAffinityExportOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["affinity export output", "affinity apply output", "affinity write result"]
    CATEGORY = ADDONS_AFFINITY
    HOST_NAME = "affinity"
    PLAN_FIELD = "affinity_export_plan_json"


class MKRFusion360TextureOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["fusion 360 texture output", "fusion texture apply", "fusion write result"]
    CATEGORY = ADDONS_FUSION360
    HOST_NAME = "fusion360"
    PLAN_FIELD = "fusion_texture_plan_json"


class MKRMayaMaterialOutput(_BaseSingleAssetPlanRuntime):
    SEARCH_ALIASES = ["maya material output", "maya material apply", "maya write result"]
    CATEGORY = ADDONS_MAYA
    HOST_NAME = "maya"
    PLAN_FIELD = "maya_material_plan_json"
