# MKRLayerStackComposite

`MKRLayerStackComposite` is a practical layer stack node for building one image from multiple masked image layers.

## What It Does

- composites a `base_image`
- layers up to 4 extra images over the base
- supports optional masks per layer
- supports per-layer opacity
- supports per-layer blend modes
- supports layer resize handling:
  - `stretch`
  - `contain`
  - `cover`

## Inputs

Required:

- `base_image`
- `layer_1`
- `layer_1_opacity`
- `layer_1_blend_mode`
- `resize_mode`

Optional:

- `layer_1_mask`
- `layer_2`, `layer_2_mask`, `layer_2_opacity`, `layer_2_blend_mode`
- `layer_3`, `layer_3_mask`, `layer_3_opacity`, `layer_3_blend_mode`
- `layer_4`, `layer_4_mask`, `layer_4_opacity`, `layer_4_blend_mode`
- `mask_feather`

## Outputs

- `image`
- `combined_mask`
- `layer_info`

## Notes

- If a layer image has an alpha channel, that alpha is used automatically.
- If a mask is also connected, the mask is multiplied with the layer alpha.
- `combined_mask` shows the overall visible contribution of the stacked layers.
- This node is meant to cover the common layered-composite case cleanly in one node instead of forcing several manual blends in sequence.
