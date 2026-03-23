import json
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw
import torch

from ..categories import PUBLISH_BUILD
from .studio_nodes import (
    _THEMES,
    _alpha_composite_clipped,
    _fit_cover,
    _fit_font_to_width,
    _load_font,
    _panel_shadow,
    _pil_to_batch,
    _render_theme_background,
    _text_size,
    _theme,
    _to_image_batch,
    _wrap_text,
)


class MKRPublishPromoFrame:
    SEARCH_ALIASES = [
        "promo frame",
        "launch frame",
        "marketing card",
        "publish frame",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "title": ("STRING", {"default": "New Release"}),
                "subtitle": ("STRING", {"default": "Feature highlight"}),
                "body": ("STRING", {"default": "", "multiline": True}),
                "badge": ("STRING", {"default": "FEATURED"}),
                "cta": ("STRING", {"default": "See more"}),
                "footer": ("STRING", {"default": "MKRShift Nodes"}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "margin_px": ("INT", {"default": 48, "min": 12, "max": 256, "step": 2}),
                "header_px": ("INT", {"default": 104, "min": 36, "max": 256, "step": 2}),
                "copy_height_px": ("INT", {"default": 168, "min": 80, "max": 320, "step": 2}),
                "show_index": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "publish_frame_info")
    FUNCTION = "frame"
    CATEGORY = PUBLISH_BUILD

    def frame(
        self,
        image: torch.Tensor,
        title: str = "New Release",
        subtitle: str = "Feature highlight",
        body: str = "",
        badge: str = "FEATURED",
        cta: str = "See more",
        footer: str = "MKRShift Nodes",
        theme: str = "Carbon",
        margin_px: int = 48,
        header_px: int = 104,
        copy_height_px: int = 168,
        show_index: bool = True,
    ):
        batch = _to_image_batch(image)
        palette = _theme(theme)
        cards: List[Image.Image] = []
        layout: List[Dict[str, Any]] = []

        for idx in range(int(batch.shape[0])):
            src = Image.fromarray(np.round(batch[idx, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")
            src_w, src_h = src.size
            margin = max(12, int(margin_px))
            header_h = max(36, int(header_px))
            copy_h = max(80, int(copy_height_px))

            out_w = src_w + (margin * 2)
            out_h = src_h + header_h + copy_h + (margin * 2)
            base = Image.new("RGBA", (out_w, out_h), palette["bg"] + (255,))
            _render_theme_background(base, theme, palette)
            draw = ImageDraw.Draw(base)

            image_box = (margin, margin + header_h, out_w - margin, margin + header_h + src_h)
            copy_box = (margin, image_box[3], out_w - margin, out_h - margin)

            _panel_shadow(base, image_box, blur_radius=max(8, margin // 3))
            _panel_shadow(base, copy_box, blur_radius=max(8, margin // 3))
            draw.rounded_rectangle(image_box, radius=28, fill=palette["panel"])
            draw.rounded_rectangle(copy_box, radius=26, fill=palette["panel_alt"])
            _alpha_composite_clipped(base, src, image_box, radius=28)
            draw.rounded_rectangle(image_box, radius=28, outline=palette["line"], width=2)
            draw.rounded_rectangle(copy_box, radius=26, outline=palette["line"], width=2)
            draw.rectangle((0, 0, out_w, max(10, margin // 4)), fill=palette["accent"])

            title_font = _fit_font_to_width(
                draw,
                title,
                int(header_h * 0.34),
                out_w - (margin * 2) - max(0, int(out_w * 0.22) if badge else 0),
                bold=True,
                min_size=max(16, int(header_h * 0.18)),
            )
            subtitle_font = _fit_font_to_width(
                draw,
                subtitle,
                int(header_h * 0.18),
                out_w - (margin * 2),
                min_size=max(11, int(header_h * 0.11)),
            )
            badge_font = _fit_font_to_width(
                draw,
                badge,
                int(header_h * 0.18),
                max(72, int(out_w * 0.26)),
                bold=True,
                min_size=max(10, int(header_h * 0.12)),
            )
            footer_font = _load_font(max(12, int(copy_h * 0.1)))
            body_font = _load_font(max(12, int(copy_h * 0.12)))
            cta_font = _load_font(max(13, int(copy_h * 0.14)), bold=True)

            draw.text((margin, margin + max(0, header_h // 10)), title, font=title_font, fill=palette["text"])
            if subtitle.strip():
                draw.text((margin, margin + int(header_h * 0.46)), subtitle, font=subtitle_font, fill=palette["muted"])

            if badge.strip():
                badge_w, badge_h = _text_size(draw, badge, badge_font)
                badge_box = (
                    out_w - margin - badge_w - max(18, margin // 2),
                    margin + max(4, header_h // 12),
                    out_w - margin,
                    margin + max(4, header_h // 12) + badge_h + max(12, margin // 4),
                )
                draw.rounded_rectangle(badge_box, radius=16, fill=palette["panel_alt"])
                draw.text((badge_box[0] + max(8, margin // 4), badge_box[1] + max(4, margin // 10)), badge, font=badge_font, fill=palette["accent"])

            copy_left = copy_box[0] + max(16, margin // 2)
            copy_y = copy_box[1] + max(14, margin // 3)
            wrap_width = copy_box[2] - copy_left - max(16, margin // 2)
            body_lines = _wrap_text(draw, body, body_font, wrap_width, 3)
            for line in body_lines:
                draw.text((copy_left, copy_y), line, font=body_font, fill=palette["text"])
                copy_y += max(16, int(copy_h * 0.14))

            if cta.strip():
                cta_w, cta_h = _text_size(draw, cta, cta_font)
                cta_box = (
                    copy_left,
                    copy_box[3] - max(18, margin // 2) - cta_h - max(10, margin // 5),
                    copy_left + cta_w + max(24, margin // 2),
                    copy_box[3] - max(18, margin // 2),
                )
                draw.rounded_rectangle(cta_box, radius=16, fill=palette["panel"])
                draw.text((cta_box[0] + max(10, margin // 4), cta_box[1] + max(4, margin // 10)), cta, font=cta_font, fill=palette["accent"])

            footer_parts = [footer.strip()] if footer.strip() else []
            if bool(show_index):
                footer_parts.append(f"{idx + 1:02d}/{int(batch.shape[0]):02d}")
            footer_text = " | ".join(part for part in footer_parts if part)
            if footer_text:
                footer_w, _ = _text_size(draw, footer_text, footer_font)
                draw.text((copy_box[2] - footer_w - max(16, margin // 2), copy_box[3] - max(18, margin // 2)), footer_text, font=footer_font, fill=palette["muted"])

            cards.append(base.convert("RGB"))
            layout.append(
                {
                    "index": idx + 1,
                    "input_size": [src_w, src_h],
                    "output_size": [out_w, out_h],
                    "title": title,
                    "subtitle": subtitle,
                    "badge": badge,
                    "cta": cta,
                    "theme": theme,
                }
            )

        info = {
            "theme": theme,
            "count": len(layout),
            "title": title,
            "subtitle": subtitle,
            "badge": badge,
            "cta": cta,
            "frames": layout,
        }
        return (_pil_to_batch(cards), json.dumps(info, ensure_ascii=False))


class MKRPublishEndCard:
    SEARCH_ALIASES = [
        "end card",
        "closing card",
        "cta card",
        "publish outro",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1080, "min": 256, "max": 4096, "step": 8}),
                "height": ("INT", {"default": 1350, "min": 256, "max": 4096, "step": 8}),
                "title": ("STRING", {"default": "Thanks for watching"}),
                "subtitle": ("STRING", {"default": "See the full drop in the next post"}),
                "body": ("STRING", {"default": "", "multiline": True}),
                "cta": ("STRING", {"default": "Follow for the next release"}),
                "footer": ("STRING", {"default": "MKRShift Nodes"}),
                "theme": (list(_THEMES.keys()), {"default": "Carbon"}),
                "margin_px": ("INT", {"default": 64, "min": 12, "max": 256, "step": 2}),
            },
            "optional": {
                "background_image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "end_card_info")
    FUNCTION = "render"
    CATEGORY = PUBLISH_BUILD

    def render(
        self,
        width: int = 1080,
        height: int = 1350,
        title: str = "Thanks for watching",
        subtitle: str = "See the full drop in the next post",
        body: str = "",
        cta: str = "Follow for the next release",
        footer: str = "MKRShift Nodes",
        theme: str = "Carbon",
        margin_px: int = 64,
        background_image: Optional[torch.Tensor] = None,
    ):
        out_w = max(256, int(width))
        out_h = max(256, int(height))
        margin = max(12, int(margin_px))
        palette = _theme(theme)
        base = Image.new("RGBA", (out_w, out_h), palette["bg"] + (255,))
        _render_theme_background(base, theme, palette)
        draw = ImageDraw.Draw(base)

        bg = None
        if background_image is not None:
            batch = _to_image_batch(background_image)
            if int(batch.shape[0]) > 0:
                bg = Image.fromarray(np.round(batch[0, ..., :3].cpu().numpy() * 255.0).astype(np.uint8), mode="RGB")

        hero_box = (margin, margin + max(20, out_h // 18), out_w - margin, out_h - margin)
        _panel_shadow(base, hero_box, blur_radius=max(12, margin // 2))
        draw.rounded_rectangle(hero_box, radius=36, fill=palette["panel"])
        if bg is not None:
            bg_fit = _fit_cover(bg, (hero_box[2] - hero_box[0], hero_box[3] - hero_box[1]))
            _alpha_composite_clipped(base, bg_fit, hero_box, radius=36)

        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(hero_box, radius=36, fill=(0, 0, 0, 110 if bg is not None else 0))
        base.alpha_composite(overlay)
        draw.rounded_rectangle(hero_box, radius=36, outline=palette["line"], width=2)
        draw.rectangle((0, 0, out_w, max(12, margin // 4)), fill=palette["accent"])

        title_font = _fit_font_to_width(draw, title, int(out_h * 0.07), hero_box[2] - hero_box[0] - margin, bold=True, min_size=max(20, int(out_h * 0.03)))
        subtitle_font = _fit_font_to_width(draw, subtitle, int(out_h * 0.03), hero_box[2] - hero_box[0] - margin, min_size=max(12, int(out_h * 0.018)))
        body_font = _load_font(max(14, int(out_h * 0.022)))
        cta_font = _load_font(max(14, int(out_h * 0.024)), bold=True)
        footer_font = _load_font(max(12, int(out_h * 0.018)))

        text_x = hero_box[0] + margin
        text_y = hero_box[1] + margin
        draw.text((text_x, text_y), title, font=title_font, fill=palette["text"])
        text_y += _text_size(draw, title, title_font)[1] + max(16, margin // 3)
        if subtitle.strip():
            draw.text((text_x, text_y), subtitle, font=subtitle_font, fill=palette["muted"])
            text_y += _text_size(draw, subtitle, subtitle_font)[1] + max(18, margin // 2)

        body_lines = _wrap_text(draw, body, body_font, hero_box[2] - hero_box[0] - (margin * 2), 5)
        for line in body_lines:
            draw.text((text_x, text_y), line, font=body_font, fill=palette["text"])
            text_y += max(18, int(out_h * 0.03))

        if cta.strip():
            cta_w, cta_h = _text_size(draw, cta, cta_font)
            cta_box = (
                text_x,
                hero_box[3] - margin - cta_h - max(18, margin // 3),
                text_x + cta_w + max(28, margin // 2),
                hero_box[3] - margin,
            )
            draw.rounded_rectangle(cta_box, radius=18, fill=palette["panel_alt"])
            draw.text((cta_box[0] + max(12, margin // 4), cta_box[1] + max(5, margin // 10)), cta, font=cta_font, fill=palette["accent"])

        if footer.strip():
            footer_w, _ = _text_size(draw, footer, footer_font)
            draw.text((hero_box[2] - footer_w - margin, hero_box[3] - margin + max(2, margin // 8)), footer, font=footer_font, fill=palette["muted"])

        info = {
            "theme": theme,
            "size": [out_w, out_h],
            "title": title,
            "subtitle": subtitle,
            "cta": cta,
            "has_background": bool(bg is not None),
        }
        return (_pil_to_batch([base.convert("RGB")]), json.dumps(info, ensure_ascii=False))
