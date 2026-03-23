# MKRPoseStudio

`MKRPoseStudio` is the first real 3D pose-layout node in the character branch. It gives you a live viewport, left/right body sliders, presets, and mirror actions, then exports reusable pose JSON plus a rendered pose guide image.

The node now works as a compact launcher for a separate Pose Studio workspace, so the editor is no longer constrained to the node body.

## Inputs

Optional:
- `settings_json`: Stored pose + viewport state used by the frontend studio workspace.
- `pose_name`
- `pose_preset`: `from_settings`, `neutral`, `heroic`, `contrapposto`, `run_start`, `power_stance`, `reach_up`, `kneel_pose`, `hands_behind_back`, `pinup_sway`, `crouch_ready`
- `mirror_mode`: `from_settings`, `off`, `left_to_right`, `right_to_left`
- `character_state_json`: Optional character record from `MKRCharacterState`

Image-fit mode, fit strength, and reference image loading now live inside the Pose Studio workspace instead of the main node surface.

## Outputs

- `pose_json`: Normalized pose payload with controls, view, world joints, and bone links.
- `pose_guide`: Branded pose-guide image for review or downstream prompt/control use.
- `pose_prompt`: Short readable descriptor.
- `summary_json`: Compact metadata summary.

## What The Viewport Does

- Realtime 3D skeleton preview with orbit camera.
- Torso, head, arm, and leg slider groups.
- Quick presets for neutral, heroic, contrapposto, run-start, power, reach, kneel, hands-behind-back, pinup-sway, and crouch-ready poses.
- Left-to-right and right-to-left mirror actions.
- Optional image-fit on execution for pulling a rough pose from a reference image or pose guide. It now starts from a broader set of kneel / overhead / turned-body seeds before refining, and it applies a support / stability prior so crouched and kneeling fits stay physically saner during the search.
- `Structured` fit is the stronger mode. It treats extracted pseudo-keypoints as a first-class prior, weighs anchor alignment more heavily, and relaxes some of the old standing-support bias on tricky silhouettes.
- When image-fit is active, the exported pose-guide output uses the studio reference image width and height so the preview framing matches the source image dimensions.
- View modes for `Bones Only`, `Bones + Mesh`, and `Depth Mesh`.
- Built-in `Female` / `Male` silhouette bodies plus an optional custom GLB silhouette path for swapping your own display mesh.
- An in-studio `Pose JSON` panel for copying, pasting, and applying full pose state directly.
- An in-studio `Reference Image` panel for loading an image and running either `Silhouette` or `Structured` local pose-fit passes from the studio UI.
- Structured fit now preserves a reference frame hint so the exported guide stays closer to the source image framing instead of always recentering the pose into a generic neutral crop.
- The reference panel now supports clickable joint anchors, so you can place head / pelvis / hand / knee / foot hints directly on the image and the fitter will use them during local fit and graph execution.
- Face, body, hand, and foot anchor groups can be enabled or disabled independently, so you can keep only the regions that help a specific reference pose.
- Saves the working pose back into `settings_json` so the studio reopens in the same state.

## Workspace Behavior

- Use the node button or double-click the node to open the external Pose Studio workspace.
- The graph node stays compact while the editor runs in a full-screen overlay.
- Closing the workspace does not discard the current pose; the saved state stays on the node.

## JSON Shape

```json
{
  "schema": "mkr_pose_studio_v1",
  "schema_version": 1,
  "pose_name": "Neutral",
  "pose_preset": "neutral",
  "mirror_mode": "off",
  "view": { "yaw": 28.0, "pitch": 8.0, "zoom": 1.0 },
  "controls": {
    "root_yaw": 0.0,
    "spine_bend": 6.0,
    "head_yaw": 6.0,
    "arm_raise_l": 18.0,
    "elbow_bend_l": 18.0,
    "hip_lift_l": 4.0,
    "knee_bend_l": 6.0
  }
}
```

`pose_json` also includes computed `joints_world`, `bones`, and a descriptor string.

## Notes

- This first pass is a production-friendly blockout tool, not a full IK rig.
- Image-fit is a best-effort blockout solver against the MKRShift pose rig. It is strongest with clean silhouettes or exported pose-guide style images, not arbitrary cluttered photography.
- If silhouette-only fit is still ambiguous, add a few anchors on the reference image before running fit. Head, pelvis, wrists, knees, and feet are the highest-value anchor points.
- Custom silhouette assets can be dropped under [web/assets/pose_studio/README.md](/Users/crisbjorndal/ComfyUI/custom_nodes/MKRShift_Nodes/web/assets/pose_studio/README.md) and loaded through the studio display controls.
- The saved pose payload is designed so future camera, lighting, sheet-builder, and Blender-bridge nodes can consume the same state format.
