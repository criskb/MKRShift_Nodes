# x1IDMapQuantize

Quantizes an image into flat material-ID style regions and exposes the region edges as a mask.

## Inputs

- `image`: Source image.
- `color_space`: Quantize in `rgb` or `hsv`.
- `levels`: Quantization density. Higher values preserve more original variation.
- `palette_mode`: `preserve` keeps quantized source colors. `id_vivid` and `id_pastel` remap regions into clean ID palettes.
- `smoothing`: Optional blur before quantization to merge noisy micro-variation.
- `edge_softness`: Softens the generated edge mask.
- `mask_feather`: Feather radius for the optional `mask`.
- `invert_mask`: Invert the optional `mask`.
- `mask`: Optional mask that limits where the ID map is emitted.

## Outputs

- `image`: Quantized ID map.
- `mask`: Region-edge mask.
- `id_map_info`: Summary string with the resolved settings and approximate region count.

## Notes

- Use this when blocking materials, generating mask bases, or flattening noisy concept art into clearer technical regions.
