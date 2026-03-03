import json
import math
import os
import re
import textwrap
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
import torch

from ..categories import CORE_CAMERA, CORE_CHARACTER, CORE_LAYOUT, INSPECT_COMPARE, INSPECT_DEBUG

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(THIS_DIR)
CONFIG_CANDIDATES = (
    os.path.join(PACKAGE_ROOT, "config", "params.json"),
    os.path.join(PACKAGE_ROOT, "web", "config", "params.json"),
)

STYLE_PRESETS: Dict[str, Dict[str, List[str]]] = {
    "cinematic_photoreal": {
        "tags": [
            "cinematic portrait photography",
            "natural skin detail",
            "realistic lens depth",
            "film-grade color",
        ],
        "negative": ["cgi look", "plastic skin", "low detail"],
    },
    "editorial_fashion": {
        "tags": [
            "editorial fashion photography",
            "studio polish",
            "clean composition",
            "premium styling",
        ],
        "negative": ["street snapshot", "messy wardrobe", "flat lighting"],
    },
    "stylized_anime": {
        "tags": [
            "anime-inspired line clarity",
            "high readability silhouettes",
            "stylized color blocking",
            "expressive design",
        ],
        "negative": ["washed colors", "muddy shading", "realistic skin pores"],
    },
    "fantasy_concept_art": {
        "tags": [
            "fantasy concept art",
            "heroic design language",
            "dramatic atmosphere",
            "production-ready concept",
        ],
        "negative": ["modern casual outfit", "flat scene", "uninspired composition"],
    },
    "game_character_sheet": {
        "tags": [
            "game-ready character sheet",
            "clear form readability",
            "design turntable quality",
            "asset-brief style clarity",
        ],
        "negative": ["motion blur", "obscured costume", "unclear silhouette"],
    },
}

GLOBAL_NEGATIVE = [
    "extra limbs",
    "bad hands",
    "deformed anatomy",
    "cross-eye",
    "disfigured face",
    "blurry",
    "watermark",
    "jpeg artifacts",
    "text overlay",
]

SHOT_TYPES = [
    "full body",
    "three quarter",
    "cowboy shot",
    "waist up",
    "close portrait",
]

MOODS = [
    "neutral",
    "confident",
    "heroic",
    "mysterious",
    "friendly",
    "intense",
]

BACKGROUND_MODES = {"blur", "black", "white", "gray"}
SETTINGS_SCHEMA_VERSION = 3
ASPECT_PRESET_CHOICES = [
    "Social - 9:16 (Stories/Reels/TikTok)",
    "Social - 4:5 (Instagram Portrait)",
    "Social - 1:1 (Square/Instagram Feed)",
    "Social - 1.91:1 (Facebook/LinkedIn Landscape)",
    "Social - 3:4 (Instagram Grid/Threads)",
    "Social - 19:6 (TikTok Wide-View/Landscape)",
    "Social - 2:3 (Pinterest Standard Pin)",
    "Social - 3:1 (X/Twitter Headers)",
    "Photo - 3:2 (Standard DSLR/35mm)",
    "Photo - 4:3 (Micro Four Thirds/Smartphones)",
    "Photo - 5:4 (8x10 Portrait Prints)",
    "Photo - 6:7 (Medium Format Ideal)",
    "Photo - 6:6 (Medium Format Square)",
    "Photo - 1:1 (Polaroid/Hasselblad)",
    "Photo - 6:17 (Panoramic Film)",
    "Photo - 65:24 (Hasselblad XPan Panoramic)",
    "Cinema - 16:9 (HDTV Standard)",
    "Cinema - 1.85:1 (DCI Flat/Standard Cinema)",
    "Cinema - 2.39:1 (Anamorphic/CinemaScope)",
    "Cinema - 2.35:1 (Classic Widescreen)",
    "Cinema - 1.37:1 (Academy Ratio)",
    "Cinema - 1.33:1 (Old TV/Silent Film)",
    "Cinema - 1.66:1 (European Widescreen)",
    "Cinema - 2.20:1 (70mm/Todd-AO)",
    "Cinema - 1.43:1 (IMAX GT)",
    "Cinema - 2.00:1 (Univisium/Netflix Standard)",
    "Cinema - 2.76:1 (Ultra Panavision 70)",
    "Cinema - 21:9 (Ultrawide Monitors)",
]

ASPECT_ORIENTATION_CHOICES = ["Portrait", "Horizontal"]
ASPECT_POSITION_CHOICES = [
    "Top • Left",
    "Top • Center",
    "Top • Right",
    "Center • Left",
    "Center • Center",
    "Center • Right",
    "Bottom • Left",
    "Bottom • Center",
    "Bottom • Right",
]

DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    "schema_version": SETTINGS_SCHEMA_VERSION,
    "coordinate_system": {"right_axis": "x", "front_axis": "y", "up_axis": "z"},
    "distance_bands": {"close": 1.2, "mid": 2.5, "far": 5.0},
    "height_bands": {"low": 0.4, "mid": 1.2},
    "side_bands": {"center": 0.25},
    "params": [],
}

DEFAULT_SETTINGS_TEMPLATE: Dict[str, Any] = {
    "schema_version": SETTINGS_SCHEMA_VERSION,
    "camera": {"pos": [0.0, 2.0, 1.4]},
    "light": {"pos": [1.2, 2.2, 2.0]},
    "gizmos": {
        "camera": {"mode": "procedural", "glb_url": ""},
        "light": {"mode": "procedural", "glb_url": ""},
    },
    "angle": {
        "rotation": 45.0,
        "tilt": -30.0,
        "zoom": 0.0,
        "strength": 0.85,
        "background_mode": "blur",
        "sheet_columns": 4,
        "label_overlay": True,
        "multi12": False,
    },
    "params": {},
}


def _resolve_config_path() -> str:
    for path in CONFIG_CANDIDATES:
        if os.path.isfile(path):
            return path
    return CONFIG_CANDIDATES[0]


