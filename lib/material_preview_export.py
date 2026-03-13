from __future__ import annotations

import json
import math
import re
import struct
import uuid
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
import torch

from .image_shared import luma_np, to_image_batch
from .technical_art_shared import decode_normal_np, encode_normal_np

try:
    import folder_paths  # type: ignore
except Exception:  # pragma: no cover
    folder_paths = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUBFOLDER = "mkrshift/material_preview"
DEFAULT_TEXTURE_SIZE = 1024
SHADER_BALL_LON_SEGMENTS = 128
SHADER_BALL_LAT_SEGMENTS = 64
GLTF_REPEAT_WRAP = 10497
GLB_HEADER_MAGIC = 0x46546C67
GLB_VERSION = 2
GLB_JSON_CHUNK_TYPE = 0x4E4F534A
GLB_BIN_CHUNK_TYPE = 0x004E4942


def _default_output_root_from_node_path() -> Path:
    node_dir = PACKAGE_ROOT.resolve()
    for parent in node_dir.parents:
        if parent.name == "custom_nodes":
            return (parent.parent / "output").resolve()
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
    parts = [part for part in raw.split("/") if part.strip() and part.strip() not in {".", ".."}]
    safe_parts: List[str] = []
    for part in parts:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", part).strip("._-")
        if cleaned:
            safe_parts.append(cleaned)
    return "/".join(safe_parts)


def _output_dir(subfolder: str = DEFAULT_SUBFOLDER) -> Path:
    base = _output_root_dir().resolve()
    safe_sub = _safe_subfolder(subfolder)
    target = (base / safe_sub).resolve() if safe_sub else base
    try:
        target.relative_to(base)
    except ValueError:
        return base
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_material_preview_output_path(model_file: str) -> Path:
    relative = str(model_file or "").replace("[output]", "").strip().strip("/")
    if not relative:
        raise ValueError("model_file was empty")
    target = (_output_root_dir() / relative).resolve()
    target.relative_to(_output_root_dir().resolve())
    return target


def _sanitize_label(value: str, fallback: str = "material_preview") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return (text or fallback)[:96]


def _parse_advanced_settings(raw: str) -> tuple[Dict[str, object], bool]:
    text = str(raw or "").strip()
    if not text:
        return {}, True
    try:
        payload = json.loads(text)
    except Exception:
        return {}, False
    return (payload if isinstance(payload, dict) else {}), isinstance(payload, dict)


def _settings_float(
    settings: Dict[str, object],
    key: str,
    default: float,
    *,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    allow_infinite: bool = False,
) -> float:
    value = settings.get(key, default)
    try:
        number = float(value)
    except Exception:
        number = float(default)
    if allow_infinite and math.isinf(number):
        return number
    if min_value is not None:
        number = max(float(min_value), number)
    if max_value is not None:
        number = min(float(max_value), number)
    return float(number)


