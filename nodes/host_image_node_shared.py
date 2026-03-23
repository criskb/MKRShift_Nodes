import json
from typing import Any, Dict, Tuple

from ..lib.host_bridge_shared import clean_text, parse_transport_plan
from ..lib.host_image_bridge_shared import (
    build_image_import_summary,
    build_live_image_output_plan,
    load_image_asset,
)


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class BaseHostImageImport:
    CATEGORY = ""
    SUMMARY_HOST = ""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"payload_json": ("STRING", {"default": "", "multiline": True})},
            "optional": {"preferred_slot": ("STRING", {"default": ""})},
        }

    def _build(self, payload_json: str, preferred_slot: str = "") -> Tuple[Any, Any, str, str, str]:
        payload, path, candidates, warnings = build_image_import_summary(payload_json, preferred_slot)
        if not path:
            raise ValueError("No image asset path found in payload_json")
        image, mask, info = load_image_asset(path)
        summary = {
            "host": self.SUMMARY_HOST,
            "asset_path": path,
            "preferred_slot": clean_text(preferred_slot),
            "candidate_count": len(candidates),
            "width": info["width"],
            "height": info["height"],
            "warnings": warnings,
        }
        return (image, mask, _json(payload), path, _json(summary))


def build_host_image_output_result(
    schema: str,
    host: str,
    asset_path: str,
    image_role: str,
    target_name: str,
    apply_mode: str,
    transport_plan_json: str,
    extra: Dict[str, Any],
) -> Tuple[str, str, str]:
    transport_plan, warnings = parse_transport_plan(transport_plan_json)
    plan = build_live_image_output_plan(
        schema,
        host,
        asset_path,
        image_role,
        target_name,
        apply_mode,
        transport_plan,
        extra,
    )
    manifest = ",".join([plan["host"], plan["image_role"], plan["apply_mode"], plan["target_name"], plan["asset_path"]])
    summary = {
        "host": host,
        "image_role": plan["image_role"],
        "apply_mode": plan["apply_mode"],
        "has_transport_plan": bool(transport_plan),
        "has_path": bool(plan["asset_path"]),
        "warnings": warnings,
    }
    return (_json(plan), manifest, _json(summary))
