import json
from typing import Any, Dict, Tuple

from ..categories import ADDONS_AFFINITY, ADDONS_FUSION360, ADDONS_MAYA
from ..lib.host_bridge_shared import attach_transport_plan, clean_text, parse_transport_plan, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRAffinityDocumentImport:
    SEARCH_ALIASES = ["affinity import", "affinity document", "affinity bridge"]
    CATEGORY = ADDONS_AFFINITY
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("affinity_packet_json", "layer_manifest_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"affinity_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, affinity_payload_json: str) -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(affinity_payload_json, "affinity_payload_json")
        layers = payload.get("layers") if isinstance(payload.get("layers"), list) else []
        packet = {"schema": "mkrshift_affinity_bridge_v1", "document_name": clean_text(payload.get("document_name")) or "Untitled.afphoto", "persona": clean_text(payload.get("persona")) or "", "layers": layers}
        return (_json(packet), _json({"layers": layers}), _json({"document_name": packet["document_name"], "layer_count": len(layers), "warnings": warnings}))


class MKRAffinityExportPlan:
    SEARCH_ALIASES = ["affinity export", "affinity plan", "affinity layer plan"]
    CATEGORY = ADDONS_AFFINITY
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("affinity_export_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "target_layer_name": ("STRING", {"default": "MKRShift Result"}),
                "placement_mode": (["new_layer", "replace_layer"], {"default": "new_layer"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, target_layer_name: str = "MKRShift Result", placement_mode: str = "new_layer", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_affinity_export_plan_v1",
            "asset_path": clean_text(asset_path),
            "target_layer_name": clean_text(target_layer_name) or "MKRShift Result",
            "placement_mode": placement_mode,
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_layer_name"], placement_mode, plan["asset_path"]]), _json({"target_layer_name": plan["target_layer_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))


class MKRAffinityPhotoshopPluginPlan:
    SEARCH_ALIASES = ["affinity photoshop plugin", "affinity ps plugin", "affinity plugin plan", "affinity plugin bridge"]
    CATEGORY = ADDONS_AFFINITY
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("affinity_plugin_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plugin_name": ("STRING", {"default": "MKRShift Photoshop Filter"}),
                "plugin_kind": (["filter", "automation", "import_export"], {"default": "filter"}),
                "plugin_search_folder": ("STRING", {"default": ""}),
                "plugin_support_folder": ("STRING", {"default": ""}),
                "asset_path": ("STRING", {"default": ""}),
                "handoff_mode": (["ps_plugin_filter", "ps_plugin_io", "psd_roundtrip"], {"default": "ps_plugin_filter"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(
        self,
        plugin_name: str = "MKRShift Photoshop Filter",
        plugin_kind: str = "filter",
        plugin_search_folder: str = "",
        plugin_support_folder: str = "",
        asset_path: str = "",
        handoff_mode: str = "ps_plugin_filter",
        transport_plan_json: str = "",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan(
            {
                "schema": "mkrshift_affinity_photoshop_plugin_plan_v1",
                "plugin_name": clean_text(plugin_name) or "MKRShift Photoshop Filter",
                "plugin_kind": plugin_kind,
                "plugin_search_folder": clean_text(plugin_search_folder),
                "plugin_support_folder": clean_text(plugin_support_folder),
                "asset_path": clean_text(asset_path),
                "asset_slug": slugify(asset_path, "asset"),
                "handoff_mode": handoff_mode,
                "notes": clean_text(notes),
            },
            "file",
            transport_plan,
        )
        manifest_line = ",".join(
            [
                plan["plugin_name"],
                plan["plugin_kind"],
                plan["handoff_mode"],
                plan["asset_path"],
            ]
        )
        summary = {
            "plugin_name": plan["plugin_name"],
            "plugin_kind": plan["plugin_kind"],
            "handoff_mode": plan["handoff_mode"],
            "has_search_folder": bool(plan["plugin_search_folder"]),
            "has_support_folder": bool(plan["plugin_support_folder"]),
            "has_transport_plan": bool(transport_plan),
            "has_path": bool(plan["asset_path"]),
            "warnings": warnings,
        }
        return (_json(plan), manifest_line, _json(summary))


class MKRFusion360SceneImport:
    SEARCH_ALIASES = ["fusion 360 import", "fusion scene", "fusion bridge"]
    CATEGORY = ADDONS_FUSION360
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("fusion_packet_json", "view_context_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"fusion_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, fusion_payload_json: str) -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(fusion_payload_json, "fusion_payload_json")
        packet = {
            "schema": "mkrshift_fusion360_bridge_v1",
            "document_name": clean_text(payload.get("document_name")) or "Fusion Document",
            "design_name": clean_text(payload.get("design_name")) or "",
            "camera_name": clean_text(payload.get("camera_name")) or "Named View",
            "visual_style": clean_text(payload.get("visual_style")) or "",
        }
        return (_json(packet), _json({"camera_name": packet["camera_name"], "visual_style": packet["visual_style"]}), _json({"document_name": packet["document_name"], "warnings": warnings}))


class MKRFusion360TexturePlan:
    SEARCH_ALIASES = ["fusion 360 texture", "fusion material plan", "fusion return"]
    CATEGORY = ADDONS_FUSION360
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("fusion_texture_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "target_appearance_name": ("STRING", {"default": "MKRShift Appearance"}),
                "apply_mode": (["decal", "appearance_texture", "canvas_reference"], {"default": "decal"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, target_appearance_name: str = "MKRShift Appearance", apply_mode: str = "decal", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_fusion360_texture_plan_v1",
            "asset_path": clean_text(asset_path),
            "asset_slug": slugify(asset_path, "asset"),
            "target_appearance_name": clean_text(target_appearance_name) or "MKRShift Appearance",
            "apply_mode": apply_mode,
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_appearance_name"], apply_mode, plan["asset_path"]]), _json({"target_appearance_name": plan["target_appearance_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))


class MKRMayaSceneImport:
    SEARCH_ALIASES = ["maya import", "maya scene", "maya bridge"]
    CATEGORY = ADDONS_MAYA
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("maya_packet_json", "camera_json", "material_manifest_json", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"maya_payload_json": ("STRING", {"default": "", "multiline": True})}}

    def build(self, maya_payload_json: str) -> Tuple[str, str, str, str]:
        payload, warnings = parse_json_object(maya_payload_json, "maya_payload_json")
        materials = payload.get("materials") if isinstance(payload.get("materials"), list) else []
        camera = payload.get("camera") if isinstance(payload.get("camera"), dict) else {}
        packet = {"schema": "mkrshift_maya_bridge_v1", "scene_name": clean_text(payload.get("scene_name")) or "untitled.ma", "workspace": clean_text(payload.get("workspace")) or "", "camera": camera, "materials": materials}
        return (_json(packet), _json(camera), _json({"materials": materials}), _json({"scene_name": packet["scene_name"], "material_count": len(materials), "warnings": warnings}))


class MKRMayaMaterialPlan:
    SEARCH_ALIASES = ["maya material plan", "maya shader plan", "maya return"]
    CATEGORY = ADDONS_MAYA
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("maya_material_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_path": ("STRING", {"default": ""}),
                "target_shader_name": ("STRING", {"default": "MKRShiftShader"}),
                "target_object_name": ("STRING", {"default": ""}),
                "apply_mode": (["file_texture", "aiStandardSurface", "viewport_preview"], {"default": "file_texture"}),
            },
            "optional": {
                "transport_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def build(self, asset_path: str, target_shader_name: str = "MKRShiftShader", target_object_name: str = "", apply_mode: str = "file_texture", transport_plan_json: str = "") -> Tuple[str, str, str]:
        transport_plan, warnings = parse_transport_plan(transport_plan_json)
        plan = attach_transport_plan({
            "schema": "mkrshift_maya_material_plan_v1",
            "asset_path": clean_text(asset_path),
            "target_shader_name": clean_text(target_shader_name) or "MKRShiftShader",
            "target_object_name": clean_text(target_object_name),
            "apply_mode": apply_mode,
        }, "file", transport_plan)
        return (_json(plan), ",".join([plan["target_shader_name"], plan["target_object_name"], apply_mode, plan["asset_path"]]), _json({"target_shader_name": plan["target_shader_name"], "has_path": bool(plan["asset_path"]), "has_transport_plan": bool(transport_plan), "warnings": warnings}))
