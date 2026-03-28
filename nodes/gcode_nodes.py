import json
import math
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageFilter
import torch

from ..categories import GCODE_EXPORT, GCODE_GENERATE, GCODE_PRINTER
from ..lib.gcode_shared import (
    _append_move,
    _build_gcode,
    _contiguous_true_runs,
    _first_pil,
    _json_text,
    _make_plan,
    _normalize_profile,
    _pil_to_batch,
    _render_plan_preview,
    _resolve_plan_settings,
)
from ..lib.settings_bundle import parse_settings_payload
from .presave_image_nodes import _output_dir, _resolve_output_file, _sanitize_basename


class MKRGCodePrinterProfile:
    SEARCH_ALIASES = ["3d printer profile", "fdm profile", "gcode printer"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "printer_name": "Generic FDM",
            "bed_width_mm": 220.0,
            "bed_depth_mm": 220.0,
            "bed_height_mm": 250.0,
            "origin": "center",
            "offset_x_mm": 0.0,
            "offset_y_mm": 0.0,
            "nozzle_diameter_mm": 0.4,
            "line_width_mm": 0.45,
            "layer_height_mm": 0.2,
            "filament_diameter_mm": 1.75,
            "extrusion_multiplier": 1.0,
            "nozzle_temp_c": 210,
            "bed_temp_c": 60,
            "print_speed_mm_s": 30.0,
            "travel_speed_mm_s": 100.0,
            "retraction_mm": 0.8,
            "retraction_speed_mm_s": 35.0,
            "travel_z_mm": 0.6,
            "home_before_print": True,
            "prime_line": True,
            "start_gcode": "M104 S210\nM140 S60\nG28\nG92 E0",
            "end_gcode": "M104 S0\nM140 S0\nG28 X0\nM84",
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("MKR_GCODE_PROFILE", "STRING", "STRING")
    RETURN_NAMES = ("profile", "profile_json", "summary")
    FUNCTION = "build"
    CATEGORY = GCODE_PRINTER

    def build(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "bed_width_mm": {"min": 50.0, "max": 1000.0},
                "bed_depth_mm": {"min": 50.0, "max": 1000.0},
                "bed_height_mm": {"min": 50.0, "max": 1500.0},
                "offset_x_mm": {"min": -1000.0, "max": 1000.0},
                "offset_y_mm": {"min": -1000.0, "max": 1000.0},
                "nozzle_diameter_mm": {"min": 0.1, "max": 2.0},
                "line_width_mm": {"min": 0.1, "max": 2.4},
                "layer_height_mm": {"min": 0.05, "max": 1.0},
                "filament_diameter_mm": {"min": 1.0, "max": 3.0},
                "extrusion_multiplier": {"min": 0.1, "max": 3.0},
                "nozzle_temp_c": {"min": 0, "max": 400, "integer": True},
                "bed_temp_c": {"min": 0, "max": 150, "integer": True},
                "print_speed_mm_s": {"min": 1.0, "max": 400.0},
                "travel_speed_mm_s": {"min": 1.0, "max": 500.0},
                "retraction_mm": {"min": 0.0, "max": 20.0},
                "retraction_speed_mm_s": {"min": 1.0, "max": 200.0},
                "travel_z_mm": {"min": 0.1, "max": 10.0},
            },
            boolean_keys={"home_before_print", "prime_line"},
            legacy=legacy_settings,
        )
        origin = str(settings.get("origin", "center") or "center")
        if origin not in {"center", "lower_left"}:
            origin = "center"
        profile = _normalize_profile(
            {
                "name": str(settings["printer_name"]),
                "bedW": settings["bed_width_mm"],
                "bedD": settings["bed_depth_mm"],
                "bedH": settings["bed_height_mm"],
                "origin": origin,
                "offsetX": settings["offset_x_mm"],
                "offsetY": settings["offset_y_mm"],
                "nozzle": settings["nozzle_diameter_mm"],
                "lineWidth": settings["line_width_mm"],
                "layerHeight": settings["layer_height_mm"],
                "filamentDia": settings["filament_diameter_mm"],
                "extrusionMult": settings["extrusion_multiplier"],
                "tempNozzle": settings["nozzle_temp_c"],
                "tempBed": settings["bed_temp_c"],
                "speedPrint": float(settings["print_speed_mm_s"]) * 60.0,
                "speedTravel": float(settings["travel_speed_mm_s"]) * 60.0,
                "retractionMm": settings["retraction_mm"],
                "retractionSpeed": settings["retraction_speed_mm_s"],
                "travelZ": settings["travel_z_mm"],
                "homeBeforePrint": settings["home_before_print"],
                "primeLine": settings["prime_line"],
                "startGcode": settings["start_gcode"],
                "endGcode": settings["end_gcode"],
            }
        )
        summary = (
            f"{profile['name']} | {profile['bedW']:.0f}x{profile['bedD']:.0f}x{profile['bedH']:.0f} mm | "
            f"nozzle {profile['nozzle']:.2f} | layer {profile['layerHeight']:.2f}"
        )
        return (profile, _json_text(profile), summary)


