import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import torch

from .categories import MEDIA_AUDIO_UTILITY, MEDIA_TIMELINE, MEDIA_WATERMARK
from .xmedia_batch1_nodes import _build_video_payload, _decode_video_to_pil, _pil_to_tensor, _save_video_from_pil
from .xmedia_batch2_nodes import _load_audio_waveform, _save_audio_result
from .xmedia_nodes import _json_text, _make_audio_payload, _make_video_payload, _read_video_metadata
from .xmedia_extra_nodes import _resample_waveform
from .xpresave import _image_batch_to_pil, _output_dir, _resolve_output_file, _sanitize_basename
from .xpresave_media import _extract_input_file, _ffmpeg_bin, _safe_ext


def _clamp_float(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, float(value))))


def _clamp_int(value: int, low: int, high: int) -> int:
    return int(max(low, min(high, int(value))))


def _merge_summary(base_json: str, extra: Dict[str, Any]) -> str:
    data: Dict[str, Any] = {}
    try:
        parsed = json.loads(str(base_json or "{}"))
        if isinstance(parsed, dict):
            data.update(parsed)
    except Exception:
        pass
    data.update(extra)
    return _json_text(data)


def _audio_empty_payload(source: Optional[Path], warnings: List[str]):
    payload = _make_audio_payload(path=source)
    return (payload, "", 0.0, _json_text({"warnings": warnings}))


def _resolve_video_format(source: Optional[Path], requested: str, warnings: List[str]) -> str:
    fmt = _safe_ext(requested)
    if fmt == "auto":
        src = _safe_ext(source.suffix) if source is not None else ""
        fmt = src if src in {"gif", "webp", "mp4", "mov", "webm"} else "gif"
    if fmt not in {"gif", "webp", "mp4", "mov", "webm"}:
        fmt = "gif"
        warnings.append("Unsupported video format, using gif")
    if fmt in {"mp4", "mov", "webm"} and not _ffmpeg_bin():
        fmt = "gif"
        warnings.append("ffmpeg unavailable for mp4/mov/webm, using gif")
    return fmt


def _save_video_result(
    frames: Sequence[Image.Image],
    fps: float,
    source: Optional[Path],
    output_format: str,
    filename_prefix: str,
    filename_label: str,
    subfolder: str,
    overwrite: bool,
    warnings: List[str],
) -> Tuple[Dict[str, Any], str, str]:
    fmt = _resolve_video_format(source, output_format, warnings)
    out_dir = _output_dir(subfolder)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_basename(filename_label or filename_prefix, filename_prefix)
    target = _resolve_output_file(out_dir=out_dir, stem=stem, ext=fmt, overwrite=bool(overwrite))
    ok, error = _save_video_from_pil(frames=frames, fps=float(max(1.0, fps)), target=target, fmt=fmt)
    if not ok:
        warnings.append(f"Failed to save video: {error}")
        payload = _build_video_payload(_pil_to_tensor(frames), fps=float(max(1.0, fps)), source_path=source)
        return payload, "", _json_text({"warnings": warnings})
    meta, meta_warn = _read_video_metadata(target)
    warnings.extend(meta_warn)
    payload = _make_video_payload(path=target, metadata=meta)
    return payload, str(target), ""


def _get_font(size: int) -> ImageFont.ImageFont:
    s = int(max(8, size))
    try:
        return ImageFont.truetype("DejaVuSans.ttf", s)
    except Exception:
        try:
            return ImageFont.truetype("Arial.ttf", s)
        except Exception:
            return ImageFont.load_default()


def _parse_color(value: str, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    try:
        c = ImageColor.getrgb(str(value or "").strip() or "#ffffff")
        return int(c[0]), int(c[1]), int(c[2])
    except Exception:
        return fallback


def _moving_average_1d(x: np.ndarray, win: int) -> np.ndarray:
    n = int(max(1, win))
    if n <= 1:
        return x.astype(np.float32, copy=False)
    kernel = np.ones((n,), dtype=np.float32) / float(n)
    return np.convolve(x.astype(np.float32, copy=False), kernel, mode="same").astype(np.float32, copy=False)


def _ensure_same_length(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    n = int(max(a.shape[1], b.shape[1]))
    if a.shape[1] < n:
        pad = np.zeros((a.shape[0], n - a.shape[1]), dtype=np.float32)
        a = np.concatenate([a, pad], axis=1)
    if b.shape[1] < n:
        pad = np.zeros((b.shape[0], n - b.shape[1]), dtype=np.float32)
        b = np.concatenate([b, pad], axis=1)
    return a, b


def _to_stereo(w: np.ndarray) -> np.ndarray:
    if w.shape[0] == 1:
        return np.repeat(w, 2, axis=0)
    if w.shape[0] >= 2:
        return w[:2, :]
    return np.zeros((2, max(1, w.shape[1] if w.ndim == 2 else 1)), dtype=np.float32)


def _payload_signature(text: str, seed: int) -> str:
    raw = f"{seed}:{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()


def _parse_srt_time_to_sec(text: str) -> float:
    s = str(text or "").strip().replace(",", ".")
    m = re.match(r"^(\d+):(\d+):(\d+)\.(\d+)$", s)
    if not m:
        return 0.0
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3))
    ms = float("0." + m.group(4))
    return float(hh * 3600 + mm * 60 + ss + ms)


