import json
from typing import Any, Dict, Tuple

from ..categories import ADDONS_WORKFLOW
from ..lib.extension_builder_shared import (
    DEFAULT_EXTENSION_BUILDER_COMMAND,
    build_advanced_options_payload,
    derive_project_name,
    derive_repository_urls,
    merge_advanced_options,
    normalize_node_list,
    normalize_requires_comfyui,
    normalize_string_list,
    normalize_tags,
    normalize_version,
    parse_builder_manifest,
    should_include_v3_dependency,
    toml_string,
)
from ..lib.host_bridge_shared import clean_text, parse_json_object, slugify


class MKRNodeExtensionBuilderAdvanced:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "description": ("STRING", {"default": "", "multiline": True}),
                "repository": ("STRING", {"default": ""}),
                "license_name": ("STRING", {"default": "MIT"}),
                "web_directory": ("STRING", {"default": ""}),
                "min_comfyui_version": ("STRING", {"default": ""}),
                "tags_csv": ("STRING", {"default": "comfyui, mkrshift"}),
                "extras_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "Optional expert-only extras object merged into the manifest extras payload.",
                    },
                ),
                "skill_url": ("STRING", {"default": ""}),
                "builder_cli_command": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("advanced_options_json", "summary_json")
    FUNCTION = "bundle"
    CATEGORY = ADDONS_WORKFLOW

    def bundle(
        self,
        description: str = "",
        repository: str = "",
        license_name: str = "MIT",
        web_directory: str = "",
        min_comfyui_version: str = "",
        tags_csv: str = "",
        extras_json: str = "{}",
        skill_url: str = "",
        builder_cli_command: str = "",
    ) -> Tuple[str, str]:
        payload, warnings = build_advanced_options_payload(
            description=description,
            repository=repository,
            license_name=license_name,
            web_directory=web_directory,
            min_comfyui_version=min_comfyui_version,
            tags_csv=tags_csv,
            extras_json=extras_json,
            skill_url=skill_url,
            builder_cli_command=builder_cli_command,
        )
        summary = {
            "keys": sorted(payload.keys()),
            "tag_count": len(payload.get("tags", [])),
            "has_extras": bool(payload.get("extras")),
            "warnings": warnings,
            "next_step": "Connect advanced_options_json to MKRNodeExtensionBuilderPlan.advanced_bundle_json.",
        }
        return (
            json.dumps(payload, ensure_ascii=False, indent=2),
            json.dumps(summary, ensure_ascii=False, indent=2),
        )


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
                        "tooltip": "Inline expert metadata JSON. For cleaner graphs, connect MKRNodeExtensionBuilderAdvanced into advanced_bundle_json instead.",
                    },
                ),
            },
            "optional": {
                "advanced_bundle_json": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional structured expert bundle from MKRNodeExtensionBuilderAdvanced.",
                    },
                ),
            },
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
        advanced_bundle_json: str = "",
    ) -> Tuple[str, str, str]:
        nodes, node_warnings = normalize_node_list(node_list_json)
        advanced, adv_warnings, used_advanced_bundle = merge_advanced_options(advanced_options_json, advanced_bundle_json)
        version_text, version_warnings = normalize_version(version)
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
            "tags": normalize_tags(advanced.get("tags")),
            "min_comfyui_version": clean_text(advanced.get("min_comfyui_version")),
            "extras": advanced.get("extras") if isinstance(advanced.get("extras"), dict) else {},
        }

        skill_url = clean_text(advanced.get("skill_url"))
        custom_builder_command = clean_text(advanced.get("builder_cli_command"))
        command = custom_builder_command or DEFAULT_EXTENSION_BUILDER_COMMAND

        summary = {
            "extension": manifest["name"],
            "package": manifest["package"],
            "node_count": len(nodes),
            "warnings": warnings,
            "advanced_keys": sorted([key for key, value in manifest.items() if key in {"description", "web_directory", "repository", "license", "tags", "min_comfyui_version", "extras"} and value not in ("", [], {})]),
            "has_web_directory": bool(manifest["web_directory"]),
            "has_repository": bool(manifest["repository"]),
            "skill_requested": bool(skill_url),
            "used_advanced_bundle": used_advanced_bundle,
            "next_step": "Write builder_manifest_json to extension.builder.json and run your chosen builder CLI.",
        }
        return (
            json.dumps(manifest, ensure_ascii=False, indent=2),
            command,
            json.dumps(summary, ensure_ascii=False, indent=2),
        )


