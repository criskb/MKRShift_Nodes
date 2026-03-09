import shutil
import subprocess
import uuid
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image
import torch

from ..categories import INSPECT_PREVIEW
from .presave_image_nodes import (
    _image_batch_to_pil,
    _output_dir,
    _resolve_output_file,
    _sanitize_basename,
    _save_animation,
    _save_still_image,
    _temp_dir,
)

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

_VIDEO_FORMATS = {"mp4", "mov", "webm", "gif", "webp"}
_AUDIO_FORMATS = {"wav", "mp3", "flac", "ogg"}
_PATH_KEYS = {
    "path",
    "file",
    "filepath",
    "filename",
    "source",
    "src",
    "video",
    "video_path",
    "audio",
    "audio_path",
    "uri",
    "url",
}


def _media_kind_from_suffix(suffix: Any, fallback: str) -> str:
    ext = _safe_ext(suffix)
    if ext in _AUDIO_FORMATS:
        return "audio"
    if ext in {"gif", "webp", "png", "jpg", "jpeg"}:
        return "image"
    if ext in _VIDEO_FORMATS:
        return "video"
    return fallback


def _ffmpeg_bin() -> Optional[str]:
    return shutil.which("ffmpeg")


def _base_dirs() -> List[Path]:
    dirs: List[Path] = [Path.cwd(), _output_dir(""), _temp_dir()]
    if folder_paths is not None:
        for getter in ("get_input_directory", "get_output_directory", "get_temp_directory"):
            try:
                fn = getattr(folder_paths, getter, None)
                if callable(fn):
                    dirs.append(Path(str(fn())))
            except Exception:
                continue
    out: List[Path] = []
    seen: set = set()
    for entry in dirs:
        try:
            resolved = entry.resolve()
        except Exception:
            resolved = entry
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _resolve_existing_file(candidate: Any) -> Optional[Path]:
    if candidate is None:
        return None
    text = str(candidate).strip()
    if not text:
        return None
    if text.startswith(("http://", "https://", "data:")):
        return None

    direct = Path(text).expanduser()
    probes: List[Path] = [direct]
    if not direct.is_absolute():
        probes.extend(base / text for base in _base_dirs())

    for probe in probes:
        try:
            if probe.exists() and probe.is_file():
                return probe.resolve()
        except Exception:
            continue
    return None


def _typed_filename_path(filename: str, subfolder: str, ftype: str) -> Optional[Path]:
    if not filename:
        return None
    clean_sub = str(subfolder or "").strip().strip("/\\")
    kind = str(ftype or "output").strip().lower()

    base: Optional[Path] = None
    if folder_paths is not None:
        mapping = {
            "output": "get_output_directory",
            "temp": "get_temp_directory",
            "input": "get_input_directory",
        }
        getter_name = mapping.get(kind, "get_output_directory")
        try:
            getter = getattr(folder_paths, getter_name, None)
            if callable(getter):
                base = Path(str(getter()))
        except Exception:
            base = None

    if base is None:
        base = _output_dir("")

    target = base / clean_sub / str(filename).strip()
    try:
        if target.exists() and target.is_file():
            return target.resolve()
    except Exception:
        return None
    return None


def _collect_path_candidates(value: Any, out: List[Any], depth: int = 0) -> None:
    if value is None or depth > 4:
        return
    if isinstance(value, (str, Path)):
        out.append(value)
        return
    if isinstance(value, dict):
        for key in _PATH_KEYS:
            if key in value:
                _collect_path_candidates(value.get(key), out, depth + 1)

        filename = value.get("filename")
        subfolder = value.get("subfolder", "")
        ftype = value.get("type", "output")
        if isinstance(filename, (str, Path)):
            out.append(filename)
            typed = _typed_filename_path(str(filename), str(subfolder), str(ftype))
            if typed is not None:
                out.append(typed)
            if str(subfolder or "").strip():
                out.append(str(Path(str(subfolder)) / str(filename)))

        for nested in value.values():
            _collect_path_candidates(nested, out, depth + 1)
        return

    if isinstance(value, (list, tuple, set)):
        for item in list(value)[:16]:
            _collect_path_candidates(item, out, depth + 1)
        return

    for attr in ("path", "file", "filepath", "filename", "video_path", "audio_path", "source"):
        try:
            if hasattr(value, attr):
                _collect_path_candidates(getattr(value, attr), out, depth + 1)
        except Exception:
            continue


def _extract_input_file(value: Any) -> Optional[Path]:
    candidates: List[Any] = []
    _collect_path_candidates(value, candidates, depth=0)
    for candidate in candidates:
        resolved = _resolve_existing_file(candidate)
        if resolved is not None:
            return resolved
    return None


