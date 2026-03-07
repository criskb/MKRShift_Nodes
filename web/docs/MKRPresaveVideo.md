# MKRPresaveVideo

## What It Does

`MKRPresaveVideo` is a preview-first saver for video-like outputs. It can review and export file-backed video inputs or frame batches that can be encoded into a final clip.

## Typical Flow

1. Connect a video payload or compatible frame-based input.
2. Use `preview_only` while checking playback and timing.
3. Choose an output format only when you are ready to write a file.
4. Add an optional `filename_label` for a cleaner final filename.

## Format Behavior

- `auto` preserves the source format when possible
- `mp4`, `mov`, and `webm` require `ffmpeg` for encoding
- `gif` and `webp` are useful for lightweight preview exports

## Notes

- `animation_fps` controls frame-rate for encoded outputs.
- `webp_quality` and `animation_loop` only affect formats that use those settings.
- This is an output node and does not emit downstream data.
