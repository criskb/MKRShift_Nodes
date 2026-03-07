import math
from typing import Optional, Tuple

import numpy as np
from PIL import Image
import torch

from .categories import UTILITY_RESIZE
from .xshared import to_image_batch as _to_image_batch


_ANCHOR_FACTORS = {
    "top_left": (0.0, 0.0),
    "top": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}


def _to_mask_batch(mask: Optional[torch.Tensor], batch: int) -> Optional[np.ndarray]:
    if mask is None:
        return None
    if not torch.is_tensor(mask):
        raise TypeError("mask input is not a torch tensor")

    m = mask.detach().float().cpu()
    if m.ndim == 2:
        m = m.unsqueeze(0)
    elif m.ndim == 4:
        if m.shape[-1] in (1, 3, 4):
            m = m[..., 0]
        elif m.shape[1] in (1, 3, 4):
            m = m[:, 0, ...]
        else:
            raise ValueError(f"Unsupported MASK shape={tuple(m.shape)}")
    elif m.ndim != 3:
        raise ValueError(f"Unsupported MASK dims={m.ndim}")

    if m.shape[0] == 1 and batch > 1:
        m = m.expand(batch, -1, -1)
    elif m.shape[0] != batch:
        raise ValueError(f"Mask batch {m.shape[0]} does not match image batch {batch}")

    return np.clip(m.numpy(), 0.0, 1.0).astype(np.float32, copy=False)


def _round_int(value: float, mode: str) -> int:
    v = float(value)
    if str(mode).lower() == "floor":
        return int(math.floor(v))
    if str(mode).lower() == "ceil":
        return int(math.ceil(v))
    return int(round(v))


def _align_dim(value: int, multiple: int, round_mode: str) -> int:
    base = max(1, int(value))
    m = max(1, int(multiple))
    if m <= 1:
        return base
    q = base / float(m)
    aligned = _round_int(q, round_mode) * m
    if aligned < 1:
        aligned = m
    return int(aligned)


def _resample_from_name(name: str) -> int:
    key = str(name).lower()
    table = {
        "nearest": Image.Resampling.NEAREST,
        "box": Image.Resampling.BOX,
        "bilinear": Image.Resampling.BILINEAR,
        "hamming": Image.Resampling.HAMMING,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }
    return int(table.get(key, Image.Resampling.BICUBIC))


def _anchor_offset(container_w: int, container_h: int, inner_w: int, inner_h: int, anchor: str) -> Tuple[int, int]:
    ax, ay = _ANCHOR_FACTORS.get(str(anchor).lower(), _ANCHOR_FACTORS["center"])
    max_x = max(0, int(container_w) - int(inner_w))
    max_y = max(0, int(container_h) - int(inner_h))
    dx = int(round(max_x * ax))
    dy = int(round(max_y * ay))
    return dx, dy


def _resize_with_mode(
    src: Image.Image,
    mode: str,
    out_w: int,
    out_h: int,
    allow_upscale: bool,
    round_mode: str,
    anchor: str,
    resample: int,
    pad_value,
) -> Image.Image:
    src_w, src_h = src.size
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))
    mode_key = str(mode).lower()

    if mode_key == "stretch":
        return src.resize((out_w, out_h), resample=resample)

    if mode_key in {"long_side", "short_side"}:
        return src.resize((out_w, out_h), resample=resample)

    fit_mode = mode_key == "fit"
    scale = min(out_w / float(src_w), out_h / float(src_h)) if fit_mode else max(out_w / float(src_w), out_h / float(src_h))
    if not allow_upscale:
        scale = min(scale, 1.0)
    rw = max(1, _round_int(src_w * scale, round_mode))
    rh = max(1, _round_int(src_h * scale, round_mode))
    resized = src.resize((rw, rh), resample=resample)

    # Fit is always letterboxed; fill_crop can fall back to letterbox when upscaling is disabled.
    if fit_mode or rw < out_w or rh < out_h:
        canvas = Image.new(src.mode, (out_w, out_h), color=pad_value)
        dx, dy = _anchor_offset(out_w, out_h, rw, rh, anchor)
        canvas.paste(resized, (dx, dy))
        return canvas

    left, top = _anchor_offset(rw, rh, out_w, out_h, anchor)
    return resized.crop((left, top, left + out_w, top + out_h))


