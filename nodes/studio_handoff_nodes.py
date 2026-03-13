import json
from typing import Any, Dict, List, Tuple

from ..categories import STUDIO_DELIVERY
from .studio_nodes import (
    _clean_text,
    _delivery_from_delivery_plan,
    _labels_from_delivery_plan,
    _manifest_notes_from_delivery_plan,
    _json_blob,
)


def _selection_manifest_from_json(raw: Any, warnings: List[str]) -> Dict[str, Any]:
    payload = _json_blob(raw, "selection_manifest_json", warnings)
    if not payload:
        return {}
    frames = payload.get("frames", [])
    if frames and not isinstance(frames, list):
        warnings.append("selection_manifest_json frames payload is invalid")
        frames = []
    status_counts = payload.get("status_counts", {})
    if status_counts and not isinstance(status_counts, dict):
        warnings.append("selection_manifest_json status_counts payload is invalid")
        status_counts = {}
    return {
        "summary": _clean_text(payload.get("summary", ""), ""),
        "selection_count": int(payload.get("selection_count", len(frames)) or 0),
        "frames_csv": _clean_text(payload.get("frames_csv", ""), ""),
        "status_counts": status_counts if isinstance(status_counts, dict) else {},
        "frames": frames if isinstance(frames, list) else [],
        "reviewer": _clean_text(payload.get("reviewer", ""), ""),
        "round_label": _clean_text(payload.get("round_label", ""), ""),
    }


def _coerce_suggested_files(manifest_notes: Dict[str, Any]) -> Dict[str, str]:
    payload = manifest_notes.get("suggested_files", {}) if isinstance(manifest_notes, dict) else {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): _clean_text(value, "") for key, value in payload.items() if _clean_text(value, "")}


def _compose_relative_path(subfolder: str, filename: str) -> str:
    folder = str(subfolder or "").strip().strip("/")
    name = str(filename or "").strip().lstrip("/")
    if not folder:
        return name
    if not name:
        return folder
    return f"{folder}/{name}"


