import json
import re
from typing import Any, Dict, List, Tuple

from .host_bridge_shared import clean_text, parse_json_object
from .settings_bundle import parse_settings_bool


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

_TOML_ESCAPES = {
    "\\": "\\\\",
    "\"": "\\\"",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


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


def parse_builder_manifest(raw_json: str) -> Tuple[Dict[str, Any], List[str]]:
    payload, warnings = parse_json_object(raw_json, "builder_manifest_json")
    if not payload:
        warnings.append("builder_manifest_json did not include any manifest data")
    return (payload, warnings)


def derive_project_name(package_name: str, extension_name: str) -> str:
    package_text = clean_text(package_name)
    if "." in package_text:
        package_text = package_text.split(".", 1)[1]
    return clean_text(package_text) or clean_text(extension_name).lower().replace(" ", "-") or "mkrshift-nodes"


def normalize_string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    items: List[str] = []
    seen = set()
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def derive_repository_urls(repository_url: str, documentation_url: str = "", bug_tracker_url: str = "") -> Tuple[str, str]:
    repository = clean_text(repository_url)
    documentation = clean_text(documentation_url)
    bug_tracker = clean_text(bug_tracker_url)

    if repository.startswith("https://github.com/"):
        if not documentation:
            documentation = repository.rstrip("/") + "/wiki"
        if not bug_tracker:
            bug_tracker = repository.rstrip("/") + "/issues"
    return (documentation, bug_tracker)


def normalize_requires_comfyui(value: str) -> str:
    token = clean_text(value)
    if not token:
        return ""
    if token.startswith((">=", "<=", "==", "!=", "~=", ">", "<")):
        return token
    return f">={token}"


def should_include_v3_dependency(options: Dict[str, Any], extras: Dict[str, Any]) -> bool:
    if "include_v3_optional_dependency" in options:
        return parse_settings_bool(options.get("include_v3_optional_dependency"), False)
    return parse_settings_bool(extras.get("supports_v3_companions"), False)


def toml_string(value: str) -> str:
    text = str(value)
    escaped = "".join(_TOML_ESCAPES.get(char, char) for char in text)
    return f"\"{escaped}\""
