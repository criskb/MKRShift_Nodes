from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
import torch


def to_image_batch(image: torch.Tensor) -> torch.Tensor:
    if not torch.is_tensor(image):
        raise TypeError("image input is not a torch tensor")
    t = image.detach().float()
    if t.ndim == 3:
        t = t.unsqueeze(0)
    if t.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got shape={tuple(t.shape)}")
    if t.shape[-1] not in (3, 4):
        raise ValueError(f"Expected channels=3 or 4, got shape={tuple(t.shape)}")
    return t.clamp(0.0, 1.0)


def mask_to_batch(
    mask: Optional[torch.Tensor],
    batch: int,
    h: int,
    w: int,
    feather_radius: float,
    invert_mask: bool,
    device: torch.device,
    dtype: torch.dtype = torch.float32,
) -> torch.Tensor:
    if mask is None:
        out = torch.ones((batch, h, w), dtype=dtype)
        return out.to(device=device)

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

    out_np = np.zeros((batch, h, w), dtype=np.float32)
    feather = float(max(0.0, feather_radius))
    for idx in range(batch):
        sample = np.clip(m[idx].numpy(), 0.0, 1.0)
        pil = Image.fromarray((sample * 255.0).astype(np.uint8), mode="L")
        if pil.size != (w, h):
            pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
        if feather > 1e-6:
            pil = pil.filter(ImageFilter.GaussianBlur(radius=feather))
        out_np[idx] = np.asarray(pil, dtype=np.float32) / 255.0

    out = torch.from_numpy(np.clip(out_np, 0.0, 1.0)).to(device=device, dtype=dtype)
    if invert_mask:
        out = 1.0 - out
    return out


def smoothstep_np(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= edge1).astype(np.float32)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32, copy=False)


def luma_np(rgb: np.ndarray) -> np.ndarray:
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32, copy=False)


def resize_rgb_np(rgb: np.ndarray, h: int, w: int) -> np.ndarray:
    if rgb.shape[0] == h and rgb.shape[1] == w:
        return rgb.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    pil = pil.resize((w, h), resample=Image.Resampling.BILINEAR)
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def gaussian_blur_rgb_np(rgb: np.ndarray, radius: float) -> np.ndarray:
    r = float(max(0.0, radius))
    if r <= 1e-6:
        return rgb.astype(np.float32, copy=False)
    pil = Image.fromarray(np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8), mode="RGB")
    pil = pil.filter(ImageFilter.GaussianBlur(radius=r))
    return (np.asarray(pil, dtype=np.float32) / 255.0).astype(np.float32, copy=False)


def rgb_to_hsv_np(rgb: np.ndarray):
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    h = np.zeros_like(maxc, dtype=np.float32)
    s = np.where(maxc > 1e-8, delta / np.maximum(maxc, 1e-8), 0.0).astype(np.float32, copy=False)
    v = maxc.astype(np.float32, copy=False)

    mask = delta > 1e-8
    rmax = (maxc == r) & mask
    gmax = (maxc == g) & mask
    bmax = (maxc == b) & mask

    h[rmax] = ((g[rmax] - b[rmax]) / delta[rmax]) % 6.0
    h[gmax] = ((b[gmax] - r[gmax]) / delta[gmax]) + 2.0
    h[bmax] = ((r[bmax] - g[bmax]) / delta[bmax]) + 4.0
    h = (h / 6.0) % 1.0
    return h.astype(np.float32, copy=False), s, v


def hsv_to_rgb_np(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    h = np.mod(h, 1.0).astype(np.float32, copy=False)
    s = np.clip(s, 0.0, 1.0).astype(np.float32, copy=False)
    v = np.clip(v, 0.0, 1.0).astype(np.float32, copy=False)

    i = np.floor(h * 6.0).astype(np.int32)
    f = (h * 6.0) - i
    i = i % 6

    p = v * (1.0 - s)
    q = v * (1.0 - (f * s))
    t = v * (1.0 - ((1.0 - f) * s))

    out = np.zeros(h.shape + (3,), dtype=np.float32)
    idx = i == 0
    out[idx] = np.stack([v[idx], t[idx], p[idx]], axis=-1)
    idx = i == 1
    out[idx] = np.stack([q[idx], v[idx], p[idx]], axis=-1)
    idx = i == 2
    out[idx] = np.stack([p[idx], v[idx], t[idx]], axis=-1)
    idx = i == 3
    out[idx] = np.stack([p[idx], q[idx], v[idx]], axis=-1)
    idx = i == 4
    out[idx] = np.stack([t[idx], p[idx], v[idx]], axis=-1)
    idx = i == 5
    out[idx] = np.stack([v[idx], p[idx], q[idx]], axis=-1)
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)
