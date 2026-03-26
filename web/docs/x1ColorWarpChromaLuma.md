# x1ColorWarpChromaLuma

Mesh-based color warp node (Chroma/Luma domain) with draggable in-node points.

## Physical Mesh UI

- Red points are draggable destination targets.
- Light points are source anchors.
- Dragging updates `warp_points_json` automatically.
- `Shift+Click` adds a point, `Alt+Click` removes the nearest point.

## Controls

- `warp_points_json`
- `strength`
- `falloff`
- `mix`
- mask controls (`mask_feather`, `invert_mask`, optional `mask`)

The visual style is intentionally minimal and ComfyUI-friendly (no nested card panels).
