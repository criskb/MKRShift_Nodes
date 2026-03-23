import json
from typing import Tuple

import torch

from ..categories import ADDONS_AFTER_EFFECTS, ADDONS_BLENDER, ADDONS_FUSION360, ADDONS_MAYA, ADDONS_NUKE, ADDONS_PHOTOSHOP, ADDONS_PREMIERE_PRO
from ..lib.host_bridge_shared import clean_text, parse_json_object
from ..lib.host_image_bridge_shared import save_image_output_assets


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


class _BaseHostImageOutputRuntime:
    CATEGORY = ""
    HOST_NAME = ""
    SEARCH_ALIASES = []

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "image_output_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "filename_override": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("written_paths_json", "primary_path", "summary_json")
    FUNCTION = "run"

    def run(self, images: torch.Tensor, image_output_plan_json: str = "{}", filename_override: str = "") -> Tuple[str, str, str]:
        plan, warnings = parse_json_object(image_output_plan_json, "image_output_plan_json")
        paths, write_warnings = save_image_output_assets(images, clean_text(plan.get("asset_path")), filename_override)
        warnings.extend(write_warnings)
        summary = {
            "host": self.HOST_NAME,
            "apply_mode": clean_text(plan.get("apply_mode")),
            "image_role": clean_text(plan.get("image_role")),
            "count": len(paths),
            "primary_path": paths[0] if paths else "",
            "warnings": warnings,
        }
        return (_json({"paths": paths, "plan": plan}), paths[0] if paths else "", _json(summary))


class MKRBlenderImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["blender image output", "blender output apply", "blender texture write"]
    CATEGORY = ADDONS_BLENDER
    HOST_NAME = "blender"


class MKRNukeImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["nuke image output", "nuke write apply", "nuke plate write"]
    CATEGORY = ADDONS_NUKE
    HOST_NAME = "nuke"


class MKRPhotoshopImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["photoshop image output", "photoshop layer write", "photoshop output apply"]
    CATEGORY = ADDONS_PHOTOSHOP
    HOST_NAME = "photoshop"


class MKRAfterEffectsImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["after effects image output", "ae image output", "after effects plate write"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    HOST_NAME = "after_effects"


class MKRPremiereImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["premiere image output", "premiere graphic write", "premiere still write"]
    CATEGORY = ADDONS_PREMIERE_PRO
    HOST_NAME = "premiere_pro"


class MKRFusion360ImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["fusion 360 image output", "fusion decal write", "fusion texture write"]
    CATEGORY = ADDONS_FUSION360
    HOST_NAME = "fusion360"


class MKRMayaImageOutput(_BaseHostImageOutputRuntime):
    SEARCH_ALIASES = ["maya image output", "maya texture write", "maya output apply"]
    CATEGORY = ADDONS_MAYA
    HOST_NAME = "maya"
