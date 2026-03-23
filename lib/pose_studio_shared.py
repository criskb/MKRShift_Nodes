import json
import math
from copy import deepcopy
from typing import Any, Dict, List, Tuple


POSE_SCHEMA = "mkr_pose_studio_v1"
POSE_SCHEMA_VERSION = 1
IMAGE_FIT_ANCHOR_KEYS = (
    "head",
    "neck",
    "eye_l",
    "eye_r",
    "chin",
    "chest",
    "pelvis",
    "shoulder_l",
    "shoulder_r",
    "elbow_l",
    "elbow_r",
    "wrist_l",
    "wrist_r",
    "hand_l",
    "hand_r",
    "thumb_l",
    "thumb_r",
    "index_l",
    "index_r",
    "knee_l",
    "knee_r",
    "ankle_l",
    "ankle_r",
    "heel_l",
    "heel_r",
    "toe_l",
    "toe_r",
)
IMAGE_FIT_ANCHOR_GROUPS = {
    "head_face": ("head", "neck", "eye_l", "eye_r", "chin"),
    "torso": ("chest", "pelvis", "shoulder_l", "shoulder_r"),
    "arms": ("elbow_l", "elbow_r"),
    "hands": ("wrist_l", "wrist_r"),
    "fingers": ("hand_l", "hand_r", "thumb_l", "thumb_r", "index_l", "index_r"),
    "legs": ("knee_l", "knee_r"),
    "feet": ("ankle_l", "ankle_r", "heel_l", "heel_r"),
    "toes": ("toe_l", "toe_r"),
}
LEGACY_IMAGE_FIT_GROUP_MAP = {
    "face": ("head_face",),
    "body": ("torso", "arms", "legs"),
    "hands": ("hands", "fingers"),
    "feet": ("feet", "toes"),
}

LEFT_RIGHT_KEYS = (
    ("arm_raise_l", "arm_raise_r", "same"),
    ("arm_forward_l", "arm_forward_r", "invert"),
    ("arm_twist_l", "arm_twist_r", "invert"),
    ("elbow_bend_l", "elbow_bend_r", "same"),
    ("wrist_twist_l", "wrist_twist_r", "invert"),
    ("hip_lift_l", "hip_lift_r", "same"),
    ("hip_side_l", "hip_side_r", "invert"),
    ("knee_bend_l", "knee_bend_r", "same"),
    ("foot_point_l", "foot_point_r", "same"),
)

CONTROL_SPECS = {
    "root_yaw": {"default": 0.0, "min": -180.0, "max": 180.0},
    "root_pitch": {"default": 2.0, "min": -45.0, "max": 45.0},
    "root_roll": {"default": 0.0, "min": -35.0, "max": 35.0},
    "spine_bend": {"default": 6.0, "min": -45.0, "max": 45.0},
    "spine_twist": {"default": 0.0, "min": -60.0, "max": 60.0},
    "head_yaw": {"default": 6.0, "min": -85.0, "max": 85.0},
    "head_pitch": {"default": -4.0, "min": -50.0, "max": 50.0},
    "head_roll": {"default": 0.0, "min": -40.0, "max": 40.0},
    "arm_raise_l": {"default": 18.0, "min": -45.0, "max": 135.0},
    "arm_forward_l": {"default": 10.0, "min": -120.0, "max": 120.0},
    "arm_twist_l": {"default": 0.0, "min": -120.0, "max": 120.0},
    "elbow_bend_l": {"default": 18.0, "min": 0.0, "max": 150.0},
    "wrist_twist_l": {"default": 0.0, "min": -120.0, "max": 120.0},
    "arm_raise_r": {"default": 14.0, "min": -45.0, "max": 135.0},
    "arm_forward_r": {"default": -8.0, "min": -120.0, "max": 120.0},
    "arm_twist_r": {"default": 0.0, "min": -120.0, "max": 120.0},
    "elbow_bend_r": {"default": 12.0, "min": 0.0, "max": 150.0},
    "wrist_twist_r": {"default": 0.0, "min": -120.0, "max": 120.0},
    "hip_lift_l": {"default": 4.0, "min": -60.0, "max": 95.0},
    "hip_side_l": {"default": 6.0, "min": -45.0, "max": 45.0},
    "knee_bend_l": {"default": 6.0, "min": 0.0, "max": 155.0},
    "foot_point_l": {"default": 6.0, "min": -45.0, "max": 75.0},
    "hip_lift_r": {"default": -2.0, "min": -60.0, "max": 95.0},
    "hip_side_r": {"default": -4.0, "min": -45.0, "max": 45.0},
    "knee_bend_r": {"default": 2.0, "min": 0.0, "max": 155.0},
    "foot_point_r": {"default": 2.0, "min": -45.0, "max": 75.0},
}

