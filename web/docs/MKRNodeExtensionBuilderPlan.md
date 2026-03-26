# MKRNodeExtensionBuilderPlan

Builds a starter `comfyui-node-extension-builder` manifest and companion command text for packaging/distribution workflows.

## Inputs

- `extension_name`: Display extension name.
- `publisher`: Publisher slug used in package identity.
- `version`: Semver version string. Invalid values auto-fallback to `0.1.0`.
- `entry_file`: Python entry file (`__init__.py` by default).
- `node_list_json`: JSON array of node names or node objects (`{"name":"Node", "enabled":true}`).
- `advanced_options_json`: Optional expert metadata JSON:
  - `description`
  - `repository`
  - `license`
  - `web_directory`
  - `min_comfyui_version`
  - `tags`
  - `extras`
  - `skill_url` (marks skill-aware planning in summary output)
  - `builder_cli_command` (optional override for the returned command string)

## Outputs

- `builder_manifest_json`: Serialized manifest JSON suitable for `extension.builder.json`.
- `builder_command`: Suggested command string (defaults to skill-installer command unless overridden by `builder_cli_command`).
- `summary_json`: Package name, node count, warnings, and metadata coverage flags.

## Notes

- Keep frequently used values in primary inputs and place packaging-specific extras in `advanced_options_json`.
- Default flow: run the returned command, write `builder_manifest_json` to `extension.builder.json`, then run your local builder CLI.
- For onboarding, see `example_workflows/mkrshift_extension_builder_plan.json`.
