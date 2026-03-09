# MKRStudioSlate

Builds a branded production slate as an `IMAGE` plus structured slate metadata.

## Inputs

- `width`, `height`: Output canvas size.
- `theme`: Visual treatment for the slate background and panels.
- `project`, `sequence`, `shot`, `take`: Core shot identity fields.
- `director`, `artist`, `camera`, `lens`, `fps`, `aspect`, `date_text`: Production metadata.
- `notes`: Short review or setup notes.
- `thumbnail` (optional): Adds a framed preview image to the right metadata panel.

## Outputs

- `image`: Slate render ready for review decks or presave export.
- `slate_json`: Machine-readable metadata for logging or downstream packaging.
- `slate_summary`: Compact human-readable summary string.

## Use Cases

- Add a branded opener frame before client review exports.
- Generate consistent shot slates for animation, previs, or still-image turnarounds.
- Feed the JSON output into pack-specific naming or delivery nodes.
