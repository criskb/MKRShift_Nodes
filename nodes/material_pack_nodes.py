from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_MAPS
from ..lib.technical_art_shared import infer_reference_shape, mask_or_gray_input


_PACK_LAYOUTS: dict[str, tuple[str, ...]] = {
    "orm": ("ao", "roughness", "metalness"),
    "rma": ("roughness", "metalness", "ao"),
    "mra": ("metalness", "roughness", "ao"),
    "orma": ("ao", "roughness", "metalness", "alpha"),
}


def _semantic_source_label(name: str, source_label: str, roughness_source: str) -> str:
    if name == "roughness" and str(roughness_source).lower() == "glossiness":
        return f"{source_label}(gloss->roughness)"
    return source_label


class x1PBRPack:
    SEARCH_ALIASES = ["orm pack", "pbr pack", "rma pack", "mra pack", "packed material maps"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "layout": (["orm", "orma", "rma", "mra"],),
                "roughness_source": (["roughness", "glossiness"],),
                "fill_ao": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "fill_roughness": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "fill_metalness": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "fill_alpha": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
            },
            "optional": {
                "ao_image": ("IMAGE",),
                "roughness_image": ("IMAGE",),
                "metalness_image": ("IMAGE",),
                "alpha_image": ("IMAGE",),
                "ao_mask": ("MASK",),
                "roughness_mask": ("MASK",),
                "metalness_mask": ("MASK",),
                "alpha_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "packing_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_MAPS

    def run(
        self,
        layout: str = "orm",
        roughness_source: str = "roughness",
        fill_ao: float = 1.0,
        fill_roughness: float = 1.0,
        fill_metalness: float = 0.0,
        fill_alpha: float = 1.0,
        ao_image: Optional[torch.Tensor] = None,
        roughness_image: Optional[torch.Tensor] = None,
        metalness_image: Optional[torch.Tensor] = None,
        alpha_image: Optional[torch.Tensor] = None,
        ao_mask: Optional[torch.Tensor] = None,
        roughness_mask: Optional[torch.Tensor] = None,
        metalness_mask: Optional[torch.Tensor] = None,
        alpha_mask: Optional[torch.Tensor] = None,
    ):
        batch, h, w = infer_reference_shape(
            ao_image,
            roughness_image,
            metalness_image,
            alpha_image,
            ao_mask,
            roughness_mask,
            metalness_mask,
            alpha_mask,
        )

        layout_key = str(layout).lower()
        channel_order = _PACK_LAYOUTS.get(layout_key, _PACK_LAYOUTS["orm"])

        ao_np, ao_src = mask_or_gray_input(ao_image, ao_mask, batch=batch, h=h, w=w, fill_value=fill_ao)
        roughness_np, roughness_src = mask_or_gray_input(
            roughness_image,
            roughness_mask,
            batch=batch,
            h=h,
            w=w,
            fill_value=fill_roughness,
        )
        if str(roughness_source).lower() == "glossiness":
            roughness_np = (1.0 - np.clip(roughness_np, 0.0, 1.0)).astype(np.float32, copy=False)

        metalness_np, metalness_src = mask_or_gray_input(
            metalness_image,
            metalness_mask,
            batch=batch,
            h=h,
            w=w,
            fill_value=fill_metalness,
        )
        alpha_np, alpha_src = mask_or_gray_input(alpha_image, alpha_mask, batch=batch, h=h, w=w, fill_value=fill_alpha)

        semantic_channels = {
            "ao": ao_np,
            "roughness": roughness_np,
            "metalness": metalness_np,
            "alpha": alpha_np,
        }
        semantic_labels = {
            "ao": _semantic_source_label("ao", ao_src, roughness_source),
            "roughness": _semantic_source_label("roughness", roughness_src, roughness_source),
            "metalness": _semantic_source_label("metalness", metalness_src, roughness_source),
            "alpha": _semantic_source_label("alpha", alpha_src, roughness_source),
        }

        packed = np.stack([semantic_channels[name] for name in channel_order], axis=-1).astype(np.float32, copy=False)

        channel_labels = ["R", "G", "B", "A"]
        channel_summary = ", ".join(
            f"{channel_labels[idx]}:{name}({semantic_labels[name]})"
            for idx, name in enumerate(channel_order)
        )
        info = (
            "x1PBRPack: layout={}, channels=[{}], fills=[ao={:.3f}, roughness={:.3f}, metalness={:.3f}, alpha={:.3f}]"
        ).format(
            layout_key,
            channel_summary,
            float(np.clip(fill_ao, 0.0, 1.0)),
            float(np.clip(fill_roughness, 0.0, 1.0)),
            float(np.clip(fill_metalness, 0.0, 1.0)),
            float(np.clip(fill_alpha, 0.0, 1.0)),
        )
        return (torch.from_numpy(np.clip(packed, 0.0, 1.0)), info)
