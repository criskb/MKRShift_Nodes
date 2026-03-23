# MKRShift TouchDesigner Bridge

This scaffold is built around the TouchDesigner patterns we can rely on safely today:

- component `.tox` packaging
- Python component extensions
- TOP / CHOP / DAT driven graph wiring

Recommended install path:

1. Create a `baseCOMP` or clone your bridge COMP.
2. Add `MKRShiftBridgeExt.py` as the component extension.
3. Add DAT/TOP parameters for:
   - incoming packet JSON
   - outgoing asset path
   - transport mode
   - TOP name
   - operator path
4. Use the ComfyUI-side nodes:
   - `MKRTouchDesignerImport`
   - `MKRTouchDesignerFramePlan`

The intended first transports are:

- `file`
- `spout`
- `ndi`
- `shared_memory`
- `websocket`

The extension now also supports loading:

- frame-plan JSON
- transport-plan JSON
- endpoint-plan JSON
- image-output-plan JSON

And it can now:

- build image payloads from TOP-style outputs
- build playback specs for loop/trigger control
- submit payloads to an endpoint plan
- poll endpoint job status

That lets the TouchDesigner bridge evolve from file-driven workflows into endpoint-driven submits without changing the host-side component shape.

This scaffold does not try to ship a binary Custom OP yet. It stays in the safer `.tox` + extension lane first.
