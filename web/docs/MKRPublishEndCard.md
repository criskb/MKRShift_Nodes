# MKRPublishEndCard

`MKRPublishEndCard` generates a standalone closing card with headline, subheadline, body copy, CTA, and optional background image.

## Inputs

- `width`, `height`: Output size.
- `title`, `subtitle`, `body`: Main messaging.
- `cta`: Call-to-action pill.
- `footer`: Footer label or brand tag.
- `theme`: Card palette.
- `margin_px`: Outer spacing.
- `background_image`: Optional image used as a hero background under the card overlay.

## Outputs

- `image`: Single end-card image.
- `end_card_info`: JSON summary of settings and layout.

## Notes

- Useful for final carousel pages, outros, launch slides, and branded closing cards.