def _safe_ext(name: Any) -> str:
    text = str(name or "").strip().lower().lstrip(".")
    return "".join(ch for ch in text if ch.isalnum())


def _run_ffmpeg(args: Sequence[str]) -> Tuple[bool, str]:
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return False, "ffmpeg is not available"
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", *list(args)],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    return False, (proc.stderr or proc.stdout or f"ffmpeg exited with code {proc.returncode}").strip()


def _copy_or_transcode(
    source: Path,
    target: Path,
    ext: str,
    kind: str,
    fps: int = 24,
) -> Tuple[bool, str]:
    src_ext = _safe_ext(source.suffix)
    dst_ext = _safe_ext(ext)

    try:
        if source.resolve() == target.resolve():
            return True, ""
    except Exception:
        pass

    if src_ext == dst_ext or not dst_ext:
        try:
            shutil.copy2(source, target)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    if kind == "video":
        codec_args: List[str] = []
        if dst_ext == "mp4":
            codec_args = ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        elif dst_ext == "mov":
            codec_args = ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        elif dst_ext == "webm":
            codec_args = ["-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30"]
        elif dst_ext == "gif":
            codec_args = ["-an", "-vf", f"fps={max(1, int(fps))}"]
        elif dst_ext == "webp":
            codec_args = ["-an", "-loop", "0"]
        else:
            return False, f"Unsupported target video format '{dst_ext}'"
        return _run_ffmpeg(["-y", "-i", str(source), *codec_args, str(target)])

    if kind == "audio":
        codec_args = []
        if dst_ext == "wav":
            codec_args = ["-c:a", "pcm_s16le"]
        elif dst_ext == "mp3":
            codec_args = ["-c:a", "libmp3lame", "-q:a", "2"]
        elif dst_ext == "flac":
            codec_args = ["-c:a", "flac"]
        elif dst_ext == "ogg":
            codec_args = ["-c:a", "libvorbis", "-q:a", "5"]
        else:
            return False, f"Unsupported target audio format '{dst_ext}'"
        return _run_ffmpeg(["-y", "-i", str(source), *codec_args, str(target)])

    return False, "Unknown media kind"


def _extract_video_frames(value: Any) -> Optional[torch.Tensor]:
    if torch.is_tensor(value):
        t = value.detach()
        if t.ndim == 4 and t.shape[-1] in (3, 4):
            return t
        if t.ndim == 3 and t.shape[-1] in (3, 4):
            return t.unsqueeze(0)
        return None
    if isinstance(value, dict):
        for key in ("frames", "images", "image", "video_frames"):
            if key in value:
                found = _extract_video_frames(value[key])
                if found is not None:
                    return found
    if isinstance(value, (list, tuple)):
        for item in value[:8]:
            found = _extract_video_frames(item)
            if found is not None:
                return found
    return None


def _save_frames_with_ffmpeg(frames: List[Image.Image], target: Path, ext: str, fps: int) -> Tuple[bool, str]:
    if not frames:
        return False, "No frames to save"
    dst_ext = _safe_ext(ext)
    if dst_ext not in {"mp4", "mov", "webm"}:
        return False, f"Unsupported ffmpeg frame output format '{dst_ext}'"

    temp_root = _temp_dir()
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=str(temp_root), prefix="mkr_presave_video_") as tmp:
        tmp_path = Path(tmp)
        for idx, frame in enumerate(frames):
            frame.convert("RGB").save(tmp_path / f"frame_{idx:05d}.png", format="PNG", compress_level=1)

        codec_args: List[str] = []
        if dst_ext == "mp4":
            codec_args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        elif dst_ext == "mov":
            codec_args = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        elif dst_ext == "webm":
            codec_args = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30"]
        return _run_ffmpeg(
            [
                "-y",
                "-framerate",
                str(max(1, int(fps))),
                "-i",
                str(tmp_path / "frame_%05d.png"),
                *codec_args,
                str(target),
            ]
        )


