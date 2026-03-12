# MKRStudioReviewFrame

Wraps each input frame in a branded review layout with title, badge, versioning, and optional safe-area guides.

## Inputs

- `image`: Input batch of images.
- `title`, `subtitle`, `badge`: Header text shown on every framed output.
- `theme`: Visual style for the review board.
- `version_tag`: Short revision marker.
- `footer_left`, `footer_right`: Footer metadata. When `footer_right` is blank the node fills it with resolution and ratio details.
- `margin_px`, `header_px`, `footer_px`: Layout sizing controls.
- `show_safe_area`: Draws inner guide boxes for title-safe and action-safe checks.
- `show_frame_index`: Adds `FRAME 01`, `FRAME 02`, and so on to the framed output.
- `shadow_strength`: Controls the image card shadow depth.
- `delivery_plan_json` (optional): Reuses labels from `MKRStudioDeliveryPlan` when the visible fields are left at their default placeholders.

## Outputs

- `image`: Framed batch of review-ready images.
- `review_frame_info`: JSON metadata describing per-frame layout details.

## Use Cases

- Client review stills with consistent branding.
- Internal lookdev approvals with version tags baked into the frame.
- Thumbnail generation for review portals or delivery boards.
- Auto-wire review titles, subtitles, and footer text from the delivery plan instead of retyping them.