def _safe_load_json(path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else fallback
    except Exception:
        return fallback


def _parse_settings_json(settings_json: str) -> Dict[str, Any]:
    if not isinstance(settings_json, str) or not settings_json.strip():
        return {}
    try:
        data = json.loads(settings_json)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_runtime_config() -> Dict[str, Any]:
    cfg = _safe_load_json(_resolve_config_path(), fallback=DEFAULT_RUNTIME_CONFIG)
    out = {
        "schema_version": _safe_int(cfg.get("schema_version", SETTINGS_SCHEMA_VERSION), SETTINGS_SCHEMA_VERSION),
        "coordinate_system": _as_dict(cfg.get("coordinate_system")),
        "distance_bands": _as_dict(cfg.get("distance_bands")),
        "height_bands": _as_dict(cfg.get("height_bands")),
        "side_bands": _as_dict(cfg.get("side_bands")),
    }
    out["params"] = cfg.get("params") if isinstance(cfg.get("params"), list) else []

    if not out["coordinate_system"]:
        out["coordinate_system"] = DEFAULT_RUNTIME_CONFIG["coordinate_system"]
    if not out["distance_bands"]:
        out["distance_bands"] = DEFAULT_RUNTIME_CONFIG["distance_bands"]
    if not out["height_bands"]:
        out["height_bands"] = DEFAULT_RUNTIME_CONFIG["height_bands"]
    if not out["side_bands"]:
        out["side_bands"] = DEFAULT_RUNTIME_CONFIG["side_bands"]
    return out


def _normalize_param_values(settings: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, float]:
    defaults: Dict[str, float] = {}
    for spec in cfg.get("params", []):
        if not isinstance(spec, dict):
            continue
        key = spec.get("key")
        if isinstance(key, str) and key:
            defaults[key] = _safe_float(spec.get("default", 0.0), 0.0)

    params_out = dict(defaults)

    raw_params = _as_dict(settings.get("params"))
    nested_params = _as_dict(_as_dict(settings.get("character")).get("params"))

    for source in (raw_params, nested_params):
        for key, value in source.items():
            if not isinstance(key, str) or not key:
                continue
            fallback = params_out.get(key, 0.0)
            params_out[key] = _safe_float(value, fallback)
    return params_out


def _normalize_settings(settings: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    raw = settings if isinstance(settings, dict) else {}

    out: Dict[str, Any] = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "camera": {"pos": list(DEFAULT_SETTINGS_TEMPLATE["camera"]["pos"])},
        "light": {"pos": list(DEFAULT_SETTINGS_TEMPLATE["light"]["pos"])},
        "gizmos": {
            "camera": dict(DEFAULT_SETTINGS_TEMPLATE["gizmos"]["camera"]),
            "light": dict(DEFAULT_SETTINGS_TEMPLATE["gizmos"]["light"]),
        },
        "angle": dict(DEFAULT_SETTINGS_TEMPLATE["angle"]),
        "params": {},
    }

    camera_obj = _as_dict(raw.get("camera"))
    light_obj = _as_dict(raw.get("light"))
    out["camera"]["pos"] = list(_vec3(camera_obj.get("pos"), default=tuple(out["camera"]["pos"])))
    out["light"]["pos"] = list(_vec3(light_obj.get("pos"), default=tuple(out["light"]["pos"])))

    gizmos = _as_dict(raw.get("gizmos"))
    cam_gizmo = _as_dict(gizmos.get("camera"))
    light_gizmo = _as_dict(gizmos.get("light"))
    out["gizmos"]["camera"]["mode"] = "glb" if cam_gizmo.get("mode") == "glb" else "procedural"
    out["gizmos"]["light"]["mode"] = "glb" if light_gizmo.get("mode") == "glb" else "procedural"
    out["gizmos"]["camera"]["glb_url"] = str(cam_gizmo.get("glb_url", "") or "")
    out["gizmos"]["light"]["glb_url"] = str(light_gizmo.get("glb_url", "") or "")

    angle_source = _as_dict(raw.get("angle"))
    angle_defaults = _as_dict(out["angle"])
    out["angle"]["rotation"] = _safe_float(
        raw.get("rotation", angle_source.get("rotation", angle_defaults["rotation"])),
        angle_defaults["rotation"],
    ) % 360.0
    out["angle"]["tilt"] = _clamp(
        _safe_float(raw.get("tilt", angle_source.get("tilt", angle_defaults["tilt"])), angle_defaults["tilt"]),
        -90.0,
        90.0,
    )
    out["angle"]["zoom"] = _clamp(
        _safe_float(raw.get("zoom", angle_source.get("zoom", angle_defaults["zoom"])), angle_defaults["zoom"]),
        -1.0,
        1.0,
    )
    out["angle"]["strength"] = _clamp(
        _safe_float(raw.get("strength", angle_source.get("strength", angle_defaults["strength"])), angle_defaults["strength"]),
        0.0,
        1.5,
    )
    bg_mode = str(
        raw.get("background_mode", angle_source.get("background_mode", angle_defaults["background_mode"])) or "blur"
    ).lower()
    out["angle"]["background_mode"] = bg_mode if bg_mode in BACKGROUND_MODES else "blur"
    out["angle"]["sheet_columns"] = int(
        _clamp(
            float(_safe_int(raw.get("sheet_columns", angle_source.get("sheet_columns", angle_defaults["sheet_columns"])), 4)),
            3.0,
            6.0,
        )
    )
    out["angle"]["label_overlay"] = _safe_bool(
        raw.get("label_overlay", angle_source.get("label_overlay", angle_defaults["label_overlay"])),
        True,
    )
    out["angle"]["multi12"] = _safe_bool(
        raw.get("multi12", angle_source.get("multi12", angle_defaults["multi12"])),
        False,
    )

    out["params"] = _normalize_param_values(raw, cfg)

    # Legacy mirrors for existing front-end scripts and old workflows.
    out["rotation"] = out["angle"]["rotation"]
    out["tilt"] = out["angle"]["tilt"]
    out["zoom"] = out["angle"]["zoom"]
    out["strength"] = out["angle"]["strength"]
    out["background_mode"] = out["angle"]["background_mode"]
    out["sheet_columns"] = out["angle"]["sheet_columns"]
    out["label_overlay"] = out["angle"]["label_overlay"]
    out["multi12"] = out["angle"]["multi12"]

    return out


def _json_dumps_stable(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _vec3(v: Any, default=(0.0, 2.0, 1.2)) -> Tuple[float, float, float]:
    if isinstance(v, (list, tuple)) and len(v) == 3:
        try:
            return (float(v[0]), float(v[1]), float(v[2]))
        except Exception:
            return default
    return default


def _norm(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _axis_value(vec: Tuple[float, float, float], axis: str) -> float:
    axis = axis.lower()
    if axis == "x":
        return vec[0]
    if axis == "y":
        return vec[1]
    return vec[2]


def _describe_position(
    pos: Tuple[float, float, float],
    coord: Dict[str, str],
    bands: Dict[str, Any],
) -> str:
    right_axis = coord.get("right_axis", "x")
    front_axis = coord.get("front_axis", "y")
    up_axis = coord.get("up_axis", "z")

    side_center = float(bands.get("side_bands", {}).get("center", 0.25))
    low_h = float(bands.get("height_bands", {}).get("low", 0.4))
    mid_h = float(bands.get("height_bands", {}).get("mid", 1.2))

    d_close = float(bands.get("distance_bands", {}).get("close", 1.2))
    d_mid = float(bands.get("distance_bands", {}).get("mid", 2.5))
    d_far = float(bands.get("distance_bands", {}).get("far", 5.0))

    side = _axis_value(pos, right_axis)
    front = _axis_value(pos, front_axis)
    up = _axis_value(pos, up_axis)
    dist = _norm(pos)

    if abs(side) <= side_center:
        side_s = "center"
    else:
        side_s = "right" if side > 0 else "left"

    if abs(front) <= side_center:
        fb_s = "center"
    else:
        fb_s = "front" if front > 0 else "back"

    if up < low_h:
        h_s = "low"
    elif up < mid_h:
        h_s = "mid"
    else:
        h_s = "high"

    if dist <= d_close:
        d_s = "close"
    elif dist <= d_mid:
        d_s = "mid-distance"
    elif dist <= d_far:
        d_s = "far"
    else:
        d_s = "very-far"

    planar = f"{fb_s}-{side_s}" if fb_s != "center" or side_s != "center" else "centered"
    return f"{planar}, {h_s}, {d_s}"


def _pil_to_comfy_image(img: Image.Image) -> torch.Tensor:
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _pil_list_to_comfy_batch(images: Sequence[Image.Image]) -> torch.Tensor:
    if not images:
        blank = np.zeros((1, 64, 64, 3), dtype=np.float32)
        return torch.from_numpy(blank)
    arr = np.stack([np.array(im.convert("RGB"), dtype=np.float32) / 255.0 for im in images], axis=0)
    return torch.from_numpy(arr)


def _comfy_batch_to_pil_list(image: torch.Tensor) -> List[Image.Image]:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")

    t = image.detach().cpu().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor with 4 dims [B,H,W,C], got shape={tuple(t.shape)}")

    if t.shape[-1] == 4:
        t = t[..., :3]
    if t.shape[-1] != 3:
        raise ValueError(f"Expected IMAGE tensor channel dimension 3 or 4, got shape={tuple(t.shape)}")

    t = t.clamp(0.0, 1.0)
    arr = (t.numpy() * 255.0).astype(np.uint8)
    return [Image.fromarray(sample, mode="RGB") for sample in arr]


def _temp_dir() -> str:
    if folder_paths and hasattr(folder_paths, "get_temp_directory"):
        return str(folder_paths.get_temp_directory())
    fallback = os.path.join(PACKAGE_ROOT, ".temp")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _make_preview_image(image: Any) -> Optional[Image.Image]:
    if image is None:
        return None

    try:
        if isinstance(image, Image.Image):
            preview = image.convert("RGB")
            preview.thumbnail((1024, 1024), resample=Image.Resampling.LANCZOS)
            return preview

        array = image
        if hasattr(array, "detach"):
            array = array.detach().cpu().numpy()
        else:
            array = np.asarray(array)

        if array.ndim == 4:
            array = array[0]
        if array.ndim == 3 and array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
            array = np.moveaxis(array, 0, -1)

        if array.ndim == 3:
            if array.shape[-1] == 1:
                array = array[..., 0]
            elif array.shape[-1] >= 3:
                array = array[..., :3]
            else:
                return None
        elif array.ndim != 2:
            return None

        if array.dtype != np.uint8:
            array = np.clip(array, 0.0, 1.0)
            array = (array * 255.0).round().astype(np.uint8)

        image_pil = Image.fromarray(array)
        image_pil.thumbnail((1024, 1024), resample=Image.Resampling.LANCZOS)
        return image_pil.convert("RGB")
    except Exception:
        return None


def _save_temp_preview(image: Any, prefix: str = "mkrshift_axb") -> Optional[Dict[str, str]]:
    preview = _make_preview_image(image)
    if preview is None:
        return None

    output_dir = _temp_dir()
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.png"
    target = os.path.join(output_dir, filename)
    preview.save(target, format="PNG", compress_level=1)
    return {"filename": filename, "subfolder": "", "type": "temp"}


def _load_fonts() -> Tuple[ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    try:
        title = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        body = ImageFont.truetype("DejaVuSans.ttf", 18)
        small = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        title = ImageFont.load_default()
        body = ImageFont.load_default()
        small = ImageFont.load_default()
    return title, body, small


def _param_value(params: Dict[str, Any], key: str, default: float = 0.0) -> float:
    return _safe_float(params.get(key, default), default)


def _build_param_descriptors(param_values: Dict[str, Any]) -> List[str]:
    if not isinstance(param_values, dict):
        return []

    desc: List[str] = []
    height = _param_value(param_values, "height", 1.0)
    muscle = _param_value(param_values, "muscle", 0.35)
    body_fat = _param_value(param_values, "body_fat", _param_value(param_values, "weight", 0.25))
    shoulders = _param_value(param_values, "shoulders", 0.0)
    hips = _param_value(param_values, "hips", 0.0)
    jaw = _param_value(param_values, "jaw_width", 0.0)
    eye = _param_value(param_values, "eye_size", 0.0)
    age_shift = _param_value(param_values, "age_shift", 0.0)

    if height >= 1.08:
        desc.append("tall body proportions")
    elif height <= 0.92:
        desc.append("compact body proportions")

    if muscle >= 0.65:
        desc.append("athletic muscular frame")
    elif muscle <= 0.2:
        desc.append("soft low-muscle frame")

    if body_fat >= 0.65:
        desc.append("fuller body fat distribution")
    elif body_fat <= 0.2:
        desc.append("lean body fat distribution")

    if shoulders >= 0.35:
        desc.append("broad shoulders")
    elif shoulders <= -0.35:
        desc.append("narrow shoulders")

    if hips >= 0.35:
        desc.append("wide hips")
    elif hips <= -0.35:
        desc.append("narrow hips")

    if jaw >= 0.4:
        desc.append("strong jawline")
    elif jaw <= -0.4:
        desc.append("soft jawline")

    if eye >= 0.35:
        desc.append("large expressive eyes")
    elif eye <= -0.35:
        desc.append("small focused eyes")

    if age_shift >= 0.35:
        desc.append("mature facial traits")
    elif age_shift <= -0.35:
        desc.append("youthful facial traits")

    for key, raw in param_values.items():
        if key in {
            "height",
            "muscle",
            "body_fat",
            "weight",
            "shoulders",
            "hips",
            "jaw_width",
            "eye_size",
            "age_shift",
        }:
            continue
        val = _safe_float(raw, 0.0)
        if abs(val) >= 0.85:
            direction = "high" if val > 0 else "low"
            desc.append(f"{key.replace('_', ' ')} {direction}")

    return desc


def _facing_label(rotation_deg: float) -> str:
    r = rotation_deg % 360.0
    if 315 <= r or r < 45:
        return "front"
    if 45 <= r < 135:
        return "right"
    if 135 <= r < 225:
        return "back"
    return "left"


def _elevation_label(tilt_deg: float) -> str:
    if tilt_deg <= -20:
        return "low-angle"
    if tilt_deg >= 20:
        return "high-angle"
    return "eye-level"


def _framing_label(zoom: float) -> str:
    if zoom <= -0.5:
        return "wide"
    if zoom >= 0.5:
        return "close-up"
    return "medium"


def _lens_from_distance(distance: float) -> int:
    if distance <= 1.3:
        return 85
    if distance <= 2.4:
        return 50
    return 35


def _lens_from_zoom(zoom: float) -> int:
    if zoom >= 0.55:
        return 85
    if zoom >= 0.1:
        return 50
    if zoom <= -0.55:
        return 24
    return 35


def _join_prompt_parts(parts: Sequence[str]) -> str:
    cleaned: List[str] = []
    seen = set()
    for part in parts:
        p = (part or "").strip(" ,")
        if not p:
            continue
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        cleaned.append(p)
    return ", ".join(cleaned)


def _draw_stick_figure(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    params: Dict[str, Any],
    profile: bool,
    color: Tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    w = float(x1 - x0)
    h = float(y1 - y0)

    height = _clamp(_param_value(params, "height", 1.0), 0.8, 1.3)
    leg_length = _clamp(_param_value(params, "leg_length", 0.0), -1.0, 1.0)
    arm_length = _clamp(_param_value(params, "arm_length", 0.0), -1.0, 1.0)
    shoulders = _clamp(_param_value(params, "shoulders", 0.0), -1.0, 1.0)
    hips = _clamp(_param_value(params, "hips", 0.0), -1.0, 1.0)
    chest = _clamp(_param_value(params, "chest", 0.0), -1.0, 1.0)
    waist = _clamp(_param_value(params, "waist", 0.0), -1.0, 1.0)
    muscle = _clamp(_param_value(params, "muscle", 0.35), 0.0, 1.0)
    body_fat = _clamp(_param_value(params, "body_fat", _param_value(params, "weight", 0.25)), 0.0, 1.0)
    head_size = _clamp(_param_value(params, "head_size", 0.0), -1.0, 1.0)

    cx = (x0 + x1) * 0.5
    feet_y = y1 - int(0.05 * h)
    body_total = h * (0.78 + (height - 1.0) * 0.22)
    top_y = feet_y - body_total

    head_r = h * (0.062 + head_size * 0.016)
    head_cy = top_y + head_r
    neck_y = head_cy + head_r + h * 0.012
    pelvis_y = top_y + body_total * (0.53 - leg_length * 0.08)

    shoulder_span = w * (0.22 + shoulders * 0.06 + muscle * 0.04)
    hip_span = w * (0.17 + hips * 0.06 + body_fat * 0.03)
    waist_span = (shoulder_span + hip_span) * (0.42 + waist * 0.08)

    arm_reach = body_total * (0.31 + arm_length * 0.08)
    elbow_drop = body_total * 0.22

    line_w = max(2, int((w + h) * (0.004 + muscle * 0.0018 + body_fat * 0.0008)))
    fill_col = (color[0], color[1], color[2], 140)

    torso_poly = [
        (cx - shoulder_span, neck_y),
        (cx + shoulder_span, neck_y),
        (cx + waist_span, (neck_y + pelvis_y) * 0.56),
        (cx + hip_span, pelvis_y),
        (cx - hip_span, pelvis_y),
        (cx - waist_span, (neck_y + pelvis_y) * 0.56),
    ]

    if profile:
        profile_shift = w * (0.08 + chest * 0.06)
        torso_poly = [(x + profile_shift if idx < 3 else x - w * 0.03, y) for idx, (x, y) in enumerate(torso_poly)]

    overlay = Image.new("RGBA", (int(w) + 4, int(h) + 4), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    o_poly = [(int(px - x0 + 2), int(py - y0 + 2)) for px, py in torso_poly]
    o_draw.polygon(o_poly, fill=fill_col)
    draw.bitmap((x0 - 2, y0 - 2), overlay)

    # Head
    draw.ellipse(
        [
            cx - head_r,
            head_cy - head_r,
            cx + head_r,
            head_cy + head_r,
        ],
        outline=color,
        width=max(2, line_w),
    )

    # Spine and pelvis
    draw.line([(cx, neck_y), (cx, pelvis_y)], fill=color, width=line_w)
    draw.line([(cx - hip_span, pelvis_y), (cx + hip_span, pelvis_y)], fill=color, width=line_w)

    # Arms
    shoulder_y = neck_y + h * 0.015
    left_shoulder = (cx - shoulder_span, shoulder_y)
    right_shoulder = (cx + shoulder_span, shoulder_y)

    if profile:
        arm_depth = w * 0.08
        left_elbow = (cx - shoulder_span + arm_depth, shoulder_y + elbow_drop)
        right_elbow = (cx + shoulder_span + arm_depth, shoulder_y + elbow_drop)
        left_hand = (left_elbow[0], left_elbow[1] + arm_reach * 0.55)
        right_hand = (right_elbow[0], right_elbow[1] + arm_reach * 0.45)
    else:
        left_elbow = (cx - shoulder_span - w * 0.05, shoulder_y + elbow_drop)
        right_elbow = (cx + shoulder_span + w * 0.05, shoulder_y + elbow_drop)
        left_hand = (left_elbow[0] - w * 0.02, left_elbow[1] + arm_reach * 0.5)
        right_hand = (right_elbow[0] + w * 0.02, right_elbow[1] + arm_reach * 0.5)

    draw.line([left_shoulder, left_elbow, left_hand], fill=color, width=line_w)
    draw.line([right_shoulder, right_elbow, right_hand], fill=color, width=line_w)

    # Legs
    left_hip = (cx - hip_span * 0.42, pelvis_y)
    right_hip = (cx + hip_span * 0.42, pelvis_y)
    knee_y = pelvis_y + body_total * (0.22 + 0.03 * (1.0 - leg_length))

    if profile:
        left_knee = (left_hip[0] + w * 0.05, knee_y)
        right_knee = (right_hip[0] + w * 0.07, knee_y + h * 0.01)
        left_foot = (left_knee[0] + w * 0.03, feet_y)
        right_foot = (right_knee[0] + w * 0.06, feet_y)
    else:
        left_knee = (left_hip[0] - w * 0.025, knee_y)
        right_knee = (right_hip[0] + w * 0.025, knee_y)
        left_foot = (left_knee[0], feet_y)
        right_foot = (right_knee[0], feet_y)

    draw.line([left_hip, left_knee, left_foot], fill=color, width=line_w)
    draw.line([right_hip, right_knee, right_foot], fill=color, width=line_w)


def _make_pose_guide_image(
    w: int,
    h: int,
    param_values: Dict[str, Any],
    camera_desc: str,
    light_desc: str,
) -> Image.Image:
    img = Image.new("RGB", (w, h), (19, 22, 30))
    draw = ImageDraw.Draw(img)
    title_font, body_font, small_font = _load_fonts()

    step = max(20, min(w, h) // 18)
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=(30, 35, 46), width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=(30, 35, 46), width=1)

    front_box = (int(w * 0.07), int(h * 0.16), int(w * 0.46), int(h * 0.93))
    side_box = (int(w * 0.54), int(h * 0.16), int(w * 0.93), int(h * 0.93))

    draw.rounded_rectangle(front_box, radius=14, outline=(70, 90, 120), width=2)
    draw.rounded_rectangle(side_box, radius=14, outline=(70, 90, 120), width=2)

    _draw_stick_figure(draw, front_box, param_values, profile=False, color=(110, 220, 255))
    _draw_stick_figure(draw, side_box, param_values, profile=True, color=(255, 192, 110))

    draw.text((front_box[0] + 10, front_box[1] + 8), "Front", font=body_font, fill=(180, 220, 245))
    draw.text((side_box[0] + 10, side_box[1] + 8), "Side", font=body_font, fill=(245, 210, 170))

    draw.text((18, 14), "Pose Guide", font=title_font, fill=(230, 235, 245))
    draw.text((18, h - 52), f"Camera: {camera_desc}", font=small_font, fill=(170, 180, 205))
    draw.text((18, h - 30), f"Light: {light_desc}", font=small_font, fill=(170, 180, 205))

    return img


def _make_scene_map(
    size: int,
    camera_pos: Tuple[float, float, float],
    light_pos: Tuple[float, float, float],
    coord: Dict[str, str],
) -> Image.Image:
    img = Image.new("RGB", (size, size), (17, 20, 27))
    draw = ImageDraw.Draw(img)
    _, body_font, small_font = _load_fonts()

    center = size // 2
    for g in range(0, size, max(24, size // 8)):
        draw.line([(g, 0), (g, size)], fill=(31, 35, 45), width=1)
        draw.line([(0, g), (size, g)], fill=(31, 35, 45), width=1)

    draw.line([(center, 0), (center, size)], fill=(65, 74, 95), width=2)
    draw.line([(0, center), (size, center)], fill=(65, 74, 95), width=2)

    draw.text((10, 8), "Top View", font=body_font, fill=(220, 224, 236))

    right_axis = coord.get("right_axis", "x")
    front_axis = coord.get("front_axis", "y")

    def to_map(pos: Tuple[float, float, float]) -> Tuple[float, float]:
        scale = size / 8.0
        px = center + _axis_value(pos, right_axis) * scale
        py = center - _axis_value(pos, front_axis) * scale
        return (px, py)

    cam_xy = to_map(camera_pos)
    light_xy = to_map(light_pos)
    subject = (center, center)

    draw.ellipse([subject[0] - 7, subject[1] - 7, subject[0] + 7, subject[1] + 7], fill=(220, 220, 220))

    draw.line([cam_xy, subject], fill=(120, 220, 255), width=3)
    draw.ellipse([cam_xy[0] - 8, cam_xy[1] - 8, cam_xy[0] + 8, cam_xy[1] + 8], fill=(80, 190, 255))
    draw.text((cam_xy[0] + 10, cam_xy[1] - 8), "CAM", font=small_font, fill=(140, 230, 255))

    draw.line([light_xy, subject], fill=(255, 193, 90), width=3)
    draw.ellipse([light_xy[0] - 8, light_xy[1] - 8, light_xy[0] + 8, light_xy[1] + 8], fill=(255, 178, 70))
    draw.text((light_xy[0] + 10, light_xy[1] - 8), "LGT", font=small_font, fill=(255, 220, 165))

    return img


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_chars: int,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
    line_height: int,
    max_lines: int,
) -> int:
    lines = textwrap.wrap(text, width=max_chars, break_long_words=False, break_on_hyphens=False)
    if not lines:
        return y
    lines = lines[:max_lines]
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill)
        y += line_height
    return y


def _make_director_sheet(
    w: int,
    h: int,
    model_path: str,
    camera_desc: str,
    light_desc: str,
    positive_prompt: str,
    negative_prompt: str,
    param_descriptors: Sequence[str],
    pose_guide: Image.Image,
    scene_map: Image.Image,
) -> Image.Image:
    sheet = Image.new("RGB", (w, h), (11, 13, 18))
    draw = ImageDraw.Draw(sheet)
    title_font, body_font, small_font = _load_fonts()

    for y in range(h):
        t = y / max(1, h - 1)
        c1 = int(16 + 18 * t)
        c2 = int(18 + 26 * t)
        c3 = int(26 + 28 * t)
        draw.line([(0, y), (w, y)], fill=(c1, c2, c3), width=1)

    margin = max(16, min(w, h) // 40)
    header_h = max(62, h // 11)

    draw.rounded_rectangle([margin, margin, w - margin, header_h], radius=12, outline=(70, 80, 98), width=2)
    draw.text((margin + 16, margin + 14), "MKR Character Director", font=title_font, fill=(232, 236, 245))

    model_text = f"Model: {model_path or '(not set)'}"
    draw.text((margin + 18, header_h - 22), model_text, font=small_font, fill=(160, 172, 194))

    left_x = margin
    left_y = header_h + margin
    left_w = int(w * 0.47) - margin
    left_h = h - left_y - margin

    right_x = left_x + left_w + margin
    right_y = left_y
    right_w = w - right_x - margin
    right_h = left_h

    draw.rounded_rectangle([left_x, left_y, left_x + left_w, left_y + left_h], radius=14, outline=(72, 90, 118), width=2)
    draw.rounded_rectangle([right_x, right_y, right_x + right_w, right_y + right_h], radius=14, outline=(72, 90, 118), width=2)

    pose_fit = ImageOps.fit(pose_guide, (left_w - 14, left_h - 14), method=Image.Resampling.BICUBIC)
    sheet.paste(pose_fit, (left_x + 7, left_y + 7))

    map_size = min(right_w - 18, max(180, int(h * 0.26)))
    map_fit = ImageOps.fit(scene_map, (map_size, map_size), method=Image.Resampling.BICUBIC)
    sheet.paste(map_fit, (right_x + 9, right_y + 10))

    text_x = right_x + 12
    text_y = right_y + map_size + 20
    max_chars = max(28, right_w // 8)

    draw.text((text_x, text_y), "Camera", font=body_font, fill=(176, 224, 255))
    text_y += 24
    text_y = _draw_wrapped(draw, camera_desc, text_x, text_y, max_chars, small_font, (188, 198, 220), 18, 3)

    text_y += 6
    draw.text((text_x, text_y), "Lighting", font=body_font, fill=(255, 219, 166))
    text_y += 24
    text_y = _draw_wrapped(draw, light_desc, text_x, text_y, max_chars, small_font, (188, 198, 220), 18, 3)

    text_y += 6
    draw.text((text_x, text_y), "Design Intent", font=body_font, fill=(203, 232, 182))
    text_y += 24
    intent = "; ".join(param_descriptors[:4]) if param_descriptors else "balanced default proportions"
    text_y = _draw_wrapped(draw, intent, text_x, text_y, max_chars, small_font, (188, 198, 220), 18, 4)

    text_y += 6
    draw.text((text_x, text_y), "Positive Prompt", font=small_font, fill=(190, 220, 255))
    text_y += 18
    text_y = _draw_wrapped(draw, positive_prompt, text_x, text_y, max_chars, small_font, (206, 214, 228), 17, 8)

    text_y += 4
    draw.text((text_x, text_y), "Negative Prompt", font=small_font, fill=(255, 186, 186))
    text_y += 18
    _draw_wrapped(draw, negative_prompt, text_x, text_y, max_chars, small_font, (206, 214, 228), 17, 5)

    return sheet


def _find_perspective_coeffs(dst_points: Sequence[Tuple[float, float]], src_points: Sequence[Tuple[float, float]]) -> List[float]:
    if len(dst_points) != 4 or len(src_points) != 4:
        raise ValueError("Perspective transform requires exactly 4 points for dst and src")

    matrix: List[List[float]] = []
    vector: List[float] = []
    for (x, y), (u, v) in zip(dst_points, src_points):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        vector.extend([u, v])

    A = np.array(matrix, dtype=np.float64)
    b = np.array(vector, dtype=np.float64)
    coeffs = np.linalg.solve(A, b)
    return coeffs.astype(np.float64).tolist()


def _projected_quad(
    w: int,
    h: int,
    rotation_deg: float,
    tilt_deg: float,
    zoom: float,
    strength: float,
) -> List[Tuple[float, float]]:
    orbit = math.radians(rotation_deg % 360.0)
    yaw = math.sin(orbit) * math.radians(42.0) * strength
    pitch = _clamp(tilt_deg, -85.0, 85.0) / 85.0 * math.radians(30.0) * strength

    cy, sy = math.cos(yaw), math.sin(yaw)
    cx, sx = math.cos(pitch), math.sin(pitch)

    corners = np.array(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )

    projected: List[Tuple[float, float]] = []
    cam_dist = _clamp(2.8 - zoom * 1.1, 1.3, 4.2)

    for x, y, z in corners:
        x1 = x * cy + z * sy
        z1 = -x * sy + z * cy

        y2 = y * cx - z1 * sx
        z2 = y * sx + z1 * cx

        denom = max(0.35, cam_dist - z2)
        px = x1 / denom
        py = y2 / denom
        projected.append((px, py))

    arr = np.array(projected, dtype=np.float64)
    max_extent = max(1e-6, float(np.max(np.abs(arr))))
    fit = 0.9 / max_extent
    arr *= fit

    arr[:, 0] += math.sin(orbit) * 0.08 * strength
    arr[:, 1] += -math.sin(math.radians(tilt_deg)) * 0.05 * strength

    if math.cos(orbit) < -0.2:
        arr[:, 0] *= -1.0

    dst: List[Tuple[float, float]] = []
    for px, py in arr:
        ix = (px * 0.5 + 0.5) * (w - 1)
        iy = (py * 0.5 + 0.5) * (h - 1)
        dst.append((float(ix), float(iy)))

    return dst


def _build_background(base: Image.Image, mode: str, zoom: float) -> Image.Image:
    mode = mode.lower()
    w, h = base.size

    if mode == "white":
        return Image.new("RGB", (w, h), (245, 245, 245))
    if mode == "gray":
        return Image.new("RGB", (w, h), (80, 80, 80))
    if mode == "black":
        return Image.new("RGB", (w, h), (0, 0, 0))

    radius = max(4, int(min(w, h) * (0.012 + 0.008 * max(0.0, zoom))))
    bg = base.filter(ImageFilter.GaussianBlur(radius))
    bg = ImageEnhance.Brightness(bg).enhance(0.92)
    return bg


def _warp_image(
    image: Image.Image,
    rotation_deg: float,
    tilt_deg: float,
    zoom: float,
    strength: float,
    background_mode: str,
) -> Tuple[Image.Image, List[Tuple[float, float]]]:
    w, h = image.size
    src = [(0.0, 0.0), (float(w - 1), 0.0), (float(w - 1), float(h - 1)), (0.0, float(h - 1))]
    dst = _projected_quad(w, h, rotation_deg, tilt_deg, zoom, strength)
    coeffs = _find_perspective_coeffs(dst, src)

    fg = image.convert("RGBA")
    warped = fg.transform(
        (w, h),
        Image.Transform.PERSPECTIVE,
        coeffs,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )

    bg = _build_background(image, background_mode, zoom).convert("RGBA")
    bg.alpha_composite(warped)

    return bg.convert("RGB"), dst


def _make_contact_sheet(
    images: Sequence[Image.Image],
    labels: Sequence[str],
    columns: int,
    label_overlay: bool,
) -> Image.Image:
    if not images:
        return Image.new("RGB", (256, 256), (18, 18, 18))

    cols = max(1, columns)
    n = len(images)
    rows = int(math.ceil(n / cols))
    w, h = images[0].size

    pad = max(8, min(w, h) // 20)
    label_h = 28 if label_overlay else 0

    sheet_w = cols * w + (cols + 1) * pad
    sheet_h = rows * (h + label_h) + (rows + 1) * pad

    sheet = Image.new("RGB", (sheet_w, sheet_h), (14, 16, 22))
    draw = ImageDraw.Draw(sheet)
    _, _, small_font = _load_fonts()

    for idx, im in enumerate(images):
        row = idx // cols
        col = idx % cols
        x = pad + col * (w + pad)
        y = pad + row * (h + label_h + pad)

        sheet.paste(im, (x, y))

        if label_overlay:
            draw.rectangle([x, y + h, x + w, y + h + label_h], fill=(7, 10, 15))
            label = labels[idx] if idx < len(labels) else f"view {idx + 1}"
            draw.text((x + 8, y + h + 6), label, font=small_font, fill=(208, 214, 230))

    return sheet


def _parse_ratio_token(text: str) -> float:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)", str(text or ""))
    if not match:
        return 1.0
    left = _safe_float(match.group(1), 1.0)
    right = _safe_float(match.group(2), 1.0)
    if left <= 0.0 or right <= 0.0:
        return 1.0
    return left / right


def _ratio_slug(text: str) -> str:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)", str(text or ""))
    if not match:
        return "ratio"
    left = match.group(1).replace(".", "p")
    right = match.group(2).replace(".", "p")
    return f"{left}x{right}"


def _resolve_aspect_label_slug(choice: str, orientation: str) -> str:
    text = str(choice or "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        return _ratio_slug(text)

    left_txt = match.group(1)
    right_txt = match.group(2)
    left = _safe_float(left_txt, 1.0)
    right = _safe_float(right_txt, 1.0)
    orient = str(orientation or "Portrait").strip().lower()

    if orient == "portrait" and left > right:
        left_txt, right_txt = right_txt, left_txt
    elif orient == "horizontal" and left < right:
        left_txt, right_txt = right_txt, left_txt

    return f"{left_txt.replace('.', 'p')}x{right_txt.replace('.', 'p')}"


def _safe_prefix_part(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(text or "").strip()).strip("_")
    return value or "item"


def _format_aspect_filename_label(prefix_base: str, orientation: str, aspect_slug: str) -> str:
    base = _safe_prefix_part(prefix_base).upper() or "AX1"
    orient = str(orientation or "Portrait").strip().lower()
    if orient not in {"portrait", "horizontal"}:
        orient = "portrait"
    orient_label = orient.capitalize()
    ratio_label = _safe_prefix_part(aspect_slug).lower() or "1x1"
    return f"{base}_{orient_label}_{ratio_label}"


def _format_aspect_label_description(
    filename_label: str,
    aspect_choice: str,
    orientation: str,
    aspect_slug: str,
) -> str:
    choice_text = re.sub(r"\s+", " ", str(aspect_choice or "").strip())
    if choice_text:
        return f"{filename_label} | {choice_text}"
    orient = str(orientation or "Portrait").strip().capitalize() or "Portrait"
    ratio_text = str(aspect_slug or "1x1").replace("p", ".").replace("x", ":")
    return f"{filename_label} | {orient} {ratio_text}"


def _resolve_aspect_wh_ratio(choice: str, orientation: str) -> float:
    text = str(choice or "").strip()
    ratio = _parse_ratio_token(text)
    if ratio <= 0.0:
        ratio = 1.0

    orient = str(orientation or "Portrait").strip().lower()
    if orient == "portrait" and ratio > 1.0:
        ratio = 1.0 / ratio
    if orient == "horizontal" and ratio < 1.0:
        ratio = 1.0 / ratio
    return _clamp(ratio, 1.0 / 40.0, 40.0)


def _resolve_aspect_position_anchor(position: str) -> Tuple[float, float]:
    normalized = re.sub(r"\s+", " ", str(position or "").strip().lower().replace("•", " "))
    normalized = re.sub(r"[^a-z ]+", " ", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized)

    if normalized == "center":
        normalized = "center center"

    anchors = {
        "top left": (0.0, 0.0),
        "top center": (0.5, 0.0),
        "top right": (1.0, 0.0),
        "center left": (0.0, 0.5),
        "center center": (0.5, 0.5),
        "center right": (1.0, 0.5),
        "bottom left": (0.0, 1.0),
        "bottom center": (0.5, 1.0),
        "bottom right": (1.0, 1.0),
    }
    return anchors.get(normalized, (0.5, 0.5))


def _resolve_aspect_offsets_and_position(
    x_offset: int = 0,
    y_offset: int = 0,
    position: str = "Center • Center",
    **kwargs,
) -> Tuple[int, int, str]:
    resolved_x = _safe_int(kwargs.get("X • Offset", kwargs.get("custom_x", x_offset)), x_offset)
    resolved_y = _safe_int(kwargs.get("Y • Offset", kwargs.get("custom_y", y_offset)), y_offset)
    resolved_position = str(kwargs.get("Position", kwargs.get("position", position)) or position)
    return resolved_x, resolved_y, resolved_position


def _reshape_to_aspect_1x(
    image: Image.Image,
    target_wh_ratio: float,
    mode: str,
    background_mode: str,
    crop_shift_x: int = 0,
    crop_shift_y: int = 0,
    position: str = "Center • Center",
) -> Image.Image:
    src = image.convert("RGB")
    w, h = src.size
    if w <= 0 or h <= 0:
        return src

    target_wh_ratio = max(1e-6, float(target_wh_ratio))
    src_wh_ratio = w / h
    anchor_x, anchor_y = _resolve_aspect_position_anchor(position)

    if mode == "crop":
        if src_wh_ratio > target_wh_ratio:
            new_w = max(1, int(round(h * target_wh_ratio)))
            max_left = max(0, w - new_w)
            base_left = int(round(float(max_left) * anchor_x))
            left = int(_clamp(float(base_left + int(crop_shift_x)), 0.0, float(max_left)))
            box = (left, 0, left + new_w, h)
        else:
            new_h = max(1, int(round(w / target_wh_ratio)))
            max_top = max(0, h - new_h)
            base_top = int(round(float(max_top) * anchor_y))
            top = int(_clamp(float(base_top + int(crop_shift_y)), 0.0, float(max_top)))
            box = (0, top, w, top + new_h)
        return src.crop(box)

    # "pad" mode
    if src_wh_ratio > target_wh_ratio:
        out_w = w
        out_h = max(1, int(round(w / target_wh_ratio)))
    else:
        out_h = h
        out_w = max(1, int(round(h * target_wh_ratio)))

    if out_w == w and out_h == h:
        return src

    bg_mode = background_mode if background_mode in BACKGROUND_MODES else "blur"
    bg = _build_background(src, bg_mode, zoom=0.0).resize((out_w, out_h), resample=Image.Resampling.BICUBIC)
    max_x = max(0, out_w - w)
    max_y = max(0, out_h - h)
    base_x = int(round(float(max_x) * anchor_x))
    base_y = int(round(float(max_y) * anchor_y))
    x = int(_clamp(float(base_x + int(crop_shift_x)), 0.0, float(max_x)))
    y = int(_clamp(float(base_y + int(crop_shift_y)), 0.0, float(max_y)))
    bg.paste(src, (x, y))
    return bg


def _pad_to_canvas(
    image: Image.Image,
    canvas_w: int,
    canvas_h: int,
    background_mode: str,
    shift_x: int = 0,
    shift_y: int = 0,
    position: str = "Center • Center",
) -> Image.Image:
    src = image.convert("RGB")
    w, h = src.size
    if w == canvas_w and h == canvas_h:
        return src

    bg_mode = background_mode if background_mode in BACKGROUND_MODES else "blur"
    canvas = _build_background(src, bg_mode, zoom=0.0).resize((canvas_w, canvas_h), resample=Image.Resampling.BICUBIC)
    anchor_x, anchor_y = _resolve_aspect_position_anchor(position)
    max_x = max(0, canvas_w - w)
    max_y = max(0, canvas_h - h)
    base_x = int(round(float(max_x) * anchor_x))
    base_y = int(round(float(max_y) * anchor_y))
    x = int(_clamp(float(base_x + int(shift_x)), 0.0, float(max_x)))
    y = int(_clamp(float(base_y + int(shift_y)), 0.0, float(max_y)))
    canvas.paste(src, (x, y))
    return canvas


def _cover_to_canvas(
    image: Image.Image,
    canvas_w: int,
    canvas_h: int,
    shift_x: int = 0,
    shift_y: int = 0,
    position: str = "Center • Center",
) -> Image.Image:
    src = image.convert("RGB")
    w, h = src.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    if w == canvas_w and h == canvas_h:
        return src

    scale = max(canvas_w / w, canvas_h / h)
    scaled_w = max(1, int(round(w * scale)))
    scaled_h = max(1, int(round(h * scale)))
    resized = src.resize((scaled_w, scaled_h), resample=Image.Resampling.BICUBIC)

    anchor_x, anchor_y = _resolve_aspect_position_anchor(position)
    max_left = max(0, scaled_w - canvas_w)
    max_top = max(0, scaled_h - canvas_h)
    base_left = int(round(float(max_left) * anchor_x))
    base_top = int(round(float(max_top) * anchor_y))
    left = int(_clamp(float(base_left + int(shift_x)), 0.0, float(max_left)))
    top = int(_clamp(float(base_top + int(shift_y)), 0.0, float(max_top)))

    return resized.crop((left, top, left + canvas_w, top + canvas_h))


def _build_theme_debug_payload(values: Dict[str, Any]) -> Tuple[str, str]:
    density_mode = str(values.get("density", "comfortable"))
    density_scale = {"compact": 0.88, "comfortable": 1.0, "spacious": 1.12}.get(density_mode, 1.0)
    button_style = str(values.get("button_style", "soft"))

    control_gap = max(2, int(_safe_int(values.get("control_gap", 8), 8)))
    section_padding = max(4, int(_safe_int(values.get("section_padding", 10), 10)))
    panel_padding = max(6, int(_safe_int(values.get("panel_padding", 12), 12)))
    panel_radius = max(0, int(_safe_int(values.get("panel_radius", 18), 18)))
    section_radius = max(0, int(_safe_int(values.get("section_radius", 13), 13)))
    input_radius = max(0, int(_safe_int(values.get("input_radius", 9), 9)))
    viewport_height = max(80, int(_safe_int(values.get("viewport_height", 260), 260)))
    shadow_blur = max(0, int(_safe_int(values.get("shadow_blur", 30), 30)))
    animation_ms = max(0, int(_safe_int(values.get("animation_ms", 260), 260)))

    css_vars: Dict[str, str] = {
        "--mkr-ink": str(values.get("mkr_ink", "#13212f")),
        "--mkr-card": str(values.get("mkr_card", "rgba(247,243,235,0.88)")),
        "--mkr-card-alt": str(values.get("mkr_card_alt", "rgba(255,250,244,0.96)")),
        "--mkr-accent-a": str(values.get("mkr_accent_a", "#2d9c8f")),
        "--mkr-accent-b": str(values.get("mkr_accent_b", "#f39f4d")),
        "--mkr-accent-c": str(values.get("mkr_accent_c", "#d9573b")),
        "--mkr-muted": str(values.get("mkr_muted", "#5a6a78")),
        "--mkr-line": str(values.get("mkr_line", "rgba(16,35,45,0.14)")),
        "--mkr-panel-gradient-start": str(values.get("panel_gradient_start", "#fffdf8")),
        "--mkr-panel-gradient-end": str(values.get("panel_gradient_end", "#f3f8fb")),
        "--mkr-font-family": str(
            values.get("font_family", "\"Space Grotesk\", \"Avenir Next\", \"Gill Sans Nova\", sans-serif")
        ),
        "--mkr-panel-radius": f"{panel_radius}px",
        "--mkr-section-radius": f"{section_radius}px",
        "--mkr-input-radius": f"{input_radius}px",
        "--mkr-panel-padding": f"{panel_padding}px",
        "--mkr-section-padding": f"{section_padding}px",
        "--mkr-control-gap": f"{control_gap}px",
        "--mkr-viewport-height": f"{viewport_height}px",
        "--mkr-font-scale": f"{density_scale:.3f}",
        "--mkr-animation-ms": f"{animation_ms}ms",
        "--mkr-shadow": f"0 {max(0, int(shadow_blur * 0.45))}px {shadow_blur}px {values.get('mkr_shadow_color', 'rgba(24,38,53,0.12)')}",
        "--mkr-button-style": button_style,
    }

    payload = {
        "schema": "mkr_theme_debug_v1",
        "theme_name": str(values.get("theme_name", "mkr_theme_v1")),
        "button_style": button_style,
        "density": density_mode,
        "notes": str(values.get("notes", "")),
        "tokens": css_vars,
    }

    css_text = ":root {\n" + "\n".join(f"  {key}: {value};" for key, value in css_vars.items()) + "\n}"
    return json.dumps(payload, ensure_ascii=False, indent=2), css_text


class MKRCharacterCustomizer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
                "model_path": ("STRING", {"default": ""}),
                "capture_w": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64}),
                "capture_h": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64}),
            },
            "optional": {
                "subject_prompt": ("STRING", {"default": "hero character design"}),
                "outfit_prompt": ("STRING", {"default": "detailed outfit, production-ready costume"}),
                "style_preset": (list(STYLE_PRESETS.keys()), {"default": "cinematic_photoreal"}),
                "shot_type": (SHOT_TYPES, {"default": "full body"}),
                "mood": (MOODS, {"default": "confident"}),
                "add_quality_tags": ("BOOLEAN", {"default": True}),
                "negative_prompt_base": (
                    "STRING",
                    {
                        "default": "bad anatomy, low quality, lowres, deformed",
                        "multiline": True,
                    },
                ),
            },
        }

    # Keep first 4 outputs backward-compatible with existing workflows.
    RETURN_TYPES = (
        "IMAGE",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "IMAGE",
        "STRING",
    )
    RETURN_NAMES = (
        "image",
        "camera_desc",
        "light_desc",
        "settings_out",
        "positive_prompt",
        "negative_prompt",
        "director_prompt",
        "pose_guide",
        "metadata_json",
    )

    FUNCTION = "run"
    CATEGORY = CORE_CHARACTER

    def run(
        self,
        settings_json: str,
        model_path: str,
        capture_w: int,
        capture_h: int,
        subject_prompt: str = "hero character design",
        outfit_prompt: str = "detailed outfit, production-ready costume",
        style_preset: str = "cinematic_photoreal",
        shot_type: str = "full body",
        mood: str = "confident",
        add_quality_tags: bool = True,
        negative_prompt_base: str = "bad anatomy, low quality, lowres, deformed",
    ):
        cfg = _load_runtime_config()
        s = _normalize_settings(_parse_settings_json(settings_json), cfg)

        camera_obj = _as_dict(s.get("camera"))
        light_obj = _as_dict(s.get("light"))
        angle_obj = _as_dict(s.get("angle"))

        camera_pos = _vec3(camera_obj.get("pos"), default=tuple(DEFAULT_SETTINGS_TEMPLATE["camera"]["pos"]))
        light_pos = _vec3(light_obj.get("pos"), default=tuple(DEFAULT_SETTINGS_TEMPLATE["light"]["pos"]))

        bands = {
            "distance_bands": cfg.get("distance_bands", {}),
            "height_bands": cfg.get("height_bands", {}),
            "side_bands": cfg.get("side_bands", {}),
        }
        coord = cfg.get("coordinate_system", {"right_axis": "x", "front_axis": "y", "up_axis": "z"})

        camera_desc = _describe_position(camera_pos, coord, bands)
        light_desc = _describe_position(light_pos, coord, bands)

        params = _as_dict(s.get("params"))
        param_descriptors = _build_param_descriptors(params)

        style_key = style_preset if style_preset in STYLE_PRESETS else "cinematic_photoreal"
        style = STYLE_PRESETS[style_key]
        style_tags = style.get("tags", [])
        style_negative = style.get("negative", [])

        right_axis = coord.get("right_axis", "x")
        front_axis = coord.get("front_axis", "y")
        yaw = (
            math.degrees(math.atan2(_axis_value(camera_pos, right_axis), _axis_value(camera_pos, front_axis))) + 360.0
        ) % 360.0
        lens = _lens_from_distance(_norm(camera_pos))
        facing = _facing_label(yaw)
        framing_hint = _framing_label(_safe_float(angle_obj.get("zoom", 0.0), 0.0))

        camera_prompt = f"{shot_type} composition, {camera_desc} viewpoint, {facing} read, orbit {yaw:.0f} deg, {lens}mm lens"
        light_prompt = f"{light_desc} key light, controlled fill, subtle rim separation"
        direction_tags = [
            f"{mood} tone",
            f"{framing_hint} framing intent",
            "clear silhouette readability",
        ]

        quality_tags = []
        if add_quality_tags:
            quality_tags = [
                "high micro detail",
                "clean anatomy",
                "material separation",
                "balanced dynamic range",
                "production-ready finish",
            ]

        positive_prompt = _join_prompt_parts(
            [
                subject_prompt,
                outfit_prompt,
                f"style preset {style_key.replace('_', ' ')}",
                ", ".join(param_descriptors[:8]),
                camera_prompt,
                light_prompt,
                ", ".join(direction_tags),
                ", ".join(style_tags),
                ", ".join(quality_tags),
            ]
        )

        negative_prompt = _join_prompt_parts(
            [
                negative_prompt_base,
                ", ".join(style_negative),
                ", ".join(GLOBAL_NEGATIVE),
            ]
        )

        director_prompt = f"POSITIVE: {positive_prompt}. NEGATIVE: {negative_prompt}"

        pose_guide_img = _make_pose_guide_image(capture_w, capture_h, params, camera_desc, light_desc)
        scene_size = min(max(180, int(min(capture_w, capture_h) * 0.28)), 320)
        scene_map = _make_scene_map(scene_size, camera_pos, light_pos, coord)

        sheet = _make_director_sheet(
            capture_w,
            capture_h,
            model_path,
            camera_desc,
            light_desc,
            positive_prompt,
            negative_prompt,
            param_descriptors,
            pose_guide_img,
            scene_map,
        )

        metadata = {
            "schema": "mkr_character_director_v3",
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "camera_pos": camera_pos,
            "light_pos": light_pos,
            "camera_desc": camera_desc,
            "light_desc": light_desc,
            "camera_yaw_deg": round(yaw, 3),
            "lens_mm_hint": lens,
            "style_preset": style_key,
            "shot_type": shot_type,
            "mood": mood,
            "param_descriptors": param_descriptors,
            "prompts": {
                "positive": positive_prompt,
                "negative": negative_prompt,
                "director": director_prompt,
            },
            "capture_size": [int(capture_w), int(capture_h)],
            "model_path": model_path or "",
            "settings": s,
        }

        settings_out = _json_dumps_stable(s)
        metadata_json = _json_dumps_stable(metadata)

        return (
            _pil_to_comfy_image(sheet),
            camera_desc,
            light_desc,
            settings_out,
            positive_prompt,
            negative_prompt,
            director_prompt,
            _pil_to_comfy_image(pose_guide_img),
            metadata_json,
        )


class AngleShift:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.5, "step": 0.01}),
                "background_mode": (sorted(BACKGROUND_MODES), {"default": "blur"}),
                "sheet_columns": ("INT", {"default": 4, "min": 3, "max": 6, "step": 1}),
                "label_overlay": ("BOOLEAN", {"default": True}),
                "generate_12_views": ("BOOLEAN", {"default": False}),
            },
        }

    # Keep first 2 outputs backward-compatible with existing workflows.
    RETURN_TYPES = ("STRING", "STRING", "IMAGE", "IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = (
        "angle_string",
        "angles_12_string",
        "shifted_image",
        "angles_12_batch",
        "angles_12_sheet",
        "metadata_json",
    )

    FUNCTION = "run"
    CATEGORY = CORE_CAMERA

    def run(
        self,
        image,
        settings_json: str,
        strength: float = 0.85,
        background_mode: str = "blur",
        sheet_columns: int = 4,
        label_overlay: bool = True,
        generate_12_views: bool = False,
    ):
        cfg = _load_runtime_config()
        s = _normalize_settings(_parse_settings_json(settings_json), cfg)
        angle = _as_dict(s.get("angle"))

        rot = _safe_float(angle.get("rotation", 0.0), 0.0)
        tilt = _safe_float(angle.get("tilt", -30.0), -30.0)
        zoom = _safe_float(angle.get("zoom", 0.0), 0.0)

        strength = _clamp(_safe_float(angle.get("strength", strength), strength), 0.0, 1.5)
        background_mode = str(angle.get("background_mode", background_mode) or "blur").lower()
        if background_mode not in BACKGROUND_MODES:
            background_mode = "blur"

        sheet_columns = _safe_int(angle.get("sheet_columns", sheet_columns), sheet_columns)
        sheet_columns = int(_clamp(float(sheet_columns), 3, 6))
        label_overlay = _safe_bool(angle.get("label_overlay", label_overlay), label_overlay)

        multi = bool(_safe_bool(angle.get("multi12", False), False) or generate_12_views)

        pil_batch = _comfy_batch_to_pil_list(image)
        shifted_batch_pil: List[Image.Image] = []
        first_quad: List[Tuple[float, float]] = []

        for pil in pil_batch:
            shifted, quad = _warp_image(pil, rot, tilt, zoom, strength, background_mode)
            shifted_batch_pil.append(shifted)
            if not first_quad:
                first_quad = quad

        shifted_image = _pil_list_to_comfy_batch(shifted_batch_pil)

        angle_string = self._angle_prompt(rot, tilt, zoom)

        angles_12_string = ""
        batch_12_pil: List[Image.Image] = []
        labels_12: List[str] = []

        if multi:
            source = pil_batch[0] if pil_batch else Image.new("RGB", (512, 512), (0, 0, 0))
            angles = self._best12_angles(tilt, zoom)
            angles_12_string = "\n".join(self._angle_prompt(r, t, zoom) for (r, t) in angles)
            for r, t in angles:
                shifted, _ = _warp_image(source, r, t, zoom, strength, background_mode)
                batch_12_pil.append(shifted)
                labels_12.append(f"r{int(round(r)):03d} t{int(round(t)):02d}")
        else:
            # Always emit one image in secondary outputs for easier chaining.
            source = pil_batch[0] if pil_batch else Image.new("RGB", (512, 512), (0, 0, 0))
            shifted, _ = _warp_image(source, rot, tilt, zoom, strength, background_mode)
            batch_12_pil = [shifted]
            labels_12 = [f"r{int(round(rot)):03d} t{int(round(tilt)):02d}"]

        angles_12_batch = _pil_list_to_comfy_batch(batch_12_pil)
        angles_12_sheet = _pil_to_comfy_image(_make_contact_sheet(batch_12_pil, labels_12, sheet_columns, label_overlay))

        metadata = {
            "schema": "mkr_angle_shift_v3",
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "rotation_deg": rot,
            "tilt_deg": tilt,
            "zoom": zoom,
            "facing": _facing_label(rot),
            "elevation": _elevation_label(tilt),
            "framing": _framing_label(zoom),
            "lens_mm_hint": _lens_from_zoom(zoom),
            "multi12": multi,
            "strength": strength,
            "background_mode": background_mode,
            "sheet_columns": sheet_columns,
            "first_warp_quad": first_quad,
            "input_batch": len(pil_batch),
            "output_batch": len(shifted_batch_pil),
            "angles_12_batch": len(batch_12_pil),
            "settings": s,
        }

        return (
            angle_string,
            angles_12_string,
            shifted_image,
            angles_12_batch,
            angles_12_sheet,
            json.dumps(metadata, ensure_ascii=False),
        )

    def _angle_prompt(self, rotation_deg: float, tilt_deg: float, zoom: float) -> str:
        facing = _facing_label(rotation_deg)
        elev = _elevation_label(tilt_deg)
        framing = _framing_label(zoom)
        lens = _lens_from_zoom(zoom)
        return (
            f"AngleShift: rotation={rotation_deg:.0f}deg, tilt={tilt_deg:.0f}deg, zoom={zoom:.2f}"
            f" | {facing}, {elev}, {framing}, lens {lens}mm"
        )

    def _best12_angles(self, base_tilt: float, zoom: float):
        rots = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
        tilt_bias = _clamp(base_tilt, -45.0, 45.0)
        zoom_influence = _clamp(abs(zoom), 0.0, 1.0)
        spread = 8.0 + zoom_influence * 6.0
        out: List[Tuple[float, float]] = []

        for r in rots:
            radians = math.radians(float(r))
            tilt = tilt_bias + math.sin(radians * 2.0) * spread * 0.35 + math.cos(radians) * spread * 0.25
            out.append((float(r), float(_clamp(tilt, -70.0, 70.0))))
        return out


