# MKRShift After Effects Addon

This scaffold starts with an ExtendScript/ScriptUI-style bridge panel, which is the most practical first pass for AE-side roundtrip work.

Files:

- `MKRShift_AE_Bridge.jsx`

Planned use:

- export comp/frame metadata
- build render handoff packets
- build image output and playback specs
- submit payloads to endpoint plans
- poll rendered plate/status responses back into the bridge
