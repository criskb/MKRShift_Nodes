from __future__ import annotations

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
ADDON_DIR = ROOT / "mkrshift_blender_bridge"
DIST_DIR = ROOT / "dist"
ZIP_PATH = DIST_DIR / "mkrshift_blender_bridge.zip"


def should_include(path: Path) -> bool:
    parts = path.parts
    if "__pycache__" in parts:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return path.is_file()


def build_zip() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ADDON_DIR.rglob("*")):
            if not should_include(path):
                continue
            archive.write(path, path.relative_to(ROOT))
    return ZIP_PATH


if __name__ == "__main__":
    zip_path = build_zip()
    print(zip_path)
