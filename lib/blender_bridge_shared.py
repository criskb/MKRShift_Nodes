import json
from typing import Any, Dict, List, Tuple


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def slugify(value: Any, fallback: str = "item") -> str:
    text = clean_text(value).lower()
    out = []
    prev_dash = False
    for char in text:
        if char.isalnum():
            out.append(char)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    slug = "".join(out).strip("-")
    return slug or fallback


def parse_json_object(raw: Any, field_name: str) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    text = clean_text(raw)
    if not text:
        return ({}, warnings)
    try:
        payload = json.loads(text)
    except Exception:
        warnings.append(f"{field_name} is not valid JSON")
        return ({}, warnings)
    if not isinstance(payload, dict):
        warnings.append(f"{field_name} must be a JSON object")
        return ({}, warnings)
    return (payload, warnings)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _round_list(values: Any, length: int, default: float = 0.0, digits: int = 6) -> List[float]:
    seq = values if isinstance(values, (list, tuple)) else []
    out: List[float] = []
    for idx in range(length):
        source = seq[idx] if idx < len(seq) else default
        out.append(round(_float(source, default), digits))
    return out


def _ratio_string(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "unknown"
    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a or 1
    div = _gcd(width, height)
    return f"{width // div}:{height // div}"


def normalize_camera_payload(camera_payload: Any) -> Dict[str, Any]:
    payload = camera_payload if isinstance(camera_payload, dict) else {}
    resolution = payload.get("resolution") if isinstance(payload.get("resolution"), dict) else {}
    width = max(1, _int(payload.get("resolution_x", resolution.get("x", 1920)), 1920))
    height = max(1, _int(payload.get("resolution_y", resolution.get("y", 1080)), 1080))
    lens_mm = round(_float(payload.get("lens_mm", payload.get("lens", 50.0)), 50.0), 4)
    sensor_width = round(_float(payload.get("sensor_width_mm", payload.get("sensor_width", 36.0)), 36.0), 4)
    sensor_height = round(_float(payload.get("sensor_height_mm", payload.get("sensor_height", 24.0)), 24.0), 4)
    location = _round_list(payload.get("location"), 3, 0.0)
    rotation_euler = _round_list(payload.get("rotation_euler_deg", payload.get("rotation_euler")), 3, 0.0)
    rotation_quaternion = _round_list(payload.get("rotation_quaternion"), 4, 0.0)
    shift_x = round(_float(payload.get("shift_x", 0.0), 0.0), 6)
    shift_y = round(_float(payload.get("shift_y", 0.0), 0.0), 6)
    return {
        "name": clean_text(payload.get("name")) or "Camera",
        "type": clean_text(payload.get("type")) or "PERSP",
        "lens_mm": lens_mm,
        "sensor_width_mm": sensor_width,
        "sensor_height_mm": sensor_height,
        "clip_start": round(_float(payload.get("clip_start", 0.1), 0.1), 6),
        "clip_end": round(_float(payload.get("clip_end", 1000.0), 1000.0), 6),
        "shift_x": shift_x,
        "shift_y": shift_y,
        "location": location,
        "rotation_euler_deg": rotation_euler,
        "rotation_quaternion": rotation_quaternion,
        "resolution": {
            "x": width,
            "y": height,
            "ratio": _ratio_string(width, height),
            "percentage": max(1, _int(payload.get("resolution_percentage", resolution.get("percentage", 100)), 100)),
        },
    }


def normalize_pose_payload(pose_payload: Any) -> Dict[str, Any]:
    payload = pose_payload if isinstance(pose_payload, dict) else {}
    source_bones = payload.get("bones") if isinstance(payload.get("bones"), list) else []
    bones: List[Dict[str, Any]] = []
    for bone in source_bones:
        if not isinstance(bone, dict):
            continue
        bones.append(
            {
                "name": clean_text(bone.get("name")) or "Bone",
                "parent": clean_text(bone.get("parent")),
                "head": _round_list(bone.get("head"), 3, 0.0),
                "tail": _round_list(bone.get("tail"), 3, 0.0),
                "location": _round_list(bone.get("location"), 3, 0.0),
                "rotation_mode": clean_text(bone.get("rotation_mode")) or "XYZ",
                "rotation_euler_deg": _round_list(bone.get("rotation_euler_deg", bone.get("rotation_euler")), 3, 0.0),
                "rotation_quaternion": _round_list(bone.get("rotation_quaternion"), 4, 0.0),
                "scale": _round_list(bone.get("scale"), 3, 1.0),
            }
        )
    return {
        "armature_name": clean_text(payload.get("armature_name")) or "Armature",
        "bone_count": len(bones),
        "bones": bones,
    }


def normalize_passes_payload(raw_passes: Any) -> List[Dict[str, Any]]:
    items = raw_passes if isinstance(raw_passes, list) else []
    passes: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        passes.append(
            {
                "name": clean_text(item.get("name")) or "pass",
                "type": clean_text(item.get("type")) or "IMAGE",
                "path": clean_text(item.get("path")),
                "colorspace": clean_text(item.get("colorspace")) or "sRGB",
            }
        )
    return passes


def normalize_material_payload(material_payload: Any) -> Dict[str, Any]:
    payload = material_payload if isinstance(material_payload, dict) else {}
    texture_items = payload.get("textures") if isinstance(payload.get("textures"), list) else []
    textures: List[Dict[str, Any]] = []
    for item in texture_items:
        if not isinstance(item, dict):
            continue
        textures.append(
            {
                "slot": clean_text(item.get("slot")) or "image",
                "path": clean_text(item.get("path")),
                "colorspace": clean_text(item.get("colorspace")) or "sRGB",
                "uv_map": clean_text(item.get("uv_map")),
            }
        )
    return {
        "name": clean_text(payload.get("name")) or "Material",
        "blend_method": clean_text(payload.get("blend_method")) or "OPAQUE",
        "shadow_method": clean_text(payload.get("shadow_method")) or "OPAQUE",
        "use_backface_culling": bool(payload.get("use_backface_culling", False)),
        "base_color": _round_list(payload.get("base_color"), 4, 1.0),
        "metallic": round(_float(payload.get("metallic", 0.0), 0.0), 6),
        "roughness": round(_float(payload.get("roughness", 0.5), 0.5), 6),
        "specular_ior_level": round(_float(payload.get("specular_ior_level", payload.get("specular", 0.5)), 0.5), 6),
        "emission_color": _round_list(payload.get("emission_color"), 4, 0.0),
        "emission_strength": round(_float(payload.get("emission_strength", 0.0), 0.0), 6),
        "normal_strength": round(_float(payload.get("normal_strength", 1.0), 1.0), 6),
        "alpha": round(_float(payload.get("alpha", 1.0), 1.0), 6),
        "textures": textures,
    }


def lens_bucket(lens_mm: float) -> str:
    if lens_mm < 24:
        return "ultra-wide"
    if lens_mm < 35:
        return "wide"
    if lens_mm < 60:
        return "normal"
    if lens_mm < 100:
        return "portrait"
    return "telephoto"


def camera_prompt_from_payload(camera_payload: Dict[str, Any], subject_name: str = "", intent_hint: str = "") -> str:
    lens_mm = round(_float(camera_payload.get("lens_mm", 50.0), 50.0), 1)
    ratio = camera_payload.get("resolution", {}).get("ratio", "unknown")
    parts = [
        "blender camera match",
        clean_text(subject_name),
        f"{lens_bucket(lens_mm)} lens",
        f"{lens_mm:g}mm",
        f"{ratio} frame",
        clean_text(intent_hint),
    ]
    return ", ".join(part for part in parts if clean_text(part))


def normalize_scene_packet(payload: Any) -> Tuple[Dict[str, Any], List[str]]:
    packet = payload if isinstance(payload, dict) else {}
    warnings: List[str] = []
    camera_payload = normalize_camera_payload(packet.get("camera"))
    pose_payload = normalize_pose_payload(packet.get("pose"))
    material_payload = normalize_material_payload(packet.get("material"))
    passes_payload = normalize_passes_payload(packet.get("passes"))
    scene_name = clean_text(packet.get("scene_name")) or "Scene"
    frame_current = _int(packet.get("frame_current", 1), 1)
    packet_out = {
        "schema": "mkrshift_blender_bridge_v1",
        "schema_version": 1,
        "source": clean_text(packet.get("source")) or "blender_extension",
        "scene_name": scene_name,
        "scene_slug": slugify(scene_name, "scene"),
        "frame_current": frame_current,
        "camera": camera_payload,
        "pose": pose_payload,
        "material": material_payload,
        "passes": passes_payload,
    }
    if not clean_text(packet.get("scene_name")):
        warnings.append("scene_name was empty and fell back to Scene")
    if pose_payload["bone_count"] == 0:
        warnings.append("pose payload did not include any bones")
    return (packet_out, warnings)
