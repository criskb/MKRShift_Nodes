# MKRPublishCopyDeck

`MKRPublishCopyDeck` turns headline/body/CTA inputs plus optional hook lines into a small caption/copy variant deck.

## Inputs

- `headline`, `subhead`, `body`, `cta`: Base copy parts.
- `hashtags_csv`: Shared hashtags.
- `hook_lines`: Optional per-variant hooks. One line per variant.
- `tone`: Simple tone preset for the deck.
- `platform_hint`: Optional note stored in the output rows.

## Outputs

- `deck_json`: Structured caption deck.
- `deck_md`: Markdown preview of the variants.
- `first_caption`: First composed caption string.
- `summary_json`: Deck summary.
- `variant_count`: Number of generated variants.

## Notes

- If `hook_lines` is empty, the node emits one variant from the base headline.
