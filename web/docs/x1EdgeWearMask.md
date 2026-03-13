# x1EdgeWearMask

Builds a grayscale wear mask that favors bright convex edges and exposed regions.

## What It Does

- Detects likely chipped or worn edges from convex luma changes plus local detail.
- Suppresses flatter or overly saturated regions by default.
- Outputs a grayscale `IMAGE`, a scalar `MASK`, and an info string.

## Typical Use

1. Feed in a baked texture, ID texture, or paint/albedo source.
2. Leave `source_mode` on `combined_edge_wear` for procedural wear extraction.
3. Increase `edge_radius` for broader wear bands or `detail_strength` for sharper breakup.
4. Use the mask to blend roughness, metal exposure, dust removal, or secondary materials.

## Notes

- This is a practical wear-selection node, not a full curvature solver.
- For cavity-only breakup, use `x1CavityMap`.
- For region cleanup before packing, follow with `x1ScalarMapAdjust`.
