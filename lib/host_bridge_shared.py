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


def parse_transport_plan(raw: Any, field_name: str = "transport_plan_json") -> Tuple[Dict[str, Any], List[str]]:
    plan, warnings = parse_json_object(raw, field_name)
    if not plan:
        return ({}, warnings)
    protocol = clean_text(plan.get("protocol"))
    if not protocol:
        warnings.append(f"{field_name} did not include a protocol")
    return (plan, warnings)


def attach_transport_plan(plan: Dict[str, Any], transport: str, transport_plan: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(plan)
    merged["transport"] = clean_text(transport) or clean_text(merged.get("transport")) or "file"
    merged["transport_plan"] = transport_plan if isinstance(transport_plan, dict) else {}
    merged["transport_protocol"] = clean_text(merged["transport_plan"].get("protocol")) or merged["transport"]
    return merged


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


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _string_list(values: Any) -> List[str]:
    seq = values if isinstance(values, (list, tuple)) else []
    return [clean_text(value) for value in seq if clean_text(value)]


def _ratio_string(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "unknown"

    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a or 1

    div = _gcd(width, height)
    return f"{width // div}:{height // div}"


def normalize_touchdesigner_packet(payload: Any) -> Tuple[Dict[str, Any], List[str]]:
    source = payload if isinstance(payload, dict) else {}
    warnings: List[str] = []
    width = max(1, _int(source.get("width", 1920), 1920))
    height = max(1, _int(source.get("height", 1080), 1080))
    transport = clean_text(source.get("transport")) or "file"
    top_name = clean_text(source.get("top_name")) or "mkrshiftTOP"
    operator_path = clean_text(source.get("operator_path")) or "/project1/mkrshift_bridge1"
    controls = source.get("controls") if isinstance(source.get("controls"), dict) else {}
    textures_in = source.get("textures") if isinstance(source.get("textures"), list) else []
    textures = []
    for item in textures_in:
        if not isinstance(item, dict):
            continue
        textures.append(
            {
                "name": clean_text(item.get("name")) or "tex",
                "path": clean_text(item.get("path")),
                "type": clean_text(item.get("type")) or "TOP",
                "colorspace": clean_text(item.get("colorspace")) or "sRGB",
            }
        )
    packet = {
        "schema": "mkrshift_touchdesigner_bridge_v1",
        "schema_version": 1,
        "source": clean_text(source.get("source")) or "touchdesigner",
        "project_name": clean_text(source.get("project_name")) or "TouchDesigner",
        "tox_name": clean_text(source.get("tox_name")) or "MKRShiftBridge",
        "operator_path": operator_path,
        "transport": transport,
        "top_name": top_name,
        "frame": _int(source.get("frame", 1), 1),
        "fps": max(1.0, _float(source.get("fps", 60.0), 60.0)),
        "resolution": {
            "x": width,
            "y": height,
            "ratio": _ratio_string(width, height),
        },
        "controls": {clean_text(key): value for key, value in controls.items() if clean_text(key)},
        "tags": _string_list(source.get("tags")),
        "textures": textures,
        "spout_enabled": _bool(source.get("spout_enabled"), transport == "spout"),
        "ndi_enabled": _bool(source.get("ndi_enabled"), transport == "ndi"),
        "notes": clean_text(source.get("notes")),
    }
    if not textures:
        warnings.append("touchdesigner payload did not include any textures")
    return (packet, warnings)


def normalize_tixl_packet(payload: Any) -> Tuple[Dict[str, Any], List[str]]:
    source = payload if isinstance(payload, dict) else {}
    warnings: List[str] = []
    width = max(1, _int(source.get("width", 1920), 1920))
    height = max(1, _int(source.get("height", 1080), 1080))
    source_kind = clean_text(source.get("source_kind")) or "texture"
    transport = clean_text(source.get("transport")) or "file"
    layers_in = source.get("layers") if isinstance(source.get("layers"), list) else []
    layers = []
    for item in layers_in:
        if not isinstance(item, dict):
            continue
        layers.append(
            {
                "name": clean_text(item.get("name")) or "Layer",
                "path": clean_text(item.get("path")),
                "kind": clean_text(item.get("kind")) or source_kind,
                "blend_mode": clean_text(item.get("blend_mode")) or "Alpha",
            }
        )
    packet = {
        "schema": "mkrshift_tixl_bridge_v1",
        "schema_version": 1,
        "source": clean_text(source.get("source")) or "tixl",
        "project_name": clean_text(source.get("project_name")) or "TiXL",
        "graph_name": clean_text(source.get("graph_name")) or "MKRShiftBridge",
        "operator_name": clean_text(source.get("operator_name")) or "MKRShiftComfyBridge",
        "transport": transport,
        "source_kind": source_kind,
        "bpm": max(1.0, _float(source.get("bpm", 120.0), 120.0)),
        "resolution": {
            "x": width,
            "y": height,
            "ratio": _ratio_string(width, height),
        },
        "layers": layers,
        "uses_ndi": _bool(source.get("uses_ndi"), transport == "ndi"),
        "uses_spout": _bool(source.get("uses_spout"), transport == "spout"),
        "uses_osc": _bool(source.get("uses_osc"), transport == "osc"),
        "notes": clean_text(source.get("notes")),
    }
    if not layers:
        warnings.append("tixl payload did not include any layers")
    return (packet, warnings)
