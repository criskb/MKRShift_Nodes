import json
import math
import re
from collections import Counter
from datetime import datetime
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
import torch

from ..categories import STUDIO_BOARDS, STUDIO_DELIVERY, STUDIO_PREP, STUDIO_REVIEW


StudioPalette = Dict[str, Tuple[int, int, int]]

_THEMES: Dict[str, StudioPalette] = {
    "Carbon": {
        "bg": (18, 19, 22),
        "panel": (29, 31, 36),
        "panel_alt": (37, 40, 46),
        "text": (243, 244, 246),
        "muted": (164, 171, 181),
        "accent": (210, 253, 81),
        "line": (76, 82, 92),
    },
    "Paper": {
        "bg": (241, 235, 226),
        "panel": (252, 249, 243),
        "panel_alt": (233, 226, 214),
        "text": (36, 34, 32),
        "muted": (111, 104, 95),
        "accent": (196, 118, 41),
        "line": (189, 178, 162),
    },
    "Signal": {
        "bg": (16, 20, 22),
        "panel": (25, 29, 31),
        "panel_alt": (36, 42, 44),
        "text": (242, 246, 247),
        "muted": (159, 175, 177),
        "accent": (255, 103, 56),
        "line": (74, 86, 89),
    },
    "Blueprint": {
        "bg": (11, 33, 67),
        "panel": (19, 47, 91),
        "panel_alt": (25, 57, 110),
        "text": (237, 246, 255),
        "muted": (164, 191, 222),
        "accent": (122, 214, 255),
        "line": (61, 110, 163),
    },
}

_DELIVERABLES: Dict[str, Dict[str, str]] = {
    "Review": {"folder": "review", "slug": "review", "badge": "IN REVIEW"},
    "Client Selects": {"folder": "client_selects", "slug": "selects", "badge": "CLIENT SELECTS"},
    "Contact Sheet": {"folder": "contact_sheet", "slug": "contact_sheet", "badge": "CONTACT SHEET"},
    "Turnover": {"folder": "turnover", "slug": "turnover", "badge": "TURNOVER"},
    "Social Cut": {"folder": "social_cut", "slug": "social_cut", "badge": "SOCIAL CUT"},
}

_DEPARTMENTS = [
    "General",
    "Lookdev",
    "Animation",
    "Lighting",
    "Comp",
    "Editorial",
    "Design",
]

_NAMING_MODES = [
    "Compact",
    "Editorial",
    "Client Friendly",
]


def _to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")
    t = image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(t.shape)}")
    if t.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(t.shape)}")
    return t.clamp(0.0, 1.0)


def _pil_to_batch(images: Sequence[Image.Image]) -> torch.Tensor:
    if not images:
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
    arr = np.stack([np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0 for img in images], axis=0)
    return torch.from_numpy(arr.astype(np.float32, copy=False))


def _first_pil(image: Optional[torch.Tensor]) -> Optional[Image.Image]:
    if image is None:
        return None
    batch = _to_image_batch(image)
    arr = np.clip(batch[0, ..., :3].cpu().numpy(), 0.0, 1.0)
    return Image.fromarray(np.round(arr * 255.0).astype(np.uint8), mode="RGB")


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    px = max(10, int(size))
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return 0, 0
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return max(0, right - left), max(0, bottom - top)
    except Exception:
        try:
            width, height = draw.textsize(text, font=font)
            return int(width), int(height)
        except Exception:
            return len(text) * 7, 12


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> List[str]:
    raw = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not raw:
        return []

    lines: List[str] = []
    for paragraph in raw:
        current = ""
        for word in paragraph.split():
            candidate = word if not current else f"{current} {word}"
            if _text_size(draw, candidate, font)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
        if current:
            lines.append(current)
        if len(lines) >= max_lines:
            break

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(lines) == max_lines:
        last = lines[-1]
        while last and _text_size(draw, f"{last}...", font)[0] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = f"{last}..." if last else "..."
    return lines


def _fit_font_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    preferred_size: int,
    max_width: int,
    *,
    bold: bool = False,
    min_size: int = 10,
) -> ImageFont.ImageFont:
    size = max(int(min_size), int(preferred_size))
    while size >= int(min_size):
        font = _load_font(size, bold=bold)
        if _text_size(draw, text, font)[0] <= max(1, int(max_width)):
            return font
        size -= 1
    return _load_font(int(min_size), bold=bold)