class MKRGCodeHeightmapPlate:
    SEARCH_ALIASES = ["lithophane", "heightmap gcode", "relief print", "image to gcode"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "width_mm": 80.0,
            "height_mm": 80.0,
            "base_layers": 3,
            "relief_height_mm": 1.6,
            "layer_height_mm": 0.2,
            "line_width_mm": 0.45,
            "fill_mode": "alternate_xy",
            "invert_heightmap": False,
            "mirror_x": False,
            "mirror_y": False,
            "blur_radius_px": 0.0,
            "height_gamma": 1.0,
            "print_speed_mm_s": 28.0,
            "travel_speed_mm_s": 120.0,
            "use_profile_defaults": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("MKR_GCODE_PLAN", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("plan", "preview", "plan_info_json", "summary")
    FUNCTION = "build"
    CATEGORY = GCODE_GENERATE

    def build(
        self,
        image: torch.Tensor,
        settings_json: str = "{}",
        profile: Optional[Dict[str, Any]] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "width_mm": {"min": 10.0, "max": 400.0},
                "height_mm": {"min": 10.0, "max": 400.0},
                "base_layers": {"min": 1, "max": 40, "integer": True},
                "relief_height_mm": {"min": 0.1, "max": 20.0},
                "layer_height_mm": {"min": 0.05, "max": 1.0},
                "line_width_mm": {"min": 0.1, "max": 2.0},
                "blur_radius_px": {"min": 0.0, "max": 32.0},
                "height_gamma": {"min": 0.1, "max": 4.0},
                "print_speed_mm_s": {"min": 1.0, "max": 300.0},
                "travel_speed_mm_s": {"min": 1.0, "max": 500.0},
            },
            boolean_keys={"invert_heightmap", "mirror_x", "mirror_y", "use_profile_defaults"},
            legacy=legacy_settings,
        )
        fill_mode = str(settings.get("fill_mode", "alternate_xy") or "alternate_xy")
        if fill_mode not in {"alternate_xy", "x_only", "y_only"}:
            fill_mode = "alternate_xy"
        layer_height, line_width, print_speed, travel_speed = _resolve_plan_settings(
            profile,
            settings["use_profile_defaults"],
            settings["layer_height_mm"],
            settings["line_width_mm"],
            settings["print_speed_mm_s"],
            settings["travel_speed_mm_s"],
        )

        src = _first_pil(image).convert("L")
        if float(settings["blur_radius_px"]) > 1e-6:
            src = src.filter(ImageFilter.GaussianBlur(radius=float(settings["blur_radius_px"])))
        cols = max(4, int(round(float(settings["width_mm"]) / max(0.1, line_width))) + 1)
        rows = max(4, int(round(float(settings["height_mm"]) / max(0.1, line_width))) + 1)
        sampled = src.resize((cols, rows), resample=Image.Resampling.BILINEAR)
        grid = np.asarray(sampled, dtype=np.float32) / 255.0
        if bool(settings["mirror_x"]):
            grid = np.fliplr(grid)
        if bool(settings["mirror_y"]):
            grid = np.flipud(grid)
        if bool(settings["invert_heightmap"]):
            grid = 1.0 - grid
        gamma = float(max(0.1, settings["height_gamma"]))
        if abs(gamma - 1.0) > 1e-6:
            grid = np.power(np.clip(grid, 0.0, 1.0), gamma)

        base_h = int(max(1, settings["base_layers"])) * layer_height
        heights = base_h + np.clip(grid, 0.0, 1.0) * float(max(0.1, settings["relief_height_mm"]))
        layer_count = max(1, int(math.ceil(float(np.max(heights)) / layer_height)))
        dx = float(settings["width_mm"]) / float(max(1, cols - 1))
        dy = float(settings["height_mm"]) / float(max(1, rows - 1))

        moves: List[Dict[str, Any]] = []
        for layer_idx in range(layer_count):
            z = float((layer_idx + 1) * layer_height)
            scan_x = str(fill_mode) == "x_only" or (str(fill_mode) == "alternate_xy" and (layer_idx % 2 == 0))
            role = "base" if layer_idx < int(settings["base_layers"]) else "relief"
            comment = f"layer {layer_idx} {role}"
            if scan_x:
                for row in range(rows):
                    mask = heights[row, :] >= (z - 1e-6)
                    segments = _contiguous_true_runs(mask.tolist())
                    if not segments:
                        continue
                    reverse = bool(row % 2 == 1)
                    ordered = list(reversed(segments)) if reverse else segments
                    y = float(row * dy)
                    for seg_idx, (start, end) in enumerate(ordered):
                        x0 = float(start * dx)
                        x1 = float(end * dx)
                        sx, ex = (x1, x0) if reverse else (x0, x1)
                        _append_move(
                            moves,
                            sx,
                            y,
                            z,
                            extrude=False,
                            role="travel",
                            line_width=line_width,
                            layer_height=layer_height,
                            speed_mm_s=travel_speed,
                            layer=layer_idx,
                            comment=comment if seg_idx == 0 else "",
                        )
                        _append_move(
                            moves,
                            ex,
                            y,
                            z,
                            extrude=True,
                            role=role,
                            line_width=line_width,
                            layer_height=layer_height,
                            speed_mm_s=print_speed,
                            layer=layer_idx,
                        )
            else:
                for col in range(cols):
                    mask = heights[:, col] >= (z - 1e-6)
                    segments = _contiguous_true_runs(mask.tolist())
                    if not segments:
                        continue
                    reverse = bool(col % 2 == 1)
                    ordered = list(reversed(segments)) if reverse else segments
                    x = float(col * dx)
                    for seg_idx, (start, end) in enumerate(ordered):
                        y0 = float(start * dy)
                        y1 = float(end * dy)
                        sy, ey = (y1, y0) if reverse else (y0, y1)
                        _append_move(
                            moves,
                            x,
                            sy,
                            z,
                            extrude=False,
                            role="travel",
                            line_width=line_width,
                            layer_height=layer_height,
                            speed_mm_s=travel_speed,
                            layer=layer_idx,
                            comment=comment if seg_idx == 0 else "",
                        )
                        _append_move(
                            moves,
                            x,
                            ey,
                            z,
                            extrude=True,
                            role=role,
                            line_width=line_width,
                            layer_height=layer_height,
                            speed_mm_s=print_speed,
                            layer=layer_idx,
                        )

        plan = _make_plan(
            "heightmap_plate",
            moves,
            {
                "width_mm": float(settings["width_mm"]),
                "height_mm": float(settings["height_mm"]),
                "base_layers": int(settings["base_layers"]),
                "relief_height_mm": float(settings["relief_height_mm"]),
                "fill_mode": str(fill_mode),
                "blur_radius_px": float(settings["blur_radius_px"]),
                "height_gamma": float(settings["height_gamma"]),
                "grid_cols": int(cols),
                "grid_rows": int(rows),
            },
        )
        preview = _render_plan_preview(plan)
        info = {
            "mode": plan["mode"],
            "stats": plan["stats"],
            "bounds": plan["bounds"],
            "meta": plan["meta"],
        }
        summary = (
            f"Heightmap plate {float(settings['width_mm']):.0f}x{float(settings['height_mm']):.0f} mm | "
            f"{plan['stats']['layer_count']} layers | {plan['stats']['print_moves']} print moves"
        )
        return (plan, _pil_to_batch([preview]), _json_text(info), summary)


class MKRGCodeSpiralVase:
    SEARCH_ALIASES = ["vase mode", "spiral vase", "helical print", "procedural vase"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "height_mm": 120.0,
            "base_radius_mm": 28.0,
            "top_radius_mm": 24.0,
            "bottom_layers": 3,
            "layer_height_mm": 0.2,
            "line_width_mm": 0.45,
            "segments_per_turn": 72,
            "wave_amplitude_mm": 0.0,
            "wave_frequency": 0.0,
            "twist_deg": 0.0,
            "phase_deg": 0.0,
            "ovality": 0.0,
            "print_speed_mm_s": 24.0,
            "travel_speed_mm_s": 120.0,
            "use_profile_defaults": False,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(cls._default_settings(), separators=(",", ":")),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("MKR_GCODE_PLAN", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("plan", "preview", "plan_info_json", "summary")
    FUNCTION = "build"
    CATEGORY = GCODE_GENERATE

    def build(
        self,
        settings_json: str = "{}",
        profile: Optional[Dict[str, Any]] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "height_mm": {"min": 10.0, "max": 500.0},
                "base_radius_mm": {"min": 2.0, "max": 250.0},
                "top_radius_mm": {"min": 2.0, "max": 250.0},
                "bottom_layers": {"min": 0, "max": 30, "integer": True},
                "layer_height_mm": {"min": 0.05, "max": 1.0},
                "line_width_mm": {"min": 0.1, "max": 2.0},
                "segments_per_turn": {"min": 12, "max": 720, "integer": True},
                "wave_amplitude_mm": {"min": 0.0, "max": 30.0},
                "wave_frequency": {"min": 0.0, "max": 50.0},
                "twist_deg": {"min": -720.0, "max": 720.0},
                "phase_deg": {"min": -360.0, "max": 360.0},
                "ovality": {"min": -0.75, "max": 0.75},
                "print_speed_mm_s": {"min": 1.0, "max": 300.0},
                "travel_speed_mm_s": {"min": 1.0, "max": 500.0},
            },
            boolean_keys={"use_profile_defaults"},
            legacy=legacy_settings,
        )
        layer_height, line_width, print_speed, travel_speed = _resolve_plan_settings(
            profile,
            settings["use_profile_defaults"],
            settings["layer_height_mm"],
            settings["line_width_mm"],
            settings["print_speed_mm_s"],
            settings["travel_speed_mm_s"],
        )

        base_radius = float(max(2.0, settings["base_radius_mm"]))
        top_radius = float(max(2.0, settings["top_radius_mm"]))
        total_h = float(max(layer_height, settings["height_mm"]))
        base_h = float(max(0, int(settings["bottom_layers"]))) * layer_height
        wall_h = max(layer_height, total_h - base_h)
        seg_turn = max(12, int(settings["segments_per_turn"]))
        phase_rad = math.radians(float(settings["phase_deg"]))
        twist_rad = math.radians(float(settings["twist_deg"]))
        ovality = float(settings["ovality"])

        moves: List[Dict[str, Any]] = []
        base_turns = max(1, int(math.ceil(base_radius / max(0.1, line_width))))
        for layer_idx in range(max(0, int(settings["bottom_layers"]))):
            z = float((layer_idx + 1) * layer_height)
            steps = max(12, base_turns * seg_turn)
            for step in range(steps + 1):
                u = float(step) / float(steps)
                theta = phase_rad + (u * base_turns * math.pi * 2.0)
                r = max(line_width * 0.5, u * max(line_width, base_radius - line_width * 0.5))
                rx = max(line_width * 0.5, r * (1.0 + ovality))
                ry = max(line_width * 0.5, r * (1.0 - ovality))
                x = rx * math.cos(theta)
                y = ry * math.sin(theta)
                _append_move(
                    moves,
                    x,
                    y,
                    z,
                    extrude=bool(step > 0),
                    role="base" if step > 0 else "travel",
                    line_width=line_width,
                    layer_height=layer_height,
                    speed_mm_s=print_speed if step > 0 else travel_speed,
                    layer=layer_idx,
                    comment="bottom spiral" if step == 0 else "",
                )

        wall_turns = max(1, int(math.ceil(wall_h / layer_height)))
        wall_steps = max(24, wall_turns * seg_turn)
        wall_start_layer = max(0, int(settings["bottom_layers"]))
        for step in range(wall_steps + 1):
            u = float(step) / float(wall_steps)
            theta = phase_rad + (u * wall_turns * math.pi * 2.0) + (twist_rad * u)
            radius = (1.0 - u) * base_radius + u * top_radius
            if float(settings["wave_amplitude_mm"]) > 1e-6 and float(settings["wave_frequency"]) > 1e-6:
                radius += float(settings["wave_amplitude_mm"]) * math.sin(u * float(settings["wave_frequency"]) * math.pi * 2.0)
            radius = max(line_width * 0.75, radius)
            z = base_h + (u * wall_h)
            rx = max(line_width * 0.75, radius * (1.0 + ovality))
            ry = max(line_width * 0.75, radius * (1.0 - ovality))
            x = rx * math.cos(theta)
            y = ry * math.sin(theta)
            layer_idx = wall_start_layer + int(max(0, math.floor(z / max(1e-6, layer_height))))
            _append_move(
                moves,
                x,
                y,
                z,
                extrude=bool(step > 0),
                role="wall" if step > 0 else "travel",
                line_width=line_width,
                layer_height=layer_height,
                speed_mm_s=print_speed if step > 0 else travel_speed,
                layer=layer_idx,
                comment="spiral wall" if step == 0 else "",
            )

        plan = _make_plan(
            "spiral_vase",
            moves,
            {
                "height_mm": total_h,
                "base_radius_mm": base_radius,
                "top_radius_mm": top_radius,
                "bottom_layers": int(settings["bottom_layers"]),
                "wave_amplitude_mm": float(settings["wave_amplitude_mm"]),
                "wave_frequency": float(settings["wave_frequency"]),
                "twist_deg": float(settings["twist_deg"]),
                "phase_deg": float(settings["phase_deg"]),
                "ovality": float(settings["ovality"]),
                "segments_per_turn": int(seg_turn),
            },
        )
        preview = _render_plan_preview(plan)
        info = {
            "mode": plan["mode"],
            "stats": plan["stats"],
            "bounds": plan["bounds"],
            "meta": plan["meta"],
        }
        summary = (
            f"Spiral vase {total_h:.0f} mm tall | radius {base_radius:.1f}->{top_radius:.1f} | "
            f"{plan['stats']['layer_count']} layers"
        )
        return (plan, _pil_to_batch([preview]), _json_text(info), summary)


class MKRGCodeExport:
    SEARCH_ALIASES = ["save gcode", "gcode export", "3d print export"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": "MKR_gcode"}),
                "subfolder": ("STRING", {"default": ""}),
                "save_file": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "include_comments": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "filename_label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("gcode_text", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = GCODE_EXPORT

    def run(
        self,
        plan: Dict[str, Any],
        profile: Dict[str, Any],
        filename_prefix: str = "MKR_gcode",
        subfolder: str = "",
        save_file: bool = True,
        overwrite: bool = False,
        include_comments: bool = True,
        filename_label: str = "",
    ):
        if not isinstance(plan, dict):
            return ("", "", _json_text({"warnings": ["plan input is invalid"]}))
        if not isinstance(profile, dict):
            return ("", "", _json_text({"warnings": ["profile input is invalid"]}))

        gcode_text, stats = _build_gcode(plan, profile, include_comments=bool(include_comments))
        warnings: List[str] = []
        output_path = ""
        if bool(save_file) and gcode_text:
            out_dir = _output_dir(subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = _sanitize_basename(filename_label or filename_prefix, "MKR_gcode")
            target = _resolve_output_file(out_dir=out_dir, stem=stem, ext="gcode", overwrite=bool(overwrite))
            try:
                target.write_text(gcode_text, encoding="utf-8")
                output_path = str(target)
            except Exception as exc:
                warnings.append(f"Failed to write gcode file: {exc}")

        summary = {
            "output_path": output_path,
            "mode": str(plan.get("mode", "unknown")),
            "line_count": int(stats.get("line_count", 0)),
            "extrusion_mm": float(stats.get("extrusion_mm", 0.0)),
            "estimated_time_min": float(stats.get("estimated_time_min", 0.0)),
            "warnings": warnings,
        }
        return (gcode_text, output_path, _json_text(summary))
