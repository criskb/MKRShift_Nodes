import json
from typing import Any, Dict, Tuple

from ..categories import BRIDGE_TOUCHDESIGNER
from ..lib.host_bridge_shared import clean_text, normalize_touchdesigner_packet, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRTouchDesignerImport:
    SEARCH_ALIASES = [
        "touchdesigner bridge",
        "touchdesigner import",
        "td packet",
        "tox bridge",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "touchdesigner_payload_json": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("td_packet_json", "controls_json", "texture_manifest_json", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_TOUCHDESIGNER

    def build(self, touchdesigner_payload_json: str) -> Tuple[str, str, str, str]:
        payload, warnings = parse_json_object(touchdesigner_payload_json, "touchdesigner_payload_json")
        packet, normalize_warnings = normalize_touchdesigner_packet(payload)
        warnings.extend(normalize_warnings)
        texture_manifest = {
            "schema": "mkrshift_touchdesigner_texture_manifest_v1",
            "top_name": packet["top_name"],
            "texture_count": len(packet["textures"]),
            "textures": packet["textures"],
        }
        summary = {
            "project_name": packet["project_name"],
            "tox_name": packet["tox_name"],
            "operator_path": packet["operator_path"],
            "transport": packet["transport"],
            "texture_count": len(packet["textures"]),
            "warnings": warnings,
        }
        return (_json(packet), _json(packet["controls"]), _json(texture_manifest), _json(summary))


class MKRTouchDesignerFramePlan:
    SEARCH_ALIASES = [
        "touchdesigner output",
        "touchdesigner frame plan",
        "td top plan",
        "spout ndi touchdesigner",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "transport": (["file", "spout", "ndi", "shared_memory", "websocket"], {"default": "file"}),
                "top_name": ("STRING", {"default": "mkrshiftTOP"}),
                "operator_path": ("STRING", {"default": "/project1/mkrshift_bridge1"}),
                "asset_kind": (["image", "image_sequence", "video", "texture"], {"default": "image"}),
                "colorspace": (["sRGB", "Linear", "Non-Color"], {"default": "sRGB"}),
            },
            "optional": {
                "metadata_json": ("STRING", {"default": "", "multiline": True}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("td_frame_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_TOUCHDESIGNER

    def build(
        self,
        asset_path: str,
        transport: str = "file",
        top_name: str = "mkrshiftTOP",
        operator_path: str = "/project1/mkrshift_bridge1",
        asset_kind: str = "image",
        colorspace: str = "sRGB",
        metadata_json: str = "",
        transport_plan_json: str = "",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        metadata, warnings = parse_json_object(metadata_json, "metadata_json")
        transport_plan, transport_warnings = parse_json_object(transport_plan_json, "transport_plan_json")
        warnings.extend(transport_warnings)
        plan = {
            "schema": "mkrshift_touchdesigner_frame_plan_v1",
            "transport": transport,
            "top_name": clean_text(top_name) or "mkrshiftTOP",
            "operator_path": clean_text(operator_path) or "/project1/mkrshift_bridge1",
            "asset": {
                "path": clean_text(asset_path),
                "kind": asset_kind,
                "colorspace": colorspace,
            },
            "asset_slug": slugify(asset_path, "asset"),
            "metadata": metadata,
            "transport_plan": transport_plan,
            "notes": clean_text(notes),
        }
        manifest_line = ",".join(
            [
                plan["transport"],
                plan["top_name"],
                plan["asset"]["kind"],
                plan["asset"]["colorspace"],
                plan["asset"]["path"],
            ]
        )
        summary = {
            "transport": transport,
            "top_name": plan["top_name"],
            "operator_path": plan["operator_path"],
            "asset_kind": asset_kind,
            "has_transport_plan": bool(transport_plan),
            "has_path": bool(plan["asset"]["path"]),
            "warnings": warnings,
        }
        return (_json(plan), manifest_line, _json(summary))
