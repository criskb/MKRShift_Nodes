import math
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
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
from .presave_image_nodes import _output_dir, _resolve_output_file, _sanitize_basename


class MKRGCodePrinterProfile:
    SEARCH_ALIASES = ["3d printer profile", "fdm profile", "gcode printer"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "printer_name": ("STRING", {"default": "Generic FDM"}),
                "bed_width_mm": ("FLOAT", {"default": 220.0, "min": 50.0, "max": 1000.0, "step": 1.0}),
                "bed_depth_mm": ("FLOAT", {"default": 220.0, "min": 50.0, "max": 1000.0, "step": 1.0}),
                "bed_height_mm": ("FLOAT", {"default": 250.0, "min": 50.0, "max": 1500.0, "step": 1.0}),
                "origin": (["center", "lower_left"], {"default": "center"}),
                "nozzle_diameter_mm": ("FLOAT", {"default": 0.4, "min": 0.1, "max": 2.0, "step": 0.01}),
                "line_width_mm": ("FLOAT", {"default": 0.45, "min": 0.1, "max": 2.4, "step": 0.01}),
                "layer_height_mm": ("FLOAT", {"default": 0.2, "min": 0.05, "max": 1.0, "step": 0.01}),
                "filament_diameter_mm": ("FLOAT", {"default": 1.75, "min": 1.0, "max": 3.0, "step": 0.01}),
                "extrusion_multiplier": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01}),
                "nozzle_temp_c": ("INT", {"default": 210, "min": 0, "max": 400, "step": 1}),
                "bed_temp_c": ("INT", {"default": 60, "min": 0, "max": 150, "step": 1}),
                "print_speed_mm_s": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 400.0, "step": 0.5}),
                "travel_speed_mm_s": ("FLOAT", {"default": 100.0, "min": 1.0, "max": 500.0, "step": 0.5}),
                "retraction_mm": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 20.0, "step": 0.1}),
                "retraction_speed_mm_s": ("FLOAT", {"default": 35.0, "min": 1.0, "max": 200.0, "step": 0.5}),
                "travel_z_mm": ("FLOAT", {"default": 0.6, "min": 0.1, "max": 10.0, "step": 0.05}),
                "home_before_print": ("BOOLEAN", {"default": True}),
                "prime_line": ("BOOLEAN", {"default": True}),
                "start_gcode": ("STRING", {"default": "M104 S210\nM140 S60\nG28\nG92 E0", "multiline": True}),
                "end_gcode": ("STRING", {"default": "M104 S0\nM140 S0\nG28 X0\nM84", "multiline": True}),
            }
        }

    RETURN_TYPES = ("MKR_GCODE_PROFILE", "STRING", "STRING")
    RETURN_NAMES = ("profile", "profile_json", "summary")
    FUNCTION = "build"
    CATEGORY = GCODE_PRINTER

    def build(
        self,
        printer_name: str = "Generic FDM",
        bed_width_mm: float = 220.0,
        bed_depth_mm: float = 220.0,
        bed_height_mm: float = 250.0,
        origin: str = "center",
        nozzle_diameter_mm: float = 0.4,
        line_width_mm: float = 0.45,
        layer_height_mm: float = 0.2,
        filament_diameter_mm: float = 1.75,
        extrusion_multiplier: float = 1.0,
        nozzle_temp_c: int = 210,
        bed_temp_c: int = 60,
        print_speed_mm_s: float = 30.0,
        travel_speed_mm_s: float = 100.0,
        retraction_mm: float = 0.8,
        retraction_speed_mm_s: float = 35.0,
        travel_z_mm: float = 0.6,
        home_before_print: bool = True,
        prime_line: bool = True,
        start_gcode: str = "M104 S210\nM140 S60\nG28\nG92 E0",
        end_gcode: str = "M104 S0\nM140 S0\nG28 X0\nM84",
    ):
        profile = _normalize_profile(
            {
                "name": printer_name,
                "bedW": bed_width_mm,
                "bedD": bed_depth_mm,
                "bedH": bed_height_mm,
                "origin": origin,
                "nozzle": nozzle_diameter_mm,
                "lineWidth": line_width_mm,
                "layerHeight": layer_height_mm,
                "filamentDia": filament_diameter_mm,
                "extrusionMult": extrusion_multiplier,
                "tempNozzle": nozzle_temp_c,
                "tempBed": bed_temp_c,
                "speedPrint": float(print_speed_mm_s) * 60.0,
                "speedTravel": float(travel_speed_mm_s) * 60.0,
                "retractionMm": retraction_mm,
                "retractionSpeed": retraction_speed_mm_s,
                "travelZ": travel_z_mm,
                "homeBeforePrint": home_before_print,
                "primeLine": prime_line,
                "startGcode": start_gcode,
                "endGcode": end_gcode,
            }
        )
        summary = (
            f"{profile['name']} | {profile['bedW']:.0f}x{profile['bedD']:.0f}x{profile['bedH']:.0f} mm | "
            f"nozzle {profile['nozzle']:.2f} | layer {profile['layerHeight']:.2f}"
        )
        return (profile, _json_text(profile), summary)


