import json
from typing import Any, Dict, List, Tuple

from .host_bridge_shared import clean_text, parse_json_object, slugify


FIELD_TYPES = {"text", "multiline", "int", "float", "bool", "choice", "file_path", "json"}


def json_text(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    return text in {"1", "true", "yes", "on"}


def _coerce_number(value: Any, field_type: str) -> Any:
    try:
        return int(value) if field_type == "int" else float(value)
    except Exception:
        return 0 if field_type == "int" else 0.0


def normalize_workflow_fields(raw_fields_json: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    text = clean_text(raw_fields_json)
    if not text:
        return ([], warnings)
    try:
        payload = json.loads(text)
    except Exception:
        return ([], ["fields_json is not valid JSON"])
    if not isinstance(payload, list):
        return ([], ["fields_json must be a JSON array"])
    fields: List[Dict[str, Any]] = []
    seen_keys = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            warnings.append(f"field {index} is not an object")
            continue
        key = clean_text(item.get("key"))
        label = clean_text(item.get("label")) or key or f"Field {index + 1}"
        field_type = clean_text(item.get("type")).lower() or "text"
        if not key:
            warnings.append(f"field {index} did not include a key")
            continue
        if key in seen_keys:
            warnings.append(f"duplicate field key: {key}")
            continue
        seen_keys.add(key)
        if field_type not in FIELD_TYPES:
            warnings.append(f"field {key} used unsupported type {field_type}, defaulted to text")
            field_type = "text"
        raw_default = item.get("default")
        if field_type == "bool":
            default = _coerce_bool(raw_default)
        elif field_type in {"int", "float"}:
            default = _coerce_number(raw_default, field_type)
        else:
            default = clean_text(raw_default) if raw_default is not None else ""
        choices = item.get("choices") if isinstance(item.get("choices"), list) else []
        if field_type == "choice":
            choices = [clean_text(choice) for choice in choices if clean_text(choice)]
            if not choices:
                warnings.append(f"choice field {key} did not include any choices")
            if clean_text(default) and clean_text(default) not in choices:
                choices.insert(0, clean_text(default))
            default = clean_text(default) or (choices[0] if choices else "")
        field = {
            "key": key,
            "label": label,
            "type": field_type,
            "default": default,
            "group": clean_text(item.get("group")) or "Workflow",
            "help": clean_text(item.get("help")),
            "placeholder": clean_text(item.get("placeholder")),
            "min": item.get("min"),
            "max": item.get("max"),
            "step": item.get("step"),
            "choices": choices,
        }
        fields.append(field)
    return (fields, warnings)


def build_addon_workflow_interface(
    interface_name: str,
    workflow_id: str,
    host_family: str,
    fields_json: Any,
    output_targets_json: Any = "",
    notes: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    fields, warnings = normalize_workflow_fields(fields_json)
    output_targets, output_warnings = parse_json_object(output_targets_json, "output_targets_json")
    warnings.extend(output_warnings)
    name = clean_text(interface_name) or "MKRShift Workflow"
    workflow_name = clean_text(workflow_id) or slugify(name, "workflow")
    interface = {
        "schema": "mkrshift_addon_workflow_interface_v1",
        "interface_name": name,
        "interface_slug": slugify(name, "workflow-interface"),
        "workflow_id": workflow_name,
        "host_family": clean_text(host_family) or "generic",
        "fields": fields,
        "output_targets": output_targets,
        "notes": clean_text(notes),
    }
    return (interface, warnings)
