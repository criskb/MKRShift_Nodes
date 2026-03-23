import json
from typing import Any, Dict, Tuple

from ..categories import ADDONS_AFTER_EFFECTS, ADDONS_PHOTOSHOP, ADDONS_PREMIERE_PRO
from ..lib.host_bridge_shared import attach_transport_plan, clean_text, parse_transport_plan, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRPhotoshopDocumentImport:
    SEARCH_ALIASES = ["photoshop import", "photoshop bridge", "psd import", "uxp bridge"]
    CATEGORY = ADDONS_PHOTOSHOP
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("photoshop_packet_json", "layer_manifest_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"photoshop_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, photoshop_payload_json: str) -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(photoshop_payload_json, "photoshop_payload_json")
        layers = payload.get("layers") if isinstance(payload.get("layers"), list) else []
        packet = {
            "schema": "mkrshift_photoshop_bridge_v1",
            "document_name": clean_text(payload.get("document_name")) or "Untitled.psd",
            "width": int(payload.get("width", 0) or 0),
            "height": int(payload.get("height", 0) or 0),
            "color_mode": clean_text(payload.get("color_mode")) or "RGB",
            "layers": layers,
        }
        return (_json(packet), _json({"layers": layers}), _json({"document_name": packet["document_name"], "layer_count": len(layers), "warnings": warnings}))


class MKRPhotoshopExportPlan:
    SEARCH_ALIASES = ["photoshop export", "photoshop plan", "psd plan", "photoshop return"]
    CATEGORY = ADDONS_PHOTOSHOP
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("photoshop_export_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "target_layer_name": ("STRING", {"default": "MKRShift Result"}),
                "placement_mode": (["new_layer", "smart_object", "replace_layer"], {"default": "new_layer"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, target_layer_name: str = "MKRShift Result", placement_mode: str = "new_layer", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_photoshop_export_plan_v1",
            "asset_path": clean_text(asset_path),
            "asset_slug": slugify(asset_path, "asset"),
            "target_layer_name": clean_text(target_layer_name) or "MKRShift Result",
            "placement_mode": placement_mode,
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_layer_name"], placement_mode, plan["asset_path"]]), _json({"target_layer_name": plan["target_layer_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))


class MKRAfterEffectsCompImport:
    SEARCH_ALIASES = ["after effects import", "ae comp import", "ae bridge"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("ae_packet_json", "render_context_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"after_effects_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, after_effects_payload_json: str) -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(after_effects_payload_json, "after_effects_payload_json")
        packet = {
            "schema": "mkrshift_after_effects_bridge_v1",
            "project_name": clean_text(payload.get("project_name")) or "Untitled.aep",
            "comp_name": clean_text(payload.get("comp_name")) or "Comp 1",
            "width": int(payload.get("width", 0) or 0),
            "height": int(payload.get("height", 0) or 0),
            "fps": float(payload.get("fps", 0.0) or 0.0),
            "duration": float(payload.get("duration", 0.0) or 0.0),
        }
        ctx = {"comp_name": packet["comp_name"], "fps": packet["fps"], "duration": packet["duration"]}
        return (_json(packet), _json(ctx), _json({"comp_name": packet["comp_name"], "project_name": packet["project_name"], "warnings": warnings}))


class MKRAfterEffectsRenderPlan:
    SEARCH_ALIASES = ["after effects render plan", "ae output", "ae render queue"]
    CATEGORY = ADDONS_AFTER_EFFECTS
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("ae_render_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "import_mode": (["footage", "replace_layer", "precomp_source"], {"default": "footage"}),
                "target_comp_name": ("STRING", {"default": "Comp 1"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, import_mode: str = "footage", target_comp_name: str = "Comp 1", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_after_effects_render_plan_v1",
            "asset_path": clean_text(asset_path),
            "import_mode": import_mode,
            "target_comp_name": clean_text(target_comp_name) or "Comp 1",
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_comp_name"], import_mode, plan["asset_path"]]), _json({"target_comp_name": plan["target_comp_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))


class MKRPremiereSequenceImport:
    SEARCH_ALIASES = ["premiere import", "premiere sequence", "premiere bridge"]
    CATEGORY = ADDONS_PREMIERE_PRO
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("premiere_packet_json", "clip_manifest_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"premiere_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, premiere_payload_json: str) -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(premiere_payload_json, "premiere_payload_json")
        clips = payload.get("clips") if isinstance(payload.get("clips"), list) else []
        packet = {
            "schema": "mkrshift_premiere_bridge_v1",
            "project_name": clean_text(payload.get("project_name")) or "Untitled.prproj",
            "sequence_name": clean_text(payload.get("sequence_name")) or "Sequence 01",
            "fps": float(payload.get("fps", 0.0) or 0.0),
            "resolution": clean_text(payload.get("resolution")) or "",
            "clips": clips,
        }
        return (_json(packet), _json({"clips": clips}), _json({"sequence_name": packet["sequence_name"], "clip_count": len(clips), "warnings": warnings}))


class MKRPremiereExportPlan:
    SEARCH_ALIASES = ["premiere export", "premiere plan", "premiere replacement"]
    CATEGORY = ADDONS_PREMIERE_PRO
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("premiere_export_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "apply_mode": (["new_track_item", "replace_clip", "graphics_panel"], {"default": "new_track_item"}),
                "target_sequence_name": ("STRING", {"default": "Sequence 01"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, apply_mode: str = "new_track_item", target_sequence_name: str = "Sequence 01", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_premiere_export_plan_v1",
            "asset_path": clean_text(asset_path),
            "apply_mode": apply_mode,
            "target_sequence_name": clean_text(target_sequence_name) or "Sequence 01",
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_sequence_name"], apply_mode, plan["asset_path"]]), _json({"target_sequence_name": plan["target_sequence_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))
