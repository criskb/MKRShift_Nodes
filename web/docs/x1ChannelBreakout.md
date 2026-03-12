# x1ChannelBreakout

Breaks an image into per-channel grayscale images and masks.

## Inputs

- `image`: Source image to split.
- `alpha_fallback`: What to emit for alpha when the source has no alpha channel. Choose `zero`, `one`, or `luma`.

## Outputs

- `red_image`, `green_image`, `blue_image`, `alpha_image`: Grayscale image previews for each channel.
- `red_mask`, `green_mask`, `blue_mask`, `alpha_mask`: Scalar mask outputs for each channel.
- `breakout_info`: Summary string describing the resolved alpha source.

## Notes

- This is useful before channel packing, mask authoring, and technical lookdev debugging.
