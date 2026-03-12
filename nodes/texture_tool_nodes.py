from typing import Optional

import numpy as np
import torch

from ..categories import SURFACE_TEXTURE
from ..lib.image_shared import luma_np, to_image_batch
from ..lib.scalar_map_shared import mask_tensor_to_np
from ..lib.texture_shared import cross_seam_mask, edge_match_low_frequency, roll_image_np, smooth_seams, tile_grid_mask


def _to_tensor(image_np: np.ndarray, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    return torch.from_numpy(np.clip(image_np, 0.0, 1.0).astype(np.float32, copy=False)).to(device=device, dtype=dtype)


def _resolve_offset_pixels(h: int, w: int, mode: str, offset_x: float, offset_y: float) -> tuple[int, int]:
    resolved = str(mode).lower()
    if resolved == "half_tile":
        return int(h // 2), int(w // 2)
    if resolved == "pixels":
        return int(round(offset_y)), int(round(offset_x))
    return int(round(float(offset_y) * float(h))), int(round(float(offset_x) * float(w)))


def _offset_seam_mask(h: int, w: int, shift_y: int, shift_x: int, seam_width: float) -> np.ndarray:
    seam_x = None if int(shift_x) % max(1, int(w)) == 0 else float(int(shift_x) % int(w))
    seam_y = None if int(shift_y) % max(1, int(h)) == 0 else float(int(shift_y) % int(h))
    return cross_seam_mask(
        h=int(h),
        w=int(w),
        seam_x=seam_x,
        seam_y=seam_y,
        half_width=float(max(0.0, seam_width)),
        softness=float(max(0.0, seam_width) * 0.5),
    )


def _tile_image_np(image: np.ndarray, tiles_y: int, tiles_x: int) -> np.ndarray:
    reps = (int(max(1, tiles_y)), int(max(1, tiles_x)), 1) if image.ndim == 3 else (int(max(1, tiles_y)), int(max(1, tiles_x)))
    return np.tile(image, reps).astype(np.float32, copy=False)


def _overlay_seams(rgb: np.ndarray, seam_mask: np.ndarray, opacity: float) -> np.ndarray:
    op = float(np.clip(opacity, 0.0, 1.0))
    if op <= 1e-6:
        return rgb.astype(np.float32, copy=False)
    seam_color = np.asarray([1.0, 0.45, 0.10], dtype=np.float32)
    mix = np.clip(seam_mask, 0.0, 1.0)[..., None] * op
    return np.clip((rgb * (1.0 - mix)) + (seam_color[None, None, :] * mix), 0.0, 1.0).astype(np.float32, copy=False)


def _edge_pad_rgb(rgb: np.ndarray, valid_mask: np.ndarray, pad_pixels: int) -> tuple[np.ndarray, np.ndarray]:
    color = rgb.astype(np.float32, copy=True)
    valid = valid_mask.astype(bool, copy=True)
    initial_valid = valid.copy()

    for _ in range(int(max(0, pad_pixels))):
        if bool(np.all(valid)):
            break
        padded_valid = np.pad(valid, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        padded_color = np.pad(color, ((1, 1), (1, 1), (0, 0)), mode="constant", constant_values=0.0)

        accum = np.zeros_like(color, dtype=np.float32)
        count = np.zeros(valid.shape, dtype=np.float32)
        for dy in range(3):
            for dx in range(3):
                if dx == 1 and dy == 1:
                    continue
                neighbor_valid = padded_valid[dy : dy + valid.shape[0], dx : dx + valid.shape[1]]
                neighbor_color = padded_color[dy : dy + color.shape[0], dx : dx + color.shape[1], :]
                accum += neighbor_color * neighbor_valid[..., None]
                count += neighbor_valid.astype(np.float32)

        can_fill = (~valid) & (count > 0.0)
        if not bool(np.any(can_fill)):
            break
        fill = accum / np.maximum(count[..., None], 1e-6)
        color[can_fill] = fill[can_fill]
        valid[can_fill] = True

    fill_mask = np.clip(valid.astype(np.float32) - initial_valid.astype(np.float32), 0.0, 1.0)
    return color.astype(np.float32, copy=False), fill_mask.astype(np.float32, copy=False)


class x1TextureOffset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["half_tile", "fraction", "pixels"],),
                "offset_x": ("FLOAT", {"default": 0.5, "min": -4096.0, "max": 4096.0, "step": 0.01}),
                "offset_y": ("FLOAT", {"default": 0.5, "min": -4096.0, "max": 4096.0, "step": 0.01}),
                "seam_width": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 256.0, "step": 0.5}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "offset_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        mode: str = "half_tile",
        offset_x: float = 0.5,
        offset_y: float = 0.5,
        seam_width: float = 6.0,
    ):
        batch = to_image_batch(image)
        b, h, w, _ = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        shift_y, shift_x = _resolve_offset_pixels(int(h), int(w), mode, offset_x, offset_y)
        seam_mask = _offset_seam_mask(int(h), int(w), shift_y, shift_x, seam_width)

        for idx in range(int(b)):
            out_np[idx] = roll_image_np(src_np[idx], shift_y=shift_y, shift_x=shift_x)
            mask_np[idx] = seam_mask

        info = (
            "x1TextureOffset: mode={}, shift_x={}px, shift_y={}px, seam_width={:.1f}px"
        ).format(str(mode).lower(), int(shift_x), int(shift_y), float(max(0.0, seam_width)))
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureSeamless:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "blend_width": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 512.0, "step": 0.5}),
                "edge_match_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_match_blur": ("FLOAT", {"default": 18.0, "min": 0.0, "max": 256.0, "step": 0.5}),
                "detail_preserve": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seam_blur": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 256.0, "step": 0.5}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "seamless_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        blend_width: float = 24.0,
        edge_match_strength: float = 0.85,
        edge_match_blur: float = 18.0,
        detail_preserve: float = 0.65,
        seam_blur: float = 12.0,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)

        shift_y = int(h // 2)
        shift_x = int(w // 2)
        bw = float(max(1.0, blend_width))
        edge_band = max(1, int(round(bw)))
        seam_mask_center = cross_seam_mask(
            h=int(h),
            w=int(w),
            seam_x=float(shift_x),
            seam_y=float(shift_y),
            half_width=bw,
            softness=max(1.0, bw * 0.5),
        )
        seam_mask_output = roll_image_np(seam_mask_center, shift_y=-shift_y, shift_x=-shift_x)

        for idx in range(int(b)):
            sample = src_np[idx]
            rgb = edge_match_low_frequency(
                image=sample[..., :3],
                blur_radius=float(max(0.0, edge_match_blur)),
                edge_band=edge_band,
                strength=float(np.clip(edge_match_strength, 0.0, 1.0)),
            )
            rgb = roll_image_np(rgb, shift_y=shift_y, shift_x=shift_x)
            rgb = smooth_seams(
                image=rgb,
                seam_mask=seam_mask_center,
                blur_radius=float(max(0.0, seam_blur)),
                detail_preserve=float(np.clip(detail_preserve, 0.0, 1.0)),
            )
            rgb = roll_image_np(rgb, shift_y=-shift_y, shift_x=-shift_x)

            if c == 4:
                alpha = edge_match_low_frequency(
                    image=sample[..., 3],
                    blur_radius=float(max(0.0, edge_match_blur)),
                    edge_band=edge_band,
                    strength=float(np.clip(edge_match_strength, 0.0, 1.0)),
                )
                alpha = roll_image_np(alpha, shift_y=shift_y, shift_x=shift_x)
                alpha = smooth_seams(
                    image=alpha,
                    seam_mask=seam_mask_center,
                    blur_radius=float(max(0.0, seam_blur)),
                    detail_preserve=float(np.clip(detail_preserve, 0.0, 1.0)),
                )
                alpha = roll_image_np(alpha, shift_y=-shift_y, shift_x=-shift_x)
                out_np[idx] = np.concatenate([rgb, alpha[..., None]], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = rgb
            mask_np[idx] = seam_mask_output

        info = (
            "x1TextureSeamless: blend_width={:.1f}px, edge_match_strength={:.2f}, edge_match_blur={:.1f}px, "
            "detail_preserve={:.2f}, seam_blur={:.1f}px"
        ).format(
            bw,
            float(np.clip(edge_match_strength, 0.0, 1.0)),
            float(max(0.0, edge_match_blur)),
            float(np.clip(detail_preserve, 0.0, 1.0)),
            float(max(0.0, seam_blur)),
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureTilePreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "tiles_x": ("INT", {"default": 3, "min": 1, "max": 8, "step": 1}),
                "tiles_y": ("INT", {"default": 3, "min": 1, "max": 8, "step": 1}),
                "show_seams": ("BOOLEAN", {"default": True}),
                "seam_width": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 32.0, "step": 0.5}),
                "seam_opacity": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "tile_preview_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        tiles_x: int = 3,
        tiles_y: int = 3,
        show_seams: bool = True,
        seam_width: float = 2.0,
        seam_opacity: float = 0.65,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)

        out_samples: list[np.ndarray] = []
        mask_samples: list[np.ndarray] = []
        tiled_h = int(h) * int(max(1, tiles_y))
        tiled_w = int(w) * int(max(1, tiles_x))
        seam_mask = tile_grid_mask(
            h=tiled_h,
            w=tiled_w,
            tiles_y=int(max(1, tiles_y)),
            tiles_x=int(max(1, tiles_x)),
            half_width=float(max(0.0, seam_width)),
            softness=max(0.5, float(max(0.0, seam_width)) * 0.5),
        )

        for idx in range(int(b)):
            tiled = _tile_image_np(src_np[idx], tiles_y=int(tiles_y), tiles_x=int(tiles_x))
            if bool(show_seams):
                rgb = _overlay_seams(tiled[..., :3], seam_mask=seam_mask, opacity=seam_opacity)
                if c == 4:
                    tiled = np.concatenate([rgb, tiled[..., 3:4]], axis=-1).astype(np.float32, copy=False)
                else:
                    tiled = rgb
            out_samples.append(tiled.astype(np.float32, copy=False))
            mask_samples.append(seam_mask.astype(np.float32, copy=False))

        out_np = np.stack(out_samples, axis=0).astype(np.float32, copy=False)
        mask_np = np.stack(mask_samples, axis=0).astype(np.float32, copy=False)
        info = (
            "x1TextureTilePreview: tiles_x={}, tiles_y={}, seam_width={:.1f}px, show_seams={}, seam_opacity={:.2f}"
        ).format(
            int(max(1, tiles_x)),
            int(max(1, tiles_y)),
            float(max(0.0, seam_width)),
            bool(show_seams),
            float(np.clip(seam_opacity, 0.0, 1.0)),
        )
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )


