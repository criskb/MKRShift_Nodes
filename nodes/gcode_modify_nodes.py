import math
from typing import Any, Dict, List, Optional, Sequence

from ..categories import GCODE_MODIFY
from ..lib.gcode_shared import (
    _clamp,
    _clone_plan,
    _json_text,
    _layer_summaries,
    _normalize_profile,
    _parse_json_text,
    _plan_bounds,
    _plan_offset,
)


def _join_gcode_lines(lines: Sequence[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _parse_layer_marker(line: str) -> Optional[int]:
    stripped = str(line or "").strip()
    if not stripped.startswith("; LAYER:"):
        return None
    try:
        return int(stripped.split(":", 1)[1].strip())
    except Exception:
        return None


def _format_value(value: float) -> str:
    text = f"{float(value):.3f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _safe_format_lines(lines: Sequence[str], values: Dict[str, Any]) -> List[str]:
    rendered: List[str] = []
    for line in lines:
        template = str(line)
        try:
            rendered.append(template.format(**values))
        except Exception:
            rendered.append(template)
    return rendered


def _coerce_rule_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(line).rstrip() for line in value if str(line).strip()]
    text = str(value or "")
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _layer_lookup(plan: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {int(entry["layer"]): entry for entry in _layer_summaries(plan.get("moves", []))}


def _calibration_command(target: str, value: float) -> Dict[str, str]:
    target_key = str(target or "temp").strip().lower()
    if target_key == "flow":
        pct = int(round(value))
        return {"label": f"flow {pct}%", "command": f"M221 S{pct}"}
    if target_key == "speed":
        pct = int(round(value))
        return {"label": f"speed {pct}%", "command": f"M220 S{pct}"}
    if target_key == "fan":
        pct = int(round(_clamp(value, 0.0, 100.0)))
        pwm = int(round((pct / 100.0) * 255.0))
        return {"label": f"fan {pct}%", "command": f"M106 S{pwm}"}
    temp = int(round(value))
    return {"label": f"temp {temp}C", "command": f"M104 S{temp}"}


def _parse_mesh(mesh_json: str) -> Dict[str, Any]:
    raw = _parse_json_text(mesh_json, {})
    if not isinstance(raw, dict):
        raw = {}
    grid = raw.get("offsets", raw.get("grid", raw.get("values", [[0.0]])))
    if not isinstance(grid, list) or not grid:
        grid = [[0.0]]
    normalized_grid: List[List[float]] = []
    for row in grid:
        if not isinstance(row, list) or not row:
            continue
        normalized_grid.append([float(cell) for cell in row])
    if not normalized_grid:
        normalized_grid = [[0.0]]
    width_mm = float(raw.get("bed_width_mm", raw.get("width_mm", raw.get("mesh_width_mm", 220.0))) or 220.0)
    depth_mm = float(raw.get("bed_depth_mm", raw.get("depth_mm", raw.get("mesh_depth_mm", 220.0))) or 220.0)
    origin_x_mm = float(raw.get("origin_x_mm", 0.0) or 0.0)
    origin_y_mm = float(raw.get("origin_y_mm", 0.0) or 0.0)
    return {
        "offsets": normalized_grid,
        "bed_width_mm": max(1.0, width_mm),
        "bed_depth_mm": max(1.0, depth_mm),
        "origin_x_mm": origin_x_mm,
        "origin_y_mm": origin_y_mm,
    }


def _sample_bed_mesh(offsets: Sequence[Sequence[float]], x_norm: float, y_norm: float) -> float:
    rows = len(offsets)
    cols = len(offsets[0]) if rows > 0 else 0
    if rows <= 0 or cols <= 0:
        return 0.0
    if rows == 1 and cols == 1:
        return float(offsets[0][0])
    px = _clamp(x_norm, 0.0, 1.0) * max(0, cols - 1)
    py = _clamp(y_norm, 0.0, 1.0) * max(0, rows - 1)
    x0 = int(math.floor(px))
    y0 = int(math.floor(py))
    x1 = min(cols - 1, x0 + 1)
    y1 = min(rows - 1, y0 + 1)
    tx = px - float(x0)
    ty = py - float(y0)
    q00 = float(offsets[y0][x0])
    q10 = float(offsets[y0][x1])
    q01 = float(offsets[y1][x0])
    q11 = float(offsets[y1][x1])
    top = (q00 * (1.0 - tx)) + (q10 * tx)
    bottom = (q01 * (1.0 - tx)) + (q11 * tx)
    return float((top * (1.0 - ty)) + (bottom * ty))


def _rule_matches(rule: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if not bool(rule.get("enabled", True)):
        return False
    rule_mode = str(rule.get("mode", "") or "").strip()
    if rule_mode and rule_mode != str(ctx.get("mode", "")):
        return False
    if "layer" in rule and int(rule["layer"]) != int(ctx.get("layer", 0)):
        return False
    if "layer_min" in rule and int(ctx.get("layer", 0)) < int(rule["layer_min"]):
        return False
    if "layer_max" in rule and int(ctx.get("layer", 0)) > int(rule["layer_max"]):
        return False
    every_layers = int(rule.get("every_layers", 0) or 0)
    if every_layers > 0 and (int(ctx.get("layer", 0)) % every_layers) != 0:
        return False
    if "z_min" in rule and float(ctx.get("z", 0.0)) < float(rule["z_min"]):
        return False
    if "z_max" in rule and float(ctx.get("z", 0.0)) > float(rule["z_max"]):
        return False
    return True


class MKRGCodeBedMeshCompensate:
    SEARCH_ALIASES = ["bed mesh compensation", "mesh leveling", "z compensation", "bed correction"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
                "mesh_json": (
                    "STRING",
                    {
                        "default": '{"bed_width_mm":220,"bed_depth_mm":220,"offsets":[[0.00,0.02,0.01],[0.03,0.00,-0.01],[0.05,0.01,-0.02]]}',
                        "multiline": True,
                    },
                ),
                "max_compensation_mm": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 5.0, "step": 0.01}),
                "warn_if_over_mm": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 5.0, "step": 0.01}),
                "fade_height_mm": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "use_profile_bed_size": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("MKR_GCODE_PLAN", "STRING", "STRING")
    RETURN_NAMES = ("plan", "report_json", "summary")
    FUNCTION = "apply"
    CATEGORY = GCODE_MODIFY

    def apply(
        self,
        plan: Dict[str, Any],
        mesh_json: str = '{"bed_width_mm":220,"bed_depth_mm":220,"offsets":[[0.00,0.02,0.01],[0.03,0.00,-0.01],[0.05,0.01,-0.02]]}',
        max_compensation_mm: float = 0.5,
        warn_if_over_mm: float = 0.4,
        fade_height_mm: float = 3.0,
        use_profile_bed_size: bool = True,
        profile: Optional[Dict[str, Any]] = None,
    ):
        if not isinstance(plan, dict):
            warnings = ["plan input is invalid"]
            return ({}, _json_text({"warnings": warnings}), "Invalid G-code plan")

        moves = plan.get("moves", []) if isinstance(plan.get("moves"), list) else []
        mesh = _parse_mesh(mesh_json)
        normalized_profile = _normalize_profile(profile)
        bounds = plan.get("bounds", {}) if isinstance(plan.get("bounds"), dict) else _plan_bounds(moves)
        offset_x, offset_y = _plan_offset(plan, normalized_profile)
        span_x = float(bounds.get("max_x", 0.0)) - float(bounds.get("min_x", 0.0))
        span_y = float(bounds.get("max_y", 0.0)) - float(bounds.get("min_y", 0.0))
        mesh_width = float(mesh["bed_width_mm"])
        mesh_depth = float(mesh["bed_depth_mm"])
        if bool(use_profile_bed_size):
            mesh_width = float(normalized_profile.get("bedW", mesh_width) or mesh_width)
            mesh_depth = float(normalized_profile.get("bedD", mesh_depth) or mesh_depth)
        if not bool(profile):
            offset_x = -float(bounds.get("min_x", 0.0))
            offset_y = -float(bounds.get("min_y", 0.0))
            mesh_width = max(mesh_width, span_x or 1.0)
            mesh_depth = max(mesh_depth, span_y or 1.0)

        warnings: List[str] = []
        new_moves: List[Dict[str, Any]] = []
        max_raw = 0.0
        max_applied = 0.0
        over_warn_count = 0

        for move in moves:
            actual_x = float(move.get("x", 0.0)) + offset_x - float(mesh.get("origin_x_mm", 0.0))
            actual_y = float(move.get("y", 0.0)) + offset_y - float(mesh.get("origin_y_mm", 0.0))
            x_norm = actual_x / max(1e-6, mesh_width)
            y_norm = actual_y / max(1e-6, mesh_depth)
            raw_comp = _sample_bed_mesh(mesh["offsets"], x_norm, y_norm)
            fade = 1.0
            z = float(move.get("z", 0.0))
            if float(fade_height_mm) > 0.0:
                fade = max(0.0, 1.0 - (z / float(fade_height_mm)))
            applied = _clamp(raw_comp * fade, -float(max_compensation_mm), float(max_compensation_mm))
            adjusted = dict(move)
            adjusted["z"] = float(max(0.0, z + applied))
            new_moves.append(adjusted)
            max_raw = max(max_raw, abs(raw_comp))
            max_applied = max(max_applied, abs(applied))
            if abs(applied) > float(warn_if_over_mm):
                over_warn_count += 1

        if over_warn_count > 0:
            warnings.append(f"{over_warn_count} move samples exceed the warning compensation limit of {float(warn_if_over_mm):.2f} mm.")
        if max_raw > float(max_compensation_mm):
            warnings.append(
                f"Raw bed mesh requested {max_raw:.3f} mm correction, clamped to {float(max_compensation_mm):.3f} mm."
            )

        report = {
            "mesh_size": [len(mesh["offsets"][0]), len(mesh["offsets"])],
            "mesh_bed_size_mm": [float(round(mesh_width, 5)), float(round(mesh_depth, 5))],
            "fade_height_mm": float(round(float(fade_height_mm), 5)),
            "max_raw_compensation_mm": float(round(max_raw, 5)),
            "max_applied_compensation_mm": float(round(max_applied, 5)),
            "warn_if_over_mm": float(round(float(warn_if_over_mm), 5)),
            "warnings": warnings,
        }
        meta_updates = {
            "bed_mesh_compensation": {
                "mesh_size": report["mesh_size"],
                "max_applied_compensation_mm": report["max_applied_compensation_mm"],
                "fade_height_mm": report["fade_height_mm"],
            }
        }
        updated_plan = _clone_plan(plan, new_moves, meta_updates=meta_updates)
        summary = (
            f"Bed mesh | max {report['max_applied_compensation_mm']:.3f} mm | "
            f"{len(warnings)} warnings"
        )
        return (updated_plan, _json_text(report), summary)


