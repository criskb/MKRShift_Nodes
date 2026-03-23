# MKRShift TiXL Bridge

This scaffold targets the TiXL / Tooll operator workflow conservatively:

- C# operator/plugin style integration
- packet-driven layer ingestion
- file / NDI / Spout / OSC planning first

Why this shape:

- TiXL publicly emphasizes shader integration, hot code reload, and writing new operators in C#.
- That makes a small custom bridge operator a much safer first delivery than pretending there is a turnkey plugin API surface identical to TouchDesigner.

Use with the ComfyUI-side nodes:

- `MKRTiXLImport`
- `MKRTiXLFramePlan`

The operator scaffold below is meant to:

- read a bridge plan JSON
- read transport-plan and endpoint-plan JSON
- expose transport/layer settings to the graph
- ingest image payload specs and image output plans
- build playback specs for triggerable clips/loops
- submit payloads to endpoint plans and poll job status
