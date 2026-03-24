# MKRCLIPTextEncodePrompt

`MKRCLIPTextEncodePrompt` is MKRShift's richer prompt-writing version of a CLIP text encode node.

## What It Does

- takes a `CLIP` input
- encodes `prompt_text` into `CONDITIONING`
- keeps the prompt text as a reusable string output
- returns a compact `summary_json` with prompt stats
- adds a built-in prompt library UI with:
  - folders
  - search
  - save
  - save copy
  - load
  - delete
  - notes
  - tags
  - favorites

## Outputs

- `conditioning`
- `prompt_text`
- `summary_json`

## Bookmark Storage

Prompt bookmarks are stored server-side in:

- `data/prompt_bookmarks.json`

That means the prompt library survives browser refreshes and can be reused across nodes and sessions.

## Typical Use

1. Connect your `CLIP` model.
2. Write or load a prompt in the node UI.
3. Save reusable prompt blocks into folders.
4. Run the graph to get conditioning.
5. Reopen the same node later and reload saved prompts.

## Notes

- The node UI is richer than the raw widget, but execution still uses a real prompt widget under the hood so workflow save/run behavior stays stable.
- Bookmark folders are lightweight strings, so you can create your own structure without extra setup.
