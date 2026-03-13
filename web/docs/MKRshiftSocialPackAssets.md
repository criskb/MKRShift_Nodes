# MKRShift Social Pack Assets

Extracts reusable arrays and summaries from the `plan_json` emitted by `MKRshiftSocialPackBuilder`.

## What It Does

- Pulls caption arrays, hashtag arrays, schedule data, and shot-plan data into separate JSON outputs.
- Emits a compact summary JSON with plan status, warnings, and pack metadata.
- Makes it easier to route social-planning data into other nodes without hand-parsing one large JSON blob.

## Outputs

1. `captions_json`
2. `hashtags_json`
3. `schedule_json`
4. `shot_plan_json`
5. `summary_json`

## Notes

- This node expects `plan_json` from `MKRshiftSocialPackBuilder`.
- Use `MKRshiftSocialPromptAtIndex` when you need one specific prompt pair from a generated prompt list.
