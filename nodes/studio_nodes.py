import json
import math
import re
from datetime import datetime
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import torch

from ..categories import STUDIO_DELIVERY, STUDIO_PREP, STUDIO_REVIEW


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


def _labels_from_delivery_plan(plan_json: Any, warnings: List[str]) -> Dict[str, str]:
    payload = _json_blob(plan_json, "delivery_plan_json", warnings)
    manifest_notes = payload.get("manifest_notes", {}) if isinstance(payload, dict) else {}
    labels = manifest_notes.get("labels", {}) if isinstance(manifest_notes, dict) else {}
    if not isinstance(labels, dict):
        warnings.append("delivery_plan_json labels payload is invalid")
        return {}
    return {str(key): _clean_text(value) for key, value in labels.items()}


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
        director: str = "",
        artist: str = "",
        camera: str = "Virtual Camera",
        lens: str = "50mm",
        fps: str = "24",
        aspect: str = "16:9",
        date_text: str = "",
        notes: str = "",
        thumbnail: Optional[torch.Tensor] = None,
    ):
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
        draw.text((left_x, left_y), str(project or "Untitled Project").upper(), font=header_font, fill=palette["text"])
        draw.text((left_x, left_y + int(h * 0.065)), f"Sequence {sequence or '-'}", font=meta_val_font, fill=palette["muted"])

        shot_y = left_y + int(h * 0.13)
        draw.text((left_x, shot_y), str(shot or "A001"), font=shot_font, fill=palette["accent"])
        take_w, take_h = _text_size(draw, f"TAKE {take or '1'}", take_font)
        take_box = (
            left_x,
            shot_y + int(h * 0.19),
            left_x + take_w + margin // 2,
            shot_y + int(h * 0.19) + take_h + margin // 3,
        )
        draw.rounded_rectangle(take_box, radius=16, fill=palette["panel_alt"])
        draw.text((take_box[0] + margin // 5, take_box[1] + margin // 8), f"TAKE {take or '1'}", font=take_font, fill=palette["text"])

        stamp = f"{camera or 'Camera'}  |  {lens or 'Lens'}  |  {fps or '24'} FPS  |  {aspect or '16:9'}"
        draw.text((left_x, left_box[3] - margin), stamp, font=meta_val_font, fill=palette["muted"])

        thumb = _first_pil(thumbnail)
        right_inner_x = right_box[0] + margin // 2
        right_inner_y = right_box[1] + margin // 2
        right_inner_w = right_box[2] - right_box[0] - margin

        if thumb is not None:
            thumb_h = int((right_box[3] - right_box[1]) * 0.34)
            thumb_box = (right_inner_x, right_inner_y, right_inner_x + right_inner_w, right_inner_y + thumb_h)
            thumb_fit = _fit_cover(thumb, (thumb_box[2] - thumb_box[0], thumb_box[3] - thumb_box[1]))
            base.alpha_composite(thumb_fit.convert("RGBA"), dest=(thumb_box[0], thumb_box[1]))
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(thumb_box, radius=20, outline=palette["line"] + (255,), width=2)
            base.alpha_composite(overlay)
            right_inner_y = thumb_box[3] + margin // 2

        metadata_rows = [
            ("Director", director or "-"),
            ("Artist", artist or "-"),
            ("Date", date_text or "-"),
            ("Aspect", aspect or _ratio_label(w, h)),
            ("FPS", fps or "24"),
            ("Lens", lens or "-"),
        ]
        row_y = right_inner_y
        for key, value in metadata_rows:
            draw.text((right_inner_x, row_y), key.upper(), font=meta_key_font, fill=palette["muted"])
            draw.text((right_inner_x + int(right_inner_w * 0.34), row_y - 2), value, font=meta_val_font, fill=palette["text"])
            draw.line(
                (
                    right_inner_x,
                    row_y + int(h * 0.032),
                    right_box[2] - margin // 2,
                    row_y + int(h * 0.032),
                ),
                fill=palette["line"],
                width=1,
            )
            row_y += int(h * 0.055)

        notes_lines = _wrap_text(draw, notes or "No notes.", note_font, notes_box[2] - notes_box[0] - margin, 3)
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
            "project": str(project or ""),
            "sequence": str(sequence or ""),
            "shot": str(shot or ""),
            "take": str(take or ""),
            "director": str(director or ""),
            "artist": str(artist or ""),
            "camera": str(camera or ""),
            "lens": str(lens or ""),
            "fps": str(fps or ""),
            "aspect": str(aspect or ""),
            "date_text": str(date_text or ""),
            "notes": str(notes or ""),
            "theme": str(theme or "Carbon"),
            "size": [w, h],
            "has_thumbnail": bool(thumb is not None),
        }
        summary = f"Studio slate {shot or 'A001'} take {take or '1'} | {w}x{h} | {theme}"
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
                "shadow_strength": ("FLOAT", {"default": 0.28, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
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
        shadow_strength: float = 0.28,
    ):
        batch = _to_image_batch(image)
        palette = _theme(theme)
        title_text = str(title or "Client Review")
        subtitle_text = str(subtitle or "")
        badge_text = str(badge or "")
        version_text = str(version_tag or "")
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
            base.alpha_composite(src.convert("RGBA"), dest=(image_box[0], image_box[1]))
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
            right_footer = footer_right or f"{src_w}x{src_h} | {ratio} | {version_text}"
            draw.text((margin, out_h - margin - int(footer_h * 0.58)), footer_left, font=footer_font, fill=palette["muted"])
            right_w, _ = _text_size(draw, right_footer, footer_font)
            draw.text((out_w - margin - right_w, out_h - margin - int(footer_h * 0.58)), right_footer, font=footer_font, fill=palette["muted"])
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
                    "version_tag": version_text,
                }
            )

        info = {
            "theme": theme,
            "count": len(layout_rows),
            "show_safe_area": bool(show_safe_area),
            "frames": layout_rows,
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
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "contact_sheet_info")
    FUNCTION = "board"
    CATEGORY = STUDIO_REVIEW

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
    ):
        batch = _to_image_batch(images)
        count = int(batch.shape[0])
        src_h = int(batch.shape[1])
        src_w = int(batch.shape[2])

        cols = max(1, min(int(columns), count or 1))
        rows = max(1, int(math.ceil(float(count) / float(cols))))
        margin = max(8, int(margin_px))
        gap = max(0, int(gap_px))
        header_h = max(48, int(header_px))
        footer_h = max(24, int(footer_px))
        cell_w = max(80, int(cell_width))
        cell_h = max(60, int(round((float(src_h) / float(max(1, src_w))) * cell_w)))
        label_h = max(44, int(cell_w * 0.22))
        card_h = cell_h + label_h

        board_w = (margin * 2) + (cols * cell_w) + (max(0, cols - 1) * gap)
        board_h = (margin * 2) + header_h + footer_h + (rows * card_h) + (max(0, rows - 1) * gap)

        palette = _theme(theme)
        base = Image.new("RGBA", (board_w, board_h), palette["bg"] + (255,))
        _render_theme_background(base, theme, palette)
        draw = ImageDraw.Draw(base)

        title_font = _load_font(int(header_h * 0.28), bold=True)
        subtitle_font = _load_font(int(header_h * 0.17))
        badge_font = _load_font(int(header_h * 0.15), bold=True)
        label_font = _load_font(max(16, int(label_h * 0.28)), bold=True)
        meta_font = _load_font(max(12, int(label_h * 0.19)))
        footer_font = _load_font(max(12, int(footer_h * 0.3)))

        draw.rectangle((0, 0, board_w, max(10, margin // 5)), fill=palette["accent"])
        draw.text((margin, margin), str(title or "Daily Selects"), font=title_font, fill=palette["text"])
        draw.text((margin, margin + int(header_h * 0.42)), str(subtitle or ""), font=subtitle_font, fill=palette["muted"])

        badge_text = str(badge or "")
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

            _panel_shadow(base, card_box, blur_radius=max(6, margin // 3))
            draw.rounded_rectangle(card_box, radius=22, fill=palette["panel"])
            draw.rectangle((card_x, label_y, card_x + cell_w, card_y + card_h), fill=palette["panel_alt"])

            src = Image.fromarray(np.round(batch[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            thumb = _fit_cover(src, (cell_w, cell_h)).convert("RGBA")
            base.alpha_composite(thumb, dest=(thumb_box[0], thumb_box[1]))
            draw.rounded_rectangle(card_box, radius=22, outline=palette["line"], width=2)
            draw.line((card_x, label_y, card_x + cell_w, label_y), fill=palette["line"], width=2)

            label = f"{label_prefix or 'SHOT'} {start_index + idx:02d}"
            detail_parts: List[str] = []
            if show_resolution:
                detail_parts.append(f"{src_w}x{src_h}")
            if show_ratio:
                detail_parts.append(ratio_text)
            detail = " | ".join(detail_parts)

            label_x = card_x + max(12, cell_w // 18)
            label_baseline = label_y + max(8, label_h // 8)
            draw.text((label_x, label_baseline), label, font=label_font, fill=palette["text"])
            if detail:
                draw.text((label_x, label_baseline + max(18, label_h // 3)), detail, font=meta_font, fill=palette["muted"])

            index_text = f"{idx + 1}/{count}"
            index_w, _ = _text_size(draw, index_text, meta_font)
            draw.text((card_x + cell_w - index_w - max(12, cell_w // 18), label_baseline), index_text, font=meta_font, fill=palette["accent"])

            frames.append(
                {
                    "index": idx + 1,
                    "row": row + 1,
                    "column": col + 1,
                    "label": label,
                    "input_size": [src_w, src_h],
                    "card_size": [cell_w, card_h],
                    "ratio": ratio_text,
                }
            )

        footer_left = f"{count} frames | {rows} rows x {cols} columns | card {cell_w}x{card_h}"
        footer_right = f"{theme} review board"
        footer_y = board_h - margin - max(16, footer_h // 2)
        draw.text((margin, footer_y), footer_left, font=footer_font, fill=palette["muted"])
        footer_right_w, _ = _text_size(draw, footer_right, footer_font)
        draw.text((board_w - margin - footer_right_w, footer_y), footer_right, font=footer_font, fill=palette["muted"])

        info = {
            "theme": theme,
            "title": str(title or ""),
            "subtitle": str(subtitle or ""),
            "badge": badge_text,
            "count": count,
            "rows": rows,
            "columns": cols,
            "cell_size": [cell_w, cell_h],
            "card_size": [cell_w, card_h],
            "board_size": [board_w, board_h],
            "show_ratio": bool(show_ratio),
            "show_resolution": bool(show_resolution),
            "frames": frames,
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
        notes_json: str = "{}",
    ):
        warnings: List[str] = []
        slate_data = _json_blob(slate_json, "slate_json", warnings)
        review_info = _json_blob(review_frame_info, "review_frame_info", warnings)
        contact_info = _json_blob(contact_sheet_info, "contact_sheet_info", warnings)
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
        date_value = _clean_text(date_text, slate_data.get("date_text", "")) or datetime.now().strftime("%Y-%m-%d")
        version_text = _normalize_version_tag(version_tag)
        take_token, take_label = _normalize_take_token(take_text)
        aspect_text = _aspect_from_sources(slate_data, review_info, contact_info) or "16:9"

        deliverable_meta = _DELIVERABLES.get(deliverable, _DELIVERABLES["Review"])
        deliverable_folder = deliverable_meta["folder"]
        deliverable_slug = deliverable_meta["slug"]
        badge_text = deliverable_meta["badge"]

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
        if bool(include_take) and take_label:
            subtitle_parts.append(f"take {take_label}")
        if date_value:
            subtitle_parts.append(date_value)
        review_subtitle = " • ".join(part for part in subtitle_parts if part)

        footer_left_parts = [department]
        if artist_text:
            footer_left_parts.append(artist_text)
        footer_left = " • ".join(part for part in footer_left_parts if part)

        footer_right_parts = [version_text, aspect_text]
        if client_text and naming_mode == "Client Friendly":
            footer_right_parts.append(client_text)
        footer_right = " | ".join(part for part in footer_right_parts if part)

        source_counts = {
            "review_frames": int(review_info.get("count", 0) or 0),
            "contact_sheet_frames": int(contact_info.get("count", 0) or 0),
        }

        suggested_files = {
            "main": f"{filename_prefix}.{ext_token}",
            "review_frame": f"{filename_prefix}_review.{ext_token}",
            "contact_sheet": f"{filename_prefix}_contact_sheet.{ext_token}",
            "slate": f"{filename_prefix}_slate.{ext_token}",
            "manifest": f"{filename_prefix}_manifest.json",
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
                "contact_title": f"{project_text} {deliverable}",
                "contact_subtitle": f"{shot_text} • {version_text}",
                "contact_label_prefix": shot_text,
            },
            "suggested_files": suggested_files,
            "source_counts": source_counts,
            "source_metadata": {
                "slate": slate_data,
                "review_frame": review_info,
                "contact_sheet": contact_info,
            },
            "notes": notes_data,
            "warnings": warnings,
        }

        summary = f"{filename_prefix} -> {subfolder} ({deliverable.lower()} | {version_text})"
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
    CATEGORY = STUDIO_REVIEW

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
            base.alpha_composite(fit_a, dest=(box_a[0], box_a[1]))
            base.alpha_composite(fit_b, dest=(box_b[0], box_b[1]))
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
