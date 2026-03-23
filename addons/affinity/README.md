# MKRShift Affinity Addon

Affinity now looks much less opaque than it did at the start of this bridge pass.

Current practical route:

- PSD / texture roundtrip compatibility
- external packet exchange
- Photoshop-plugin compatibility where applicable

That last point matters. Affinity Photo exposes Photoshop-plugin support and plugin-folder configuration, which gives us a realistic bridge direction:

- packet + asset handoff from ComfyUI
- Affinity-side Photoshop-plugin search/support folder setup
- filter or import/export style handoff instead of pretending there is a separate mature Affinity-native plugin SDK surface

Use the ComfyUI-side nodes:

- `MKRAffinityDocumentImport`
- `MKRAffinityExportPlan`
- `MKRAffinityPhotoshopPluginPlan`

This keeps the bridge honest: leverage the Photoshop-plugin lane where Affinity supports it, and keep packet-first plans around it.