class x1TextureEdgePad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_mode": (["alpha", "mask", "luma_nonzero"],),
                "pad_pixels": ("INT", {"default": 16, "min": 1, "max": 512, "step": 1}),
                "alpha_threshold": ("FLOAT", {"default": 0.01, "min": 0.0, "max": 1.0, "step": 0.001}),
                "expand_alpha": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "source_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "edge_pad_info")
    FUNCTION = "run"
    CATEGORY = SURFACE_TEXTURE

    def run(
        self,
        image: torch.Tensor,
        source_mode: str = "alpha",
        pad_pixels: int = 16,
        alpha_threshold: float = 0.01,
        expand_alpha: bool = False,
        source_mask: Optional[torch.Tensor] = None,
    ):
        batch = to_image_batch(image)
        b, h, w, c = batch.shape
        src_np = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        out_np = np.empty_like(src_np)
        fill_mask_np = np.zeros((int(b), int(h), int(w)), dtype=np.float32)
        source_mask_np = mask_tensor_to_np(source_mask, int(b), int(h), int(w)) if torch.is_tensor(source_mask) else None
        threshold = float(np.clip(alpha_threshold, 0.0, 1.0))

        resolved_source = str(source_mode).lower()
        for idx in range(int(b)):
            sample = src_np[idx]
            rgb = sample[..., :3]
            if resolved_source == "mask" and source_mask_np is not None:
                valid = source_mask_np[idx] > threshold
                resolved = "mask"
            elif resolved_source == "alpha" and c == 4:
                valid = sample[..., 3] > threshold
                resolved = "alpha"
            else:
                valid = luma_np(rgb) > threshold
                resolved = "luma_nonzero"

            padded_rgb, fill_mask = _edge_pad_rgb(rgb, valid, int(max(1, pad_pixels)))
            fill_mask_np[idx] = fill_mask

            if c == 4:
                alpha = sample[..., 3:4]
                if bool(expand_alpha):
                    alpha = np.maximum(alpha, fill_mask[..., None]).astype(np.float32, copy=False)
                out_np[idx] = np.concatenate([padded_rgb, alpha], axis=-1).astype(np.float32, copy=False)
            else:
                out_np[idx] = padded_rgb
            resolved_source = resolved

        info = (
            "x1TextureEdgePad: source_mode={}, pad_pixels={}, alpha_threshold={:.3f}, expand_alpha={}"
        ).format(resolved_source, int(max(1, pad_pixels)), threshold, bool(expand_alpha))
        return (
            _to_tensor(out_np, device=batch.device, dtype=batch.dtype),
            torch.from_numpy(fill_mask_np).to(device=batch.device, dtype=batch.dtype),
            info,
        )