def _parse_srt(srt_text: str) -> List[Dict[str, Any]]:
    text = str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out: List[Dict[str, Any]] = []
    for block in blocks:
        lines = [ln.strip("\n") for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        idx_line = lines[0]
        time_line = lines[1]
        txt_lines = lines[2:] if "-->" in time_line else lines[1:]
        if "-->" not in time_line:
            continue
        parts = [p.strip() for p in time_line.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_srt_time_to_sec(parts[0])
        end = _parse_srt_time_to_sec(parts[1])
        if end <= start:
            continue
        out.append({"index": idx_line, "start": float(start), "end": float(end), "text": "\n".join(txt_lines).strip()})
    return out


def _audio_payload_from_wave(path: Optional[Path], waveform: np.ndarray, sample_rate: int) -> Dict[str, Any]:
    payload = _make_audio_payload(path=path, sample_rate=int(max(1, sample_rate)))
    payload["waveform"] = torch.from_numpy(np.clip(waveform.astype(np.float32, copy=False), -1.0, 1.0))
    return payload


class MKRCompressorGate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "threshold_db": ("FLOAT", {"default": -18.0, "min": -60.0, "max": 0.0, "step": 0.1}),
                "ratio": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 20.0, "step": 0.1}),
                "attack_ms": ("FLOAT", {"default": 10.0, "min": 0.1, "max": 500.0, "step": 0.1}),
                "release_ms": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 2000.0, "step": 0.1}),
                "gate_threshold_db": ("FLOAT", {"default": -50.0, "min": -90.0, "max": 0.0, "step": 0.1}),
                "gate_floor_db": ("FLOAT", {"default": -24.0, "min": -60.0, "max": 0.0, "step": 0.1}),
                "makeup_db": ("FLOAT", {"default": 0.0, "min": -24.0, "max": 24.0, "step": 0.1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_comp_gate"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        threshold_db: float = -18.0,
        ratio: float = 3.0,
        attack_ms: float = 10.0,
        release_ms: float = 120.0,
        gate_threshold_db: float = -50.0,
        gate_floor_db: float = -24.0,
        makeup_db: float = 0.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_comp_gate",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sr, source, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return _audio_empty_payload(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sample_rate = int(max(1, sr))
        env_input = np.max(np.abs(w), axis=0)
        attack_coeff = float(math.exp(-1.0 / max(1.0, float(attack_ms) * sample_rate / 1000.0)))
        release_coeff = float(math.exp(-1.0 / max(1.0, float(release_ms) * sample_rate / 1000.0)))
        ratio_v = float(max(1.0, ratio))

        gains = np.ones((env_input.size,), dtype=np.float32)
        env = 0.0
        for i, x in enumerate(env_input):
            if x > env:
                env = attack_coeff * env + (1.0 - attack_coeff) * float(x)
            else:
                env = release_coeff * env + (1.0 - release_coeff) * float(x)
            env_db = float(20.0 * math.log10(max(1e-9, env)))

            comp_gain_db = 0.0
            if env_db > float(threshold_db):
                compressed_db = float(threshold_db) + (env_db - float(threshold_db)) / ratio_v
                comp_gain_db = compressed_db - env_db

            gate_gain_db = 0.0
            if env_db < float(gate_threshold_db):
                t = float((float(gate_threshold_db) - env_db) / 12.0)
                t = float(max(0.0, min(1.0, t)))
                gate_gain_db = float(gate_floor_db) * t

            total_db = comp_gain_db + gate_gain_db + float(makeup_db)
            gains[i] = float(10.0 ** (total_db / 20.0))

        out = np.clip(w * gains[None, :], -1.0, 1.0).astype(np.float32, copy=False)
        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "threshold_db": float(threshold_db),
            "ratio": float(ratio_v),
            "gate_threshold_db": float(gate_threshold_db),
            "gate_floor_db": float(gate_floor_db),
            "makeup_db": float(makeup_db),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRDeEsser:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "threshold_db": ("FLOAT", {"default": -35.0, "min": -80.0, "max": -5.0, "step": 0.1}),
                "center_freq_hz": ("FLOAT", {"default": 6500.0, "min": 2000.0, "max": 12000.0, "step": 10.0}),
                "amount": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_deesser"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        threshold_db: float = -35.0,
        center_freq_hz: float = 6500.0,
        amount: float = 0.6,
        output_format: str = "auto",
        filename_prefix: str = "MKR_deesser",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sr, source, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return _audio_empty_payload(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sample_rate = int(max(1, sr))
        threshold = float(10.0 ** (float(threshold_db) / 20.0))
        amt = float(_clamp_float(amount, 0.0, 1.0))
        cf = float(max(2000.0, min(12000.0, center_freq_hz)))

        lp_win = int(max(3, min(301, round(sample_rate / max(200.0, cf)))))
        env_win = int(max(8, round(sample_rate * 0.004)))

        out = np.zeros_like(w, dtype=np.float32)
        for ch in range(w.shape[0]):
            x = w[ch]
            low = _moving_average_1d(x, lp_win)
            high = x - low
            env = _moving_average_1d(np.abs(high), env_win)
            red = np.clip((env - threshold) / max(1e-9, threshold), 0.0, 1.0) * amt
            high2 = high * (1.0 - red)
            out[ch] = low + high2

        out = np.clip(out, -1.0, 1.0)
        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {"threshold_db": float(threshold_db), "center_freq_hz": float(cf), "amount": float(amt)}
        return (payload, path, float(duration), _merge_summary(summary, extra))


def _spectral_gate_channel(x: np.ndarray, n_fft: int, noise_frames: int, threshold_mult: float, atten_lin: float) -> np.ndarray:
    n = int(x.size)
    hop = int(max(1, n_fft // 2))
    win = np.hanning(n_fft).astype(np.float32)
    if n < n_fft:
        pad = np.zeros((n_fft - n,), dtype=np.float32)
        x = np.concatenate([x.astype(np.float32, copy=False), pad], axis=0)
        n = int(x.size)

    frames: List[np.ndarray] = []
    idxs: List[int] = []
    for i in range(0, n - n_fft + 1, hop):
        seg = x[i : i + n_fft] * win
        spec = np.fft.rfft(seg)
        frames.append(spec)
        idxs.append(i)
    if not frames:
        return x.astype(np.float32, copy=False)

    mags = np.stack([np.abs(s) for s in frames], axis=0)
    noise_n = int(max(1, min(mags.shape[0], noise_frames)))
    noise_profile = np.mean(mags[:noise_n], axis=0)

    out = np.zeros((n,), dtype=np.float32)
    norm = np.zeros((n,), dtype=np.float32)
    for fi, spec in enumerate(frames):
        mag = np.abs(spec)
        ph = np.angle(spec)
        keep = mag >= (noise_profile * threshold_mult)
        mag2 = np.where(keep, mag, mag * atten_lin)
        rec = np.fft.irfft(mag2 * np.exp(1j * ph), n=n_fft).astype(np.float32)
        pos = idxs[fi]
        out[pos : pos + n_fft] += rec * win
        norm[pos : pos + n_fft] += win
    norm = np.where(norm > 1e-6, norm, 1.0)
    y = out / norm
    return y[: x.shape[0]].astype(np.float32, copy=False)


class MKRNoiseReductionSpectral:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "noise_profile_sec": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 10.0, "step": 0.05}),
                "sensitivity": ("FLOAT", {"default": 1.5, "min": 0.5, "max": 8.0, "step": 0.1}),
                "reduction_db": ("FLOAT", {"default": -14.0, "min": -60.0, "max": -1.0, "step": 0.1}),
                "fft_size": ("INT", {"default": 1024, "min": 256, "max": 8192, "step": 2}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_noise_reduce"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        noise_profile_sec: float = 0.5,
        sensitivity: float = 1.5,
        reduction_db: float = -14.0,
        fft_size: int = 1024,
        output_format: str = "auto",
        filename_prefix: str = "MKR_noise_reduce",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sr, source, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return _audio_empty_payload(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sample_rate = int(max(1, sr))
        nfft = int(max(256, min(8192, fft_size)))
        nfft = int(nfft + (nfft % 2))
        hop = int(max(1, nfft // 2))
        prof_frames = int(max(1, round(float(max(0.05, noise_profile_sec)) * float(sample_rate) / float(hop))))
        sens = float(max(0.5, min(8.0, sensitivity)))
        atten = float(10.0 ** (float(reduction_db) / 20.0))

        out = np.zeros_like(w, dtype=np.float32)
        for ch in range(w.shape[0]):
            out[ch] = _spectral_gate_channel(
                x=w[ch],
                n_fft=nfft,
                noise_frames=prof_frames,
                threshold_mult=sens,
                atten_lin=atten,
            )[: w.shape[1]]
        out = np.clip(out, -1.0, 1.0)

        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "noise_profile_sec": float(noise_profile_sec),
            "sensitivity": float(sens),
            "reduction_db": float(reduction_db),
            "fft_size": int(nfft),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRSidechainDucker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "main_audio": ("*",),
                "sidechain_audio": ("*",),
                "duck_db": ("FLOAT", {"default": -12.0, "min": -36.0, "max": -1.0, "step": 0.1}),
                "threshold_db": ("FLOAT", {"default": -40.0, "min": -80.0, "max": 0.0, "step": 0.1}),
                "attack_ms": ("FLOAT", {"default": 15.0, "min": 0.5, "max": 500.0, "step": 0.1}),
                "release_ms": ("FLOAT", {"default": 180.0, "min": 1.0, "max": 2000.0, "step": 0.1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_sidechain_duck"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        main_audio: Any,
        sidechain_audio: Any,
        duck_db: float = -12.0,
        threshold_db: float = -40.0,
        attack_ms: float = 15.0,
        release_ms: float = 180.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_sidechain_duck",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        main_w, main_sr, source, err_main = _load_audio_waveform(main_audio)
        side_w, side_sr, _, err_side = _load_audio_waveform(sidechain_audio)
        if main_w is None or side_w is None:
            if err_main:
                warnings.append(err_main)
            if err_side:
                warnings.append(err_side)
            return _audio_empty_payload(source, warnings)

        sr = int(max(1, main_sr))
        main = main_w.astype(np.float32, copy=False)
        side = side_w.astype(np.float32, copy=False)
        if int(side_sr) != sr:
            side = _resample_waveform(side, int(side_sr), sr).astype(np.float32, copy=False)
        main, side = _ensure_same_length(main, side)

        side_env = np.max(np.abs(side), axis=0)
        threshold = float(10.0 ** (float(threshold_db) / 20.0))
        max_reduction_lin = float(10.0 ** (float(duck_db) / 20.0))

        a = float(math.exp(-1.0 / max(1.0, float(attack_ms) * sr / 1000.0)))
        r = float(math.exp(-1.0 / max(1.0, float(release_ms) * sr / 1000.0)))
        env = 0.0
        gain = np.ones((side_env.size,), dtype=np.float32)
        for i, x in enumerate(side_env):
            if x > env:
                env = a * env + (1.0 - a) * float(x)
            else:
                env = r * env + (1.0 - r) * float(x)
            if env <= threshold:
                tgt = 1.0
            else:
                t = float((env - threshold) / max(1e-9, (1.0 - threshold)))
                t = float(max(0.0, min(1.0, t)))
                tgt = 1.0 + (max_reduction_lin - 1.0) * t
            gain[i] = float(tgt)

        out = np.clip(main * gain[None, :], -1.0, 1.0).astype(np.float32, copy=False)
        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sr,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {"duck_db": float(duck_db), "threshold_db": float(threshold_db)}
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRStemSplitter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "save_stems": ("BOOLEAN", {"default": True}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "wav"}),
                "filename_prefix": ("STRING", {"default": "MKR_stem"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "MKR_AUDIO", "MKR_AUDIO", "MKR_AUDIO", "STRING")
    RETURN_NAMES = ("vocals", "drums", "bass", "other", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_AUDIO_UTILITY

    def run(
        self,
        audio: Any,
        save_stems: bool = True,
        output_format: str = "wav",
        filename_prefix: str = "MKR_stem",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sr, source, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            empty = _make_audio_payload(path=source)
            return (empty, empty, empty, empty, _json_text({"warnings": warnings}))

        w = waveform.astype(np.float32, copy=False)
        sample_rate = int(max(1, sr))
        n = int(w.shape[1])

        freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate)).astype(np.float32)
        bass_mask = (freqs <= 250.0).astype(np.float32)
        vocal_mask = ((freqs > 250.0) & (freqs <= 4000.0)).astype(np.float32)
        high_mask = (freqs > 4000.0).astype(np.float32)

        bass = np.zeros_like(w, dtype=np.float32)
        vocals = np.zeros_like(w, dtype=np.float32)
        drums = np.zeros_like(w, dtype=np.float32)
        for ch in range(w.shape[0]):
            spec = np.fft.rfft(w[ch].astype(np.float64))
            bass[ch] = np.fft.irfft(spec * bass_mask.astype(np.float64), n=n).astype(np.float32)
            vocals[ch] = np.fft.irfft(spec * vocal_mask.astype(np.float64), n=n).astype(np.float32)
            high = np.fft.irfft(spec * high_mask.astype(np.float64), n=n).astype(np.float32)
            trans = np.concatenate([np.zeros((1,), dtype=np.float32), np.diff(w[ch])], axis=0)
            drums[ch] = 0.7 * high + 0.3 * trans

        other = w - (0.6 * vocals + 0.8 * bass + 0.6 * drums)
        bass = np.clip(bass, -1.0, 1.0)
        vocals = np.clip(vocals, -1.0, 1.0)
        drums = np.clip(drums, -1.0, 1.0)
        other = np.clip(other, -1.0, 1.0)

        def save_or_payload(stem_name: str, wave_data: np.ndarray) -> Dict[str, Any]:
            if not bool(save_stems):
                return _audio_payload_from_wave(path=None, waveform=wave_data, sample_rate=sample_rate)
            payload, _, _, _ = _save_audio_result(
                waveform=wave_data,
                sample_rate=sample_rate,
                source=source,
                output_format=output_format,
                filename_prefix=filename_prefix,
                filename_label=f"{filename_label or filename_prefix}_{stem_name}",
                subfolder=subfolder,
                overwrite=overwrite,
                warnings=warnings,
            )
            return payload

        p_vocals = save_or_payload("vocals", vocals)
        p_drums = save_or_payload("drums", drums)
        p_bass = save_or_payload("bass", bass)
        p_other = save_or_payload("other", other)

        summary = {
            "sample_rate": int(sample_rate),
            "channels": int(w.shape[0]),
            "duration_sec": float(w.shape[1] / float(sample_rate)),
            "save_stems": bool(save_stems),
            "warnings": warnings,
        }
        return (p_vocals, p_drums, p_bass, p_other, _json_text(summary))


class MKRInvisibleImageWatermark:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "payload_text": ("STRING", {"default": "MKRSHIFT", "multiline": False}),
                "strength": ("FLOAT", {"default": 0.01, "min": 0.0005, "max": 0.05, "step": 0.0005}),
                "seed": ("INT", {"default": 1337, "min": 0, "max": 2**31 - 1, "step": 1}),
                "channel": (["blue", "green", "red", "luma"], {"default": "blue"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_WATERMARK

    def run(self, image: torch.Tensor, payload_text: str = "MKRSHIFT", strength: float = 0.01, seed: int = 1337, channel: str = "blue"):
        warnings: List[str] = []
        t = image.detach().float()
        if t.ndim == 3:
            t = t.unsqueeze(0)
        if t.ndim != 4 or int(t.shape[-1]) < 3:
            warnings.append("Invalid IMAGE tensor")
            return (torch.zeros((1, 64, 64, 3), dtype=torch.float32), _json_text({"warnings": warnings}))

        sig = _payload_signature(payload_text, int(seed))
        rng = np.random.default_rng(int(sig[:8], 16))
        out = t.clone().cpu().numpy()
        str_v = float(_clamp_float(strength, 0.0005, 0.05))
        ch_name = str(channel or "blue").strip().lower()
        ch_idx = {"red": 0, "green": 1, "blue": 2}.get(ch_name, 2)

        for i in range(out.shape[0]):
            h = out.shape[1]
            w = out.shape[2]
            pattern = rng.choice([-1.0, 1.0], size=(h, w)).astype(np.float32)
            bit_scalar = 1.0 if (int(sig[(i * 2) % len(sig)], 16) % 2 == 0) else -1.0
            delta = pattern * str_v * bit_scalar
            if ch_name == "luma":
                for ch in range(3):
                    out[i, :, :, ch] = np.clip(out[i, :, :, ch] + delta * 0.333, 0.0, 1.0)
            else:
                out[i, :, :, ch_idx] = np.clip(out[i, :, :, ch_idx] + delta, 0.0, 1.0)

        summary = {
            "signature": sig,
            "payload_len": int(len(str(payload_text))),
            "strength": float(str_v),
            "channel": ch_name,
            "warnings": warnings,
        }
        return (torch.from_numpy(out).float(), _json_text(summary))


class MKRInvisibleAudioWatermark:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("*",),
                "payload_text": ("STRING", {"default": "MKRSHIFT", "multiline": False}),
                "strength_db": ("FLOAT", {"default": -42.0, "min": -80.0, "max": -20.0, "step": 0.1}),
                "carrier_hz": ("FLOAT", {"default": 15000.0, "min": 2000.0, "max": 20000.0, "step": 1.0}),
                "chunk_ms": ("INT", {"default": 80, "min": 20, "max": 1000, "step": 1}),
                "seed": ("INT", {"default": 1337, "min": 0, "max": 2**31 - 1, "step": 1}),
                "output_format": (["auto", "wav", "mp3", "flac", "ogg"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_invisible_audio_wm"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "output_path", "duration_sec", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_WATERMARK

    def run(
        self,
        audio: Any,
        payload_text: str = "MKRSHIFT",
        strength_db: float = -42.0,
        carrier_hz: float = 15000.0,
        chunk_ms: int = 80,
        seed: int = 1337,
        output_format: str = "auto",
        filename_prefix: str = "MKR_invisible_audio_wm",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        waveform, sr, source, err = _load_audio_waveform(audio)
        if waveform is None:
            if err:
                warnings.append(err)
            return _audio_empty_payload(source, warnings)

        w = waveform.astype(np.float32, copy=False)
        sample_rate = int(max(1, sr))
        sig = _payload_signature(payload_text, int(seed))
        rng = np.random.default_rng(int(sig[:8], 16))
        amp = float(10.0 ** (float(strength_db) / 20.0))
        carrier = float(max(2000.0, min(sample_rate * 0.45, carrier_hz)))
        chunk = int(max(1, round(float(max(20, chunk_ms)) * sample_rate / 1000.0)))

        bits: List[int] = []
        for b in str(payload_text).encode("utf-8", errors="ignore"):
            for shift in range(7, -1, -1):
                bits.append((b >> shift) & 1)
            bits.append(0)
        if not bits:
            bits = [1]

        wm = np.zeros((w.shape[1],), dtype=np.float32)
        cursor = 0
        t_total = np.arange(w.shape[1], dtype=np.float32) / float(sample_rate)
        while cursor < w.shape[1]:
            for bit in bits:
                if cursor >= w.shape[1]:
                    break
                end = int(min(w.shape[1], cursor + chunk))
                seg_t = t_total[cursor:end]
                phase_offset = float(rng.uniform(0.0, 2.0 * math.pi))
                freq = carrier if bit == 1 else carrier * 0.92
                tone = np.sin(2.0 * math.pi * freq * seg_t + phase_offset).astype(np.float32)
                wm[cursor:end] += tone
                cursor = end
            if cursor < w.shape[1]:
                break
        wm = wm * amp

        out = np.clip(w + wm[None, :], -1.0, 1.0).astype(np.float32, copy=False)
        payload, path, duration, summary = _save_audio_result(
            waveform=out,
            sample_rate=sample_rate,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        extra = {
            "signature": sig,
            "payload_len": int(len(str(payload_text))),
            "strength_db": float(strength_db),
            "carrier_hz": float(carrier),
            "chunk_ms": int(chunk_ms),
        }
        return (payload, path, float(duration), _merge_summary(summary, extra))


class MKRChapterMarkerGenerator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "duration_sec": ("FLOAT", {"default": 60.0, "min": 0.0, "max": 86400.0, "step": 0.01}),
                "scene_ranges_json": ("STRING", {"default": "[]", "multiline": True}),
                "beat_markers_json": ("STRING", {"default": "[]", "multiline": True}),
                "silence_ranges_json": ("STRING", {"default": "[]", "multiline": True}),
                "min_chapter_sec": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 600.0, "step": 0.1}),
                "title_prefix": ("STRING", {"default": "Chapter", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("chapters_json", "ffmetadata_text", "chapter_count", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        duration_sec: float = 60.0,
        scene_ranges_json: str = "[]",
        beat_markers_json: str = "[]",
        silence_ranges_json: str = "[]",
        min_chapter_sec: float = 8.0,
        title_prefix: str = "Chapter",
    ):
        warnings: List[str] = []
        duration = float(max(0.0, duration_sec))
        min_gap = float(max(1.0, min_chapter_sec))

        candidates: List[float] = [0.0]
        try:
            scenes = json.loads(scene_ranges_json or "[]")
            if isinstance(scenes, list):
                for it in scenes:
                    if isinstance(it, dict):
                        candidates.append(float(it.get("start_time", it.get("start_sec", 0.0)) or 0.0))
        except Exception:
            warnings.append("scene_ranges_json parse failed")

        try:
            beats = json.loads(beat_markers_json or "[]")
            if isinstance(beats, list):
                for i, b in enumerate(beats):
                    if i % 8 == 0:
                        candidates.append(float(b))
        except Exception:
            warnings.append("beat_markers_json parse failed")

        try:
            sil = json.loads(silence_ranges_json or "[]")
            if isinstance(sil, list):
                for it in sil:
                    if isinstance(it, dict):
                        candidates.append(float(it.get("end_sec", it.get("end_time", 0.0)) or 0.0))
        except Exception:
            warnings.append("silence_ranges_json parse failed")

        candidates = sorted(set(float(max(0.0, min(duration, c))) for c in candidates if not math.isnan(float(c))))
        chosen: List[float] = []
        last = -1e9
        for c in candidates:
            if c - last >= min_gap:
                chosen.append(c)
                last = c
        if not chosen:
            chosen = [0.0]
        if duration > 0.0 and chosen[-1] >= duration:
            chosen = chosen[:-1] if len(chosen) > 1 else chosen

        chapters: List[Dict[str, Any]] = []
        for i, st in enumerate(chosen):
            en = duration if i + 1 >= len(chosen) else chosen[i + 1]
            chapters.append(
                {
                    "index": int(i + 1),
                    "title": f"{title_prefix} {i + 1}",
                    "start_sec": float(round(st, 6)),
                    "end_sec": float(round(max(st, en), 6)),
                }
            )

        ff_lines = [";FFMETADATA1"]
        for ch in chapters:
            ff_lines.append("[CHAPTER]")
            ff_lines.append("TIMEBASE=1/1000")
            ff_lines.append(f"START={int(round(ch['start_sec'] * 1000.0))}")
            ff_lines.append(f"END={int(round(ch['end_sec'] * 1000.0))}")
            ff_lines.append(f"title={ch['title']}")
        ffmeta = "\n".join(ff_lines) + "\n"

        summary = {"chapter_count": int(len(chapters)), "duration_sec": float(duration), "warnings": warnings}
        return (_json_text(chapters), ffmeta, int(len(chapters)), _json_text(summary))


class MKRSubtitleBurnIn:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "subtitles_path": ("STRING", {"default": ""}),
                "subtitles_srt": ("STRING", {"default": "", "multiline": True}),
                "font_size": ("INT", {"default": 42, "min": 8, "max": 256, "step": 1}),
                "position": (["bottom", "center", "top"], {"default": "bottom"}),
                "y_margin": ("INT", {"default": 64, "min": 0, "max": 1024, "step": 1}),
                "text_color": ("STRING", {"default": "#FFFFFF"}),
                "stroke_color": ("STRING", {"default": "#000000"}),
                "stroke_width": ("INT", {"default": 3, "min": 0, "max": 20, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_sub_burnin"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        video: Any,
        subtitles_path: str = "",
        subtitles_srt: str = "",
        font_size: int = 42,
        position: str = "bottom",
        y_margin: int = 64,
        text_color: str = "#FFFFFF",
        stroke_color: str = "#000000",
        stroke_width: int = 3,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_sub_burnin",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        srt_text = str(subtitles_srt or "")
        p = Path(str(subtitles_path or "").strip())
        if p.as_posix().strip():
            try:
                if p.exists() and p.is_file():
                    srt_text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                warnings.append(f"Failed to read subtitles_path: {exc}")
        cues = _parse_srt(srt_text)
        if not cues:
            warnings.append("No subtitle cues found")
            payload, path, save_summary = _save_video_result(
                frames=frames,
                fps=fps,
                source=source,
                output_format=output_format,
                filename_prefix=filename_prefix,
                filename_label=filename_label,
                subfolder=subfolder,
                overwrite=overwrite,
                warnings=warnings,
            )
            summary = {"output_path": path, "cue_count": 0, "warnings": warnings}
            if save_summary:
                summary["output_path"] = ""
            return (payload, path, _json_text(summary))

        font = _get_font(int(font_size))
        tc = _parse_color(text_color, (255, 255, 255))
        sc = _parse_color(stroke_color, (0, 0, 0))
        pos = str(position or "bottom").strip().lower()
        margin = int(max(0, y_margin))
        sw = int(max(0, stroke_width))

        out_frames: List[Image.Image] = []
        for i, frame in enumerate(frames):
            t = float(i / fps)
            active = [cue["text"] for cue in cues if float(cue["start"]) <= t < float(cue["end"])]
            if not active:
                out_frames.append(frame.convert("RGB"))
                continue
            text = "\n".join(active[-2:])
            img = frame.convert("RGB")
            draw = ImageDraw.Draw(img)
            bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4, stroke_width=sw)
            tw = int(max(1, bbox[2] - bbox[0]))
            th = int(max(1, bbox[3] - bbox[1]))
            x = int((img.width - tw) // 2)
            if pos == "top":
                y = margin
            elif pos == "center":
                y = int((img.height - th) // 2)
            else:
                y = int(max(0, img.height - th - margin))
            draw.multiline_text(
                (x, y),
                text,
                font=font,
                fill=(tc[0], tc[1], tc[2]),
                align="center",
                spacing=4,
                stroke_width=sw,
                stroke_fill=(sc[0], sc[1], sc[2]),
            )
            out_frames.append(img)

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {"output_path": out_path, "cue_count": int(len(cues)), "warnings": warnings}
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))


class MKRLowerThirdTemplate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("*",),
                "headline": ("STRING", {"default": "Headline", "multiline": False}),
                "subline": ("STRING", {"default": "Subtitle line", "multiline": False}),
                "start_sec": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 3600.0, "step": 0.01}),
                "duration_sec": ("FLOAT", {"default": 3.5, "min": 0.1, "max": 3600.0, "step": 0.01}),
                "animate_sec": ("FLOAT", {"default": 0.35, "min": 0.05, "max": 5.0, "step": 0.01}),
                "inset_x": ("INT", {"default": 56, "min": 0, "max": 2048, "step": 1}),
                "inset_y": ("INT", {"default": 56, "min": 0, "max": 2048, "step": 1}),
                "bar_color": ("STRING", {"default": "#121212"}),
                "accent_color": ("STRING", {"default": "#E7B13D"}),
                "text_color": ("STRING", {"default": "#FFFFFF"}),
                "font_size_headline": ("INT", {"default": 44, "min": 8, "max": 256, "step": 1}),
                "font_size_subline": ("INT", {"default": 28, "min": 8, "max": 256, "step": 1}),
                "fallback_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.1}),
                "output_format": (["auto", "gif", "webp", "mp4", "mov", "webm"], {"default": "auto"}),
                "filename_prefix": ("STRING", {"default": "MKR_lower_third"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MKR_VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = MEDIA_TIMELINE

    def run(
        self,
        video: Any,
        headline: str = "Headline",
        subline: str = "Subtitle line",
        start_sec: float = 0.5,
        duration_sec: float = 3.5,
        animate_sec: float = 0.35,
        inset_x: int = 56,
        inset_y: int = 56,
        bar_color: str = "#121212",
        accent_color: str = "#E7B13D",
        text_color: str = "#FFFFFF",
        font_size_headline: int = 44,
        font_size_subline: int = 28,
        fallback_fps: float = 24.0,
        output_format: str = "auto",
        filename_prefix: str = "MKR_lower_third",
        subfolder: str = "",
        overwrite: bool = False,
        filename_label: str = "",
    ):
        warnings: List[str] = []
        frames, fps, warn = _decode_video_to_pil(video=video, requested_fps=0.0, max_frames=0)
        warnings.extend(warn)
        source = _extract_input_file(video)
        fps = float(max(1.0, fps if fps > 0.0 else fallback_fps))
        if not frames:
            warnings.append("No frames available")
            return (_make_video_payload(path=source), "", _json_text({"warnings": warnings}))

        start = float(max(0.0, start_sec))
        end = float(start + max(0.1, duration_sec))
        anim = float(max(0.05, animate_sec))

        bc = _parse_color(bar_color, (18, 18, 18))
        ac = _parse_color(accent_color, (231, 177, 61))
        tc = _parse_color(text_color, (255, 255, 255))
        fh = _get_font(int(font_size_headline))
        fs = _get_font(int(font_size_subline))
        ix = int(max(0, inset_x))
        iy = int(max(0, inset_y))

        out_frames: List[Image.Image] = []
        for i, frame in enumerate(frames):
            t = float(i / fps)
            img = frame.convert("RGBA")
            if start <= t < end:
                local = t - start
                tail = end - t
                phase = 1.0
                if local < anim:
                    phase = local / max(1e-6, anim)
                elif tail < anim:
                    phase = tail / max(1e-6, anim)
                phase = float(max(0.0, min(1.0, phase)))
                ease = float(phase * phase * (3.0 - 2.0 * phase))

                w = int(img.width * 0.58)
                h = int(max(90, img.height * 0.18))
                y = int(max(0, img.height - h - iy))
                x_base = int(ix)
                x = int(round(-w + (w + x_base) * ease))

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay, mode="RGBA")
                draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=(bc[0], bc[1], bc[2], int(230 * ease)))
                draw.rectangle((x, y, x + 10, y + h), fill=(ac[0], ac[1], ac[2], int(255 * ease)))

                tx = x + 26
                ty = y + 16
                draw.text((tx, ty), str(headline), font=fh, fill=(tc[0], tc[1], tc[2], int(255 * ease)))
                draw.text((tx, ty + int(font_size_headline * 0.95)), str(subline), font=fs, fill=(tc[0], tc[1], tc[2], int(230 * ease)))
                img = Image.alpha_composite(img, overlay)
            out_frames.append(img.convert("RGB"))

        payload, out_path, save_summary = _save_video_result(
            frames=out_frames,
            fps=fps,
            source=source,
            output_format=output_format,
            filename_prefix=filename_prefix,
            filename_label=filename_label,
            subfolder=subfolder,
            overwrite=overwrite,
            warnings=warnings,
        )
        summary = {
            "output_path": out_path,
            "start_sec": float(start),
            "duration_sec": float(duration_sec),
            "animate_sec": float(anim),
            "warnings": warnings,
        }
        if save_summary:
            summary["output_path"] = ""
        return (payload, out_path, _json_text(summary))
