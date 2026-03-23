from __future__ import annotations

from typing import Any, Dict, List


def _round_list(values: Any, digits: int = 6) -> List[float]:
    seq = values if isinstance(values, (list, tuple)) else []
    return [round(float(value), digits) for value in seq]


def build_camera_payload(camera_object, scene) -> Dict[str, Any]:
    camera_data = getattr(camera_object, "data", None)
    render = getattr(scene, "render", None)
    return {
        "name": getattr(camera_object, "name", "Camera"),
        "type": getattr(camera_data, "type", "PERSP"),
        "lens_mm": getattr(camera_data, "lens", 50.0),
        "sensor_width_mm": getattr(camera_data, "sensor_width", 36.0),
        "sensor_height_mm": getattr(camera_data, "sensor_height", 24.0),
        "clip_start": getattr(camera_data, "clip_start", 0.1),
        "clip_end": getattr(camera_data, "clip_end", 1000.0),
        "shift_x": getattr(camera_data, "shift_x", 0.0),
        "shift_y": getattr(camera_data, "shift_y", 0.0),
        "location": _round_list(getattr(camera_object, "location", (0.0, 0.0, 0.0))),
        "rotation_euler_deg": [round(value * 57.2957795, 6) for value in getattr(camera_object, "rotation_euler", (0.0, 0.0, 0.0))],
        "rotation_quaternion": _round_list(getattr(camera_object, "rotation_quaternion", (1.0, 0.0, 0.0, 0.0))),
        "resolution": {
            "x": int(getattr(render, "resolution_x", 1920)),
            "y": int(getattr(render, "resolution_y", 1080)),
            "percentage": int(getattr(render, "resolution_percentage", 100)),
        },
    }


def build_pose_payload(armature_object) -> Dict[str, Any]:
    pose = getattr(armature_object, "pose", None)
    bones_payload: List[Dict[str, Any]] = []
    for pose_bone in getattr(pose, "bones", []):
        bones_payload.append(
            {
                "name": getattr(pose_bone, "name", "Bone"),
                "parent": getattr(getattr(pose_bone, "parent", None), "name", ""),
                "head": _round_list(getattr(pose_bone, "head", (0.0, 0.0, 0.0))),
                "tail": _round_list(getattr(pose_bone, "tail", (0.0, 0.0, 0.0))),
                "location": _round_list(getattr(pose_bone, "location", (0.0, 0.0, 0.0))),
                "rotation_mode": getattr(pose_bone, "rotation_mode", "XYZ"),
                "rotation_euler_deg": [round(value * 57.2957795, 6) for value in getattr(pose_bone, "rotation_euler", (0.0, 0.0, 0.0))],
                "rotation_quaternion": _round_list(getattr(pose_bone, "rotation_quaternion", (1.0, 0.0, 0.0, 0.0))),
                "scale": _round_list(getattr(pose_bone, "scale", (1.0, 1.0, 1.0))),
            }
        )
    return {
        "armature_name": getattr(armature_object, "name", "Armature"),
        "bones": bones_payload,
    }


def _resolve_active_material(context):
    active_object = getattr(context, "active_object", None)
    if not active_object:
        return (None, None)
    material = getattr(active_object, "active_material", None)
    return (active_object, material)


def _image_texture_entries(material) -> List[Dict[str, Any]]:
    node_tree = getattr(material, "node_tree", None)
    if not node_tree:
        return []
    entries: List[Dict[str, Any]] = []
    for node in getattr(node_tree, "nodes", []):
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        if not image:
            continue
        path = getattr(image, "filepath", "") or getattr(image, "filepath_raw", "")
        entries.append(
            {
                "slot": getattr(node, "label", "") or getattr(node, "name", "") or "image",
                "path": path,
                "colorspace": getattr(getattr(image, "colorspace_settings", None), "name", "sRGB"),
                "uv_map": "",
            }
        )
    return entries


def _resolve_active_image(context):
    space_data = getattr(context, "space_data", None)
    image = getattr(space_data, "image", None)
    if image:
        return image

    _, material = _resolve_active_material(context)
    if material is None:
        return None
    for entry in _image_texture_entries(material):
        path = entry.get("path")
        if path:
            try:
                import bpy  # type: ignore

                return bpy.data.images.load(path, check_existing=True)
            except Exception:
                continue
    return None


def build_material_payload(context) -> Dict[str, Any]:
    active_object, material = _resolve_active_material(context)
    if material is None:
        return {"name": "", "textures": []}
    return {
        "name": getattr(material, "name", "Material"),
        "object_name": getattr(active_object, "name", ""),
        "blend_method": getattr(material, "blend_method", "OPAQUE"),
        "shadow_method": getattr(material, "shadow_method", "OPAQUE"),
        "use_backface_culling": bool(getattr(material, "use_backface_culling", False)),
        "base_color": _round_list(getattr(material, "diffuse_color", (1.0, 1.0, 1.0, 1.0))),
        "metallic": float(getattr(material, "metallic", 0.0)),
        "roughness": float(getattr(material, "roughness", 0.5)),
        "specular_ior_level": float(getattr(material, "specular_intensity", 0.5)),
        "emission_color": _round_list(getattr(material, "line_color", (0.0, 0.0, 0.0, 1.0))),
        "emission_strength": 0.0,
        "normal_strength": 1.0,
        "alpha": float(getattr(material, "diffuse_color", (1.0, 1.0, 1.0, 1.0))[3]),
        "textures": _image_texture_entries(material),
    }


def build_image_payload(context) -> Dict[str, Any]:
    image = _resolve_active_image(context)
    if image is None:
        return {"name": "", "path": "", "kind": "image"}
    path = getattr(image, "filepath", "") or getattr(image, "filepath_raw", "")
    size = getattr(image, "size", (0, 0))
    return {
        "schema": "mkrshift_blender_image_v1",
        "name": getattr(image, "name", "Image"),
        "path": path,
        "kind": "image",
        "colorspace": getattr(getattr(image, "colorspace_settings", None), "name", "sRGB"),
        "width": int(size[0] if len(size) > 0 else 0),
        "height": int(size[1] if len(size) > 1 else 0),
    }


def build_scene_packet(context) -> Dict[str, Any]:
    scene = context.scene
    camera_object = getattr(scene, "camera", None)
    active_object = getattr(context, "active_object", None)
    armature_object = active_object if getattr(active_object, "type", "") == "ARMATURE" else None
    return {
        "schema": "mkrshift_blender_bridge_v1",
        "schema_version": 1,
        "source": "mkrshift_blender_bridge",
        "scene_name": getattr(scene, "name", "Scene"),
        "frame_current": int(getattr(scene, "frame_current", 1)),
        "camera": build_camera_payload(camera_object, scene) if camera_object else {},
        "pose": build_pose_payload(armature_object) if armature_object else {"armature_name": "", "bones": []},
        "passes": [],
    }
