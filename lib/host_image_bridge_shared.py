from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image
import torch

from .host_bridge_shared import clean_text, parse_json_object, slugify


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".exr"}


def load_image_asset(path_text: str) -> Tuple[torch.Tensor, torch.Tensor, Dict[str, Any]]:
    path = Path(clean_text(path_text)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Image asset not found: {path}")

    with Image.open(path) as pil:
        rgba = pil.convert("RGBA")
        arr = np.asarray(rgba, dtype=np.float32) / 255.0
    rgb = torch.from_numpy(arr[..., :3]).unsqueeze(0).float()
    alpha = torch.from_numpy(arr[..., 3]).unsqueeze(0).float()
    info = {"path": str(path), "width": int(arr.shape[1]), "height": int(arr.shape[0]), "has_alpha": True}
    return (rgb, alpha, info)


def _looks_like_image_path(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return False
    return Path(text).suffix.lower() in IMAGE_SUFFIXES


def _collect_candidates(payload: Any, trail: List[str], out: List[Dict[str, str]]) -> None:
    if isinstance(payload, dict):
        path_value = payload.get("path")
        asset_path_value = payload.get("asset_path")
        candidate_path = path_value if _looks_like_image_path(path_value) else asset_path_value if _looks_like_image_path(asset_path_value) else ""
        if candidate_path:
            out.append(
                {
                    "path": clean_text(candidate_path),
                    "slot": clean_text(payload.get("slot") or payload.get("name") or payload.get("kind") or payload.get("type")),
                    "trail": "/".join(trail),
                }
            )
        for key, value in payload.items():
            _collect_candidates(value, trail + [clean_text(key) or str(key)], out)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            _collect_candidates(value, trail + [str(idx)], out)


def resolve_image_path_from_payload(payload: Dict[str, Any], preferred_slot: str = "") -> Tuple[str, List[Dict[str, str]]]:
    candidates: List[Dict[str, str]] = []
    _collect_candidates(payload, [], candidates)
    if not candidates:
        return ("", [])

    preferred = clean_text(preferred_slot).lower()
    if preferred:
        for item in candidates:
            if preferred in clean_text(item.get("slot")).lower():
                return (item["path"], candidates)
            if preferred in clean_text(item.get("trail")).lower():
                return (item["path"], candidates)
    return (candidates[0]["path"], candidates)


def build_image_import_summary(payload_json: str, preferred_slot: str = "") -> Tuple[Dict[str, Any], str, List[Dict[str, str]], List[str]]:
    payload, warnings = parse_json_object(payload_json, "payload_json")
    path, candidates = resolve_image_path_from_payload(payload, preferred_slot)
    if not path:
        warnings.append("No image path found in payload_json")
    return (payload, path, candidates, warnings)


def build_live_image_output_plan(
    schema: str,
    host: str,
    asset_path: str,
    image_role: str,
    target_name: str,
    apply_mode: str,
    transport_plan: Dict[str, Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    plan = {
        "schema": schema,
        "host": host,
        "asset_path": clean_text(asset_path),
        "asset_slug": slugify(asset_path, "asset"),
        "image_role": clean_text(image_role) or "beauty",
        "target_name": clean_text(target_name) or "MKRShift Result",
        "apply_mode": clean_text(apply_mode) or "texture",
        "transport_plan": transport_plan if isinstance(transport_plan, dict) else {},
    }
    plan.update(extra or {})
    return plan


def _resolve_output_path(asset_path: str, filename_override: str = "") -> Path:
    base = Path(clean_text(filename_override) or clean_text(asset_path) or "mkrshift_output.png").expanduser()
    suffix = base.suffix.lower()
    if suffix not in IMAGE_SUFFIXES or suffix == ".exr":
        return base.with_suffix(".png")
    return base


def _tensor_to_pil(image: torch.Tensor) -> Image.Image:
    array = image.detach().cpu().numpy()
    array = np.clip(array, 0.0, 1.0)
    uint8 = (array * 255.0).round().astype(np.uint8)
    return Image.fromarray(uint8, mode="RGB")


def save_image_output_assets(images: torch.Tensor, asset_path: str, filename_override: str = "") -> Tuple[List[str], List[str]]:
    target = _resolve_output_path(asset_path, filename_override)
    target.parent.mkdir(parents=True, exist_ok=True)
    warnings: List[str] = []
    if clean_text(target.suffix.lower()) != clean_text(Path(clean_text(filename_override) or clean_text(asset_path) or "").suffix.lower()):
        warnings.append("unsupported or missing output suffix, wrote PNG instead")
    batch = images if isinstance(images, torch.Tensor) and images.ndim == 4 else images.unsqueeze(0)
    paths: List[str] = []
    for index in range(int(batch.shape[0])):
        path = target if int(batch.shape[0]) == 1 else target.with_name(f"{target.stem}_{index:04d}{target.suffix}")
        pil = _tensor_to_pil(batch[index])
        pil.save(path)
        paths.append(str(path))
    return (paths, warnings)
