import json
from typing import Any, Dict, List, Optional

from ..categories import GCODE_ANALYZE
from ..lib.gcode_shared import (
    _bed_fit_report,
    _distance_mm,
    _estimate_material_usage,
    _json_text,
    _layer_summaries,
    _normalize_profile,
    _plan_stats,
)
from ..lib.settings_bundle import parse_settings_payload


class MKRGCodePlanAnalyzer:
    SEARCH_ALIASES = ["gcode analyzer", "failure analyzer", "print estimator", "toolpath analysis"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "max_volumetric_flow_mm3_s": 12.0,
            "min_feature_mm": 0.3,
            "min_layer_time_s": 8.0,
            "warn_travel_ratio_percent": 35.0,
            "warn_bed_usage_percent": 75.0,
            "filament_price_per_kg": 20.0,
            "material_density_g_cm3": 1.24,
            "printer_wattage_w": 120.0,
            "electricity_price_per_kwh": 0.20,
            "warn_total_cost": 12.0,
        }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
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

    RETURN_TYPES = ("MKR_GCODE_PLAN", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("plan", "analysis_json", "warnings_json", "summary")
    FUNCTION = "analyze"
    CATEGORY = GCODE_ANALYZE

    def analyze(
        self,
        plan: Dict[str, Any],
        settings_json: str = "{}",
        profile: Optional[Dict[str, Any]] = None,
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "max_volumetric_flow_mm3_s": {"min": 0.5, "max": 80.0},
                "min_feature_mm": {"min": 0.05, "max": 10.0},
                "min_layer_time_s": {"min": 0.0, "max": 300.0},
                "warn_travel_ratio_percent": {"min": 0.0, "max": 100.0},
                "warn_bed_usage_percent": {"min": 0.0, "max": 100.0},
                "filament_price_per_kg": {"min": 0.0, "max": 500.0},
                "material_density_g_cm3": {"min": 0.1, "max": 10.0},
                "printer_wattage_w": {"min": 0.0, "max": 5000.0},
                "electricity_price_per_kwh": {"min": 0.0, "max": 5.0},
                "warn_total_cost": {"min": 0.0, "max": 10000.0},
            },
            legacy=legacy_settings,
        )
        if not isinstance(plan, dict):
            warnings = ["plan input is invalid"]
            return ({}, _json_text({"warnings": warnings}), _json_text({"warnings": warnings}), "Invalid G-code plan")

        moves = plan.get("moves", []) if isinstance(plan.get("moves"), list) else []
        stats = dict(plan.get("stats", {})) if isinstance(plan.get("stats"), dict) else _plan_stats(moves)
        layers = _layer_summaries(moves)
        normalized_profile = _normalize_profile(profile)
        material = _estimate_material_usage(plan, normalized_profile, density_g_cm3=settings["material_density_g_cm3"])

        peak_flow = 0.0
        avg_flow = 0.0
        print_volume_mm3 = 0.0
        print_time_s = 0.0
        tiny_feature_count = 0
        for idx in range(1, len(moves)):
            prev = moves[idx - 1]
            cur = moves[idx]
            if not bool(cur.get("extrude", False)):
                continue
            dist = _distance_mm(prev, cur)
            if dist <= 0.0:
                continue
            line_width = float(max(0.1, cur.get("line_width", normalized_profile.get("lineWidth", 0.45))))
            layer_height = float(max(0.01, cur.get("layer_height", normalized_profile.get("layerHeight", 0.2))))
            speed = float(max(0.1, cur.get("speed_mm_s", 1.0)))
            segment_volume = dist * line_width * layer_height * float(normalized_profile.get("extrusionMult", 1.0) or 1.0)
            segment_time = dist / speed
            flow = segment_volume / max(1e-9, segment_time)
            peak_flow = max(peak_flow, flow)
            print_volume_mm3 += segment_volume
            print_time_s += segment_time
            if dist < float(settings["min_feature_mm"]):
                tiny_feature_count += 1
        if print_time_s > 1e-9:
            avg_flow = print_volume_mm3 / print_time_s

        estimated_time_min = float(stats.get("estimated_time_min", 0.0) or 0.0)
        energy_kwh = (float(settings["printer_wattage_w"]) * (estimated_time_min / 60.0)) / 1000.0
        material_cost = (float(material.get("mass_g", 0.0)) / 1000.0) * float(settings["filament_price_per_kg"])
        energy_cost = energy_kwh * float(settings["electricity_price_per_kwh"])
        travel_ratio = 0.0
        path_length = float(stats.get("path_length_mm", 0.0) or 0.0)
        if path_length > 1e-9:
            travel_ratio = (float(stats.get("travel_length_mm", 0.0) or 0.0) / path_length) * 100.0

        bounds = plan.get("bounds", {}) if isinstance(plan.get("bounds"), dict) else {}
        bed_area = float(normalized_profile.get("bedW", 0.0)) * float(normalized_profile.get("bedD", 0.0))
        used_area = max(0.0, float(bounds.get("max_x", 0.0)) - float(bounds.get("min_x", 0.0))) * max(
            0.0,
            float(bounds.get("max_y", 0.0)) - float(bounds.get("min_y", 0.0)),
        )
        bed_usage_percent = (used_area / bed_area) * 100.0 if bed_area > 1e-9 else 0.0

        short_layers = [
            {
                "layer": int(entry["layer"]),
                "estimated_time_s": float(entry["estimated_time_s"]),
            }
            for entry in layers
            if float(entry.get("print_length_mm", 0.0)) > 0.0 and float(entry.get("estimated_time_s", 0.0)) < float(settings["min_layer_time_s"])
        ]

        warnings: List[str] = []
        if len(moves) < 2:
            warnings.append("Toolpath is empty.")
        if peak_flow > float(settings["max_volumetric_flow_mm3_s"]):
            warnings.append(
                f"Peak volumetric flow {peak_flow:.2f} mm^3/s exceeds limit {float(settings['max_volumetric_flow_mm3_s']):.2f} mm^3/s."
            )
        if tiny_feature_count > 0:
            warnings.append(f"{tiny_feature_count} extrude segments are shorter than {float(settings['min_feature_mm']):.2f} mm.")
        if short_layers:
            warnings.append(
                f"{len(short_layers)} layers are below the minimum layer time of {float(settings['min_layer_time_s']):.1f} s."
            )
        if travel_ratio > float(settings["warn_travel_ratio_percent"]):
            warnings.append(
                f"Travel ratio {travel_ratio:.1f}% exceeds warning threshold {float(settings['warn_travel_ratio_percent']):.1f}%."
            )
        if bed_usage_percent > float(settings["warn_bed_usage_percent"]):
            warnings.append(
                f"Bed usage {bed_usage_percent:.1f}% exceeds warning threshold {float(settings['warn_bed_usage_percent']):.1f}%."
            )

        bed_fit = _bed_fit_report(plan, normalized_profile)
        if not bool(bed_fit.get("fits_xy", True)):
            warnings.append("Placed footprint exceeds the configured bed size.")
        if not bool(bed_fit.get("fits_z", True)):
            warnings.append("Placed height exceeds the configured Z clearance.")
        if (material_cost + energy_cost) > float(settings["warn_total_cost"]):
            warnings.append(
                f"Estimated total cost {material_cost + energy_cost:.2f} exceeds warning threshold {float(settings['warn_total_cost']):.2f}."
            )

        analysis = {
            "mode": str(plan.get("mode", "unknown")),
            "stats": stats,
            "layers": layers,
            "flow_estimate": {
                "peak_volumetric_flow_mm3_s": float(round(peak_flow, 5)),
                "avg_volumetric_flow_mm3_s": float(round(avg_flow, 5)),
                "threshold_mm3_s": float(round(float(settings["max_volumetric_flow_mm3_s"]), 5)),
                "tiny_feature_count": int(tiny_feature_count),
                "min_feature_mm": float(round(float(settings["min_feature_mm"]), 5)),
            },
            "bed_fit": bed_fit,
            "bed_usage_percent": float(round(bed_usage_percent, 5)),
            "material_estimate": material,
            "cost_estimate": {
                "filament_price_per_kg": float(round(float(settings["filament_price_per_kg"]), 5)),
                "material_cost": float(round(material_cost, 5)),
                "printer_wattage_w": float(round(float(settings["printer_wattage_w"]), 5)),
                "electricity_price_per_kwh": float(round(float(settings["electricity_price_per_kwh"]), 5)),
                "energy_kwh": float(round(energy_kwh, 5)),
                "energy_cost": float(round(energy_cost, 5)),
                "total_cost": float(round(material_cost + energy_cost, 5)),
                "warn_total_cost": float(round(float(settings["warn_total_cost"]), 5)),
            },
            "warnings": warnings,
            "short_layer_alerts": short_layers[:24],
        }
        summary = (
            f"Analyzer | {int(stats.get('layer_count', 0))} layers | "
            f"{estimated_time_min:.1f} min | {float(material.get('mass_g', 0.0)):.1f} g | {len(warnings)} warnings"
        )
        return (plan, _json_text(analysis), _json_text({"warnings": warnings}), summary)
