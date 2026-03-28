from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import torch

from ..categories import FX_COMPOSITE
from ..lib.layer_stack_shared import composite_single_layer, fit_image_batch_to_rgba, fit_optional_mask
from ..lib.image_shared import to_image_batch


LAYER_BLEND_MODES = ["normal", "screen", "multiply", "overlay", "soft_light", "add", "lighten", "darken"]
LAYER_RESIZE_MODES = ["stretch", "contain", "cover"]


class MKRLayerStackComposite:
    SEARCH_ALIASES = [
        "layer stack composite",
        "image layer blend",
        "masked image layer stack",
        "image over image with mask",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_image": ("IMAGE",),
                "layer_1": ("IMAGE",),
                "layer_1_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "layer_1_blend_mode": (LAYER_BLEND_MODES, {"default": "normal"}),
                "resize_mode": (LAYER_RESIZE_MODES, {"default": "stretch"}),
            },
            "optional": {
                "layer_1_mask": ("MASK",),
                "layer_2": ("IMAGE",),
                "layer_2_mask": ("MASK",),
                "layer_2_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "layer_2_blend_mode": (LAYER_BLEND_MODES, {"default": "normal"}),
                "layer_3": ("IMAGE",),
                "layer_3_mask": ("MASK",),
                "layer_3_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "layer_3_blend_mode": (LAYER_BLEND_MODES, {"default": "normal"}),
                "layer_4": ("IMAGE",),
                "layer_4_mask": ("MASK",),
                "layer_4_opacity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "layer_4_blend_mode": (LAYER_BLEND_MODES, {"default": "normal"}),
                "mask_feather": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 128.0, "step": 0.5}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "combined_mask", "layer_info")
    FUNCTION = "composite"
    CATEGORY = FX_COMPOSITE

    def composite(
        self,
        base_image: torch.Tensor,
        layer_1: torch.Tensor,
        layer_1_opacity: float = 1.0,
        layer_1_blend_mode: str = "normal",
        resize_mode: str = "stretch",
        layer_1_mask: Optional[torch.Tensor] = None,
        layer_2: Optional[torch.Tensor] = None,
        layer_2_mask: Optional[torch.Tensor] = None,
        layer_2_opacity: float = 1.0,
        layer_2_blend_mode: str = "normal",
        layer_3: Optional[torch.Tensor] = None,
        layer_3_mask: Optional[torch.Tensor] = None,
        layer_3_opacity: float = 1.0,
        layer_3_blend_mode: str = "normal",
        layer_4: Optional[torch.Tensor] = None,
        layer_4_mask: Optional[torch.Tensor] = None,
        layer_4_opacity: float = 1.0,
        layer_4_blend_mode: str = "normal",
        mask_feather: float = 0.0,
    ) -> Tuple[torch.Tensor, torch.Tensor, str]:
        base_batch = to_image_batch(base_image)
        batch, height, width, channels = base_batch.shape
        device = base_batch.device
        dtype = base_batch.dtype

        base_rgba = fit_image_batch_to_rgba(base_image, int(batch), int(height), int(width), "stretch")
        output_rgb = base_rgba[..., :3].copy()
        combined_mask = np.zeros((int(batch), int(height), int(width)), dtype=np.float32)

        layer_specs = [
            (layer_1, layer_1_mask, layer_1_opacity, layer_1_blend_mode, "Layer 1"),
            (layer_2, layer_2_mask, layer_2_opacity, layer_2_blend_mode, "Layer 2"),
            (layer_3, layer_3_mask, layer_3_opacity, layer_3_blend_mode, "Layer 3"),
            (layer_4, layer_4_mask, layer_4_opacity, layer_4_blend_mode, "Layer 4"),
        ]

        applied = []
        feather_value = float(max(0.0, mask_feather))

        for image_tensor, mask_tensor, opacity, blend_mode, label in layer_specs:
            if image_tensor is None:
                continue
            layer_rgba = fit_image_batch_to_rgba(image_tensor, int(batch), int(height), int(width), resize_mode)
            extra_mask = fit_optional_mask(mask_tensor, int(batch), int(height), int(width), feather_value, device, dtype)

            next_rgb = np.empty_like(output_rgb)
            layer_alpha = np.zeros((int(batch), int(height), int(width)), dtype=np.float32)
            for idx in range(int(batch)):
                next_rgb[idx], layer_alpha[idx] = composite_single_layer(
                    base_rgb=output_rgb[idx],
                    layer_rgba=layer_rgba[idx],
                    extra_mask=None if extra_mask is None else extra_mask[idx],
                    opacity=float(opacity),
                    blend_mode=str(blend_mode),
                )

            output_rgb = next_rgb
            combined_mask = np.clip(np.maximum(combined_mask, layer_alpha), 0.0, 1.0).astype(np.float32, copy=False)
            applied.append(f"{label}: mode={blend_mode}, opacity={float(opacity):.2f}")

        alpha = base_batch[..., 3:4] if channels == 4 else None
        out_tensor = torch.from_numpy(np.clip(output_rgb, 0.0, 1.0)).to(device=device, dtype=dtype)
        if alpha is not None:
            out_tensor = torch.cat((out_tensor, alpha), dim=-1)

        mask_tensor = torch.from_numpy(combined_mask).to(device=device, dtype=dtype)
        info = (
            f"MKRLayerStackComposite: layers={len(applied)}, resize_mode={resize_mode}, "
            f"mask_feather={feather_value:.1f}px"
        )
        if applied:
            info = f"{info} | " + " | ".join(applied)
        return out_tensor.clamp(0.0, 1.0), mask_tensor.clamp(0.0, 1.0), info
