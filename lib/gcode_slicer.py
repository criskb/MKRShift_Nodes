import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .gcode_shared import _append_move, _make_plan, _normalize_profile


def _safe_json_parse(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_slicer_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if any(isinstance(item, (list, dict, tuple)) for item in value):
            return None
        return ",".join(str(item) for item in value)
    if isinstance(value, dict):
        return None
    text = str(value)
    return text.replace("\r\n", "\n").replace("\n", "\\n")


def _printable_area_bounds(area: Any) -> Optional[Dict[str, float]]:
    if not isinstance(area, list) or len(area) < 3:
        return None
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for point in area:
        if not isinstance(point, list) or len(point) < 2:
            continue
        try:
            x = float(point[0])
            y = float(point[1])
        except Exception:
            continue
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
    if not all(v not in {float("inf"), float("-inf")} for v in (min_x, min_y, max_x, max_y)):
        return None
    return {"w": max_x - min_x, "d": max_y - min_y, "min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}


def _orca_type(obj: Any) -> str:
    if not isinstance(obj, dict):
        return "unknown"
    type_hint = str(obj.get("type", obj.get("profile_type", obj.get("preset_type", ""))) or "").lower()
    if "filament" in type_hint:
        return "filament"
    if "process" in type_hint:
        return "process"
    if "machine" in type_hint or "printer" in type_hint:
        return "machine"
    if any(key in obj for key in ("filament_diameter", "filament_dia", "filament_type")):
        return "filament"
    if any(key in obj for key in ("infill_density", "layer_height", "perimeter_speed")):
        return "process"
    if any(key in obj for key in ("nozzle_diameter", "printable_area", "machine_start_gcode")):
        return "machine"
    return "unknown"


def _orca_entry(obj: Dict[str, Any], id_hint: str) -> Dict[str, Any]:
    entry_id = str(obj.get("id", obj.get("internal_id", obj.get("uuid", id_hint))) or id_hint)
    name = str(obj.get("name", obj.get("preset_name", obj.get("display_name", entry_id))) or entry_id)
    return {"id": entry_id, "name": name, "type": _orca_type(obj), "obj": obj}


def _load_orca_profiles(source_path: str, recursive: bool = True) -> Dict[str, Any]:
    store = {"printers": [], "filaments": [], "processes": [], "files": {}}
    path = Path(source_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Orca profile source not found: {path}")

    def consume(name: str, text: str) -> None:
        obj = _safe_json_parse(text)
        if not isinstance(obj, dict):
            return
        entry = _orca_entry(obj, name)
        bucket_key = {"machine": "printers", "filament": "filaments", "process": "processes"}.get(entry["type"], "")
        if not bucket_key:
            return
        bucket = store[bucket_key]
        for idx, existing in enumerate(bucket):
            if existing["id"] == entry["id"]:
                bucket[idx] = entry
                break
        else:
            bucket.append(entry)
        store["files"][name] = text

    def iter_paths(root: Path) -> Iterable[Path]:
        if root.is_file():
            yield root
            return
        pattern = "**/*" if recursive else "*"
        for candidate in root.glob(pattern):
            if candidate.is_file():
                yield candidate

    for candidate in iter_paths(path):
        suffix = candidate.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(candidate, "r") as archive:
                for member in archive.namelist():
                    low = member.lower()
                    if not low.endswith((".json", ".orca_printer", ".orca_filament", ".orca_process")):
                        continue
                    try:
                        consume(member, archive.read(member).decode("utf-8", errors="ignore"))
                    except Exception:
                        continue
            continue
        if suffix not in {".json", ".orca_printer", ".orca_filament", ".orca_process"}:
            continue
        consume(candidate.name, candidate.read_text(encoding="utf-8", errors="ignore"))
    return store


def _select_orca_entry(entries: Sequence[Dict[str, Any]], match: str, selection_mode: str) -> Optional[Dict[str, Any]]:
    if not entries:
        return None
    query = str(match or "").strip()
    mode = str(selection_mode or "auto").strip().lower()
    if not query:
        return entries[0]

    def exact(entry: Dict[str, Any]) -> bool:
        return query == str(entry.get("id", "")) or query == str(entry.get("name", ""))

    def contains(entry: Dict[str, Any]) -> bool:
        q = query.lower()
        return q in str(entry.get("id", "")).lower() or q in str(entry.get("name", "")).lower()

    if mode in {"id_or_name_exact", "exact"}:
        for entry in entries:
            if exact(entry):
                return entry
        return None
    if mode in {"substring", "contains"}:
        for entry in entries:
            if contains(entry):
                return entry
        return None
    for matcher in (exact, contains):
        for entry in entries:
            if matcher(entry):
                return entry
    return entries[0]


def _map_orca_to_profile(
    machine_obj: Optional[Dict[str, Any]],
    filament_obj: Optional[Dict[str, Any]],
    process_obj: Optional[Dict[str, Any]],
    base_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = _normalize_profile(base_profile)
    machine = machine_obj or {}
    filament = filament_obj or {}
    process = process_obj or {}

    profile["name"] = str(machine.get("name", profile.get("name", "Generic FDM")) or profile.get("name", "Generic FDM"))
    area = _printable_area_bounds(machine.get("printable_area"))
    if area:
        profile["bedW"] = float(round(area["w"], 5))
        profile["bedD"] = float(round(area["d"], 5))
        profile["origin"] = "lower_left"
        profile["offsetX"] = 0.0
        profile["offsetY"] = 0.0
    if machine.get("printable_height") is not None:
        profile["bedH"] = float(machine["printable_height"])
    if machine.get("nozzle_diameter") is not None:
        profile["nozzle"] = float(machine["nozzle_diameter"])
        profile["lineWidth"] = float(round(max(0.2, profile["nozzle"] * 1.125), 5))
    for key in ("filament_diameter", "filament_dia"):
        if filament.get(key) is not None:
            profile["filamentDia"] = float(filament[key])
            break
    for key in ("temperature", "nozzle_temperature"):
        if filament.get(key) is not None:
            profile["tempNozzle"] = int(round(float(filament[key])))
            break
    if filament.get("bed_temperature") is not None:
        profile["tempBed"] = int(round(float(filament["bed_temperature"])))
    if process.get("layer_height") is not None:
        profile["layerHeight"] = float(process["layer_height"])
    for key in ("print_speed", "outer_wall_speed", "perimeter_speed"):
        if process.get(key) is not None:
            profile["speedPrint"] = float(process[key]) * 60.0
            break
    if process.get("travel_speed") is not None:
        profile["speedTravel"] = float(process["travel_speed"]) * 60.0
    for key in ("retraction_length", "retract_length"):
        if process.get(key) is not None:
            profile["retractionMm"] = float(process[key])
            break
    for key in ("retraction_speed", "retract_speed"):
        if process.get(key) is not None:
            profile["retractionSpeed"] = float(process[key])
            break
    if machine.get("machine_start_gcode"):
        profile["startGcode"] = str(machine["machine_start_gcode"])
    if machine.get("machine_end_gcode"):
        profile["endGcode"] = str(machine["machine_end_gcode"])
    return profile


def _orca_flat_settings(*objs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        for key, value in obj.items():
            if isinstance(value, dict):
                continue
            if isinstance(value, list) and any(isinstance(item, (list, dict, tuple)) for item in value):
                continue
            merged[str(key)] = value
    return merged


def _profile_prusa_defaults(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    p = _normalize_profile(profile)
    return {
        "nozzle_diameter": p.get("nozzle"),
        "filament_diameter": p.get("filamentDia"),
        "bed_temperature": p.get("tempBed"),
        "temperature": p.get("tempNozzle"),
        "layer_height": p.get("layerHeight"),
        "travel_speed": round(float(p.get("speedTravel", 6000.0)) / 60.0, 5),
        "perimeter_speed": round(float(p.get("speedPrint", 1800.0)) / 60.0, 5),
        "start_gcode": p.get("startGcode"),
        "end_gcode": p.get("endGcode"),
    }


def _profile_cura_defaults(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    p = _normalize_profile(profile)
    return {
        "machine_nozzle_size": p.get("nozzle"),
        "material_diameter": p.get("filamentDia"),
        "layer_height": p.get("layerHeight"),
        "line_width": p.get("lineWidth"),
        "speed_print": round(float(p.get("speedPrint", 1800.0)) / 60.0, 5),
        "speed_travel": round(float(p.get("speedTravel", 6000.0)) / 60.0, 5),
        "material_print_temperature": p.get("tempNozzle"),
        "material_bed_temperature": p.get("tempBed"),
        "retraction_amount": p.get("retractionMm"),
        "retraction_speed": p.get("retractionSpeed"),
        "machine_start_gcode": p.get("startGcode"),
        "machine_end_gcode": p.get("endGcode"),
    }


def _build_prusa_orca_config_text(settings: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]]) -> str:
    merged: Dict[str, Any] = {}
    if isinstance(settings, dict):
        config_blob = settings.get("config", settings)
        if isinstance(config_blob, dict):
            merged.update(config_blob)
    for key, value in _profile_prusa_defaults(profile).items():
        merged.setdefault(key, value)
    lines: List[str] = []
    raw_config = ""
    if isinstance(settings, dict):
        raw_config = str(settings.get("config_text", settings.get("prusa_config_text", "")) or "")
    if raw_config.strip():
        lines.extend([line for line in raw_config.splitlines() if line.strip()])
    for key in sorted(merged):
        normalized = _normalize_slicer_value(merged[key])
        if normalized in {None, ""}:
            continue
        lines.append(f"{key} = {normalized}")
    return "\n".join(lines)


def _default_engine_binary(engine: str, engine_path: str = "") -> str:
    if engine_path.strip():
        return engine_path.strip()
    key = str(engine or "orca").strip().lower()
    if key == "cura":
        return os.environ.get("CURA_ENGINE_PATH") or os.environ.get("CURAENGINE_PATH") or "CuraEngine"
    if key == "prusa":
        return os.environ.get("PRUSA_SLICER_PATH") or os.environ.get("SLIC3R_PATH") or "PrusaSlicer"
    return os.environ.get("ORCA_SLICER_PATH") or os.environ.get("ORCASLICER_PATH") or "OrcaSlicer"


def _split_arg_lines(engine_args_text: str) -> List[str]:
    return [line.strip() for line in str(engine_args_text or "").splitlines() if line.strip()]


def _build_external_command(
    *,
    engine: str,
    engine_path: str,
    engine_args_text: str,
    input_path: Path,
    output_path: Path,
    config_path: Path,
    settings: Optional[Dict[str, Any]],
    profile: Optional[Dict[str, Any]],
) -> Tuple[List[str], str]:
    engine_key = str(engine or "orca").strip().lower()
    binary = _default_engine_binary(engine_key, engine_path)
    config_text = _build_prusa_orca_config_text(settings, profile) if engine_key in {"orca", "prusa"} else ""
    custom_args = _split_arg_lines(engine_args_text)
    if custom_args:
        args = [
            arg.replace("{input}", str(input_path)).replace("{output}", str(output_path)).replace("{config}", str(config_path))
            for arg in custom_args
        ]
        return [binary, *args], config_text
    if engine_key == "cura":
        args: List[str] = ["slice", "-l", str(input_path), "-o", str(output_path)]
        merged_settings: Dict[str, Any] = {}
        if isinstance(settings, dict):
            config_blob = settings.get("config", settings)
            if isinstance(config_blob, dict):
                merged_settings.update(config_blob)
        for key, value in _profile_cura_defaults(profile).items():
            merged_settings.setdefault(key, value)
        for key in sorted(merged_settings):
            normalized = _normalize_slicer_value(merged_settings[key])
            if normalized in {None, ""}:
                continue
            args.extend(["-s", f"{key}={normalized}"])
        return [binary, *args], ""
    args = ["--export-gcode", "--load", str(config_path), "--output", str(output_path), str(input_path)]
    return [binary, *args], config_text


def _role_from_comment(comment: str) -> str:
    text = str(comment or "").strip()
    upper = text.upper()
    if "TYPE:" in upper:
        text = text.split(":", 1)[1].strip()
        upper = text.upper()
    mapping = {
        "WALL-OUTER": "wall_outer",
        "WALL-INNER": "wall_inner",
        "WALL": "walls",
        "SKIN": "top",
        "TOP": "top",
        "BOTTOM": "bottom",
        "TOP/BOTTOM": "top",
        "FILL": "infill",
        "INFILL": "infill",
        "SUPPORT": "support",
        "SUPPORT-INTERFACE": "support",
        "SKIRT": "skirt",
        "BRIM": "skirt",
        "TRAVEL": "travel",
        "EXTERNAL PERIMETER": "wall_outer",
        "PERIMETER": "wall_inner",
        "INTERNAL INFILL": "infill",
        "SOLID INFILL": "bottom",
        "TOP SOLID INFILL": "top",
        "BRIDGE INFILL": "infill",
        "SKIRT/BRIM": "skirt",
        "WIPE TOWER": "support",
    }
    return mapping.get(upper, text.lower().replace(" ", "_")) if text else ""


def _plan_from_gcode_text(gcode_text: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = _normalize_profile(profile)
    lines = str(gcode_text or "").splitlines()
    moves: List[Dict[str, Any]] = []
    x = 0.0
    y = 0.0
    z = 0.0
    e = 0.0
    feed = float(p.get("speedTravel", 6000.0))
    absolute_pos = True
    absolute_e = True
    current_role = ""
    current_layer = 0
    have_layer_comments = False
    last_extrude_z: Optional[float] = None

    for raw_line in lines:
        code_part, sep, comment_part = raw_line.partition(";")
        comment = comment_part.strip() if sep else ""
        if comment.upper().startswith("LAYER:"):
            try:
                current_layer = int(comment.split(":", 1)[1].strip())
                have_layer_comments = True
            except Exception:
                pass
        role = _role_from_comment(comment)
        if role:
            current_role = role

        line = code_part.strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].upper()

        if cmd == "G90":
            absolute_pos = True
            continue
        if cmd == "G91":
            absolute_pos = False
            continue
        if cmd == "M82":
            absolute_e = True
            continue
        if cmd == "M83":
            absolute_e = False
            continue
        if cmd == "G92":
            for token in parts[1:]:
                key = token[:1].upper()
                try:
                    value = float(token[1:])
                except Exception:
                    continue
                if key == "X":
                    x = value
                elif key == "Y":
                    y = value
                elif key == "Z":
                    z = value
                elif key == "E":
                    e = value
            continue
        if cmd not in {"G0", "G1"}:
            continue

        nx, ny, nz, ne = x, y, z, e
        has_motion = False
        has_e = False
        for token in parts[1:]:
            if len(token) < 2:
                continue
            key = token[:1].upper()
            try:
                value = float(token[1:])
            except Exception:
                continue
            if key == "X":
                nx = value if absolute_pos else x + value
                has_motion = True
            elif key == "Y":
                ny = value if absolute_pos else y + value
                has_motion = True
            elif key == "Z":
                nz = value if absolute_pos else z + value
                has_motion = True
            elif key == "E":
                ne = value if absolute_e else e + value
                has_motion = True
                has_e = True
            elif key == "F":
                feed = value
        if not has_motion:
            continue

        extruding = has_e and ne > (e + 1e-6)
        if not have_layer_comments and extruding:
            if last_extrude_z is None:
                last_extrude_z = nz
            elif nz > last_extrude_z + 1e-6:
                current_layer += 1
                last_extrude_z = nz
        layer_height = float(p.get("layerHeight", 0.2))
        if extruding and nz > z + 1e-6:
            layer_height = max(0.01, nz - z)
        _append_move(
            moves,
            nx,
            ny,
            nz,
            extrude=extruding,
            role=current_role if extruding else "travel",
            line_width=float(p.get("lineWidth", 0.45)),
            layer_height=layer_height,
            speed_mm_s=max(0.1, float(feed) / 60.0),
            layer=current_layer,
        )
        x, y, z, e = nx, ny, nz, ne

    return _make_plan(
        "imported_gcode",
        moves,
        {
            "line_count": int(len(lines)),
            "source": "gcode_text",
        },
    )


def _run_slicer_command(
    *,
    command: Sequence[str],
    config_text: str,
    output_path: Path,
    save_target: Optional[Path],
    dry_run: bool,
    timeout_s: int = 360,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "command": list(command),
        "config_text": config_text,
        "output_path": str(save_target) if save_target else "",
        "warnings": [],
        "executed": False,
    }
    if dry_run:
        summary["warnings"].append("dry_run enabled: slicer command was not executed")
        return {"gcode_text": "", "output_path": "", "summary": summary}

    binary = str(command[0]) if command else ""
    resolved = shutil.which(binary) if binary and not Path(binary).is_file() else binary
    if not resolved:
        summary["warnings"].append(f"Slicer binary not found: {binary}")
        return {"gcode_text": "", "output_path": "", "summary": summary}

    try:
        subprocess.run(list(command), check=True, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.CalledProcessError as exc:
        summary["warnings"].append((exc.stderr or exc.stdout or str(exc)).strip())
        return {"gcode_text": "", "output_path": "", "summary": summary}
    except Exception as exc:
        summary["warnings"].append(str(exc))
        return {"gcode_text": "", "output_path": "", "summary": summary}

    gcode_text = output_path.read_text(encoding="utf-8", errors="ignore") if output_path.is_file() else ""
    summary["executed"] = True
    if save_target and output_path.is_file() and output_path != save_target:
        save_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, save_target)
        summary["output_path"] = str(save_target)
    elif output_path.is_file() and save_target is not None:
        summary["output_path"] = str(save_target)
    return {"gcode_text": gcode_text, "output_path": summary["output_path"], "summary": summary}


__all__ = [
    "_build_external_command",
    "_build_prusa_orca_config_text",
    "_default_engine_binary",
    "_load_orca_profiles",
    "_map_orca_to_profile",
    "_orca_flat_settings",
    "_plan_from_gcode_text",
    "_run_slicer_command",
    "_select_orca_entry",
]
