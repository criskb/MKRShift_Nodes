# x1PBRPack

Packs material maps into common engine-ready PBR channel layouts with named AO, roughness, metalness, and alpha slots.

## What It Does

1. Accepts AO, roughness, metalness, and optional alpha as either grayscale images or masks.
2. Packs them into `ORM`, `ORMA`, `RMA`, or `MRA` layouts.
3. Automatically inverts gloss maps into roughness when needed.

## Inputs

- `layout`: Chooses the packed channel order.
- `roughness_source`: Set to `glossiness` when the connected roughness input is actually a gloss map.
- `fill_ao`, `fill_roughness`, `fill_metalness`, `fill_alpha`: Defaults used when a slot is not connected.
- `*_image`, `*_mask`: Semantic map inputs for each packed slot.

## Outputs

- `image`: Packed RGB or RGBA texture.
- `packing_info`: Summary of the chosen layout and which sources populated each channel.

## Notes

- Use this when you want semantic material packing without manually wiring `x1ChannelPack`.
- `x1ChannelPack` is still the better choice for arbitrary non-PBR channel layouts.
- A practical flow is `x1CavityMap` / `x1RoughnessMap` / `x1MetalnessMap` -> `x1PBRPack`.
