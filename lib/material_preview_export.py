from __future__ import annotations

import base64
import json
import math
import re
import uuid
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
GLTF_REPEAT_WRAP = 10497


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


def _save_rgb_png(path: Path, rgb: np.ndarray) -> None:
    image = Image.fromarray(np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    image.save(path)


def _save_rgba_png(path: Path, rgba: np.ndarray) -> None:
    image = Image.fromarray(np.clip(rgba * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGBA")
    image.save(path)


def _pack_accessor(
    binary: bytearray,
    array: np.ndarray,
    component_type: int,
    accessor_type: str,
    target: Optional[int] = None,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    start = len(binary)
    binary.extend(array.tobytes())
    while len(binary) % 4:
        binary.append(0)
    buffer_view: Dict[str, object] = {
        "buffer": 0,
        "byteOffset": start,
        "byteLength": int(array.nbytes),
    }
    if target is not None:
        buffer_view["target"] = int(target)

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


def _build_sphere(uv_scale: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lon_segments = 64
    lat_segments = 32
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
            indices.extend([i0, i2, i1, i1, i2, i3])

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
    height_to_normal_strength: float,
    emissive_strength: float,
    alpha_mode: str,
    base_color: Optional[torch.Tensor] = None,
    normal: Optional[torch.Tensor] = None,
    roughness: Optional[torch.Tensor] = None,
    metalness: Optional[torch.Tensor] = None,
    specular: Optional[torch.Tensor] = None,
    height: Optional[torch.Tensor] = None,
    ao: Optional[torch.Tensor] = None,
    opacity: Optional[torch.Tensor] = None,
    emissive: Optional[torch.Tensor] = None,
) -> Dict[str, object]:
    width, height_px = _first_resolution(base_color, normal, roughness, metalness, specular, height, ao, opacity, emissive)
    base_rgba = np.full((height_px, width, 4), 0.72, dtype=np.float32)
    base_rgba[..., 3] = 1.0
    used_maps: List[str] = []
    notes: List[str] = []

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

    if specular is not None:
        specular_np = _sample_scalar_np(specular, width=width, height=height_px)
        if roughness is None:
            roughness_np = np.clip(1.0 - (specular_np * 0.82), 0.04, 1.0).astype(np.float32, copy=False)
        else:
            roughness_np = np.clip(roughness_np * (1.0 - (specular_np * 0.35)), 0.04, 1.0).astype(np.float32, copy=False)
        used_maps.append("specular")
        notes.append("specular->roughness")

    normal_rgb = _neutral_normal(width=width, height=height_px)
    if normal is not None:
        normal_rgb = _sample_image_np(normal, width=width, height=height_px, include_alpha=False)[..., :3]
        used_maps.append("normal")

    if height is not None:
        height_np = _sample_scalar_np(height, width=width, height=height_px)
        height_normal = _height_to_normal_rgb(height_np, strength=height_to_normal_strength)
        normal_rgb = _blend_whiteout_normals(normal_rgb, height_normal) if normal is not None else height_normal
        used_maps.append("height")
        notes.append("height->normal")

    normal_rgb = _apply_normal_strength(normal_rgb, normal_strength)

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
    gltf_path = out_dir / f"{stem}.gltf"
    base_color_path = out_dir / f"{stem}_basecolor.png"
    normal_path = out_dir / f"{stem}_normal.png"
    metal_rough_path = out_dir / f"{stem}_metalrough.png"
    ao_path = out_dir / f"{stem}_ao.png"
    emissive_path = out_dir / f"{stem}_emissive.png"

    _save_rgba_png(base_color_path, np.clip(base_rgba, 0.0, 1.0))
    _save_rgb_png(normal_path, np.clip(normal_rgb, 0.0, 1.0))
    _save_rgb_png(metal_rough_path, np.clip(metal_rough_rgb, 0.0, 1.0))
    written_files = [base_color_path.name, normal_path.name, metal_rough_path.name]

    if ao_rgb is not None:
        _save_rgb_png(ao_path, ao_rgb)
        written_files.append(ao_path.name)
    if emissive_rgb is not None:
        _save_rgb_png(emissive_path, emissive_rgb)
        written_files.append(emissive_path.name)

    positions, normals, uvs, indices = _build_preview_mesh(preview_mesh, uv_scale=uv_scale)

    binary = bytearray()
    buffer_views: List[Dict[str, object]] = []
    accessors: List[Dict[str, object]] = []

    for array, component_type, accessor_type, target in (
        (positions, 5126, "VEC3", 34962),
        (normals, 5126, "VEC3", 34962),
        (uvs, 5126, "VEC2", 34962),
        (indices, 5123, "SCALAR", 34963),
    ):
        buffer_view, accessor = _pack_accessor(binary, array, component_type, accessor_type, target)
        accessor["bufferView"] = len(buffer_views)
        buffer_views.append(buffer_view)
        accessors.append(accessor)

    buffer_uri = "data:application/octet-stream;base64," + base64.b64encode(bytes(binary)).decode("ascii")

    images = [
        {"uri": base_color_path.name},
        {"uri": normal_path.name},
        {"uri": metal_rough_path.name},
    ]
    textures = [
        {"sampler": 0, "source": 0},
        {"sampler": 0, "source": 1},
        {"sampler": 0, "source": 2},
    ]

    ao_texture_index: Optional[int] = None
    emissive_texture_index: Optional[int] = None

    if ao_rgb is not None:
        ao_texture_index = len(textures)
        images.append({"uri": ao_path.name})
        textures.append({"sampler": 0, "source": len(images) - 1})
    if emissive_rgb is not None:
        emissive_texture_index = len(textures)
        images.append({"uri": emissive_path.name})
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
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
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
        "buffers": [{"byteLength": len(binary), "uri": buffer_uri}],
    }

    gltf_path.write_text(json.dumps(gltf, indent=2), encoding="utf-8")

    model_relative = f"{DEFAULT_SUBFOLDER}/{gltf_path.name}[output]"
    info = (
        "x1PreviewMaterial: label={}, mesh={}, uv_scale={:.2f}, size={}x{}, alpha_mode={}, "
        "used_maps={}, notes={}, files={}"
    ).format(
        label,
        str(preview_mesh or "shader_ball").lower(),
        float(max(0.01, uv_scale)),
        int(width),
        int(height_px),
        resolved_alpha_mode.lower(),
        ",".join(used_maps) if used_maps else "defaults_only",
        ",".join(notes) if notes else "none",
        ",".join(written_files),
    )
    return {
        "model_file": model_relative,
        "info": info,
        "gltf_path": str(gltf_path),
        "written_files": written_files,
    }
