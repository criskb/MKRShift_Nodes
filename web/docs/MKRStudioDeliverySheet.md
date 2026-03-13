# MKRStudioDeliverySheet

Builds a markdown and JSON file sheet from `MKRStudioDeliveryPlan`.

## What It Does

- Turns the plan’s suggested files into a delivery table with roles, filenames, and resolved paths.
- Optionally carries selected-frame context through to every row for client-selects or approval packages.
- Makes it easier to hand a consistent file list to production, editorial, or a client portal task.

## Outputs

1. `delivery_rows_json`
2. `delivery_sheet_md`
3. `summary_json`
4. `row_count`

## Notes

- `root_folder` is optional; if you leave it blank the node emits paths relative to the plan subfolder.
- `include_optional_files` lets you trim the list down to the essential handoff files when needed.
