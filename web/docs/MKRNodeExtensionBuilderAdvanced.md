# MKRNodeExtensionBuilderAdvanced

Builds a structured `advanced_options_json` bundle for `MKRNodeExtensionBuilderPlan` so expert packaging controls can live in a sidecar node or subgraph instead of the main planning node.

## Inputs

- `description`: Optional manifest description override.
- `repository`: Repository URL for the extension package.
- `license_name`: License string written into the manifest.
- `web_directory`: Optional `WEB_DIRECTORY` path when the extension ships frontend assets.
- `min_comfyui_version`: Optional minimum ComfyUI version string.
- `tags_csv`: Comma-separated tags. Duplicate tags are removed automatically.
- `extras_json`: Optional JSON object merged into `manifest.extras`.
- `skill_url`: Optional skill/repo URL used as a planning hint in the plan summary.
- `builder_cli_command`: Optional builder command override returned by the plan node.

## Outputs

- `advanced_options_json`: Structured expert metadata JSON for `MKRNodeExtensionBuilderPlan.advanced_bundle_json`.
- `summary_json`: Included keys, tag count, extras presence, and validation warnings.

## Notes

- Use this node when you want a cleaner main node surface and a reusable advanced-settings subgraph.
- `extras_json` must be a JSON object. Invalid JSON falls back to `{}` and is reported in `summary_json`.
- This node does not build the final manifest by itself. Connect its output into `MKRNodeExtensionBuilderPlan`, then pass that manifest into `MKRNodeExtensionPyprojectPlan` if you want a matching `pyproject.toml` draft.