class MKRGCodeHeightmapPlate:
    SEARCH_ALIASES = ["lithophane", "heightmap gcode", "relief print", "image to gcode"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "width_mm": ("FLOAT", {"default": 80.0, "min": 10.0, "max": 400.0, "step": 1.0}),
                "height_mm": ("FLOAT", {"default": 80.0, "min": 10.0, "max": 400.0, "step": 1.0}),
                "base_layers": ("INT", {"default": 3, "min": 1, "max": 40, "step": 1}),
                "relief_height_mm": ("FLOAT", {"default": 1.6, "min": 0.1, "max": 20.0, "step": 0.05}),
                "layer_height_mm": ("FLOAT", {"default": 0.2, "min": 0.05, "max": 1.0, "step": 0.01}),
                "line_width_mm": ("FLOAT", {"default": 0.45, "min": 0.1, "max": 2.0, "step": 0.01}),
                "fill_mode": (["alternate_xy", "x_only", "y_only"], {"default": "alternate_xy"}),
                "invert_heightmap": ("BOOLEAN", {"default": False}),
                "mirror_x": ("BOOLEAN", {"default": False}),
                "mirror_y": ("BOOLEAN", {"default": False}),
                "print_speed_mm_s": ("FLOAT", {"default": 28.0, "min": 1.0, "max": 300.0, "step": 0.5}),
                "travel_speed_mm_s": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 500.0, "step": 0.5}),
                "use_profile_defaults": ("BOOLEAN", {"default": False}),
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
        width_mm: float = 80.0,
        height_mm: float = 80.0,
        base_layers: int = 3,
        relief_height_mm: float = 1.6,
        layer_height_mm: float = 0.2,
        line_width_mm: float = 0.45,
        fill_mode: str = "alternate_xy",
        invert_heightmap: bool = False,
        mirror_x: bool = False,
        mirror_y: bool = False,
        print_speed_mm_s: float = 28.0,
        travel_speed_mm_s: float = 120.0,
        use_profile_defaults: bool = False,
        profile: Optional[Dict[str, Any]] = None,
    ):
        layer_height, line_width, print_speed, travel_speed = _resolve_plan_settings(
            profile,
            use_profile_defaults,
            layer_height_mm,
            line_width_mm,
            print_speed_mm_s,
            travel_speed_mm_s,
        )

        src = _first_pil(image).convert("L")
        cols = max(4, int(round(float(width_mm) / max(0.1, line_width))) + 1)
        rows = max(4, int(round(float(height_mm) / max(0.1, line_width))) + 1)
        sampled = src.resize((cols, rows), resample=Image.Resampling.BILINEAR)
        grid = np.asarray(sampled, dtype=np.float32) / 255.0
        if bool(mirror_x):
            grid = np.fliplr(grid)
        if bool(mirror_y):
            grid = np.flipud(grid)
        if bool(invert_heightmap):
            grid = 1.0 - grid

        base_h = int(max(1, base_layers)) * layer_height
        heights = base_h + np.clip(grid, 0.0, 1.0) * float(max(0.1, relief_height_mm))
        layer_count = max(1, int(math.ceil(float(np.max(heights)) / layer_height)))
        dx = float(width_mm) / float(max(1, cols - 1))
        dy = float(height_mm) / float(max(1, rows - 1))

        moves: List[Dict[str, Any]] = []
        for layer_idx in range(layer_count):
            z = float((layer_idx + 1) * layer_height)
            scan_x = str(fill_mode) == "x_only" or (str(fill_mode) == "alternate_xy" and (layer_idx % 2 == 0))
            role = "base" if layer_idx < int(base_layers) else "relief"
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
                "width_mm": float(width_mm),
                "height_mm": float(height_mm),
                "base_layers": int(base_layers),
                "relief_height_mm": float(relief_height_mm),
                "fill_mode": str(fill_mode),
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
            f"Heightmap plate {float(width_mm):.0f}x{float(height_mm):.0f} mm | "
            f"{plan['stats']['layer_count']} layers | {plan['stats']['print_moves']} print moves"
        )
        return (plan, _pil_to_batch([preview]), _json_text(info), summary)


