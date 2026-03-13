# x1TextureCellPattern

Generates a seamless cell-based pattern useful for stone, reptile scales, paneling, crack masks, and stylized wear breakup.

## Inputs

- `width`, `height`: Output texture resolution.
- `pattern_mode`: Chooses between filled cells, edge emphasis, cracks, raw distance falloff, or a beveled hybrid.
- `cell_scale_px`: Average size of each cell region.
- `jitter`: How irregular the cell placement is.
- `edge_width`: Thickness of the border response in edge and crack-style outputs.
- `contrast`, `balance`, `invert`: Final shaping controls.
- `seed`: Keeps the pattern deterministic.

## Outputs

- `image`: The grayscale pattern expanded to RGB.
- `mask`: The same scalar field as a reusable mask.
- `cell_pattern_info`: Summary string with the resolved settings.

## Notes

- `fill` works well as a base breakup map for roughness or albedo tinting.
- `cracks` is the fastest path to grout, fissure, or panel-line style masks.
- Because it tiles cleanly, you can run it through `x1PreviewMaterial` as height, roughness, or transmission shaping without first fixing borders.
