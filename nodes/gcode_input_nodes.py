import json
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image
import torch

from ..categories import GCODE_INPUT, GCODE_PRINTER
from ..lib.gcode_mesh import _bed_align_mesh, _center_mesh_xy, _load_mesh_file, _render_mesh_preview, _transform_mesh
from ..lib.gcode_shared import _json_text, _normalize_profile, _pil_to_batch
from ..lib.settings_bundle import parse_settings_payload
from ..lib.gcode_slicer import (
    _build_prusa_orca_config_text,
    _load_orca_profiles,
    _map_orca_to_profile,
    _orca_flat_settings,
    _select_orca_entry,
)


def _empty_preview(size: int = 768) -> torch.Tensor:
    return _pil_to_batch([Image.new("RGB", (size, size), (18, 19, 22))])


class MKRGCodeOrcaProfileLoader:
    SEARCH_ALIASES = ["orca profile", "orca preset", "orca bundle", "orca slicer config"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_path": ("STRING", {"default": ""}),
                "printer_match": ("STRING", {"default": ""}),
                "filament_match": ("STRING", {"default": ""}),
                "process_match": ("STRING", {"default": ""}),
                "selection_mode": (["auto", "id_or_name_exact", "substring"], {"default": "auto"}),
                "recursive": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("MKR_GCODE_PROFILE", "MKR_GCODE_SLICER_SETTINGS", "STRING", "STRING")
    RETURN_NAMES = ("profile", "slicer_settings", "bundle_json", "summary")
    FUNCTION = "load"
    CATEGORY = GCODE_PRINTER

    def load(
        self,
        source_path: str = "",
        printer_match: str = "",
        filament_match: str = "",
        process_match: str = "",
        selection_mode: str = "auto",
        recursive: bool = True,
    ):
        warnings = []
        if not str(source_path or "").strip():
            warnings.append("source_path is empty")
            profile = _normalize_profile(None)
            settings = {
                "schema": "mkr_gcode_slicer_settings_v1",
                "source": "orca",
                "engine_family": "prusa_orca",
                "config": {},
                "config_text": "",
            }
            payload = {"warnings": warnings, "counts": {"printers": 0, "filaments": 0, "processes": 0}}
            return (profile, settings, _json_text(payload), "Orca loader | no source path")

        store = _load_orca_profiles(source_path, recursive=bool(recursive))
        printer_entry = _select_orca_entry(store["printers"], printer_match, selection_mode)
        filament_entry = _select_orca_entry(store["filaments"], filament_match, selection_mode)
        process_entry = _select_orca_entry(store["processes"], process_match, selection_mode)

        profile = _map_orca_to_profile(
            printer_entry["obj"] if printer_entry else None,
            filament_entry["obj"] if filament_entry else None,
            process_entry["obj"] if process_entry else None,
            _normalize_profile(None),
        )
        config = _orca_flat_settings(
            printer_entry["obj"] if printer_entry else None,
            filament_entry["obj"] if filament_entry else None,
            process_entry["obj"] if process_entry else None,
        )
        settings = {
            "schema": "mkr_gcode_slicer_settings_v1",
            "source": "orca",
            "engine_family": "prusa_orca",
            "config": config,
            "config_text": _build_prusa_orca_config_text({"config": config}, profile),
            "machine": printer_entry["obj"] if printer_entry else {},
            "filament": filament_entry["obj"] if filament_entry else {},
            "process": process_entry["obj"] if process_entry else {},
        }
        if not printer_entry:
            warnings.append("No Orca printer preset matched; using generic fallback profile")
        payload = {
            "source_path": str(source_path),
            "counts": {
                "printers": int(len(store["printers"])),
                "filaments": int(len(store["filaments"])),
                "processes": int(len(store["processes"])),
            },
            "selected": {
                "printer": printer_entry["name"] if printer_entry else "",
                "filament": filament_entry["name"] if filament_entry else "",
                "process": process_entry["name"] if process_entry else "",
            },
            "warnings": warnings,
        }
        summary = (
            f"Orca loader | printers {len(store['printers'])} | "
            f"{payload['selected']['printer'] or profile['name']} | warnings {len(warnings)}"
        )
        return (profile, settings, _json_text(payload), summary)


class MKRGCodeLoadMeshModel:
    SEARCH_ALIASES = ["load stl", "load obj", "import mesh", "3d model loader", "mesh import"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "model_path": "",
            "center_xy": True,
            "bed_align": True,
            "scale": 1.0,
            "target_longest_mm": 0.0,
            "rotate_x_deg": 0.0,
            "rotate_y_deg": 0.0,
            "rotate_z_deg": 0.0,
            "translate_x_mm": 0.0,
            "translate_y_mm": 0.0,
            "translate_z_mm": 0.0,
            "preview_view": "isometric",
            "preview_size": 768,
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

    RETURN_TYPES = ("MKR_GCODE_MESH", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("mesh", "preview", "mesh_info_json", "summary")
    FUNCTION = "load"
    CATEGORY = GCODE_INPUT

    def load(
        self,
        settings_json: str = "{}",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "scale": {"min": 0.001, "max": 1000.0},
                "target_longest_mm": {"min": 0.0, "max": 4000.0},
                "rotate_x_deg": {"min": -360.0, "max": 360.0},
                "rotate_y_deg": {"min": -360.0, "max": 360.0},
                "rotate_z_deg": {"min": -360.0, "max": 360.0},
                "translate_x_mm": {"min": -1000.0, "max": 1000.0},
                "translate_y_mm": {"min": -1000.0, "max": 1000.0},
                "translate_z_mm": {"min": -1000.0, "max": 1000.0},
                "preview_size": {"min": 128, "max": 2048, "integer": True},
            },
            boolean_keys={"center_xy", "bed_align"},
            legacy=legacy_settings,
        )
        preview_view = str(settings.get("preview_view", "isometric") or "isometric")
        if preview_view not in {"isometric", "top"}:
            preview_view = "isometric"
        warnings = []
        try:
            path = Path(str(settings["model_path"] or "")).expanduser()
            mesh = _load_mesh_file(path)
            if bool(settings["center_xy"]):
                mesh = _center_mesh_xy(mesh)
            mesh = _transform_mesh(
                mesh,
                scale=float(settings["scale"]),
                rotate_x_deg=float(settings["rotate_x_deg"]),
                rotate_y_deg=float(settings["rotate_y_deg"]),
                rotate_z_deg=float(settings["rotate_z_deg"]),
                translate_x_mm=0.0,
                translate_y_mm=0.0,
                translate_z_mm=0.0,
            )
            target_longest = float(settings["target_longest_mm"])
            if target_longest > 1e-6:
                bounds = mesh.get("bounds", {}) if isinstance(mesh.get("bounds"), dict) else {}
                longest = max(
                    float(bounds.get("max_x", 0.0)) - float(bounds.get("min_x", 0.0)),
                    float(bounds.get("max_y", 0.0)) - float(bounds.get("min_y", 0.0)),
                    float(bounds.get("max_z", 0.0)) - float(bounds.get("min_z", 0.0)),
                )
                if longest > 1e-6:
                    mesh = _transform_mesh(mesh, scale=(target_longest / longest))
            mesh = _transform_mesh(
                mesh,
                scale=1.0,
                translate_x_mm=float(settings["translate_x_mm"]),
                translate_y_mm=float(settings["translate_y_mm"]),
                translate_z_mm=float(settings["translate_z_mm"]),
            )
            if bool(settings["bed_align"]):
                mesh = _bed_align_mesh(mesh)
            preview = _pil_to_batch([_render_mesh_preview(mesh, size=int(settings["preview_size"]), view_mode=preview_view)])
            info = {
                "source_path": str(path),
                "tri_count": int(mesh.get("tri_count", 0)),
                "bounds": mesh.get("bounds", {}),
                "meta": mesh.get("meta", {}),
                "warnings": warnings,
            }
            summary = (
                f"Mesh load | {path.name} | tris {int(mesh.get('tri_count', 0))} | "
                f"{mesh.get('bounds', {}).get('max_z', 0.0):.1f} mm tall"
            )
            return (mesh, preview, _json_text(info), summary)
        except Exception as exc:
            warnings.append(str(exc))
            info = {"source_path": str(settings.get("model_path", "")), "warnings": warnings}
            return ({}, _empty_preview(int(settings["preview_size"])), _json_text(info), "Mesh load failed")
