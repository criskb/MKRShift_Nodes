import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw
import torch


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _parse_json_text(text: Any, fallback: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    raw = str(text or "").strip()
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return float(max(minimum, min(maximum, float(value))))


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


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


def _pil_to_batch(images: Sequence[Image.Image]) -> torch.Tensor:
    if not images:
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    arr = np.stack([np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0 for img in images], axis=0)
    return torch.from_numpy(arr.astype(np.float32, copy=False))


def _first_pil(image: torch.Tensor) -> Image.Image:
    batch = _to_image_batch(image)
    arr = np.clip(batch[0, ..., :3].cpu().numpy(), 0.0, 1.0)
    return Image.fromarray(np.round(arr * 255.0).astype(np.uint8), mode="RGB")


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(fallback)


def _normalize_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = profile if isinstance(profile, dict) else {}
    line_width = max(0.1, _float(raw.get("lineWidth", 0.45), 0.45))
    layer_height = max(0.05, _float(raw.get("layerHeight", 0.2), 0.2))
    nozzle = max(0.1, _float(raw.get("nozzle", 0.4), 0.4))
    bed_w = max(50.0, _float(raw.get("bedW", 220.0), 220.0))
    bed_d = max(50.0, _float(raw.get("bedD", 220.0), 220.0))
    bed_h = max(50.0, _float(raw.get("bedH", 250.0), 250.0))
    filament_dia = max(1.0, _float(raw.get("filamentDia", 1.75), 1.75))
    extrusion_mult = max(0.1, _float(raw.get("extrusionMult", 1.0), 1.0))
    speed_print = max(1.0, _float(raw.get("speedPrint", 1800.0), 1800.0))
    speed_travel = max(1.0, _float(raw.get("speedTravel", 6000.0), 6000.0))
    return {
        "name": str(raw.get("name", "Generic FDM") or "Generic FDM"),
        "bedW": float(bed_w),
        "bedD": float(bed_d),
        "bedH": float(bed_h),
        "origin": str(raw.get("origin", "center") or "center"),
        "offsetX": float(_float(raw.get("offsetX", 0.0), 0.0)),
        "offsetY": float(_float(raw.get("offsetY", 0.0), 0.0)),
        "travelZ": float(max(0.1, _float(raw.get("travelZ", 0.6), 0.6))),
        "nozzle": float(nozzle),
        "lineWidth": float(line_width),
        "layerHeight": float(layer_height),
        "filamentDia": float(filament_dia),
        "extrusionMult": float(extrusion_mult),
        "tempNozzle": int(max(0, _int(raw.get("tempNozzle", 210), 210))),
        "tempBed": int(max(0, _int(raw.get("tempBed", 60), 60))),
        "speedPrint": float(speed_print),
        "speedTravel": float(speed_travel),
        "retractionMm": float(max(0.0, _float(raw.get("retractionMm", 0.8), 0.8))),
        "retractionSpeed": float(max(1.0, _float(raw.get("retractionSpeed", 35.0), 35.0))),
        "primeLine": bool(raw.get("primeLine", True)),
        "homeBeforePrint": bool(raw.get("homeBeforePrint", True)),
        "startGcode": str(raw.get("startGcode", "") or ""),
        "endGcode": str(raw.get("endGcode", "") or ""),
        "schema": "mkr_gcode_profile_v1",
    }


def _resolve_plan_settings(
    profile: Optional[Dict[str, Any]],
    use_profile_defaults: bool,
    layer_height_mm: float,
    line_width_mm: float,
    print_speed_mm_s: float,
    travel_speed_mm_s: float,
) -> Tuple[float, float, float, float]:
    p = _normalize_profile(profile)
    if not bool(use_profile_defaults) or not isinstance(profile, dict):
        return (
            float(max(0.05, layer_height_mm)),
            float(max(0.1, line_width_mm)),
            float(max(1.0, print_speed_mm_s)),
            float(max(1.0, travel_speed_mm_s)),
        )
    return (
        float(max(0.05, _float(p.get("layerHeight", layer_height_mm), layer_height_mm))),
        float(max(0.1, _float(p.get("lineWidth", line_width_mm), line_width_mm))),
        float(max(1.0, _float(p.get("speedPrint", print_speed_mm_s * 60.0), print_speed_mm_s * 60.0) / 60.0)),
        float(max(1.0, _float(p.get("speedTravel", travel_speed_mm_s * 60.0), travel_speed_mm_s * 60.0) / 60.0)),
    )


def _contiguous_true_runs(flags: Sequence[bool]) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for idx, flag in enumerate(flags):
        if flag and start is None:
            start = idx
        elif (not flag) and start is not None:
            runs.append((start, idx - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def _append_move(
    moves: List[Dict[str, Any]],
    x: float,
    y: float,
    z: float,
    *,
    extrude: bool,
    role: str,
    line_width: float,
    layer_height: float,
    speed_mm_s: float,
    layer: int,
    comment: str = "",
) -> None:
    moves.append(
        {
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "extrude": bool(extrude),
            "role": str(role),
            "line_width": float(max(0.1, line_width)),
            "layer_height": float(max(0.01, layer_height)),
            "speed_mm_s": float(max(0.1, speed_mm_s)),
            "layer": int(max(0, layer)),
            "comment": str(comment or ""),
        }
    )


def _plan_bounds(moves: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    if not moves:
        return {"min_x": 0.0, "max_x": 0.0, "min_y": 0.0, "max_y": 0.0, "min_z": 0.0, "max_z": 0.0}
    xs = [float(m.get("x", 0.0)) for m in moves]
    ys = [float(m.get("y", 0.0)) for m in moves]
    zs = [float(m.get("z", 0.0)) for m in moves]
    return {
        "min_x": float(min(xs)),
        "max_x": float(max(xs)),
        "min_y": float(min(ys)),
        "max_y": float(max(ys)),
        "min_z": float(min(zs)),
        "max_z": float(max(zs)),
    }


def _distance_mm(prev: Dict[str, Any], cur: Dict[str, Any]) -> float:
    dx = float(cur.get("x", 0.0)) - float(prev.get("x", 0.0))
    dy = float(cur.get("y", 0.0)) - float(prev.get("y", 0.0))
    dz = float(cur.get("z", 0.0)) - float(prev.get("z", 0.0))
    return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def _plan_stats(moves: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if len(moves) < 2:
        return {
            "move_count": int(len(moves)),
            "print_moves": 0,
            "travel_moves": 0,
            "path_length_mm": 0.0,
            "print_length_mm": 0.0,
            "travel_length_mm": 0.0,
            "estimated_time_min": 0.0,
            "layer_count": 0,
        }
    print_moves = 0
    travel_moves = 0
    path_length = 0.0
    print_length = 0.0
    travel_length = 0.0
    time_s = 0.0
    seen_layers = set()
    for idx in range(1, len(moves)):
        prev = moves[idx - 1]
        cur = moves[idx]
        seen_layers.add(int(cur.get("layer", 0)))
        dist = _distance_mm(prev, cur)
        speed = float(max(0.1, cur.get("speed_mm_s", 1.0)))
        path_length += dist
        time_s += dist / speed
        if bool(cur.get("extrude", False)):
            print_moves += 1
            print_length += dist
        else:
            travel_moves += 1
            travel_length += dist
    return {
        "move_count": int(len(moves)),
        "print_moves": int(print_moves),
        "travel_moves": int(travel_moves),
        "path_length_mm": float(round(path_length, 3)),
        "print_length_mm": float(round(print_length, 3)),
        "travel_length_mm": float(round(travel_length, 3)),
        "estimated_time_min": float(round(time_s / 60.0, 3)),
        "layer_count": int(len(seen_layers)),
    }


def _layer_summaries(moves: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    layers: Dict[int, Dict[str, Any]] = {}
    if moves:
        first_layer = int(moves[0].get("layer", 0))
        first_z = float(moves[0].get("z", 0.0))
        layers[first_layer] = {
            "layer": first_layer,
            "z_min": first_z,
            "z_max": first_z,
            "path_length_mm": 0.0,
            "print_length_mm": 0.0,
            "travel_length_mm": 0.0,
            "estimated_time_s": 0.0,
            "print_moves": 0,
            "travel_moves": 0,
        }
    for idx in range(1, len(moves)):
        prev = moves[idx - 1]
        cur = moves[idx]
        layer = int(cur.get("layer", 0))
        z = float(cur.get("z", 0.0))
        entry = layers.setdefault(
            layer,
            {
                "layer": layer,
                "z_min": z,
                "z_max": z,
                "path_length_mm": 0.0,
                "print_length_mm": 0.0,
                "travel_length_mm": 0.0,
                "estimated_time_s": 0.0,
                "print_moves": 0,
                "travel_moves": 0,
            },
        )
        dist = _distance_mm(prev, cur)
        speed = float(max(0.1, cur.get("speed_mm_s", 1.0)))
        entry["z_min"] = min(float(entry["z_min"]), z)
        entry["z_max"] = max(float(entry["z_max"]), z)
        entry["path_length_mm"] += dist
        entry["estimated_time_s"] += dist / speed
        if bool(cur.get("extrude", False)):
            entry["print_moves"] += 1
            entry["print_length_mm"] += dist
        else:
            entry["travel_moves"] += 1
            entry["travel_length_mm"] += dist
    ordered: List[Dict[str, Any]] = []
    for layer in sorted(layers):
        entry = dict(layers[layer])
        for key in ("z_min", "z_max", "path_length_mm", "print_length_mm", "travel_length_mm", "estimated_time_s"):
            entry[key] = float(round(float(entry[key]), 5))
        ordered.append(entry)
    return ordered


def _render_plan_preview(plan: Dict[str, Any], size: int = 768) -> Image.Image:
    moves = plan.get("moves", []) if isinstance(plan, dict) else []
    bounds = plan.get("bounds", {}) if isinstance(plan, dict) else {}
    canvas = Image.new("RGB", (size, size), (18, 19, 22))
    draw = ImageDraw.Draw(canvas)
    min_x = float(bounds.get("min_x", 0.0))
    max_x = float(bounds.get("max_x", 1.0))
    min_y = float(bounds.get("min_y", 0.0))
    max_y = float(bounds.get("max_y", 1.0))
    w = max(1e-6, max_x - min_x)
    h = max(1e-6, max_y - min_y)
    margin = 36.0
    scale = min((size - margin * 2.0) / w, (size - margin * 2.0) / h)

    def tx(x: float) -> float:
        return margin + (x - min_x) * scale

    def ty(y: float) -> float:
        return size - margin - (y - min_y) * scale

    role_colors = {
        "base": (122, 214, 255),
        "relief": (210, 253, 81),
        "wall": (255, 103, 56),
        "travel": (88, 96, 107),
    }
    for idx in range(1, len(moves)):
        prev = moves[idx - 1]
        cur = moves[idx]
        if bool(cur.get("extrude", False)):
            role = str(cur.get("role", "relief"))
            color = role_colors.get(role, (210, 253, 81))
            width = 2
        else:
            color = role_colors["travel"]
            width = 1
        draw.line(
            (
                tx(float(prev.get("x", 0.0))),
                ty(float(prev.get("y", 0.0))),
                tx(float(cur.get("x", 0.0))),
                ty(float(cur.get("y", 0.0))),
            ),
            fill=color,
            width=width,
        )
    draw.rectangle((12, 12, size - 12, size - 12), outline=(61, 110, 163), width=2)
    return canvas


def _make_plan(mode: str, moves: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    bounds = _plan_bounds(moves)
    stats = _plan_stats(moves)
    return {
        "schema": "mkr_gcode_plan_v1",
        "mode": str(mode),
        "units": "mm",
        "moves": moves,
        "bounds": bounds,
        "stats": stats,
        "meta": dict(meta),
    }


def _clone_plan(
    plan: Optional[Dict[str, Any]],
    moves: Sequence[Dict[str, Any]],
    *,
    meta_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source = plan if isinstance(plan, dict) else {}
    meta = dict(source.get("meta", {})) if isinstance(source.get("meta"), dict) else {}
    if isinstance(meta_updates, dict):
        meta.update(meta_updates)
    cloned = _make_plan(str(source.get("mode", "unknown") or "unknown"), list(moves), meta)
    for key, value in source.items():
        if key in cloned or key in {"moves", "bounds", "stats", "meta"}:
            continue
        cloned[key] = value
    return cloned


def _filament_area(profile: Dict[str, Any]) -> float:
    dia = max(0.1, _float(profile.get("filamentDia", 1.75), 1.75))
    return float(math.pi * math.pow(dia / 2.0, 2.0))


def _estimate_material_usage(
    plan: Dict[str, Any],
    profile: Optional[Dict[str, Any]],
    density_g_cm3: float = 1.24,
) -> Dict[str, Any]:
    p = _normalize_profile(profile)
    moves = plan.get("moves", []) if isinstance(plan, dict) else []
    extrusion_mult = float(p.get("extrusionMult", 1.0) or 1.0)
    volume_mm3 = 0.0
    for idx in range(1, len(moves)):
        prev = moves[idx - 1]
        cur = moves[idx]
        if not bool(cur.get("extrude", False)):
            continue
        dist = _distance_mm(prev, cur)
        line_width = float(max(0.1, cur.get("line_width", p.get("lineWidth", 0.45))))
        layer_height = float(max(0.01, cur.get("layer_height", p.get("layerHeight", 0.2))))
        volume_mm3 += dist * line_width * layer_height * extrusion_mult
    volume_cm3 = volume_mm3 / 1000.0
    mass_g = volume_cm3 * max(0.1, float(density_g_cm3))
    filament_length_mm = volume_mm3 / max(1e-9, _filament_area(p))
    return {
        "volume_mm3": float(round(volume_mm3, 5)),
        "volume_cm3": float(round(volume_cm3, 5)),
        "filament_length_mm": float(round(filament_length_mm, 5)),
        "mass_g": float(round(mass_g, 5)),
        "density_g_cm3": float(round(max(0.1, float(density_g_cm3)), 5)),
    }


def _profile_start_gcode(profile: Dict[str, Any]) -> List[str]:
    lines = [line.rstrip() for line in str(profile.get("startGcode", "") or "").splitlines() if line.strip()]
    if lines:
        return lines
    out: List[str] = []
    out.append(f"M104 S{int(profile.get('tempNozzle', 210) or 210)}")
    out.append(f"M140 S{int(profile.get('tempBed', 60) or 60)}")
    if bool(profile.get("homeBeforePrint", True)):
        out.append("G28")
    out.append(f"M109 S{int(profile.get('tempNozzle', 210) or 210)}")
    out.append(f"M190 S{int(profile.get('tempBed', 60) or 60)}")
    out.append("G92 E0")
    return out


def _profile_end_gcode(profile: Dict[str, Any]) -> List[str]:
    lines = [line.rstrip() for line in str(profile.get("endGcode", "") or "").splitlines() if line.strip()]
    if lines:
        return lines
    return ["M104 S0", "M140 S0", "G28 X0", "M84"]


def _plan_offset(plan: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[float, float]:
    bounds = plan.get("bounds", {}) if isinstance(plan, dict) else {}
    min_x = float(bounds.get("min_x", 0.0))
    max_x = float(bounds.get("max_x", 0.0))
    min_y = float(bounds.get("min_y", 0.0))
    max_y = float(bounds.get("max_y", 0.0))
    span_x = max_x - min_x
    span_y = max_y - min_y
    bed_w = float(profile.get("bedW", 220.0) or 220.0)
    bed_d = float(profile.get("bedD", 220.0) or 220.0)
    offset_x = float(profile.get("offsetX", 0.0) or 0.0)
    offset_y = float(profile.get("offsetY", 0.0) or 0.0)
    origin = str(profile.get("origin", "center") or "center").strip().lower()
    if origin == "center":
        return (
            (bed_w * 0.5) - (min_x + span_x * 0.5) + offset_x,
            (bed_d * 0.5) - (min_y + span_y * 0.5) + offset_y,
        )
    return (offset_x - min_x + 5.0, offset_y - min_y + 5.0)


def _bed_fit_report(plan: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    p = _normalize_profile(profile)
    bounds = plan.get("bounds", {}) if isinstance(plan, dict) else {}
    offset_x, offset_y = _plan_offset(plan, p)
    placed_min_x = float(bounds.get("min_x", 0.0)) + offset_x
    placed_max_x = float(bounds.get("max_x", 0.0)) + offset_x
    placed_min_y = float(bounds.get("min_y", 0.0)) + offset_y
    placed_max_y = float(bounds.get("max_y", 0.0)) + offset_y
    placed_max_z = float(bounds.get("max_z", 0.0))
    return {
        "bed_width_mm": float(p.get("bedW", 220.0)),
        "bed_depth_mm": float(p.get("bedD", 220.0)),
        "bed_height_mm": float(p.get("bedH", 250.0)),
        "placed_bounds_mm": {
            "min_x": float(round(placed_min_x, 5)),
            "max_x": float(round(placed_max_x, 5)),
            "min_y": float(round(placed_min_y, 5)),
            "max_y": float(round(placed_max_y, 5)),
            "max_z": float(round(placed_max_z, 5)),
        },
        "fits_xy": bool(placed_min_x >= 0.0 and placed_max_x <= float(p.get("bedW", 220.0)) and placed_min_y >= 0.0 and placed_max_y <= float(p.get("bedD", 220.0))),
        "fits_z": bool(placed_max_z <= float(p.get("bedH", 250.0))),
    }


def _build_gcode(plan: Dict[str, Any], profile: Dict[str, Any], include_comments: bool = True) -> Tuple[str, Dict[str, Any]]:
    moves = plan.get("moves", []) if isinstance(plan, dict) else []
    if not isinstance(moves, list) or len(moves) < 2:
        return "", {"line_count": 0, "extrusion_mm": 0.0, "estimated_time_min": 0.0}

    p = _normalize_profile(profile)
    filament_area = _filament_area(p)
    offset_x, offset_y = _plan_offset(plan, p)

    lines: List[str] = []
    lines.append("; MKRShift Nodes G-code")
    lines.append(f"; Plan mode: {plan.get('mode', 'unknown')}")
    lines.append(f"; Printer: {p.get('name', 'Generic FDM')}")
    lines.append("G21")
    lines.append("G90")
    lines.append("M82")
    lines.extend(_profile_start_gcode(p))

    if bool(p.get("primeLine", True)):
        prime_x = 5.0
        prime_y = 5.0
        prime_len = 40.0
        lines.append(f"G0 X{prime_x:.3f} Y{prime_y:.3f} Z{max(0.2, float(p.get('layerHeight', 0.2))):.3f} F{float(p.get('speedTravel', 6000.0)):.0f}")
        lines.append("G92 E0")
        lines.append(f"G1 X{prime_x + prime_len:.3f} Y{prime_y:.3f} E2.000 F{float(p.get('speedPrint', 1800.0)):.0f}")
        lines.append("G92 E0")

    e_abs = 0.0
    last_layer: Optional[int] = None
    extrusion_mult = float(p.get("extrusionMult", 1.0) or 1.0)
    time_s = 0.0

    for idx in range(1, len(moves)):
        prev = moves[idx - 1]
        cur = moves[idx]
        layer = int(cur.get("layer", 0) or 0)
        if include_comments and layer != last_layer:
            lines.append(f"; LAYER:{layer}")
            last_layer = layer
        comment = str(cur.get("comment", "") or "").strip()
        if include_comments and comment:
            lines.append(f"; {comment}")

        x = float(cur.get("x", 0.0)) + offset_x
        y = float(cur.get("y", 0.0)) + offset_y
        z = float(cur.get("z", 0.0))
        dist = _distance_mm(prev, cur)
        speed_mm_s = float(max(0.1, cur.get("speed_mm_s", 1.0)))
        time_s += dist / speed_mm_s
        feed_mm_min = speed_mm_s * 60.0
        if bool(cur.get("extrude", False)):
            line_width = float(max(0.1, cur.get("line_width", p.get("lineWidth", 0.45))))
            layer_height = float(max(0.01, cur.get("layer_height", p.get("layerHeight", 0.2))))
            volume = dist * line_width * layer_height * extrusion_mult
            e_abs += float(volume / max(1e-9, filament_area))
            lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} E{e_abs:.5f} F{feed_mm_min:.0f}")
        else:
            lines.append(f"G0 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feed_mm_min:.0f}")

    lines.extend(_profile_end_gcode(p))
    return "\n".join(lines) + "\n", {
        "line_count": int(len(lines)),
        "extrusion_mm": float(round(e_abs, 5)),
        "estimated_time_min": float(round(time_s / 60.0, 3)),
    }


__all__ = [
    "_append_move",
    "_bed_fit_report",
    "_build_gcode",
    "_clamp",
    "_clamp01",
    "_clone_plan",
    "_contiguous_true_runs",
    "_distance_mm",
    "_estimate_material_usage",
    "_first_pil",
    "_float",
    "_int",
    "_json_text",
    "_layer_summaries",
    "_make_plan",
    "_normalize_profile",
    "_parse_json_text",
    "_pil_to_batch",
    "_plan_bounds",
    "_plan_offset",
    "_plan_stats",
    "_render_plan_preview",
    "_resolve_plan_settings",
    "_to_image_batch",
]
