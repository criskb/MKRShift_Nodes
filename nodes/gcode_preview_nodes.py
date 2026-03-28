import json
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw

from ..categories import GCODE_PREVIEW
from ..lib.gcode_mesh import _render_mesh_preview
from ..lib.gcode_shared import _json_text, _pil_to_batch, _render_plan_preview
from ..lib.settings_bundle import parse_settings_payload
from ..lib.gcode_slicer import _plan_from_gcode_text


def _blank_preview(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size), (18, 19, 22))
    draw = ImageDraw.Draw(image)
    draw.text((24, 24), "No preview input", fill=(220, 220, 220))
    return image


def _load_gcode_text(gcode_text: str, gcode_path: str) -> str:
    if str(gcode_text or "").strip():
        return str(gcode_text)
    path = Path(str(gcode_path or "").strip()).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _combine_split(left: Image.Image, right: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (left.width + right.width, max(left.height, right.height)), (12, 14, 18))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((left.width, 0, left.width, canvas.height), fill=(56, 68, 84), width=2)
    return canvas


class MKRGCodePreview:
    SEARCH_ALIASES = ["gcode preview", "toolpath preview", "mesh preview", "3d print preview"]

    @staticmethod
    def _default_settings() -> Dict[str, Any]:
        return {
            "view_mode": "auto",
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
            },
            "optional": {
                "plan": ("MKR_GCODE_PLAN", {"forceInput": True}),
                "mesh": ("MKR_GCODE_MESH", {"forceInput": True}),
                "profile": ("MKR_GCODE_PROFILE", {"forceInput": True}),
                "gcode_text": ("STRING", {"default": "", "multiline": True}),
                "gcode_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "MKR_GCODE_PLAN")
    RETURN_NAMES = ("preview", "preview_info_json", "summary", "plan")
    FUNCTION = "run"
    CATEGORY = GCODE_PREVIEW

    def run(
        self,
        settings_json: str = "{}",
        plan: Optional[Dict[str, Any]] = None,
        mesh: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
        gcode_text: str = "",
        gcode_path: str = "",
        **legacy_settings,
    ):
        settings = parse_settings_payload(
            settings_json=settings_json,
            defaults=self._default_settings(),
            numeric_specs={
                "preview_size": {"min": 128, "max": 2048, "integer": True},
            },
            legacy=legacy_settings,
        )
        warnings = []
        parsed_plan = plan if isinstance(plan, dict) else None
        source_gcode = _load_gcode_text(gcode_text, gcode_path)
        if parsed_plan is None and source_gcode:
            parsed_plan = _plan_from_gcode_text(source_gcode, profile)
        mode = str(settings.get("view_mode", "auto") or "auto").strip().lower()
        preview_size = int(settings.get("preview_size", 768) or 768)
        if mode == "auto":
            if parsed_plan and isinstance(mesh, dict) and mesh.get("tris"):
                mode = "split"
            elif parsed_plan:
                mode = "plan_top"
            elif isinstance(mesh, dict) and mesh.get("tris"):
                mode = "mesh_isometric"
            else:
                mode = "blank"

        if mode == "plan_top" and parsed_plan:
            preview_image = _render_plan_preview(parsed_plan, size=int(preview_size))
        elif mode == "mesh_top" and isinstance(mesh, dict) and mesh.get("tris"):
            preview_image = _render_mesh_preview(mesh, size=int(preview_size), view_mode="top")
        elif mode == "mesh_isometric" and isinstance(mesh, dict) and mesh.get("tris"):
            preview_image = _render_mesh_preview(mesh, size=int(preview_size), view_mode="isometric")
        elif mode == "split" and parsed_plan and isinstance(mesh, dict) and mesh.get("tris"):
            left = _render_plan_preview(parsed_plan, size=int(preview_size))
            right = _render_mesh_preview(mesh, size=int(preview_size), view_mode="isometric")
            preview_image = _combine_split(left, right)
        else:
            preview_image = _blank_preview(int(preview_size))
            warnings.append("No valid plan, gcode, or mesh input was available for preview")

        info = {
            "view_mode": mode,
            "plan_stats": parsed_plan.get("stats", {}) if isinstance(parsed_plan, dict) else {},
            "mesh_tri_count": int(mesh.get("tri_count", 0)) if isinstance(mesh, dict) else 0,
            "gcode_loaded": bool(source_gcode),
            "warnings": warnings,
        }
        summary = (
            f"G-code preview | {mode} | "
            f"layers {int(parsed_plan.get('stats', {}).get('layer_count', 0)) if isinstance(parsed_plan, dict) else 0}"
        )
        return (_pil_to_batch([preview_image]), _json_text(info), summary, parsed_plan or {})
