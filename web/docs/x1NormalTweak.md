# x1NormalTweak

Adjusts an existing tangent-space normal map for strength, softness, axis flips, and OpenGL/DirectX conversion.

## Inputs

- `image`: Source normal map.
- `strength`: Multiplies the tangent slope away from a flat neutral normal.
- `blur_radius`: Softens the incoming normal field before re-normalizing.
- `input_convention`: Interprets the source normal map as `opengl` or `directx`.
- `output_convention`: Writes the result as `match_input`, `opengl`, or `directx`.
- `flip_x`, `flip_y`: Flips the red or green normal direction.
- `mask_feather`: Feather radius for the optional output `mask`.
- `invert_mask`: Invert the optional output `mask`.
- `strength_mask`: Optional mask that locally blends between neutral strength and the requested `strength`.
- `mask`: Optional mask that limits where the adjusted normals are applied.

## Outputs

- `image`: Adjusted tangent-space normal map.
- `mask`: Final influence mask after `strength_mask` and optional output masking.
- `normal_tweak_info`: Summary string with the resolved settings.

## Notes

- Use this when a generated or painted normal map is too flat, too aggressive, or in the wrong green-channel convention for the target renderer.
- `strength_mask` is useful for boosting trim details or panel lines without overdriving the whole surface.
