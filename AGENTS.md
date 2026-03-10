# MKRShift Nodes Project Notes

## Node Design Preferences

- When a node has a large set of secondary or expert-only controls, prefer a subgraph or advanced-input pattern instead of putting every option directly on the main node.
- Use this especially for utility, lookdev, and finishing nodes where the common case should stay fast but deeper tuning still needs to be available.
- Keep the main node surface focused on the controls most users need every time, and push niche or verbose tuning into optional advanced wiring when that makes the graph easier to read.
- Follow the pattern used by the sharpen node update when it is a good fit, but do not force it onto simple nodes that are clearer as a single compact node.
