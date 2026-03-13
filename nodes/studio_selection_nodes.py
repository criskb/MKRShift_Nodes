import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from ..categories import STUDIO_REVIEW
from .studio_nodes import _clean_text, _json_blob, _labels_from_delivery_plan


def _iter_selection_chunks(raw: Any) -> Iterable[str]:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "|" not in stripped and ("," in stripped or ";" in stripped):
            for token in re.split(r"[;,]", stripped):
                chunk = token.strip()
                if chunk:
                    yield chunk
            continue
        yield stripped


def _parse_index_span(token: str) -> List[int]:
    match = re.match(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*$", str(token or ""))
    if not match:
        return []
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    lo, hi = sorted((start, end))
    return list(range(lo, hi + 1))


def _parse_selection_line(raw: str, default_status: str) -> Tuple[List[int], str, str]:
    before_note, _, note_text = str(raw or "").partition("|")
    note = str(note_text or "").strip()
    match = re.match(r"^\s*(\d+(?:\s*-\s*\d+)?)\s*(?:(?::|=)\s*|\s+)?(.*?)\s*$", before_note)
    if not match:
        return ([], "", note)

    index_span = _parse_index_span(match.group(1))
    status = _clean_text(match.group(2), default_status).upper()
    return (index_span, status or str(default_status or "SELECT").upper(), note)


def _normalize_selection_payload(raw: Any) -> Dict[int, Dict[str, str]]:
    payload = _json_blob(raw, "base_selection_json", [])
    out: Dict[int, Dict[str, str]] = {}
    for key, value in payload.items():
        try:
            display_index = int(str(key).strip())
        except Exception:
            continue
        if isinstance(value, dict):
            status = _clean_text(value.get("status", value.get("label", "")), "SELECT").upper()
            note = _clean_text(value.get("note", ""), "")
        else:
            status = _clean_text(value, "SELECT").upper()
            note = ""
        out[display_index] = {
            "display_index": str(display_index),
            "status": status or "SELECT",
            "note": note,
        }
    return out


class MKRStudioSelectionSet:
    SEARCH_ALIASES = [
        "client selects",
        "selection json",
        "review selections",
        "approval selects",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "marked_frames": (
                    "STRING",
                    {
                        "default": "12:hero|best lighting\n14-15:select\n18:revise|hair needs cleanup",
                        "multiline": True,
                    },
                ),
                "default_status": (["SELECT", "APPROVE", "HERO", "HOLD", "REVISE", "KILL"], {"default": "SELECT"}),
                "sort_output": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "base_selection_json": ("STRING", {"default": "", "multiline": True}),
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
                "reviewer": ("STRING", {"default": ""}),
                "round_label": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = (
        "selection_json",
        "selection_manifest_json",
        "frames_csv",
        "selection_summary",
        "selection_count",
    )
    FUNCTION = "build"
    CATEGORY = STUDIO_REVIEW

    def build(
        self,
        marked_frames: str,
        default_status: str = "SELECT",
        sort_output: bool = True,
        base_selection_json: str = "",
        delivery_plan_json: str = "",
        reviewer: str = "",
        round_label: str = "",
    ):
        warnings: List[str] = []
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        delivery_payload = _json_blob(delivery_plan_json, "delivery_plan_json", warnings)
        manifest_notes = delivery_payload.get("manifest_notes", {}) if isinstance(delivery_payload, dict) else {}
        delivery_info = manifest_notes.get("delivery", {}) if isinstance(manifest_notes, dict) else {}
        selections = _normalize_selection_payload(base_selection_json)

        fallback_status = _clean_text(default_status, "SELECT").upper() or "SELECT"
        for chunk in _iter_selection_chunks(marked_frames):
            frames, status, note = _parse_selection_line(chunk, fallback_status)
            if not frames:
                warnings.append(f"Could not parse selection entry '{chunk}'")
                continue
            for display_index in frames:
                selections[int(display_index)] = {
                    "display_index": str(display_index),
                    "status": status or fallback_status,
                    "note": note,
                }

        ordered_indexes = list(selections.keys())
        if bool(sort_output):
            ordered_indexes.sort()

        selection_payload: Dict[str, Dict[str, str]] = {}
        rows: List[Dict[str, str]] = []
        status_counts = Counter()
        for display_index in ordered_indexes:
            row = dict(selections[display_index])
            status = _clean_text(row.get("status", ""), fallback_status).upper() or fallback_status
            note = _clean_text(row.get("note", ""), "")
            row["status"] = status
            row["note"] = note
            selection_payload[str(display_index)] = {
                "status": status,
                "note": note,
            }
            rows.append(
                {
                    "display_index": str(display_index),
                    "status": status,
                    "note": note,
                }
            )
            status_counts[status] += 1

        reviewer_text = _clean_text(reviewer, delivery_info.get("reviewer", ""))
        round_text = _clean_text(round_label, labels.get("round_label", ""))
        frames_csv = ",".join(row["display_index"] for row in rows)

        summary_bits = [f"{len(rows)} selections"]
        for status, count in sorted(status_counts.items()):
            summary_bits.append(f"{status} {count}")
        if round_text:
            summary_bits.append(round_text)
        if reviewer_text:
            summary_bits.append(reviewer_text)
        summary = " | ".join(summary_bits) if summary_bits else "0 selections"

        manifest = {
            "schema_version": 1,
            "summary": summary,
            "selection_count": len(rows),
            "frames_csv": frames_csv,
            "status_counts": dict(sorted(status_counts.items())),
            "reviewer": reviewer_text,
            "round_label": round_text,
            "delivery": delivery_info if isinstance(delivery_info, dict) else {},
            "labels": labels,
            "frames": rows,
            "warnings": warnings,
        }

        return (
            json.dumps(selection_payload, ensure_ascii=False, indent=2),
            json.dumps(manifest, ensure_ascii=False, indent=2),
            frames_csv,
            summary,
            len(rows),
        )
