import math
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw


def _mesh_bounds_from_tris(tris: Sequence[float]) -> Dict[str, float]:
    if not tris:
        return {
            "min_x": 0.0,
            "max_x": 0.0,
            "min_y": 0.0,
            "max_y": 0.0,
            "min_z": 0.0,
            "max_z": 0.0,
        }
    arr = np.asarray(list(tris), dtype=np.float32).reshape(-1, 3)
    mins = arr.min(axis=0)
    maxs = arr.max(axis=0)
    return {
        "min_x": float(mins[0]),
        "max_x": float(maxs[0]),
        "min_y": float(mins[1]),
        "max_y": float(maxs[1]),
        "min_z": float(mins[2]),
        "max_z": float(maxs[2]),
    }


def _mesh_from_tris(
    tris: Sequence[float],
    *,
    source_path: str = "",
    source_format: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    tri_list = [float(v) for v in tris]
    bounds = _mesh_bounds_from_tris(tri_list)
    payload_meta = dict(meta or {})
    if source_path:
        payload_meta["source_path"] = str(source_path)
    if source_format:
        payload_meta["source_format"] = str(source_format)
    return {
        "schema": "mkr_gcode_mesh_v1",
        "format": "tris",
        "tris": tri_list,
        "tri_count": int(len(tri_list) // 9),
        "bounds": bounds,
        "meta": payload_meta,
    }


def _parse_ascii_stl_text(text: str) -> List[float]:
    tris: List[float] = []
    tri_vertices: List[Tuple[float, float, float]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("vertex"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            tri_vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        except Exception:
            continue
        if len(tri_vertices) == 3:
            for vx, vy, vz in tri_vertices:
                tris.extend((vx, vy, vz))
            tri_vertices = []
    return tris


def _parse_binary_stl_bytes(data: bytes) -> Optional[List[float]]:
    if len(data) < 84:
        return None
    try:
        tri_count = struct.unpack_from("<I", data, 80)[0]
    except struct.error:
        return None
    expected = 84 + (tri_count * 50)
    if expected != len(data):
        return None
    tris: List[float] = []
    offset = 84
    for _ in range(int(tri_count)):
        if offset + 50 > len(data):
            return None
        try:
            ax, ay, az, bx, by, bz, cx, cy, cz = struct.unpack_from("<fffffffff", data, offset + 12)
        except struct.error:
            return None
        tris.extend((ax, ay, az, bx, by, bz, cx, cy, cz))
        offset += 50
    return tris


def _parse_stl_bytes(data: bytes) -> List[float]:
    binary = _parse_binary_stl_bytes(data)
    if binary is not None:
        return binary
    try:
        return _parse_ascii_stl_text(data.decode("utf-8", errors="ignore"))
    except Exception:
        return []


def _parse_obj_text(text: str) -> List[float]:
    vertices: List[Tuple[float, float, float]] = []
    tris: List[float] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0].lower()
        if head == "v" and len(parts) >= 4:
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except Exception:
                continue
            continue
        if head != "f" or len(parts) < 4:
            continue
        face_indices: List[int] = []
        for token in parts[1:]:
            base = token.split("/", 1)[0]
            if not base:
                continue
            try:
                idx = int(base)
            except Exception:
                continue
            if idx < 0:
                idx = len(vertices) + idx
            else:
                idx = idx - 1
            if 0 <= idx < len(vertices):
                face_indices.append(idx)
        if len(face_indices) < 3:
            continue
        root = face_indices[0]
        for i in range(1, len(face_indices) - 1):
            tri = (root, face_indices[i], face_indices[i + 1])
            for vidx in tri:
                vx, vy, vz = vertices[vidx]
                tris.extend((vx, vy, vz))
    return tris


def _load_mesh_file(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".stl":
        tris = _parse_stl_bytes(data)
        fmt = "stl"
    elif suffix == ".obj":
        tris = _parse_obj_text(data.decode("utf-8", errors="ignore"))
        fmt = "obj"
    else:
        raise ValueError(f"Unsupported mesh format '{path.suffix}'")
    if len(tris) < 9:
        raise ValueError("Mesh file does not contain any triangles")
    return _mesh_from_tris(tris, source_path=str(path), source_format=fmt)


def _mesh_vertices(mesh: Dict[str, Any]) -> np.ndarray:
    tris = mesh.get("tris", []) if isinstance(mesh, dict) else []
    if not isinstance(tris, list) or len(tris) < 9:
        return np.zeros((0, 3), dtype=np.float32)
    return np.asarray(tris, dtype=np.float32).reshape(-1, 3)


def _center_mesh_xy(mesh: Dict[str, Any]) -> Dict[str, Any]:
    verts = _mesh_vertices(mesh)
    if verts.size == 0:
        return dict(mesh)
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    center_x = (mins[0] + maxs[0]) * 0.5
    center_y = (mins[1] + maxs[1]) * 0.5
    verts[:, 0] -= center_x
    verts[:, 1] -= center_y
    return _mesh_from_tris(
        verts.reshape(-1).tolist(),
        meta={**dict(mesh.get("meta", {})), "centered_xy": True},
        source_path=str(mesh.get("meta", {}).get("source_path", "")),
        source_format=str(mesh.get("meta", {}).get("source_format", "")),
    )


def _bed_align_mesh(mesh: Dict[str, Any]) -> Dict[str, Any]:
    verts = _mesh_vertices(mesh)
    if verts.size == 0:
        return dict(mesh)
    min_z = float(verts[:, 2].min())
    verts[:, 2] -= min_z
    return _mesh_from_tris(
        verts.reshape(-1).tolist(),
        meta={**dict(mesh.get("meta", {})), "bed_aligned": True},
        source_path=str(mesh.get("meta", {}).get("source_path", "")),
        source_format=str(mesh.get("meta", {}).get("source_format", "")),
    )


def _transform_mesh(
    mesh: Dict[str, Any],
    *,
    scale: float = 1.0,
    rotate_x_deg: float = 0.0,
    rotate_y_deg: float = 0.0,
    rotate_z_deg: float = 0.0,
    translate_x_mm: float = 0.0,
    translate_y_mm: float = 0.0,
    translate_z_mm: float = 0.0,
) -> Dict[str, Any]:
    verts = _mesh_vertices(mesh)
    if verts.size == 0:
        return dict(mesh)
    s = float(scale)
    verts *= s

    rx = math.radians(float(rotate_x_deg))
    ry = math.radians(float(rotate_y_deg))
    rz = math.radians(float(rotate_z_deg))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    rx_m = np.asarray(((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx)), dtype=np.float32)
    ry_m = np.asarray(((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy)), dtype=np.float32)
    rz_m = np.asarray(((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0)), dtype=np.float32)
    rot = rz_m @ ry_m @ rx_m
    verts = verts @ rot.T
    verts[:, 0] += float(translate_x_mm)
    verts[:, 1] += float(translate_y_mm)
    verts[:, 2] += float(translate_z_mm)

    meta = dict(mesh.get("meta", {}))
    meta["transform"] = {
        "scale": float(scale),
        "rotate_x_deg": float(rotate_x_deg),
        "rotate_y_deg": float(rotate_y_deg),
        "rotate_z_deg": float(rotate_z_deg),
        "translate_x_mm": float(translate_x_mm),
        "translate_y_mm": float(translate_y_mm),
        "translate_z_mm": float(translate_z_mm),
    }
    return _mesh_from_tris(
        verts.reshape(-1).tolist(),
        meta=meta,
        source_path=str(mesh.get("meta", {}).get("source_path", "")),
        source_format=str(mesh.get("meta", {}).get("source_format", "")),
    )


def _mesh_edges(verts: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray]]:
    edges: List[Tuple[np.ndarray, np.ndarray]] = []
    for i in range(0, len(verts), 3):
        tri = verts[i : i + 3]
        if len(tri) < 3:
            continue
        edges.append((tri[0], tri[1]))
        edges.append((tri[1], tri[2]))
        edges.append((tri[2], tri[0]))
    return edges


def _project_mesh_vertices(verts: np.ndarray, view_mode: str) -> Tuple[np.ndarray, np.ndarray]:
    if verts.size == 0:
        return np.zeros((0, 2), dtype=np.float32), np.zeros((0,), dtype=np.float32)
    mode = str(view_mode or "isometric").strip().lower()
    work = verts.copy()
    if mode in {"top", "mesh_top"}:
        proj = np.stack((work[:, 0], -work[:, 1]), axis=1)
        depth = work[:, 2]
        return proj, depth
    if mode in {"front"}:
        proj = np.stack((work[:, 0], -work[:, 2]), axis=1)
        depth = work[:, 1]
        return proj, depth
    rx = math.radians(35.264)
    rz = math.radians(45.0)
    cx, sx = math.cos(rx), math.sin(rx)
    cz, sz = math.cos(rz), math.sin(rz)
    rx_m = np.asarray(((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx)), dtype=np.float32)
    rz_m = np.asarray(((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0)), dtype=np.float32)
    rot = rz_m @ rx_m
    work = work @ rot.T
    proj = np.stack((work[:, 0], -work[:, 1]), axis=1)
    depth = work[:, 2]
    return proj, depth


def _render_mesh_preview(mesh: Dict[str, Any], size: int = 768, view_mode: str = "isometric") -> Image.Image:
    canvas = Image.new("RGB", (size, size), (15, 18, 24))
    draw = ImageDraw.Draw(canvas)
    verts = _mesh_vertices(mesh)
    if verts.size == 0:
        draw.text((24, 24), "No mesh", fill=(220, 220, 220))
        return canvas
    projected, depth = _project_mesh_vertices(verts, view_mode)
    min_xy = projected.min(axis=0)
    max_xy = projected.max(axis=0)
    span = np.maximum(max_xy - min_xy, 1e-6)
    margin = 48.0
    scale = min((size - margin * 2.0) / float(span[0]), (size - margin * 2.0) / float(span[1]))
    projected = (projected - min_xy) * scale
    projected[:, 0] += margin
    projected[:, 1] += margin

    edge_tris = []
    for i in range(0, len(projected), 3):
        tri = projected[i : i + 3]
        tri_depth = float(depth[i : i + 3].mean()) if i + 3 <= len(depth) else 0.0
        edge_tris.append((tri_depth, tri))
    edge_tris.sort(key=lambda item: item[0])
    dmin = float(depth.min())
    dmax = float(depth.max())
    drange = max(1e-6, dmax - dmin)
    for tri_depth, tri in edge_tris:
        t = (tri_depth - dmin) / drange
        color = (
            int(72 + (84 * t)),
            int(122 + (92 * t)),
            int(180 + (60 * t)),
        )
        pts = [tuple(map(float, tri[j])) for j in range(3)]
        draw.line((pts[0], pts[1]), fill=color, width=1)
        draw.line((pts[1], pts[2]), fill=color, width=1)
        draw.line((pts[2], pts[0]), fill=color, width=1)
    draw.rectangle((12, 12, size - 12, size - 12), outline=(66, 104, 145), width=2)
    return canvas


def _mesh_to_ascii_stl(mesh: Dict[str, Any], name: str = "mesh") -> str:
    tris = mesh.get("tris", []) if isinstance(mesh, dict) else []
    lines = [f"solid {name}"]
    for i in range(0, len(tris), 9):
        ax, ay, az, bx, by, bz, cx, cy, cz = [float(v) for v in tris[i : i + 9]]
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        lines.append(f"      vertex {ax} {ay} {az}")
        lines.append(f"      vertex {bx} {by} {bz}")
        lines.append(f"      vertex {cx} {cy} {cz}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    return "\n".join(lines)


__all__ = [
    "_bed_align_mesh",
    "_center_mesh_xy",
    "_load_mesh_file",
    "_mesh_bounds_from_tris",
    "_mesh_from_tris",
    "_mesh_to_ascii_stl",
    "_render_mesh_preview",
    "_transform_mesh",
]
