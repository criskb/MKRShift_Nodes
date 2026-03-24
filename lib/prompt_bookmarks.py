from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from aiohttp import web  # type: ignore
except Exception:  # pragma: no cover
    web = None

try:
    from server import PromptServer  # type: ignore
except Exception:  # pragma: no cover
    PromptServer = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROMPT_BOOKMARKS_ENV = "MKRSHIFT_PROMPT_BOOKMARKS_PATH"
_LOCK = threading.Lock()


def _storage_path() -> Path:
    custom = str(os.environ.get(PROMPT_BOOKMARKS_ENV, "")).strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return (PACKAGE_ROOT / "data" / "prompt_bookmarks.json").resolve()


def _ensure_storage_file() -> Path:
    path = _storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(json.dumps({"schema_version": 1, "bookmarks": []}, indent=2), encoding="utf-8")
    return path


def _clean_text(value: Any, limit: int = 10000) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    return text[:limit]


def _clean_folder(value: Any) -> str:
    raw = _clean_text(value, limit=160)
    return raw or "Default"


def _clean_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split(",")
    tags: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_text(item, limit=48)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(text)
    return tags[:24]


def _read_payload() -> Dict[str, Any]:
    path = _ensure_storage_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"schema_version": 1, "bookmarks": []}
    if not isinstance(data, dict):
        data = {"schema_version": 1, "bookmarks": []}
    if not isinstance(data.get("bookmarks"), list):
        data["bookmarks"] = []
    data["schema_version"] = 1
    return data


def _write_payload(payload: Dict[str, Any]) -> None:
    path = _ensure_storage_file()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _normalize_bookmark(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    prompt = _clean_text(raw.get("prompt"), limit=200000)
    name = _clean_text(raw.get("name"), limit=160)
    if not name or not prompt:
        return None
    created_at = float(raw.get("created_at") or time.time())
    updated_at = float(raw.get("updated_at") or created_at)
    bookmark = {
        "id": _clean_text(raw.get("id"), limit=80) or uuid.uuid4().hex,
        "folder": _clean_folder(raw.get("folder")),
        "name": name,
        "prompt": prompt,
        "notes": _clean_text(raw.get("notes"), limit=8000),
        "tags": _clean_tags(raw.get("tags")),
        "created_at": created_at,
        "updated_at": updated_at,
        "favorite": bool(raw.get("favorite", False)),
    }
    return bookmark


def list_prompt_bookmarks() -> Dict[str, Any]:
    with _LOCK:
        payload = _read_payload()
        bookmarks: List[Dict[str, Any]] = []
        for item in payload.get("bookmarks", []):
            normalized = _normalize_bookmark(item)
            if normalized is not None:
                bookmarks.append(normalized)
        bookmarks.sort(key=lambda item: (-int(item.get("favorite", False)), -float(item.get("updated_at", 0.0)), item["folder"].lower(), item["name"].lower()))
        payload["bookmarks"] = bookmarks
        _write_payload(payload)
    folders = sorted({bookmark["folder"] for bookmark in bookmarks}, key=str.lower)
    return {
        "schema_version": 1,
        "storage_path": str(_storage_path()),
        "folders": folders,
        "bookmarks": bookmarks,
        "count": len(bookmarks),
    }


def save_prompt_bookmark(bookmark_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    incoming = _normalize_bookmark(bookmark_payload)
    if incoming is None:
        raise ValueError("Bookmark requires a non-empty name and prompt.")

    with _LOCK:
        payload = _read_payload()
        bookmarks: List[Dict[str, Any]] = []
        for item in payload.get("bookmarks", []):
            normalized = _normalize_bookmark(item)
            if normalized is not None:
                bookmarks.append(normalized)

        updated = False
        now = time.time()
        for index, item in enumerate(bookmarks):
            if item["id"] != incoming["id"]:
                continue
            incoming["created_at"] = item.get("created_at", now)
            incoming["updated_at"] = now
            bookmarks[index] = incoming
            updated = True
            break

        if not updated:
            incoming["created_at"] = now
            incoming["updated_at"] = now
            bookmarks.append(incoming)

        payload["bookmarks"] = bookmarks
        _write_payload(payload)
    return incoming, updated


def delete_prompt_bookmark(bookmark_id: str) -> bool:
    target = _clean_text(bookmark_id, limit=80)
    if not target:
        return False
    with _LOCK:
        payload = _read_payload()
        bookmarks = [_normalize_bookmark(item) for item in payload.get("bookmarks", [])]
        normalized = [item for item in bookmarks if item is not None]
        next_items = [item for item in normalized if item["id"] != target]
        if len(next_items) == len(normalized):
            return False
        payload["bookmarks"] = next_items
        _write_payload(payload)
        return True


if PromptServer is not None and web is not None:

    @PromptServer.instance.routes.get("/mkrshift/prompt_bookmarks/list")
    async def mkrshift_prompt_bookmarks_list(_request):  # pragma: no cover - integration surface
        return web.json_response(list_prompt_bookmarks())


    @PromptServer.instance.routes.post("/mkrshift/prompt_bookmarks/save")
    async def mkrshift_prompt_bookmarks_save(request):  # pragma: no cover - integration surface
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object.")
            bookmark, updated = save_prompt_bookmark(payload)
            return web.json_response({"ok": True, "updated": updated, "bookmark": bookmark})
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=500)


    @PromptServer.instance.routes.post("/mkrshift/prompt_bookmarks/delete")
    async def mkrshift_prompt_bookmarks_delete(request):  # pragma: no cover - integration surface
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object.")
            deleted = delete_prompt_bookmark(str(payload.get("id", "")))
            return web.json_response({"ok": deleted})
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
