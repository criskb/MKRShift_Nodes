import json
import re
from typing import Any, Dict, List, Tuple

from ..categories import ADDONS_WORKFLOW
from ..lib.host_bridge_shared import clean_text, parse_json_object, slugify


_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _normalize_node_list(raw: str) -> Tuple[List[str], List[str]]:
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


def _normalize_version(value: str) -> Tuple[str, List[str]]:
    version = clean_text(value) or "0.1.0"
    warnings: List[str] = []
    if not _SEMVER_PATTERN.match(version):
        warnings.append("version did not match semver and was reset to 0.1.0")
        return ("0.1.0", warnings)
    return (version, warnings)


class MKRNodeExtensionBuilderPlan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "extension_name": ("STRING", {"default": "MKRShift Nodes"}),
                "publisher": ("STRING", {"default": "mkrshift"}),
                "version": ("STRING", {"default": "0.1.0"}),
                "entry_file": ("STRING", {"default": "__init__.py"}),
                "node_list_json": ("STRING", {"default": "[\"x1SharpenPro\", \"x1HeatHaze\"]", "multiline": True}),
                "advanced_options_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "Optional expert controls (tags, repository, web_directory, min_comfyui_version, description, and extras).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("builder_manifest_json", "builder_command", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_WORKFLOW

    def build(
        self,
        extension_name: str,
        publisher: str = "mkrshift",
        version: str = "0.1.0",
        entry_file: str = "__init__.py",
        node_list_json: str = "[]",
        advanced_options_json: str = "{}",
    ) -> Tuple[str, str, str]:
        nodes, node_warnings = _normalize_node_list(node_list_json)
        advanced, adv_warnings = parse_json_object(advanced_options_json, "advanced_options_json")
        version_text, version_warnings = _normalize_version(version)
        warnings = [*node_warnings, *adv_warnings, *version_warnings]

        name = clean_text(extension_name) or "MKRShift Nodes"
        publisher_id = slugify(publisher, "publisher")
        package_slug = slugify(name, "node-extension")
        entry = clean_text(entry_file) or "__init__.py"
        if not entry.endswith(".py"):
            warnings.append("entry_file should usually point to a Python file")

        manifest: Dict[str, Any] = {
            "schema": "comfyui_node_extension_builder_v1",
            "name": name,
            "package": f"{publisher_id}.{package_slug}",
            "publisher": publisher_id,
            "version": version_text,
            "entry": entry,
            "nodes": nodes,
            "description": clean_text(advanced.get("description")) or f"Node extension scaffold for {name}.",
            "web_directory": clean_text(advanced.get("web_directory")),
            "repository": clean_text(advanced.get("repository")),
            "license": clean_text(advanced.get("license")) or "MIT",
            "tags": [clean_text(tag) for tag in (advanced.get("tags") if isinstance(advanced.get("tags"), list) else []) if clean_text(tag)],
            "min_comfyui_version": clean_text(advanced.get("min_comfyui_version")),
            "extras": advanced.get("extras") if isinstance(advanced.get("extras"), dict) else {},
        }

        base_command = (
            "python3 /opt/codex/skills/.system/skill-installer/scripts/install-skill-from-github.py "
            "--repo criskb/comfyui-node-extension-builder --path . --name comfyui-node-extension-builder"
        )
        skill_url = clean_text(advanced.get("skill_url"))
        custom_builder_command = clean_text(advanced.get("builder_cli_command"))
        command = custom_builder_command or base_command

        summary = {
            "extension": manifest["name"],
            "package": manifest["package"],
            "node_count": len(nodes),
            "warnings": warnings,
            "has_web_directory": bool(manifest["web_directory"]),
            "has_repository": bool(manifest["repository"]),
            "skill_requested": bool(skill_url),
            "next_step": "Write builder_manifest_json to extension.builder.json and run your chosen builder CLI.",
        }
        return (
            json.dumps(manifest, ensure_ascii=False, indent=2),
            command,
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