class MKRGCodeCalibrationTower:
    SEARCH_ALIASES = ["calibration tower", "temp tower", "flow tower", "speed tower"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
                "gcode_text": ("STRING", {"default": "", "multiline": True}),
                "axis": (["z_mm", "layer_index"], {"default": "z_mm"}),
                "target": (["temp", "flow", "speed", "fan"], {"default": "temp"}),
                "start_value": ("FLOAT", {"default": 220.0, "min": -999.0, "max": 999.0, "step": 0.1}),
                "step_value": ("FLOAT", {"default": -5.0, "min": -999.0, "max": 999.0, "step": 0.1}),
                "every": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 999.0, "step": 0.1}),
                "clamp_min": ("FLOAT", {"default": 180.0, "min": -999.0, "max": 999.0, "step": 0.1}),
                "clamp_max": ("FLOAT", {"default": 260.0, "min": -999.0, "max": 999.0, "step": 0.1}),
                "only_on_change": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("gcode_text", "steps_json", "summary")
    FUNCTION = "apply"
    CATEGORY = GCODE_MODIFY

    def apply(
        self,
        plan: Dict[str, Any],
        gcode_text: str = "",
        axis: str = "z_mm",
        target: str = "temp",
        start_value: float = 220.0,
        step_value: float = -5.0,
        every: float = 5.0,
        clamp_min: float = 180.0,
        clamp_max: float = 260.0,
        only_on_change: bool = True,
    ):
        lines = str(gcode_text or "").splitlines()
        layer_map = _layer_lookup(plan if isinstance(plan, dict) else {})
        warnings: List[str] = []
        applied: List[Dict[str, Any]] = []
        out: List[str] = []
        last_value: Optional[float] = None
        layer_markers = 0

        for line in lines:
            out.append(line)
            layer = _parse_layer_marker(line)
            if layer is None:
                continue
            layer_markers += 1
            layer_info = layer_map.get(layer, {})
            axis_value = float(layer if str(axis) == "layer_index" else layer_info.get("z_min", layer_info.get("z_max", 0.0)))
            step_index = int(math.floor(axis_value / max(0.1, float(every))))
            raw_value = float(start_value) + (step_index * float(step_value))
            value = _clamp(raw_value, float(clamp_min), float(clamp_max))
            if bool(only_on_change) and last_value is not None and abs(value - last_value) < 1e-9:
                continue
            command = _calibration_command(target, value)
            out.append(f"; MKR calibration {command['label']}")
            out.append(command["command"])
            applied.append(
                {
                    "layer": int(layer),
                    "axis": str(axis),
                    "axis_value": float(round(axis_value, 5)),
                    "target": str(target),
                    "value": float(round(value, 5)),
                    "command": command["command"],
                }
            )
            last_value = value

        if not lines:
            warnings.append("gcode_text input is empty.")
        if layer_markers == 0:
            warnings.append("No '; LAYER:' markers found. Export with comments enabled before using calibration injection.")

        result = {
            "axis": str(axis),
            "target": str(target),
            "step_count": int(len(applied)),
            "steps": applied,
            "warnings": warnings,
        }
        summary = f"Calibration tower | {len(applied)} injected steps | {len(warnings)} warnings"
        return (_join_gcode_lines(out) if out else str(gcode_text or ""), _json_text(result), summary)


