# MKRStudioReviewNotes

Builds handoff-ready markdown review notes from `MKRStudioDeliveryPlan` and optional `MKRStudioSelectionSet` output.

## What It Does

- Generates a clean markdown note block for Slack, email, ticket comments, or internal reviews.
- Pulls shot, version, reviewer, round, and subfolder data directly from `delivery_plan_json`.
- Expands selected-frame notes and suggested files so the handoff text stays tied to the real package.

## Outputs

1. `review_notes_md`
2. `review_notes_json`
3. `summary`

## Typical Use

1. Build your naming package with `MKRStudioDeliveryPlan`.
2. Mark picks with `MKRStudioSelectionSet`.
3. Feed both into `MKRStudioReviewNotes` and paste the markdown into your handoff message.
