import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import torch

from ..categories import INSPECT_PREVIEW

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
THIS_DIR = str(PACKAGE_ROOT)
ALLOWED_FORMATS = {"png", "jpeg", "webp", "gif"}
ALLOWED_ANIMATION_MODES = {"auto", "single_animation", "per_frame"}
ALLOWED_ORIENTATIONS = {"vertical", "horizontal"}
ALLOWED_FIT_MODES = {"contain", "cover", "stretch"}


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, float(value))))


def _to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")

    t = image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(t.shape)}")
    if t.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(t.shape)}")

    return t.clamp(0.0, 1.0)


def _image_batch_to_pil(image: torch.Tensor) -> List[Image.Image]:
    batch = _to_image_batch(image)
    rgb = batch[..., :3].cpu().numpy().astype(np.float32, copy=False)
    rgb_u8 = np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    return [Image.fromarray(sample, mode="RGB") for sample in rgb_u8]


def _mask_to_batch(mask: Optional[torch.Tensor], batch: int, h: int, w: int) -> Optional[np.ndarray]:
    if mask is None:
        return None
    if not torch.is_tensor(mask):
        raise TypeError("mask input is not a torch tensor")

    m = mask.detach().float().cpu()
    if m.ndim == 2:
        m = m.unsqueeze(0)
    elif m.ndim == 4:
        if m.shape[-1] in (1, 3, 4):
            m = m[..., 0]
        elif m.shape[1] in (1, 3, 4):
            m = m[:, 0, ...]
        else:
            raise ValueError(f"Unsupported mask shape={tuple(m.shape)}")
    elif m.ndim != 3:
        raise ValueError(f"Unsupported mask dims={m.ndim}")

    if m.shape[0] <= 0:
        return None
    if m.shape[0] == 1 and batch > 1:
        m = m.expand(batch, -1, -1)
    elif m.shape[0] < batch:
        repeat_count = int(batch - m.shape[0])
        m = torch.cat([m, m[-1:].expand(repeat_count, -1, -1)], dim=0)
    elif m.shape[0] > batch:
        m = m[:batch]

    out = np.zeros((int(batch), int(h), int(w)), dtype=np.float32)
    for idx in range(int(batch)):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        pil = Image.fromarray((sample * 255.0).astype(np.uint8), mode="L")
        if pil.size != (int(w), int(h)):
            pil = pil.resize((int(w), int(h)), resample=Image.Resampling.BILINEAR)
        out[idx] = np.asarray(pil, dtype=np.float32) / 255.0

    return np.clip(out, 0.0, 1.0)


