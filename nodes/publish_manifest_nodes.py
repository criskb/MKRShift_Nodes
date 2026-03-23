import csv
import io
import json
import re
from typing import Any, Dict, List, Tuple

import torch

from ..categories import PUBLISH_BUILD, PUBLISH_UTILS
from .studio_nodes import _ratio_label, _to_image_batch


def _split_lines_or_csv(text: Any) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[\n,;]+", raw) if part.strip()]


def _slug(value: Any, fallback: str = "asset") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _parse_manifest(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    try:
        payload = json.loads(str(raw or "{}"))
    except Exception:
        warnings.append("manifest_json is not valid JSON")
        return ({}, warnings)
    if not isinstance(payload, dict):
        warnings.append("manifest_json must be a JSON object")
        return ({}, warnings)
    return (payload, warnings)


def _caption_from_parts(headline: str, subhead: str, body: str, cta: str, hashtags: List[str]) -> str:
    parts = [part.strip() for part in [headline, subhead, body, cta] if str(part or "").strip()]
    text = "\n\n".join(parts)
    if hashtags:
        text = f"{text}\n\n{' '.join(hashtags)}" if text else " ".join(hashtags)
    return text


class MKRPublishAssetManifest:
    SEARCH_ALIASES = [
        "asset manifest",
        "filename manifest",
        "publish manifest",
        "delivery manifest",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "project": ("STRING", {"default": "MKRShift"}),
                "asset_prefix": ("STRING", {"default": "asset"}),
                "channel": ("STRING", {"default": "main"}),
                "extension": ("STRING", {"default": "png"}),
                "start_index": ("INT", {"default": 1, "min": 0, "max": 99999, "step": 1}),
                "title_prefix": ("STRING", {"default": "Release"}),
                "tags_csv": ("STRING", {"default": ""}),
                "notes": ("STRING", {"default": "", "multiline": True}),
                "alt_template": ("STRING", {"default": "{project} {display_index:02d} | {title} | {ratio}"}),
            },
            "optional": {
                "titles_csv": ("STRING", {"default": "", "multiline": True}),
                "shot_labels_csv": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("manifest_json", "manifest_csv", "manifest_md", "summary_json", "asset_count")
    FUNCTION = "build"
    CATEGORY = PUBLISH_BUILD

    def build(
        self,
        images: torch.Tensor,
        project: str = "MKRShift",
        asset_prefix: str = "asset",
        channel: str = "main",
        extension: str = "png",
        start_index: int = 1,
        title_prefix: str = "Release",
        tags_csv: str = "",
        notes: str = "",
        alt_template: str = "{project} {display_index:02d} | {title} | {ratio}",
        titles_csv: str = "",
        shot_labels_csv: str = "",
    ):
        batch = _to_image_batch(images)
        count = int(batch.shape[0])
        height = int(batch.shape[1]) if count else 0
        width = int(batch.shape[2]) if count else 0
        ratio = _ratio_label(width, height)

        project_text = str(project or "MKRShift").strip() or "MKRShift"
        prefix_slug = _slug(asset_prefix or "asset", "asset")
        ext = re.sub(r"[^A-Za-z0-9]+", "", str(extension or "png").strip().lower()) or "png"
        title_rows = _split_lines_or_csv(titles_csv)
        shot_rows = _split_lines_or_csv(shot_labels_csv)
        tags = _split_lines_or_csv(tags_csv)
        notes_text = str(notes or "").strip()

        rows: List[Dict[str, Any]] = []
        for idx in range(count):
            display_index = int(start_index) + idx
            title = title_rows[idx] if idx < len(title_rows) else f"{str(title_prefix or project_text).strip() or project_text} {display_index:02d}"
            shot_label = shot_rows[idx] if idx < len(shot_rows) else ""
            filename = f"{prefix_slug}_{display_index:03d}.{ext}"
            alt_text = str(alt_template or "").format(
                project=project_text,
                title=title,
                index=idx,
                display_index=display_index,
                channel=str(channel or "").strip(),
                width=width,
                height=height,
                ratio=ratio,
                filename=filename,
                shot_label=shot_label,
            )
            rows.append(
                {
                    "index": idx,
                    "display_index": display_index,
                    "filename": filename,
                    "project": project_text,
                    "channel": str(channel or "").strip(),
                    "title": title,
                    "shot_label": shot_label,
                    "width": width,
                    "height": height,
                    "ratio": ratio,
                    "alt_text": alt_text.strip(),
                    "tags": tags,
                    "notes": notes_text,
                }
            )

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=["display_index", "filename", "title", "shot_label", "ratio", "width", "height", "alt_text", "tags", "channel", "notes"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "display_index": row["display_index"],
                    "filename": row["filename"],
                    "title": row["title"],
                    "shot_label": row["shot_label"],
                    "ratio": row["ratio"],
                    "width": row["width"],
                    "height": row["height"],
                    "alt_text": row["alt_text"],
                    "tags": ", ".join(row["tags"]),
                    "channel": row["channel"],
                    "notes": row["notes"],
                }
            )

        md_lines = [
            "| # | Filename | Title | Ratio | Tags |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            md_lines.append(
                f"| {row['display_index']} | {row['filename']} | {row['title']} | {row['ratio']} | {' '.join(row['tags'])} |"
            )

        manifest = {
            "schema_version": 1,
            "project": project_text,
            "channel": str(channel or "").strip(),
            "asset_prefix": prefix_slug,
            "extension": ext,
            "count": count,
            "rows": rows,
        }
        summary = {
            "project": project_text,
            "asset_prefix": prefix_slug,
            "channel": str(channel or "").strip(),
            "count": count,
            "ratio": ratio,
            "notes": notes_text,
        }

        return (
            json.dumps(manifest, ensure_ascii=False, indent=2),
            csv_buffer.getvalue(),
            "\n".join(md_lines),
            json.dumps(summary, ensure_ascii=False, indent=2),
            count,
        )


class MKRPublishManifestAtIndex:
    SEARCH_ALIASES = [
        "manifest row at index",
        "publish row",
        "asset at index",
        "filename at index",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "manifest_json": ("STRING", {"default": "", "multiline": True}),
                "index": ("INT", {"default": 0, "min": 0, "max": 99999, "step": 1}),
                "index_mode": (["List Index", "Display Index"], {"default": "List Index"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("row_json", "filename", "title", "alt_text", "tags_csv")
    FUNCTION = "pick"
    CATEGORY = PUBLISH_UTILS

    def pick(self, manifest_json: str, index: int = 0, index_mode: str = "List Index"):
        manifest, warnings = _parse_manifest(manifest_json)
        rows = manifest.get("rows", []) if isinstance(manifest.get("rows"), list) else []
        selected: Dict[str, Any] = {}

        if index_mode == "Display Index":
            for row in rows:
                if isinstance(row, dict) and int(row.get("display_index", -1) or -1) == int(index):
                    selected = row
                    break
        elif 0 <= int(index) < len(rows) and isinstance(rows[int(index)], dict):
            selected = rows[int(index)]

        if not selected:
            selected = {
                "index": int(index),
                "display_index": int(index),
                "filename": "",
                "title": "",
                "alt_text": "",
                "tags": [],
                "warnings": warnings or ["requested row was not found"],
            }

        return (
            json.dumps(selected, ensure_ascii=False, indent=2),
            str(selected.get("filename", "")),
            str(selected.get("title", "")),
            str(selected.get("alt_text", "")),
            ", ".join(str(tag).strip() for tag in selected.get("tags", []) if str(tag).strip()),
        )


class MKRPublishCopyDeck:
    SEARCH_ALIASES = [
        "copy deck",
        "caption deck",
        "publish copy",
        "caption variants",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "headline": ("STRING", {"default": "New release"}),
                "subhead": ("STRING", {"default": ""}),
                "body": ("STRING", {"default": "", "multiline": True}),
                "cta": ("STRING", {"default": ""}),
                "hashtags_csv": ("STRING", {"default": ""}),
                "hook_lines": ("STRING", {"default": "", "multiline": True}),
                "tone": (["Neutral", "Clean", "Bold", "Warm"], {"default": "Clean"}),
                "platform_hint": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("deck_json", "deck_md", "first_caption", "summary_json", "variant_count")
    FUNCTION = "build"
    CATEGORY = PUBLISH_UTILS

    def build(
        self,
        headline: str = "New release",
        subhead: str = "",
        body: str = "",
        cta: str = "",
        hashtags_csv: str = "",
        hook_lines: str = "",
        tone: str = "Clean",
        platform_hint: str = "",
    ):
        hooks = _split_lines_or_csv(hook_lines) or [str(headline or "").strip() or "New release"]
        hashtags = [f"#{_slug(tag, '').replace('-', '')}" for tag in _split_lines_or_csv(hashtags_csv) if _slug(tag, "")]
        rows: List[Dict[str, Any]] = []

        tone_prefix = {
            "Neutral": "",
            "Clean": "Clean cut:",
            "Bold": "Big swing:",
            "Warm": "A little softer:",
        }.get(tone, "")

        for idx, hook in enumerate(hooks, start=1):
            row_headline = hook.strip() or str(headline or "").strip()
            caption = _caption_from_parts(
                " ".join(part for part in [tone_prefix, row_headline] if part).strip(),
                str(subhead or "").strip(),
                str(body or "").strip(),
                str(cta or "").strip(),
                hashtags,
            )
            rows.append(
                {
                    "index": idx,
                    "headline": row_headline,
                    "subhead": str(subhead or "").strip(),
                    "body": str(body or "").strip(),
                    "cta": str(cta or "").strip(),
                    "hashtags": hashtags,
                    "platform_hint": str(platform_hint or "").strip(),
                    "tone": tone,
                    "caption": caption,
                }
            )

        deck_md = "\n\n".join(
            [
                f"### Variant {row['index']}\n\n{row['caption']}"
                for row in rows
            ]
        )
        summary = {
            "variant_count": len(rows),
            "tone": tone,
            "platform_hint": str(platform_hint or "").strip(),
            "has_hashtags": bool(hashtags),
        }
        return (
            json.dumps({"schema_version": 1, "variants": rows}, ensure_ascii=False, indent=2),
            deck_md,
            rows[0]["caption"] if rows else "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            len(rows),
        )


class MKRPublishCopyAtIndex:
    SEARCH_ALIASES = [
        "copy at index",
        "caption at index",
        "publish caption pick",
        "copy variant pick",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "deck_json": ("STRING", {"default": "", "multiline": True}),
                "index": ("INT", {"default": 0, "min": 0, "max": 99999, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("variant_json", "headline", "caption", "hashtags_csv")
    FUNCTION = "pick"
    CATEGORY = PUBLISH_UTILS

    def pick(self, deck_json: str, index: int = 0):
        warnings: List[str] = []
        try:
            payload = json.loads(str(deck_json or "{}"))
        except Exception:
            payload = {}
            warnings.append("deck_json is not valid JSON")

        variants = payload.get("variants", []) if isinstance(payload, dict) else []
        selected: Dict[str, Any] = {}
        if 0 <= int(index) < len(variants) and isinstance(variants[int(index)], dict):
            selected = variants[int(index)]
        if not selected:
            selected = {
                "index": int(index),
                "headline": "",
                "caption": "",
                "hashtags": [],
                "warnings": warnings or ["requested variant was not found"],
            }

        return (
            json.dumps(selected, ensure_ascii=False, indent=2),
            str(selected.get("headline", "")),
            str(selected.get("caption", "")),
            ", ".join(str(tag).strip() for tag in selected.get("hashtags", []) if str(tag).strip()),
        )
