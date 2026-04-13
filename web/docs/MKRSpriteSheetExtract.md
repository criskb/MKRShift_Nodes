# MKRSpriteSheetExtract

Extracts separate sprites from a transparent atlas or color-keyed sprite sheet and returns them as a padded image batch.

## Inputs

- `image`: Source atlas or sprite sheet.
- `source_mode`: `alpha` or `color_key`.
- `alpha_threshold`: Minimum alpha used for sprite detection in `alpha` mode.
- `key_color`: Background key color for `color_key` mode.
- `key_threshold`: Distance threshold around the key color.
- `min_sprite_pixels`: Minimum connected-pixel area required to keep a sprite.
- `padding`: Transparent padding added around each extracted sprite.
- `sort_mode`: `top_left`, `left_to_right`, or `area_desc`.

## Outputs

- `sprites`: Extracted sprite batch, padded to a shared tile size.
- `sprite_map_json`: Sprite bounds, order, and batch tile size metadata.
- `summary_json`: Detection mode, sprite count, and warnings.

## Notes

- This is especially handy for classic pixel-art cleanup, retro UI sheets, and exported game atlases.
- `alpha` is usually best for modern atlases; `color_key` is useful for magenta/green-screen style sheets.
- Combine the output with `MKRImageCombineGrid` when you want to rebuild a cleaner contact sheet or atlas preview.
