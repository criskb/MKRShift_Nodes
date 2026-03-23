# MKRShift TiXL Addon

This addon scaffold is built around the TiXL / Tooll operator workflow.

Current public signals from TiXL emphasize:

- custom shader integration
- hot code reloading
- NDI / Spout / OSC interoperability
- writing new Operators with C#

Reference:

- [TiXL Workshop Page](https://tixl.app/news01-workshop-berlin)

Files:

- `MKRShiftComfyBridgeOperator.cs`

Suggested ComfyUI-side pairings:

- `MKRTiXLImport`
- `MKRTiXLFramePlan`
- `MKROSCMessagePlan`
- `MKRNDIStreamPlan`
- `MKRSpoutSenderPlan`
- `MKRWebSocketBridgePlan`
