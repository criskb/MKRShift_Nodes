# MKROutfitSet

`MKROutfitSet` adds or updates a named outfit inside a character state record and emits a resolved prompt for that look.

## Inputs

- `character_state_json`: Character record from `MKRCharacterState`.
- `outfit_name`: Outfit/costume label.
- `outfit_prompt`: Main costume description.
- `silhouette_notes`: Readability or shape notes.
- `material_notes`: Material/surface notes.
- `accessories_csv`: Accessory list.
- `palette_csv`: Palette tags or dominant colors.
- `mood_hint`: Optional look-specific mood.
- `match_strength`: How tightly this look should track the base character identity.
- `set_as_default`: Sets this outfit as the default look in the state record.
- `outfit_notes`: Freeform production notes.

## Outputs

- `character_state_json`: Updated state with the outfit added.
- `outfit_json`: Isolated outfit record.
- `resolved_prompt`: Combined character + outfit prompt.
- `summary_json`: Compact summary of the outfit update.

## Notes

- Reusing the same `outfit_name` updates that outfit instead of duplicating it.
- This is designed to stay lightweight and composable so later expression/sheet nodes can consume the same state format.
