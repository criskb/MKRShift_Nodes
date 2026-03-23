# MKRShift Photoshop Addon

This scaffold targets Photoshop as a UXP plugin panel.

Files:

- `manifest.json`
- `index.html`
- `index.js`

Current bridge surface:

- read/write Comfy packet JSON
- send selected document/export info into bridge payloads
- build image payload and image output specs
- submit payloads to local/remote endpoint plans
- poll endpoint job status for roundtrip completion
