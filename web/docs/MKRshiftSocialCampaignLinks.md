# MKRshiftSocialCampaignLinks

Builds per-asset tracked URLs from `MKRshiftSocialPackBuilder` output.

## What It Does

- Reads the generated social plan and emits one campaign link per asset.
- Adds `utm_source`, `utm_medium`, `utm_campaign`, and `utm_content` automatically.
- Outputs both machine-friendly JSON and a markdown table that can drop straight into briefs or posting docs.

## Outputs

1. `links_json`
2. `link_table_md`
3. `first_url`
4. `summary_json`
5. `link_count`

## Notes

- If `utm_campaign` is blank, the node falls back to the plan’s project name, product name, or pack id.
- `utm_content_mode` lets you key links by slot, role, shot, or index depending on how you post.
- When a plan has no assets, the node still emits one root campaign link so the workflow does not dead-end.
