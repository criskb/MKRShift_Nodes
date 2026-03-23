# Pose Studio Custom Silhouette Asset

`MKRPoseStudio` can load a custom GLB silhouette asset from:

`/extensions/MKRShift_Nodes/assets/pose_studio/custom_silhouette.glb`

This is intended for a swappable display body, not a full arbitrary rig import.

## Named Mesh Contract

If your GLB contains meshes with these names, Pose Studio will use them for the matching body parts:

- `torso`
- `shoulder`
- `armUpper`
- `armLower`
- `hand`
- `hip`
- `legUpper`
- `legLower`
- `foot`
- `chest`
- `pelvis`
- `head`

You do not need every part. Missing names fall back to the built-in procedural silhouette.

## Notes

- This works best with simple closed meshes meant to read as a silhouette.
- A stock VRoid-derived body can work if you split or rename meshes to match the part names above.
- This is a display layer for posing and framing, not a full skinned-character importer yet.
