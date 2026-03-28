import json
from typing import Optional


def parse_settings_bool(value, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "on"}:
            return True
        if token in {"false", "0", "no", "off"}:
            return False
    return fallback


def parse_settings_payload(
    settings_json: str,
    defaults: dict,
    numeric_specs: Optional[dict] = None,
    boolean_keys: Optional[set[str]] = None,
    legacy: Optional[dict] = None,
) -> dict:
    payload = {}
    try:
        parsed = json.loads(str(settings_json or "{}"))
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}

    if isinstance(legacy, dict):
        for key, value in legacy.items():
            if key in defaults and key not in payload:
                payload[key] = value

    specs = numeric_specs or {}
    bool_keys = boolean_keys or set()
    settings = defaults.copy()

    for key, default in defaults.items():
        if key in specs:
            spec = specs[key]
            try:
                raw = float(payload.get(key, default))
            except Exception:
                raw = float(default)
            clamped = max(float(spec["min"]), min(float(spec["max"]), raw))
            settings[key] = int(round(clamped)) if spec.get("integer") else float(clamped)
        elif key in bool_keys:
            settings[key] = parse_settings_bool(payload.get(key), bool(default))
        elif key in payload:
            settings[key] = payload[key]

    return settings
