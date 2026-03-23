import json
import base64
import io
from typing import Any, Dict, Tuple

import numpy as np
import torch
from PIL import Image, ImageDraw

from ..categories import CORE_CHARACTER
from ..lib.pose_image_fit import filter_anchors_by_groups, fit_pose_settings_from_image
from ..lib.pose_studio_shared import (
    POSE_BONES,
    describe_pose,
    normalize_pose_settings,
    pose_payload,
    project_pose_points,
)


def _pil_to_comfy_image(img: Image.Image) -> torch.Tensor:
    arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _image_to_numpy(image: torch.Tensor | None) -> np.ndarray | None:
    if image is None:
        return None
    if not isinstance(image, torch.Tensor):
        raise ValueError(f"Expected IMAGE tensor, got {type(image)!r}")
    if image.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(image.shape)}")
    arr = image.detach().cpu().numpy()
    return np.clip(arr[0], 0.0, 1.0).astype(np.float32)


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        value_i = int(value)
    except Exception:
        value_i = int(default)
    return max(int(lo), min(int(hi), value_i))


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _data_url_to_numpy(data_url: str) -> np.ndarray | None:
    text = _clean_text(data_url)
    if not text or not text.startswith("data:image/") or "," not in text:
        return None
    _, encoded = text.split(",", 1)
    try:
        raw = base64.b64decode(encoded)
        with Image.open(io.BytesIO(raw)) as img:
            return np.array(img.convert("RGB"), dtype=np.float32) / 255.0
    except Exception:
        return None


def _parse_character_name(character_state_json: str) -> str:
    if not _clean_text(character_state_json):
        return ""
    try:
        payload = json.loads(character_state_json)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return _clean_text(payload.get("character_name"))


