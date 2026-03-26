# x1ColorWheels

Primary color-correction node with drag-able physical wheels for:

- **Shadows** (`lift_*`)
- **Midtones** (`gamma_*`)
- **Highlights** (`gain_*`)
- **Offset** (`offset_*`)

The in-node UI is intentionally simple (flat wheel layout, standard ComfyUI-friendly styling, no nested cards).

## Drag Behavior

- Drag inside a wheel to move the white puck.
- Wheel position updates the underlying RGB triplet widgets.
- `builder`-style hidden controls are still available in workflow JSON for compatibility.

## Remaining Controls

Keep these as normal widgets:

- `balance`
- `saturation`
- `mix`
- mask controls (`mask_feather`, `invert_mask`, optional `mask`)

## Notes

- The UI is a frontend helper only; backend processing remains deterministic and fully workflow-compatible.
- If needed, you can still directly edit the numeric widget values from JSON/workflow edits.