def _mask_preview_from_mask(mask_2d: np.ndarray) -> Image.Image:
    m = np.clip(mask_2d.astype(np.float32, copy=False), 0.0, 1.0)
    tint = np.stack([0.16 * m, 0.98 * m, 0.42 * m], axis=-1)
    rgb_u8 = np.clip(tint * 255.0, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(rgb_u8, mode="RGB")


def _temp_dir() -> Path:
    if folder_paths and hasattr(folder_paths, "get_temp_directory"):
        try:
            return Path(str(folder_paths.get_temp_directory()))
        except Exception:
            pass
    fallback = PACKAGE_ROOT / ".temp"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _default_output_root_from_node_path() -> Path:
    node_dir = PACKAGE_ROOT.resolve()
    # Expected layout: <ComfyUI>/custom_nodes/MKRShift_Nodes
    for parent in node_dir.parents:
        if parent.name == "custom_nodes":
            return (parent.parent / "output").resolve()
    # Fallback to two levels up from this node directory.
    return (node_dir.parent.parent / "output").resolve()


def _output_root_dir() -> Path:
    default_out = _default_output_root_from_node_path()
    if folder_paths and hasattr(folder_paths, "get_output_directory"):
        try:
            out_dir = Path(str(folder_paths.get_output_directory())).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            return out_dir
        except Exception:
            pass
    default_out.mkdir(parents=True, exist_ok=True)
    return default_out


def _safe_subfolder(subfolder: str) -> str:
    raw = str(subfolder or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return ""
    parts = [p for p in raw.split("/") if p.strip() and p.strip() not in {".", ".."}]
    safe_parts: List[str] = []
    for part in parts:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", part).strip("._-")
        if cleaned:
            safe_parts.append(cleaned)
    return "/".join(safe_parts)


def _output_dir(subfolder: str) -> Path:
    base = _output_root_dir().resolve()
    safe_sub = _safe_subfolder(subfolder)
    if not safe_sub:
        return base
    target = (base / safe_sub).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return base
    return target


def _sanitize_basename(text: str, fallback: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    if not value:
        value = fallback
    value = value[:128].strip("._-")
    if not value:
        value = fallback
    return value


def _collect_labels(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for entry in value:
            out.extend(_collect_labels(entry))
        return out
    if isinstance(value, dict):
        out: List[str] = []
        for entry in value.values():
            out.extend(_collect_labels(entry))
        return out

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _collect_labels(parsed)
        except Exception:
            pass

    labels: List[str] = []
    for line in text.splitlines():
        chunks = re.split(r"[,;]", line)
        for chunk in chunks:
            item = str(chunk).strip()
            if item:
                labels.append(item)
    if not labels and text:
        labels = [text]
    return labels


def _build_frame_basenames(frame_count: int, prefix: str, labels: List[str]) -> List[str]:
    safe_prefix = _sanitize_basename(str(prefix or "MKR"), "MKR")
    raw_bases: List[str] = []
    for idx in range(int(frame_count)):
        if idx < len(labels) and str(labels[idx]).strip():
            raw = str(labels[idx]).strip()
        else:
            raw = f"{safe_prefix}_{idx:05d}"
        raw_bases.append(_sanitize_basename(raw, f"{safe_prefix}_{idx:05d}"))

    deduped: List[str] = []
    seen: Dict[str, int] = {}
    for base in raw_bases:
        count = int(seen.get(base, 0)) + 1
        seen[base] = count
        deduped.append(base if count == 1 else f"{base}_{count}")
    return deduped


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _png_metadata(prompt: Any = None, extra_pnginfo: Any = None) -> Optional[PngInfo]:
    if prompt is None and extra_pnginfo is None:
        return None
    info = PngInfo()
    if prompt is not None:
        info.add_text("prompt", _json_text(prompt))
    if isinstance(extra_pnginfo, dict):
        for key, value in extra_pnginfo.items():
            info.add_text(str(key), _json_text(value))
    elif extra_pnginfo is not None:
        info.add_text("extra_pnginfo", _json_text(extra_pnginfo))
    return info


def _resolve_save_mode(output_format: str, animation_mode: str, frame_count: int, warnings: List[str]) -> str:
    fmt = str(output_format or "png").strip().lower()
    mode = str(animation_mode or "auto").strip().lower()
    if mode not in ALLOWED_ANIMATION_MODES:
        mode = "auto"

    if mode == "auto":
        if fmt in {"gif", "webp"} and int(frame_count) > 1:
            return "single_animation"
        return "per_frame"

    if mode == "single_animation" and fmt not in {"gif", "webp"}:
        warnings.append(
            f"animation_mode='single_animation' is not supported for format '{fmt}', falling back to per_frame."
        )
        return "per_frame"
    return mode


def _resolve_output_file(out_dir: Path, stem: str, ext: str, overwrite: bool) -> Path:
    target = out_dir / f"{stem}.{ext}"
    if bool(overwrite):
        return target

    candidate = target
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_{counter}.{ext}"
        counter += 1
    return candidate


def _save_preview_temp(image: Image.Image, prefix: str) -> Optional[Dict[str, str]]:
    try:
        temp_dir = _temp_dir()
        temp_dir.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}_{uuid.uuid4().hex[:10]}.png"
        target = temp_dir / name
        image.convert("RGB").save(target, format="PNG", compress_level=1)
        return {"filename": name, "subfolder": "", "type": "temp"}
    except Exception:
        return None


def _save_still_image(
    image: Image.Image,
    path: Path,
    output_format: str,
    png_compress_level: int,
    jpeg_quality: int,
    webp_quality: int,
    pnginfo: Optional[PngInfo],
):
    fmt = str(output_format).lower()
    rgb = image.convert("RGB")
    if fmt == "png":
        rgb.save(
            path,
            format="PNG",
            compress_level=int(max(0, min(9, int(png_compress_level)))),
            pnginfo=pnginfo,
        )
        return
    if fmt == "jpeg":
        rgb.save(
            path,
            format="JPEG",
            quality=int(max(1, min(100, int(jpeg_quality)))),
            optimize=True,
        )
        return
    if fmt == "webp":
        rgb.save(
            path,
            format="WEBP",
            quality=int(max(1, min(100, int(webp_quality)))),
            method=6,
        )
        return
    if fmt == "gif":
        rgb.save(path, format="GIF")
        return
    raise ValueError(f"Unsupported format '{fmt}'")


def _save_animation(
    frames: List[Image.Image],
    path: Path,
    output_format: str,
    webp_quality: int,
    animation_fps: int,
    animation_loop: int,
):
    if not frames:
        raise ValueError("No frames to save")

    fps = max(1, int(animation_fps))
    duration_ms = max(1, int(round(1000.0 / float(fps))))
    loop = int(max(0, min(1000, int(animation_loop))))
    sequence = [f.convert("RGB") for f in frames]
    first, rest = sequence[0], sequence[1:]

    fmt = str(output_format).lower()
    if fmt == "gif":
        first.save(
            path,
            format="GIF",
            save_all=True,
            append_images=rest,
            duration=duration_ms,
            loop=loop,
            optimize=False,
        )
        return
    if fmt == "webp":
        first.save(
            path,
            format="WEBP",
            save_all=True,
            append_images=rest,
            duration=duration_ms,
            loop=loop,
            quality=int(max(1, min(100, int(webp_quality)))),
            method=6,
        )
        return
    raise ValueError(f"Animation output is not supported for format '{fmt}'")


class MKRPreSave:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "preview_only": ("BOOLEAN", {"default": True}),
                "output_format": (["png", "jpeg", "webp", "gif"], {"default": "png"}),
                "animation_mode": (
                    ["auto", "single_animation", "per_frame"],
                    {"default": "auto"},
                ),
                "filename_prefix": ("STRING", {"default": "MKR"}),
                "subfolder": ("STRING", {"default": ""}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_mask": ("BOOLEAN", {"default": False}),
                "orientation": (["horizontal", "vertical"], {"default": "horizontal"}),
                "split_percent": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.001}),
                "fit_mode": (["contain", "cover", "stretch"], {"default": "contain"}),
                "png_compress_level": ("INT", {"default": 4, "min": 0, "max": 9, "step": 1}),
                "jpeg_quality": ("INT", {"default": 92, "min": 1, "max": 100, "step": 1}),
                "webp_quality": ("INT", {"default": 90, "min": 1, "max": 100, "step": 1}),
                "animation_fps": ("INT", {"default": 12, "min": 1, "max": 60, "step": 1}),
                "animation_loop": ("INT", {"default": 0, "min": 0, "max": 1000, "step": 1}),
            },
            "optional": {
                "mask": ("MASK",),
                "filename_labels": ("STRING", {"default": "", "multiline": False}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = INSPECT_PREVIEW

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Save/preview output nodes should execute every queue event.
        return float("nan")

    def run(
        self,
        image: torch.Tensor,
        preview_only: bool = True,
        output_format: str = "png",
        animation_mode: str = "auto",
        filename_prefix: str = "MKR",
        subfolder: str = "",
        overwrite: bool = False,
        save_mask: bool = False,
        orientation: str = "horizontal",
        split_percent: float = 0.5,
        fit_mode: str = "contain",
        png_compress_level: int = 4,
        jpeg_quality: int = 92,
        webp_quality: int = 90,
        animation_fps: int = 12,
        animation_loop: int = 0,
        mask: Optional[torch.Tensor] = None,
        filename_labels: Any = None,
        prompt: Any = None,
        extra_pnginfo: Any = None,
    ):
        pil_frames = _image_batch_to_pil(image)
        frame_count = len(pil_frames)
        if frame_count <= 0:
            pil_frames = [Image.new("RGB", (64, 64), (0, 0, 0))]
            frame_count = 1

        first_w, first_h = pil_frames[0].size
        mask_batch = _mask_to_batch(mask=mask, batch=frame_count, h=first_h, w=first_w)
        has_mask = mask_batch is not None

        fmt = str(output_format or "png").strip().lower()
        warnings: List[str] = []
        if fmt not in ALLOWED_FORMATS:
            warnings.append(f"Unsupported output_format='{fmt}', using 'png'.")
            fmt = "png"

        orientation_norm = str(orientation or "horizontal").strip().lower()
        if orientation_norm not in ALLOWED_ORIENTATIONS:
            orientation_norm = "horizontal"

        fit_mode_norm = str(fit_mode or "contain").strip().lower()
        if fit_mode_norm not in ALLOWED_FIT_MODES:
            fit_mode_norm = "contain"

        mode = _resolve_save_mode(
            output_format=fmt,
            animation_mode=str(animation_mode or "auto"),
            frame_count=frame_count,
            warnings=warnings,
        )

        labels = _collect_labels(filename_labels)
        basenames = _build_frame_basenames(
            frame_count=frame_count,
            prefix=str(filename_prefix or "MKR"),
            labels=labels,
        )

        ui_images: List[Dict[str, str]] = []
        ui_masks: List[Dict[str, str]] = []
        for idx, frame in enumerate(pil_frames):
            entry = _save_preview_temp(frame, prefix=f"mkrshift_presave_img_{idx:03d}")
            if entry is not None:
                ui_images.append(entry)
            if has_mask and mask_batch is not None:
                mask_preview = _mask_preview_from_mask(mask_batch[idx])
                mask_entry = _save_preview_temp(mask_preview, prefix=f"mkrshift_presave_mask_{idx:03d}")
                if mask_entry is not None:
                    ui_masks.append(mask_entry)

        saved_paths: List[str] = []
        saved_mask_paths: List[str] = []
        save_enabled = not bool(preview_only)
        pnginfo = _png_metadata(prompt=prompt, extra_pnginfo=extra_pnginfo) if fmt == "png" else None

        if save_enabled:
            out_dir = _output_dir(subfolder=subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                if mode == "single_animation" and fmt in {"gif", "webp"}:
                    animation_stem_raw = basenames[0] if basenames else str(filename_prefix or "MKR")
                    animation_stem = _sanitize_basename(animation_stem_raw, "MKR")
                    target = _resolve_output_file(
                        out_dir=out_dir,
                        stem=animation_stem,
                        ext=fmt,
                        overwrite=bool(overwrite),
                    )
                    if frame_count <= 1:
                        _save_still_image(
                            image=pil_frames[0],
                            path=target,
                            output_format=fmt,
                            png_compress_level=int(png_compress_level),
                            jpeg_quality=int(jpeg_quality),
                            webp_quality=int(webp_quality),
                            pnginfo=pnginfo,
                        )
                    else:
                        _save_animation(
                            frames=pil_frames,
                            path=target,
                            output_format=fmt,
                            webp_quality=int(webp_quality),
                            animation_fps=int(animation_fps),
                            animation_loop=int(animation_loop),
                        )
                    saved_paths.append(str(target))
                else:
                    for idx, frame in enumerate(pil_frames):
                        stem = basenames[idx]
                        target = _resolve_output_file(
                            out_dir=out_dir,
                            stem=stem,
                            ext=fmt,
                            overwrite=bool(overwrite),
                        )
                        _save_still_image(
                            image=frame,
                            path=target,
                            output_format=fmt,
                            png_compress_level=int(png_compress_level),
                            jpeg_quality=int(jpeg_quality),
                            webp_quality=int(webp_quality),
                            pnginfo=pnginfo,
                        )
                        saved_paths.append(str(target))
            except Exception as exc:
                warnings.append(f"Failed to save image output: {exc}")

            if bool(save_mask) and has_mask and mask_batch is not None:
                try:
                    for idx in range(frame_count):
                        stem = _sanitize_basename(f"{basenames[idx]}_mask", f"MKR_{idx:05d}_mask")
                        target = _resolve_output_file(
                            out_dir=out_dir,
                            stem=stem,
                            ext="png",
                            overwrite=bool(overwrite),
                        )
                        mask_img = Image.fromarray(
                            np.clip(mask_batch[idx] * 255.0, 0.0, 255.0).astype(np.uint8),
                            mode="L",
                        )
                        mask_img.save(
                            target,
                            format="PNG",
                            compress_level=int(max(0, min(9, int(png_compress_level)))),
                        )
                        saved_mask_paths.append(str(target))
                except Exception as exc:
                    warnings.append(f"Failed to save mask output: {exc}")

        ui_payload: Dict[str, Any] = {
            # Use custom UI keys so Comfy's generic image preview widget is not injected.
            "presave_images": ui_images,
            "presave_state": [
                {
                    "preview_only": bool(preview_only),
                    "has_mask": bool(has_mask),
                    "frame_count": int(frame_count),
                    "saved_count": int(len(saved_paths)),
                    "orientation": orientation_norm,
                    "split_percent": _clamp01(float(split_percent)),
                    "fit_mode": fit_mode_norm,
                    "format": fmt,
                    "animation_mode": mode,
                }
            ],
            "save_summary": [
                {
                    "saved_paths": saved_paths,
                    "saved_mask_paths": saved_mask_paths,
                    "warnings": warnings,
                }
            ],
        }
        if has_mask:
            ui_payload["presave_mask_images"] = ui_masks

        return {
            "ui": ui_payload,
            "result": (),
        }
