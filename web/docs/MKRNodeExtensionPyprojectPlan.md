# MKRNodeExtensionPyprojectPlan

Builds a registry-ready `pyproject.toml` draft from the `builder_manifest_json` output of `MKRNodeExtensionBuilderPlan`.

## Inputs

- `builder_manifest_json`: Manifest JSON from `MKRNodeExtensionBuilderPlan`.
- `version_override`: Optional version override. Falls back to the manifest version when left empty.
- `readme_path`: README path written into `[project].readme`.
- `requires_python`: Python requirement string written into `[project].requires-python`.
- `pyproject_options_json`: Optional JSON object for advanced overrides:
  - `documentation_url`
  - `bug_tracker_url`
  - `display_name`
  - `icon_path`
  - `license_file`
  - `includes`
  - `requires_comfyui`
  - `include_v3_optional_dependency`
  - `v3_requirement`

## Outputs

- `pyproject_toml`: Generated TOML text you can write into `pyproject.toml`.
- `summary_json`: Derived project/display names, metadata coverage flags, and warnings.

## Notes

- GitHub repositories automatically derive `Documentation` as `/wiki` and `Bug Tracker` as `/issues` unless overridden.
- `requires_comfyui` inherits from `min_comfyui_version` in the manifest when present.
- The V3 optional dependency is included automatically when the manifest extras declare `supports_v3_companions`, or explicitly through `pyproject_options_json`.
