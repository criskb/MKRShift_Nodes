import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from .categories import SOCIAL_BUILDER, SOCIAL_UTILS

try:
    import folder_paths  # type: ignore
except Exception:
    folder_paths = None

try:
    from aiohttp import web  # type: ignore
except Exception:
    web = None

try:
    from fastapi import HTTPException  # type: ignore
    from fastapi.responses import FileResponse as FastFileResponse  # type: ignore
    from fastapi.responses import JSONResponse as FastJSONResponse  # type: ignore
except Exception:
    HTTPException = None
    FastFileResponse = None
    FastJSONResponse = None

try:
    from server import PromptServer  # type: ignore
except Exception:
    PromptServer = None


MODULE_DIR = Path(__file__).resolve().parent
PACK_DIR = MODULE_DIR / "packs"
PREVIEW_DIR = PACK_DIR / "previews"

PACK_SCHEMA_VERSION = "2.0"
DEFAULT_NEGATIVE = "low quality, blurry, overprocessed skin, watermark, text artifacts, compression artifacts"

PLATFORM_GUIDE: Dict[str, Dict[str, Any]] = {
    "Instagram": {
        "ratio_default": "4:5",
        "posting_windows": ["11:00", "18:00"],
        "style": "high performing social photography",
    },
    "TikTok": {
        "ratio_default": "9:16",
        "posting_windows": ["09:00", "20:00"],
        "style": "native vertical social video frame",
    },
    "YouTube Shorts": {
        "ratio_default": "9:16",
        "posting_windows": ["12:00", "19:00"],
        "style": "clean short-form creator style",
    },
    "LinkedIn": {
        "ratio_default": "1:1",
        "posting_windows": ["08:00", "12:00"],
        "style": "professional editorial social image",
    },
    "X": {
        "ratio_default": "1:1",
        "posting_windows": ["09:00", "17:00"],
        "style": "fast scroll-stopping social graphic-photo blend",
    },
    "Mixed": {
        "ratio_default": "4:5",
        "posting_windows": ["10:00", "16:00"],
        "style": "platform-agnostic social content",
    },
}

OBJECTIVE_GUIDE: Dict[str, Dict[str, str]] = {
    "Engagement": {
        "benefit": "invite comments, saves, and shares",
        "prompt_hint": "designed to maximize engagement",
    },
    "Sales": {
        "benefit": "drive purchase intent and conversion",
        "prompt_hint": "commercial intent with product clarity",
    },
    "Awareness": {
        "benefit": "increase recall and brand recognition",
        "prompt_hint": "distinctive and memorable visual identity",
    },
    "Leads": {
        "benefit": "generate qualified inbound interest",
        "prompt_hint": "value-forward and action-oriented framing",
    },
}

TONE_HINTS: Dict[str, Dict[str, str]] = {
    "None": {
        "caption": "neutral copy",
        "prompt": "clear editorial tone",
    },
    "Casual": {
        "caption": "friendly conversational copy",
        "prompt": "authentic creator vibe",
    },
    "Clean": {
        "caption": "minimal and sharp copy",
        "prompt": "clean premium composition",
    },
    "Spicy": {
        "caption": "punchy high-energy copy",
        "prompt": "bold contrast and dynamic framing",
    },
}

HOOK_TEMPLATES: Dict[str, List[str]] = {
    "Question": [
        "Would you try this {shot}?",
        "What would you rate this {shot}?",
        "Have you seen a {shot} like this before?",
    ],
    "Bold Claim": [
        "This {shot} changes everything.",
        "Our strongest {shot} yet.",
        "This is the benchmark for {product}.",
    ],
    "Story": [
        "Quick story behind this {shot}.",
        "From idea to final {shot}.",
        "How this {shot} came together.",
    ],
    "Tutorial": [
        "How to recreate this {shot} in 3 steps.",
        "Step-by-step breakdown of this {shot}.",
        "Simple method for this {shot} result.",
    ],
    "Problem/Solution": [
        "If your {product} feels flat, start with this {shot}.",
        "The common mistake: weak {shot}. The fix is this.",
        "Problem solved: a cleaner {shot} that converts.",
    ],
}

CTA_MAP: Dict[str, str] = {
    "Soft": "If this helped, save it for later.",
    "Direct": "Tap through now to get started.",
    "None": "",
}

