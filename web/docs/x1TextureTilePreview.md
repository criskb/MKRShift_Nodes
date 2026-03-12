# x1TextureTilePreview

Repeats a texture into a tiled preview so you can inspect visible seams before export or baking.

## Inputs

- `image`: Source texture batch.
- `tiles_x`, `tiles_y`: Number of repeats horizontally and vertically.
- `show_seams`: Overlay seam guides on the preview.
- `seam_width`: Width of the seam guide lines.
- `seam_opacity`: Overlay opacity when `show_seams` is enabled.

## Outputs

- `image`: Tiled preview image.
- `mask`: Seam guide mask across the tile boundaries.
- `tile_preview_info`: Summary string with the resolved tiling settings.

## Notes

- This node is useful immediately after `x1TextureSeamless` or `x1TextureOffset` so you can check the result without leaving the graph.
