import json
import re
from typing import Any, Dict, List, Tuple

from .host_bridge_shared import clean_text, parse_json_object


DEFAULT_EXTENSION_BUILDER_COMMAND = (
    "python3 /opt/codex/skills/.system/skill-installer/scripts/install-skill-from-github.py "
    "--repo criskb/comfyui-node-extension-builder --path . --name comfyui-node-extension-builder"
)

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ADVANCED_TEXT_KEYS = (
    "description",
    "repository",
    "license",
    "web_directory",
    "min_comfyui_version",
    "skill_url",
    "builder_cli_command",
)


def normalize_node_list(raw: str) -> Tuple[List[str], List[str]]:
    text = clean_text(raw)
    if not text:
        return ([], [])
    warnings: List[str] = []
    try:
        payload = json.loads(text)
    except Exception:
        return ([], ["node_list_json is not valid JSON"])
    if not isinstance(payload, list):
        return ([], ["node_list_json must be a JSON array"])

    nodes: List[str] = []
    seen = set()
    for index, value in enumerate(payload):
        if isinstance(value, dict):
            if bool(value.get("enabled", True)) is False:
                continue
            name = clean_text(value.get("name"))
        else:
            name = clean_text(value)
        if not name:
            warnings.append(f"node entry {index} is empty")
            continue
        if name in seen:
            continue
        seen.add(name)
        nodes.append(name)
    if not nodes:
        warnings.append("node_list_json did not include any node names")
    return (nodes, warnings)


def normalize_version(value: str) -> Tuple[str, List[str]]:
    version = clean_text(value) or "0.1.0"
    warnings: List[str] = []
    if not _SEMVER_PATTERN.match(version):
        warnings.append("version did not match semver and was reset to 0.1.0")
        return ("0.1.0", warnings)
    return (version, warnings)


def normalize_tags(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    tags: List[str] = []
    seen = set()
    for value in values:
        tag = clean_text(value)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def parse_tags_csv(raw: str) -> List[str]:
    tokens = []
    for part in str(raw or "").replace("\n", ",").split(","):
        token = clean_text(part)
        if token:
            tokens.append(token)
    return normalize_tags(tokens)


def build_advanced_options_payload(
    description: str = "",
    repository: str = "",
    license_name: str = "MIT",
    web_directory: str = "",
    min_comfyui_version: str = "",
    tags_csv: str = "",
    extras_json: str = "{}",
    skill_url: str = "",
    builder_cli_command: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    extras, warnings = parse_json_object(extras_json, "extras_json")
    payload: Dict[str, Any] = {
        "description": clean_text(description),
        "repository": clean_text(repository),
        "license": clean_text(license_name) or "MIT",
        "web_directory": clean_text(web_directory),
        "min_comfyui_version": clean_text(min_comfyui_version),
        "tags": parse_tags_csv(tags_csv),
        "skill_url": clean_text(skill_url),
        "builder_cli_command": clean_text(builder_cli_command),
        "extras": extras if isinstance(extras, dict) else {},
    }
    return ({key: value for key, value in payload.items() if value not in ("", [], {})}, warnings)


def merge_advanced_options(raw_json: str, bundle_json: str = "") -> Tuple[Dict[str, Any], List[str], bool]:
    inline, inline_warnings = parse_json_object(raw_json, "advanced_options_json")
    bundle, bundle_warnings = parse_json_object(bundle_json, "advanced_bundle_json")
    warnings = [*inline_warnings, *bundle_warnings]

    merged: Dict[str, Any] = {}
    for key in _ADVANCED_TEXT_KEYS:
        bundle_value = clean_text(bundle.get(key))
        inline_value = clean_text(inline.get(key))
        value = bundle_value or inline_value
        if value:
            merged[key] = value

    merged_tags = normalize_tags(inline.get("tags")) + normalize_tags(bundle.get("tags"))
    merged["tags"] = normalize_tags(merged_tags)

    extras: Dict[str, Any] = {}
    if isinstance(inline.get("extras"), dict):
        extras.update(inline["extras"])
    if isinstance(bundle.get("extras"), dict):
        extras.update(bundle["extras"])
    merged["extras"] = extras

    return (merged, warnings, bool(clean_text(bundle_json)))
