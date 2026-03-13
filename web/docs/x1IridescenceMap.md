# x1IridescenceMap

Derives a thin-film / iridescence-strength mask for soap-film, coated plastic, lacquered paint, beetle-shell, and stylized interference looks.

## Inputs

- `image`: Source texture batch.
- `source_mode`: `combined_iridescence` prefers bright, saturated, smoother regions that read plausibly as thin-film interference.
- `normalize_mode`, `value_min`, `value_max`, `percentile_low`, `percentile_high`: Scalar remapping controls.
- `detail_radius`, `detail_strength`: Detail shaping for cleaner or more broken-up iridescence masks.
- `gamma`, `contrast`, `blur_radius`: Final scalar shaping controls.
- `source_mask`, `mask`, `mask_feather`: Upstream source gating and final output masking.

## Outputs

- `image`: Grayscale iridescence-strength image.
- `mask`: Scalar iridescence-strength mask.
- `iridescence_info`: Summary string with the resolved settings.

## Notes

- Feed this into `x1PreviewMaterial`'s `iridescence` input for experimental glTF thin-film preview support.
- `x1ThicknessMap` or `x1ScalarMapAdjust` are the best follow-up nodes when you also want to drive `iridescence_thickness`.
