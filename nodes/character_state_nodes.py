import json
import re
from typing import Any, Dict, List, Tuple

from ..categories import CORE_CHARACTER


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _split_tokens(value: Any) -> List[str]:
    raw = _clean_text(value)
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[\n,;|]+", raw) if part.strip()]


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


def _slug(value: Any, fallback: str = "character") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", _clean_text(value).lower()).strip("-")
    return text or fallback


def _parse_json_object(raw: Any, field_name: str) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    text = _clean_text(raw)
    if not text:
        return ({}, warnings)
    try:
        payload = json.loads(text)
    except Exception:
        warnings.append(f"{field_name} is not valid JSON")
        return ({}, warnings)
    if not isinstance(payload, dict):
        warnings.append(f"{field_name} must be a JSON object")
        return ({}, warnings)
    return (payload, warnings)


def _join_prompt_parts(parts: List[str]) -> str:
    cleaned = [part.strip().strip(",") for part in parts if _clean_text(part)]
    return ", ".join(cleaned)


class MKRCharacterState:
    SEARCH_ALIASES = [
        "character state",
        "character library",
        "character record",
        "identity state",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character_name": ("STRING", {"default": "Hero"}),
                "core_identity_prompt": ("STRING", {"default": "hero character design", "multiline": True}),
                "body_notes": ("STRING", {"default": "clear silhouette, readable anatomy"}),
                "face_notes": ("STRING", {"default": "recognizable face, stable eye shape"}),
                "style_anchor": ("STRING", {"default": "cinematic character design"}),
                "consistency_tokens_csv": ("STRING", {"default": ""}),
                "avoid_tokens_csv": ("STRING", {"default": ""}),
                "default_negative": ("STRING", {"default": "bad anatomy, off-model face, unstable costume details", "multiline": True}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "character_state_json": ("STRING", {"default": "", "multiline": True}),
                "reference_notes": ("STRING", {"default": "", "multiline": True}),
                "default_outfit_name": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("character_state_json", "positive_anchor", "negative_anchor", "summary_json")
    FUNCTION = "build"
    CATEGORY = CORE_CHARACTER

    def build(
        self,
        character_name: str = "Hero",
        core_identity_prompt: str = "hero character design",
        body_notes: str = "clear silhouette, readable anatomy",
        face_notes: str = "recognizable face, stable eye shape",
        style_anchor: str = "cinematic character design",
        consistency_tokens_csv: str = "",
        avoid_tokens_csv: str = "",
        default_negative: str = "bad anatomy, off-model face, unstable costume details",
        notes: str = "",
        character_state_json: str = "",
        reference_notes: str = "",
        default_outfit_name: str = "",
    ):
        existing, warnings = _parse_json_object(character_state_json, "character_state_json")
        previous_tokens = existing.get("consistency_tokens", []) if isinstance(existing.get("consistency_tokens"), list) else []
        previous_avoid = existing.get("avoid_tokens", []) if isinstance(existing.get("avoid_tokens"), list) else []
        outfits = existing.get("outfits", []) if isinstance(existing.get("outfits"), list) else []

        identity_prompt = _clean_text(core_identity_prompt) or _clean_text(existing.get("core_identity_prompt")) or "hero character design"
        body_text = _clean_text(body_notes) or _clean_text(existing.get("body_notes"))
        face_text = _clean_text(face_notes) or _clean_text(existing.get("face_notes"))
        style_text = _clean_text(style_anchor) or _clean_text(existing.get("style_anchor")) or "cinematic character design"
        reference_text = _clean_text(reference_notes) or _clean_text(existing.get("reference_notes"))
        note_text = _clean_text(notes) or _clean_text(existing.get("notes"))

        consistency_tokens = _dedupe_keep_order(
            [str(token).strip() for token in previous_tokens if str(token).strip()] + _split_tokens(consistency_tokens_csv)
        )
        avoid_tokens = _dedupe_keep_order(
            [str(token).strip() for token in previous_avoid if str(token).strip()] + _split_tokens(avoid_tokens_csv)
        )

        resolved_name = _clean_text(character_name) or _clean_text(existing.get("character_name")) or "Hero"
        resolved_default_outfit = (
            _clean_text(default_outfit_name)
            or _clean_text(existing.get("default_outfit"))
            or (outfits[0].get("name", "") if outfits and isinstance(outfits[0], dict) else "")
        )

        positive_anchor = _join_prompt_parts(
            [
                identity_prompt,
                body_text,
                face_text,
                style_text,
                ", ".join(consistency_tokens),
                reference_text,
            ]
        )
        negative_anchor = _join_prompt_parts([default_negative, ", ".join(avoid_tokens)])

        payload = {
            "schema_version": 1,
            "character_name": resolved_name,
            "character_slug": _slug(resolved_name, "character"),
            "core_identity_prompt": identity_prompt,
            "body_notes": body_text,
            "face_notes": face_text,
            "style_anchor": style_text,
            "reference_notes": reference_text,
            "consistency_tokens": consistency_tokens,
            "avoid_tokens": avoid_tokens,
            "default_negative": _clean_text(default_negative),
            "default_outfit": resolved_default_outfit,
            "outfits": outfits,
            "notes": note_text,
            "anchors": {
                "positive": positive_anchor,
                "negative": negative_anchor,
            },
            "warnings": warnings,
        }
        summary = {
            "character_name": resolved_name,
            "character_slug": payload["character_slug"],
            "outfit_count": len(outfits),
            "default_outfit": resolved_default_outfit,
            "consistency_token_count": len(consistency_tokens),
            "avoid_token_count": len(avoid_tokens),
        }
        return (
            json.dumps(payload, ensure_ascii=False, indent=2),
            positive_anchor,
            negative_anchor,
            json.dumps(summary, ensure_ascii=False, indent=2),
        )


class MKROutfitSet:
    SEARCH_ALIASES = [
        "outfit set",
        "character outfit",
        "costume set",
        "wardrobe set",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character_state_json": ("STRING", {"default": "", "multiline": True}),
                "outfit_name": ("STRING", {"default": "Base Look"}),
                "outfit_prompt": ("STRING", {"default": "signature costume, production-ready outfit", "multiline": True}),
                "silhouette_notes": ("STRING", {"default": "clear read from distance"}),
                "material_notes": ("STRING", {"default": "distinct material breakup"}),
                "accessories_csv": ("STRING", {"default": ""}),
                "palette_csv": ("STRING", {"default": ""}),
                "mood_hint": ("STRING", {"default": ""}),
                "match_strength": ("FLOAT", {"default": 0.82, "min": 0.0, "max": 1.0, "step": 0.01}),
                "set_as_default": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "outfit_notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("character_state_json", "outfit_json", "resolved_prompt", "summary_json")
    FUNCTION = "build"
    CATEGORY = CORE_CHARACTER

    def build(
        self,
        character_state_json: str,
        outfit_name: str = "Base Look",
        outfit_prompt: str = "signature costume, production-ready outfit",
        silhouette_notes: str = "clear read from distance",
        material_notes: str = "distinct material breakup",
        accessories_csv: str = "",
        palette_csv: str = "",
        mood_hint: str = "",
        match_strength: float = 0.82,
        set_as_default: bool = True,
        outfit_notes: str = "",
    ):
        state, warnings = _parse_json_object(character_state_json, "character_state_json")
        outfits = state.get("outfits", []) if isinstance(state.get("outfits"), list) else []
        existing_index = -1
        target_name = _clean_text(outfit_name) or "Base Look"
        for idx, outfit in enumerate(outfits):
            if isinstance(outfit, dict) and _clean_text(outfit.get("name")) == target_name:
                existing_index = idx
                break

        accessories = _dedupe_keep_order(_split_tokens(accessories_csv))
        palette = _dedupe_keep_order(_split_tokens(palette_csv))
        outfit_payload = {
            "name": target_name,
            "slug": _slug(target_name, "outfit"),
            "prompt": _clean_text(outfit_prompt),
            "silhouette_notes": _clean_text(silhouette_notes),
            "material_notes": _clean_text(material_notes),
            "accessories": accessories,
            "palette": palette,
            "mood_hint": _clean_text(mood_hint),
            "match_strength": round(float(match_strength), 4),
            "notes": _clean_text(outfit_notes),
        }

        if existing_index >= 0:
            outfits[existing_index] = outfit_payload
        else:
            outfits.append(outfit_payload)

        if bool(set_as_default):
            state["default_outfit"] = target_name
        elif not _clean_text(state.get("default_outfit")):
            state["default_outfit"] = target_name

        state["outfits"] = outfits
        if warnings:
            state["warnings"] = _dedupe_keep_order(
                [str(item).strip() for item in state.get("warnings", []) if str(item).strip()] + warnings
            )

        anchors = state.get("anchors", {}) if isinstance(state.get("anchors"), dict) else {}
        positive_anchor = _clean_text(anchors.get("positive"))
        resolved_prompt = _join_prompt_parts(
            [
                positive_anchor,
                outfit_payload["prompt"],
                outfit_payload["silhouette_notes"],
                outfit_payload["material_notes"],
                ", ".join(accessories),
                ", ".join(palette),
                outfit_payload["mood_hint"],
            ]
        )
        state.setdefault("anchors", {})
        state["anchors"]["outfit_prompt"] = resolved_prompt

        summary = {
            "character_name": _clean_text(state.get("character_name")),
            "outfit_name": target_name,
            "outfit_count": len(outfits),
            "default_outfit": _clean_text(state.get("default_outfit")),
            "match_strength": outfit_payload["match_strength"],
            "accessory_count": len(accessories),
        }
        return (
            json.dumps(state, ensure_ascii=False, indent=2),
            json.dumps(outfit_payload, ensure_ascii=False, indent=2),
            resolved_prompt,
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