class AdvResize:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["fit", "fill_crop", "stretch", "long_side", "short_side"],),
                "target_width": ("INT", {"default": 1024, "min": 1, "max": 32768, "step": 1}),
                "target_height": ("INT", {"default": 1024, "min": 1, "max": 32768, "step": 1}),
                "side_length": ("INT", {"default": 1024, "min": 1, "max": 32768, "step": 1}),
                "interpolation": (["lanczos", "bicubic", "bilinear", "hamming", "box", "nearest"],),
                "round_mode": (["round", "floor", "ceil"],),
                "align_to_multiple": ("INT", {"default": 1, "min": 1, "max": 512, "step": 1}),
                "anchor": (
                    [
                        "center",
                        "top_left",
                        "top",
                        "top_right",
                        "left",
                        "right",
                        "bottom_left",
                        "bottom",
                        "bottom_right",
                    ],
                ),
                "allow_upscale": ("BOOLEAN", {"default": True}),
                "pad_r": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "pad_g": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "pad_b": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "pad_a": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_pad_value": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "resize_info")
    FUNCTION = "run"
    CATEGORY = UTILITY_RESIZE

    def run(
        self,
        image: torch.Tensor,
        mode: str = "fit",
        target_width: int = 1024,
        target_height: int = 1024,
        side_length: int = 1024,
        interpolation: str = "lanczos",
        round_mode: str = "round",
        align_to_multiple: int = 1,
        anchor: str = "center",
        allow_upscale: bool = True,
        pad_r: float = 0.0,
        pad_g: float = 0.0,
        pad_b: float = 0.0,
        pad_a: float = 1.0,
        mask_pad_value: float = 0.0,
        mask: Optional[torch.Tensor] = None,
    ):
        batch = _to_image_batch(image)
        b, h, w, c = batch.shape
        src_cpu = batch.detach().cpu().numpy().astype(np.float32, copy=False)
        mask_batch = _to_mask_batch(mask, int(b))

        out_w = _align_dim(int(target_width), int(align_to_multiple), str(round_mode))
        out_h = _align_dim(int(target_height), int(align_to_multiple), str(round_mode))

        if str(mode).lower() in {"long_side", "short_side"}:
            basis = max(int(w), int(h)) if str(mode).lower() == "long_side" else min(int(w), int(h))
            scale = float(max(1, int(side_length))) / float(max(1, basis))
            if not bool(allow_upscale):
                scale = min(scale, 1.0)
            out_w = _align_dim(max(1, _round_int(int(w) * scale, str(round_mode))), int(align_to_multiple), str(round_mode))
            out_h = _align_dim(max(1, _round_int(int(h) * scale, str(round_mode))), int(align_to_multiple), str(round_mode))

        out_np = np.zeros((int(b), int(out_h), int(out_w), int(c)), dtype=np.float32)
        out_mask_np = np.zeros((int(b), int(out_h), int(out_w)), dtype=np.float32)

        img_resample = _resample_from_name(str(interpolation))
        mask_resample = Image.Resampling.BILINEAR if img_resample != Image.Resampling.NEAREST else Image.Resampling.NEAREST
        pad_rgb = (
            int(np.clip(pad_r, 0.0, 1.0) * 255.0),
            int(np.clip(pad_g, 0.0, 1.0) * 255.0),
            int(np.clip(pad_b, 0.0, 1.0) * 255.0),
        )
        pad_alpha = int(np.clip(pad_a, 0.0, 1.0) * 255.0)
        pad_mask_u8 = int(np.clip(mask_pad_value, 0.0, 1.0) * 255.0)

        for idx in range(int(b)):
            sample = np.clip(src_cpu[idx], 0.0, 1.0)
            if int(c) == 4:
                src_img = Image.fromarray((sample * 255.0).astype(np.uint8), mode="RGBA")
                pad_value = (pad_rgb[0], pad_rgb[1], pad_rgb[2], pad_alpha)
            else:
                src_img = Image.fromarray((sample * 255.0).astype(np.uint8), mode="RGB")
                pad_value = pad_rgb

            out_img = _resize_with_mode(
                src=src_img,
                mode=str(mode),
                out_w=int(out_w),
                out_h=int(out_h),
                allow_upscale=bool(allow_upscale),
                round_mode=str(round_mode),
                anchor=str(anchor),
                resample=int(img_resample),
                pad_value=pad_value,
            )
            out_np[idx] = np.asarray(out_img, dtype=np.float32) / 255.0

            if mask_batch is None:
                mask_src = np.ones((int(h), int(w)), dtype=np.float32)
            else:
                mask_src = np.clip(mask_batch[idx], 0.0, 1.0).astype(np.float32, copy=False)
            mask_img = Image.fromarray((mask_src * 255.0).astype(np.uint8), mode="L")
            out_mask_img = _resize_with_mode(
                src=mask_img,
                mode=str(mode),
                out_w=int(out_w),
                out_h=int(out_h),
                allow_upscale=bool(allow_upscale),
                round_mode=str(round_mode),
                anchor=str(anchor),
                resample=int(mask_resample),
                pad_value=pad_mask_u8,
            )
            out_mask_np[idx] = np.asarray(out_mask_img, dtype=np.float32) / 255.0

        out_t = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        out_mask_t = torch.from_numpy(np.clip(out_mask_np, 0.0, 1.0)).to(device=batch.device, dtype=batch.dtype)
        info = "AdvResize: mode={}, in={}x{}, out={}x{}, interpolation={}, anchor={}, align_to_multiple={}, allow_upscale={}".format(
            str(mode),
            int(w),
            int(h),
            int(out_w),
            int(out_h),
            str(interpolation).lower(),
            str(anchor).lower(),
            int(max(1, align_to_multiple)),
            bool(allow_upscale),
        )
        return (out_t.clamp(0.0, 1.0), out_mask_t.clamp(0.0, 1.0), info)