HASHTAG_LIMITS = {
    "Auto": 10,
    "Lite": 5,
    "Off": 0,
}

_GENERIC_SHOTS = [
    "hero shot",
    "detail close-up",
    "context/lifestyle frame",
    "angle variation",
    "process moment",
    "final result",
]

_PACKS_CACHE: Dict[str, Dict[str, Any]] = {}


def _split_csv(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    return [x.strip() for x in re.split(r"[,;\n]", raw) if x.strip()]


def _slug_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", str(value or "")).strip()
    if not cleaned:
        return ""
    return "".join(chunk.capitalize() for chunk in cleaned.split() if chunk)


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


def _normalize_pack(raw: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    pid = str(raw.get("id") or fallback_id).strip() or fallback_id
    name = str(raw.get("name") or pid).strip() or pid
    tags = [str(t).strip() for t in raw.get("tags", []) if str(t).strip()]
    prompt_style = raw.get("promptStyle", {}) if isinstance(raw.get("promptStyle", {}), dict) else {}
    defaults = raw.get("defaults", {}) if isinstance(raw.get("defaults", {}), dict) else {}
    export_cfg = raw.get("export", {}) if isinstance(raw.get("export", {}), dict) else {}
    shots = [str(s).strip() for s in raw.get("shotList", []) if str(s).strip()]

    return {
        "id": pid,
        "name": name,
        "tags": tags,
        "description": str(raw.get("description", "")).strip(),
        "preview": str(raw.get("preview", "")).strip(),
        "defaults": {
            "count": int(defaults.get("count", 12)) if str(defaults.get("count", "")).isdigit() else 12,
            "ratios": [str(r).strip() for r in defaults.get("ratios", []) if str(r).strip()],
        },
        "promptStyle": {
            "base": str(prompt_style.get("base", "")).strip(),
            "neg": str(prompt_style.get("neg", "")).strip(),
        },
        "shotList": shots,
        "export": export_cfg,
    }


def _load_packs() -> Dict[str, Dict[str, Any]]:
    packs: Dict[str, Dict[str, Any]] = {}
    if not PACK_DIR.exists():
        return packs

    for p in sorted(PACK_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            normalized = _normalize_pack(data if isinstance(data, dict) else {}, p.stem)
            packs[normalized["id"]] = normalized
        except Exception:
            continue
    return packs


def _refresh_packs_cache() -> Dict[str, Dict[str, Any]]:
    global _PACKS_CACHE
    _PACKS_CACHE = _load_packs()
    return _PACKS_CACHE


def _pack_choices() -> List[str]:
    packs = _refresh_packs_cache()
    choices = [f"{pack['name']} ({pack_id})" for pack_id, pack in packs.items()]
    return sorted(choices, key=lambda x: x.lower())


def _extract_pack_id(choice: str) -> str:
    text = str(choice or "").strip()
    if "(" in text and text.endswith(")"):
        return text.split("(")[-1][:-1].strip()
    return text


def _pack_metadata() -> List[Dict[str, Any]]:
    packs = _refresh_packs_cache()
    rows: List[Dict[str, Any]] = []

    for pid, data in packs.items():
        preview_name = str(data.get("preview", "")).strip() or f"{pid}.png"
        preview_name = Path(preview_name).name
        rows.append(
            {
                "id": pid,
                "name": data.get("name", pid),
                "tags": data.get("tags", []),
                "description": data.get("description", ""),
                "preview": f"/mkrshift_social/preview/{preview_name}",
                "default_count": data.get("defaults", {}).get("count", 12),
                "ratios": data.get("defaults", {}).get("ratios", []),
                "shot_count": len(data.get("shotList", [])),
                "export": data.get("export", {}),
                "schema": PACK_SCHEMA_VERSION,
            }
        )

    rows.sort(key=lambda x: str(x.get("name", x.get("id", ""))).lower())
    return rows


def _find_pack(pack_id: str, pack_label: str = "") -> Tuple[Dict[str, Any], bool]:
    packs = _refresh_packs_cache()
    pid = str(pack_id or "").strip()
    if pid and pid in packs:
        return packs[pid], False

    fallback_id = _extract_pack_id(pack_label)
    if fallback_id in packs:
        return packs[fallback_id], False

    if packs:
        first = sorted(packs.values(), key=lambda x: str(x.get("name", "")).lower())[0]
        return first, True

    return (
        {
            "id": "missing_packs",
            "name": "Missing Packs",
            "tags": [],
            "description": "No pack files found.",
            "defaults": {"count": 12, "ratios": ["4:5"]},
            "promptStyle": {"base": "", "neg": ""},
            "shotList": list(_GENERIC_SHOTS),
            "export": {"type": "mixed", "zip": False},
            "preview": "",
        },
        True,
    )


def _platform_value(platform: str) -> Dict[str, Any]:
    key = platform if platform in PLATFORM_GUIDE else "Mixed"
    return PLATFORM_GUIDE[key]


def _objective_value(objective: str) -> Dict[str, str]:
    key = objective if objective in OBJECTIVE_GUIDE else "Engagement"
    return OBJECTIVE_GUIDE[key]


def _tone_value(caption_tone: str) -> Dict[str, str]:
    key = caption_tone if caption_tone in TONE_HINTS else "None"
    return TONE_HINTS[key]


def _select_ratio(aspect: str, output_mode: str, platform: str, pack: Dict[str, Any]) -> str:
    explicit = str(aspect or "").strip()
    if explicit and explicit != "Auto":
        return explicit

    ratios = pack.get("defaults", {}).get("ratios", [])
    if ratios:
        return str(ratios[0])

    if output_mode == "Story":
        return "9:16"
    if output_mode == "Mixed":
        return "1:1"
    return _platform_value(platform).get("ratio_default", "4:5")


def _parse_start_date(value: str) -> date:
    text = str(value or "").strip()
    if not text:
        return date.today()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(text)
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue

    try:
        return date.fromisoformat(text)
    except Exception:
        return date.today()


def _build_shot_plan(pack: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    shots = [str(x).strip() for x in pack.get("shotList", []) if str(x).strip()] or list(_GENERIC_SHOTS)
    out: List[Dict[str, Any]] = []
    for idx in range(count):
        shot = shots[idx % len(shots)]
        out.append(
            {
                "index": idx + 1,
                "shot": shot,
                "slot": f"item_{idx + 1:02d}",
            }
        )
    return out


def _build_hashtag_pool(
    pack_tags: List[str],
    project_name: str,
    product_name: str,
    audience: str,
    objective: str,
    platform: str,
) -> List[str]:
    seed_words = []
    seed_words.extend(pack_tags)
    seed_words.extend(_split_csv(project_name))
    seed_words.extend(_split_csv(product_name))
    seed_words.extend(_split_csv(audience))
    seed_words.append(objective)
    seed_words.append(platform)
    seed_words.extend(["ComfyUI", "AIGenerated", "ContentCreation"])

    tokens = [_slug_token(word) for word in seed_words]
    tokens = _dedupe_keep_order([t for t in tokens if t])
    return tokens or ["ComfyUI", "ContentCreation", "VisualStorytelling"]


def _build_hashtags(pool: List[str], mode: str, offset: int) -> List[str]:
    limit = HASHTAG_LIMITS.get(mode, HASHTAG_LIMITS["Auto"])
    if limit <= 0:
        return []

    rotated = pool[offset:] + pool[:offset]
    selected = rotated[:limit]
    return [f"#{token}" for token in selected]


def _build_hook(hook_style: str, index: int, shot: str, product_name: str) -> str:
    style = hook_style if hook_style in HOOK_TEMPLATES else "Question"
    templates = HOOK_TEMPLATES[style]
    template = templates[index % len(templates)]
    return template.format(
        shot=shot.lower(),
        product=(product_name.strip() or "this product"),
    )


def _build_caption(
    index: int,
    shot: str,
    objective: str,
    caption_tone: str,
    hook: str,
    cta_mode: str,
    hashtags: List[str],
    offer: str,
) -> str:
    objective_hint = _objective_value(objective).get("benefit", "drive action")
    tone_hint = _tone_value(caption_tone).get("caption", "clear copy")
    cta = CTA_MAP.get(cta_mode, "")

    body_parts = [
        hook,
        f"{shot.capitalize()} that helps {objective_hint}.",
        f"Tone: {tone_hint}.",
    ]

    offer_text = str(offer or "").strip()
    if offer_text:
        body_parts.append(f"Offer: {offer_text}.")

    if cta:
        body_parts.append(cta)

    if hashtags:
        body_parts.append(" ".join(hashtags))

    caption = " ".join(part for part in body_parts if part).strip()
    return re.sub(r"\s+", " ", caption)


def _build_prompt(
    pack: Dict[str, Any],
    shot: str,
    ratio: str,
    output_mode: str,
    branding: str,
    caption_tone: str,
    platform: str,
    objective: str,
    project_name: str,
    product_name: str,
    audience: str,
    custom_prompt_boost: str,
    offer: str,
    has_logo: bool,
) -> str:
    style = pack.get("promptStyle", {})
    base = str(style.get("base", "")).strip()

    platform_style = _platform_value(platform).get("style", "social media style")
    objective_hint = _objective_value(objective).get("prompt_hint", "")
    tone_prompt = _tone_value(caption_tone).get("prompt", "")

    parts = [
        base,
        shot,
        f"{ratio} composition",
        f"{output_mode.lower()} deliverable",
        platform_style,
        objective_hint,
        tone_prompt,
    ]

    if project_name.strip():
        parts.append(f"project context: {project_name.strip()}")
    if product_name.strip():
        parts.append(f"product focus: {product_name.strip()}")
    if audience.strip():
        parts.append(f"target audience: {audience.strip()}")
    if offer.strip():
        parts.append(f"key offer: {offer.strip()}")

    if branding == "Light":
        parts.append("subtle brand cues")
    elif branding == "Full":
        parts.append("strong brand expression")
        parts.append("visible logo placement" if has_logo else "logo area reserved")

    if custom_prompt_boost.strip():
        parts.append(custom_prompt_boost.strip())

    clean = _dedupe_keep_order([str(p).strip() for p in parts if str(p).strip()])
    return ", ".join(clean)


def _build_negative(pack: Dict[str, Any], negative_boost: str, banned_terms: str) -> str:
    style = pack.get("promptStyle", {})
    base_neg = str(style.get("neg", "")).strip()

    parts = [base_neg, DEFAULT_NEGATIVE]
    if negative_boost.strip():
        parts.append(negative_boost.strip())

    banned = _split_csv(banned_terms)
    if banned:
        parts.append("forbidden terms: " + ", ".join(banned))

    clean = _dedupe_keep_order([str(p).strip() for p in parts if str(p).strip()])
    return ", ".join(clean)


def _build_schedule(count: int, start_date_text: str, platform: str) -> List[Dict[str, Any]]:
    windows = _platform_value(platform).get("posting_windows", ["10:00"])
    start = _parse_start_date(start_date_text)

    out: List[Dict[str, Any]] = []
    for idx in range(count):
        day = start + timedelta(days=idx // max(1, len(windows)))
        slot = windows[idx % len(windows)]
        out.append(
            {
                "index": idx + 1,
                "platform": platform,
                "publish_at_local": f"{day.isoformat()}T{slot}:00",
            }
        )
    return out


def _readiness_warnings(pack_missing: bool, branding: str, has_logo: bool) -> List[str]:
    warnings: List[str] = []
    if pack_missing:
        warnings.append("Selected pack was missing; fallback pack used.")
    if branding != "Off" and not has_logo:
        warnings.append("Branding enabled without a connected logo input.")
    return warnings


def _temp_dir() -> Path:
    if folder_paths and hasattr(folder_paths, "get_temp_directory"):
        return Path(folder_paths.get_temp_directory())
    fallback = MODULE_DIR / ".temp"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _make_preview_image(image: Any) -> Optional[Image.Image]:
    if image is None:
        return None

    try:
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
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        image_pil.thumbnail((1024, 1024), resample=resample)
        return image_pil
    except Exception:
        return None


def _save_input_preview(image: Any) -> Optional[Dict[str, str]]:
    preview = _make_preview_image(image)
    if preview is None:
        return None

    output_dir = _temp_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"mkrshift_social_input_{uuid.uuid4().hex[:10]}.png"
    target = output_dir / filename
    preview.save(target, format="PNG", compress_level=1)
    return {"filename": filename, "subfolder": "", "type": "temp"}


def _is_fastapi_runtime() -> bool:
    if PromptServer is None:
        return False
    try:
        app = getattr(PromptServer.instance, "app", None)
        if app is None:
            return False
        module_name = str(app.__class__.__module__).lower()
        return ("fastapi" in module_name) or ("starlette" in module_name)
    except Exception:
        return False


def _json_response(payload: Any, status: int = 200):
    if _is_fastapi_runtime() and FastJSONResponse is not None:
        return FastJSONResponse(payload, status_code=status)
    if web is not None:
        return web.json_response(payload, status=status)
    if FastJSONResponse is not None:
        return FastJSONResponse(payload, status_code=status)
    return payload


def _file_response(path: Path):
    if _is_fastapi_runtime() and FastFileResponse is not None:
        return FastFileResponse(path)
    if web is not None:
        return web.FileResponse(path)
    if FastFileResponse is not None:
        return FastFileResponse(path)
    raise RuntimeError("No response backend available")


def _not_found(message: str):
    if _is_fastapi_runtime() and HTTPException is not None:
        raise HTTPException(status_code=404, detail=message)
    if web is not None:
        raise web.HTTPNotFound(text=message)
    if HTTPException is not None:
        raise HTTPException(status_code=404, detail=message)
    return _json_response({"error": message}, status=404)


def _resolve_path_value(request=None, key: str = "", default: str = "") -> str:
    if request is None or not key:
        return default
    if hasattr(request, "match_info"):
        return str(request.match_info.get(key, default))
    if hasattr(request, "path_params"):
        return str(request.path_params.get(key, default))
    return default


if PromptServer is not None:

    @PromptServer.instance.routes.get("/mkrshift_social/packs")
    async def mkrshift_social_pack_list(request=None):
        return _json_response(_pack_metadata())


    @PromptServer.instance.routes.get("/mkrshift_social/packs/{pack_id}")
    async def mkrshift_social_pack_details(request=None, pack_id: str = ""):
        pid = pack_id or _resolve_path_value(request, "pack_id", "")
        pack, missing = _find_pack(pid)
        payload = {
            "pack": pack,
            "fallback_used": missing,
            "schema": PACK_SCHEMA_VERSION,
        }
        return _json_response(payload)


    @PromptServer.instance.routes.get("/mkrshift_social/reload")
    async def mkrshift_social_reload_packs(request=None):
        packs = _refresh_packs_cache()
        return _json_response(
            {
                "ok": True,
                "count": len(packs),
                "packs": sorted(list(packs.keys())),
            }
        )


    @PromptServer.instance.routes.get("/mkrshift_social/preview/{filename}")
    async def mkrshift_social_pack_preview(request=None, filename: str = ""):
        raw_filename = filename or _resolve_path_value(request, "filename", "")
        safe_filename = Path(raw_filename).name
        if not safe_filename:
            return _not_found("Missing preview filename")

        preview_dir = PREVIEW_DIR.resolve()
        path = (PREVIEW_DIR / safe_filename).resolve()
        if path.parent != preview_dir or not path.exists():
            return _not_found("Preview not found")

        return _file_response(path)


class MKRshiftSocialPackBuilder:
    """
    Social Pack Builder v2
    - visual pack selection
    - smart prompt/caption/hashtag/schedule generation
    - IMAGE passthrough + structured JSON outputs
    """

    @classmethod
    def INPUT_TYPES(cls):
        packs = _pack_choices()
        if not packs:
            packs = ["(no packs found) (missing_packs)"]

        return {
            "required": {
                "image": ("IMAGE",),
                "pack": (packs,),
                "output_mode": (["Carousel", "Story", "Mixed"],),
                "count": ("INT", {"default": 12, "min": 1, "max": 60, "step": 1}),
                "aspect": (["Auto", "1:1", "4:5", "9:16"],),
                "branding": (["Off", "Light", "Full"],),
                "caption_tone": (["None", "Casual", "Clean", "Spicy"],),
                "platform": (["Instagram", "TikTok", "YouTube Shorts", "LinkedIn", "X", "Mixed"],),
                "objective": (["Engagement", "Sales", "Awareness", "Leads"],),
                "hook_style": (["Question", "Bold Claim", "Story", "Tutorial", "Problem/Solution"],),
                "cta_mode": (["Soft", "Direct", "None"],),
                "hashtag_mode": (["Auto", "Lite", "Off"],),
            },
            "optional": {
                "brand_logo": ("IMAGE",),
                "project_name": ("STRING", {"default": ""}),
                "product_name": ("STRING", {"default": ""}),
                "audience": ("STRING", {"default": ""}),
                "offer": ("STRING", {"default": ""}),
                "custom_prompt_boost": ("STRING", {"default": ""}),
                "negative_boost": ("STRING", {"default": ""}),
                "banned_terms": ("STRING", {"default": ""}),
                "start_date": ("STRING", {"default": ""}),
                "locale": ("STRING", {"default": "en-US"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_out", "plan_json", "prompts_json", "negative_prompts_json")
    FUNCTION = "build"
    CATEGORY = SOCIAL_BUILDER

    def build(
        self,
        image,
        pack,
        output_mode,
        count,
        aspect,
        branding,
        caption_tone,
        platform,
        objective,
        hook_style,
        cta_mode,
        hashtag_mode,
        brand_logo=None,
        project_name="",
        product_name="",
        audience="",
        offer="",
        custom_prompt_boost="",
        negative_boost="",
        banned_terms="",
        start_date="",
        locale="en-US",
        **legacy_kwargs,
    ):
        # Backward compatibility for previously exposed fields.
        legacy_pack_id = str(legacy_kwargs.get("pack_id", "")).strip()
        seed_mode = str(legacy_kwargs.get("seed_mode", "Fixed")).strip() or "Fixed"
        legacy_brand_colors = str(legacy_kwargs.get("brand_colors", "")).strip()

        pack_data, pack_missing = _find_pack(legacy_pack_id, str(pack))
        pack_id = str(pack_data.get("id", "missing_packs"))

        item_count = int(max(1, min(60, int(count))))
        aspect_used = _select_ratio(aspect, output_mode, platform, pack_data)
        has_logo = brand_logo is not None

        shot_plan = _build_shot_plan(pack_data, item_count)
        hashtag_pool = _build_hashtag_pool(
            pack_tags=pack_data.get("tags", []),
            project_name=project_name,
            product_name=product_name,
            audience=audience,
            objective=objective,
            platform=platform,
        )

        negatives: List[str] = []
        prompts: List[str] = []
        assets: List[Dict[str, Any]] = []

        for idx, shot_item in enumerate(shot_plan):
            shot = shot_item.get("shot", "")
            hook = _build_hook(hook_style, idx, shot, product_name)
            hashtags = _build_hashtags(hashtag_pool, hashtag_mode, idx)

            prompt = _build_prompt(
                pack=pack_data,
                shot=shot,
                ratio=aspect_used,
                output_mode=output_mode,
                branding=branding,
                caption_tone=caption_tone,
                platform=platform,
                objective=objective,
                project_name=project_name,
                product_name=product_name,
                audience=audience,
                custom_prompt_boost=custom_prompt_boost,
                offer=offer,
                has_logo=has_logo,
            )
            negative = _build_negative(pack_data, negative_boost, banned_terms)
            caption = _build_caption(
                index=idx,
                shot=shot,
                objective=objective,
                caption_tone=caption_tone,
                hook=hook,
                cta_mode=cta_mode,
                hashtags=hashtags,
                offer=offer,
            )

            prompts.append(prompt)
            negatives.append(negative)
            assets.append(
                {
                    "index": idx + 1,
                    "shot": shot,
                    "hook": hook,
                    "prompt": prompt,
                    "negative": negative,
                    "caption": caption,
                    "hashtags": hashtags,
                }
            )

        schedule = _build_schedule(item_count, start_date, platform)

        warnings = _readiness_warnings(
            pack_missing=pack_missing,
            branding=branding,
            has_logo=has_logo,
        )

        plan = {
            "schema_version": PACK_SCHEMA_VERSION,
            "pack": {
                "id": pack_id,
                "name": pack_data.get("name", pack_id),
                "tags": pack_data.get("tags", []),
                "description": pack_data.get("description", ""),
            },
            "creative_brief": {
                "project_name": str(project_name).strip(),
                "product_name": str(product_name).strip(),
                "audience": str(audience).strip(),
                "offer": str(offer).strip(),
                "platform": platform,
                "objective": objective,
                "hook_style": hook_style,
                "cta_mode": cta_mode,
                "caption_tone": caption_tone,
                "locale": str(locale).strip() or "en-US",
            },
            "generation": {
                "output_mode": output_mode,
                "count": item_count,
                "aspect": aspect_used,
                "branding": branding,
                "seed_mode": seed_mode,
                "hashtag_mode": hashtag_mode,
                "brand": {
                    "has_logo": has_logo,
                    "colors": legacy_brand_colors,
                },
            },
            "quality": {
                "status": "ready" if not warnings else "needs_attention",
                "warnings": warnings,
            },
            "shot_plan": shot_plan,
            "assets": assets,
            "schedule": schedule,
            "export": pack_data.get("export", {}),
        }

        input_preview = _save_input_preview(image)
        ui_payload: Dict[str, Any] = {}
        if input_preview is not None:
            ui_payload["input_preview"] = [input_preview]
        ui_payload["readiness"] = [
            {
                "status": plan["quality"]["status"],
                "warnings": warnings,
            }
        ]

        return {
            "ui": ui_payload,
            "result": (
                image,
                json.dumps(plan, ensure_ascii=False, indent=2),
                json.dumps(prompts, ensure_ascii=False),
                json.dumps(negatives, ensure_ascii=False),
            ),
        }


class MKRshiftSocialPackAssets:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "plan_json": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "captions_json",
        "hashtags_json",
        "schedule_json",
        "shot_plan_json",
        "summary_json",
    )
    FUNCTION = "extract"
    CATEGORY = SOCIAL_UTILS

    def extract(self, plan_json: str):
        try:
            plan = json.loads(plan_json or "{}")
            if not isinstance(plan, dict):
                plan = {}
        except Exception:
            plan = {}

        assets = plan.get("assets", []) if isinstance(plan.get("assets", []), list) else []
        captions = [item.get("caption", "") for item in assets if isinstance(item, dict)]
        hashtags = [item.get("hashtags", []) for item in assets if isinstance(item, dict)]

        summary = {
            "schema_version": plan.get("schema_version", "unknown"),
            "asset_count": len(assets),
            "status": plan.get("quality", {}).get("status", "unknown") if isinstance(plan.get("quality"), dict) else "unknown",
            "warnings": plan.get("quality", {}).get("warnings", []) if isinstance(plan.get("quality"), dict) else [],
            "pack": plan.get("pack", {}),
        }

        return (
            json.dumps(captions, ensure_ascii=False),
            json.dumps(hashtags, ensure_ascii=False),
            json.dumps(plan.get("schedule", []), ensure_ascii=False),
            json.dumps(plan.get("shot_plan", []), ensure_ascii=False),
            json.dumps(summary, ensure_ascii=False, indent=2),
        )


class MKRshiftSocialPromptAtIndex:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompts_json": ("STRING", {"default": "[]", "multiline": True}),
                "negative_prompts_json": ("STRING", {"default": "[]", "multiline": True}),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "index_mode": (["Clamp", "Wrap"],),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("prompt", "negative_prompt", "index_used", "total")
    FUNCTION = "pick"
    CATEGORY = SOCIAL_UTILS

    def pick(self, prompts_json: str, negative_prompts_json: str, index: int, index_mode: str):
        try:
            prompts = json.loads(prompts_json or "[]")
            if not isinstance(prompts, list):
                prompts = []
        except Exception:
            prompts = []

        try:
            negatives = json.loads(negative_prompts_json or "[]")
            if not isinstance(negatives, list):
                negatives = []
        except Exception:
            negatives = []

        total = len(prompts)
        if total <= 0:
            return ("", "", 0, 0)

        raw_idx = int(max(0, index))
        if index_mode == "Wrap":
            idx = raw_idx % total
        else:
            idx = min(raw_idx, total - 1)

        prompt = str(prompts[idx]) if idx < len(prompts) else ""
        negative = str(negatives[idx]) if idx < len(negatives) else ""
        return (prompt, negative, idx, total)


class MKRshiftSocialPackCatalog:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("packs_json", "pack_count")
    FUNCTION = "list_packs"
    CATEGORY = SOCIAL_UTILS

    def list_packs(self):
        packs = _pack_metadata()
        return (json.dumps(packs, ensure_ascii=False, indent=2), len(packs))
