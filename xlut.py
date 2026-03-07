import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import numpy as np
from PIL import Image
import torch

from .categories import COLOR_LUT
from .xshared import to_image_batch as _to_image_batch

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

try:
    from aiohttp import web  # type: ignore
except Exception:
    web = None

try:
    from fastapi import HTTPException  # type: ignore
    from fastapi.responses import FileResponse as FastFileResponse  # type: ignore
    from fastapi.responses import JSONResponse as FastJSONResponse  # type: ignore
except Exception:
    HTTPException = None
    FastFileResponse = None
    FastJSONResponse = None

try:
    from server import PromptServer  # type: ignore
except Exception:
    PromptServer = None

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
LUT_EXTENSIONS = {".cube"}
NO_LUT_SELECTED = "None"
LUT_DATA_TYPE = "MKR_LUT"
LUT_PREVIEW_SCHEMA_VERSION = 4


@dataclass(frozen=True)
class LutCube:
    path: str
    title: str
    size: int
    domain_min: Tuple[float, float, float]
    domain_max: Tuple[float, float, float]
    table: np.ndarray


def _candidate_lut_dirs() -> List[str]:
    dirs: List[str] = [os.path.join(THIS_DIR, "luts")]
    if folder_paths and hasattr(folder_paths, "get_input_directory"):
        try:
            dirs.append(os.path.join(str(folder_paths.get_input_directory()), "luts"))
        except Exception:
            pass
    if folder_paths and hasattr(folder_paths, "get_folder_paths"):
        try:
            for item in folder_paths.get_folder_paths("luts"):
                if item:
                    dirs.append(str(item))
        except Exception:
            pass

    unique_dirs: List[str] = []
    seen = set()
    for path in dirs:
        normalized = os.path.abspath(os.path.expanduser(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_dirs.append(normalized)
    return unique_dirs


def _discover_luts() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for base_dir in _candidate_lut_dirs():
        if not os.path.isdir(base_dir):
            continue
        root_label = os.path.basename(base_dir) or "luts"
        for root, _, files in os.walk(base_dir):
            for file_name in files:
                ext = os.path.splitext(file_name)[1].lower()
                if ext not in LUT_EXTENSIONS:
                    continue
                abs_path = os.path.abspath(os.path.join(root, file_name))
                rel_path = os.path.relpath(abs_path, base_dir).replace(os.sep, "/")
                label = rel_path
                if label in out and out[label] != abs_path:
                    label = f"{root_label}/{rel_path}"
                suffix = 2
                while label in out and out[label] != abs_path:
                    label = f"{root_label}/{rel_path} ({suffix})"
                    suffix += 1
                out[label] = abs_path
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


def _lut_options() -> List[str]:
    discovered = _discover_luts()
    return [NO_LUT_SELECTED] + list(discovered.keys())


def _resolve_lut_path(lut_name: str) -> Tuple[Optional[str], str]:
    if lut_name == NO_LUT_SELECTED:
        return None, "xLUT: No LUT selected. Output is passthrough."
    resolved = _discover_luts().get(lut_name)
    if not resolved:
        return None, f"xLUT: LUT '{lut_name}' was not found."
    return resolved, ""


def _sanitize_lut_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        text = "mkrshift_image_lut"
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    if not text:
        text = "mkrshift_image_lut"
    return text[:96]


def _mean_saturation(rgb: np.ndarray) -> float:
    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    delta = maxc - minc
    sat = np.where(maxc > 1e-6, delta / np.maximum(maxc, 1e-6), 0.0)
    return float(np.clip(np.mean(sat), 0.0, 1.0))


def _generate_lut_table_from_image(reference_image: torch.Tensor, size: int, style_strength: float) -> np.ndarray:
    batch = _to_image_batch(reference_image)
    ref = batch[0, ..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
    h, w = ref.shape[:2]
    flat = ref.reshape(-1, 3)

    if flat.shape[0] > 300_000:
        stride = max(1, int(flat.shape[0] // 300_000))
        flat = flat[::stride]

    quantile_steps = np.linspace(0.0, 1.0, 257, dtype=np.float32)
    curve_r = np.quantile(flat[:, 0], quantile_steps).astype(np.float32, copy=False)
    curve_g = np.quantile(flat[:, 1], quantile_steps).astype(np.float32, copy=False)
    curve_b = np.quantile(flat[:, 2], quantile_steps).astype(np.float32, copy=False)

    levels = np.linspace(0.0, 1.0, int(size), dtype=np.float32)
    rr, gg, bb = np.meshgrid(levels, levels, levels, indexing="ij")
    out = np.empty((int(size), int(size), int(size), 3), dtype=np.float32)
    out[..., 0] = np.interp(rr, quantile_steps, curve_r).astype(np.float32, copy=False)
    out[..., 1] = np.interp(gg, quantile_steps, curve_g).astype(np.float32, copy=False)
    out[..., 2] = np.interp(bb, quantile_steps, curve_b).astype(np.float32, copy=False)

    strength = float(np.clip(style_strength, 0.0, 2.0))
    if strength > 1e-6:
        mean_rgb = np.mean(flat, axis=0).astype(np.float32, copy=False)
        sat_ref = _mean_saturation(ref)
        sat_gain = float(np.clip(1.0 + ((sat_ref - 0.35) * 1.2 * strength), 0.35, 1.9))
        luma = (
            0.2126 * out[..., 0]
            + 0.7152 * out[..., 1]
            + 0.0722 * out[..., 2]
        )[..., None].astype(np.float32, copy=False)
        out = luma + ((out - luma) * sat_gain)

        tint = (mean_rgb - float(np.mean(mean_rgb))) * (0.32 * strength)
        mid_weight = np.clip(1.0 - (np.abs(luma - 0.5) * 2.0), 0.0, 1.0)
        out = out + (tint[None, None, None, :] * mid_weight)

    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def _write_cube(path: str, title: str, table: np.ndarray) -> None:
    size = int(table.shape[0])
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        flat = table.reshape(-1, 3)
        for row in flat:
            f.write(f"{float(row[0]):.8f} {float(row[1]):.8f} {float(row[2]):.8f}\n")


def _build_lut_from_image(
    reference_image: torch.Tensor,
    lut_size: int,
    lut_name_hint: str,
    style_strength: float,
) -> LutCube:
    size = int(np.clip(int(lut_size), 4, 64))
    table = _generate_lut_table_from_image(
        reference_image=reference_image,
        size=size,
        style_strength=float(style_strength),
    )

    safe_name = _sanitize_lut_name(lut_name_hint)
    return LutCube(
        path="",
        title=safe_name,
        size=size,
        domain_min=(0.0, 0.0, 0.0),
        domain_max=(1.0, 1.0, 1.0),
        table=table,
    )


def _lut_payload_from_cube(lut: LutCube) -> Dict[str, object]:
    return {
        "path": str(lut.path),
        "title": str(lut.title),
        "size": int(lut.size),
        "domain_min": (float(lut.domain_min[0]), float(lut.domain_min[1]), float(lut.domain_min[2])),
        "domain_max": (float(lut.domain_max[0]), float(lut.domain_max[1]), float(lut.domain_max[2])),
        "table": np.asarray(lut.table, dtype=np.float32),
    }


def _cube_from_lut_payload(payload: object) -> LutCube:
    if isinstance(payload, LutCube):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("LUT payload is not a dict")

    path = str(payload.get("path", "")).strip()
    title = str(payload.get("title", "")).strip()
    table = payload.get("table", None)
    size_raw = payload.get("size", None)
    dmin_raw = payload.get("domain_min", (0.0, 0.0, 0.0))
    dmax_raw = payload.get("domain_max", (1.0, 1.0, 1.0))

    if table is not None:
        arr = np.asarray(table, dtype=np.float32)
        if arr.ndim != 4 or arr.shape[-1] != 3:
            raise ValueError("LUT payload table must have shape [N,N,N,3]")
        size = int(arr.shape[0])
        if arr.shape[1] != size or arr.shape[2] != size:
            raise ValueError("LUT payload table must be cubic [N,N,N,3]")
        if not title:
            title = os.path.splitext(os.path.basename(path))[0] if path else "mkrshift_lut"
        try:
            dmin = tuple(float(x) for x in dmin_raw)[:3]
            dmax = tuple(float(x) for x in dmax_raw)[:3]
        except Exception:
            dmin = (0.0, 0.0, 0.0)
            dmax = (1.0, 1.0, 1.0)
        if len(dmin) != 3:
            dmin = (0.0, 0.0, 0.0)
        if len(dmax) != 3:
            dmax = (1.0, 1.0, 1.0)
        return LutCube(
            path=path,
            title=title,
            size=size,
            domain_min=(float(dmin[0]), float(dmin[1]), float(dmin[2])),
            domain_max=(float(dmax[0]), float(dmax[1]), float(dmax[2])),
            table=arr,
        )

    if path:
        return _load_cube(path)

    if size_raw is not None:
        size = int(size_raw)
        levels = np.linspace(0.0, 1.0, max(2, size), dtype=np.float32)
        rr, gg, bb = np.meshgrid(levels, levels, levels, indexing="ij")
        ident = np.stack([rr, gg, bb], axis=-1).astype(np.float32, copy=False)
        return LutCube(
            path="",
            title=title or "identity",
            size=max(2, size),
            domain_min=(0.0, 0.0, 0.0),
            domain_max=(1.0, 1.0, 1.0),
            table=ident,
        )

    raise ValueError("LUT payload is missing table/path")


def _safe_subfolder(subfolder: str) -> str:
    raw = str(subfolder or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return "generated"
    parts = [p for p in raw.split("/") if p.strip()]
    safe_parts: List[str] = []
    for p in parts:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", p).strip("._-")
        if cleaned:
            safe_parts.append(cleaned)
    return "/".join(safe_parts) if safe_parts else "generated"


def _save_lut_cube(cube: LutCube, save_name: str, subfolder: str, overwrite: bool) -> str:
    base_candidates = _candidate_lut_dirs()
    base_dir = base_candidates[0] if base_candidates else os.path.join(THIS_DIR, "luts")
    safe_sub = _safe_subfolder(subfolder)
    out_dir = os.path.abspath(os.path.join(base_dir, safe_sub))
    os.makedirs(out_dir, exist_ok=True)

    stem = _sanitize_lut_name(save_name or cube.title or "mkrshift_lut")
    path = os.path.join(out_dir, f"{stem}.cube")
    if not bool(overwrite):
        candidate = path
        counter = 2
        while os.path.exists(candidate):
            candidate = os.path.join(out_dir, f"{stem}_{counter}.cube")
            counter += 1
        path = candidate

    _write_cube(path=path, title=stem, table=np.asarray(cube.table, dtype=np.float32))
    return os.path.abspath(path)


def _preview_path_for_lut(cube_path: str) -> str:
    stem, _ = os.path.splitext(os.path.abspath(cube_path))
    return f"{stem}.preview.v{int(LUT_PREVIEW_SCHEMA_VERSION)}.png"


def _build_lut_preview_rgb(width: int, height: int) -> np.ndarray:
    w = max(64, int(width))
    h = max(48, int(height))
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)

    rgb = np.empty((h, w, 3), dtype=np.float32)
    rgb[..., 0] = xx
    rgb[..., 1] = np.clip((1.0 - yy) * 0.72 + (xx * 0.28), 0.0, 1.0)
    rgb[..., 2] = np.clip(yy * 0.86 + ((1.0 - xx) * 0.14), 0.0, 1.0)

    band_h = max(10, int(round(h * 0.17)))
    row0 = max(0, h - band_h)
    if row0 < h:
        band_y = np.linspace(0.0, 1.0, h - row0, dtype=np.float32)[:, None]
        skin = np.asarray([0.88, 0.72, 0.58], dtype=np.float32)[None, None, :]
        cyan = np.asarray([0.16, 0.72, 0.82], dtype=np.float32)[None, None, :]
        magenta = np.asarray([0.78, 0.36, 0.74], dtype=np.float32)[None, None, :]
        warm = np.asarray([0.92, 0.74, 0.18], dtype=np.float32)[None, None, :]
        quarter = w // 4
        if quarter > 0:
            rgb[row0:, 0:quarter, :] = np.clip(skin * (0.78 + 0.22 * band_y[..., None]), 0.0, 1.0)
            rgb[row0:, quarter : quarter * 2, :] = np.clip(cyan * (0.75 + 0.25 * band_y[..., None]), 0.0, 1.0)
            rgb[row0:, quarter * 2 : quarter * 3, :] = np.clip(magenta * (0.74 + 0.26 * band_y[..., None]), 0.0, 1.0)
            rgb[row0:, quarter * 3 :, :] = np.clip(warm * (0.72 + 0.28 * band_y[..., None]), 0.0, 1.0)

    return np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)


def _preview_source_from_image(reference_image: torch.Tensor, width: int, height: int) -> np.ndarray:
    batch = _to_image_batch(reference_image)
    src = batch[0, ..., :3].detach().cpu().numpy().astype(np.float32, copy=False)
    sh, sw = src.shape[:2]
    target_w = max(64, int(width))
    target_h = max(48, int(height))
    if sh <= 0 or sw <= 0:
        return _build_lut_preview_rgb(target_w, target_h)

    # Cover-fit and center crop to preserve aspect while filling preview frame.
    scale = max(target_w / float(sw), target_h / float(sh))
    rw = max(1, int(round(sw * scale)))
    rh = max(1, int(round(sh * scale)))
    pil = Image.fromarray(np.clip(src * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    pil = pil.resize((rw, rh), resample=Image.Resampling.LANCZOS)
    arr = np.asarray(pil, dtype=np.float32) / 255.0
    x0 = max(0, (rw - target_w) // 2)
    y0 = max(0, (rh - target_h) // 2)
    arr = arr[y0 : y0 + target_h, x0 : x0 + target_w, :3]
    if arr.shape[0] != target_h or arr.shape[1] != target_w:
        # Final safeguard if rounding produced edge mismatch.
        pil2 = Image.fromarray(np.clip(arr * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
        pil2 = pil2.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)
        arr = np.asarray(pil2, dtype=np.float32) / 255.0
    return np.clip(arr, 0.0, 1.0).astype(np.float32, copy=False)


def _save_lut_preview_image(
    cube: LutCube,
    cube_path: str,
    preview_size: int = 448,
    reference_image: Optional[torch.Tensor] = None,
) -> str:
    w = int(np.clip(int(preview_size), 128, 2048))
    h = max(72, int(round(w * 0.56)))
    if reference_image is not None:
        src = _preview_source_from_image(reference_image, w, h)
    else:
        src = _build_lut_preview_rgb(w, h)
    # Show LUT color-table style on the left side; reference/fallback source on the right.
    lut_chart_src = _build_lut_preview_rgb(w, h)
    lut_data = _trilinear_lookup(lut_chart_src, cube)

    split = max(8, min(w - 8, int(round(w * 0.5))))
    combo = np.concatenate([lut_data[:, :split, :], src[:, split:, :]], axis=1)
    combo[:, max(0, split - 1):min(w, split + 1), :] = 1.0
    preview_u8 = np.clip(combo * 255.0, 0.0, 255.0).astype(np.uint8)

    path = _preview_path_for_lut(cube_path)
    Image.fromarray(preview_u8, mode="RGB").save(path, format="PNG", compress_level=2)
    return os.path.abspath(path)


def _folder_from_label(label: str) -> str:
    folder = os.path.dirname(str(label).replace("\\", "/")).strip()
    return "" if folder in {".", "/"} else folder


def _maybe_generate_preview_for_lut_path(path: str, preview_size: int = 448) -> Optional[str]:
    try:
        preview_path = _preview_path_for_lut(path)
        if os.path.isfile(preview_path):
            return preview_path
        cube = _load_cube(path)
        return _save_lut_preview_image(cube, path, preview_size=preview_size)
    except Exception:
        return None


def _lut_catalog_payload(folder_filter: str = "") -> Dict[str, object]:
    catalog = _discover_luts()
    folders = sorted({_folder_from_label(label) for label in catalog.keys()})
    selected = str(folder_filter or "").strip().strip("/")
    if selected and selected not in folders:
        selected = ""

    entries: List[Dict[str, object]] = []
    for label, path in catalog.items():
        folder = _folder_from_label(label)
        if selected and folder != selected:
            continue
        safe_label = str(label)
        rel = safe_label.replace("\\", "/")
        preview_path = _preview_path_for_lut(path)
        preview_exists = os.path.isfile(preview_path)
        entry = {
            "label": safe_label,
            "name": os.path.basename(path),
            "folder": folder,
            "relative": rel,
            "has_preview": bool(preview_exists),
            "preview_url": f"/mkrshift_lut/preview?label={quote(safe_label, safe='')}",
        }
        entries.append(entry)

    return {
        "schema": "mkrshift_lut_catalog_v1",
        "selected_folder": selected,
        "folders": folders,
        "entries": entries,
        "count": len(entries),
        "total": len(catalog),
    }


def _parse_triplet(parts: List[str], line_no: int, label: str) -> Tuple[float, float, float]:
    if len(parts) != 4:
        raise ValueError(f"{label} expects 3 values (line {line_no})")
    try:
        return float(parts[1]), float(parts[2]), float(parts[3])
    except ValueError as exc:
        raise ValueError(f"Invalid {label} values on line {line_no}") from exc


def _parse_cube_lut(path: str) -> LutCube:
    lut_size: Optional[int] = None
    lut_title = ""
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    rows: List[Tuple[float, float, float]] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        for line_no, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "#" in line:
                line = line.split("#", 1)[0].strip()
            if not line:
                continue

            parts = line.split()
            head = parts[0].upper()

            if head == "TITLE":
                title_value = line[len(parts[0]) :].strip()
                lut_title = title_value.strip().strip('"')
                continue
            if head == "LUT_1D_SIZE":
                raise ValueError("1D LUT files are not supported by xLUT")
            if head == "LUT_3D_SIZE":
                if len(parts) != 2:
                    raise ValueError(f"LUT_3D_SIZE expects one integer (line {line_no})")
                try:
                    lut_size = int(parts[1])
                except ValueError as exc:
                    raise ValueError(f"Invalid LUT_3D_SIZE on line {line_no}") from exc
                if lut_size < 2:
                    raise ValueError("LUT_3D_SIZE must be at least 2")
                continue
            if head == "DOMAIN_MIN":
                domain_min = _parse_triplet(parts, line_no, "DOMAIN_MIN")
                continue
            if head == "DOMAIN_MAX":
                domain_max = _parse_triplet(parts, line_no, "DOMAIN_MAX")
                continue
            if any(ch.isalpha() for ch in parts[0]):
                continue

            if len(parts) != 3:
                raise ValueError(f"Expected RGB row with 3 values (line {line_no})")
            try:
                rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError as exc:
                raise ValueError(f"Invalid RGB row on line {line_no}") from exc

    if lut_size is None:
        raise ValueError("LUT_3D_SIZE is missing")

    expected_rows = lut_size * lut_size * lut_size
    if len(rows) != expected_rows:
        raise ValueError(f"Expected {expected_rows} LUT rows, found {len(rows)}")

    table = np.asarray(rows, dtype=np.float32).reshape((lut_size, lut_size, lut_size, 3))
    title = lut_title or os.path.splitext(os.path.basename(path))[0]
    return LutCube(
        path=os.path.abspath(path),
        title=title,
        size=lut_size,
        domain_min=(float(domain_min[0]), float(domain_min[1]), float(domain_min[2])),
        domain_max=(float(domain_max[0]), float(domain_max[1]), float(domain_max[2])),
        table=table,
    )


@lru_cache(maxsize=64)
def _load_cube_cached(path: str, mtime_ns: int) -> LutCube:
    del mtime_ns
    return _parse_cube_lut(path)


def _load_cube(path: str) -> LutCube:
    stat = os.stat(path)
    return _load_cube_cached(os.path.abspath(path), int(stat.st_mtime_ns))


def _trilinear_lookup(rgb: np.ndarray, lut: LutCube) -> np.ndarray:
    if lut.size == 1:
        base = lut.table[0, 0, 0]
        return np.broadcast_to(base, rgb.shape).astype(np.float32, copy=False)

    dmin = np.asarray(lut.domain_min, dtype=np.float32)
    dmax = np.asarray(lut.domain_max, dtype=np.float32)
    span = np.maximum(dmax - dmin, 1e-6)

    normalized = np.clip((rgb - dmin) / span, 0.0, 1.0)
    scaled = normalized * float(lut.size - 1)

    idx0 = np.floor(scaled).astype(np.int32)
    idx1 = np.clip(idx0 + 1, 0, lut.size - 1)
    frac = scaled - idx0

    r0, g0, b0 = idx0[..., 0], idx0[..., 1], idx0[..., 2]
    r1, g1, b1 = idx1[..., 0], idx1[..., 1], idx1[..., 2]

    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    c000 = lut.table[r0, g0, b0]
    c001 = lut.table[r0, g0, b1]
    c010 = lut.table[r0, g1, b0]
    c011 = lut.table[r0, g1, b1]
    c100 = lut.table[r1, g0, b0]
    c101 = lut.table[r1, g0, b1]
    c110 = lut.table[r1, g1, b0]
    c111 = lut.table[r1, g1, b1]

    out = (
        c000 * (1.0 - fr) * (1.0 - fg) * (1.0 - fb)
        + c001 * (1.0 - fr) * (1.0 - fg) * fb
        + c010 * (1.0 - fr) * fg * (1.0 - fb)
        + c011 * (1.0 - fr) * fg * fb
        + c100 * fr * (1.0 - fg) * (1.0 - fb)
        + c101 * fr * (1.0 - fg) * fb
        + c110 * fr * fg * (1.0 - fb)
        + c111 * fr * fg * fb
    )
    return out.astype(np.float32, copy=False)


def _apply_lut_to_image_tensor(image: torch.Tensor, lut: LutCube, strength: float) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")

    input_tensor = image.detach()
    had_batch_dim = input_tensor.ndim == 4
    if input_tensor.ndim == 3:
        input_tensor = input_tensor.unsqueeze(0)
    if input_tensor.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(input_tensor.shape)}")
    if input_tensor.shape[-1] not in {3, 4}:
        raise ValueError(f"Expected IMAGE channels 3 or 4, got shape={tuple(input_tensor.shape)}")

    work = input_tensor.float().clamp(0.0, 1.0)
    rgb = work[..., :3]
    alpha = work[..., 3:4] if work.shape[-1] == 4 else None

    rgb_np = rgb.cpu().numpy().astype(np.float32, copy=False)
    mapped_np = _trilinear_lookup(rgb_np, lut)

    blend = max(0.0, min(1.0, float(strength)))
    if blend < 1.0:
        mapped_np = (rgb_np * (1.0 - blend)) + (mapped_np * blend)

    mapped_np = np.clip(mapped_np, 0.0, 1.0).astype(np.float32, copy=False)
    mapped = torch.from_numpy(mapped_np).to(device=input_tensor.device, dtype=work.dtype)

    if alpha is not None:
        mapped = torch.cat([mapped, alpha.to(device=input_tensor.device, dtype=work.dtype)], dim=-1)

    if not had_batch_dim:
        mapped = mapped.squeeze(0)
    return mapped


class xLUT:
    @classmethod
    def INPUT_TYPES(cls):
        lut_choices = _lut_options()
        return {
            "required": {
                "image": ("IMAGE",),
                "lut_name": (lut_choices, {"default": NO_LUT_SELECTED}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "generated_lut_size": ("INT", {"default": 33, "min": 4, "max": 64, "step": 1}),
                "generated_style_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "apply_generated_lut": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "lut_image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", LUT_DATA_TYPE)
    RETURN_NAMES = ("image", "lut_info", "lut")
    FUNCTION = "run"
    CATEGORY = COLOR_LUT

    def run(
        self,
        image: torch.Tensor,
        lut_name: str = NO_LUT_SELECTED,
        strength: float = 1.0,
        generated_lut_size: int = 33,
        generated_style_strength: float = 1.0,
        apply_generated_lut: bool = True,
        lut_image: Optional[torch.Tensor] = None,
    ):
        generated_info = ""
        lut: Optional[LutCube] = None
        lut_payload: Optional[Dict[str, object]] = None

        if lut_name != NO_LUT_SELECTED:
            resolved, resolve_info = _resolve_lut_path(lut_name=lut_name)
            if not resolved:
                return (image, resolve_info or "xLUT: No LUT selected. Output is passthrough.", None)
            try:
                lut = _load_cube(resolved)
            except Exception as exc:
                return (image, f"xLUT: Failed to load LUT '{resolved}': {exc}", None)
        elif lut_image is not None:
            try:
                lut = _build_lut_from_image(
                    reference_image=lut_image,
                    lut_size=int(generated_lut_size),
                    lut_name_hint="in_memory_lut",
                    style_strength=float(generated_style_strength),
                )
            except Exception as exc:
                return (image, f"xLUT: Failed to generate LUT from lut_image: {exc}", None)
            generated_info = f"xLUT: Generated image LUT '{lut.title}' (size={lut.size}) in memory."
            lut_payload = _lut_payload_from_cube(lut)
            if not bool(apply_generated_lut):
                return (image, f"{generated_info} apply_generated_lut=False, output is passthrough.", lut_payload)
        else:
            return (image, "xLUT: No LUT selected and no lut_image connected. Output is passthrough.", None)

        try:
            out = _apply_lut_to_image_tensor(image, lut=lut, strength=strength)
        except Exception as exc:
            return (image, f"xLUT: Failed to apply LUT '{lut.title if lut else 'unknown'}': {exc}", None)

        info = (
            f"xLUT: Applied '{lut.title}' "
            f"(size={lut.size}, strength={max(0.0, min(1.0, float(strength))):.2f})"
        )
        if generated_info:
            info = f"{generated_info} {info}"
        if lut_payload is None and lut is not None:
            lut_payload = _lut_payload_from_cube(lut)
        return (out, info, lut_payload)


class xLUTOutput:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "save_name": ("STRING", {"default": "mkrshift_lut"}),
                "subfolder": ("STRING", {"default": "generated"}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_preview": ("BOOLEAN", {"default": True}),
                "preview_size": ("INT", {"default": 448, "min": 128, "max": 2048, "step": 8}),
                "generated_lut_size": ("INT", {"default": 33, "min": 4, "max": 64, "step": 1}),
                "generated_style_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
            },
            "optional": {
                "lut": (LUT_DATA_TYPE,),
                "lut_image": ("IMAGE",),
            },
        }

    RETURN_TYPES = (LUT_DATA_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("lut", "saved_path", "save_info")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = COLOR_LUT

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Save nodes should run on every queue even when inputs are unchanged.
        return float("nan")

    def run(
        self,
        save_name: str = "mkrshift_lut",
        subfolder: str = "generated",
        overwrite: bool = False,
        save_preview: bool = True,
        preview_size: int = 448,
        generated_lut_size: int = 33,
        generated_style_strength: float = 1.0,
        lut: Optional[Dict[str, object]] = None,
        lut_image: Optional[torch.Tensor] = None,
    ):
        cube: Optional[LutCube] = None
        lut_payload: Optional[Dict[str, object]] = None

        if lut is not None:
            try:
                cube = _cube_from_lut_payload(lut)
            except Exception as exc:
                return (None, "", f"xLUTOutput: Invalid LUT input: {exc}")
        elif lut_image is not None:
            try:
                cube = _build_lut_from_image(
                    reference_image=lut_image,
                    lut_size=int(generated_lut_size),
                    lut_name_hint=str(save_name),
                    style_strength=float(generated_style_strength),
                )
            except Exception as exc:
                return (None, "", f"xLUTOutput: Failed to generate LUT from lut_image: {exc}")
        else:
            return (None, "", "xLUTOutput: No LUT input connected. Connect xLUT 'lut' output or a lut_image.")

        try:
            saved_path = _save_lut_cube(
                cube=cube,
                save_name=str(save_name),
                subfolder=str(subfolder),
                overwrite=bool(overwrite),
            )
        except Exception as exc:
            return (None, "", f"xLUTOutput: Failed to save LUT: {exc}")

        try:
            saved_cube = _load_cube(saved_path)
            lut_payload = _lut_payload_from_cube(saved_cube)
            cube_for_preview = saved_cube
        except Exception:
            cube_for_preview = LutCube(
                path=saved_path,
                title=_sanitize_lut_name(save_name),
                size=int(cube.size),
                domain_min=cube.domain_min,
                domain_max=cube.domain_max,
                table=np.asarray(cube.table, dtype=np.float32),
            )
            lut_payload = _lut_payload_from_cube(
                cube_for_preview
            )

        preview_info = ""
        if bool(save_preview):
            try:
                preview_source = "lut_image" if lut_image is not None else "chart"
                preview_path = _save_lut_preview_image(
                    cube_for_preview,
                    saved_path,
                    preview_size=int(preview_size),
                    reference_image=lut_image,
                )
                preview_info = f" preview='{preview_path}' preview_source='{preview_source}'"
            except Exception as exc:
                preview_info = f" preview_error='{exc}'"

        info = f"xLUTOutput: Saved LUT '{_sanitize_lut_name(save_name)}' to '{saved_path}' (size={int(cube.size)}).{preview_info}"
        print(info)
        return (lut_payload, saved_path, info)


def _is_fastapi_runtime() -> bool:
    if PromptServer is None:
        return False
    try:
        app_instance = getattr(PromptServer.instance, "app", None)
        if app_instance is None:
            return False
        module_name = str(app_instance.__class__.__module__).lower()
        return ("fastapi" in module_name) or ("starlette" in module_name)
    except Exception:
        return False


def _json_response(payload, status: int = 200):
    if _is_fastapi_runtime() and FastJSONResponse is not None:
        return FastJSONResponse(payload, status_code=status)
    if web is not None:
        return web.json_response(payload, status=status)
    if FastJSONResponse is not None:
        return FastJSONResponse(payload, status_code=status)
    return payload


def _file_response(path: str):
    if _is_fastapi_runtime() and FastFileResponse is not None:
        return FastFileResponse(path)
    if web is not None:
        return web.FileResponse(path)
    if FastFileResponse is not None:
        return FastFileResponse(path)
    raise RuntimeError("No response backend available")


def _not_found(message: str):
    if _is_fastapi_runtime() and HTTPException is not None:
        raise HTTPException(status_code=404, detail=message)
    if web is not None:
        raise web.HTTPNotFound(text=message)
    if HTTPException is not None:
        raise HTTPException(status_code=404, detail=message)
    return _json_response({"error": message}, status=404)


def _query_value(request=None, key: str = "", default: str = "") -> str:
    if request is None or not key:
        return default
    try:
        if hasattr(request, "rel_url") and hasattr(request.rel_url, "query"):
            value = request.rel_url.query.get(key, default)
            return str(value)
    except Exception:
        pass
    try:
        query_params = getattr(request, "query_params", None)
        if query_params is not None:
            value = query_params.get(key, default)
            return str(value)
    except Exception:
        pass
    return default


if PromptServer is not None:

    @PromptServer.instance.routes.get("/mkrshift_lut/list")
    async def mkrshift_lut_list(request=None):
        folder = _query_value(request, "folder", "")
        payload = _lut_catalog_payload(folder_filter=folder)
        return _json_response(payload)


    @PromptServer.instance.routes.get("/mkrshift_lut/preview")
    async def mkrshift_lut_preview(request=None):
        label = _query_value(request, "label", "").strip()
        if not label:
            return _not_found("Missing LUT label")

        resolved = _discover_luts().get(label)
        if not resolved:
            return _not_found(f"LUT '{label}' not found")

        preview_path = _maybe_generate_preview_for_lut_path(resolved)
        if not preview_path or not os.path.isfile(preview_path):
            return _not_found("LUT preview not found")
        return _file_response(preview_path)
