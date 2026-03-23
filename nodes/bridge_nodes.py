import json
from typing import Any, Dict, Tuple

from ..categories import BRIDGE_BLENDER
from ..lib.blender_bridge_shared import (
    camera_prompt_from_payload,
    clean_text,
    lens_bucket,
    normalize_material_payload,
    normalize_scene_packet,
    parse_json_object,
    slugify,
)


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRBlenderSceneImport:
    SEARCH_ALIASES = [
        "blender bridge",
        "blender scene import",
        "camera payload",
        "pose payload",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bridge_payload_json": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "character_state_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("scene_packet_json", "camera_json", "pose_json", "camera_prompt", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_BLENDER

    def build(self, bridge_payload_json: str, character_state_json: str = "") -> Tuple[str, str, str, str, str]:
        payload, warnings = parse_json_object(bridge_payload_json, "bridge_payload_json")
        packet, normalize_warnings = normalize_scene_packet(payload)
        warnings.extend(normalize_warnings)

        subject_name = ""
        character_payload, _ = parse_json_object(character_state_json, "character_state_json")
        if character_payload:
            subject_name = clean_text(character_payload.get("character_name"))

        camera_prompt = camera_prompt_from_payload(packet["camera"], subject_name=subject_name)
        summary = {
            "scene_name": packet["scene_name"],
            "frame_current": packet["frame_current"],
            "camera_name": packet["camera"]["name"],
            "lens_mm": packet["camera"]["lens_mm"],
            "resolution_ratio": packet["camera"]["resolution"]["ratio"],
            "pose_bone_count": packet["pose"]["bone_count"],
            "pass_count": len(packet["passes"]),
            "warnings": warnings,
        }
        return (
            _json(packet),
            _json(packet["camera"]),
            _json(packet["pose"]),
            camera_prompt,
            _json(summary),
        )


class MKRBlenderCameraShot:
    SEARCH_ALIASES = [
        "blender camera shot",
        "camera prompt from blender",
        "shot prompt",
        "camera bridge",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "camera_json": ("STRING", {"default": "", "multiline": True}),
                "subject_name": ("STRING", {"default": ""}),
                "intent_hint": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("camera_prompt", "shot_recipe_json", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_BLENDER

    def build(self, camera_json: str, subject_name: str = "", intent_hint: str = "") -> Tuple[str, str, str]:
        camera_payload, warnings = parse_json_object(camera_json, "camera_json")
        packet, normalize_warnings = normalize_scene_packet({"camera": camera_payload, "scene_name": "Camera Import"})
        warnings.extend(normalize_warnings)
        camera_payload = packet["camera"]
        camera_prompt = camera_prompt_from_payload(camera_payload, subject_name=subject_name, intent_hint=intent_hint)
        shot_recipe = {
            "schema": "mkrshift_blender_camera_shot_v1",
            "camera_name": camera_payload["name"],
            "lens_mm": camera_payload["lens_mm"],
            "lens_bucket": lens_bucket(float(camera_payload["lens_mm"])),
            "resolution": camera_payload["resolution"],
            "location": camera_payload["location"],
            "rotation_euler_deg": camera_payload["rotation_euler_deg"],
            "prompt": camera_prompt,
        }
        summary = {
            "camera_name": camera_payload["name"],
            "ratio": camera_payload["resolution"]["ratio"],
            "lens_mm": camera_payload["lens_mm"],
            "warnings": warnings,
        }
        return (camera_prompt, _json(shot_recipe), _json(summary))


class MKRBlenderReturnPlan:
    SEARCH_ALIASES = [
        "blender return plan",
        "bridge return",
        "send back to blender",
        "roundtrip plan",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "generated_asset_path": ("STRING", {"default": ""}),
                "asset_kind": (["image", "image_sequence", "video"], {"default": "image"}),
                "apply_mode": (["image_plane", "camera_background", "compositor_image", "texture_image"], {"default": "image_plane"}),
                "target_name": ("STRING", {"default": "MKRShift Result"}),
                "colorspace": (["sRGB", "Non-Color", "Linear"], {"default": "sRGB"}),
            },
            "optional": {
                "scene_packet_json": ("STRING", {"default": "", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("return_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_BLENDER

    def build(
        self,
        generated_asset_path: str,
        asset_kind: str = "image",
        apply_mode: str = "image_plane",
        target_name: str = "MKRShift Result",
        colorspace: str = "sRGB",
        scene_packet_json: str = "",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        packet_payload, warnings = parse_json_object(scene_packet_json, "scene_packet_json")
        scene_name = clean_text(packet_payload.get("scene_name")) or "Scene"
        frame_current = int(packet_payload.get("frame_current", 1) or 1)
        target = clean_text(target_name) or "MKRShift Result"
        output_path = clean_text(generated_asset_path)
        plan = {
            "schema": "mkrshift_blender_return_plan_v1",
            "scene_name": scene_name,
            "frame_current": frame_current,
            "asset": {
                "path": output_path,
                "kind": asset_kind,
                "apply_mode": apply_mode,
                "colorspace": colorspace,
            },
            "target_name": target,
            "target_slug": slugify(target, "mkrshift-result"),
            "notes": clean_text(notes),
        }
        manifest_line = f"{scene_name},{frame_current},{asset_kind},{apply_mode},{target},{output_path}"
        summary = {
            "scene_name": scene_name,
            "frame_current": frame_current,
            "asset_kind": asset_kind,
            "apply_mode": apply_mode,
            "target_name": target,
            "has_path": bool(output_path),
            "warnings": warnings,
        }
        return (_json(plan), manifest_line, _json(summary))


class MKRBlenderMaterialImport:
    SEARCH_ALIASES = [
        "blender material import",
        "bridge material import",
        "material payload",
        "blender shader import",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "material_payload_json": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("material_json", "material_prompt", "texture_manifest_json", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_BLENDER

    def build(self, material_payload_json: str) -> Tuple[str, str, str, str]:
        payload, warnings = parse_json_object(material_payload_json, "material_payload_json")
        material = normalize_material_payload(payload)
        texture_manifest = {
            "schema": "mkrshift_blender_material_manifest_v1",
            "material_name": material["name"],
            "texture_count": len(material["textures"]),
            "textures": material["textures"],
        }
        material_prompt_parts = [
            "blender material match",
            clean_text(material.get("name")),
            f"roughness {float(material.get('roughness', 0.5)):.2f}",
            f"metallic {float(material.get('metallic', 0.0)):.2f}",
        ]
        if float(material.get("emission_strength", 0.0)) > 0.001:
            material_prompt_parts.append("emissive")
        if clean_text(material.get("blend_method")) not in {"", "OPAQUE"}:
            material_prompt_parts.append(clean_text(material.get("blend_method")).lower())
        material_prompt = ", ".join(part for part in material_prompt_parts if clean_text(part))
        summary = {
            "material_name": material["name"],
            "blend_method": material["blend_method"],
            "texture_count": len(material["textures"]),
            "warnings": warnings,
        }
        return (_json(material), material_prompt, _json(texture_manifest), _json(summary))


class MKRBlenderMaterialReturnPlan:
    SEARCH_ALIASES = [
        "blender material return",
        "material return plan",
        "bridge material output",
        "send material to blender",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "material_name": ("STRING", {"default": "MKRShift Material"}),
                "base_color_path": ("STRING", {"default": ""}),
                "normal_path": ("STRING", {"default": ""}),
                "roughness_path": ("STRING", {"default": ""}),
                "metallic_path": ("STRING", {"default": ""}),
                "emission_path": ("STRING", {"default": ""}),
                "alpha_path": ("STRING", {"default": ""}),
                "target_object_name": ("STRING", {"default": ""}),
                "target_material_slot": ("STRING", {"default": ""}),
            },
            "optional": {
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("material_return_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = BRIDGE_BLENDER

    def build(
        self,
        material_name: str = "MKRShift Material",
        base_color_path: str = "",
        normal_path: str = "",
        roughness_path: str = "",
        metallic_path: str = "",
        emission_path: str = "",
        alpha_path: str = "",
        target_object_name: str = "",
        target_material_slot: str = "",
        notes: str = "",
    ) -> Tuple[str, str, str]:
        textures = {
            "base_color": clean_text(base_color_path),
            "normal": clean_text(normal_path),
            "roughness": clean_text(roughness_path),
            "metallic": clean_text(metallic_path),
            "emission": clean_text(emission_path),
            "alpha": clean_text(alpha_path),
        }
        plan = {
            "schema": "mkrshift_blender_material_return_plan_v1",
            "material_name": clean_text(material_name) or "MKRShift Material",
            "target_object_name": clean_text(target_object_name),
            "target_material_slot": clean_text(target_material_slot),
            "textures": textures,
            "notes": clean_text(notes),
        }
        manifest_line = ",".join([
            plan["material_name"],
            plan["target_object_name"],
            plan["target_material_slot"],
            textures["base_color"],
            textures["normal"],
            textures["roughness"],
            textures["metallic"],
            textures["emission"],
            textures["alpha"],
        ])
        summary = {
            "material_name": plan["material_name"],
            "target_object_name": plan["target_object_name"],
            "target_material_slot": plan["target_material_slot"],
            "texture_count": sum(1 for value in textures.values() if value),
            "has_base_color": bool(textures["base_color"]),
            "has_normal": bool(textures["normal"]),
        }
        return (_json(plan), manifest_line, _json(summary))