POSE_PRESETS = {
    "neutral": {},
    "heroic": {
        "root_yaw": 12.0,
        "root_pitch": 4.0,
        "spine_bend": 10.0,
        "head_yaw": 10.0,
        "arm_raise_l": 28.0,
        "arm_forward_l": 14.0,
        "elbow_bend_l": 34.0,
        "arm_raise_r": 10.0,
        "arm_forward_r": -14.0,
        "hip_lift_l": 9.0,
        "hip_side_l": 10.0,
        "hip_lift_r": -6.0,
        "hip_side_r": -7.0,
        "knee_bend_l": 12.0,
    },
    "contrapposto": {
        "root_yaw": 18.0,
        "root_roll": 7.0,
        "spine_bend": 8.0,
        "spine_twist": 11.0,
        "head_yaw": 16.0,
        "head_pitch": -6.0,
        "arm_raise_l": 24.0,
        "arm_forward_l": 12.0,
        "elbow_bend_l": 26.0,
        "arm_raise_r": 2.0,
        "arm_forward_r": -18.0,
        "hip_lift_l": 10.0,
        "hip_side_l": 14.0,
        "hip_lift_r": -8.0,
        "hip_side_r": -9.0,
        "knee_bend_l": 18.0,
        "knee_bend_r": 4.0,
    },
    "run_start": {
        "root_pitch": 14.0,
        "spine_bend": 18.0,
        "head_pitch": -10.0,
        "arm_raise_l": 40.0,
        "arm_forward_l": 42.0,
        "elbow_bend_l": 64.0,
        "arm_raise_r": 26.0,
        "arm_forward_r": -36.0,
        "elbow_bend_r": 44.0,
        "hip_lift_l": 30.0,
        "hip_side_l": 10.0,
        "knee_bend_l": 44.0,
        "foot_point_l": 18.0,
        "hip_lift_r": -20.0,
        "hip_side_r": -8.0,
        "knee_bend_r": 12.0,
        "foot_point_r": -4.0,
    },
    "power_stance": {
        "root_yaw": 10.0,
        "root_pitch": 3.0,
        "root_roll": 4.0,
        "spine_bend": 9.0,
        "spine_twist": 8.0,
        "head_yaw": 8.0,
        "arm_raise_l": 20.0,
        "arm_forward_l": 10.0,
        "elbow_bend_l": 24.0,
        "arm_raise_r": 6.0,
        "arm_forward_r": -10.0,
        "elbow_bend_r": 12.0,
        "hip_lift_l": 8.0,
        "hip_side_l": 10.0,
        "hip_lift_r": -8.0,
        "hip_side_r": -10.0,
        "knee_bend_l": 10.0,
        "knee_bend_r": 4.0,
    },
    "reach_up": {
        "root_pitch": 8.0,
        "spine_bend": 16.0,
        "head_pitch": -10.0,
        "arm_raise_l": 84.0,
        "arm_forward_l": 20.0,
        "arm_twist_l": 10.0,
        "elbow_bend_l": 18.0,
        "arm_raise_r": 32.0,
        "arm_forward_r": -12.0,
        "elbow_bend_r": 22.0,
        "hip_lift_l": 14.0,
        "hip_side_l": 8.0,
        "hip_lift_r": -8.0,
        "hip_side_r": -6.0,
        "knee_bend_l": 14.0,
        "foot_point_l": 10.0,
    },
    "kneel_pose": {
        "root_pitch": 10.0,
        "spine_bend": 12.0,
        "head_pitch": -6.0,
        "arm_raise_l": 18.0,
        "arm_forward_l": 12.0,
        "elbow_bend_l": 36.0,
        "arm_raise_r": 6.0,
        "arm_forward_r": -16.0,
        "elbow_bend_r": 20.0,
        "hip_lift_l": 26.0,
        "hip_side_l": 8.0,
        "knee_bend_l": 82.0,
        "foot_point_l": 18.0,
        "hip_lift_r": -12.0,
        "hip_side_r": -6.0,
        "knee_bend_r": 24.0,
        "foot_point_r": -6.0,
    },
    "hands_behind_back": {
        "root_yaw": 8.0,
        "spine_bend": 6.0,
        "spine_twist": 6.0,
        "head_yaw": 14.0,
        "head_pitch": -4.0,
        "arm_raise_l": -8.0,
        "arm_forward_l": -42.0,
        "arm_twist_l": -36.0,
        "elbow_bend_l": 52.0,
        "wrist_twist_l": -18.0,
        "arm_raise_r": -10.0,
        "arm_forward_r": 42.0,
        "arm_twist_r": 36.0,
        "elbow_bend_r": 48.0,
        "wrist_twist_r": 18.0,
        "hip_lift_l": 8.0,
        "hip_side_l": 8.0,
        "hip_lift_r": -6.0,
        "hip_side_r": -8.0,
        "knee_bend_l": 8.0,
        "knee_bend_r": 4.0,
    },
    "pinup_sway": {
        "root_yaw": 16.0,
        "root_roll": 8.0,
        "spine_bend": 10.0,
        "spine_twist": 14.0,
        "head_yaw": 18.0,
        "head_pitch": -8.0,
        "head_roll": 6.0,
        "arm_raise_l": 34.0,
        "arm_forward_l": 18.0,
        "elbow_bend_l": 44.0,
        "wrist_twist_l": 12.0,
        "arm_raise_r": 4.0,
        "arm_forward_r": -22.0,
        "elbow_bend_r": 22.0,
        "hip_lift_l": 14.0,
        "hip_side_l": 16.0,
        "hip_lift_r": -12.0,
        "hip_side_r": -10.0,
        "knee_bend_l": 22.0,
        "foot_point_l": 12.0,
        "knee_bend_r": 6.0,
    },
    "crouch_ready": {
        "root_pitch": 18.0,
        "spine_bend": 20.0,
        "head_pitch": -8.0,
        "arm_raise_l": 26.0,
        "arm_forward_l": 24.0,
        "elbow_bend_l": 58.0,
        "arm_raise_r": 18.0,
        "arm_forward_r": -18.0,
        "elbow_bend_r": 46.0,
        "hip_lift_l": 20.0,
        "hip_side_l": 10.0,
        "knee_bend_l": 54.0,
        "foot_point_l": 10.0,
        "hip_lift_r": -18.0,
        "hip_side_r": -8.0,
        "knee_bend_r": 48.0,
        "foot_point_r": 8.0,
    },
}

