import json
from typing import Any, Dict, Tuple

from ..categories import ADDONS_NUKE
from ..lib.host_bridge_shared import attach_transport_plan, clean_text, parse_transport_plan, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRNukeScriptImport:
    SEARCH_ALIASES = ["nuke import", "nuke script", "nuke bridge", "gizmo import"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"nuke_payload_json": ("STRING", {"default": "", "multiline": True})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("nuke_packet_json", "read_manifest_json", "script_context_json", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NUKE

    def build(self, nuke_payload_json: str) -> Tuple[str, str, str, str]:
        payload, warnings = parse_json_object(nuke_payload_json, "nuke_payload_json")
        reads_in = payload.get("reads") if isinstance(payload.get("reads"), list) else []
        reads = []
        for item in reads_in:
            if not isinstance(item, dict):
                continue
            reads.append(
                {
                    "name": clean_text(item.get("name")) or "Read1",
                    "path": clean_text(item.get("path")),
                    "colorspace": clean_text(item.get("colorspace")) or "default",
                }
            )
        packet = {
            "schema": "mkrshift_nuke_bridge_v1",
            "source": clean_text(payload.get("source")) or "nuke",
            "script_name": clean_text(payload.get("script_name")) or "untitled.nk",
            "root_format": clean_text(payload.get("root_format")) or "HD_1080",
            "frame_range": clean_text(payload.get("frame_range")) or "1-100",
            "viewer_process": clean_text(payload.get("viewer_process")) or "None",
            "reads": reads,
            "notes": clean_text(payload.get("notes")),
        }
        summary = {
            "script_name": packet["script_name"],
            "read_count": len(reads),
            "frame_range": packet["frame_range"],
            "warnings": warnings,
        }
        return (_json(packet), _json({"reads": reads}), _json({"root_format": packet["root_format"], "viewer_process": packet["viewer_process"]}), _json(summary))


class MKRNukeReadPlan:
    SEARCH_ALIASES = ["nuke read plan", "nuke output", "read node plan", "nuke writeback"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "node_name": ("STRING", {"default": "Read_MKRShift"}),
                "colorspace": ("STRING", {"default": "default"}),
                "frame_mode": (["single", "sequence", "movie"], {"default": "single"}),
            },
            "optional": {
                "script_context_json": ("STRING", {"default": "", "multiline": True}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("nuke_read_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NUKE

    def build(self, asset_path: str, node_name: str = "Read_MKRShift", colorspace: str = "default", frame_mode: str = "single", script_context_json: str = "", transport_plan_json: str = "", notes: str = "") -> Tuple[str, str, str]:
        context, warnings = parse_json_object(script_context_json, "script_context_json")
        transport_plan, transport_warnings = parse_transport_plan(transport_plan_json)
        warnings.extend(transport_warnings)
        plan = attach_transport_plan({
            "schema": "mkrshift_nuke_read_plan_v1",
            "node_name": clean_text(node_name) or "Read_MKRShift",
            "asset_path": clean_text(asset_path),
            "asset_slug": slugify(asset_path, "asset"),
            "colorspace": clean_text(colorspace) or "default",
            "frame_mode": frame_mode,
            "root_format": clean_text(context.get("root_format")),
            "viewer_process": clean_text(context.get("viewer_process")),
            "notes": clean_text(notes),
        }, "file", transport_plan)
        manifest_line = ",".join([plan["node_name"], plan["frame_mode"], plan["colorspace"], plan["asset_path"]])
        summary = {"node_name": plan["node_name"], "frame_mode": frame_mode, "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}
        return (_json(plan), manifest_line, _json(summary))
