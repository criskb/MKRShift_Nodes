# MKRshiftSocialPackBuilder

## What It Does

`MKRshiftSocialPackBuilder` turns one source image plus a pack preset into a structured social-content plan. It outputs a processed image batch together with plan and prompt JSON you can reuse elsewhere in the graph.

## Typical Flow

1. Connect an `IMAGE`.
2. Choose a pack preset such as commerce, event recap, or social dump.
3. Set `output_mode`, `count`, `aspect`, and platform strategy controls.
4. Add optional project, product, audience, or offer details.
5. Feed the JSON outputs into the utility nodes to extract captions, hashtags, prompts, or schedule data.

## Mixed Mode Behavior

- `aspect = Auto` with `output_mode = Mixed` now cycles through the pack's default ratios per asset instead of repeating a single ratio for the entire plan.
- The compact `Defaults` action restores `aspect = Auto`, so Mixed and Story presets keep their pack-aware ratio behavior instead of being flattened to one fixed frame.
- Each planned asset includes its own `ratio`, `role`, and `publish_at_local` value in the generated plan JSON.

## UI Notes

- The node now keeps the normal Comfy widgets visible and uses a compact dark summary panel as assistive UI instead of replacing the whole node with a custom shell.
- The summary panel works as a small Nodes 2.0 DOM widget when available, but the node still functions with plain widgets if a custom DOM surface is unavailable.
- The panel shows the selected pack, a source or pack preview, current ratio and pacing summaries, and readiness warnings when a fixed aspect is overriding Mixed or Story behavior.

## Outputs

1. `image_out`
2. `plan_json`
3. `prompts_json`
4. `negative_prompts_json`

## Related Nodes

- `MKRshiftSocialPackCatalog` lists available packs
- `MKRshiftSocialPackAssets` extracts structured text assets from the generated plan
- `MKRshiftSocialPromptAtIndex` picks one prompt pair from the generated prompt arrays
