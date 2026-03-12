# x1UVCheckerOverlay

Generates or overlays a UV-style checker pattern for technical layout and distortion checks.

## Inputs

- `image`: Source image used as the size reference and, in `overlay` mode, the base image.
- `mode`: `overlay` blends the checker onto the source image. `generate` emits only the checker.
- `palette`: Checker color palette preset.
- `cells_x`, `cells_y`: Checker cell count horizontally and vertically.
- `line_width`: Grid line width in pixels.
- `mix`: Blend amount in `overlay` mode.
- `invert_pattern`: Swap the two checker colors.
- `mask_feather`: Feather radius for the optional `mask`.
- `invert_mask`: Invert the optional `mask`.
- `mask`: Optional mask that limits where the checker is applied.

## Outputs

- `image`: Generated or overlaid checker image.
- `mask`: Checker line mask.
- `checker_info`: Summary string with the resolved settings.

## Notes

- Use this for UV distortion checks, 2D alignment passes, and technical paint/layout review.
