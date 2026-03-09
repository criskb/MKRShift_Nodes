# MKRStudioDeliveryPlan

Builds save-ready naming, subfolder, and manifest-note metadata for studio review handoff.

## Inputs

- `project`, `sequence`, `shot`, `take`, `version_tag`: Core shot identity.
- `deliverable`: Handoff mode such as review, client selects, contact sheet, turnover, or social cut.
- `department`, `artist`, `client`: Human-facing context for labels and naming.
- `date_text`: Review or delivery date. Falls back to the current date if blank.
- `naming_mode`: Controls whether the filename is compact, editorial, or client-friendly.
- `extension`: Suggested primary output extension.
- `include_take`, `include_date`, `include_artist`, `include_client`: Toggles extra tokens in the generated filename.
- `slate_json`, `review_frame_info`, `contact_sheet_info` (optional): Pulls metadata from the studio nodes added earlier.
- `notes_json` (optional): Extra structured notes to embed into the generated manifest notes bundle.

## Outputs

- `filename_prefix`: Sanitized prefix suitable for presave or export nodes.
- `subfolder`: Suggested relative subfolder path for organized delivery output.
- `review_title`: Ready-to-use title for review frames.
- `manifest_notes_json`: Structured notes payload that can be forwarded into manifest-oriented nodes.
- `delivery_plan_json`: Full delivery plan with labels, suggested files, and source metadata.

## Use Cases

- Standardize filenames across slates, review stills, contact sheets, and manifests.
- Generate consistent client-facing labels from shot metadata.
- Bridge the new studio review nodes into `MKRPreSave` and `MKRProjectManifest` without manual renaming.