class MKRNodeExtensionPyprojectPlan:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "builder_manifest_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "Manifest JSON from MKRNodeExtensionBuilderPlan.",
                    },
                ),
                "version_override": ("STRING", {"default": ""}),
                "readme_path": ("STRING", {"default": "README.md"}),
                "requires_python": ("STRING", {"default": ">=3.10"}),
                "pyproject_options_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "Optional overrides for documentation_url, bug_tracker_url, display_name, icon_path, license_file, includes, requires_comfyui, include_v3_optional_dependency, and v3_requirement.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("pyproject_toml", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_WORKFLOW

    def build(
        self,
        builder_manifest_json: str,
        version_override: str = "",
        readme_path: str = "README.md",
        requires_python: str = ">=3.10",
        pyproject_options_json: str = "{}",
    ) -> Tuple[str, str]:
        manifest, manifest_warnings = parse_builder_manifest(builder_manifest_json)
        pyproject_options, options_warnings = parse_json_object(pyproject_options_json, "pyproject_options_json")
        warnings = [*manifest_warnings, *options_warnings]

        manifest_name = clean_text(manifest.get("name")) or "MKRShift Nodes"
        manifest_package = clean_text(manifest.get("package"))
        manifest_publisher = clean_text(manifest.get("publisher")) or slugify(manifest_package.split(".", 1)[0] if "." in manifest_package else "", "mkrshift")
        version_text, version_warnings = normalize_version(version_override or clean_text(manifest.get("version")) or "0.1.0")
        warnings.extend(version_warnings)

        description = clean_text(manifest.get("description")) or f"Node extension scaffold for {manifest_name}."
        repository = clean_text(manifest.get("repository"))
        documentation_url, bug_tracker_url = derive_repository_urls(
            repository,
            clean_text(pyproject_options.get("documentation_url")),
            clean_text(pyproject_options.get("bug_tracker_url")),
        )
        readme_text = clean_text(readme_path) or "README.md"
        requires_python_text = clean_text(requires_python) or ">=3.10"
        project_name = derive_project_name(manifest_package, manifest_name)
        display_name = clean_text(pyproject_options.get("display_name")) or manifest_name
        license_file = clean_text(pyproject_options.get("license_file")) or "LICENSE"
        icon_path = clean_text(pyproject_options.get("icon_path"))
        includes = normalize_string_list(pyproject_options.get("includes"))
        requires_comfyui = normalize_requires_comfyui(
            clean_text(pyproject_options.get("requires_comfyui")) or clean_text(manifest.get("min_comfyui_version"))
        )
        extras = manifest.get("extras") if isinstance(manifest.get("extras"), dict) else {}
        include_v3 = should_include_v3_dependency(pyproject_options, extras)
        v3_requirement = clean_text(pyproject_options.get("v3_requirement")) or "comfy_api>=0.0.2"

        lines = [
            "[project]",
            f"name = {toml_string(project_name)}",
            f"description = {toml_string(description)}",
            f"version = {toml_string(version_text)}",
            f"readme = {toml_string(readme_text)}",
            f"requires-python = {toml_string(requires_python_text)}",
            f"license = {{file = {toml_string(license_file)}}}",
        ]
        if include_v3:
            lines.append(f"optional-dependencies = {{ v3 = [{toml_string(v3_requirement)}] }}")

        if repository or documentation_url or bug_tracker_url:
            lines.extend(["", "[project.urls]"])
            if repository:
                lines.append(f"Repository = {toml_string(repository)}")
            if documentation_url:
                lines.append(f"Documentation = {toml_string(documentation_url)}")
            if bug_tracker_url:
                lines.append(f'"Bug Tracker" = {toml_string(bug_tracker_url)}')

        lines.extend(
            [
                "",
                "[tool.comfy]",
                f"PublisherId = {toml_string(manifest_publisher)}",
                f"DisplayName = {toml_string(display_name)}",
                f"Icon = {toml_string(icon_path)}",
                f"includes = {json.dumps(includes, ensure_ascii=False)}",
            ]
        )
        if requires_comfyui:
            lines.append(f'"requires-comfyui" = {toml_string(requires_comfyui)}')

        summary = {
            "project_name": project_name,
            "display_name": display_name,
            "publisher": manifest_publisher,
            "has_repository": bool(repository),
            "has_documentation_url": bool(documentation_url),
            "has_bug_tracker_url": bool(bug_tracker_url),
            "has_v3_optional_dependency": include_v3,
            "includes_count": len(includes),
            "warnings": warnings,
            "next_step": "Write pyproject_toml to pyproject.toml and review registry-facing fields before publishing.",
        }
        return ("\n".join(lines) + "\n", json.dumps(summary, ensure_ascii=False, indent=2))