class MKRStudioReviewNotes:
    SEARCH_ALIASES = ["review notes", "client notes", "studio handoff notes", "approval notes"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
                "headline": ("STRING", {"default": ""}),
                "next_steps": ("STRING", {"default": "", "multiline": True}),
                "include_suggested_files": ("BOOLEAN", {"default": True}),
                "include_frame_notes": ("BOOLEAN", {"default": True}),
                "include_status_breakdown": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "selection_manifest_json": ("STRING", {"default": "", "multiline": True}),
                "extra_notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("review_notes_md", "review_notes_json", "summary")
    FUNCTION = "build"
    CATEGORY = STUDIO_DELIVERY

    def build(
        self,
        delivery_plan_json: str,
        headline: str = "",
        next_steps: str = "",
        include_suggested_files: bool = True,
        include_frame_notes: bool = True,
        include_status_breakdown: bool = True,
        selection_manifest_json: str = "",
        extra_notes: str = "",
    ):
        warnings: List[str] = []
        manifest_notes = _manifest_notes_from_delivery_plan(delivery_plan_json, warnings)
        delivery = _delivery_from_delivery_plan(delivery_plan_json, warnings)
        labels = _labels_from_delivery_plan(delivery_plan_json, warnings)
        selection_manifest = _selection_manifest_from_json(selection_manifest_json, warnings)
        suggested_files = _coerce_suggested_files(manifest_notes)

        title_text = _clean_text(headline, labels.get("review_title", "")) or "Studio Review Notes"
        summary = _clean_text(delivery.get("deliverable", ""), "Review")
        shot_parts = [
            _clean_text(delivery.get("project", ""), ""),
            _clean_text(delivery.get("sequence", ""), ""),
            _clean_text(delivery.get("shot", ""), ""),
            _clean_text(delivery.get("version_tag", ""), ""),
        ]
        shot_label = " | ".join(part for part in shot_parts if part)

        lines: List[str] = [f"# {title_text}", ""]
        if shot_label:
            lines.append(f"- Shot: {shot_label}")
        if summary:
            lines.append(f"- Deliverable: {summary}")
        if _clean_text(delivery.get("department", ""), ""):
            lines.append(f"- Department: {_clean_text(delivery.get('department', ''), '')}")
        if _clean_text(delivery.get("reviewer", ""), ""):
            lines.append(f"- Reviewer: {_clean_text(delivery.get('reviewer', ''), '')}")
        if _clean_text(delivery.get("round_label", ""), ""):
            lines.append(f"- Round: {_clean_text(delivery.get('round_label', ''), '')}")
        if _clean_text(delivery.get("subfolder", ""), ""):
            lines.append(f"- Subfolder: {_clean_text(delivery.get('subfolder', ''), '')}")

        if selection_manifest.get("selection_count", 0) > 0:
            lines.extend(["", "## Selected Frames"])
            lines.append(f"- Count: {int(selection_manifest.get('selection_count', 0))}")
            if selection_manifest.get("frames_csv"):
                lines.append(f"- Frames: {selection_manifest['frames_csv']}")
            if bool(include_status_breakdown) and selection_manifest.get("status_counts"):
                for status, count in sorted(selection_manifest["status_counts"].items()):
                    lines.append(f"- {status}: {count}")
            if bool(include_frame_notes):
                for frame in selection_manifest.get("frames", []):
                    if not isinstance(frame, dict):
                        continue
                    display_index = _clean_text(frame.get("display_index", ""), "")
                    status = _clean_text(frame.get("status", ""), "")
                    note = _clean_text(frame.get("note", ""), "")
                    frame_line = f"- {display_index}"
                    if status:
                        frame_line += f" | {status}"
                    if note:
                        frame_line += f" | {note}"
                    lines.append(frame_line)

        cleaned_steps = [line.strip() for line in str(next_steps or "").splitlines() if line.strip()]
        if cleaned_steps:
            lines.extend(["", "## Next Steps"])
            for line in cleaned_steps:
                lines.append(f"- {line}")

        cleaned_extra = [line.rstrip() for line in str(extra_notes or "").splitlines() if line.strip()]
        if cleaned_extra:
            lines.extend(["", "## Extra Notes"])
            lines.extend(cleaned_extra)

        if bool(include_suggested_files) and suggested_files:
            lines.extend(["", "## Suggested Files"])
            subfolder = _clean_text(delivery.get("subfolder", ""), "")
            for role, filename in suggested_files.items():
                lines.append(f"- {role}: {_compose_relative_path(subfolder, filename)}")

        markdown = "\n".join(lines).rstrip() + "\n"
        notes_payload = {
            "schema_version": 1,
            "headline": title_text,
            "shot_label": shot_label,
            "delivery": delivery,
            "selection": selection_manifest,
            "suggested_files": suggested_files,
            "next_steps": cleaned_steps,
            "extra_notes": cleaned_extra,
            "warnings": warnings,
        }
        summary_text = shot_label or title_text
        if int(selection_manifest.get("selection_count", 0)) > 0:
            summary_text += f" | {int(selection_manifest.get('selection_count', 0))} selections"
        return (markdown, json.dumps(notes_payload, ensure_ascii=False, indent=2), summary_text)


class MKRStudioDeliverySheet:
    SEARCH_ALIASES = ["delivery sheet", "studio file list", "handoff sheet", "turnover sheet"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delivery_plan_json": ("STRING", {"default": "", "multiline": True}),
                "root_folder": ("STRING", {"default": ""}),
                "include_optional_files": ("BOOLEAN", {"default": True}),
                "include_selection_context": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "selection_manifest_json": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("delivery_rows_json", "delivery_sheet_md", "summary_json", "row_count")
    FUNCTION = "build"
    CATEGORY = STUDIO_DELIVERY

    def build(
        self,
        delivery_plan_json: str,
        root_folder: str = "",
        include_optional_files: bool = True,
        include_selection_context: bool = True,
        selection_manifest_json: str = "",
    ):
        warnings: List[str] = []
        manifest_notes = _manifest_notes_from_delivery_plan(delivery_plan_json, warnings)
        delivery = _delivery_from_delivery_plan(delivery_plan_json, warnings)
        selection_manifest = _selection_manifest_from_json(selection_manifest_json, warnings)
        suggested_files = _coerce_suggested_files(manifest_notes)
        subfolder = _clean_text(delivery.get("subfolder", ""), "")
        root = str(root_folder or "").strip().rstrip("/")
        optional_roles = {
            "burnin",
            "compare_board",
            "contact_sheet",
            "slate",
            "selection_manifest",
            "review_notes",
            "delivery_sheet",
            "notes",
        }
        preferred_order = [
            "main",
            "review_frame",
            "burnin",
            "compare_board",
            "contact_sheet",
            "slate",
            "selection_manifest",
            "review_notes",
            "delivery_sheet",
            "manifest",
            "notes",
        ]

        rows: List[Dict[str, Any]] = []
        sorted_roles = sorted(
            suggested_files.keys(),
            key=lambda role: (preferred_order.index(role) if role in preferred_order else len(preferred_order), role),
        )
        for role in sorted_roles:
            if not bool(include_optional_files) and role in optional_roles:
                continue
            filename = suggested_files[role]
            relative_path = _compose_relative_path(subfolder, filename)
            resolved_path = f"{root}/{relative_path}".lstrip("/") if root else relative_path
            row = {
                "role": role,
                "filename": filename,
                "relative_path": relative_path,
                "resolved_path": resolved_path,
                "deliverable": _clean_text(delivery.get("deliverable", ""), ""),
                "version_tag": _clean_text(delivery.get("version_tag", ""), ""),
            }
            if bool(include_selection_context):
                row["selection_frames_csv"] = selection_manifest.get("frames_csv", "")
                row["selection_count"] = int(selection_manifest.get("selection_count", 0) or 0)
            rows.append(row)

        md_lines = [
            "| Role | Filename | Relative Path | Version | Selected Frames |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            md_lines.append(
                "| {role} | {filename} | {relative_path} | {version_tag} | {selection_frames_csv} |".format(
                    role=str(row.get("role", "")).replace("|", "\\|"),
                    filename=str(row.get("filename", "")).replace("|", "\\|"),
                    relative_path=str(row.get("relative_path", "")).replace("|", "\\|"),
                    version_tag=str(row.get("version_tag", "")).replace("|", "\\|"),
                    selection_frames_csv=str(row.get("selection_frames_csv", "")).replace("|", "\\|"),
                )
            )

        summary = {
            "schema_version": 1,
            "row_count": len(rows),
            "deliverable": _clean_text(delivery.get("deliverable", ""), ""),
            "subfolder": subfolder,
            "root_folder": root,
            "selection_count": int(selection_manifest.get("selection_count", 0) or 0),
            "warnings": warnings,
        }
        return (
            json.dumps(rows, ensure_ascii=False, indent=2),
            "\n".join(md_lines),
            json.dumps(summary, ensure_ascii=False, indent=2),
            len(rows),
        )
