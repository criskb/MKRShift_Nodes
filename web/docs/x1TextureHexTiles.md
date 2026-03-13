# x1TextureHexTiles

Generates a seamless hex-cell pattern for honeycomb surfaces, reptile scales, sci-fi paneling, and hard-surface breakup masks.

## Inputs

- `width`, `height`: Output texture resolution.
- `pattern_mode`: Chooses filled cells, border lines, center falloff, or a beveled hybrid.
- `hex_scale_px`: Approximate size of each hex cell.
- `line_width`: Thickness of the hex border response.
- `contrast`, `balance`, `invert`: Final shaping controls.
- `seed`: Keeps the per-cell variation deterministic.

## Outputs

- `image`: The grayscale pattern expanded to RGB.
- `mask`: The same scalar field as a reusable mask.
- `hex_tiles_info`: Summary string with the resolved settings.

## Notes

- `lines` is a good starting point for panel seams, emissive trims, and stylized outlines.
- `fill` works well for scales, tiled roughness breakup, or honeycomb-like height masks.
- Search aliases include `honeycomb`, `hexagon`, and `scales`.
