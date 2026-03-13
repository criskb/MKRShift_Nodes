import json
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..categories import SOCIAL_UTILS


def _slugify_token(value: Any, fallback: str = "campaign") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _parse_plan(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    try:
        payload = json.loads(str(raw or "{}"))
    except Exception:
        warnings.append("plan_json is not valid JSON")
        return ({}, warnings)
    if not isinstance(payload, dict):
        warnings.append("plan_json must be a JSON object")
        return ({}, warnings)
    return (payload, warnings)


def _resolve_asset_source(asset: Dict[str, Any], plan_platform: str, mode: str, custom_source: str) -> str:
    if mode == "Custom":
        return _slugify_token(custom_source or "custom", "custom")
    if mode == "Plan Platform":
        return _slugify_token(plan_platform or "mixed", "mixed")
    return _slugify_token(asset.get("platform", plan_platform or "mixed"), "mixed")


def _resolve_asset_content(asset: Dict[str, Any], index: int, mode: str, include_ratio_suffix: bool) -> str:
    if mode == "Role":
        base = str(asset.get("role", "")).strip()
    elif mode == "Shot":
        base = str(asset.get("shot", "")).strip()
    elif mode == "Index":
        base = f"item-{index:02d}"
    else:
        base = str(asset.get("slot", "")).strip()

    content = _slugify_token(base or f"item-{index:02d}", f"item-{index:02d}")
    if bool(include_ratio_suffix):
        ratio = str(asset.get("ratio", "")).strip()
        if ratio:
            content = f"{content}-{ratio.replace(':', 'x')}"
    return content


def _compose_target_url(base_url: str, target_path: str, params: Dict[str, str]) -> str:
    root = str(base_url or "").strip() or "https://example.com"
    path_text = str(target_path or "").strip()
    if path_text.startswith("http://") or path_text.startswith("https://"):
        target = path_text
    elif path_text:
        target = urljoin(root.rstrip("/") + "/", path_text.lstrip("/"))
    else:
        target = root

    parsed = urlparse(target)
    current_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current_params.update({key: value for key, value in params.items() if str(value or "").strip()})
    query = urlencode(current_params)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def _markdown_row(values: List[str]) -> str:
    escaped = [str(value or "").replace("|", "\\|") for value in values]
    return "| " + " | ".join(escaped) + " |"


class MKRshiftSocialCampaignLinks:
    SEARCH_ALIASES = [
        "social utm builder",
        "campaign links",
        "tracking links",
        "social link table",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan_json": ("STRING", {"default": "", "multiline": True}),
                "base_url": ("STRING", {"default": "https://example.com"}),
                "target_path": ("STRING", {"default": "/"}),
                "utm_medium": ("STRING", {"default": "social"}),
                "utm_campaign": ("STRING", {"default": ""}),
                "utm_source_mode": (["Asset Platform", "Plan Platform", "Custom"], {"default": "Asset Platform"}),
                "utm_content_mode": (["Slot", "Role", "Shot", "Index"], {"default": "Slot"}),
                "include_ratio_suffix": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "custom_source": ("STRING", {"default": ""}),
                "utm_term": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = (
        "links_json",
        "link_table_md",
        "first_url",
        "summary_json",
        "link_count",
    )
    FUNCTION = "build_links"
    CATEGORY = SOCIAL_UTILS

    def build_links(
        self,
        plan_json: str,
        base_url: str,
        target_path: str = "/",
        utm_medium: str = "social",
        utm_campaign: str = "",
        utm_source_mode: str = "Asset Platform",
        utm_content_mode: str = "Slot",
        include_ratio_suffix: bool = True,
        custom_source: str = "",
        utm_term: str = "",
    ):
        plan, warnings = _parse_plan(plan_json)
        creative = plan.get("creative_brief", {}) if isinstance(plan.get("creative_brief"), dict) else {}
        pack = plan.get("pack", {}) if isinstance(plan.get("pack"), dict) else {}
        assets = plan.get("assets", []) if isinstance(plan.get("assets"), list) else []
        schedule = plan.get("schedule", []) if isinstance(plan.get("schedule"), list) else []
        plan_platform = str(creative.get("platform", "")).strip() or "Mixed"

        campaign_slug = _slugify_token(
            utm_campaign
            or creative.get("project_name")
            or creative.get("product_name")
            or pack.get("id")
            or pack.get("name")
            or "mkrshift-campaign",
            "mkrshift-campaign",
        )
        medium_slug = _slugify_token(utm_medium or "social", "social")
        term_text = str(utm_term or "").strip()

        rows: List[Dict[str, Any]] = []
        if not assets:
            assets = [{"index": 1, "slot": "campaign", "role": "root", "shot": "", "platform": plan_platform, "ratio": ""}]
            warnings.append("plan_json contained no assets; emitted a single campaign root link")

        for idx, asset in enumerate(assets, start=1):
            asset_data = asset if isinstance(asset, dict) else {}
            source = _resolve_asset_source(asset_data, plan_platform, utm_source_mode, custom_source)
            content = _resolve_asset_content(asset_data, idx, utm_content_mode, include_ratio_suffix)
            params = {
                "utm_source": source,
                "utm_medium": medium_slug,
                "utm_campaign": campaign_slug,
                "utm_content": content,
                "utm_term": term_text,
            }
            url = _compose_target_url(base_url, target_path, params)
            publish_at_local = str(asset_data.get("publish_at_local", "")).strip()
            if not publish_at_local and idx - 1 < len(schedule) and isinstance(schedule[idx - 1], dict):
                publish_at_local = str(schedule[idx - 1].get("publish_at_local", "")).strip()
            rows.append(
                {
                    "index": idx,
                    "platform": str(asset_data.get("platform", plan_platform)).strip() or plan_platform,
                    "ratio": str(asset_data.get("ratio", "")).strip(),
                    "slot": str(asset_data.get("slot", "")).strip(),
                    "role": str(asset_data.get("role", "")).strip(),
                    "shot": str(asset_data.get("shot", "")).strip(),
                    "publish_at_local": publish_at_local,
                    "utm": {key: value for key, value in params.items() if value},
                    "url": url,
                }
            )

        table_lines = [
            _markdown_row(["#", "Platform", "Ratio", "Slot", "Publish", "URL"]),
            _markdown_row(["---", "---", "---", "---", "---", "---"]),
        ]
        for row in rows:
            table_lines.append(
                _markdown_row(
                    [
                        str(row["index"]),
                        row["platform"],
                        row["ratio"],
                        row["slot"] or row["role"],
                        row["publish_at_local"],
                        row["url"],
                    ]
                )
            )

        summary = {
            "schema_version": 1,
            "campaign_slug": campaign_slug,
            "link_count": len(rows),
            "base_url": str(base_url or "").strip(),
            "target_path": str(target_path or "").strip(),
            "utm_source_mode": utm_source_mode,
            "utm_content_mode": utm_content_mode,
            "warnings": warnings,
        }

        return (
            json.dumps(rows, ensure_ascii=False, indent=2),
            "\n".join(table_lines),
            rows[0]["url"] if rows else "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            len(rows),
        )