class MKRGCodeSpiralVase:
    SEARCH_ALIASES = ["vase mode", "spiral vase", "helical print", "procedural vase"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "height_mm": ("FLOAT", {"default": 120.0, "min": 10.0, "max": 500.0, "step": 1.0}),
                "base_radius_mm": ("FLOAT", {"default": 28.0, "min": 2.0, "max": 250.0, "step": 0.5}),
                "top_radius_mm": ("FLOAT", {"default": 24.0, "min": 2.0, "max": 250.0, "step": 0.5}),
                "bottom_layers": ("INT", {"default": 3, "min": 0, "max": 30, "step": 1}),
                "layer_height_mm": ("FLOAT", {"default": 0.2, "min": 0.05, "max": 1.0, "step": 0.01}),
                "line_width_mm": ("FLOAT", {"default": 0.45, "min": 0.1, "max": 2.0, "step": 0.01}),
                "segments_per_turn": ("INT", {"default": 72, "min": 12, "max": 720, "step": 1}),
                "wave_amplitude_mm": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 30.0, "step": 0.1}),
                "wave_frequency": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 50.0, "step": 0.1}),
                "print_speed_mm_s": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 300.0, "step": 0.5}),
                "travel_speed_mm_s": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 500.0, "step": 0.5}),
                "use_profile_defaults": ("BOOLEAN", {"default": False}),
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
        height_mm: float = 120.0,
        base_radius_mm: float = 28.0,
        top_radius_mm: float = 24.0,
        bottom_layers: int = 3,
        layer_height_mm: float = 0.2,
        line_width_mm: float = 0.45,
        segments_per_turn: int = 72,
        wave_amplitude_mm: float = 0.0,
        wave_frequency: float = 0.0,
        print_speed_mm_s: float = 24.0,
        travel_speed_mm_s: float = 120.0,
        use_profile_defaults: bool = False,
        profile: Optional[Dict[str, Any]] = None,
    ):
        layer_height, line_width, print_speed, travel_speed = _resolve_plan_settings(
            profile,
            use_profile_defaults,
            layer_height_mm,
            line_width_mm,
            print_speed_mm_s,
            travel_speed_mm_s,
        )

        base_radius = float(max(2.0, base_radius_mm))
        top_radius = float(max(2.0, top_radius_mm))
        total_h = float(max(layer_height, height_mm))
        base_h = float(max(0, int(bottom_layers))) * layer_height
        wall_h = max(layer_height, total_h - base_h)
        seg_turn = max(12, int(segments_per_turn))

        moves: List[Dict[str, Any]] = []
        base_turns = max(1, int(math.ceil(base_radius / max(0.1, line_width))))
        for layer_idx in range(max(0, int(bottom_layers))):
            z = float((layer_idx + 1) * layer_height)
            steps = max(12, base_turns * seg_turn)
            for step in range(steps + 1):
                u = float(step) / float(steps)
                theta = u * base_turns * math.pi * 2.0
                r = max(line_width * 0.5, u * max(line_width, base_radius - line_width * 0.5))
                x = r * math.cos(theta)
                y = r * math.sin(theta)
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
        wall_start_layer = max(0, int(bottom_layers))
        for step in range(wall_steps + 1):
            u = float(step) / float(wall_steps)
            theta = u * wall_turns * math.pi * 2.0
            radius = (1.0 - u) * base_radius + u * top_radius
            if float(wave_amplitude_mm) > 1e-6 and float(wave_frequency) > 1e-6:
                radius += float(wave_amplitude_mm) * math.sin(u * float(wave_frequency) * math.pi * 2.0)
            radius = max(line_width * 0.75, radius)
            z = base_h + (u * wall_h)
            x = radius * math.cos(theta)
            y = radius * math.sin(theta)
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
                "bottom_layers": int(bottom_layers),
                "wave_amplitude_mm": float(wave_amplitude_mm),
                "wave_frequency": float(wave_frequency),
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