class MKRGCodeConditionalInjector:
    SEARCH_ALIASES = ["conditional gcode injector", "macro injector", "gcode rules", "post process gcode"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
                "gcode_text": ("STRING", {"default": "", "multiline": True}),
                "rules_json": (
                    "STRING",
                    {
                        "default": '[{"label":"announce-start","when":"start","inject":"M117 START {mode}"},{"label":"fan-boost","when":"layer_change","layer_min":2,"every_layers":2,"inject":"M106 S255"},{"label":"announce-end","when":"end","inject":"M118 DONE {mode}"}]',
                        "multiline": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("gcode_text", "applied_json", "summary")
    FUNCTION = "apply"
    CATEGORY = GCODE_MODIFY

    def apply(
        self,
        plan: Dict[str, Any],
        gcode_text: str = "",
        rules_json: str = '[{"label":"announce-start","when":"start","inject":"M117 START {mode}"},{"label":"fan-boost","when":"layer_change","layer_min":2,"every_layers":2,"inject":"M106 S255"},{"label":"announce-end","when":"end","inject":"M118 DONE {mode}"}]',
    ):
        if not isinstance(plan, dict):
            warnings = ["plan input is invalid"]
            return (str(gcode_text or ""), _json_text({"warnings": warnings}), "Invalid G-code plan")

        raw_rules = _parse_json_text(rules_json, [])
        if isinstance(raw_rules, dict):
            raw_rules = [raw_rules]
        rules = [rule for rule in raw_rules if isinstance(rule, dict)]
        layer_map = _layer_lookup(plan)
        mode = str(plan.get("mode", "unknown"))
        lines = str(gcode_text or "").splitlines()
        out: List[str] = []
        applied: List[Dict[str, Any]] = []
        warnings: List[str] = []
        layer_markers = 0

        start_rules = [rule for rule in rules if str(rule.get("when", "layer_change")).strip().lower() == "start"]
        layer_rules = [rule for rule in rules if str(rule.get("when", "layer_change")).strip().lower() == "layer_change"]
        end_rules = [rule for rule in rules if str(rule.get("when", "layer_change")).strip().lower() == "end"]

        base_ctx = {"layer": 0, "z": 0.0, "mode": mode}
        for rule_idx, rule in enumerate(start_rules):
            ctx = dict(base_ctx)
            ctx["rule_index"] = rule_idx
            rendered = _safe_format_lines(_coerce_rule_lines(rule.get("inject", "")), ctx)
            if not rendered:
                continue
            label = str(rule.get("label", f"start-{rule_idx}") or f"start-{rule_idx}")
            out.append(f"; MKR inject {label}")
            out.extend(rendered)
            applied.append({"label": label, "when": "start", "layer": 0, "lines": rendered})

        for line in lines:
            out.append(line)
            layer = _parse_layer_marker(line)
            if layer is None:
                continue
            layer_markers += 1
            layer_info = layer_map.get(layer, {})
            ctx = {
                "layer": int(layer),
                "z": float(layer_info.get("z_min", layer_info.get("z_max", 0.0))),
                "mode": mode,
            }
            for rule_idx, rule in enumerate(layer_rules):
                if not _rule_matches(rule, ctx):
                    continue
                rendered = _safe_format_lines(_coerce_rule_lines(rule.get("inject", "")), ctx)
                if not rendered:
                    continue
                label = str(rule.get("label", f"layer-{rule_idx}") or f"layer-{rule_idx}")
                out.append(f"; MKR inject {label}")
                out.extend(rendered)
                applied.append({"label": label, "when": "layer_change", "layer": int(layer), "lines": rendered})

        end_ctx = dict(base_ctx)
        for rule_idx, rule in enumerate(end_rules):
            rendered = _safe_format_lines(_coerce_rule_lines(rule.get("inject", "")), end_ctx)
            if not rendered:
                continue
            label = str(rule.get("label", f"end-{rule_idx}") or f"end-{rule_idx}")
            out.append(f"; MKR inject {label}")
            out.extend(rendered)
            applied.append({"label": label, "when": "end", "layer": 0, "lines": rendered})

        if not lines:
            warnings.append("gcode_text input is empty.")
        if layer_rules and layer_markers == 0:
            warnings.append("No '; LAYER:' markers found, so layer_change rules were not applied.")

        report = {
            "rule_count": int(len(rules)),
            "applied_count": int(len(applied)),
            "applied": applied,
            "warnings": warnings,
        }
        summary = f"Conditional injector | {len(applied)} events | {len(warnings)} warnings"
        return (_join_gcode_lines(out), _json_text(report), summary)
