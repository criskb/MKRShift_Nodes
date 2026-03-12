# x1TextureOffset

Wrap-offsets a texture for seam inspection and prep work.

## Inputs

- `image`: Source texture batch.
- `mode`: `half_tile` offsets by half the texture size on both axes. `fraction` uses normalized offsets. `pixels` uses direct pixel shifts.
- `offset_x`, `offset_y`: Horizontal and vertical offsets for `fraction` or `pixels` mode.
- `seam_width`: Width of the generated seam guide mask.

## Outputs

- `image`: Offset texture with wraparound.
- `mask`: Seam guide mask showing where the wrap boundary lands.
- `offset_info`: Summary string with the resolved pixel offsets.

## Notes

- `half_tile` is the fastest way to push seams into the middle of the frame before painting or downstream cleanup.
