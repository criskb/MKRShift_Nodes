# MKRShift Social Pack Catalog

Lists the installed social packs that the builder node can use.

## What It Does

- Reads pack metadata from the local `packs/` directory.
- Outputs a JSON array describing the available packs plus a `pack_count`.
- Gives you a workflow-readable way to inspect or validate which presets are installed.

## Notes

- This is a utility node for inspection, debugging, and automation around the social planning system.
- Pair it with `MKRshiftSocialPackBuilder` when you want to expose available packs in a workflow.
