# x1TextureAlbedoSafe

Pushes scanned or painted base-color textures into safer PBR albedo ranges without changing their hue identity.

## What It Does

1. Remaps the texture value range toward more practical dark and bright limits.
2. Compresses excessive saturation, especially in clipped highlights and deep shadows.
3. Preserves alpha and emits an adjustment mask showing where the texture changed most.

## Inputs

- `target_black`, `target_white`: Target value range for the albedo remap.
- `saturation_limit`: Maximum saturation target before compression starts.
- `shadow_lift`, `highlight_rolloff`: How strongly the node lifts crushed darks and tames hot highlights.
- `mask`, `mask_feather`: Restrict the correction to selected regions.

## Notes

- This pairs well with `x1TextureDelight` when cleaning scanned textures before lookdev.
- A practical order is `x1TextureDelight` -> `x1TextureAlbedoSafe` -> `x1PreviewMaterial`.
