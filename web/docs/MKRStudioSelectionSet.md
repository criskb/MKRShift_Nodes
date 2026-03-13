# MKRStudioSelectionSet

Builds contact-sheet ready `selection_json` from quick review notes like `12:hero`, `14-15:select`, or `18:revise|hair cleanup`.

## What It Does

- Parses frame numbers and ranges into the same `selection_json` shape that `MKRStudioContactSheet` already understands.
- Keeps reviewer and round metadata alongside the picks so approvals stay traceable.
- Emits a manifest payload and CSV string for handoff notes, spreadsheets, or downstream delivery nodes.

## Input Format

- One entry per line is the safest pattern.
- Supported examples:
  - `12`
  - `14:hero`
  - `18-20:select`
  - `22:revise|hair cleanup`

## Outputs

1. `selection_json`
2. `selection_manifest_json`
3. `frames_csv`
4. `selection_summary`
5. `selection_count`

## Typical Use

1. Build your review labels with `MKRStudioDeliveryPlan`.
2. Type the chosen frames into `MKRStudioSelectionSet`.
3. Feed `selection_json` into `MKRStudioContactSheet` so the board renders status chips automatically.