POSE_BONES = [
    ("pelvis", "spine"),
    ("spine", "chest"),
    ("chest", "neck"),
    ("neck", "head"),
    ("head", "eye_l"),
    ("head", "eye_r"),
    ("head", "chin"),
    ("chest", "shoulder_l"),
    ("shoulder_l", "elbow_l"),
    ("elbow_l", "wrist_l"),
    ("wrist_l", "hand_l"),
    ("hand_l", "thumb_l"),
    ("hand_l", "index_l"),
    ("chest", "shoulder_r"),
    ("shoulder_r", "elbow_r"),
    ("elbow_r", "wrist_r"),
    ("wrist_r", "hand_r"),
    ("hand_r", "thumb_r"),
    ("hand_r", "index_r"),
    ("pelvis", "hip_l"),
    ("hip_l", "knee_l"),
    ("knee_l", "ankle_l"),
    ("ankle_l", "heel_l"),
    ("ankle_l", "toe_l"),
    ("pelvis", "hip_r"),
    ("hip_r", "knee_r"),
    ("knee_r", "ankle_r"),
    ("ankle_r", "heel_r"),
    ("ankle_r", "toe_r"),
]


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        value_f = float(value)
    except Exception:
        value_f = float(default)
    return max(float(lo), min(float(hi), value_f))


def _identity3() -> List[List[float]]:
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _matmul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    out = [[0.0, 0.0, 0.0] for _ in range(3)]
    for row in range(3):
        for col in range(3):
            out[row][col] = a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col]
    return out