def _settings_color(settings: Dict[str, object], key: str, default: Tuple[float, float, float]) -> List[float]:
    value = settings.get(key, default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return [float(default[0]), float(default[1]), float(default[2])]
    out: List[float] = []
    for idx in range(3):
        try:
            out.append(float(np.clip(float(value[idx]), 0.0, 1.0)))
        except Exception:
            out.append(float(default[idx]))
    return out


def _sample_image_np(image: torch.Tensor, width: int, height: int, include_alpha: bool = False) -> np.ndarray:
    batch = to_image_batch(image)
    sample = batch[0].detach().cpu().numpy().astype(np.float32, copy=False)
    mode = "RGBA" if include_alpha else "RGB"
    channels = 4 if include_alpha else 3
    if include_alpha and sample.shape[-1] == 3:
        alpha = np.ones((sample.shape[0], sample.shape[1], 1), dtype=np.float32)
        sample = np.concatenate([sample[..., :3], alpha], axis=-1)
    pil = Image.fromarray(np.clip(sample[..., :channels] * 255.0, 0.0, 255.0).astype(np.uint8), mode=mode)
    if pil.size != (int(width), int(height)):
        pil = pil.resize((int(width), int(height)), resample=Image.Resampling.BILINEAR)
    out = np.asarray(pil, dtype=np.float32) / 255.0
    return out.astype(np.float32, copy=False)


def _sample_scalar_np(image: torch.Tensor, width: int, height: int, prefer_alpha: bool = False) -> np.ndarray:
    sample = _sample_image_np(image, width=width, height=height, include_alpha=prefer_alpha)
    if prefer_alpha and sample.shape[-1] >= 4:
        return np.clip(sample[..., 3], 0.0, 1.0).astype(np.float32, copy=False)
    if sample.shape[-1] == 1:
        return np.clip(sample[..., 0], 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip(luma_np(sample[..., :3]), 0.0, 1.0).astype(np.float32, copy=False)


def _first_resolution(*images: Optional[torch.Tensor]) -> Tuple[int, int]:
    for value in images:
        if value is None or not torch.is_tensor(value):
            continue
        batch = to_image_batch(value)
        return int(batch.shape[2]), int(batch.shape[1])
    return (DEFAULT_TEXTURE_SIZE, DEFAULT_TEXTURE_SIZE)


def _neutral_normal(width: int, height: int) -> np.ndarray:
    out = np.empty((int(height), int(width), 3), dtype=np.float32)
    out[..., 0] = 0.5
    out[..., 1] = 0.5
    out[..., 2] = 1.0
    return out


def _height_to_normal_rgb(height: np.ndarray, strength: float) -> np.ndarray:
    grad_y, grad_x = np.gradient(np.clip(height, 0.0, 1.0).astype(np.float32, copy=False))
    nx = -grad_x * float(max(0.0, strength))
    ny = -grad_y * float(max(0.0, strength))
    nz = np.ones_like(height, dtype=np.float32)
    length = np.sqrt((nx * nx) + (ny * ny) + (nz * nz))
    normal = np.stack(
        [
            (nx / np.maximum(length, 1e-6) * 0.5) + 0.5,
            (ny / np.maximum(length, 1e-6) * 0.5) + 0.5,
            (nz / np.maximum(length, 1e-6) * 0.5) + 0.5,
        ],
        axis=-1,
    )
    return np.clip(normal, 0.0, 1.0).astype(np.float32, copy=False)


def _apply_normal_strength(normal_rgb: np.ndarray, strength: float) -> np.ndarray:
    s = float(max(0.0, strength))
    if abs(s - 1.0) <= 1e-6:
        return np.clip(normal_rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    normal = decode_normal_np(normal_rgb[..., :3])
    normal[..., 0] *= s
    normal[..., 1] *= s
    return encode_normal_np(normal)


def _blend_whiteout_normals(base_rgb: np.ndarray, detail_rgb: np.ndarray) -> np.ndarray:
    base = decode_normal_np(base_rgb[..., :3])
    detail = decode_normal_np(detail_rgb[..., :3])
    blended = np.stack(
        [
            base[..., 0] + detail[..., 0],
            base[..., 1] + detail[..., 1],
            base[..., 2] * detail[..., 2],
        ],
        axis=-1,
    )
    return encode_normal_np(blended)


def _convert_input_normal_rgb(normal_rgb: np.ndarray, source_convention: str) -> np.ndarray:
    rgb = np.clip(normal_rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=True)
    if str(source_convention or "directx").strip().lower() == "directx":
        rgb[..., 1] = 1.0 - rgb[..., 1]
    return rgb.astype(np.float32, copy=False)


def _alpha_mode_from_values(alpha: np.ndarray, requested_mode: str) -> str:
    mode = str(requested_mode or "auto").strip().lower()
    if np.all(alpha >= 0.999):
        return "OPAQUE"
    if mode == "mask":
        return "MASK"
    if mode == "blend":
        return "BLEND"
    transition_ratio = float(np.mean((alpha > 0.02) & (alpha < 0.98)))
    return "BLEND" if transition_ratio > 0.01 else "MASK"


def _encode_png_bytes(image_np: np.ndarray, mode: str) -> bytes:
    buffer = BytesIO()
    image = Image.fromarray(np.clip(image_np * 255.0, 0.0, 255.0).astype(np.uint8), mode=mode)
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _encode_rgb_png_bytes(rgb: np.ndarray) -> bytes:
    return _encode_png_bytes(rgb, mode="RGB")


def _encode_rgba_png_bytes(rgba: np.ndarray) -> bytes:
    return _encode_png_bytes(rgba, mode="RGBA")


def _scalar_to_rgb(scalar: np.ndarray) -> np.ndarray:
    return np.repeat(np.clip(scalar, 0.0, 1.0)[..., None], 3, axis=-1).astype(np.float32, copy=False)


def _scalar_to_alpha_rgba(scalar: np.ndarray, rgb: Optional[np.ndarray] = None) -> np.ndarray:
    alpha = np.clip(scalar, 0.0, 1.0).astype(np.float32, copy=False)[..., None]
    if rgb is None:
        rgb_np = np.ones(alpha.shape[:-1] + (3,), dtype=np.float32)
    else:
        rgb_np = np.clip(rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    return np.concatenate([rgb_np, alpha], axis=-1).astype(np.float32, copy=False)


def _has_meaningful_chroma(rgb: np.ndarray) -> bool:
    sample = np.clip(rgb[..., :3], 0.0, 1.0).astype(np.float32, copy=False)
    chroma = np.max(sample, axis=-1) - np.min(sample, axis=-1)
    return float(np.mean(chroma)) > 0.015


def _append_binary_blob(binary: bytearray, payload: bytes, target: Optional[int] = None) -> Dict[str, object]:
    start = len(binary)
    binary.extend(payload)
    while len(binary) % 4:
        binary.append(0)
    buffer_view: Dict[str, object] = {
        "buffer": 0,
        "byteOffset": start,
        "byteLength": int(len(payload)),
    }
    if target is not None:
        buffer_view["target"] = int(target)
    return buffer_view


def _pack_accessor(
    binary: bytearray,
    array: np.ndarray,
    component_type: int,
    accessor_type: str,
    target: Optional[int] = None,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    buffer_view = _append_binary_blob(binary, array.tobytes(), target=target)

    accessor: Dict[str, object] = {
        "bufferView": 0,  # placeholder, filled by caller
        "componentType": int(component_type),
        "count": int(array.shape[0]),
        "type": accessor_type,
    }
    if accessor_type != "SCALAR":
        accessor["min"] = [float(v) for v in np.min(array, axis=0).tolist()]
        accessor["max"] = [float(v) for v in np.max(array, axis=0).tolist()]
    elif array.size:
        accessor["min"] = [int(np.min(array))]
        accessor["max"] = [int(np.max(array))]
    return buffer_view, accessor


def _build_glb_bytes(gltf: Dict[str, object], binary: bytes) -> bytes:
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(json_chunk) % 4:
        json_chunk += b" "

    bin_chunk = bytes(binary)
    while len(bin_chunk) % 4:
        bin_chunk += b"\x00"

    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return b"".join(
        [
            struct.pack("<III", GLB_HEADER_MAGIC, GLB_VERSION, total_length),
            struct.pack("<II", len(json_chunk), GLB_JSON_CHUNK_TYPE),
            json_chunk,
            struct.pack("<II", len(bin_chunk), GLB_BIN_CHUNK_TYPE),
            bin_chunk,
        ]
    )


def _normalize_vectors(vectors: np.ndarray, fallback: Optional[np.ndarray] = None) -> np.ndarray:
    length = np.linalg.norm(vectors, axis=-1, keepdims=True)
    normalized = vectors / np.maximum(length, 1e-6)
    if fallback is None:
        return normalized.astype(np.float32, copy=False)
    mask = length.squeeze(-1) <= 1e-6
    if np.any(mask):
        normalized = normalized.astype(np.float32, copy=True)
        normalized[mask] = fallback[mask]
    return normalized.astype(np.float32, copy=False)


def _sample_scalar_at_uv(scalar: np.ndarray, uvs: np.ndarray) -> np.ndarray:
    h, w = scalar.shape[:2]
    if h <= 0 or w <= 0:
        return np.zeros((int(uvs.shape[0]),), dtype=np.float32)

    u = np.mod(uvs[:, 0], 1.0).astype(np.float32, copy=False)
    v = np.mod(uvs[:, 1], 1.0).astype(np.float32, copy=False)
    x = u * float(max(1, w - 1))
    y = v * float(max(1, h - 1))

    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = (x0 + 1) % max(1, w)
    y1 = (y0 + 1) % max(1, h)
    tx = (x - x0).astype(np.float32, copy=False)
    ty = (y - y0).astype(np.float32, copy=False)

    s00 = scalar[y0, x0]
    s10 = scalar[y0, x1]
    s01 = scalar[y1, x0]
    s11 = scalar[y1, x1]
    top = (s00 * (1.0 - tx)) + (s10 * tx)
    bottom = (s01 * (1.0 - tx)) + (s11 * tx)
    return ((top * (1.0 - ty)) + (bottom * ty)).astype(np.float32, copy=False)


def _sample_rgb_at_uv(rgb: np.ndarray, uvs: np.ndarray) -> np.ndarray:
    channels = []
    for channel_idx in range(3):
        channels.append(_sample_scalar_at_uv(rgb[..., channel_idx], uvs))
    return np.stack(channels, axis=-1).astype(np.float32, copy=False)


def _fallback_tangent_from_normal(normals: np.ndarray) -> np.ndarray:
    up = np.zeros_like(normals, dtype=np.float32)
    up[:, 1] = 1.0
    tangent = np.cross(up, normals)
    tangent = _normalize_vectors(tangent)
    weak = np.linalg.norm(tangent, axis=-1) <= 1e-4
    if np.any(weak):
        axis = np.zeros_like(normals, dtype=np.float32)
        axis[:, 0] = 1.0
        tangent[weak] = _normalize_vectors(np.cross(axis[weak], normals[weak]))
    return tangent.astype(np.float32, copy=False)


def _compute_vertex_tangent_frame(
    positions: np.ndarray,
    normals: np.ndarray,
    uvs: np.ndarray,
    indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    tangents = np.zeros_like(positions, dtype=np.float32)
    bitangent_accum = np.zeros_like(positions, dtype=np.float32)
    triangles = indices.reshape(-1, 3)

    for tri in triangles:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        p0, p1, p2 = positions[i0], positions[i1], positions[i2]
        uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]

        edge1 = p1 - p0
        edge2 = p2 - p0
        duv1 = uv1 - uv0
        duv2 = uv2 - uv0
        determinant = float((duv1[0] * duv2[1]) - (duv1[1] * duv2[0]))
        if abs(determinant) <= 1e-8:
            continue

        inv_det = 1.0 / determinant
        tangent = ((edge1 * duv2[1]) - (edge2 * duv1[1])) * inv_det
        bitangent = ((edge2 * duv1[0]) - (edge1 * duv2[0])) * inv_det
        tangents[i0] += tangent
        tangents[i1] += tangent
        tangents[i2] += tangent
        bitangent_accum[i0] += bitangent
        bitangent_accum[i1] += bitangent
        bitangent_accum[i2] += bitangent

    fallback_tangent = _fallback_tangent_from_normal(normals)
    tangents = tangents - (normals * np.sum(normals * tangents, axis=-1, keepdims=True))
    tangents = _normalize_vectors(tangents, fallback=fallback_tangent)

    bitangents = np.cross(normals, tangents)
    handedness = np.sign(np.sum(np.cross(normals, tangents) * bitangent_accum, axis=-1, keepdims=True))
    handedness = np.where(np.abs(handedness) <= 1e-6, 1.0, handedness).astype(np.float32, copy=False)
    bitangents = _normalize_vectors(bitangents * handedness)
    return tangents.astype(np.float32, copy=False), bitangents.astype(np.float32, copy=False)


def _recompute_vertex_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(positions, dtype=np.float32)
    triangles = indices.reshape(-1, 3)
    for tri in triangles:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        p0, p1, p2 = positions[i0], positions[i1], positions[i2]
        face_normal = np.cross(p1 - p0, p2 - p0)
        normals[i0] += face_normal
        normals[i1] += face_normal
        normals[i2] += face_normal
    fallback = _normalize_vectors(positions.copy())
    return _normalize_vectors(normals, fallback=fallback)


def _resolve_displacement_mode(settings: Dict[str, object]) -> str:
    mode = str(settings.get("displacement_mode", "auto") or "auto").strip().lower()
    if mode in {"off", "none", "disabled"}:
        return "off"
    if mode in {"height", "normal", "height_normal", "normal_height", "auto"}:
        return mode
    return "auto"


def _default_height_displacement_strength(preview_mesh: str, has_height: bool) -> float:
    if not has_height:
        return 0.0
    mesh_key = str(preview_mesh or "shader_ball").strip().lower()
    if mesh_key == "plane":
        return 0.08
    if mesh_key == "cube":
        return 0.06
    return 0.10


def _apply_preview_displacement(
    *,
    positions: np.ndarray,
    normals: np.ndarray,
    uvs: np.ndarray,
    indices: np.ndarray,
    height_scalar: Optional[np.ndarray],
    input_normal_rgb: Optional[np.ndarray],
    displacement_mode: str,
    height_displacement_strength: float,
    normal_displacement_strength: float,
    displacement_midlevel: float,
) -> tuple[np.ndarray, np.ndarray, List[str]]:
    displaced_positions = positions.astype(np.float32, copy=True)
    current_normals = _normalize_vectors(normals.astype(np.float32, copy=False), fallback=_normalize_vectors(positions))
    applied: List[str] = []
    mode = str(displacement_mode or "auto").strip().lower()

    use_height = mode in {"auto", "height", "height_normal", "normal_height"} and height_scalar is not None and float(height_displacement_strength) > 1e-6
    use_normal = mode in {"auto", "normal", "height_normal", "normal_height"} and input_normal_rgb is not None and float(normal_displacement_strength) > 1e-6

    if use_height:
        height_samples = _sample_scalar_at_uv(height_scalar, uvs)
        height_offset = (height_samples - float(np.clip(displacement_midlevel, 0.0, 1.0))) * float(height_displacement_strength)
        displaced_positions += current_normals * height_offset[:, None]
        current_normals = _recompute_vertex_normals(displaced_positions, indices)
        applied.append("height")

    if use_normal:
        tangents, bitangents = _compute_vertex_tangent_frame(displaced_positions, current_normals, uvs, indices)
        sampled_normal_rgb = _sample_rgb_at_uv(input_normal_rgb, uvs)
        tangent_normals = decode_normal_np(sampled_normal_rgb)
        world_offset = (
            (tangents * tangent_normals[:, 0:1])
            + (bitangents * tangent_normals[:, 1:2])
            + (current_normals * (tangent_normals[:, 2:3] - 1.0))
        ).astype(np.float32, copy=False)
        displaced_positions += world_offset * float(normal_displacement_strength)
        current_normals = _recompute_vertex_normals(displaced_positions, indices)
        applied.append("normal")

    return displaced_positions.astype(np.float32, copy=False), current_normals.astype(np.float32, copy=False), applied


def _build_sphere(uv_scale: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Keep the shader ball dense enough for silhouette and displacement preview work.
    lon_segments = SHADER_BALL_LON_SEGMENTS
    lat_segments = SHADER_BALL_LAT_SEGMENTS
    positions: List[List[float]] = []
    normals: List[List[float]] = []
    uvs: List[List[float]] = []
    indices: List[int] = []

    for y_idx in range(lat_segments + 1):
        v = y_idx / float(lat_segments)
        theta = v * math.pi
        sin_theta = math.sin(theta)
        cos_theta = math.cos(theta)
        for x_idx in range(lon_segments + 1):
            u = x_idx / float(lon_segments)
            phi = u * math.tau
            px = sin_theta * math.cos(phi)
            py = cos_theta
            pz = sin_theta * math.sin(phi)
            positions.append([px, py, pz])
            normals.append([px, py, pz])
            uvs.append([u * uv_scale, (1.0 - v) * uv_scale])

    stride = lon_segments + 1
    for y_idx in range(lat_segments):
        for x_idx in range(lon_segments):
            i0 = y_idx * stride + x_idx
            i1 = i0 + 1
            i2 = i0 + stride
            i3 = i2 + 1
            indices.extend([i0, i1, i2, i1, i3, i2])

    return (
        np.asarray(positions, dtype=np.float32),
        np.asarray(normals, dtype=np.float32),
        np.asarray(uvs, dtype=np.float32),
        np.asarray(indices, dtype=np.uint16),
    )


def _build_plane(uv_scale: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    positions = np.asarray(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    normals = np.asarray([[0.0, 0.0, 1.0]] * 4, dtype=np.float32)
    uvs = np.asarray(
        [
            [0.0, uv_scale],
            [uv_scale, uv_scale],
            [uv_scale, 0.0],
            [0.0, 0.0],
        ],
        dtype=np.float32,
    )
    indices = np.asarray([0, 1, 2, 0, 2, 3], dtype=np.uint16)
    return positions, normals, uvs, indices


def _build_cube(uv_scale: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    face_specs = [
        ((0.0, 0.0, 1.0), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0.0, 0.0, -1.0), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),
        ((1.0, 0.0, 0.0), [(1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1)]),
        ((-1.0, 0.0, 0.0), [(-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)]),
        ((0.0, 1.0, 0.0), [(-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)]),
        ((0.0, -1.0, 0.0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
    ]
    uv_face = [(0.0, uv_scale), (uv_scale, uv_scale), (uv_scale, 0.0), (0.0, 0.0)]
    positions: List[List[float]] = []
    normals: List[List[float]] = []
    uvs: List[List[float]] = []
    indices: List[int] = []

    for face_idx, (normal, verts) in enumerate(face_specs):
        base_index = face_idx * 4
        for vertex, uv in zip(verts, uv_face):
            positions.append([float(vertex[0]), float(vertex[1]), float(vertex[2])])
            normals.append([float(normal[0]), float(normal[1]), float(normal[2])])
            uvs.append([float(uv[0]), float(uv[1])])
        indices.extend([base_index, base_index + 1, base_index + 2, base_index, base_index + 2, base_index + 3])

    return (
        np.asarray(positions, dtype=np.float32),
        np.asarray(normals, dtype=np.float32),
        np.asarray(uvs, dtype=np.float32),
        np.asarray(indices, dtype=np.uint16),
    )


def _build_preview_mesh(mesh_name: str, uv_scale: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    key = str(mesh_name or "shader_ball").strip().lower()
    scale = float(max(0.01, uv_scale))
    if key == "plane":
        return _build_plane(scale)
    if key == "cube":
        return _build_cube(scale)
    return _build_sphere(scale)


def export_material_preview_asset(
    *,
    preview_mesh: str,
    uv_scale: float,
    asset_label: str,
    roughness_default: float,
    metalness_default: float,
    normal_strength: float,
    normal_convention: str,
    height_to_normal_strength: float,
    emissive_strength: float,
    alpha_mode: str,
    advanced_settings_json: str = "",
    base_color: Optional[torch.Tensor] = None,
    normal: Optional[torch.Tensor] = None,
    roughness: Optional[torch.Tensor] = None,
    metalness: Optional[torch.Tensor] = None,
    specular: Optional[torch.Tensor] = None,
    height: Optional[torch.Tensor] = None,
    ao: Optional[torch.Tensor] = None,
    opacity: Optional[torch.Tensor] = None,
    emissive: Optional[torch.Tensor] = None,
    clearcoat: Optional[torch.Tensor] = None,
    clearcoat_roughness: Optional[torch.Tensor] = None,
    anisotropy: Optional[torch.Tensor] = None,
    sheen_color: Optional[torch.Tensor] = None,
    sheen_roughness: Optional[torch.Tensor] = None,
    transmission: Optional[torch.Tensor] = None,
    thickness: Optional[torch.Tensor] = None,
    iridescence: Optional[torch.Tensor] = None,
    iridescence_thickness: Optional[torch.Tensor] = None,
) -> Dict[str, object]:
    settings, settings_valid = _parse_advanced_settings(advanced_settings_json)
    clearcoat_default = _settings_float(settings, "clearcoat_default", 0.0, min_value=0.0, max_value=1.0)
    clearcoat_roughness_default = _settings_float(
        settings,
        "clearcoat_roughness_default",
        0.15,
        min_value=0.0,
        max_value=1.0,
    )
    anisotropy_default = _settings_float(settings, "anisotropy_default", 0.0, min_value=0.0, max_value=1.0)
    if "anisotropy_rotation_deg" in settings:
        anisotropy_rotation = math.radians(
            _settings_float(settings, "anisotropy_rotation_deg", 0.0, min_value=-360.0, max_value=360.0)
        )
    else:
        anisotropy_rotation = _settings_float(
            settings,
            "anisotropy_rotation",
            0.0,
            min_value=-math.tau,
            max_value=math.tau,
        )
    specular_default = _settings_float(settings, "specular_default", 1.0, min_value=0.0, max_value=1.0)
    specular_color_default = _settings_color(settings, "specular_color_default", (1.0, 1.0, 1.0))
    sheen_roughness_default = _settings_float(settings, "sheen_roughness_default", 0.35, min_value=0.0, max_value=1.0)
    sheen_color_default = _settings_color(settings, "sheen_color_default", (0.0, 0.0, 0.0))
    transmission_default = _settings_float(settings, "transmission_default", 0.0, min_value=0.0, max_value=1.0)
    thickness_default = _settings_float(settings, "thickness_default", 0.0, min_value=0.0, max_value=1.0)
    iridescence_default = _settings_float(settings, "iridescence_default", 0.0, min_value=0.0, max_value=1.0)
    iridescence_ior = _settings_float(settings, "iridescence_ior", 1.3, min_value=1.0, max_value=3.0)
    iridescence_thickness_min = _settings_float(
        settings,
        "iridescence_thickness_min",
        100.0,
        min_value=0.0,
        max_value=4000.0,
    )
    iridescence_thickness_max = _settings_float(
        settings,
        "iridescence_thickness_max",
        400.0,
        min_value=0.0,
        max_value=4000.0,
    )
    if iridescence_thickness_max < iridescence_thickness_min:
        iridescence_thickness_max = iridescence_thickness_min
    ior_value = _settings_float(settings, "ior", 1.5, min_value=1.0, max_value=2.5)
    attenuation_distance = _settings_float(
        settings,
        "attenuation_distance",
        math.inf,
        min_value=1e-3,
        allow_infinite=True,
    )
    attenuation_color = _settings_color(settings, "attenuation_color", (1.0, 1.0, 1.0))

    width, height_px = _first_resolution(
        base_color,
        normal,
        roughness,
        metalness,
        specular,
        height,
        ao,
        opacity,
        emissive,
        clearcoat,
        clearcoat_roughness,
        anisotropy,
        sheen_color,
        sheen_roughness,
        transmission,
        thickness,
        iridescence,
        iridescence_thickness,
    )
    base_rgba = np.full((height_px, width, 4), 0.72, dtype=np.float32)
    base_rgba[..., 3] = 1.0
    used_maps: List[str] = []
    notes: List[str] = []
    if str(advanced_settings_json or "").strip() and not settings_valid:
        notes.append("advanced_settings_json(invalid)")

    if base_color is not None:
        base_rgba = _sample_image_np(base_color, width=width, height=height_px, include_alpha=True)
        used_maps.append("base_color")
    else:
        notes.append("base_color=fallback")

    if opacity is not None:
        base_rgba[..., 3] = np.clip(base_rgba[..., 3] * _sample_scalar_np(opacity, width=width, height=height_px), 0.0, 1.0)
        used_maps.append("opacity")

    roughness_np = np.full((height_px, width), float(np.clip(roughness_default, 0.0, 1.0)), dtype=np.float32)
    if roughness is not None:
        roughness_np = _sample_scalar_np(roughness, width=width, height=height_px)
        used_maps.append("roughness")

    metalness_np = np.full((height_px, width), float(np.clip(metalness_default, 0.0, 1.0)), dtype=np.float32)
    if metalness is not None:
        metalness_np = _sample_scalar_np(metalness, width=width, height=height_px)
        used_maps.append("metalness")

    specular_scalar: Optional[np.ndarray] = None
    specular_color_rgb: Optional[np.ndarray] = None
    specular_factor = specular_default
    specular_color_factor = [float(value) for value in specular_color_default]
    if specular is not None:
        specular_sample_rgb = _sample_image_np(specular, width=width, height=height_px, include_alpha=False)[..., :3]
        specular_scalar = _sample_scalar_np(specular, width=width, height=height_px)
        specular_factor = 1.0
        if _has_meaningful_chroma(specular_sample_rgb):
            specular_color_rgb = specular_sample_rgb.astype(np.float32, copy=False)
        if roughness is None:
            roughness_np = np.clip(1.0 - (specular_scalar * 0.82), 0.04, 1.0).astype(np.float32, copy=False)
        else:
            roughness_np = np.clip(roughness_np * (1.0 - (specular_scalar * 0.35)), 0.04, 1.0).astype(np.float32, copy=False)
        used_maps.append("specular")
        notes.append("specular->roughness")
    elif abs(float(specular_default) - 1.0) > 1e-6:
        notes.append(f"specular_default={specular_default:.2f}")

    normal_rgb = _neutral_normal(width=width, height=height_px)
    input_normal_rgb_for_displacement: Optional[np.ndarray] = None
    if normal is not None:
        normal_rgb = _sample_image_np(normal, width=width, height=height_px, include_alpha=False)[..., :3]
        normal_rgb = _convert_input_normal_rgb(normal_rgb, source_convention=normal_convention)
        input_normal_rgb_for_displacement = normal_rgb.copy()
        used_maps.append("normal")

    height_np: Optional[np.ndarray] = None
    if height is not None:
        height_np = _sample_scalar_np(height, width=width, height=height_px)
        height_normal = _height_to_normal_rgb(height_np, strength=height_to_normal_strength)
        normal_rgb = _blend_whiteout_normals(normal_rgb, height_normal) if normal is not None else height_normal
        used_maps.append("height")
        notes.append("height->normal")

    normal_rgb = _apply_normal_strength(normal_rgb, normal_strength)
    if input_normal_rgb_for_displacement is not None:
        input_normal_rgb_for_displacement = _apply_normal_strength(input_normal_rgb_for_displacement, normal_strength)

    displacement_mode = _resolve_displacement_mode(settings)
    height_displacement_strength = _settings_float(
        settings,
        "height_displacement_strength",
        _default_height_displacement_strength(preview_mesh, has_height=height_np is not None),
        min_value=0.0,
        max_value=4.0,
    )
    normal_displacement_strength = _settings_float(
        settings,
        "normal_displacement_strength",
        0.0,
        min_value=0.0,
        max_value=4.0,
    )
    displacement_midlevel = _settings_float(
        settings,
        "displacement_midlevel",
        0.5,
        min_value=0.0,
        max_value=1.0,
    )

    ao_rgb: Optional[np.ndarray] = None
    if ao is not None:
        ao_scalar = _sample_scalar_np(ao, width=width, height=height_px)
        ao_rgb = np.repeat(ao_scalar[..., None], 3, axis=-1).astype(np.float32, copy=False)
        used_maps.append("ao")

    emissive_rgb: Optional[np.ndarray] = None
    if emissive is not None:
        emissive_rgb = np.clip(
            _sample_image_np(emissive, width=width, height=height_px, include_alpha=False)[..., :3] * float(max(0.0, emissive_strength)),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)
        used_maps.append("emissive")

    clearcoat_scalar: Optional[np.ndarray] = None
    clearcoat_factor = clearcoat_default
    if clearcoat is not None:
        clearcoat_scalar = _sample_scalar_np(clearcoat, width=width, height=height_px)
        clearcoat_factor = 1.0
        used_maps.append("clearcoat")
    elif clearcoat_default > 1e-6:
        notes.append(f"clearcoat_default={clearcoat_default:.2f}")

    clearcoat_roughness_scalar: Optional[np.ndarray] = None
    clearcoat_roughness_factor = clearcoat_roughness_default
    if clearcoat_roughness is not None:
        clearcoat_roughness_scalar = _sample_scalar_np(clearcoat_roughness, width=width, height=height_px)
        clearcoat_roughness_factor = 1.0
        used_maps.append("clearcoat_roughness")

    anisotropy_rgb: Optional[np.ndarray] = None
    anisotropy_factor = anisotropy_default
    if anisotropy is not None:
        anisotropy_rgb = _sample_image_np(anisotropy, width=width, height=height_px, include_alpha=False)[..., :3]
        anisotropy_factor = 1.0
        used_maps.append("anisotropy")
    elif anisotropy_default > 1e-6:
        notes.append(f"anisotropy_default={anisotropy_default:.2f}")

    sheen_color_rgb: Optional[np.ndarray] = None
    sheen_color_factor = [float(value) for value in sheen_color_default]
    if sheen_color is not None:
        sheen_color_rgb = _sample_image_np(sheen_color, width=width, height=height_px, include_alpha=False)[..., :3]
        sheen_color_factor = [1.0, 1.0, 1.0]
        used_maps.append("sheen_color")
    elif any(abs(channel) > 1e-6 for channel in sheen_color_default):
        notes.append("sheen_color_default")

    sheen_roughness_scalar: Optional[np.ndarray] = None
    sheen_roughness_factor = sheen_roughness_default
    if sheen_roughness is not None:
        sheen_roughness_scalar = _sample_scalar_np(sheen_roughness, width=width, height=height_px)
        sheen_roughness_factor = 1.0
        used_maps.append("sheen_roughness")

    transmission_scalar: Optional[np.ndarray] = None
    transmission_factor = transmission_default
    if transmission is not None:
        transmission_scalar = _sample_scalar_np(transmission, width=width, height=height_px)
        transmission_factor = 1.0
        used_maps.append("transmission")
    elif transmission_default > 1e-6:
        notes.append(f"transmission_default={transmission_default:.2f}")

    thickness_scalar: Optional[np.ndarray] = None
    thickness_factor = thickness_default
    if thickness is not None:
        thickness_scalar = _sample_scalar_np(thickness, width=width, height=height_px)
        thickness_factor = 1.0
        used_maps.append("thickness")
    elif thickness_default > 1e-6:
        notes.append(f"thickness_default={thickness_default:.2f}")

    iridescence_scalar: Optional[np.ndarray] = None
    iridescence_factor = iridescence_default
    if iridescence is not None:
        iridescence_scalar = _sample_scalar_np(iridescence, width=width, height=height_px)
        iridescence_factor = 1.0
        used_maps.append("iridescence")
    elif iridescence_default > 1e-6:
        notes.append(f"iridescence_default={iridescence_default:.2f}")

    iridescence_thickness_scalar: Optional[np.ndarray] = None
    if iridescence_thickness is not None:
        iridescence_thickness_scalar = _sample_scalar_np(iridescence_thickness, width=width, height=height_px)
        used_maps.append("iridescence_thickness")

    resolved_alpha_mode = _alpha_mode_from_values(base_rgba[..., 3], alpha_mode)
    material_double_sided = str(preview_mesh or "").strip().lower() == "plane" or resolved_alpha_mode != "OPAQUE"

    metal_rough_rgb = np.ones((height_px, width, 3), dtype=np.float32)
    metal_rough_rgb[..., 0] = 1.0
    metal_rough_rgb[..., 1] = np.clip(roughness_np, 0.0, 1.0)
    metal_rough_rgb[..., 2] = np.clip(metalness_np, 0.0, 1.0)

    label = _sanitize_label(asset_label, fallback="material_preview")
    token = uuid.uuid4().hex[:10]
    stem = f"{label}_{_sanitize_label(preview_mesh, fallback='shader_ball')}_{token}"
    out_dir = _output_dir(DEFAULT_SUBFOLDER)
    glb_path = out_dir / f"{stem}.glb"
    base_color_png = _encode_rgba_png_bytes(np.clip(base_rgba, 0.0, 1.0))
    normal_png = _encode_rgb_png_bytes(np.clip(normal_rgb, 0.0, 1.0))
    metal_rough_png = _encode_rgb_png_bytes(np.clip(metal_rough_rgb, 0.0, 1.0))
    ao_png = _encode_rgb_png_bytes(ao_rgb) if ao_rgb is not None else None
    emissive_png = _encode_rgb_png_bytes(emissive_rgb) if emissive_rgb is not None else None
    specular_png = _encode_rgba_png_bytes(_scalar_to_alpha_rgba(specular_scalar)) if specular_scalar is not None else None
    specular_color_png = _encode_rgb_png_bytes(specular_color_rgb) if specular_color_rgb is not None else None
    clearcoat_png = _encode_rgb_png_bytes(_scalar_to_rgb(clearcoat_scalar)) if clearcoat_scalar is not None else None
    clearcoat_roughness_png = (
        _encode_rgb_png_bytes(_scalar_to_rgb(clearcoat_roughness_scalar))
        if clearcoat_roughness_scalar is not None
        else None
    )
    anisotropy_png = _encode_rgb_png_bytes(np.clip(anisotropy_rgb, 0.0, 1.0)) if anisotropy_rgb is not None else None
    sheen_color_png = _encode_rgb_png_bytes(sheen_color_rgb) if sheen_color_rgb is not None else None
    sheen_roughness_png = (
        _encode_rgba_png_bytes(_scalar_to_alpha_rgba(sheen_roughness_scalar))
        if sheen_roughness_scalar is not None
        else None
    )
    transmission_png = _encode_rgb_png_bytes(_scalar_to_rgb(transmission_scalar)) if transmission_scalar is not None else None
    thickness_png = _encode_rgb_png_bytes(_scalar_to_rgb(thickness_scalar)) if thickness_scalar is not None else None
    iridescence_png = _encode_rgb_png_bytes(_scalar_to_rgb(iridescence_scalar)) if iridescence_scalar is not None else None
    iridescence_thickness_png = (
        _encode_rgb_png_bytes(_scalar_to_rgb(iridescence_thickness_scalar))
        if iridescence_thickness_scalar is not None
        else None
    )
    written_files = [glb_path.name]

    positions, normals, uvs, indices = _build_preview_mesh(preview_mesh, uv_scale=uv_scale)
    positions, normals, applied_displacement = _apply_preview_displacement(
        positions=positions,
        normals=normals,
        uvs=uvs,
        indices=indices,
        height_scalar=height_np,
        input_normal_rgb=input_normal_rgb_for_displacement,
        displacement_mode=displacement_mode,
        height_displacement_strength=height_displacement_strength,
        normal_displacement_strength=normal_displacement_strength,
        displacement_midlevel=displacement_midlevel,
    )
    if "height" in applied_displacement:
        notes.append("height->displacement")
    if "normal" in applied_displacement:
        notes.append("normal->displacement")
    tangents, bitangents = _compute_vertex_tangent_frame(positions, normals, uvs, indices)
    tangent_w = np.sign(np.sum(np.cross(normals, tangents) * bitangents, axis=-1, keepdims=True))
    tangent_w = np.where(np.abs(tangent_w) <= 1e-6, 1.0, tangent_w).astype(np.float32, copy=False)
    tangent_vec4 = np.concatenate([tangents, tangent_w], axis=-1).astype(np.float32, copy=False)

    binary = bytearray()
    buffer_views: List[Dict[str, object]] = []
    accessors: List[Dict[str, object]] = []

    for array, component_type, accessor_type, target in (
        (positions, 5126, "VEC3", 34962),
        (normals, 5126, "VEC3", 34962),
        (uvs, 5126, "VEC2", 34962),
        (tangent_vec4, 5126, "VEC4", 34962),
        (indices, 5123, "SCALAR", 34963),
    ):
        buffer_view, accessor = _pack_accessor(binary, array, component_type, accessor_type, target)
        accessor["bufferView"] = len(buffer_views)
        buffer_views.append(buffer_view)
        accessors.append(accessor)

    images: List[Dict[str, object]] = []
    textures = [
        {"sampler": 0, "source": 0},
        {"sampler": 0, "source": 1},
        {"sampler": 0, "source": 2},
    ]

    for png_bytes in (base_color_png, normal_png, metal_rough_png):
        image_buffer_view = _append_binary_blob(binary, png_bytes)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(image_buffer_view)

    ao_texture_index: Optional[int] = None
    emissive_texture_index: Optional[int] = None
    specular_texture_index: Optional[int] = None
    specular_color_texture_index: Optional[int] = None
    clearcoat_texture_index: Optional[int] = None
    clearcoat_roughness_texture_index: Optional[int] = None
    anisotropy_texture_index: Optional[int] = None
    sheen_color_texture_index: Optional[int] = None
    sheen_roughness_texture_index: Optional[int] = None
    transmission_texture_index: Optional[int] = None
    thickness_texture_index: Optional[int] = None
    iridescence_texture_index: Optional[int] = None
    iridescence_thickness_texture_index: Optional[int] = None

    if ao_png is not None:
        ao_texture_index = len(textures)
        ao_buffer_view = _append_binary_blob(binary, ao_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(ao_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if emissive_png is not None:
        emissive_texture_index = len(textures)
        emissive_buffer_view = _append_binary_blob(binary, emissive_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(emissive_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if specular_png is not None:
        specular_texture_index = len(textures)
        specular_buffer_view = _append_binary_blob(binary, specular_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(specular_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if specular_color_png is not None:
        specular_color_texture_index = len(textures)
        specular_color_buffer_view = _append_binary_blob(binary, specular_color_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(specular_color_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if clearcoat_png is not None:
        clearcoat_texture_index = len(textures)
        clearcoat_buffer_view = _append_binary_blob(binary, clearcoat_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(clearcoat_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if clearcoat_roughness_png is not None:
        clearcoat_roughness_texture_index = len(textures)
        clearcoat_roughness_buffer_view = _append_binary_blob(binary, clearcoat_roughness_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(clearcoat_roughness_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if anisotropy_png is not None:
        anisotropy_texture_index = len(textures)
        anisotropy_buffer_view = _append_binary_blob(binary, anisotropy_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(anisotropy_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if sheen_color_png is not None:
        sheen_color_texture_index = len(textures)
        sheen_color_buffer_view = _append_binary_blob(binary, sheen_color_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(sheen_color_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if sheen_roughness_png is not None:
        sheen_roughness_texture_index = len(textures)
        sheen_roughness_buffer_view = _append_binary_blob(binary, sheen_roughness_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(sheen_roughness_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if transmission_png is not None:
        transmission_texture_index = len(textures)
        transmission_buffer_view = _append_binary_blob(binary, transmission_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(transmission_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if thickness_png is not None:
        thickness_texture_index = len(textures)
        thickness_buffer_view = _append_binary_blob(binary, thickness_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(thickness_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if iridescence_png is not None:
        iridescence_texture_index = len(textures)
        iridescence_buffer_view = _append_binary_blob(binary, iridescence_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(iridescence_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})
    if iridescence_thickness_png is not None:
        iridescence_thickness_texture_index = len(textures)
        iridescence_thickness_buffer_view = _append_binary_blob(binary, iridescence_thickness_png)
        images.append({"bufferView": len(buffer_views), "mimeType": "image/png"})
        buffer_views.append(iridescence_thickness_buffer_view)
        textures.append({"sampler": 0, "source": len(images) - 1})

    material: Dict[str, object] = {
        "name": label,
        "doubleSided": bool(material_double_sided),
        "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "metallicRoughnessTexture": {"index": 2},
            "metallicFactor": 1.0,
            "roughnessFactor": 1.0,
        },
        "normalTexture": {"index": 1, "scale": 1.0},
    }
    if resolved_alpha_mode != "OPAQUE":
        material["alphaMode"] = resolved_alpha_mode
        if resolved_alpha_mode == "MASK":
            material["alphaCutoff"] = 0.5
    if ao_texture_index is not None:
        material["occlusionTexture"] = {"index": ao_texture_index, "strength": 1.0}
    if emissive_texture_index is not None:
        material["emissiveTexture"] = {"index": emissive_texture_index}
        material["emissiveFactor"] = [1.0, 1.0, 1.0]

    material_extensions: Dict[str, object] = {}
    extensions_used: List[str] = []
    specular_color_is_default = all(abs(channel - 1.0) <= 1e-6 for channel in specular_color_factor)
    specular_active = (
        specular_texture_index is not None
        or specular_color_texture_index is not None
        or abs(float(specular_factor) - 1.0) > 1e-6
        or not specular_color_is_default
    )
    clearcoat_active = clearcoat_texture_index is not None or clearcoat_factor > 1e-6
    anisotropy_active = anisotropy_texture_index is not None or anisotropy_factor > 1e-6 or abs(float(anisotropy_rotation)) > 1e-6
    sheen_color_is_black = all(abs(channel) <= 1e-6 for channel in sheen_color_factor)
    sheen_active = sheen_color_texture_index is not None or not sheen_color_is_black
    transmission_active = transmission_texture_index is not None or transmission_factor > 1e-6
    attenuation_is_default = bool(math.isinf(attenuation_distance)) and all(abs(channel - 1.0) <= 1e-6 for channel in attenuation_color)
    volume_active = transmission_active and (
        thickness_texture_index is not None or thickness_factor > 1e-6 or not attenuation_is_default
    )
    iridescence_active = iridescence_texture_index is not None or iridescence_factor > 1e-6
    ior_active = abs(float(ior_value) - 1.5) > 1e-6

    if specular_active:
        specular_ext: Dict[str, object] = {
            "specularFactor": float(np.clip(specular_factor, 0.0, 1.0)),
            "specularColorFactor": [float(value) for value in specular_color_factor],
        }
        if specular_texture_index is not None:
            specular_ext["specularTexture"] = {"index": specular_texture_index}
        if specular_color_texture_index is not None:
            specular_ext["specularColorTexture"] = {"index": specular_color_texture_index}
        material_extensions["KHR_materials_specular"] = specular_ext
        extensions_used.append("KHR_materials_specular")

    if clearcoat_active:
        clearcoat_ext: Dict[str, object] = {
            "clearcoatFactor": float(np.clip(clearcoat_factor, 0.0, 1.0)),
            "clearcoatRoughnessFactor": float(np.clip(clearcoat_roughness_factor, 0.0, 1.0)),
        }
        if clearcoat_texture_index is not None:
            clearcoat_ext["clearcoatTexture"] = {"index": clearcoat_texture_index}
        if clearcoat_roughness_texture_index is not None:
            clearcoat_ext["clearcoatRoughnessTexture"] = {"index": clearcoat_roughness_texture_index}
        material_extensions["KHR_materials_clearcoat"] = clearcoat_ext
        extensions_used.append("KHR_materials_clearcoat")

    if anisotropy_active:
        anisotropy_ext: Dict[str, object] = {
            "anisotropyStrength": float(np.clip(anisotropy_factor, 0.0, 1.0)),
            "anisotropyRotation": float(anisotropy_rotation),
        }
        if anisotropy_texture_index is not None:
            anisotropy_ext["anisotropyTexture"] = {"index": anisotropy_texture_index}
        material_extensions["KHR_materials_anisotropy"] = anisotropy_ext
        extensions_used.append("KHR_materials_anisotropy")

    if sheen_active:
        sheen_ext: Dict[str, object] = {
            "sheenColorFactor": [float(value) for value in sheen_color_factor],
            "sheenRoughnessFactor": float(np.clip(sheen_roughness_factor, 0.0, 1.0)),
        }
        if sheen_color_texture_index is not None:
            sheen_ext["sheenColorTexture"] = {"index": sheen_color_texture_index}
        if sheen_roughness_texture_index is not None:
            sheen_ext["sheenRoughnessTexture"] = {"index": sheen_roughness_texture_index}
        material_extensions["KHR_materials_sheen"] = sheen_ext
        extensions_used.append("KHR_materials_sheen")

    if transmission_active:
        transmission_ext: Dict[str, object] = {"transmissionFactor": float(np.clip(transmission_factor, 0.0, 1.0))}
        if transmission_texture_index is not None:
            transmission_ext["transmissionTexture"] = {"index": transmission_texture_index}
        material_extensions["KHR_materials_transmission"] = transmission_ext
        extensions_used.append("KHR_materials_transmission")

    if volume_active:
        volume_ext: Dict[str, object] = {
            "thicknessFactor": float(np.clip(thickness_factor, 0.0, 1.0)),
            "attenuationColor": [float(value) for value in attenuation_color],
        }
        if thickness_texture_index is not None:
            volume_ext["thicknessTexture"] = {"index": thickness_texture_index}
        if not math.isinf(attenuation_distance):
            volume_ext["attenuationDistance"] = float(max(1e-3, attenuation_distance))
        material_extensions["KHR_materials_volume"] = volume_ext
        extensions_used.append("KHR_materials_volume")

    if iridescence_active:
        iridescence_ext: Dict[str, object] = {
            "iridescenceFactor": float(np.clip(iridescence_factor, 0.0, 1.0)),
            "iridescenceIor": float(iridescence_ior),
            "iridescenceThicknessMinimum": float(iridescence_thickness_min),
            "iridescenceThicknessMaximum": float(iridescence_thickness_max),
        }
        if iridescence_texture_index is not None:
            iridescence_ext["iridescenceTexture"] = {"index": iridescence_texture_index}
        if iridescence_thickness_texture_index is not None:
            iridescence_ext["iridescenceThicknessTexture"] = {"index": iridescence_thickness_texture_index}
        material_extensions["KHR_materials_iridescence"] = iridescence_ext
        extensions_used.append("KHR_materials_iridescence")

    if ior_active:
        material_extensions["KHR_materials_ior"] = {"ior": float(ior_value)}
        extensions_used.append("KHR_materials_ior")

    if material_extensions:
        material["extensions"] = material_extensions

    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "MKRShift Nodes x1PreviewMaterial",
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": label, "mesh": 0}],
        "meshes": [
            {
                "name": label,
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "TANGENT": 3},
                        "indices": 4,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [material],
        "samplers": [
            {
                "wrapS": GLTF_REPEAT_WRAP,
                "wrapT": GLTF_REPEAT_WRAP,
                "magFilter": 9729,
                "minFilter": 9987,
            }
        ],
        "images": images,
        "textures": textures,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary)}],
    }
    if extensions_used:
        gltf["extensionsUsed"] = sorted(set(extensions_used))

    # Preview3D resolves external glTF siblings through a query-string path that
    # can misresolve `./texture.png`. A self-contained GLB avoids that entire class of failures.
    glb_path.write_bytes(_build_glb_bytes(gltf, bytes(binary)))

    model_relative = f"{DEFAULT_SUBFOLDER}/{glb_path.name}"
    info = (
        "x1PreviewMaterial: label={}, mesh={}, uv_scale={:.2f}, size={}x{}, alpha_mode={}, "
        "normal_convention={}, used_maps={}, notes={}, files={}"
    ).format(
        label,
        str(preview_mesh or "shader_ball").lower(),
        float(max(0.01, uv_scale)),
        int(width),
        int(height_px),
        resolved_alpha_mode.lower(),
        str(normal_convention or "directx").lower(),
        ",".join(used_maps) if used_maps else "defaults_only",
        ",".join(notes) if notes else "none",
        ",".join(written_files),
    )
    return {
        "model_file": model_relative,
        "info": info,
        "model_path": str(glb_path),
        "glb_path": str(glb_path),
        "written_files": written_files,
    }
