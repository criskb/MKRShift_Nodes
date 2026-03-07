# MKRPresaveAudio

## What It Does

`MKRPresaveAudio` is a preview-first audio saver for waveform-like or file-backed audio inputs.

## Typical Flow

1. Connect an audio payload.
2. Review with `preview_only` enabled.
3. Switch to save mode when you are happy with the result.
4. Pick a final output format and optional `filename_label`.

## Supported Formats

- `auto`
- `wav`
- `mp3`
- `flac`
- `ogg`

## Notes

- Encoded formats may require `ffmpeg` depending on the input and conversion path.
- Use `wav` if you want the safest interchange format for downstream tools.
- This is an output node and does not emit downstream data.