def _draw_pose_guide(width: int, height: int, payload: Dict[str, Any], character_name: str) -> Image.Image:
    img = Image.new("RGB", (width, height), (10, 16, 23))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        blend = y / max(1, height - 1)
        color = (
            int(10 + blend * 18),
            int(16 + blend * 22),
            int(23 + blend * 26),
        )
        draw.line([(0, y), (width, y)], fill=color)

    draw.rounded_rectangle(
        [(24, 24), (width - 24, height - 24)],
        radius=28,
        outline=(82, 112, 128),
        width=2,
        fill=(15, 23, 31),
    )

    raw_screen = project_pose_points(payload["joints_world"], width, height, payload.get("view", {}))
    xs = [point[0] for point in raw_screen.values()]
    ys = [point[1] for point in raw_screen.values()]
    pose_x0 = min(xs)
    pose_x1 = max(xs)
    pose_y0 = min(ys)
    pose_y1 = max(ys)
    pose_w = max(1.0, pose_x1 - pose_x0)
    pose_h = max(1.0, pose_y1 - pose_y0)
    frame_x0 = 36.0
    frame_y0 = 72.0
    frame_x1 = width - 36.0
    frame_y1 = height - 72.0
    target_w = max(1.0, frame_x1 - frame_x0)
    target_h = max(1.0, frame_y1 - frame_y0)
    frame_hint = payload.get("image_fit", {}).get("frame_hint") if isinstance(payload.get("image_fit"), dict) else None
    if isinstance(frame_hint, dict):
        desired_cx = frame_x0 + target_w * float(frame_hint.get("cx", 0.5))
        desired_cy = frame_y0 + target_h * float(frame_hint.get("cy", 0.5))
        desired_w = max(target_w * 0.2, target_w * min(0.92, max(0.18, float(frame_hint.get("bw", 0.0)))))
        desired_h = max(target_h * 0.28, target_h * min(0.96, max(0.24, float(frame_hint.get("bh", 0.0)))))
        fit_scale = min(desired_w / pose_w, desired_h / pose_h)
        fit_scale = max(0.1, fit_scale)
        offset_x = desired_cx - ((pose_x0 + pose_x1) * 0.5 * fit_scale)
        offset_y = desired_cy - ((pose_y0 + pose_y1) * 0.5 * fit_scale)
    else:
        fit_scale = min((target_w * 0.88) / pose_w, (target_h * 0.94) / pose_h)
        fit_scale = max(0.1, fit_scale)
        offset_x = (frame_x0 + target_w * 0.5) - ((pose_x0 + pose_x1) * 0.5 * fit_scale)
        offset_y = (frame_y0 + target_h * 0.58) - ((pose_y0 + pose_y1) * 0.5 * fit_scale)
    screen = {
        key: (point[0] * fit_scale + offset_x, point[1] * fit_scale + offset_y)
        for key, point in raw_screen.items()
    }
    left_bone = (176, 240, 212)
    right_bone = (120, 188, 255)
    center_bone = (225, 236, 241)

    shadow_offset = (2.0, 3.0)
    for start, end in POSE_BONES:
        p0 = screen[start]
        p1 = screen[end]
        draw.line(
            [(p0[0] + shadow_offset[0], p0[1] + shadow_offset[1]), (p1[0] + shadow_offset[0], p1[1] + shadow_offset[1])],
            fill=(4, 8, 12),
            width=10,
        )
        if start.endswith("_l") or end.endswith("_l"):
            color = left_bone
        elif start.endswith("_r") or end.endswith("_r"):
            color = right_bone
        else:
            color = center_bone
        draw.line([p0, p1], fill=color, width=7)

    for name, point in screen.items():
        if name.endswith("_l"):
            fill = left_bone
        elif name.endswith("_r"):
            fill = right_bone
        else:
            fill = center_bone
        draw.ellipse([(point[0] - 7, point[1] - 7), (point[0] + 7, point[1] + 7)], fill=(8, 12, 16))
        draw.ellipse([(point[0] - 5, point[1] - 5), (point[0] + 5, point[1] + 5)], fill=fill)

    draw.text((42, 38), "MKRSHIFT POSE STUDIO", fill=(214, 249, 118))
    name_line = character_name or "Character pose blockout"
    draw.text((42, 64), name_line, fill=(222, 230, 236))
    descriptor = payload.get("descriptor", "")
    if descriptor:
        draw.text((42, 90), descriptor, fill=(148, 167, 181))

    badge = f"{payload.get('pose_name') or 'Pose'} | yaw {payload.get('view', {}).get('yaw', 0):.0f} | pitch {payload.get('view', {}).get('pitch', 0):.0f}"
    tw = draw.textbbox((0, 0), badge)
    badge_w = tw[2] - tw[0]
    badge_h = tw[3] - tw[1]
    badge_box = (width - badge_w - 56, 36, width - 38, 36 + badge_h + 12)
    draw.rounded_rectangle(badge_box, radius=16, fill=(25, 35, 44), outline=(76, 99, 115))
    draw.text((badge_box[0] + 12, badge_box[1] + 6), badge, fill=(205, 244, 157))

    footer = "Left = mint | Right = blue | Pose JSON stays reusable across future camera / light nodes"
    draw.text((42, height - 58), footer, fill=(140, 157, 171))
    return img


def _reference_image_size(image: torch.Tensor | None) -> tuple[int, int] | None:
    if image is None or not isinstance(image, torch.Tensor) or image.ndim != 4:
        return None
    _, height, width, _ = tuple(image.shape)
    return int(width), int(height)


