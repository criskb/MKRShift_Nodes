# x1ClearcoatRoughnessMap

Derives a grayscale clearcoat roughness map from a base texture.

## What It Does

- Favors rougher values in scuffed, noisy, less polished regions.
- Keeps smoother values in bright, neutral, polished coat regions.
- Outputs a grayscale `IMAGE`, a scalar `MASK`, and an info string for debugging.

## Typical Use

1. Feed in a scan, base color, or already-cleaned coat texture.
2. Leave `source_mode` on `combined_clearcoat_roughness` for the default heuristic.
3. Raise `detail_strength` if scratches and scuffs are underrepresented.
4. Send the result into `x1PreviewMaterial -> clearcoat_roughness` or pack it downstream.

## Notes

- `x1ClearcoatMap` and `x1ClearcoatRoughnessMap` are meant to be paired.
- `x1ScalarMapAdjust` is the follow-up node when you need a tighter artistic range.
- Use `mask` when only part of the material should get a coat treatment.
