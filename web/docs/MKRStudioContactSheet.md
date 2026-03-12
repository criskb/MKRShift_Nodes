# MKRStudioContactSheet

Turns an image batch into a labeled studio contact sheet for daily selects, proof sheets, and batch review.

## Inputs

- `images`: Input image batch.
- `title`, `subtitle`, `badge`: Board-level labels for the review sheet.
- `theme`: Board style.
- `columns`: Number of cards per row.
- `cell_width`: Target thumbnail width per card.
- `gap_px`, `margin_px`, `header_px`, `footer_px`: Layout spacing controls.
- `label_prefix`, `start_index`: Generates labels like `SHOT 12`, `SHOT 13`, and so on.
- `show_ratio`, `show_resolution`: Appends ratio and pixel dimensions in each card footer.
- `delivery_plan_json` (optional): Reuses contact-sheet titles, badge text, and label prefix from `MKRStudioDeliveryPlan`.
- `selection_json` (optional): Marks specific displayed frame numbers with status chips such as `HERO`, `HOLD`, or `REJECT`.

## Outputs

- `image`: Single rendered contact-sheet board.
- `contact_sheet_info`: JSON metadata with board size, grid layout, and per-card labels.

## Use Cases

- Batch review of render candidates.
- Proof-sheet exports for approvals or handoff.
- Visual dailies boards with consistent labels and metadata.
- Mark selects directly on the board for client notes or internal shortlist passes.
