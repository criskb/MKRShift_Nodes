# x1Curves

Simple physical curve UI for fast grading with draggable points directly inside the node.

## Draggable Controls

- **Master curve points**: `master_shadows`, `master_midtones`, `master_highlights`
- **RGB channel points**: `red_curve`, `green_curve`, `blue_curve`

The graph uses a flat ComfyUI-style canvas look (no nested card containers).

## Remaining Widgets

Keep using regular widgets for:

- `contrast`
- `mix`
- mask controls (`mask_feather`, `invert_mask`, optional `mask`)

## Notes

- Dragging a point updates the underlying numeric widgets in real time.
- Workflow JSON compatibility is preserved because backend parameters are unchanged.
