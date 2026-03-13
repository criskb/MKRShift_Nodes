from __future__ import annotations

from typing import Optional

import torch

from ..categories import SURFACE_PREVIEW
from ..lib import native_3d_bridge as _native_3d_bridge  # noqa: F401
from ..lib.material_preview_export import export_material_preview_asset


class x1PreviewMaterial:
    SEARCH_ALIASES = ["material preview", "pbr preview", "shader ball", "3d material preview", "preview material"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preview_mesh": (["shader_ball", "plane", "cube"],),
                "uv_scale": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 32.0, "step": 0.01}),
                "roughness_default": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "metalness_default": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "normal_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0, "step": 0.01}),
                "normal_convention": (["directx", "opengl"],),
                "height_to_normal_strength": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 64.0, "step": 0.1}),
                "emissive_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0, "step": 0.01}),
                "alpha_mode": (["auto", "blend", "mask"],),
                "asset_label": ("STRING", {"default": "material_preview"}),
                "advanced_settings_json": ("STRING", {"default": "", "multiline": True}),
                "model_file": ("STRING", {"default": ""}),
            },
            "optional": {
                "base_color": ("IMAGE",),
                "normal": ("IMAGE",),
                "roughness": ("IMAGE",),
                "metalness": ("IMAGE",),
                "specular": ("IMAGE",),
                "height": ("IMAGE",),
                "ao": ("IMAGE",),
                "opacity": ("IMAGE",),
                "emissive": ("IMAGE",),
                "clearcoat": ("IMAGE",),
                "clearcoat_roughness": ("IMAGE",),
                "anisotropy": ("IMAGE",),
                "sheen_color": ("IMAGE",),
                "sheen_roughness": ("IMAGE",),
                "transmission": ("IMAGE",),
                "thickness": ("IMAGE",),
                "iridescence": ("IMAGE",),
                "iridescence_thickness": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("model_file", "preview_info")
    FUNCTION = "build"
    CATEGORY = SURFACE_PREVIEW

    def build(
        self,
        preview_mesh: str = "shader_ball",
        uv_scale: float = 1.0,
        roughness_default: float = 0.55,
        metalness_default: float = 0.0,
        normal_strength: float = 1.0,
        normal_convention: str = "directx",
        height_to_normal_strength: float = 6.0,
        emissive_strength: float = 1.0,
        alpha_mode: str = "auto",
        asset_label: str = "material_preview",
        advanced_settings_json: str = "",
        model_file: str = "",
        base_color: Optional[torch.Tensor] = None,
        normal: Optional[torch.Tensor] = None,
        roughness: Optional[torch.Tensor] = None,
        metalness: Optional[torch.Tensor] = None,
        specular: Optional[torch.Tensor] = None,
        height: Optional[torch.Tensor] = None,
        ao: Optional[torch.Tensor] = None,
        opacity: Optional[torch.Tensor] = None,
        emissive: Optional[torch.Tensor] = None,
        clearcoat: Optional[torch.Tensor] = None,
        clearcoat_roughness: Optional[torch.Tensor] = None,
        anisotropy: Optional[torch.Tensor] = None,
        sheen_color: Optional[torch.Tensor] = None,
        sheen_roughness: Optional[torch.Tensor] = None,
        transmission: Optional[torch.Tensor] = None,
        thickness: Optional[torch.Tensor] = None,
        iridescence: Optional[torch.Tensor] = None,
        iridescence_thickness: Optional[torch.Tensor] = None,
    ):
        result = export_material_preview_asset(
            preview_mesh=preview_mesh,
            uv_scale=uv_scale,
            asset_label=asset_label,
            roughness_default=roughness_default,
            metalness_default=metalness_default,
            normal_strength=normal_strength,
            normal_convention=normal_convention,
            height_to_normal_strength=height_to_normal_strength,
            emissive_strength=emissive_strength,
            alpha_mode=alpha_mode,
            advanced_settings_json=advanced_settings_json,
            base_color=base_color,
            normal=normal,
            roughness=roughness,
            metalness=metalness,
            specular=specular,
            height=height,
            ao=ao,
            opacity=opacity,
            emissive=emissive,
            clearcoat=clearcoat,
            clearcoat_roughness=clearcoat_roughness,
            anisotropy=anisotropy,
            sheen_color=sheen_color,
            sheen_roughness=sheen_roughness,
            transmission=transmission,
            thickness=thickness,
            iridescence=iridescence,
            iridescence_thickness=iridescence_thickness,
        )
        return (str(result["model_file"]), str(result["info"]))
