import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..categories import ADDONS_NETWORK
from ..lib.host_bridge_shared import clean_text, parse_json_object


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _diff_values(old: Any, new: Any, path: str, changes: List[Dict[str, Any]]) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        keys = sorted(set(old.keys()) | set(new.keys()))
        for key in keys:
            key_path = f"{path}.{key}" if path else str(key)
            if key not in old:
                changes.append({"path": key_path, "change": "added", "new": new[key]})
            elif key not in new:
                changes.append({"path": key_path, "change": "removed", "old": old[key]})
            else:
                _diff_values(old[key], new[key], key_path, changes)
        return
    if isinstance(old, list) and isinstance(new, list):
        limit = max(len(old), len(new))
        for index in range(limit):
            item_path = f"{path}[{index}]"
            if index >= len(old):
                changes.append({"path": item_path, "change": "added", "new": new[index]})
            elif index >= len(new):
                changes.append({"path": item_path, "change": "removed", "old": old[index]})
            else:
                _diff_values(old[index], new[index], item_path, changes)
        return
    if old != new:
        changes.append({"path": path or "$", "change": "changed", "old": old, "new": new})


class MKRJSONDiff:
    SEARCH_ALIASES = ["json diff", "payload diff", "bridge diff", "compare json"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json_old": ("STRING", {"default": "{}", "multiline": True}),
                "json_new": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("diff_json", "diff_lines", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, json_old: str = "{}", json_new: str = "{}") -> Tuple[str, str, str]:
        old_payload, old_warnings = parse_json_object(json_old, "json_old")
        new_payload, new_warnings = parse_json_object(json_new, "json_new")
        changes: List[Dict[str, Any]] = []
        _diff_values(old_payload, new_payload, "", changes)
        diff = {
            "schema": "mkrshift_json_diff_v1",
            "change_count": len(changes),
            "changes": changes,
        }
        diff_lines = "\n".join(f"{item['change'].upper():7} {item['path']}" for item in changes) or "NO CHANGES"
        summary = {
            "change_count": len(changes),
            "warnings": old_warnings + new_warnings,
        }
        return (_json(diff), diff_lines, _json(summary))


class MKRAddonStats:
    SEARCH_ALIASES = ["addon stats", "bridge stats", "endpoint stats", "payload stats"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "watch_path": ("STRING", {"default": ""}),
                "endpoint_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("stats_json", "stats_lines", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, payload_json: str = "{}", watch_path: str = "", endpoint_plan_json: str = "{}") -> Tuple[str, str, str]:
        payload, payload_warnings = parse_json_object(payload_json, "payload_json")
        endpoint_plan, endpoint_warnings = parse_json_object(endpoint_plan_json, "endpoint_plan_json")

        payload_text = clean_text(payload_json)
        watch_dir = Path(clean_text(watch_path)).expanduser() if clean_text(watch_path) else None
        watch_exists = bool(watch_dir and watch_dir.exists())
        watch_files = 0
        latest_mtime = 0.0
        if watch_dir and watch_dir.is_dir():
            for item in watch_dir.iterdir():
                if not item.is_file():
                    continue
                watch_files += 1
                latest_mtime = max(latest_mtime, item.stat().st_mtime)

        key_count = len(payload.keys()) if isinstance(payload, dict) else 0
        schema = clean_text(payload.get("schema")) if isinstance(payload, dict) else ""
        transport_protocol = clean_text((endpoint_plan.get("protocol") or endpoint_plan.get("transport_protocol") or endpoint_plan.get("transport")) if isinstance(endpoint_plan, dict) else "")
        stats = {
            "schema": "mkrshift_addon_stats_v1",
            "payload_bytes": len(payload_text.encode("utf-8")),
            "payload_key_count": key_count,
            "payload_schema": schema,
            "watch_path": str(watch_dir) if watch_dir else "",
            "watch_exists": watch_exists,
            "watch_file_count": watch_files,
            "watch_latest_epoch": latest_mtime,
            "watch_latest_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(latest_mtime)) if latest_mtime else "",
            "endpoint_base_url": clean_text(endpoint_plan.get("base_url")) if isinstance(endpoint_plan, dict) else "",
            "endpoint_protocol": transport_protocol,
        }
        stats_lines = "\n".join(
            [
                f"payload_bytes: {stats['payload_bytes']}",
                f"payload_key_count: {stats['payload_key_count']}",
                f"payload_schema: {stats['payload_schema'] or '-'}",
                f"watch_exists: {stats['watch_exists']}",
                f"watch_file_count: {stats['watch_file_count']}",
                f"endpoint_protocol: {stats['endpoint_protocol'] or '-'}",
            ]
        )
        summary = {
            "warnings": payload_warnings + endpoint_warnings,
            "has_watch_path": bool(watch_dir),
            "has_endpoint_plan": bool(endpoint_plan),
        }
        return (_json(stats), stats_lines, _json(summary))
