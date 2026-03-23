from typing import Tuple

from ..categories import ADDONS_WORKFLOW
from ..lib.addon_workflow_shared import build_addon_workflow_interface, json_text
from ..lib.host_bridge_shared import clean_text


class MKRAddonWorkflowInterface:
    SEARCH_ALIASES = ["addon workflow interface", "host workflow interface", "dynamic addon ui", "workflow metadata"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "interface_name": ("STRING", {"default": "MKRShift Workflow"}),
                "workflow_id": ("STRING", {"default": "mkrshift-workflow"}),
                "host_family": (
                    [
                        "generic",
                        "blender",
                        "touchdesigner",
                        "tixl",
                        "nuke",
                        "photoshop",
                        "after_effects",
                        "premiere_pro",
                        "affinity",
                        "fusion360",
                        "maya",
                    ],
                    {"default": "blender"},
                ),
                "fields_json": ("STRING", {"default": "[]", "multiline": True}),
            },
            "optional": {
                "output_targets_json": ("STRING", {"default": "{}", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("workflow_interface_json", "field_keys_csv", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_WORKFLOW

    def build(
        self,
        interface_name: str = "MKRShift Workflow",
        workflow_id: str = "mkrshift-workflow",
        host_family: str = "blender",
        fields_json: str = "[]",
        output_targets_json: str = "{}",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        interface, warnings = build_addon_workflow_interface(interface_name, workflow_id, host_family, fields_json, output_targets_json, notes)
        summary = {
            "interface_name": interface["interface_name"],
            "workflow_id": interface["workflow_id"],
            "host_family": interface["host_family"],
            "field_count": len(interface["fields"]),
            "groups": sorted({clean_text(field.get("group")) or "Workflow" for field in interface["fields"]}),
            "warnings": warnings,
        }
        field_keys_csv = ", ".join(field["key"] for field in interface["fields"])
        return (json_text(interface), field_keys_csv, json_text(summary))
