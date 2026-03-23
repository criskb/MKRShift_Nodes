import json
from typing import Any, Dict, Tuple

from ..categories import BRIDGE_TIXL
from ..lib.host_bridge_shared import clean_text, normalize_tixl_packet, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRTiXLImport:
    SEARCH_ALIASES = [
        "tixl bridge",
        "tixl import",
        "tooll bridge",
        "tixl packet",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tixl_payload_json": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("tixl_packet_json", "layer_manifest_json", "timing_json", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_TIXL

    def build(self, tixl_payload_json: str) -> Tuple[str, str, str, str]:
        payload, warnings = parse_json_object(tixl_payload_json, "tixl_payload_json")
        packet, normalize_warnings = normalize_tixl_packet(payload)
        warnings.extend(normalize_warnings)
        layer_manifest = {
            "schema": "mkrshift_tixl_layer_manifest_v1",
            "graph_name": packet["graph_name"],
            "layer_count": len(packet["layers"]),
            "layers": packet["layers"],
        }
        timing = {
            "schema": "mkrshift_tixl_timing_v1",
            "bpm": packet["bpm"],
            "transport": packet["transport"],
            "resolution": packet["resolution"],
        }
        summary = {
            "project_name": packet["project_name"],
            "graph_name": packet["graph_name"],
            "operator_name": packet["operator_name"],
            "transport": packet["transport"],
            "layer_count": len(packet["layers"]),
            "warnings": warnings,
        }
        return (_json(packet), _json(layer_manifest), _json(timing), _json(summary))


class MKRTiXLFramePlan:
    SEARCH_ALIASES = [
        "tixl output",
        "tixl bridge output",
        "tooll output plan",
        "tixl frame plan",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "transport": (["file", "ndi", "spout", "osc"], {"default": "file"}),
                "source_kind": (["texture", "image_sequence", "video", "mask"], {"default": "texture"}),
                "layer_name": ("STRING", {"default": "MKRShift Layer"}),
                "graph_name": ("STRING", {"default": "MKRShiftBridge"}),
                "blend_mode": (["Alpha", "Add", "Screen", "Multiply"], {"default": "Alpha"}),
            },
            "optional": {
                "metadata_json": ("STRING", {"default": "", "multiline": True}),
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("tixl_frame_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_TIXL

    def build(
        self,
        asset_path: str,
        transport: str = "file",
        source_kind: str = "texture",
        layer_name: str = "MKRShift Layer",
        graph_name: str = "MKRShiftBridge",
        blend_mode: str = "Alpha",
        metadata_json: str = "",
        transport_plan_json: str = "",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        metadata, warnings = parse_json_object(metadata_json, "metadata_json")
        transport_plan, transport_warnings = parse_json_object(transport_plan_json, "transport_plan_json")
        warnings.extend(transport_warnings)
        plan = {
            "schema": "mkrshift_tixl_frame_plan_v1",
            "transport": transport,
            "graph_name": clean_text(graph_name) or "MKRShiftBridge",
            "layer": {
                "name": clean_text(layer_name) or "MKRShift Layer",
                "path": clean_text(asset_path),
                "kind": source_kind,
                "blend_mode": blend_mode,
            },
            "layer_slug": slugify(layer_name, "mkrshift-layer"),
            "metadata": metadata,
            "transport_plan": transport_plan,
            "notes": clean_text(notes),
        }
        manifest_line = ",".join(
            [
                plan["transport"],
                plan["graph_name"],
                plan["layer"]["kind"],
                plan["layer"]["blend_mode"],
                plan["layer"]["path"],
            ]
        )
        summary = {
            "transport": transport,
            "graph_name": plan["graph_name"],
            "layer_name": plan["layer"]["name"],
            "source_kind": source_kind,
            "has_transport_plan": bool(transport_plan),
            "has_path": bool(plan["layer"]["path"]),
            "warnings": warnings,
        }
        return (_json(plan), manifest_line, _json(summary))