def _matvec(m: List[List[float]], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _rot_x(deg: float) -> List[List[float]]:
    rad = math.radians(float(deg))
    c = math.cos(rad)
    s = math.sin(rad)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def _rot_y(deg: float) -> List[List[float]]:
    rad = math.radians(float(deg))
    c = math.cos(rad)
    s = math.sin(rad)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _rot_z(deg: float) -> List[List[float]]:
    rad = math.radians(float(deg))
    c = math.cos(rad)
    s = math.sin(rad)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _compose_rot(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> List[List[float]]:
    return _matmul(_rot_y(ry), _matmul(_rot_x(rx), _rot_z(rz)))


def _add(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _round_vec(v: Tuple[float, float, float], digits: int = 4) -> List[float]:
    return [round(float(v[0]), digits), round(float(v[1]), digits), round(float(v[2]), digits)]


def _sorted_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


def default_pose_settings() -> Dict[str, Any]:
    controls = {key: spec["default"] for key, spec in CONTROL_SPECS.items()}
    return {
        "schema": POSE_SCHEMA,
        "schema_version": POSE_SCHEMA_VERSION,
        "pose_name": "Neutral",
        "pose_preset": "neutral",
        "mirror_mode": "off",
        "view": {"yaw": 28.0, "pitch": 8.0, "zoom": 1.0},
        "image_fit": {
            "fit_mode": "fit_from_image_structured",
            "strength": 1.0,
            "selected_anchor": "head",
            "anchors": {},
            "frame_hint": None,
            "reference_image_data_url": "",
            "reference_image_name": "",
            "enabled_groups": {
                key: True
                for key in IMAGE_FIT_ANCHOR_GROUPS.keys()
            },
        },
        "controls": controls,
    }


def _normalize_enabled_anchor_groups(raw_enabled_groups: Dict[str, Any]) -> Dict[str, bool]:
    normalized = {
        key: True
        for key in IMAGE_FIT_ANCHOR_GROUPS.keys()
    }
    if not isinstance(raw_enabled_groups, dict):
        return normalized
    for key in IMAGE_FIT_ANCHOR_GROUPS.keys():
        if key in raw_enabled_groups:
            normalized[key] = bool(raw_enabled_groups.get(key, True))
    for legacy_key, mapped_keys in LEGACY_IMAGE_FIT_GROUP_MAP.items():
        if legacy_key not in raw_enabled_groups:
            continue
        value = bool(raw_enabled_groups.get(legacy_key, True))
        for mapped_key in mapped_keys:
            if mapped_key not in raw_enabled_groups:
                normalized[mapped_key] = value
    return normalized


def parse_pose_settings(raw: Any) -> Dict[str, Any]:
    base = default_pose_settings()
    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
    elif isinstance(raw, dict):
        payload = deepcopy(raw)
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    base["pose_name"] = str(payload.get("pose_name") or base["pose_name"]).strip() or base["pose_name"]
    preset = str(payload.get("pose_preset") or base["pose_preset"]).strip().lower()
    base["pose_preset"] = preset if preset in POSE_PRESETS else "neutral"

    mirror_mode = str(payload.get("mirror_mode") or base["mirror_mode"]).strip().lower()
    base["mirror_mode"] = mirror_mode if mirror_mode in {"off", "left_to_right", "right_to_left"} else "off"

    view = payload.get("view") if isinstance(payload.get("view"), dict) else {}
    base["view"] = {
        "yaw": _clamp(view.get("yaw"), -180.0, 180.0, base["view"]["yaw"]),
        "pitch": _clamp(view.get("pitch"), -85.0, 85.0, base["view"]["pitch"]),
        "zoom": _clamp(view.get("zoom"), 0.4, 2.4, base["view"]["zoom"]),
    }

    raw_image_fit = payload.get("image_fit") if isinstance(payload.get("image_fit"), dict) else {}
    raw_anchors = raw_image_fit.get("anchors") if isinstance(raw_image_fit.get("anchors"), dict) else {}
    raw_enabled_groups = raw_image_fit.get("enabled_groups") if isinstance(raw_image_fit.get("enabled_groups"), dict) else {}
    raw_frame_hint = raw_image_fit.get("frame_hint") if isinstance(raw_image_fit.get("frame_hint"), dict) else {}
    anchors: Dict[str, Dict[str, float]] = {}
    for key in IMAGE_FIT_ANCHOR_KEYS:
        entry = raw_anchors.get(key)
        if not isinstance(entry, dict):
            continue
        x = _clamp(entry.get("x"), 0.0, 1.0, 0.5)
        y = _clamp(entry.get("y"), 0.0, 1.0, 0.5)
        anchors[key] = {"x": x, "y": y}
    selected_anchor = str(raw_image_fit.get("selected_anchor") or "head").strip().lower()
    fit_mode = str(raw_image_fit.get("fit_mode") or "fit_from_image_structured").strip().lower()
    if fit_mode not in {"fit_from_image", "fit_from_image_structured"}:
        fit_mode = "fit_from_image_structured"
    fit_strength = _clamp(raw_image_fit.get("strength"), 0.0, 1.0, 1.0)
    reference_image_data_url = str(raw_image_fit.get("reference_image_data_url") or "").strip()
    reference_image_name = str(raw_image_fit.get("reference_image_name") or "").strip()
    frame_hint = None
    if raw_frame_hint:
        frame_hint = {
            "cx": _clamp(raw_frame_hint.get("cx"), 0.0, 1.0, 0.5),
            "cy": _clamp(raw_frame_hint.get("cy"), 0.0, 1.0, 0.5),
            "bw": _clamp(raw_frame_hint.get("bw"), 0.0, 1.0, 0.0),
            "bh": _clamp(raw_frame_hint.get("bh"), 0.0, 1.0, 0.0),
        }
    base["image_fit"] = {
        "fit_mode": fit_mode,
        "strength": fit_strength,
        "selected_anchor": selected_anchor if selected_anchor in IMAGE_FIT_ANCHOR_KEYS else "head",
        "anchors": anchors,
        "frame_hint": frame_hint,
        "reference_image_data_url": reference_image_data_url,
        "reference_image_name": reference_image_name,
        "enabled_groups": _normalize_enabled_anchor_groups(raw_enabled_groups),
    }

    raw_controls = payload.get("controls") if isinstance(payload.get("controls"), dict) else {}
    controls: Dict[str, float] = {}
    for key, spec in CONTROL_SPECS.items():
        controls[key] = _clamp(raw_controls.get(key), spec["min"], spec["max"], spec["default"])
    base["controls"] = controls
    base["schema"] = POSE_SCHEMA
    base["schema_version"] = POSE_SCHEMA_VERSION
    return base


def apply_pose_preset(settings: Dict[str, Any], preset_name: str) -> Dict[str, Any]:
    preset_key = str(preset_name or "neutral").strip().lower()
    if preset_key not in POSE_PRESETS:
        return settings
    controls = settings.get("controls", {})
    for key, spec in CONTROL_SPECS.items():
        controls[key] = float(spec["default"])
    for key, value in POSE_PRESETS[preset_key].items():
        if key in CONTROL_SPECS:
            controls[key] = _clamp(value, CONTROL_SPECS[key]["min"], CONTROL_SPECS[key]["max"], CONTROL_SPECS[key]["default"])
    settings["controls"] = controls
    settings["pose_preset"] = preset_key
    if not str(settings.get("pose_name") or "").strip():
        settings["pose_name"] = preset_key.replace("_", " ").title()
    return settings


def mirror_pose_controls(settings: Dict[str, Any], source_mode: str) -> Dict[str, Any]:
    if source_mode not in {"left_to_right", "right_to_left"}:
        return settings
    controls = settings.get("controls", {})
    for left_key, right_key, mode in LEFT_RIGHT_KEYS:
        if source_mode == "left_to_right":
            source_value = controls.get(left_key, CONTROL_SPECS[left_key]["default"])
            controls[right_key] = float(source_value) if mode == "same" else float(-source_value)
        else:
            source_value = controls.get(right_key, CONTROL_SPECS[right_key]["default"])
            controls[left_key] = float(source_value) if mode == "same" else float(-source_value)
    settings["controls"] = controls
    settings["mirror_mode"] = source_mode
    return settings


def normalize_pose_settings(raw: Any, preset_name: str = "from_settings", mirror_mode: str = "from_settings") -> Dict[str, Any]:
    settings = parse_pose_settings(raw)
    explicit_preset = str(preset_name or "from_settings").strip().lower()
    if explicit_preset != "from_settings":
        apply_pose_preset(settings, explicit_preset)

    resolved_mirror = str(mirror_mode or "from_settings").strip().lower()
    if resolved_mirror == "from_settings":
        resolved_mirror = str(settings.get("mirror_mode") or "off").strip().lower()
    mirror_pose_controls(settings, resolved_mirror)
    return settings


def build_pose_points(settings: Dict[str, Any]) -> Dict[str, Tuple[float, float, float]]:
    c = settings.get("controls", {})

    pelvis = (0.0, 1.05, 0.0)
    root_rot = _compose_rot(c["root_pitch"], c["root_yaw"], c["root_roll"])
    spine_rot = _matmul(root_rot, _compose_rot(c["spine_bend"], c["spine_twist"], 0.0))
    head_rot = _matmul(spine_rot, _compose_rot(c["head_pitch"], c["head_yaw"], c["head_roll"]))

    spine = _add(pelvis, _matvec(root_rot, (0.0, 0.22, 0.0)))
    chest = _add(spine, _matvec(spine_rot, (0.0, 0.24, 0.0)))
    neck = _add(chest, _matvec(spine_rot, (0.0, 0.15, 0.0)))
    head = _add(neck, _matvec(head_rot, (0.0, 0.18, 0.0)))
    eye_l = _add(head, _matvec(head_rot, (-0.055, 0.025, 0.075)))
    eye_r = _add(head, _matvec(head_rot, (0.055, 0.025, 0.075)))
    chin = _add(head, _matvec(head_rot, (0.0, -0.07, 0.085)))

    points: Dict[str, Tuple[float, float, float]] = {
        "pelvis": pelvis,
        "spine": spine,
        "chest": chest,
        "neck": neck,
        "head": head,
        "eye_l": eye_l,
        "eye_r": eye_r,
        "chin": chin,
    }

    for side_name, sign in (("l", -1.0), ("r", 1.0)):
        shoulder = _add(chest, _matvec(spine_rot, (0.22 * sign, 0.05, 0.0)))
        arm_raise = c[f"arm_raise_{side_name}"]
        arm_forward = c[f"arm_forward_{side_name}"]
        arm_twist = c[f"arm_twist_{side_name}"]
        elbow_bend = c[f"elbow_bend_{side_name}"]
        wrist_twist = c[f"wrist_twist_{side_name}"]

        shoulder_rot = _matmul(
            spine_rot,
            _compose_rot(-arm_forward, arm_twist, -sign * arm_raise),
        )
        elbow = _add(shoulder, _matvec(shoulder_rot, (0.32 * sign, -0.06, 0.01)))
        elbow_rot = _matmul(shoulder_rot, _compose_rot(0.0, wrist_twist * 0.12, -sign * elbow_bend))
        wrist = _add(elbow, _matvec(elbow_rot, (0.28 * sign, -0.04, 0.02)))
        hand = _add(wrist, _matvec(elbow_rot, (0.16 * sign, -0.02, 0.04)))
        thumb = _add(hand, _matvec(elbow_rot, (0.045 * sign, 0.012, 0.055)))
        index = _add(hand, _matvec(elbow_rot, (0.085 * sign, -0.004, 0.105)))

        hip = _add(pelvis, _matvec(root_rot, (0.12 * sign, -0.04, 0.0)))
        hip_lift = c[f"hip_lift_{side_name}"]
        hip_side = c[f"hip_side_{side_name}"]
        knee_bend = c[f"knee_bend_{side_name}"]
        foot_point = c[f"foot_point_{side_name}"]

        hip_rot = _matmul(root_rot, _compose_rot(-hip_lift, 0.0, -sign * hip_side))
        knee = _add(hip, _matvec(hip_rot, (0.06 * sign, -0.5, 0.02)))
        knee_rot = _matmul(hip_rot, _compose_rot(knee_bend, 0.0, 0.0))
        ankle = _add(knee, _matvec(knee_rot, (0.03 * sign, -0.46, 0.02)))
        foot_rot = _matmul(knee_rot, _compose_rot(-foot_point, 0.0, 0.0))
        heel = _add(ankle, _matvec(foot_rot, (-0.035 * sign, -0.015, -0.085)))
        toe = _add(ankle, _matvec(foot_rot, (0.05 * sign, -0.03, 0.22)))

        points[f"shoulder_{side_name}"] = shoulder
        points[f"elbow_{side_name}"] = elbow
        points[f"wrist_{side_name}"] = wrist
        points[f"hand_{side_name}"] = hand
        points[f"thumb_{side_name}"] = thumb
        points[f"index_{side_name}"] = index
        points[f"hip_{side_name}"] = hip
        points[f"knee_{side_name}"] = knee
        points[f"ankle_{side_name}"] = ankle
        points[f"heel_{side_name}"] = heel
        points[f"toe_{side_name}"] = toe

    return points


def project_pose_points(
    points: Dict[str, Tuple[float, float, float]],
    width: int,
    height: int,
    view: Dict[str, Any],
) -> Dict[str, Tuple[float, float]]:
    yaw = -float(view.get("yaw", 0.0))
    pitch = -float(view.get("pitch", 0.0))
    zoom = float(view.get("zoom", 1.0))
    pan_x = float(view.get("pan_x", 0.0))
    pan_y = float(view.get("pan_y", 0.0))
    rot = _matmul(_rot_x(pitch), _rot_y(yaw))

    projected: Dict[str, Tuple[float, float]] = {}
    transformed: List[Tuple[float, float, float]] = []
    for key, pos in points.items():
        rotated = _matvec(rot, pos)
        transformed.append(rotated)
        projected[key] = (rotated[0], rotated[1])

    xs = [pos[0] for pos in transformed] or [0.0]
    ys = [pos[1] for pos in transformed] or [0.0]
    span_x = max(max(xs) - min(xs), 0.001)
    span_y = max(max(ys) - min(ys), 0.001)
    scale = min((width * 0.56) / span_x, (height * 0.72) / span_y) * zoom
    center_x = width * (0.5 + pan_x * 0.12)
    center_y = height * (0.63 - pan_y * 0.12)

    screen: Dict[str, Tuple[float, float]] = {}
    for key, (x, y) in projected.items():
        screen[key] = (center_x + x * scale, center_y - (y - 1.0) * scale)
    return screen


def describe_pose(settings: Dict[str, Any]) -> str:
    c = settings.get("controls", {})
    tags: List[str] = []
    preset = str(settings.get("pose_preset") or "neutral").replace("_", " ")
    tags.append(preset)

    twist = c.get("spine_twist", 0.0)
    if abs(twist) > 8:
        tags.append("torso twist")

    left_arm = c.get("arm_raise_l", 0.0)
    right_arm = c.get("arm_raise_r", 0.0)
    if max(left_arm, right_arm) > 45:
        tags.append("raised arm read")
    elif max(left_arm, right_arm) > 20:
        tags.append("open arm gesture")

    if c.get("knee_bend_l", 0.0) > 22 or c.get("knee_bend_r", 0.0) > 22:
        tags.append("active leg bend")

    if abs(c.get("head_yaw", 0.0)) > 10:
        tags.append("head turn")

    if abs(c.get("root_roll", 0.0)) > 5 or abs(c.get("hip_side_l", 0.0) - c.get("hip_side_r", 0.0)) > 8:
        tags.append("weight shift")

    return ", ".join(tags)


def pose_payload(settings: Dict[str, Any]) -> Dict[str, Any]:
    points = build_pose_points(settings)
    joints = {name: _round_vec(value) for name, value in points.items()}
    payload = {
        "schema": POSE_SCHEMA,
        "schema_version": POSE_SCHEMA_VERSION,
        "pose_name": settings.get("pose_name", "Neutral"),
        "pose_preset": settings.get("pose_preset", "neutral"),
        "mirror_mode": settings.get("mirror_mode", "off"),
        "view": {
            "yaw": round(float(settings.get("view", {}).get("yaw", 0.0)), 4),
            "pitch": round(float(settings.get("view", {}).get("pitch", 0.0)), 4),
            "zoom": round(float(settings.get("view", {}).get("zoom", 1.0)), 4),
            "pan_x": round(float(settings.get("view", {}).get("pan_x", 0.0)), 4),
            "pan_y": round(float(settings.get("view", {}).get("pan_y", 0.0)), 4),
        },
        "image_fit": {
            "fit_mode": str(settings.get("image_fit", {}).get("fit_mode") or "fit_from_image_structured"),
            "frame_hint": settings.get("image_fit", {}).get("frame_hint"),
        },
        "controls": {key: round(float(value), 4) for key, value in settings.get("controls", {}).items()},
        "joints_world": joints,
        "bones": [list(bone) for bone in POSE_BONES],
        "descriptor": describe_pose(settings),
    }
    return payload


def stable_pose_json(settings: Dict[str, Any]) -> str:
    return _sorted_json(pose_payload(settings))
