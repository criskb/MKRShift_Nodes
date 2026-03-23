import os
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_ROOT = REPO_ROOT / "plugins"
ADDONS_ROOT = REPO_ROOT / "addons"
BLENDER_ZIP = REPO_ROOT / "blender_extension" / "dist" / "mkrshift_blender_bridge.zip"


def default_target(host: str) -> str:
    home = Path.home()
    system = sys.platform
    if host == "touchdesigner":
        return str(home / "Documents" / "Derivative" / "Palette")
    if host == "tixl":
        return str(home / "Documents" / "TiXL" / "Plugins")
    if host == "nuke":
        return str(home / ".nuke")
    if host == "photoshop":
        if system == "darwin":
            return str(home / "Library" / "Application Support" / "Adobe" / "UXP" / "Plugins" / "External")
        return str(home / "AppData" / "Roaming" / "Adobe" / "UXP" / "Plugins" / "External")
    if host == "after_effects":
        if system == "darwin":
            return str(home / "Documents" / "Adobe Scripts" / "ScriptUI Panels")
        return str(home / "Documents" / "Adobe" / "Scripts" / "ScriptUI Panels")
    if host == "premiere_pro":
        if system == "darwin":
            return str(home / "Library" / "Application Support" / "Adobe" / "UXP" / "Plugins" / "External")
        return str(home / "AppData" / "Roaming" / "Adobe" / "UXP" / "Plugins" / "External")
    if host == "affinity":
        return str(home / "Library" / "Application Support" / "Affinity" if system == "darwin" else home / "AppData" / "Roaming" / "Affinity")
    if host == "fusion360":
        if system == "darwin":
            return str(home / "Library" / "Application Support" / "Autodesk" / "Autodesk Fusion 360" / "API" / "AddIns")
        return str(home / "AppData" / "Roaming" / "Autodesk" / "Autodesk Fusion 360" / "API" / "AddIns")
    if host == "maya":
        return str(home / "Documents" / "maya")
    if host == "blender":
        return str(home / "Downloads")
    return str(home)


HOSTS = {
    "blender": {"source_type": "zip", "source": BLENDER_ZIP, "folder_name": "mkrshift_blender_bridge"},
    "touchdesigner": {"source_type": "dir", "source": PLUGINS_ROOT / "touchdesigner", "folder_name": "mkrshift_touchdesigner_bridge"},
    "tixl": {"source_type": "dir", "source": PLUGINS_ROOT / "tixl", "folder_name": "mkrshift_tixl_bridge"},
    "nuke": {"source_type": "dir", "source": PLUGINS_ROOT / "nuke", "folder_name": "mkrshift_nuke_bridge"},
    "photoshop": {"source_type": "dir", "source": PLUGINS_ROOT / "photoshop", "folder_name": "mkrshift_photoshop_bridge"},
    "after_effects": {"source_type": "dir", "source": PLUGINS_ROOT / "after_effects", "folder_name": "mkrshift_after_effects_bridge"},
    "premiere_pro": {"source_type": "dir", "source": PLUGINS_ROOT / "premiere_pro", "folder_name": "mkrshift_premiere_bridge"},
    "affinity": {"source_type": "dir", "source": PLUGINS_ROOT / "affinity", "folder_name": "mkrshift_affinity_bridge"},
    "fusion360": {"source_type": "dir", "source": PLUGINS_ROOT / "fusion360", "folder_name": "mkrshift_fusion360_bridge"},
    "maya": {"source_type": "dir", "source": PLUGINS_ROOT / "maya", "folder_name": "mkrshift_maya_bridge"},
}


def install_host(host: str, target_dir: Path) -> str:
    spec = HOSTS[host]
    source = spec["source"]
    target_dir.mkdir(parents=True, exist_ok=True)
    if spec["source_type"] == "zip":
        if not source.is_file():
            raise FileNotFoundError(f"Missing Blender zip: {source}")
        dest = target_dir / source.name
        shutil.copy2(source, dest)
        return str(dest)
    dest = target_dir / spec["folder_name"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    return str(dest)


class InstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MKRShift Plugin Installer")
        self.rows = {}
        tk.Label(root, text="Select plugins to install and confirm the destination folder for each host.").grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 8))
        for row_idx, host in enumerate(HOSTS.keys(), start=1):
            enabled = tk.BooleanVar(value=host in {"touchdesigner", "tixl", "nuke", "photoshop"})
            path_var = tk.StringVar(value=default_target(host))
            tk.Checkbutton(root, text=host.replace("_", " ").title(), variable=enabled).grid(row=row_idx, column=0, sticky="w", padx=10, pady=4)
            tk.Entry(root, textvariable=path_var, width=70).grid(row=row_idx, column=1, sticky="ew", padx=6)
            tk.Button(root, text="Browse", command=lambda var=path_var: self.browse(var)).grid(row=row_idx, column=2, padx=4)
            self.rows[host] = (enabled, path_var)
        tk.Button(root, text="Install Selected", command=self.install).grid(row=len(HOSTS) + 1, column=0, columnspan=3, pady=12)
        root.grid_columnconfigure(1, weight=1)

    def browse(self, path_var: tk.StringVar):
        chosen = filedialog.askdirectory(initialdir=path_var.get() or str(Path.home()))
        if chosen:
            path_var.set(chosen)

    def install(self):
        installed = []
        for host, (enabled, path_var) in self.rows.items():
            if not enabled.get():
                continue
            target = Path(path_var.get()).expanduser()
            result = install_host(host, target)
            installed.append(f"{host}: {result}")
        if not installed:
            messagebox.showinfo("MKRShift Plugin Installer", "No plugins selected.")
            return
        messagebox.showinfo("MKRShift Plugin Installer", "Installed:\n\n" + "\n".join(installed))


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