def _extract_waveform(value: Any) -> Tuple[Optional[np.ndarray], int]:
    waveform: Optional[torch.Tensor] = None
    sample_rate = 44100

    if torch.is_tensor(value):
        waveform = value.detach().float().cpu()
    elif isinstance(value, dict):
        wf = value.get("waveform")
        if torch.is_tensor(wf):
            waveform = wf.detach().float().cpu()
        elif isinstance(wf, np.ndarray):
            waveform = torch.from_numpy(wf).float().cpu()
        for key in ("sample_rate", "sr", "rate"):
            if key in value:
                try:
                    sample_rate = int(value[key])
                    break
                except Exception:
                    continue
    elif isinstance(value, (list, tuple)) and len(value) >= 1:
        maybe_wave, maybe_sr = value[0], value[1] if len(value) > 1 else 44100
        if torch.is_tensor(maybe_wave):
            waveform = maybe_wave.detach().float().cpu()
        elif isinstance(maybe_wave, np.ndarray):
            waveform = torch.from_numpy(maybe_wave).float().cpu()
        try:
            sample_rate = int(maybe_sr)
        except Exception:
            sample_rate = 44100

    if waveform is None:
        return None, sample_rate

    t = waveform
    if t.ndim == 0:
        return None, sample_rate
    if t.ndim == 1:
        t = t.unsqueeze(0)
    elif t.ndim == 2:
        # Accept [C,S] (preferred) and fallback from [B,S].
        if t.shape[0] > 8 and t.shape[1] <= 8:
            t = t.transpose(0, 1)
        if t.shape[0] > 8:
            t = t[:1, :]
    elif t.ndim == 3:
        # Accept [B,C,S] and [B,S,C], use first batch.
        t = t[0]
        if t.ndim != 2:
            return None, sample_rate
        if t.shape[0] > 8 and t.shape[1] <= 8:
            t = t.transpose(0, 1)
        if t.shape[0] > 8:
            t = t[:1, :]
    else:
        return None, sample_rate

    arr = np.clip(t.numpy().astype(np.float32, copy=False), -1.0, 1.0)
    return arr, max(1, int(sample_rate))


def _save_wav(path: Path, waveform: np.ndarray, sample_rate: int) -> Tuple[bool, str]:
    try:
        channels = int(max(1, waveform.shape[0]))
        samples = np.clip(waveform, -1.0, 1.0)
        pcm = np.round(samples * 32767.0).astype(np.int16)
        interleaved = pcm.T.reshape(-1)

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(max(1, sample_rate)))
            wav_file.writeframes(interleaved.tobytes())
    except Exception as exc:
        return False, str(exc)
    return True, ""


def _preview_entry_from_file(source: Path, prefix: str, media_kind: Optional[str] = None) -> Optional[Dict[str, str]]:
    try:
        temp_dir = _temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        ext = _safe_ext(source.suffix) or "bin"
        name = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
        target = temp_dir / name
        shutil.copy2(source, target)
        return {
            "filename": name,
            "subfolder": "",
            "type": "temp",
            "format": ext,
            "media_kind": media_kind or _media_kind_from_suffix(source.suffix, "file"),
        }
    except Exception:
        return None


def _preview_entry_from_frames(
    frames: List[Image.Image],
    prefix: str,
    fps: int,
    webp_quality: int,
    loop: int,
) -> Optional[Dict[str, str]]:
    if not frames:
        return None
    try:
        temp_dir = _temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}_{uuid.uuid4().hex[:10]}.webp"
        target = temp_dir / name
        if len(frames) <= 1:
            _save_still_image(
                image=frames[0],
                path=target,
                output_format="webp",
                png_compress_level=4,
                jpeg_quality=92,
                webp_quality=int(webp_quality),
                pnginfo=None,
            )
        else:
            _save_animation(
                frames=frames,
                path=target,
                output_format="webp",
                webp_quality=int(webp_quality),
                animation_fps=int(max(1, fps)),
                animation_loop=int(max(0, loop)),
            )
        return {"filename": name, "subfolder": "", "type": "temp", "format": "webp", "media_kind": "image"}
    except Exception:
        return None


def _preview_entry_from_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    prefix: str,
) -> Optional[Dict[str, str]]:
    try:
        temp_dir = _temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}_{uuid.uuid4().hex[:10]}.wav"
        target = temp_dir / name
        ok, _ = _save_wav(target, waveform=waveform, sample_rate=int(max(1, sample_rate)))
        if not ok:
            return None
        return {"filename": name, "subfolder": "", "type": "temp", "format": "wav", "media_kind": "audio"}
    except Exception:
        return None


class MKRPresaveVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "preview_only": ("BOOLEAN", {"default": True}),
                "output_format": (["auto", "mp4", "mov", "webm", "gif", "webp"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_video"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "animation_fps": ("INT", {"default": 24, "min": 1, "max": 120, "step": 1}),
                "webp_quality": ("INT", {"default": 90, "min": 1, "max": 100, "step": 1}),
                "animation_loop": ("INT", {"default": 0, "min": 0, "max": 1000, "step": 1}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = INSPECT_PREVIEW

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return float("nan")

    def run(
        self,
        video: Any,
        preview_only: bool = True,
        output_format: str = "auto",
        filename_prefix: str = "MKR_video",
        subfolder: str = "",
        overwrite: bool = False,
        animation_fps: int = 24,
        webp_quality: int = 90,
        animation_loop: int = 0,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        saved_paths: List[str] = []
        preview_entries: List[Dict[str, str]] = []
        fmt = _safe_ext(output_format or "auto")
        if fmt and fmt != "auto" and fmt not in _VIDEO_FORMATS:
            warnings.append(f"Unsupported output_format='{output_format}', using 'auto'.")
            fmt = "auto"

        source = _extract_input_file(video)
        frames_tensor = _extract_video_frames(video) if source is None else None
        frames_for_preview: Optional[List[Image.Image]] = None

        if source is not None:
            entry = _preview_entry_from_file(source, prefix="mkrshift_presave_video")
            if entry is not None:
                preview_entries.append(entry)
        elif frames_tensor is not None:
            try:
                frames_for_preview = _image_batch_to_pil(frames_tensor)
            except Exception:
                frames_for_preview = None
            if frames_for_preview:
                entry = _preview_entry_from_frames(
                    frames=frames_for_preview,
                    prefix="mkrshift_presave_video",
                    fps=int(animation_fps),
                    webp_quality=int(webp_quality),
                    loop=int(animation_loop),
                )
                if entry is not None:
                    preview_entries.append(entry)
        else:
            warnings.append(
                "Video input is not file-like and no frame tensor was detected. "
                "Provide a path-like media object or IMAGE batch."
            )

        save_enabled = not bool(preview_only)
        if save_enabled:
            out_dir = _output_dir(subfolder=subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)

            if source is not None:
                src_ext = _safe_ext(source.suffix)
                dst_ext = src_ext if fmt == "auto" else fmt
                if not dst_ext:
                    dst_ext = "mp4"

                stem_raw = filename_label or source.stem or filename_prefix
                stem = _sanitize_basename(stem_raw, "MKR_video")
                target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))
                ok, error = _copy_or_transcode(
                    source=source,
                    target=target,
                    ext=dst_ext,
                    kind="video",
                    fps=int(animation_fps),
                )
                if ok:
                    saved_paths.append(str(target))
                else:
                    warnings.append(f"Failed to save video '{source.name}': {error}")
            else:
                if frames_tensor is not None:
                    frames = frames_for_preview if frames_for_preview is not None else _image_batch_to_pil(frames_tensor)
                    dst_ext = fmt if fmt != "auto" else "gif"
                    stem = _sanitize_basename(filename_label or filename_prefix, "MKR_video")
                    target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))

                    if dst_ext in {"gif", "webp"}:
                        try:
                            if len(frames) <= 1:
                                _save_still_image(
                                    image=frames[0],
                                    path=target,
                                    output_format=dst_ext,
                                    png_compress_level=4,
                                    jpeg_quality=92,
                                    webp_quality=int(webp_quality),
                                    pnginfo=None,
                                )
                            else:
                                _save_animation(
                                    frames=frames,
                                    path=target,
                                    output_format=dst_ext,
                                    webp_quality=int(webp_quality),
                                    animation_fps=int(animation_fps),
                                    animation_loop=int(animation_loop),
                                )
                            saved_paths.append(str(target))
                        except Exception as exc:
                            warnings.append(f"Failed to save frame animation: {exc}")
                    elif dst_ext in {"mp4", "mov", "webm"}:
                        ok, error = _save_frames_with_ffmpeg(
                            frames=frames,
                            target=target,
                            ext=dst_ext,
                            fps=int(animation_fps),
                        )
                        if ok:
                            saved_paths.append(str(target))
                        else:
                            warnings.append(f"Failed to encode video via ffmpeg: {error}")
                    else:
                        warnings.append(
                            f"Unsupported frame output format '{dst_ext}'. Use gif/webp or install ffmpeg for mp4/mov/webm."
                        )

        if not preview_entries and saved_paths:
            preview_source = _extract_input_file(saved_paths[0])
            if preview_source is not None:
                entry = _preview_entry_from_file(preview_source, prefix="mkrshift_presave_video")
                if entry is not None:
                    preview_entries.append(entry)

        return {
            "ui": {
                "save_summary": [
                    {
                        "saved_paths": saved_paths,
                        "warnings": warnings,
                    }
                ],
                "presave_media_state": [
                    {
                        "preview_only": bool(preview_only),
                        "kind": "video",
                        "saved_count": int(len(saved_paths)),
                        "preview_count": int(len(preview_entries)),
                        "preview_media_kind": (
                            str(preview_entries[0].get("media_kind", "video")) if preview_entries else "video"
                        ),
                    }
                ],
                "presave_video_preview": preview_entries,
            },
            "result": (),
        }


class MKRPresaveAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "preview_only": ("BOOLEAN", {"default": True}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_audio"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = INSPECT_PREVIEW

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return float("nan")

    def run(
        self,
        audio: Any,
        preview_only: bool = True,
        output_format: str = "auto",
        filename_prefix: str = "MKR_audio",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        saved_paths: List[str] = []
        preview_entries: List[Dict[str, str]] = []
        fmt = _safe_ext(output_format or "auto")
        if fmt and fmt != "auto" and fmt not in _AUDIO_FORMATS:
            warnings.append(f"Unsupported output_format='{output_format}', using 'auto'.")
            fmt = "auto"

        source = _extract_input_file(audio)
        waveform: Optional[np.ndarray] = None
        sample_rate = 44100
        if source is not None:
            entry = _preview_entry_from_file(source, prefix="mkrshift_presave_audio")
            if entry is not None:
                preview_entries.append(entry)
        else:
            waveform, sample_rate = _extract_waveform(audio)
            if waveform is None:
                warnings.append(
                    "Audio input is not file-like and no waveform tensor was detected. "
                    "Provide a path-like media object or AUDIO waveform payload."
                )
            else:
                entry = _preview_entry_from_waveform(
                    waveform=waveform,
                    sample_rate=int(sample_rate),
                    prefix="mkrshift_presave_audio",
                )
                if entry is not None:
                    preview_entries.append(entry)

        save_enabled = not bool(preview_only)
        if save_enabled:
            out_dir = _output_dir(subfolder=subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)

            if source is not None:
                src_ext = _safe_ext(source.suffix)
                dst_ext = src_ext if fmt == "auto" else fmt
                if not dst_ext:
                    dst_ext = "wav"

                stem_raw = filename_label or source.stem or filename_prefix
                stem = _sanitize_basename(stem_raw, "MKR_audio")
                target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))
                ok, error = _copy_or_transcode(
                    source=source,
                    target=target,
                    ext=dst_ext,
                    kind="audio",
                )
                if ok:
                    saved_paths.append(str(target))
                else:
                    warnings.append(f"Failed to save audio '{source.name}': {error}")
            else:
                if waveform is not None:
                    dst_ext = fmt if fmt != "auto" else "wav"
                    stem = _sanitize_basename(filename_label or filename_prefix, "MKR_audio")
                    target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=dst_ext, overwrite=bool(overwrite))

                    if dst_ext == "wav":
                        ok, error = _save_wav(target, waveform=waveform, sample_rate=sample_rate)
                        if ok:
                            saved_paths.append(str(target))
                        else:
                            warnings.append(f"Failed to write WAV file: {error}")
                    else:
                        temp_dir = _temp_dir()
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        temp_wav = _resolve_output_file(
                            out_dir=temp_dir,
                            stem=f"{stem}_src",
                            ext="wav",
                            overwrite=False,
                        )
                        wav_ok, wav_error = _save_wav(temp_wav, waveform=waveform, sample_rate=sample_rate)
                        if not wav_ok:
                            warnings.append(f"Failed to build temp WAV for transcode: {wav_error}")
                        else:
                            ok, error = _copy_or_transcode(
                                source=temp_wav,
                                target=target,
                                ext=dst_ext,
                                kind="audio",
                            )
                            try:
                                temp_wav.unlink(missing_ok=True)
                            except Exception:
                                pass
                            if ok:
                                saved_paths.append(str(target))
                            else:
                                warnings.append(f"Failed to encode audio via ffmpeg: {error}")

        if not preview_entries and saved_paths:
            preview_source = _extract_input_file(saved_paths[0])
            if preview_source is not None:
                entry = _preview_entry_from_file(preview_source, prefix="mkrshift_presave_audio")
                if entry is not None:
                    preview_entries.append(entry)

        return {
            "ui": {
                "save_summary": [
                    {
                        "saved_paths": saved_paths,
                        "warnings": warnings,
                    }
                ],
                "presave_media_state": [
                    {
                        "preview_only": bool(preview_only),
                        "kind": "audio",
                        "saved_count": int(len(saved_paths)),
                        "preview_count": int(len(preview_entries)),
                        "preview_media_kind": (
                            str(preview_entries[0].get("media_kind", "audio")) if preview_entries else "audio"
                        ),
                    }
                ],
                "presave_audio_preview": preview_entries,
            },
            "result": (),
        }
