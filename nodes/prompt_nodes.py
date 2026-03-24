from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from ..categories import CORE_PROMPT
from ..lib.prompt_bookmarks import list_prompt_bookmarks


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _approx_token_count(prompt_text: str) -> int:
    text = _clean_text(prompt_text)
    if not text:
        return 0
    return max(1, round(len(text) / 3.8))


def _encode_prompt_conditioning(clip: Any, prompt_text: str) -> List[List[Any]]:
    if clip is None:
        return []

    tokenize = getattr(clip, "tokenize", None)
    encode_from_tokens = getattr(clip, "encode_from_tokens", None)
    if not callable(tokenize) or not callable(encode_from_tokens):
        return []

    prompt = str(prompt_text or "")
    tokens = tokenize(prompt)
    if isinstance(tokens, dict) and "g" in tokens and "l" in tokens:
        local_tokens = list(tokens.get("l", []) or [])
        global_tokens = list(tokens.get("g", []) or [])
        if len(local_tokens) != len(global_tokens):
            empty_tokens = tokenize("")
            empty_local = list(empty_tokens.get("l", []) or [])
            empty_global = list(empty_tokens.get("g", []) or [])
            while len(local_tokens) < len(global_tokens) and empty_local:
                local_tokens += empty_local
            while len(global_tokens) < len(local_tokens) and empty_global:
                global_tokens += empty_global
            tokens["l"] = local_tokens
            tokens["g"] = global_tokens

    encoded = encode_from_tokens(tokens, return_pooled=True)
    if isinstance(encoded, tuple):
        cond = encoded[0] if len(encoded) > 0 else None
        pooled = encoded[1] if len(encoded) > 1 else None
    else:
        cond = encoded
        pooled = None

    if cond is None:
        return []

    metadata: Dict[str, Any] = {}
    if pooled is not None:
        metadata["pooled_output"] = pooled
    return [[cond, metadata]]


class MKRCLIPTextEncodePrompt:
    SEARCH_ALIASES = [
        "prompt encode",
        "clip text encode prompt",
        "prompt bookmark writer",
        "prompt studio",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
            },
            "optional": {
                "prompt_text": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "STRING", "STRING")
    RETURN_NAMES = ("conditioning", "prompt_text", "summary_json")
    FUNCTION = "encode"
    CATEGORY = CORE_PROMPT

    def encode(self, clip, prompt_text: str = "") -> Tuple[List[List[Any]], str, str]:
        prompt = str(prompt_text or "")
        conditioning = _encode_prompt_conditioning(clip, prompt)
        bookmarks_payload = list_prompt_bookmarks()
        summary = {
            "prompt_text": prompt,
            "char_count": len(prompt),
            "line_count": prompt.count("\n") + (1 if prompt else 0),
            "word_count": len([part for part in prompt.replace("\n", " ").split(" ") if part]),
            "approx_token_count": _approx_token_count(prompt),
            "bookmark_count": int(bookmarks_payload.get("count", 0)),
            "folders": bookmarks_payload.get("folders", []),
            "has_conditioning": bool(conditioning),
        }
        return conditioning, prompt, json.dumps(summary, ensure_ascii=True)
