# x1ChannelPack

Packs grayscale images or masks into RGB or RGBA texture channels.

## Inputs

- `output_mode`: Choose `rgb` or `rgba`.
- `fill_missing`: Fallback value used when a channel has no connected source.
- `red_image`, `green_image`, `blue_image`, `alpha_image`: Optional grayscale image sources. The node uses luma from each image.
- `red_mask`, `green_mask`, `blue_mask`, `alpha_mask`: Optional mask sources. Masks override image inputs on the same channel.

## Outputs

- `image`: Packed texture.
- `packing_info`: Summary string showing which source was used for each channel.

## Notes

- This is useful for ORM/RMA-style packing, mask atlases, and shader-input consolidation.
- If you need to pull specific color channels out of an image first, use `x1ChannelBreakout` before packing.