def _fit_cover(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    target_w, target_h = max(1, int(size[0])), max(1, int(size[1]))
    src = image.convert("RGB")
    sw, sh = src.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (target_w, target_h), (0, 0, 0))
    scale = max(target_w / float(sw), target_h / float(sh))
    resized = src.resize((max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))), resample=Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _fit_contain(image: Image.Image, size: Tuple[int, int], fill: Tuple[int, int, int]) -> Image.Image:
    target_w, target_h = max(1, int(size[0])), max(1, int(size[1]))
    src = image.convert("RGB")
    sw, sh = src.size
    canvas = Image.new("RGB", (target_w, target_h), fill)
    if sw <= 0 or sh <= 0:
        return canvas
    scale = min(target_w / float(sw), target_h / float(sh))
    resized = src.resize(
        (max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))),
        resample=Image.Resampling.LANCZOS,
    )
    left = max(0, (target_w - resized.width) // 2)
    top = max(0, (target_h - resized.height) // 2)
    canvas.paste(resized, (left, top))
    return canvas


def _rounded_mask(
    size: Tuple[int, int],
    radius: int,
    *,
    round_top_left: bool = True,
    round_top_right: bool = True,
    round_bottom_right: bool = True,
    round_bottom_left: bool = True,
) -> Image.Image:
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    corner = max(0, min(int(radius), width // 2, height // 2))
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    if corner <= 0:
        mask_draw.rectangle((0, 0, width, height), fill=255)
        return mask

    mask_draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=corner, fill=255)
    if not round_top_left:
        mask_draw.rectangle((0, 0, corner, corner), fill=255)
    if not round_top_right:
        mask_draw.rectangle((width - corner, 0, width, corner), fill=255)
    if not round_bottom_right:
        mask_draw.rectangle((width - corner, height - corner, width, height), fill=255)
    if not round_bottom_left:
        mask_draw.rectangle((0, height - corner, corner, height), fill=255)
    return mask


def _alpha_composite_clipped(
    base: Image.Image,
    image: Image.Image,
    box: Tuple[int, int, int, int],
    *,
    radius: int = 0,
    round_top_left: bool = True,
    round_top_right: bool = True,
    round_bottom_right: bool = True,
    round_bottom_left: bool = True,
) -> None:
    x0, y0, x1, y1 = [int(value) for value in box]
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    clipped = image.convert("RGBA")
    if clipped.size != (width, height):
        clipped = clipped.resize((width, height), resample=Image.Resampling.LANCZOS)
    if int(radius) > 0:
        mask = _rounded_mask(
            (width, height),
            int(radius),
            round_top_left=round_top_left,
            round_top_right=round_top_right,
            round_bottom_right=round_bottom_right,
            round_bottom_left=round_bottom_left,
        )
        clipped.putalpha(ImageChops.multiply(clipped.getchannel("A"), mask))
    base.alpha_composite(clipped, dest=(x0, y0))


def _ratio_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "0:0"
    frac = Fraction(int(width), int(height)).limit_denominator(32)
    return f"{frac.numerator}:{frac.denominator}"


def _theme(name: str) -> StudioPalette:
    return _THEMES.get(str(name or "Carbon"), _THEMES["Carbon"])


def _slug_token(text: Any, fallback: str = "", max_len: int = 48) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        raw = str(fallback or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        raw = str(fallback or "").strip().lower()
    if max_len > 0:
        raw = raw[: int(max_len)].strip("_")
    return raw or str(fallback or "").strip().lower() or "item"


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or str(fallback or "").strip()


def _json_blob(raw: Any, label: str, warnings: List[str]) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        warnings.append(f"{label} is not valid JSON")
        return {}
    if isinstance(parsed, dict):
        return parsed
    warnings.append(f"{label} must be a JSON object")
    return {}


def _normalize_version_tag(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[vV]?\d+", text):
        digits = int(re.sub(r"[^0-9]", "", text) or "1")
        return f"v{digits:03d}"
    token = _slug_token(text, "v001", max_len=16)
    return token if token.startswith("v") else f"v_{token}"


def _normalize_take_token(value: Any) -> Tuple[str, str]:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+", text):
        number = int(text)
        return f"t{number:02d}", f"{number:02d}"
    token = _slug_token(text, "", max_len=12)
    return (f"t_{token}", text) if token else ("", "")


def _aspect_from_sources(slate_data: Dict[str, Any], review_info: Dict[str, Any], contact_info: Dict[str, Any]) -> str:
    aspect = _clean_text(slate_data.get("aspect", ""))
    if aspect:
        return aspect
    frames = review_info.get("frames", []) if isinstance(review_info.get("frames"), list) else []
    if frames:
        aspect = _clean_text(frames[0].get("ratio", ""))
        if aspect:
            return aspect
    frames = contact_info.get("frames", []) if isinstance(contact_info.get("frames"), list) else []
    if frames:
        aspect = _clean_text(frames[0].get("ratio", ""))
        if aspect:
            return aspect
    return ""


def _manifest_notes_from_delivery_plan(plan_json: Any, warnings: List[str]) -> Dict[str, Any]:
    payload = _json_blob(plan_json, "delivery_plan_json", warnings)
    if not payload:
        return {}
    manifest_notes = payload.get("manifest_notes", {})
    if not isinstance(manifest_notes, dict):
        warnings.append("delivery_plan_json manifest_notes payload is invalid")
        return {}
    return manifest_notes


def _delivery_from_delivery_plan(plan_json: Any, warnings: List[str]) -> Dict[str, Any]:
    manifest_notes = _manifest_notes_from_delivery_plan(plan_json, warnings)
    delivery = manifest_notes.get("delivery", {}) if isinstance(manifest_notes, dict) else {}
    if delivery and not isinstance(delivery, dict):
        warnings.append("delivery_plan_json delivery payload is invalid")
        return {}
    return delivery if isinstance(delivery, dict) else {}


def _labels_from_delivery_plan(plan_json: Any, warnings: List[str]) -> Dict[str, str]:
    manifest_notes = _manifest_notes_from_delivery_plan(plan_json, warnings)
    labels = manifest_notes.get("labels", {}) if isinstance(manifest_notes, dict) else {}
    if not isinstance(labels, dict):
        warnings.append("delivery_plan_json labels payload is invalid")
        return {}
    return {str(key): _clean_text(value) for key, value in labels.items()}


def _resolve_delivery_text(value: Any, placeholder: str, delivery_value: str, hard_default: str = "") -> str:
    text = _clean_text(value, "")
    placeholder_text = _clean_text(placeholder, "")
    if text and text != placeholder_text:
        return text
    if delivery_value:
        return delivery_value
    if text:
        return text
    return _clean_text(hard_default, "")


def _mix_rgb(a: Tuple[int, int, int], b: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    t = float(np.clip(amount, 0.0, 1.0))
    return (
        int(round((a[0] * (1.0 - t)) + (b[0] * t))),
        int(round((a[1] * (1.0 - t)) + (b[1] * t))),
        int(round((a[2] * (1.0 - t)) + (b[2] * t))),
    )


def _selection_mark_map(raw: Any, start_index: int, count: int, warnings: List[str]) -> Dict[int, Dict[str, str]]:
    payload = _json_blob(raw, "selection_json", warnings)
    if not payload:
        return {}

    marks: Dict[int, Dict[str, str]] = {}
    for key, value in payload.items():
        try:
            display_index = int(str(key).strip())
        except Exception:
            warnings.append(f"selection_json key '{key}' is not a frame number")
            continue

        zero_index = int(display_index) - int(start_index)
        if zero_index < 0 or zero_index >= int(count):
            warnings.append(f"selection_json frame {display_index} is outside the displayed range")
            continue

        if isinstance(value, dict):
            status_text = _clean_text(value.get("status", value.get("label", "")), "SELECT")
            note_text = _clean_text(value.get("note", ""), "")
        else:
            status_text = _clean_text(value, "SELECT")
            note_text = ""

        marks[zero_index] = {
            "display_index": str(display_index),
            "status": status_text or "SELECT",
            "note": note_text,
        }
    return marks


def _status_chip_fill(palette: StudioPalette, status: str) -> Tuple[int, int, int]:
    token = _slug_token(status, "", max_len=24)
    if any(part in token for part in ("hero", "select", "approved", "final", "best")):
        return _mix_rgb(palette["accent"], (36, 184, 111), 0.58)
    if any(part in token for part in ("hold", "review", "revise", "wip", "temp")):
        return _mix_rgb(palette["accent"], (245, 166, 35), 0.42)
    if any(part in token for part in ("omit", "reject", "kill", "drop", "out")):
        return _mix_rgb(palette["accent"], (224, 78, 78), 0.56)
    return palette["accent"]


def _render_theme_background(canvas: Image.Image, theme_name: str, palette: StudioPalette) -> None:
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    draw.rectangle((0, 0, w, h), fill=palette["bg"])

    if theme_name == "Blueprint":
        step = max(18, int(min(w, h) * 0.025))
        for x in range(0, w, step):
            draw.line((x, 0, x, h), fill=palette["line"], width=1)
        for y in range(0, h, step):
            draw.line((0, y, w, y), fill=palette["line"], width=1)
    elif theme_name == "Signal":
        for idx in range(10):
            x0 = int((idx / 10.0) * w)
            draw.rectangle((x0, 0, min(w, x0 + max(2, w // 18)), h), fill=(palette["bg"][0], palette["bg"][1] + 1, palette["bg"][2] + 1))
    else:
        glow = Image.new("RGB", (w, h), palette["bg"])
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse(
            (
                int(w * 0.58),
                int(h * -0.08),
                int(w * 1.02),
                int(h * 0.46),
            ),
            fill=palette["panel_alt"],
        )
        glow = glow.filter(ImageFilter.GaussianBlur(radius=max(18, int(min(w, h) * 0.05))))
        canvas.paste(glow, (0, 0))


def _panel_shadow(base: Image.Image, box: Tuple[int, int, int, int], blur_radius: int) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + 10, y0 + 12, x1 + 10, y1 + 12), radius=24, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, blur_radius)))
    base.alpha_composite(shadow)


class MKRStudioSlate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1920, "min": 256, "max": 4096, "step": 16}),
                "height": ("INT", {"default": 1080, "min": 256, "max": 4096, "step": 16}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "project": ("STRING", {"default": "MKRShift Production"}),
                "sequence": ("STRING", {"default": "SEQ_01"}),
                "shot": ("STRING", {"default": "A001"}),
                "take": ("STRING", {"default": "1"}),
                "version_tag": ("STRING", {"default": ""}),
                "department": ("STRING", {"default": ""}),
                "badge": ("STRING", {"default": ""}),
                "director": ("STRING", {"default": ""}),
                "artist": ("STRING", {"default": ""}),
                "camera": ("STRING", {"default": "Virtual Camera"}),
                "lens": ("STRING", {"default": "50mm"}),
                "fps": ("STRING", {"default": "24"}),
                "aspect": ("STRING", {"default": "16:9"}),
                "date_text": ("STRING", {"default": ""}),
                "notes": ("STRING", {"default": ""}),
            },
            "optional": {
                "thumbnail": ("IMAGE",),
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "slate_json", "slate_summary")
    FUNCTION = "build"
    CATEGORY = STUDIO_PREP

    def build(
        self,
        width: int = 1920,
        height: int = 1080,
        theme: str = "Carbon",
        project: str = "MKRShift Production",
        sequence: str = "SEQ_01",
        shot: str = "A001",
        take: str = "1",
        version_tag: str = "",
        department: str = "",
        badge: str = "",
        director: str = "",
        artist: str = "",
        camera: str = "Virtual Camera",
        lens: str = "50mm",
        fps: str = "24",
        aspect: str = "16:9",
        date_text: str = "",
        notes: str = "",
        thumbnail: Optional[torch.Tensor] = None,
        delivery_plan_json: str = "",
    ):
        warnings: List[str] = []
        delivery_info = _delivery_from_delivery_plan(delivery_plan_json, warnings)
        delivery_labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        project_text = _clean_text(project, delivery_info.get("project", "MKRShift Production"))
        sequence_text = _clean_text(sequence, delivery_info.get("sequence", "SEQ_01"))
        shot_text = _clean_text(shot, delivery_info.get("shot", "A001"))
        take_text = _clean_text(take, delivery_info.get("take", "1"))
        version_text = _clean_text(version_tag, delivery_info.get("version_tag", ""))
        department_text = _clean_text(department, delivery_info.get("department", ""))
        badge_text = _clean_text(badge, delivery_labels.get("slate_badge", delivery_labels.get("badge", "")))
        artist_text = _clean_text(artist, delivery_info.get("artist", ""))
        date_value = _clean_text(date_text, delivery_info.get("date_text", ""))
        aspect_text = _clean_text(aspect, delivery_info.get("aspect", "16:9"))
        notes_text = _clean_text(notes, "")
        if not notes_text:
            fallback_notes: List[str] = []
            task_text = _clean_text(delivery_info.get("task", ""))
            round_text = _clean_text(delivery_info.get("round_label", ""))
            reviewer_text = _clean_text(delivery_info.get("reviewer", ""))
            if task_text:
                fallback_notes.append(f"Task: {task_text}")
            if round_text:
                fallback_notes.append(f"Round: {round_text}")
            if reviewer_text:
                fallback_notes.append(f"Reviewer: {reviewer_text}")
            notes_text = " | ".join(fallback_notes)

        w = int(max(256, width))
        h = int(max(256, height))
        palette = _theme(theme)
        base = Image.new("RGBA", (w, h), palette["bg"] + (255,))
        _render_theme_background(base, theme, palette)
        draw = ImageDraw.Draw(base)

        margin = max(28, int(min(w, h) * 0.055))
        accent_h = max(12, int(h * 0.014))
        draw.rectangle((0, 0, w, accent_h), fill=palette["accent"])

        header_font = _load_font(int(h * 0.045), bold=True)
        shot_font = _load_font(int(h * 0.17), bold=True)
        take_font = _load_font(int(h * 0.075), bold=True)
        meta_key_font = _load_font(int(h * 0.02), bold=True)
        meta_val_font = _load_font(int(h * 0.028))
        note_font = _load_font(int(h * 0.026))
        micro_font = _load_font(int(h * 0.017))

        left_w = int(w * 0.46)
        left_box = (margin, margin + accent_h + max(12, margin // 4), margin + left_w, h - margin - int(h * 0.22))
        right_box = (left_box[2] + margin // 2, left_box[1], w - margin, h - margin - int(h * 0.22))
        notes_box = (margin, h - margin - int(h * 0.18), w - margin, h - margin)

        _panel_shadow(base, left_box, blur_radius=max(8, margin // 2))
        _panel_shadow(base, right_box, blur_radius=max(8, margin // 2))
        _panel_shadow(base, notes_box, blur_radius=max(6, margin // 3))

        draw.rounded_rectangle(left_box, radius=26, fill=palette["panel"])
        draw.rounded_rectangle(right_box, radius=26, fill=palette["panel"])
        draw.rounded_rectangle(notes_box, radius=22, fill=palette["panel_alt"])

        left_x = left_box[0] + margin // 2
        left_y = left_box[1] + margin // 2
        project_text_upper = str(project_text or "Untitled Project").upper()
        project_font = _fit_font_to_width(
            draw,
            project_text_upper,
            int(h * 0.045),
            left_box[2] - left_x - max(12, margin // 2),
            bold=True,
            min_size=max(12, int(h * 0.026)),
        )
        sequence_font = _fit_font_to_width(
            draw,
            f"Sequence {sequence_text or '-'}",
            int(h * 0.028),
            left_box[2] - left_x - max(12, margin // 2),
            min_size=max(10, int(h * 0.02)),
        )
        draw.text((left_x, left_y), project_text_upper, font=project_font, fill=palette["text"])
        draw.text((left_x, left_y + int(h * 0.065)), f"Sequence {sequence_text or '-'}", font=sequence_font, fill=palette["muted"])

        shot_y = left_y + int(h * 0.13)
        draw.text((left_x, shot_y), str(shot_text or "A001"), font=shot_font, fill=palette["accent"])
        take_w, take_h = _text_size(draw, f"TAKE {take_text or '1'}", take_font)
        take_box = (
            left_x,
            shot_y + int(h * 0.19),
            left_x + take_w + margin // 2,
            shot_y + int(h * 0.19) + take_h + margin // 3,
        )
        draw.rounded_rectangle(take_box, radius=16, fill=palette["panel_alt"])
        draw.text((take_box[0] + margin // 5, take_box[1] + margin // 8), f"TAKE {take_text or '1'}", font=take_font, fill=palette["text"])

        if version_text:
            version_w, version_h = _text_size(draw, version_text.upper(), badge_font := _load_font(int(h * 0.034), bold=True))
            version_box = (
                take_box[2] + max(12, margin // 4),
                take_box[1] + max(2, margin // 12),
                take_box[2] + max(12, margin // 4) + version_w + max(18, margin // 3),
                take_box[1] + max(2, margin // 12) + version_h + max(12, margin // 5),
            )
            draw.rounded_rectangle(version_box, radius=16, fill=palette["panel_alt"])
            draw.text((version_box[0] + max(8, margin // 6), version_box[1] + max(4, margin // 12)), version_text.upper(), font=badge_font, fill=palette["accent"])
            if badge_text:
                badge_w, badge_h = _text_size(draw, badge_text.upper(), badge_font)
                badge_box = (
                    version_box[0],
                    version_box[3] + max(10, margin // 6),
                    version_box[0] + badge_w + max(18, margin // 3),
                    version_box[3] + max(10, margin // 6) + badge_h + max(12, margin // 5),
                )
                draw.rounded_rectangle(badge_box, radius=16, fill=palette["panel_alt"])
                draw.text((badge_box[0] + max(8, margin // 6), badge_box[1] + max(4, margin // 12)), badge_text.upper(), font=badge_font, fill=palette["text"])
        elif badge_text:
            badge_font = _load_font(int(h * 0.034), bold=True)
            badge_w, badge_h = _text_size(draw, badge_text.upper(), badge_font)
            badge_box = (
                take_box[2] + max(12, margin // 4),
                take_box[1] + max(2, margin // 12),
                take_box[2] + max(12, margin // 4) + badge_w + max(18, margin // 3),
                take_box[1] + max(2, margin // 12) + badge_h + max(12, margin // 5),
            )
            draw.rounded_rectangle(badge_box, radius=16, fill=palette["panel_alt"])
            draw.text((badge_box[0] + max(8, margin // 6), badge_box[1] + max(4, margin // 12)), badge_text.upper(), font=badge_font, fill=palette["text"])

        stamp = f"{camera or 'Camera'}  |  {lens or 'Lens'}  |  {fps or '24'} FPS  |  {aspect_text or '16:9'}"
        stamp_font = _fit_font_to_width(
            draw,
            stamp,
            int(h * 0.028),
            left_box[2] - left_x - max(12, margin // 2),
            min_size=max(10, int(h * 0.018)),
        )
        draw.text((left_x, left_box[3] - margin), stamp, font=stamp_font, fill=palette["muted"])

        thumb = _first_pil(thumbnail)
        right_inner_x = right_box[0] + margin // 2
        right_inner_y = right_box[1] + margin // 2
        right_inner_w = right_box[2] - right_box[0] - margin

        metadata_rows = [
            ("Department", department_text or "-"),
            ("Version", version_text or "-"),
            ("Director", director or "-"),
            ("Artist", artist_text or "-"),
            ("Date", date_value or "-"),
            ("Aspect", aspect_text or _ratio_label(w, h)),
            ("FPS", fps or "24"),
            ("Lens", lens or "-"),
        ]
        panel_h = right_box[3] - right_box[1]
        inner_pad = max(10, margin // 2)
        meta_key_size = max(10, int(h * 0.02))
        meta_val_size = max(10, int(h * 0.028))
        metadata_gap = max(6, margin // 5)
        thumb_default_h = int(panel_h * 0.34) if thumb is not None else 0
        thumb_gap = margin // 2 if thumb is not None else 0
        metadata_row_step = 0
        thumbnail_height = 0
        thumbnail_visible = bool(thumb is not None)

        while True:
            meta_key_font = _load_font(meta_key_size, bold=True)
            meta_val_font = _load_font(meta_val_size)
            key_height = max(_text_size(draw, key, meta_key_font)[1] for key, _ in metadata_rows)
            value_height = max(_text_size(draw, str(value), meta_val_font)[1] for _, value in metadata_rows)
            metadata_row_step = max(key_height, value_height) + metadata_gap
            metadata_needed_h = metadata_row_step * len(metadata_rows)
            available_for_thumb = panel_h - (inner_pad * 2) - metadata_needed_h - thumb_gap
            thumbnail_height = min(thumb_default_h, max(0, available_for_thumb))
            if thumb is None:
                thumbnail_visible = False
                thumbnail_height = 0
                break
            if thumbnail_height >= max(32, int(panel_h * 0.16)):
                break
            if meta_key_size <= 10 and meta_val_size <= 10:
                thumbnail_visible = False
                thumbnail_height = 0
                warnings.append("thumbnail hidden to keep metadata inside the right panel")
                break
            meta_key_size = max(10, meta_key_size - 1)
            meta_val_size = max(10, meta_val_size - 1)

        thumb_box: Optional[Tuple[int, int, int, int]] = None
        if thumb is not None and bool(thumbnail_visible) and int(thumbnail_height) > 0:
            thumb_h = int(thumbnail_height)
            thumb_box = (right_inner_x, right_inner_y, right_inner_x + right_inner_w, right_inner_y + thumb_h)
            thumb_fit = _fit_cover(thumb, (thumb_box[2] - thumb_box[0], thumb_box[3] - thumb_box[1]))
            _alpha_composite_clipped(base, thumb_fit, thumb_box, radius=20)
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(thumb_box, radius=20, outline=palette["line"] + (255,), width=2)
            base.alpha_composite(overlay)
            right_inner_y = thumb_box[3] + margin // 2

        row_y = right_inner_y
        value_x = right_inner_x + int(right_inner_w * 0.37)
        metadata_bottom = row_y
        for key, value in metadata_rows:
            draw.text((right_inner_x, row_y), key.upper(), font=meta_key_font, fill=palette["muted"])
            value_text = str(value)
            value_font = _fit_font_to_width(
                draw,
                value_text,
                meta_val_size,
                right_box[2] - value_x - max(8, margin // 3),
                min_size=10,
            )
            draw.text((value_x, row_y - 2), value_text, font=value_font, fill=palette["text"])
            line_y = min(right_box[3] - inner_pad, row_y + metadata_row_step - max(2, metadata_gap // 2))
            draw.line(
                (
                    right_inner_x,
                    line_y,
                    right_box[2] - margin // 2,
                    line_y,
                ),
                fill=palette["line"],
                width=1,
            )
            row_y += metadata_row_step
            metadata_bottom = line_y

        notes_lines = _wrap_text(draw, notes_text or "No notes.", note_font, notes_box[2] - notes_box[0] - margin, 3)
        draw.text((notes_box[0] + margin // 2, notes_box[1] + margin // 3), "NOTES", font=meta_key_font, fill=palette["muted"])
        line_y = notes_box[1] + margin
        for line in notes_lines:
            draw.text((notes_box[0] + margin // 2, line_y), line, font=note_font, fill=palette["text"])
            line_y += int(h * 0.035)

        draw.text(
            (w - margin - _text_size(draw, "MKRSHIFT STUDIO SLATE", micro_font)[0], h - margin + margin // 6),
            "MKRSHIFT STUDIO SLATE",
            font=micro_font,
            fill=palette["muted"],
        )

        metadata = {
            "project": str(project_text or ""),
            "sequence": str(sequence_text or ""),
            "shot": str(shot_text or ""),
            "take": str(take_text or ""),
            "version_tag": version_text,
            "department": str(department_text or ""),
            "badge": badge_text,
            "director": str(director or ""),
            "artist": str(artist_text or ""),
            "camera": str(camera or ""),
            "lens": str(lens or ""),
            "fps": str(fps or ""),
            "aspect": str(aspect_text or ""),
            "date_text": str(date_value or ""),
            "notes": str(notes_text or ""),
            "theme": str(theme or "Carbon"),
            "size": [w, h],
            "has_thumbnail": bool(thumb is not None and bool(thumbnail_visible) and int(thumbnail_height) > 0),
            "layout": {
                "right_box": list(right_box),
                "right_inner_padding": inner_pad,
                "thumbnail_height": int(thumbnail_height) if thumb is not None else 0,
                "metadata_row_step": int(metadata_row_step),
                "metadata_bottom": int(metadata_bottom),
                "thumbnail_box": list(thumb_box) if thumb_box is not None else [],
            },
            "warnings": warnings,
        }
        summary_bits = [f"Studio slate {shot_text or 'A001'}", f"take {take_text or '1'}"]
        if version_text:
            summary_bits.append(version_text)
        if department_text:
            summary_bits.append(str(department_text))
        summary_bits.extend([f"{w}x{h}", str(theme)])
        summary = " | ".join(summary_bits)
        return (_pil_to_batch([base.convert("RGB")]), json.dumps(metadata, ensure_ascii=False), summary)


class MKRStudioReviewFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "title": ("STRING", {"default": "Client Review"}),
                "subtitle": ("STRING", {"default": "Lookdev pass"}),
                "badge": ("STRING", {"default": "IN REVIEW"}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "version_tag": ("STRING", {"default": "v001"}),
                "footer_left": ("STRING", {"default": "MKRShift Nodes"}),
                "footer_right": ("STRING", {"default": ""}),
                "margin_px": ("INT", {"default": 72, "min": 12, "max": 256, "step": 2}),
                "header_px": ("INT", {"default": 120, "min": 36, "max": 320, "step": 2}),
                "footer_px": ("INT", {"default": 72, "min": 24, "max": 200, "step": 2}),
                "show_safe_area": ("BOOLEAN", {"default": True}),
                "show_frame_index": ("BOOLEAN", {"default": True}),
                "shadow_strength": ("FLOAT", {"default": 0.28, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "review_frame_info")
    FUNCTION = "frame"
    CATEGORY = STUDIO_REVIEW

    def frame(
        self,
        image: torch.Tensor,
        title: str = "Client Review",
        subtitle: str = "Lookdev pass",
        badge: str = "IN REVIEW",
        theme: str = "Carbon",
        version_tag: str = "v001",
        footer_left: str = "MKRShift Nodes",
        footer_right: str = "",
        margin_px: int = 72,
        header_px: int = 120,
        footer_px: int = 72,
        show_safe_area: bool = True,
        show_frame_index: bool = True,
        shadow_strength: float = 0.28,
        delivery_plan_json: str = "",
    ):
        batch = _to_image_batch(image)
        palette = _theme(theme)
        warnings: List[str] = []
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        title_text = _resolve_delivery_text(title, "Client Review", labels.get("review_title", ""), "Client Review")
        subtitle_text = _resolve_delivery_text(subtitle, "Lookdev pass", labels.get("review_subtitle", ""), "")
        badge_text = _resolve_delivery_text(badge, "IN REVIEW", labels.get("badge", ""), "IN REVIEW")
        version_text = str(version_tag or "")
        footer_left_text = _resolve_delivery_text(footer_left, "MKRShift Nodes", labels.get("footer_left", ""), "MKRShift Nodes")
        framed: List[Image.Image] = []
        layout_rows: List[Dict[str, Any]] = []

        for idx in range(int(batch.shape[0])):
            src = Image.fromarray(np.round(batch[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            src_w, src_h = src.size
            margin = int(max(12, margin_px))
            header_h = int(max(36, header_px))
            footer_h = int(max(24, footer_px))
            out_w = src_w + (margin * 2)
            out_h = src_h + header_h + footer_h + (margin * 2)

            base = Image.new("RGBA", (out_w, out_h), palette["bg"] + (255,))
            _render_theme_background(base, theme, palette)
            draw = ImageDraw.Draw(base)

            header_font = _load_font(int(header_h * 0.28), bold=True)
            subtitle_font = _load_font(int(header_h * 0.18))
            badge_font = _load_font(int(header_h * 0.16), bold=True)
            footer_font = _load_font(int(footer_h * 0.24))
            micro_font = _load_font(int(footer_h * 0.2), bold=True)

            image_box = (margin, margin + header_h, out_w - margin, out_h - margin - footer_h)
            shadow_alpha = int(180 * float(np.clip(shadow_strength, 0.0, 1.0)))
            shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle(
                (
                    image_box[0] + 12,
                    image_box[1] + 16,
                    image_box[2] + 12,
                    image_box[3] + 16,
                ),
                radius=26,
                fill=(0, 0, 0, shadow_alpha),
            )
            base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius=max(8, margin // 3))))

            draw.rounded_rectangle(image_box, radius=24, fill=palette["panel"], outline=palette["line"], width=2)
            _alpha_composite_clipped(base, src, image_box, radius=24)
            draw.rounded_rectangle(image_box, radius=24, outline=palette["line"], width=2)

            draw.rectangle((0, 0, out_w, max(10, margin // 5)), fill=palette["accent"])
            draw.text((margin, margin + max(0, header_h // 10)), title_text, font=header_font, fill=palette["text"])
            draw.text((margin, margin + int(header_h * 0.48)), subtitle_text, font=subtitle_font, fill=palette["muted"])

            if badge_text:
                badge_w, badge_h = _text_size(draw, badge_text, badge_font)
                badge_box = (
                    out_w - margin - badge_w - margin // 2,
                    margin + max(0, header_h // 12),
                    out_w - margin,
                    margin + max(0, header_h // 12) + badge_h + margin // 3,
                )
                draw.rounded_rectangle(badge_box, radius=16, fill=palette["panel_alt"])
                draw.text((badge_box[0] + margin // 4, badge_box[1] + margin // 10), badge_text, font=badge_font, fill=palette["accent"])

            if show_safe_area:
                inset_a = int(min(src_w, src_h) * 0.05)
                inset_b = int(min(src_w, src_h) * 0.1)
                for inset, color in ((inset_a, palette["line"]), (inset_b, palette["muted"])):
                    guide = (
                        image_box[0] + inset,
                        image_box[1] + inset,
                        image_box[2] - inset,
                        image_box[3] - inset,
                    )
                    draw.rectangle(guide, outline=color, width=1)

            ratio = _ratio_label(src_w, src_h)
            fallback_right = f"{src_w}x{src_h} | {ratio} | {version_text}" if version_text else f"{src_w}x{src_h} | {ratio}"
            right_footer_base = _clean_text(footer_right, labels.get("footer_right", "")) or fallback_right
            draw.text((margin, out_h - margin - int(footer_h * 0.58)), footer_left_text, font=footer_font, fill=palette["muted"])

            right_parts = [right_footer_base] if right_footer_base else []
            if bool(show_frame_index):
                right_parts.append(f"FRAME {idx + 1:02d}")
            right_footer = " | ".join(part for part in right_parts if part)
            right_w, _ = _text_size(draw, right_footer, footer_font)
            draw.text((out_w - margin - right_w, out_h - margin - int(footer_h * 0.58)), right_footer, font=footer_font, fill=palette["muted"])
            if bool(show_frame_index):
                draw.text((margin, out_h - margin - int(footer_h * 0.22)), f"FRAME {idx + 1:02d}", font=micro_font, fill=palette["accent"])

            framed.append(base.convert("RGB"))
            layout_rows.append(
                {
                    "index": idx + 1,
                    "input_size": [src_w, src_h],
                    "output_size": [out_w, out_h],
                    "ratio": ratio,
                    "theme": theme,
                    "title": title_text,
                    "subtitle": subtitle_text,
                    "badge": badge_text,
                    "footer_left": footer_left_text,
                    "footer_right": right_footer_base,
                    "version_tag": version_text,
                }
            )

        info = {
            "theme": theme,
            "count": len(layout_rows),
            "show_safe_area": bool(show_safe_area),
            "show_frame_index": bool(show_frame_index),
            "labels": {
                "title": title_text,
                "subtitle": subtitle_text,
                "badge": badge_text,
                "footer_left": footer_left_text,
                "footer_right": _clean_text(footer_right, labels.get("footer_right", "")),
            },
            "frames": layout_rows,
            "warnings": warnings,
        }
        return (_pil_to_batch(framed), json.dumps(info, ensure_ascii=False))


class MKRStudioContactSheet:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "title": ("STRING", {"default": "Daily Selects"}),
                "subtitle": ("STRING", {"default": "Batch review board"}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "badge": ("STRING", {"default": "CONTACT SHEET"}),
                "columns": ("INT", {"default": 4, "min": 1, "max": 8, "step": 1}),
                "cell_width": ("INT", {"default": 360, "min": 80, "max": 2048, "step": 8}),
                "gap_px": ("INT", {"default": 24, "min": 0, "max": 128, "step": 2}),
                "margin_px": ("INT", {"default": 40, "min": 8, "max": 256, "step": 2}),
                "header_px": ("INT", {"default": 112, "min": 48, "max": 320, "step": 2}),
                "footer_px": ("INT", {"default": 56, "min": 24, "max": 160, "step": 2}),
                "label_prefix": ("STRING", {"default": "SHOT"}),
                "start_index": ("INT", {"default": 1, "min": 0, "max": 9999, "step": 1}),
                "show_ratio": ("BOOLEAN", {"default": True}),
                "show_resolution": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
                "selection_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "contact_sheet_info")
    FUNCTION = "board"
    CATEGORY = STUDIO_BOARDS

    def board(
        self,
        images: torch.Tensor,
        title: str = "Daily Selects",
        subtitle: str = "Batch review board",
        theme: str = "Carbon",
        badge: str = "CONTACT SHEET",
        columns: int = 4,
        cell_width: int = 360,
        gap_px: int = 24,
        margin_px: int = 40,
        header_px: int = 112,
        footer_px: int = 56,
        label_prefix: str = "SHOT",
        start_index: int = 1,
        show_ratio: bool = True,
        show_resolution: bool = True,
        delivery_plan_json: str = "",
        selection_json: str = "",
    ):
        batch = _to_image_batch(images)
        count = int(batch.shape[0])
        src_h = int(batch.shape[1])
        src_w = int(batch.shape[2])
        warnings: List[str] = []
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        title_text = _resolve_delivery_text(title, "Daily Selects", labels.get("contact_title", ""), "Daily Selects")
        subtitle_text = _resolve_delivery_text(subtitle, "Batch review board", labels.get("contact_subtitle", ""), "")
        badge_text = _resolve_delivery_text(badge, "CONTACT SHEET", labels.get("badge", ""), "CONTACT SHEET")
        label_prefix_text = _resolve_delivery_text(label_prefix, "SHOT", labels.get("contact_label_prefix", ""), "SHOT")
        selection_marks = _selection_mark_map(selection_json, start_index=int(start_index), count=int(count), warnings=warnings)

        cols = max(1, min(int(columns), count or 1))
        rows = max(1, int(math.ceil(float(count) / float(cols))))
        margin = max(8, int(margin_px))
        gap = max(0, int(gap_px))
        header_h = max(48, int(header_px))
        footer_h_requested = max(24, int(footer_px))
        cell_w = max(80, int(cell_width))
        cell_h = max(60, int(round((float(src_h) / float(max(1, src_w))) * cell_w)))
        label_h = max(44, int(cell_w * 0.22))
        card_h = cell_h + label_h
        palette = _theme(theme)

        board_w = (margin * 2) + (cols * cell_w) + (max(0, cols - 1) * gap)
        selection_status_counts = Counter(_clean_text(mark.get("status", ""), "SELECT").upper() for mark in selection_marks.values())
        footer_left = f"{count} frames | {rows} rows x {cols} columns | card {cell_w}x{card_h}"
        if selection_marks:
            footer_left += f" | {len(selection_marks)} marked"
        if selection_status_counts:
            footer_left += " | " + " | ".join(
                f"{status} {status_count}"
                for status, status_count in sorted(selection_status_counts.items())
            )
        footer_right = f"{theme} review board"

        footer_measure = ImageDraw.Draw(Image.new("RGBA", (max(1, board_w), max(8, footer_h_requested * 3)), palette["bg"] + (255,)))
        footer_font_size = max(12, int(footer_h_requested * 0.3))
        footer_min_size = max(10, int(footer_h_requested * 0.2))
        footer_gap = max(18, margin // 2)
        footer_span = max(1, board_w - (margin * 2))
        footer_layout = "single_line"
        while footer_font_size >= footer_min_size:
            footer_font = _load_font(footer_font_size)
            left_w, _ = _text_size(footer_measure, footer_left, footer_font)
            right_w, _ = _text_size(footer_measure, footer_right, footer_font)
            if left_w + footer_gap + right_w <= footer_span:
                break
            footer_font_size -= 1

        footer_font = _load_font(max(footer_min_size, footer_font_size))
        left_w, left_h = _text_size(footer_measure, footer_left, footer_font)
        right_w, right_h = _text_size(footer_measure, footer_right, footer_font)
        if left_w + footer_gap + right_w > footer_span:
            footer_layout = "stacked"
            footer_left_font = _fit_font_to_width(
                footer_measure,
                footer_left,
                max(footer_min_size, footer_font_size),
                footer_span,
                min_size=footer_min_size,
            )
            footer_right_font = _fit_font_to_width(
                footer_measure,
                footer_right,
                max(footer_min_size, footer_font_size),
                footer_span,
                min_size=footer_min_size,
            )
            left_w, left_h = _text_size(footer_measure, footer_left, footer_left_font)
            right_w, right_h = _text_size(footer_measure, footer_right, footer_right_font)
            footer_h = max(footer_h_requested, left_h + right_h + max(10, footer_h_requested // 4) + max(10, margin // 6))
        else:
            footer_left_font = footer_font
            footer_right_font = footer_font
            footer_h = footer_h_requested

        board_h = (margin * 2) + header_h + footer_h + (rows * card_h) + (max(0, rows - 1) * gap)

        base = Image.new("RGBA", (board_w, board_h), palette["bg"] + (255,))
        _render_theme_background(base, theme, palette)
        draw = ImageDraw.Draw(base)

        badge_font = _fit_font_to_width(
            draw,
            badge_text,
            int(header_h * 0.15),
            max(90, int(board_w * 0.32)),
            bold=True,
            min_size=max(10, int(header_h * 0.1)),
        )
        badge_reserved_w = 0
        if badge_text:
            badge_w, _ = _text_size(draw, badge_text, badge_font)
            badge_reserved_w = badge_w + margin
        title_font = _fit_font_to_width(
            draw,
            title_text,
            int(header_h * 0.28),
            board_w - (margin * 2) - badge_reserved_w,
            bold=True,
            min_size=max(16, int(header_h * 0.18)),
        )
        subtitle_font = _fit_font_to_width(
            draw,
            subtitle_text,
            int(header_h * 0.17),
            board_w - (margin * 2),
            min_size=max(10, int(header_h * 0.11)),
        )
        label_font_size = max(16, int(label_h * 0.28))
        meta_font_size = max(12, int(label_h * 0.19))

        draw.rectangle((0, 0, board_w, max(10, margin // 5)), fill=palette["accent"])
        draw.text((margin, margin), title_text, font=title_font, fill=palette["text"])
        draw.text((margin, margin + int(header_h * 0.42)), subtitle_text, font=subtitle_font, fill=palette["muted"])

        if badge_text:
            badge_w, badge_h = _text_size(draw, badge_text, badge_font)
            badge_box = (
                board_w - margin - badge_w - margin // 2,
                margin,
                board_w - margin,
                margin + badge_h + margin // 3,
            )
            draw.rounded_rectangle(badge_box, radius=16, fill=palette["panel_alt"])
            draw.text((badge_box[0] + margin // 4, badge_box[1] + margin // 10), badge_text, font=badge_font, fill=palette["accent"])

        frames: List[Dict[str, Any]] = []
        ratio_text = _ratio_label(src_w, src_h)

        for idx in range(count):
            row = idx // cols
            col = idx % cols
            card_x = margin + (col * (cell_w + gap))
            card_y = margin + header_h + (row * (card_h + gap))
            card_box = (card_x, card_y, card_x + cell_w, card_y + card_h)
            thumb_box = (card_x, card_y, card_x + cell_w, card_y + cell_h)
            label_y = card_y + cell_h
            label_box = (card_x, label_y, card_x + cell_w, card_y + card_h)

            _panel_shadow(base, card_box, blur_radius=max(6, margin // 3))
            draw.rounded_rectangle(card_box, radius=22, fill=palette["panel"])
            _alpha_composite_clipped(
                base,
                Image.new("RGBA", (cell_w, max(1, card_h - cell_h)), palette["panel_alt"] + (255,)),
                label_box,
                radius=22,
                round_top_left=False,
                round_top_right=False,
            )

            src = Image.fromarray(np.round(batch[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            thumb = _fit_cover(src, (cell_w, cell_h)).convert("RGBA")
            _alpha_composite_clipped(
                base,
                thumb,
                thumb_box,
                radius=22,
                round_bottom_right=False,
                round_bottom_left=False,
            )
            draw.rounded_rectangle(card_box, radius=22, outline=palette["line"], width=2)
            draw.line((card_x, label_y, card_x + cell_w, label_y), fill=palette["line"], width=2)

            label = f"{label_prefix_text or 'SHOT'} {start_index + idx:02d}"
            mark = selection_marks.get(idx)
            detail_parts: List[str] = []
            if show_resolution:
                detail_parts.append(f"{src_w}x{src_h}")
            if show_ratio:
                detail_parts.append(ratio_text)
            if mark and mark.get("note"):
                note_text = _clean_text(mark.get("note", ""), "")
                if len(note_text) > 30:
                    note_text = note_text[:27].rstrip() + "..."
                detail_parts.append(note_text)
            detail = " | ".join(detail_parts)

            label_x = card_x + max(12, cell_w // 18)
            label_baseline = label_y + max(8, label_h // 8)
            index_text = f"{idx + 1}/{count}"
            index_font = _fit_font_to_width(
                draw,
                index_text,
                meta_font_size,
                max(28, int(cell_w * 0.22)),
                min_size=10,
            )
            index_w, _ = _text_size(draw, index_text, index_font)
            label_font = _fit_font_to_width(
                draw,
                label,
                label_font_size,
                max(40, cell_w - (label_x - card_x) - index_w - max(16, cell_w // 14)),
                bold=True,
                min_size=12,
            )
            draw.text((label_x, label_baseline), label, font=label_font, fill=palette["text"])
            if detail:
                detail_font = _fit_font_to_width(
                    draw,
                    detail,
                    meta_font_size,
                    max(40, cell_w - (label_x - card_x) - max(12, cell_w // 18)),
                    min_size=10,
                )
                draw.text((label_x, label_baseline + max(18, label_h // 3)), detail, font=detail_font, fill=palette["muted"])

            draw.text((card_x + cell_w - index_w - max(12, cell_w // 18), label_baseline), index_text, font=index_font, fill=palette["accent"])

            if mark:
                chip_text = _clean_text(mark.get("status", ""), "SELECT").upper()
                chip_fill = _status_chip_fill(palette, chip_text)
                chip_font = _fit_font_to_width(
                    draw,
                    chip_text,
                    meta_font_size,
                    max(48, int(cell_w * 0.34)),
                    min_size=10,
                )
                chip_w, chip_h = _text_size(draw, chip_text, chip_font)
                chip_box = (
                    card_x + cell_w - chip_w - max(22, cell_w // 7),
                    card_y + max(10, cell_w // 18),
                    card_x + cell_w - max(10, cell_w // 18),
                    card_y + max(10, cell_w // 18) + chip_h + max(10, cell_w // 16),
                )
                draw.rounded_rectangle(chip_box, radius=12, fill=chip_fill)
                draw.text((chip_box[0] + max(8, cell_w // 24), chip_box[1] + max(4, cell_w // 28)), chip_text, font=chip_font, fill=palette["bg"])
                draw.rounded_rectangle(card_box, radius=22, outline=chip_fill, width=3)
            frames.append(
                {
                    "index": idx + 1,
                    "display_index": start_index + idx,
                    "row": row + 1,
                    "column": col + 1,
                    "label": label,
                    "input_size": [src_w, src_h],
                    "card_size": [cell_w, card_h],
                    "ratio": ratio_text,
                    "selection": mark or {},
                }
            )

        footer_top = board_h - margin - footer_h
        footer_text_y = footer_top + max(8, footer_h // 6)
        if footer_layout == "stacked":
            draw.text((margin, footer_text_y), footer_left, font=footer_left_font, fill=palette["muted"])
            right_footer_w, _ = _text_size(draw, footer_right, footer_right_font)
            draw.text(
                (board_w - margin - right_footer_w, footer_text_y + left_h + max(8, footer_h // 8)),
                footer_right,
                font=footer_right_font,
                fill=palette["muted"],
            )
        else:
            footer_y = board_h - margin - max(16, footer_h // 2)
            draw.text((margin, footer_y), footer_left, font=footer_left_font, fill=palette["muted"])
            footer_right_w, _ = _text_size(draw, footer_right, footer_right_font)
            draw.text((board_w - margin - footer_right_w, footer_y), footer_right, font=footer_right_font, fill=palette["muted"])

        info = {
            "theme": theme,
            "title": title_text,
            "subtitle": subtitle_text,
            "badge": badge_text,
            "count": count,
            "rows": rows,
            "columns": cols,
            "cell_size": [cell_w, cell_h],
            "card_size": [cell_w, card_h],
            "board_size": [board_w, board_h],
            "footer_height": footer_h,
            "footer_layout": footer_layout,
            "show_ratio": bool(show_ratio),
            "show_resolution": bool(show_resolution),
            "selection_count": len(selection_marks),
            "selection_status_counts": dict(sorted(selection_status_counts.items())),
            "selection_frames_csv": ",".join(str(start_index + idx) for idx in sorted(selection_marks.keys())),
            "selection_labels": {str(start_index + idx): mark.get("status", "") for idx, mark in selection_marks.items()},
            "frames": frames,
            "warnings": warnings,
        }
        return (_pil_to_batch([base.convert("RGB")]), json.dumps(info, ensure_ascii=False))


class MKRStudioDeliveryPlan:
    SEARCH_ALIASES = ["studio handoff", "delivery naming", "review package", "filename builder"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("STRING", {"default": "MKRShift Production"}),
                "sequence": ("STRING", {"default": "SEQ_01"}),
                "shot": ("STRING", {"default": "A001"}),
                "take": ("STRING", {"default": "1"}),
                "version_tag": ("STRING", {"default": "v001"}),
                "deliverable": (list(_DELIVERABLES.keys()), {"default": "Review"}),
                "department": (_DEPARTMENTS, {"default": "Lookdev"}),
                "artist": ("STRING", {"default": ""}),
                "client": ("STRING", {"default": ""}),
                "task": ("STRING", {"default": ""}),
                "round_label": ("STRING", {"default": ""}),
                "reviewer": ("STRING", {"default": ""}),
                "custom_badge": ("STRING", {"default": ""}),
                "date_text": ("STRING", {"default": ""}),
                "naming_mode": (_NAMING_MODES, {"default": "Editorial"}),
                "extension": ("STRING", {"default": "png"}),
                "include_take": ("BOOLEAN", {"default": True}),
                "include_date": ("BOOLEAN", {"default": True}),
                "include_artist": ("BOOLEAN", {"default": False}),
                "include_client": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "slate_json": ("STRING", {"default": "", "multiline": True}),
                "review_frame_info": ("STRING", {"default": "", "multiline": True}),
                "contact_sheet_info": ("STRING", {"default": "", "multiline": True}),
                "selection_manifest_json": ("STRING", {"default": "", "multiline": True}),
                "notes_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("filename_prefix", "subfolder", "review_title", "manifest_notes_json", "delivery_plan_json")
    FUNCTION = "plan"
    CATEGORY = STUDIO_DELIVERY

    def plan(
        self,
        project: str = "MKRShift Production",
        sequence: str = "SEQ_01",
        shot: str = "A001",
        take: str = "1",
        version_tag: str = "v001",
        deliverable: str = "Review",
        department: str = "Lookdev",
        artist: str = "",
        client: str = "",
        task: str = "",
        round_label: str = "",
        reviewer: str = "",
        custom_badge: str = "",
        date_text: str = "",
        naming_mode: str = "Editorial",
        extension: str = "png",
        include_take: bool = True,
        include_date: bool = True,
        include_artist: bool = False,
        include_client: bool = False,
        slate_json: str = "",
        review_frame_info: str = "",
        contact_sheet_info: str = "",
        selection_manifest_json: str = "",
        notes_json: str = "{}",
    ):
        warnings: List[str] = []
        slate_data = _json_blob(slate_json, "slate_json", warnings)
        review_info = _json_blob(review_frame_info, "review_frame_info", warnings)
        contact_info = _json_blob(contact_sheet_info, "contact_sheet_info", warnings)
        selection_manifest = _json_blob(selection_manifest_json, "selection_manifest_json", warnings)
        notes_data: Any
        try:
            notes_data = json.loads(str(notes_json or "{}"))
        except Exception:
            notes_data = str(notes_json or "")
            warnings.append("notes_json is not valid JSON")

        project_text = _clean_text(project, slate_data.get("project", "MKRShift Production"))
        sequence_text = _clean_text(sequence, slate_data.get("sequence", "SEQ_01"))
        shot_text = _clean_text(shot, slate_data.get("shot", "A001"))
        take_text = _clean_text(take, slate_data.get("take", "1"))
        artist_text = _clean_text(artist, slate_data.get("artist", ""))
        client_text = _clean_text(client, "")
        task_text = _clean_text(task, "")
        round_text = _clean_text(round_label, "")
        reviewer_text = _clean_text(reviewer, "")
        date_value = _clean_text(date_text, slate_data.get("date_text", "")) or datetime.now().strftime("%Y-%m-%d")
        version_text = _normalize_version_tag(version_tag)
        take_token, take_label = _normalize_take_token(take_text)
        aspect_text = _aspect_from_sources(slate_data, review_info, contact_info) or "16:9"

        deliverable_meta = _DELIVERABLES.get(deliverable, _DELIVERABLES["Review"])
        deliverable_folder = deliverable_meta["folder"]
        deliverable_slug = deliverable_meta["slug"]
        badge_text = _clean_text(custom_badge, deliverable_meta["badge"])

        project_token = _slug_token(project_text, "mkrshift")
        sequence_token = _slug_token(sequence_text, "seq_01")
        shot_token = _slug_token(shot_text, "a001")
        artist_token = _slug_token(artist_text, "", max_len=24)
        client_token = _slug_token(client_text, "", max_len=24)
        department_token = _slug_token(department, "general", max_len=24)
        date_token = _slug_token(date_value, datetime.now().strftime("%Y_%m_%d"), max_len=24)
        ext_token = _slug_token(extension, "png", max_len=8) or "png"

        tokens: List[str] = [project_token]
        if naming_mode != "Client Friendly":
            tokens.append(sequence_token)
        tokens.append(shot_token)
        if bool(include_take) and take_token:
            tokens.append(take_token)
        tokens.append(version_text)
        if naming_mode == "Editorial" and department_token:
            tokens.append(department_token)
        task_token = _slug_token(task_text, "", max_len=24) if task_text else ""
        round_token = _slug_token(round_text, "", max_len=24) if round_text else ""
        if task_token and naming_mode != "Compact":
            tokens.append(task_token)
        if round_token and naming_mode == "Editorial":
            tokens.append(round_token)
        tokens.append(deliverable_slug)
        if bool(include_date):
            tokens.append(date_token)
        if bool(include_client) and client_token:
            tokens.append(client_token)
        if bool(include_artist) and artist_token:
            tokens.append(artist_token)
        filename_prefix = _slug_token("_".join([tok for tok in tokens if tok]), "mkrshift_review", max_len=160)

        subfolder_parts = [project_token, sequence_token, shot_token, deliverable_folder, version_text]
        subfolder = "/".join(part for part in subfolder_parts if part)

        review_title = f"{project_text} | {sequence_text} | {shot_text} | {version_text}"
        subtitle_parts = [department.lower(), deliverable.lower()]
        if task_text:
            subtitle_parts.append(task_text)
        if round_text:
            subtitle_parts.append(round_text)
        if bool(include_take) and take_label:
            subtitle_parts.append(f"take {take_label}")
        if date_value:
            subtitle_parts.append(date_value)
        review_subtitle = " • ".join(part for part in subtitle_parts if part)

        footer_left_parts = [department]
        if artist_text:
            footer_left_parts.append(artist_text)
        if task_text:
            footer_left_parts.append(task_text)
        footer_left = " • ".join(part for part in footer_left_parts if part)

        footer_right_parts = [version_text, aspect_text]
        if round_text:
            footer_right_parts.append(round_text)
        if client_text and naming_mode == "Client Friendly":
            footer_right_parts.append(client_text)
        footer_right = " | ".join(part for part in footer_right_parts if part)

        source_counts = {
            "review_frames": int(review_info.get("count", 0) or 0),
            "contact_sheet_frames": int(contact_info.get("count", 0) or 0),
            "selection_frames": int(selection_manifest.get("selection_count", 0) or 0),
        }
        selection_frames = selection_manifest.get("frames", []) if isinstance(selection_manifest.get("frames"), list) else []
        selection_status_counts = selection_manifest.get("status_counts", {}) if isinstance(selection_manifest.get("status_counts"), dict) else {}
        selection_frames_csv = _clean_text(selection_manifest.get("frames_csv", ""), "")
        selection_summary = _clean_text(selection_manifest.get("summary", ""), "")

        suggested_files = {
            "main": f"{filename_prefix}.{ext_token}",
            "review_frame": f"{filename_prefix}_review.{ext_token}",
            "burnin": f"{filename_prefix}_burnin.{ext_token}",
            "compare_board": f"{filename_prefix}_compare.{ext_token}",
            "contact_sheet": f"{filename_prefix}_contact_sheet.{ext_token}",
            "slate": f"{filename_prefix}_slate.{ext_token}",
            "selection_manifest": f"{filename_prefix}_selection_manifest.json",
            "review_notes": f"{filename_prefix}_review_notes.md",
            "delivery_sheet": f"{filename_prefix}_delivery_sheet.md",
            "manifest": f"{filename_prefix}_manifest.json",
            "notes": f"{filename_prefix}_notes.txt",
        }

        manifest_notes = {
            "delivery": {
                "project": project_text,
                "sequence": sequence_text,
                "shot": shot_text,
                "take": take_text,
                "version_tag": version_text,
                "deliverable": deliverable,
                "department": department,
                "artist": artist_text,
                "client": client_text,
                "task": task_text,
                "round_label": round_text,
                "reviewer": reviewer_text,
                "date_text": date_value,
                "aspect": aspect_text,
                "filename_prefix": filename_prefix,
                "subfolder": subfolder,
                "extension": ext_token,
            },
            "labels": {
                "review_title": review_title,
                "review_subtitle": review_subtitle,
                "badge": badge_text,
                "footer_left": footer_left,
                "footer_right": footer_right,
                "contact_title": f"{project_text} {deliverable}" + (f" • {task_text}" if task_text else ""),
                "contact_subtitle": f"{shot_text} • {version_text}" + (f" • {round_text}" if round_text else ""),
                "contact_label_prefix": shot_text,
                "slate_badge": badge_text,
                "round_label": round_text,
                "task": task_text,
                "reviewer": reviewer_text,
                "selection_summary": selection_summary,
            },
            "suggested_files": suggested_files,
            "source_counts": source_counts,
            "source_metadata": {
                "slate": slate_data,
                "review_frame": review_info,
                "contact_sheet": contact_info,
                "selection_manifest": selection_manifest,
            },
            "selection": {
                "selection_count": int(selection_manifest.get("selection_count", 0) or 0),
                "frames_csv": selection_frames_csv,
                "status_counts": selection_status_counts,
                "frames": selection_frames,
            },
            "notes": notes_data,
            "warnings": warnings,
        }

        summary = f"{filename_prefix} -> {subfolder} ({deliverable.lower()} | {version_text})"
        if int(source_counts["selection_frames"]) > 0:
            summary += f" | {int(source_counts['selection_frames'])} selected"
        delivery_plan = {
            "schema_version": 1,
            "summary": summary,
            "filename_prefix": filename_prefix,
            "subfolder": subfolder,
            "deliverable": deliverable,
            "naming_mode": naming_mode,
            "manifest_notes": manifest_notes,
        }
        return (
            filename_prefix,
            subfolder,
            review_title,
            json.dumps(manifest_notes, ensure_ascii=False),
            json.dumps(delivery_plan, ensure_ascii=False),
        )


class MKRStudioReviewBurnIn:
    SEARCH_ALIASES = ["review burn in", "studio overlay", "version stamp", "dailies burnin"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "title": ("STRING", {"default": ""}),
                "subtitle": ("STRING", {"default": ""}),
                "badge": ("STRING", {"default": ""}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "footer_left": ("STRING", {"default": ""}),
                "footer_right": ("STRING", {"default": ""}),
                "inset_px": ("INT", {"default": 28, "min": 0, "max": 512, "step": 2}),
                "band_height_px": ("INT", {"default": 96, "min": 40, "max": 320, "step": 2}),
                "accent_width_px": ("INT", {"default": 12, "min": 2, "max": 64, "step": 1}),
                "opacity": ("FLOAT", {"default": 0.9, "min": 0.1, "max": 1.0, "step": 0.01}),
                "show_frame_index": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "burnin_info")
    FUNCTION = "burn_in"
    CATEGORY = STUDIO_REVIEW

    def burn_in(
        self,
        image: torch.Tensor,
        title: str = "",
        subtitle: str = "",
        badge: str = "",
        theme: str = "Carbon",
        footer_left: str = "",
        footer_right: str = "",
        inset_px: int = 28,
        band_height_px: int = 96,
        accent_width_px: int = 12,
        opacity: float = 0.9,
        show_frame_index: bool = True,
        delivery_plan_json: str = "",
    ):
        warnings: List[str] = []
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        title_text = _clean_text(title, labels.get("review_title", "")) or "Client Review"
        subtitle_text = _clean_text(subtitle, labels.get("review_subtitle", ""))
        badge_text = _clean_text(badge, labels.get("badge", ""))
        footer_left_text = _clean_text(footer_left, labels.get("footer_left", "")) or "MKRShift Nodes"
        footer_right_text = _clean_text(footer_right, labels.get("footer_right", ""))

        batch = _to_image_batch(image)
        palette = _theme(theme)
        out_frames: List[Image.Image] = []

        inset = max(0, int(inset_px))
        band_h = max(40, int(band_height_px))
        accent_w = max(2, int(accent_width_px))
        alpha_fill = int(255 * float(np.clip(opacity, 0.1, 1.0)))

        for idx in range(int(batch.shape[0])):
            src = Image.fromarray(np.round(batch[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            base = src.convert("RGBA")
            draw = ImageDraw.Draw(base)
            w, h = base.size

            band_x0 = inset
            band_y0 = max(0, h - inset - band_h)
            band_x1 = max(band_x0 + 1, w - inset)
            band_y1 = min(h, band_y0 + band_h)
            band_box = (band_x0, band_y0, band_x1, band_y1)

            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(band_box, radius=max(14, band_h // 5), fill=palette["panel"] + (alpha_fill,))
            overlay_draw.rectangle((band_x0, band_y0, min(band_x1, band_x0 + accent_w), band_y1), fill=palette["accent"] + (255,))

            if badge_text:
                badge_font = _load_font(max(12, int(band_h * 0.16)), bold=True)
                badge_w, badge_h = _text_size(overlay_draw, badge_text, badge_font)
                badge_box = (
                    band_x0 + accent_w + max(10, band_h // 10),
                    max(0, band_y0 - badge_h - max(10, band_h // 8)),
                    band_x0 + accent_w + max(10, band_h // 10) + badge_w + max(16, band_h // 5),
                    band_y0 - max(2, band_h // 18),
                )
                overlay_draw.rounded_rectangle(badge_box, radius=14, fill=palette["panel_alt"] + (alpha_fill,))
                overlay_draw.text((badge_box[0] + max(8, band_h // 10), badge_box[1] + max(4, band_h // 12)), badge_text, font=badge_font, fill=palette["accent"] + (255,))

            base.alpha_composite(overlay)
            draw = ImageDraw.Draw(base)

            title_font = _load_font(max(16, int(band_h * 0.24)), bold=True)
            subtitle_font = _load_font(max(12, int(band_h * 0.15)))
            footer_font = _load_font(max(12, int(band_h * 0.16)))
            index_font = _load_font(max(12, int(band_h * 0.17)), bold=True)

            text_x = band_x0 + accent_w + max(14, band_h // 8)
            title_y = band_y0 + max(8, band_h // 9)
            draw.text((text_x, title_y), title_text, font=title_font, fill=palette["text"])

            if subtitle_text:
                subtitle_lines = _wrap_text(draw, subtitle_text, subtitle_font, max(40, band_x1 - text_x - max(120, band_h * 2)), 2)
                subtitle_y = title_y + max(18, band_h // 3)
                for line in subtitle_lines:
                    draw.text((text_x, subtitle_y), line, font=subtitle_font, fill=palette["muted"])
                    subtitle_y += max(14, int(band_h * 0.16))

            footer_y = band_y1 - max(22, band_h // 4)
            draw.text((text_x, footer_y), footer_left_text, font=footer_font, fill=palette["muted"])

            right_chunks: List[str] = []
            if footer_right_text:
                right_chunks.append(footer_right_text)
            if bool(show_frame_index):
                right_chunks.append(f"FRAME {idx + 1:02d}")
            right_text = " | ".join(chunk for chunk in right_chunks if chunk)
            if right_text:
                right_w, _ = _text_size(draw, right_text, index_font)
                draw.text((band_x1 - right_w - max(14, band_h // 8), footer_y), right_text, font=index_font, fill=palette["accent"])

            out_frames.append(base.convert("RGB"))

        info = {
            "theme": theme,
            "count": int(batch.shape[0]),
            "labels": {
                "title": title_text,
                "subtitle": subtitle_text,
                "badge": badge_text,
                "footer_left": footer_left_text,
                "footer_right": footer_right_text,
            },
            "layout": {
                "inset_px": inset,
                "band_height_px": band_h,
                "accent_width_px": accent_w,
                "show_frame_index": bool(show_frame_index),
            },
            "warnings": warnings,
        }
        return (_pil_to_batch(out_frames), json.dumps(info, ensure_ascii=False))


class MKRStudioCompareBoard:
    SEARCH_ALIASES = ["ab board", "before after board", "studio compare", "review compare"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "title": ("STRING", {"default": ""}),
                "subtitle": ("STRING", {"default": ""}),
                "label_a": ("STRING", {"default": "A"}),
                "label_b": ("STRING", {"default": "B"}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "orientation": (["Horizontal", "Vertical"], {"default": "Horizontal"}),
                "footer_left": ("STRING", {"default": ""}),
                "footer_right": ("STRING", {"default": ""}),
                "margin_px": ("INT", {"default": 24, "min": 8, "max": 256, "step": 2}),
                "gutter_px": ("INT", {"default": 16, "min": 0, "max": 128, "step": 2}),
                "header_px": ("INT", {"default": 56, "min": 24, "max": 240, "step": 2}),
                "footer_px": ("INT", {"default": 32, "min": 16, "max": 160, "step": 2}),
                "shadow_strength": ("FLOAT", {"default": 0.24, "min": 0.0, "max": 1.0, "step": 0.01}),
                "show_index": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "compare_info")
    FUNCTION = "board"
    CATEGORY = STUDIO_BOARDS

    def board(
        self,
        image_a: torch.Tensor,
        image_b: torch.Tensor,
        title: str = "",
        subtitle: str = "",
        label_a: str = "A",
        label_b: str = "B",
        theme: str = "Carbon",
        orientation: str = "Horizontal",
        footer_left: str = "",
        footer_right: str = "",
        margin_px: int = 24,
        gutter_px: int = 16,
        header_px: int = 56,
        footer_px: int = 32,
        shadow_strength: float = 0.24,
        show_index: bool = True,
        delivery_plan_json: str = "",
    ):
        warnings: List[str] = []
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        title_text = _clean_text(title, labels.get("review_title", "")) or "A/B Compare"
        subtitle_text = _clean_text(subtitle, labels.get("review_subtitle", ""))
        footer_left_text = _clean_text(footer_left, labels.get("footer_left", "")) or "MKRShift Nodes"
        footer_right_text = _clean_text(footer_right, labels.get("footer_right", ""))
        batch_a = _to_image_batch(image_a)
        batch_b = _to_image_batch(image_b)
        count = min(int(batch_a.shape[0]), int(batch_b.shape[0]))
        if int(batch_a.shape[0]) != int(batch_b.shape[0]):
            warnings.append("image_a and image_b batch counts differ; using shortest batch")

        palette = _theme(theme)
        horizontal = str(orientation or "Horizontal").strip().lower() != "vertical"
        framed: List[Image.Image] = []
        rows: List[Dict[str, Any]] = []

        margin = max(8, int(margin_px))
        gutter = max(0, int(gutter_px))
        header_h = max(24, int(header_px))
        footer_h = max(16, int(footer_px))

        for idx in range(count):
            src_a = Image.fromarray(np.round(batch_a[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            src_b = Image.fromarray(np.round(batch_b[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            slot_w = max(src_a.width, src_b.width)
            slot_h = max(src_a.height, src_b.height)

            if horizontal:
                out_w = (margin * 2) + (slot_w * 2) + gutter
                out_h = (margin * 2) + header_h + footer_h + slot_h
                box_a = (margin, margin + header_h, margin + slot_w, margin + header_h + slot_h)
                box_b = (box_a[2] + gutter, box_a[1], box_a[2] + gutter + slot_w, box_a[3])
            else:
                out_w = (margin * 2) + slot_w
                out_h = (margin * 2) + header_h + footer_h + (slot_h * 2) + gutter
                box_a = (margin, margin + header_h, margin + slot_w, margin + header_h + slot_h)
                box_b = (margin, box_a[3] + gutter, margin + slot_w, box_a[3] + gutter + slot_h)

            base = Image.new("RGBA", (out_w, out_h), palette["bg"] + (255,))
            _render_theme_background(base, theme, palette)
            draw = ImageDraw.Draw(base)

            title_font = _load_font(max(14, int(header_h * 0.3)), bold=True)
            subtitle_font = _load_font(max(12, int(header_h * 0.16)))
            footer_font = _load_font(max(12, int(footer_h * 0.4)))
            chip_font = _load_font(max(12, int(min(slot_w, slot_h) * 0.06)), bold=True)

            shadow_alpha = int(160 * float(np.clip(shadow_strength, 0.0, 1.0)))
            for box in (box_a, box_b):
                shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow)
                shadow_draw.rounded_rectangle(
                    (box[0] + 10, box[1] + 12, box[2] + 10, box[3] + 12),
                    radius=22,
                    fill=(0, 0, 0, shadow_alpha),
                )
                base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius=max(6, margin // 3))))
                draw.rounded_rectangle(box, radius=20, fill=palette["panel"], outline=palette["line"], width=2)

            fit_a = _fit_contain(src_a, (slot_w, slot_h), palette["panel_alt"]).convert("RGBA")
            fit_b = _fit_contain(src_b, (slot_w, slot_h), palette["panel_alt"]).convert("RGBA")
            _alpha_composite_clipped(base, fit_a, box_a, radius=20)
            _alpha_composite_clipped(base, fit_b, box_b, radius=20)
            draw.rounded_rectangle(box_a, radius=20, outline=palette["line"], width=2)
            draw.rounded_rectangle(box_b, radius=20, outline=palette["line"], width=2)

            draw.rectangle((0, 0, out_w, max(8, margin // 4)), fill=palette["accent"])
            draw.text((margin, margin), title_text, font=title_font, fill=palette["text"])
            if subtitle_text:
                draw.text((margin, margin + max(16, header_h // 2)), subtitle_text, font=subtitle_font, fill=palette["muted"])

            def draw_chip(box: Tuple[int, int, int, int], text: str) -> None:
                chip_w, chip_h = _text_size(draw, text, chip_font)
                chip_box = (
                    box[0] + max(10, margin // 2),
                    box[1] + max(10, margin // 2),
                    box[0] + max(10, margin // 2) + chip_w + max(18, margin // 2),
                    box[1] + max(10, margin // 2) + chip_h + max(12, margin // 3),
                )
                draw.rounded_rectangle(chip_box, radius=14, fill=palette["panel_alt"])
                draw.text((chip_box[0] + max(8, margin // 3), chip_box[1] + max(4, margin // 4)), text, font=chip_font, fill=palette["accent"])

            draw_chip(box_a, _clean_text(label_a, "A"))
            draw_chip(box_b, _clean_text(label_b, "B"))

            footer_y = out_h - margin - max(16, footer_h // 2)
            draw.text((margin, footer_y), footer_left_text, font=footer_font, fill=palette["muted"])

            right_parts: List[str] = []
            if footer_right_text:
                right_parts.append(footer_right_text)
            if bool(show_index):
                right_parts.append(f"PAIR {idx + 1:02d}")
            right_text = " | ".join(part for part in right_parts if part)
            if right_text:
                right_w, _ = _text_size(draw, right_text, footer_font)
                draw.text((out_w - margin - right_w, footer_y), right_text, font=footer_font, fill=palette["muted"])

            framed.append(base.convert("RGB"))
            rows.append(
                {
                    "index": idx + 1,
                    "orientation": "horizontal" if horizontal else "vertical",
                    "output_size": [out_w, out_h],
                    "slot_size": [slot_w, slot_h],
                    "label_a": _clean_text(label_a, "A"),
                    "label_b": _clean_text(label_b, "B"),
                }
            )

        info = {
            "theme": theme,
            "count": count,
            "orientation": "horizontal" if horizontal else "vertical",
            "title": title_text,
            "subtitle": subtitle_text,
            "footer_left": footer_left_text,
            "footer_right": footer_right_text,
            "rows": rows,
            "warnings": warnings,
        }
        return (_pil_to_batch(framed), json.dumps(info, ensure_ascii=False))
