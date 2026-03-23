# MKRPublishPromoFrame

`MKRPublishPromoFrame` turns an image batch into clean promo/export cards with a title, subtitle, copy block, badge, CTA, and footer.

## Inputs

- `image`: Source image batch.
- `title`: Main headline.
- `subtitle`: Secondary line under the headline.
- `body`: Multi-line copy block rendered in the lower card.
- `badge`: Small accent badge in the header.
- `cta`: Call-to-action pill in the lower card.
- `footer`: Footer label, brand, or collection tag.
- `theme`: Card palette.
- `margin_px`, `header_px`, `copy_height_px`: Layout sizing controls.
- `show_index`: Appends `current/total` in the footer.

## Outputs

- `image`: Framed promo batch.
- `publish_frame_info`: JSON summary of card sizing and labels.

## Notes

- Designed for export-facing presentation rather than review markup.
- Keeps one output card per input image so it stays easy to chain into save nodes.