class MKRPoseStudio:
    SEARCH_ALIASES = [
        "pose studio",
        "3d pose",
        "pose viewport",
        "character pose editor",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
                "pose_name": ("STRING", {"default": ""}),
                "pose_preset": (
                    [
                        "from_settings",
                        "neutral",
                        "heroic",
                        "contrapposto",
                        "run_start",
                        "power_stance",
                        "reach_up",
                        "kneel_pose",
                        "hands_behind_back",
                        "pinup_sway",
                        "crouch_ready",
                    ],
                    {"default": "from_settings"},
                ),
                "mirror_mode": (["from_settings", "off", "left_to_right", "right_to_left"], {"default": "from_settings"}),
                "character_state_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("pose_json", "pose_guide", "pose_prompt", "summary_json")
    FUNCTION = "build"
    CATEGORY = CORE_CHARACTER

    def build(
        self,
        settings_json: str = "{}",
        capture_w: int = 1024,
        capture_h: int = 1024,
        pose_name: str = "",
        pose_preset: str = "from_settings",
        mirror_mode: str = "from_settings",
        character_state_json: str = "",
        pose_reference_image: torch.Tensor | None = None,
        pose_from_image_mode: str = "off",
        pose_image_strength: float = 1.0,
    ) -> Tuple[str, torch.Tensor, str, str]:
        width = _clamp_int(capture_w, 384, 2048, 1024)
        height = _clamp_int(capture_h, 384, 2048, 1024)

        settings = normalize_pose_settings(settings_json, preset_name=pose_preset, mirror_mode=mirror_mode)
        image_fit_settings = settings.get("image_fit") if isinstance(settings.get("image_fit"), dict) else {}
        legacy_mode = str(pose_from_image_mode or "off").strip().lower()
        if legacy_mode in {"fit_from_image", "fit_from_image_structured"}:
            pose_from_image_mode_value = legacy_mode
        else:
            pose_from_image_mode_value = str(image_fit_settings.get("fit_mode") or "off").strip().lower()
        pose_image_strength_value = float(image_fit_settings.get("strength", pose_image_strength))
        reference_np = _data_url_to_numpy(image_fit_settings.get("reference_image_data_url", ""))
        if reference_np is None:
            reference_np = _image_to_numpy(pose_reference_image)
        fit_from_image_enabled = reference_np is not None and pose_from_image_mode_value in {"fit_from_image", "fit_from_image_structured"}
        if fit_from_image_enabled and reference_np is not None:
            height = int(reference_np.shape[0])
            width = int(reference_np.shape[1])

        image_fit_info: Dict[str, Any] = {"applied": False, "reason": "disabled"}
        if fit_from_image_enabled:
            settings, image_fit_info = fit_pose_settings_from_image(
                reference_np,
                settings,
                strength=pose_image_strength_value,
                anchors=filter_anchors_by_groups(
                    image_fit_settings.get("anchors"),
                    image_fit_settings.get("enabled_groups"),
                ),
                mode=pose_from_image_mode_value,
            )
            if image_fit_info.get("applied") and not _clean_text(pose_name):
                settings["pose_name"] = "Image Fit"
            if image_fit_info.get("applied"):
                settings["view"] = {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0}
        if _clean_text(pose_name):
            settings["pose_name"] = _clean_text(pose_name)

        payload = pose_payload(settings)
        descriptor = describe_pose(settings)
        character_name = _parse_character_name(character_state_json)

        pose_prompt = ", ".join(
            part
            for part in [
                "character pose guide",
                settings.get("pose_name", "Pose").strip(),
                descriptor,
                f"view yaw {payload.get('view', {}).get('yaw', 0):.0f}",
            ]
            if _clean_text(part)
        )

        summary = {
            "schema": payload["schema"],
            "schema_version": payload["schema_version"],
            "pose_name": payload["pose_name"],
            "pose_preset": payload["pose_preset"],
            "mirror_mode": payload["mirror_mode"],
            "descriptor": descriptor,
            "character_name": character_name,
            "capture_size": [width, height],
            "joints_world": payload["joints_world"],
            "bone_count": len(payload["bones"]),
            "image_fit": image_fit_info,
        }

        guide = _draw_pose_guide(width, height, payload, character_name)
        return (
            json.dumps(payload, ensure_ascii=False, indent=2),
            _pil_to_comfy_image(guide),
            pose_prompt,
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
