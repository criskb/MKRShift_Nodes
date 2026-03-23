# MKRPublishAssetManifest

`MKRPublishAssetManifest` converts an image batch into a structured filename/metadata manifest for export workflows.

## Inputs

- `images`: Source image batch.
- `project`, `asset_prefix`, `channel`: Manifest labels.
- `extension`: Output file extension token.
- `start_index`: First display index.
- `title_prefix`: Fallback title stem if no explicit title list is supplied.
- `tags_csv`: Shared tags for all rows.
- `notes`: Shared notes text for all rows.
- `alt_template`: Python-style format string used to build per-row alt text.
- `titles_csv`: Optional per-row titles.
- `shot_labels_csv`: Optional per-row shot labels.

## Outputs

- `manifest_json`: Full structured manifest.
- `manifest_csv`: Spreadsheet-friendly CSV.
- `manifest_md`: Markdown table preview.
- `summary_json`: Compact manifest summary.
- `asset_count`: Number of manifest rows.

## Notes

- The alt-text template can use: `project`, `title`, `index`, `display_index`, `channel`, `width`, `height`, `ratio`, `filename`, `shot_label`.