class Aspect1X:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "aspect_1x": (ASPECT_PRESET_CHOICES, {"default": "Social - 9:16 (Stories/Reels/TikTok)"}),
                "orientation": (ASPECT_ORIENTATION_CHOICES, {"default": "Portrait"}),
                "mode": (["pad", "crop"], {"default": "pad"}),
            },
            "optional": {
                "X • Offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "Y • Offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "Position": (ASPECT_POSITION_CHOICES, {"default": "Center • Center"}),
                "filename_prefix_base": ("STRING", {"default": "AX1"}),
                "background_mode": (sorted(BACKGROUND_MODES), {"default": "blur"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image_out", "filename_labels")
    FUNCTION = "run"
    CATEGORY = CORE_LAYOUT

    def run(
        self,
        image,
        aspect_1x: str = "Social - 9:16 (Stories/Reels/TikTok)",
        orientation: str = "Portrait",
        mode: str = "pad",
        x_offset: int = 0,
        y_offset: int = 0,
        position: str = "Center • Center",
        filename_prefix_base: str = "AX1",
        background_mode: str = "blur",
        **kwargs,
    ):
        target_wh_ratio = _resolve_aspect_wh_ratio(aspect_1x, orientation)
        shape_mode = "crop" if str(mode).lower() == "crop" else "pad"
        bg_mode = str(background_mode or "blur").lower()
        if bg_mode not in BACKGROUND_MODES:
            bg_mode = "blur"
        resolved_x, resolved_y, resolved_position = _resolve_aspect_offsets_and_position(
            x_offset=x_offset,
            y_offset=y_offset,
            position=position,
            **kwargs,
        )

        pil_batch = _comfy_batch_to_pil_list(image)
        out_batch = [
            _reshape_to_aspect_1x(
                pil,
                target_wh_ratio,
                shape_mode,
                bg_mode,
                crop_shift_x=int(resolved_x),
                crop_shift_y=int(resolved_y),
                position=resolved_position,
            )
            for pil in pil_batch
        ]
        aspect_slug = _resolve_aspect_label_slug(aspect_1x, orientation)
        filename_labels = _format_aspect_filename_label(
            filename_prefix_base,
            orientation,
            aspect_slug,
        )
        return (_pil_list_to_comfy_batch(out_batch), filename_labels)


class Aspect1XBatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "orientation": (["Portrait", "Horizontal", "Both"], {"default": "Portrait"}),
                "mode": (["pad", "crop"], {"default": "pad"}),
            },
            "optional": {
                "X • Offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "Y • Offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "Position": (ASPECT_POSITION_CHOICES, {"default": "Center • Center"}),
                "filename_prefix_base": ("STRING", {"default": "AX1"}),
                "background_mode": (sorted(BACKGROUND_MODES), {"default": "blur"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image_out", "filename_labels", "labels_with_descriptions")
    OUTPUT_IS_LIST = (True, True, True)
    FUNCTION = "run"
    CATEGORY = CORE_LAYOUT

    def run(
        self,
        image,
        orientation: str = "Portrait",
        mode: str = "pad",
        x_offset: int = 0,
        y_offset: int = 0,
        position: str = "Center • Center",
        filename_prefix_base: str = "AX1",
        background_mode: str = "blur",
        **kwargs,
    ):
        shape_mode = "crop" if str(mode).lower() == "crop" else "pad"
        bg_mode = str(background_mode or "blur").lower()
        if bg_mode not in BACKGROUND_MODES:
            bg_mode = "blur"
        resolved_x, resolved_y, resolved_position = _resolve_aspect_offsets_and_position(
            x_offset=x_offset,
            y_offset=y_offset,
            position=position,
            **kwargs,
        )

        orientation_modes: List[str]
        ori = str(orientation or "Portrait").strip().lower()
        if ori == "both":
            orientation_modes = ["Portrait", "Horizontal"]
        elif ori == "horizontal":
            orientation_modes = ["Horizontal"]
        else:
            orientation_modes = ["Portrait"]

        # Keep stable order while avoiding duplicate ratios (e.g. square formats).
        ratio_specs: List[Tuple[str, float, str, str]] = []
        seen = set()
        for ori_name in orientation_modes:
            for choice in ASPECT_PRESET_CHOICES:
                ratio = _resolve_aspect_wh_ratio(choice, ori_name)
                key = f"{ori_name}:{ratio:.8f}"
                if key in seen:
                    continue
                seen.add(key)
                aspect_slug = _resolve_aspect_label_slug(choice, ori_name)
                ratio_specs.append((ori_name, ratio, aspect_slug, str(choice)))

        pil_batch = _comfy_batch_to_pil_list(image)
        out_images: List[torch.Tensor] = []
        filename_labels: List[str] = []
        labels_with_descriptions: List[str] = []
        for pil in pil_batch:
            for ori_name, ratio, aspect_slug, aspect_choice in ratio_specs:
                out = _reshape_to_aspect_1x(
                    pil,
                    ratio,
                    shape_mode,
                    bg_mode,
                    crop_shift_x=int(resolved_x),
                    crop_shift_y=int(resolved_y),
                    position=resolved_position,
                )
                out_images.append(_pil_to_comfy_image(out))
                filename_label = _format_aspect_filename_label(
                    filename_prefix_base,
                    ori_name,
                    aspect_slug,
                )
                filename_labels.append(filename_label)
                labels_with_descriptions.append(
                    _format_aspect_label_description(
                        filename_label,
                        aspect_choice,
                        ori_name,
                        aspect_slug,
                    )
                )

        if not out_images:
            blank = Image.new("RGB", (64, 64), (0, 0, 0))
            out_images = [_pil_to_comfy_image(blank)]
            fallback_label = _format_aspect_filename_label(filename_prefix_base, "Portrait", "1x1")
            filename_labels = [fallback_label]
            labels_with_descriptions = [_format_aspect_label_description(fallback_label, "", "Portrait", "1x1")]

        return (out_images, filename_labels, labels_with_descriptions)


class AxBCompare:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "orientation": (["horizontal", "vertical"], {"default": "horizontal"}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = INSPECT_COMPARE

    def run(
        self,
        image_a,
        image_b,
        orientation: str = "horizontal",
        **kwargs,
    ):
        split_percent = float(kwargs.get("split_percent", 0.5))
        fit_mode = str(kwargs.get("fit_mode", "contain"))
        swap_inputs = bool(kwargs.get("swap_inputs", False))
        a_batch = _comfy_batch_to_pil_list(image_a)
        b_batch = _comfy_batch_to_pil_list(image_b)
        if not a_batch:
            a_batch = [Image.new("RGB", (512, 512), (0, 0, 0))]
        if not b_batch:
            b_batch = [Image.new("RGB", (512, 512), (0, 0, 0))]

        if swap_inputs:
            a_batch, b_batch = b_batch, a_batch

        preview_a = _save_temp_preview(a_batch[0], prefix="mkrshift_axb_a")
        preview_b = _save_temp_preview(b_batch[0], prefix="mkrshift_axb_b")

        orientation_norm = str(orientation or "horizontal").strip().lower()
        if orientation_norm not in {"vertical", "horizontal"}:
            orientation_norm = "horizontal"
        split_norm = float(split_percent if split_percent is not None else 0.5)
        split_norm = max(0.0, min(1.0, split_norm))
        fit_norm = str(fit_mode or "contain").strip().lower()
        if fit_norm not in {"contain", "cover", "stretch"}:
            fit_norm = "contain"

        ui_payload: Dict[str, Any] = {
            "compare_state": [
                {
                    "orientation": orientation_norm,
                    "split_percent": split_norm,
                    "fit_mode": fit_norm,
                    "swap_inputs": bool(swap_inputs),
                }
            ]
        }
        if preview_a:
            ui_payload["a_preview"] = [preview_a]
        if preview_b:
            ui_payload["b_preview"] = [preview_b]

        return {
            "ui": ui_payload,
            "result": (),
        }


class MKRThemeDebugger:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "theme_name": ("STRING", {"default": "mkr_theme_v1"}),
                "mkr_ink": ("STRING", {"default": "#13212f"}),
                "mkr_card": ("STRING", {"default": "rgba(247,243,235,0.88)"}),
                "mkr_card_alt": ("STRING", {"default": "rgba(255,250,244,0.96)"}),
                "mkr_accent_a": ("STRING", {"default": "#2d9c8f"}),
                "mkr_accent_b": ("STRING", {"default": "#f39f4d"}),
                "mkr_accent_c": ("STRING", {"default": "#d9573b"}),
                "mkr_muted": ("STRING", {"default": "#5a6a78"}),
                "mkr_line": ("STRING", {"default": "rgba(16,35,45,0.14)"}),
                "mkr_shadow_color": ("STRING", {"default": "rgba(24,38,53,0.12)"}),
                "panel_gradient_start": ("STRING", {"default": "#fffdf8"}),
                "panel_gradient_end": ("STRING", {"default": "#f3f8fb"}),
                "font_family": (
                    "STRING",
                    {"default": "\"Space Grotesk\", \"Avenir Next\", \"Gill Sans Nova\", sans-serif"},
                ),
                "panel_radius": ("INT", {"default": 18, "min": 0, "max": 80, "step": 1}),
                "section_radius": ("INT", {"default": 13, "min": 0, "max": 80, "step": 1}),
                "input_radius": ("INT", {"default": 9, "min": 0, "max": 80, "step": 1}),
                "panel_padding": ("INT", {"default": 12, "min": 2, "max": 64, "step": 1}),
                "section_padding": ("INT", {"default": 10, "min": 2, "max": 64, "step": 1}),
                "control_gap": ("INT", {"default": 8, "min": 2, "max": 48, "step": 1}),
                "viewport_height": ("INT", {"default": 260, "min": 80, "max": 1200, "step": 2}),
                "shadow_blur": ("INT", {"default": 30, "min": 0, "max": 120, "step": 1}),
                "animation_ms": ("INT", {"default": 260, "min": 0, "max": 3000, "step": 10}),
                "button_style": (["soft", "solid", "outline"], {"default": "soft"}),
                "density": (["compact", "comfortable", "spacious"], {"default": "comfortable"}),
            },
            "optional": {
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("theme_json", "theme_css_vars")
    FUNCTION = "run"
    CATEGORY = INSPECT_DEBUG

    def run(
        self,
        theme_name: str,
        mkr_ink: str,
        mkr_card: str,
        mkr_card_alt: str,
        mkr_accent_a: str,
        mkr_accent_b: str,
        mkr_accent_c: str,
        mkr_muted: str,
        mkr_line: str,
        mkr_shadow_color: str,
        panel_gradient_start: str,
        panel_gradient_end: str,
        font_family: str,
        panel_radius: int,
        section_radius: int,
        input_radius: int,
        panel_padding: int,
        section_padding: int,
        control_gap: int,
        viewport_height: int,
        shadow_blur: int,
        animation_ms: int,
        button_style: str,
        density: str,
        notes: str = "",
    ):
        values = {
            "theme_name": theme_name,
            "mkr_ink": mkr_ink,
            "mkr_card": mkr_card,
            "mkr_card_alt": mkr_card_alt,
            "mkr_accent_a": mkr_accent_a,
            "mkr_accent_b": mkr_accent_b,
            "mkr_accent_c": mkr_accent_c,
            "mkr_muted": mkr_muted,
            "mkr_line": mkr_line,
            "mkr_shadow_color": mkr_shadow_color,
            "panel_gradient_start": panel_gradient_start,
            "panel_gradient_end": panel_gradient_end,
            "font_family": font_family,
            "panel_radius": panel_radius,
            "section_radius": section_radius,
            "input_radius": input_radius,
            "panel_padding": panel_padding,
            "section_padding": section_padding,
            "control_gap": control_gap,
            "viewport_height": viewport_height,
            "shadow_blur": shadow_blur,
            "animation_ms": animation_ms,
            "button_style": button_style,
            "density": density,
            "notes": notes,
        }
        theme_json, theme_css = _build_theme_debug_payload(values)
        return (theme_json, theme_css)
