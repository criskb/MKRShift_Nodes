import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ..categories import GCODE_SLICE
from ..lib.gcode_mesh import _mesh_to_ascii_stl
from ..lib.gcode_shared import _json_text
from ..lib.gcode_slicer import (
    _build_external_command,
    _plan_from_gcode_text,
    _run_slicer_command,
)
from .presave_image_nodes import _output_dir, _resolve_output_file, _sanitize_basename


class MKRGCodeExternalSlicer:
    SEARCH_ALIASES = ["slicer", "orca slicer", "prusa slicer", "cura engine", "slice mesh"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mesh": ("MKR_GCODE_MESH", {"forceInput": True}),
                "engine": (["orca", "prusa", "cura"], {"default": "orca"}),
                "engine_path": ("STRING", {"default": ""}),
                "engine_args_text": ("STRING", {"default": "", "multiline": True}),
                "filename_prefix": ("STRING", {"default": "MKR_sliced"}),
                "subfolder": ("STRING", {"default": ""}),
                "save_file": ("BOOLEAN", {"default": False}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "dry_run": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
                "slicer_settings": ("MKR_GCODE_SLICER_SETTINGS", {"forceInput": True}),
                "settings_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "MKR_GCODE_PLAN", "STRING", "STRING")
    RETURN_NAMES = ("gcode_text", "plan", "output_path", "summary")
    FUNCTION = "run"
    CATEGORY = GCODE_SLICE

    def run(
        self,
        mesh: Dict[str, Any],
        engine: str = "orca",
        engine_path: str = "",
        engine_args_text: str = "",
        filename_prefix: str = "MKR_sliced",
        subfolder: str = "",
        save_file: bool = False,
        overwrite: bool = False,
        dry_run: bool = True,
        profile: Optional[Dict[str, Any]] = None,
        slicer_settings: Optional[Dict[str, Any]] = None,
        settings_json: str = "",
    ):
        warnings = []
        if not isinstance(mesh, dict) or not isinstance(mesh.get("tris"), list) or len(mesh.get("tris", [])) < 9:
            warnings.append("mesh input is invalid")
            return ("", {}, "", _json_text({"warnings": warnings}))

        settings_payload: Dict[str, Any] = {}
        if isinstance(slicer_settings, dict):
            settings_payload.update(slicer_settings)
        if str(settings_json or "").strip():
            try:
                parsed = json.loads(settings_json)
                if isinstance(parsed, dict):
                    merged_config = dict(settings_payload.get("config", {})) if isinstance(settings_payload.get("config"), dict) else {}
                    merged_config.update(parsed)
                    settings_payload["config"] = merged_config
            except Exception as exc:
                warnings.append(f"Invalid settings_json: {exc}")

        output_path = ""
        save_target: Optional[Path] = None
        if bool(save_file):
            out_dir = _output_dir(subfolder)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = _sanitize_basename(filename_prefix, "MKR_sliced")
            save_target = _resolve_output_file(out_dir=out_dir, stem=stem, ext="gcode", overwrite=bool(overwrite))
            output_path = str(save_target)

        with tempfile.TemporaryDirectory(prefix="mkr_gcode_slice_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            input_path = tmp_root / "input.stl"
            config_path = tmp_root / "config.ini"
            temp_output_path = save_target if save_target else (tmp_root / "output.gcode")
            input_path.write_text(_mesh_to_ascii_stl(mesh, name="mkr_mesh"), encoding="utf-8")

            command, config_text = _build_external_command(
                engine=engine,
                engine_path=engine_path,
                engine_args_text=engine_args_text,
                input_path=input_path,
                output_path=temp_output_path,
                config_path=config_path,
                settings=settings_payload,
                profile=profile,
            )
            if config_text.strip():
                config_path.write_text(config_text, encoding="utf-8")

            result = _run_slicer_command(
                command=command,
                config_text=config_text,
                output_path=temp_output_path,
                save_target=save_target if save_file else None,
                dry_run=bool(dry_run),
            )

        gcode_text = str(result.get("gcode_text", "") or "")
        if not bool(save_file):
            output_path = ""
        elif result.get("output_path"):
            output_path = str(result.get("output_path"))
        summary = dict(result.get("summary", {})) if isinstance(result.get("summary"), dict) else {}
        summary.setdefault("engine", str(engine))
        summary.setdefault("warnings", [])
        summary["warnings"] = list(summary.get("warnings", [])) + warnings
        plan = _plan_from_gcode_text(gcode_text, profile) if gcode_text else {}
        if gcode_text:
            summary["parsed_plan_stats"] = plan.get("stats", {})
        return (gcode_text, plan, output_path, _json_text(summary))
