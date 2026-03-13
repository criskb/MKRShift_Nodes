from __future__ import annotations

import site
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from aiohttp import web  # type: ignore
except Exception:  # pragma: no cover
    web = None

try:
    from server import PromptServer  # type: ignore
except Exception:  # pragma: no cover
    PromptServer = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _candidate_frontend_asset_dirs() -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    site_roots: List[str] = []
    try:
        site_roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            site_roots.append(user_site)
    except Exception:
        pass

    for root in site_roots:
        asset_dir = Path(str(root)) / "comfyui_frontend_package" / "static" / "assets"
        if asset_dir.is_dir():
            resolved = str(asset_dir.resolve())
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(asset_dir.resolve())

    for parent in PACKAGE_ROOT.parents:
        for env_name in (".venv", "venv"):
            lib_root = parent / env_name / "lib"
            if not lib_root.is_dir():
                continue
            for python_dir in sorted(lib_root.glob("python*")):
                asset_dir = python_dir / "site-packages" / "comfyui_frontend_package" / "static" / "assets"
                if asset_dir.is_dir():
                    resolved = str(asset_dir.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(asset_dir.resolve())

    return candidates


def _iter_load3d_wrappers(asset_dir: Path) -> Iterable[Path]:
    for path in sorted(asset_dir.glob("Load3D-*.js")):
        if "Configuration" in path.name or "Controls" in path.name:
            continue
        yield path


def _pick_load3d_component_asset(asset_dir: Path) -> str:
    for path in _iter_load3d_wrappers(asset_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "export{e as default}" in text or "export { e as default }" in text or "export{t as default}" in text:
            return path.name

    fallback = min(_iter_load3d_wrappers(asset_dir), key=lambda item: item.stat().st_size, default=None)
    if fallback is not None:
        return fallback.name
    raise FileNotFoundError("No Load3D frontend asset was found in the ComfyUI frontend package")


def _pick_use_load3d_asset(asset_dir: Path) -> str:
    for path in sorted(asset_dir.glob("useLoad3d-*.js")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "nodeToLoad3dMap" in text and "useLoad3d" in text:
            return path.name

    raise FileNotFoundError("No stable useLoad3d frontend asset was found in the ComfyUI frontend package")


@lru_cache(maxsize=1)
def resolve_native_3d_assets() -> Dict[str, str]:
    errors: List[str] = []
    for asset_dir in _candidate_frontend_asset_dirs():
        try:
            component_asset = _pick_load3d_component_asset(asset_dir)
            use_load3d_asset = _pick_use_load3d_asset(asset_dir)
            return {
                "load3d_component_asset": f"/assets/{component_asset}",
                "use_load3d_asset": f"/assets/{use_load3d_asset}",
                "frontend_assets_dir": str(asset_dir),
            }
        except Exception as exc:
            errors.append(f"{asset_dir}: {exc}")

    detail = "; ".join(errors) if errors else "no ComfyUI frontend asset directory was discovered"
    raise FileNotFoundError(f"Unable to resolve the built-in Load3D frontend asset: {detail}")


if PromptServer is not None and web is not None:

    @PromptServer.instance.routes.get("/mkrshift/native_3d_assets")
    async def mkrshift_native_3d_assets(_request):  # pragma: no cover - integration surface
        try:
            return web.json_response(resolve_native_3d_assets())
        except FileNotFoundError as exc:
            return web.json_response({"error": str(exc)}, status=404)
