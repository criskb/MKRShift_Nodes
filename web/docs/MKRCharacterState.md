# MKRCharacterState

`MKRCharacterState` builds a persistent character record you can reuse across outfit, expression, and sheet-generation workflows.

## Inputs

- `character_name`: Character label.
- `core_identity_prompt`: Core identity description.
- `body_notes`: Body/readability notes.
- `face_notes`: Face-stability notes.
- `style_anchor`: Shared style anchor for downstream prompts.
- `consistency_tokens_csv`: Tokens you want repeated across looks.
- `avoid_tokens_csv`: Tokens you want suppressed.
- `default_negative`: Base negative prompt for the character.
- `notes`: Freeform production notes.
- `character_state_json`: Optional previous state to update.
- `reference_notes`: Optional extra reference guidance.
- `default_outfit_name`: Optional default outfit override.

## Outputs

- `character_state_json`: Updated persistent state payload.
- `positive_anchor`: Resolved positive anchor prompt.
- `negative_anchor`: Resolved negative anchor prompt.
- `summary_json`: Compact summary of state contents.

## Notes

- This node is meant to become the base record for later outfit, expression, and sheet nodes.
- When you feed an older `character_state_json` back in, tokens and outfits are preserved unless you replace them explicitly.
