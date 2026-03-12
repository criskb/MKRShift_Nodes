# x1TextureSeamless

Makes a texture more tileable by matching opposite edges and softening the seam zones.

## Inputs

- `image`: Source texture batch.
- `blend_width`: Width of the seam zones that get softened after the half-tile offset.
- `edge_match_strength`: How strongly opposite borders are nudged toward the same low-frequency value.
- `edge_match_blur`: Blur radius used for the low-frequency edge-matching solve.
- `detail_preserve`: Amount of high-frequency texture detail kept in the softened seam regions.
- `seam_blur`: Blur radius used only inside the seam zones.

## Outputs

- `image`: Seam-matched texture.
- `mask`: Border-region mask showing where seam correction was focused.
- `seamless_info`: Summary string with the resolved settings.

## Notes

- This is a practical lookdev helper for scans, decals, and surface albedo maps. It will reduce obvious tiling seams, but it does not replace manual patching on strongly directional textures.
