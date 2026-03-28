import math

import numpy as np

from .image_shared import smoothstep_np


def _resolve_cells(length: int, scale_px: float) -> int:
    resolved_scale = float(max(1.0, scale_px))
    return int(max(2, math.ceil(float(length) / resolved_scale)))


def _wrapped_value_noise(h: int, w: int, cell_scale_px: float, seed: int) -> np.ndarray:
    cells_y = _resolve_cells(int(h), float(cell_scale_px))
    cells_x = _resolve_cells(int(w), float(cell_scale_px))
    rng = np.random.default_rng(int(seed))
    grid = rng.uniform(0.0, 1.0, size=(cells_y, cells_x)).astype(np.float32, copy=False)

    ys = (np.arange(int(h), dtype=np.float32) * float(cells_y)) / float(max(1, int(h)))
    xs = (np.arange(int(w), dtype=np.float32) * float(cells_x)) / float(max(1, int(w)))
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = (y0 + 1) % cells_y
    x1 = (x0 + 1) % cells_x
    fy = (ys - y0).astype(np.float32, copy=False)[:, None]
    fx = (xs - x0).astype(np.float32, copy=False)[None, :]

    g00 = grid[y0[:, None], x0[None, :]]
    g10 = grid[y1[:, None], x0[None, :]]
    g01 = grid[y0[:, None], x1[None, :]]
    g11 = grid[y1[:, None], x1[None, :]]

    a = (g00 * (1.0 - fx)) + (g01 * fx)
    b = (g10 * (1.0 - fx)) + (g11 * fx)
    return _enforce_tile_edges(((a * (1.0 - fy)) + (b * fy)).astype(np.float32, copy=False))


def _enforce_tile_edges(field: np.ndarray) -> np.ndarray:
    out = field.astype(np.float32, copy=True)
    if out.shape[0] > 1:
        out[-1, :] = out[0, :]
    if out.shape[1] > 1:
        out[:, -1] = out[:, 0]
    return out.astype(np.float32, copy=False)


def procedural_noise_field(
    h: int,
    w: int,
    scale_px: float,
    octaves: int,
    lacunarity: float,
    gain: float,
    seed: int,
    variant: str = "fbm",
) -> np.ndarray:
    resolved_variant = str(variant).lower()
    if resolved_variant == "value":
        return _wrapped_value_noise(int(h), int(w), float(scale_px), int(seed))

    out = np.zeros((int(h), int(w)), dtype=np.float32)
    weight = 1.0
    total_weight = 0.0
    freq_scale = float(max(1.0, scale_px))
    resolved_octaves = int(max(1, octaves))
    resolved_lacunarity = float(max(1.1, lacunarity))
    resolved_gain = float(np.clip(gain, 0.01, 1.0))

    for octave in range(resolved_octaves):
        layer = _wrapped_value_noise(
            int(h),
            int(w),
            cell_scale_px=max(1.0, freq_scale),
            seed=int(seed) + (octave * 173),
        )
        if resolved_variant == "turbulence":
            layer = np.abs((layer * 2.0) - 1.0).astype(np.float32, copy=False)
        elif resolved_variant == "ridged":
            layer = (1.0 - np.abs((layer * 2.0) - 1.0)).astype(np.float32, copy=False)
        out += layer * weight
        total_weight += weight
        weight *= resolved_gain
        freq_scale /= resolved_lacunarity

    if total_weight <= 1e-6:
        return np.zeros((int(h), int(w)), dtype=np.float32)
    return _enforce_tile_edges(np.clip(out / total_weight, 0.0, 1.0).astype(np.float32, copy=False))


def shape_scalar_field(field: np.ndarray, contrast: float = 1.0, balance: float = 0.0, invert: bool = False) -> np.ndarray:
    out = np.clip(field, 0.0, 1.0).astype(np.float32, copy=False)
    out = np.clip(((out - 0.5) * float(max(0.01, contrast))) + 0.5 + (float(np.clip(balance, -1.0, 1.0)) * 0.5), 0.0, 1.0)
    if bool(invert):
        out = 1.0 - out
    return out.astype(np.float32, copy=False)


def grayscale_to_rgb(field: np.ndarray) -> np.ndarray:
    clipped = np.clip(field, 0.0, 1.0).astype(np.float32, copy=False)
    return np.repeat(clipped[..., None], 3, axis=-1).astype(np.float32, copy=False)


def procedural_cell_pattern(
    h: int,
    w: int,
    cell_scale_px: float,
    jitter: float,
    edge_width: float,
    seed: int,
    pattern_mode: str = "fill",
) -> np.ndarray:
    cells_y = _resolve_cells(int(h), float(cell_scale_px))
    cells_x = _resolve_cells(int(w), float(cell_scale_px))
    rng = np.random.default_rng(int(seed))
    jitter_span = float(np.clip(jitter, 0.0, 1.0)) * 0.45
    offset_y = (0.5 + rng.uniform(-jitter_span, jitter_span, size=(cells_y, cells_x))).astype(np.float32, copy=False)
    offset_x = (0.5 + rng.uniform(-jitter_span, jitter_span, size=(cells_y, cells_x))).astype(np.float32, copy=False)
    cell_values = rng.uniform(0.0, 1.0, size=(cells_y, cells_x)).astype(np.float32, copy=False)

    py = (((np.arange(int(h), dtype=np.float32) + 0.5) * float(cells_y)) / float(max(1, int(h)))) - 0.5
    px = (((np.arange(int(w), dtype=np.float32) + 0.5) * float(cells_x)) / float(max(1, int(w)))) - 0.5
    py_grid, px_grid = np.meshgrid(py, px, indexing="ij")
    base_y = np.floor(py_grid).astype(np.int32)
    base_x = np.floor(px_grid).astype(np.int32)
    base_yf = base_y.astype(np.float32, copy=False)
    base_xf = base_x.astype(np.float32, copy=False)

    f1 = np.full((int(h), int(w)), np.inf, dtype=np.float32)
    f2 = np.full((int(h), int(w)), np.inf, dtype=np.float32)
    nearest_value = np.zeros((int(h), int(w)), dtype=np.float32)

    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            idx_y = (base_y + dy) % cells_y
            idx_x = (base_x + dx) % cells_x
            feat_y = (base_yf + float(dy)) + offset_y[idx_y, idx_x]
            feat_x = (base_xf + float(dx)) + offset_x[idx_y, idx_x]
            dist = np.sqrt(((feat_y - py_grid) ** 2) + ((feat_x - px_grid) ** 2)).astype(np.float32, copy=False)

            replace_primary = dist < f1
            f2 = np.where(replace_primary, f1, np.minimum(f2, dist))
            f1 = np.where(replace_primary, dist, f1)
            nearest_value = np.where(replace_primary, cell_values[idx_y, idx_x], nearest_value)

            replace_secondary = (~replace_primary) & (dist < f2)
            f2 = np.where(replace_secondary, dist, f2)

    norm = float(max(np.percentile(f1, 98.0), 1e-4))
    distance_field = np.clip(1.0 - (f1 / norm), 0.0, 1.0).astype(np.float32, copy=False)
    edge_metric = 1.0 - np.clip((f2 - f1) / float(max(1e-3, edge_width)), 0.0, 1.0)
    edge_metric = smoothstep_np(0.0, 1.0, edge_metric).astype(np.float32, copy=False)
    fill_field = np.clip((nearest_value * 0.58) + (distance_field * 0.42), 0.0, 1.0).astype(np.float32, copy=False)
    cracks_field = np.power(np.clip(edge_metric, 0.0, 1.0), 2.35).astype(np.float32, copy=False)
    bevel_field = np.clip((distance_field * 0.62) + (edge_metric * 0.48), 0.0, 1.0).astype(np.float32, copy=False)

    resolved_mode = str(pattern_mode).lower()
    if resolved_mode == "edge":
        return _enforce_tile_edges(edge_metric)
    if resolved_mode == "cracks":
        return _enforce_tile_edges(cracks_field)
    if resolved_mode == "distance":
        return _enforce_tile_edges(distance_field)
    if resolved_mode == "bevel":
        return _enforce_tile_edges(bevel_field)
    return _enforce_tile_edges(fill_field)


def procedural_strata_pattern(
    h: int,
    w: int,
    band_scale_px: float,
    direction_deg: float,
    warp_strength: float,
    breakup_scale_px: float,
    breakup_strength: float,
    seed: int,
    profile: str = "soft",
) -> np.ndarray:
    resolved_scale = float(max(1.0, band_scale_px))
    cycles = max(1, int(round(float(max(int(h), int(w))) / resolved_scale)))
    theta = math.radians(float(direction_deg))
    freq_x = int(round(math.cos(theta) * cycles))
    freq_y = int(round(math.sin(theta) * cycles))
    if freq_x == 0 and freq_y == 0:
        freq_x = cycles

    u = np.arange(int(w), dtype=np.float32) / float(max(1, int(w)))
    v = np.arange(int(h), dtype=np.float32) / float(max(1, int(h)))
    vv, uu = np.meshgrid(v, u, indexing="ij")

    warp = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, float(breakup_scale_px) * 1.35),
        octaves=4,
        lacunarity=2.0,
        gain=0.55,
        seed=int(seed) + 307,
        variant="turbulence",
    )
    breakup = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, float(breakup_scale_px)),
        octaves=4,
        lacunarity=2.15,
        gain=0.58,
        seed=int(seed) + 911,
        variant="fbm",
    )
    phase = (uu * float(freq_x)) + (vv * float(freq_y))
    phase = phase + ((warp - 0.5) * float(np.clip(warp_strength, 0.0, 1.0)) * 0.9)
    phase = phase + ((breakup - 0.5) * float(np.clip(breakup_strength, 0.0, 1.0)) * 0.35)
    wave = phase * (2.0 * math.pi)

    resolved_profile = str(profile).lower()
    if resolved_profile == "veins":
        base = (1.0 - np.abs(np.sin(wave))).astype(np.float32, copy=False)
    elif resolved_profile == "terrace":
        stair = np.mod(phase, 1.0).astype(np.float32, copy=False)
        base = smoothstep_np(0.08, 0.92, stair).astype(np.float32, copy=False)
    else:
        base = (0.5 + (0.5 * np.sin(wave))).astype(np.float32, copy=False)

    amplitude = 1.0 + ((breakup - 0.5) * float(np.clip(breakup_strength, 0.0, 1.0)) * 0.95)
    out = np.clip(0.5 + ((base - 0.5) * amplitude), 0.0, 1.0).astype(np.float32, copy=False)
    return _enforce_tile_edges(out)


def procedural_hex_pattern(
    h: int,
    w: int,
    hex_scale_px: float,
    line_width: float,
    seed: int,
    pattern_mode: str = "fill",
) -> np.ndarray:
    resolved_scale = float(max(4.0, hex_scale_px))
    cols = int(max(2, round(float(w) / resolved_scale)))
    row_spacing = math.sqrt(3.0) * 0.5
    rows = int(max(2, round(float(h) / max(1.0, resolved_scale * row_spacing))))
    if rows % 2 != 0:
        rows += 1

    rng = np.random.default_rng(int(seed))
    cell_values = rng.uniform(0.0, 1.0, size=(rows, cols)).astype(np.float32, copy=False)

    world_x = ((np.arange(int(w), dtype=np.float32) + 0.5) / float(max(1, int(w)))) * float(cols)
    world_y = ((np.arange(int(h), dtype=np.float32) + 0.5) / float(max(1, int(h)))) * float(rows * row_spacing)
    wy, wx = np.meshgrid(world_y, world_x, indexing="ij")

    base_row = np.floor(wy / row_spacing).astype(np.int32)
    f1 = np.full((int(h), int(w)), np.inf, dtype=np.float32)
    f2 = np.full((int(h), int(w)), np.inf, dtype=np.float32)
    nearest_value = np.zeros((int(h), int(w)), dtype=np.float32)

    for dy in (-1, 0, 1):
        row = base_row + dy
        row_wrap = np.mod(row, rows)
        parity = (row_wrap % 2).astype(np.float32, copy=False)
        center_y = (row.astype(np.float32, copy=False) + 0.5) * row_spacing
        base_col = np.floor(wx - (parity * 0.5)).astype(np.int32)

        for dx in (-1, 0, 1):
            col = base_col + dx
            col_wrap = np.mod(col, cols)
            center_x = col.astype(np.float32, copy=False) + 0.5 + (parity * 0.5)
            dist = np.sqrt(((center_x - wx) ** 2) + ((center_y - wy) ** 2)).astype(np.float32, copy=False)

            replace_primary = dist < f1
            f2 = np.where(replace_primary, f1, np.minimum(f2, dist))
            f1 = np.where(replace_primary, dist, f1)
            nearest_value = np.where(replace_primary, cell_values[row_wrap, col_wrap], nearest_value)

            replace_secondary = (~replace_primary) & (dist < f2)
            f2 = np.where(replace_secondary, dist, f2)

    center_norm = float(max(np.percentile(f1, 98.0), 1e-4))
    center_field = np.clip(1.0 - (f1 / center_norm), 0.0, 1.0).astype(np.float32, copy=False)
    edge_metric = 1.0 - np.clip((f2 - f1) / float(max(1e-3, line_width)), 0.0, 1.0)
    edge_metric = smoothstep_np(0.0, 1.0, edge_metric).astype(np.float32, copy=False)
    fill_field = np.clip((nearest_value * 0.54) + (center_field * 0.46), 0.0, 1.0).astype(np.float32, copy=False)
    bevel_field = np.clip((center_field * 0.52) + (edge_metric * 0.48), 0.0, 1.0).astype(np.float32, copy=False)

    resolved_mode = str(pattern_mode).lower()
    if resolved_mode == "lines":
        return _enforce_tile_edges(edge_metric)
    if resolved_mode == "centers":
        return _enforce_tile_edges(center_field)
    if resolved_mode == "bevel":
        return _enforce_tile_edges(bevel_field)
    return _enforce_tile_edges(fill_field)


def procedural_weave_pattern(
    h: int,
    w: int,
    warp_scale_px: float,
    weft_scale_px: float,
    thread_width: float,
    relief: float,
    seed: int,
    style: str = "plain",
) -> np.ndarray:
    cycles_x = int(max(1, round(float(w) / float(max(4.0, warp_scale_px)))))
    cycles_y = int(max(1, round(float(h) / float(max(4.0, weft_scale_px)))))

    u = ((np.arange(int(w), dtype=np.float32) + 0.5) / float(max(1, int(w)))) * float(cycles_x)
    v = ((np.arange(int(h), dtype=np.float32) + 0.5) / float(max(1, int(h)))) * float(cycles_y)
    vv, uu = np.meshgrid(v, u, indexing="ij")

    x_idx = np.floor(uu).astype(np.int32)
    y_idx = np.floor(vv).astype(np.int32)
    local_x = (uu - x_idx).astype(np.float32, copy=False)
    local_y = (vv - y_idx).astype(np.float32, copy=False)

    half_width = float(np.clip(thread_width, 0.05, 0.98)) * 0.5
    edge_softness = float(min(0.24, max(0.02, (1.0 - float(np.clip(thread_width, 0.05, 0.98))) * 0.45)))
    warp_profile = 1.0 - smoothstep_np(
        half_width,
        min(0.5, half_width + edge_softness),
        np.abs(local_x - 0.5).astype(np.float32, copy=False),
    )
    weft_profile = 1.0 - smoothstep_np(
        half_width,
        min(0.5, half_width + edge_softness),
        np.abs(local_y - 0.5).astype(np.float32, copy=False),
    )

    resolved_style = str(style).lower()
    if resolved_style == "twill":
        over_mask = ((x_idx + (y_idx * 2)) % 4) < 2
    elif resolved_style == "basket":
        over_mask = (((x_idx // 2) + (y_idx // 2)) % 2) == 0
    else:
        over_mask = ((x_idx + y_idx) % 2) == 0

    relief_amt = float(np.clip(relief, 0.0, 1.0))
    jitter = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, max(float(warp_scale_px), float(weft_scale_px)) * 1.5),
        octaves=3,
        lacunarity=2.0,
        gain=0.6,
        seed=int(seed) + 701,
        variant="fbm",
    )
    warp_profile = np.clip(warp_profile * (0.92 + ((jitter - 0.5) * 0.16)), 0.0, 1.0).astype(np.float32, copy=False)
    weft_profile = np.clip(weft_profile * (0.92 - ((jitter - 0.5) * 0.16)), 0.0, 1.0).astype(np.float32, copy=False)

    over = over_mask.astype(np.float32, copy=False)
    under = 1.0 - over
    warp_field = warp_profile * (0.30 + (relief_amt * ((0.70 * over) + (0.28 * under))))
    weft_field = weft_profile * (0.30 + (relief_amt * ((0.70 * under) + (0.28 * over))))
    crossover = (warp_profile * weft_profile).astype(np.float32, copy=False)
    field = np.clip(0.05 + np.maximum(warp_field, weft_field) - (crossover * (0.06 + (0.12 * relief_amt))), 0.0, 1.0)
    return _enforce_tile_edges(field.astype(np.float32, copy=False))


def procedural_ripple_pattern(
    h: int,
    w: int,
    ripple_scale_px: float,
    direction_deg: float,
    radial_mix: float,
    interference: float,
    warp_strength: float,
    seed: int,
    pattern_mode: str = "interference",
) -> np.ndarray:
    resolved_scale = float(max(4.0, ripple_scale_px))
    cycles = max(1.0, float(max(int(h), int(w))) / resolved_scale)
    theta = math.radians(float(direction_deg))

    u = np.arange(int(w), dtype=np.float32) / float(max(1, int(w)))
    v = np.arange(int(h), dtype=np.float32) / float(max(1, int(h)))
    vv, uu = np.meshgrid(v, u, indexing="ij")

    torus_x = np.sin(uu * (2.0 * math.pi))
    torus_y = np.sin(vv * (2.0 * math.pi))
    torus_r = np.sqrt((torus_x * torus_x) + (torus_y * torus_y)).astype(np.float32, copy=False)

    directional = (
        (math.cos(theta) * np.sin(uu * (2.0 * math.pi * cycles)))
        + (math.sin(theta) * np.sin(vv * (2.0 * math.pi * cycles)))
    ).astype(np.float32, copy=False)
    radial = np.sin((torus_r * math.pi * cycles * 1.5) + (math.cos(theta) * 0.7)).astype(np.float32, copy=False)
    cross = np.sin(((uu + vv) * 2.0 * math.pi * cycles * 0.5) + (directional * 1.2)).astype(np.float32, copy=False)

    warp = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 0.65),
        octaves=4,
        lacunarity=2.0,
        gain=0.56,
        seed=int(seed) + 701,
        variant="fbm",
    )
    warped = ((warp - 0.5) * float(np.clip(warp_strength, 0.0, 1.0)) * 2.2).astype(np.float32, copy=False)

    resolved_mode = str(pattern_mode).lower()
    radial_mix = float(np.clip(radial_mix, 0.0, 1.0))
    interference = float(np.clip(interference, 0.0, 1.0))

    if resolved_mode == "rings":
        phase = radial + warped
    elif resolved_mode == "directional":
        phase = directional + warped
    else:
        phase = (
            (directional * (1.0 - radial_mix))
            + (radial * radial_mix)
            + (cross * interference * 0.65)
            + warped
        ).astype(np.float32, copy=False)

    out = (0.5 + (0.5 * np.sin(phase * math.pi))).astype(np.float32, copy=False)
    return _enforce_tile_edges(np.clip(out, 0.0, 1.0).astype(np.float32, copy=False))


def procedural_contour_pattern(
    h: int,
    w: int,
    contour_scale_px: float,
    line_width: float,
    terrace_strength: float,
    warp_strength: float,
    seed: int,
    pattern_mode: str = "lines",
) -> np.ndarray:
    base = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, float(contour_scale_px)),
        octaves=5,
        lacunarity=2.0,
        gain=0.56,
        seed=int(seed),
        variant="fbm",
    )
    warp = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, float(contour_scale_px) * 0.52),
        octaves=4,
        lacunarity=2.15,
        gain=0.58,
        seed=int(seed) + 313,
        variant="ridged",
    )
    terrain = np.clip(base + ((warp - 0.5) * float(np.clip(warp_strength, 0.0, 1.0)) * 0.55), 0.0, 1.0).astype(
        np.float32,
        copy=False,
    )

    levels = max(4.0, float(max(int(h), int(w))) / float(max(6.0, contour_scale_px)) * 3.0)
    contour_phase = np.mod(terrain * levels, 1.0).astype(np.float32, copy=False)
    width = float(np.clip(line_width, 0.01, 1.0))
    line = 1.0 - smoothstep_np(0.0, max(1e-4, width), np.abs(contour_phase - 0.5) * 2.0)
    line = np.clip(line, 0.0, 1.0).astype(np.float32, copy=False)

    terraces = np.floor(terrain * levels) / max(levels - 1.0, 1.0)
    terraces = np.clip(terraces, 0.0, 1.0).astype(np.float32, copy=False)
    bevel = np.clip((terraces * (1.0 - float(np.clip(terrace_strength, 0.0, 1.0)))) + (line * 0.85), 0.0, 1.0)

    resolved_mode = str(pattern_mode).lower()
    if resolved_mode == "height":
        return _enforce_tile_edges(terrain)
    if resolved_mode == "terrace":
        return _enforce_tile_edges(np.clip((terraces * 0.78) + (line * 0.35), 0.0, 1.0).astype(np.float32, copy=False))
    if resolved_mode == "bevel":
        return _enforce_tile_edges(bevel.astype(np.float32, copy=False))
    return _enforce_tile_edges(line.astype(np.float32, copy=False))


def procedural_marble_pattern(
    h: int,
    w: int,
    vein_scale_px: float,
    direction_deg: float,
    flow_strength: float,
    mineral_mix: float,
    seed: int,
    pattern_mode: str = "classic",
) -> np.ndarray:
    resolved_scale = float(max(4.0, vein_scale_px))
    cycles = max(1.0, float(max(int(h), int(w))) / resolved_scale)
    theta = math.radians(float(direction_deg))

    u = np.arange(int(w), dtype=np.float32) / float(max(1, int(w)))
    v = np.arange(int(h), dtype=np.float32) / float(max(1, int(h)))
    vv, uu = np.meshgrid(v, u, indexing="ij")

    flow = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 0.82),
        octaves=5,
        lacunarity=2.0,
        gain=0.57,
        seed=int(seed) + 211,
        variant="fbm",
    )
    mineral = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 0.36),
        octaves=4,
        lacunarity=2.15,
        gain=0.54,
        seed=int(seed) + 577,
        variant="ridged",
    )
    swirl = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 1.55),
        octaves=3,
        lacunarity=1.9,
        gain=0.60,
        seed=int(seed) + 887,
        variant="turbulence",
    )

    phase = (
        (uu * math.cos(theta) * cycles)
        + (vv * math.sin(theta) * cycles)
        + ((flow - 0.5) * float(np.clip(flow_strength, 0.0, 1.0)) * 1.55)
        + ((swirl - 0.5) * 0.55)
    )
    wave = np.sin(phase * (2.0 * math.pi)).astype(np.float32, copy=False)
    mineral_mix = float(np.clip(mineral_mix, 0.0, 1.0))
    resolved_mode = str(pattern_mode).lower()

    if resolved_mode == "vein":
        veins = np.power(1.0 - np.abs(wave), 1.45).astype(np.float32, copy=False)
        field = np.clip((veins * 0.88) + (mineral * (0.12 + (mineral_mix * 0.32))), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    elif resolved_mode == "onyx":
        cloud = (0.5 + (0.5 * np.sin((phase * (2.0 * math.pi * 0.64)) + ((mineral - 0.5) * 2.2)))).astype(
            np.float32,
            copy=False,
        )
        band = np.power(0.5 + (0.5 * wave), 0.82).astype(np.float32, copy=False)
        field = np.clip((cloud * 0.74) + (band * 0.26) + (mineral * mineral_mix * 0.18), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    else:
        band = (0.5 + (0.5 * wave)).astype(np.float32, copy=False)
        wisps = (0.5 + (0.5 * np.sin((phase * (2.0 * math.pi * 1.55)) + ((mineral - 0.5) * 1.8)))).astype(
            np.float32,
            copy=False,
        )
        field = np.clip((band * 0.74) + (wisps * 0.16) + (mineral * mineral_mix * 0.24), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    return _enforce_tile_edges(field)


def procedural_dune_pattern(
    h: int,
    w: int,
    dune_scale_px: float,
    direction_deg: float,
    wind_skew: float,
    crest_sharpness: float,
    ripple_detail: float,
    drift_strength: float,
    seed: int,
    pattern_mode: str = "ridges",
) -> np.ndarray:
    resolved_scale = float(max(4.0, dune_scale_px))
    cycles = max(1.0, float(max(int(h), int(w))) / resolved_scale)
    theta = math.radians(float(direction_deg))

    u = np.arange(int(w), dtype=np.float32) / float(max(1, int(w)))
    v = np.arange(int(h), dtype=np.float32) / float(max(1, int(h)))
    vv, uu = np.meshgrid(v, u, indexing="ij")

    along = (uu * math.cos(theta)) + (vv * math.sin(theta))
    across = (-uu * math.sin(theta)) + (vv * math.cos(theta))
    drift = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 0.76),
        octaves=4,
        lacunarity=2.0,
        gain=0.57,
        seed=int(seed) + 401,
        variant="fbm",
    )
    ripple = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, resolved_scale * 0.26),
        octaves=3,
        lacunarity=2.1,
        gain=0.55,
        seed=int(seed) + 613,
        variant="ridged",
    )

    path = (
        along
        + ((across - 0.5) * float(np.clip(wind_skew, 0.0, 1.0)) * 0.48)
        + ((drift - 0.5) * float(np.clip(drift_strength, 0.0, 1.0)) * 0.55)
    )
    dune_wave = np.sin(path * (2.0 * math.pi * cycles)).astype(np.float32, copy=False)
    ridge_base = (0.5 + (0.5 * dune_wave)).astype(np.float32, copy=False)
    sharpness = 0.55 + (float(np.clip(crest_sharpness, 0.0, 1.0)) * 2.6)
    ridges = np.power(np.clip(ridge_base, 0.0, 1.0), sharpness).astype(np.float32, copy=False)
    sheets = (0.5 + (0.5 * np.sin((path * (2.0 * math.pi * cycles * 0.72)) + ((ripple - 0.5) * 1.4)))).astype(
        np.float32,
        copy=False,
    )
    detail = np.sin((path * (2.0 * math.pi * cycles * 3.6)) + (ripple * math.pi * 1.8)).astype(np.float32, copy=False)
    detail = ((detail * 0.5) + 0.5).astype(np.float32, copy=False)
    detail_mix = float(np.clip(ripple_detail, 0.0, 1.0)) * 0.24
    resolved_mode = str(pattern_mode).lower()

    if resolved_mode == "sheet":
        field = np.clip((sheets * 0.82) + (detail * detail_mix), 0.0, 1.0).astype(np.float32, copy=False)
    elif resolved_mode == "crescent":
        crescent_gate = smoothstep_np(
            0.18,
            0.86,
            0.5 + (0.5 * np.sin(((across * 2.1) + ((drift - 0.5) * 0.72)) * (2.0 * math.pi))),
        ).astype(np.float32, copy=False)
        field = np.clip(
            (ridges * (1.0 - (crescent_gate * 0.28)))
            + (sheets * crescent_gate * 0.44)
            + (detail * detail_mix),
            0.0,
            1.0,
        ).astype(np.float32, copy=False)
    else:
        field = np.clip((ridges * 0.88) + (detail * detail_mix), 0.0, 1.0).astype(np.float32, copy=False)

    return _enforce_tile_edges(field)


def procedural_caustic_pattern(
    h: int,
    w: int,
    caustic_scale_px: float,
    focus: float,
    shimmer: float,
    warp_strength: float,
    seed: int,
    pattern_mode: str = "web",
) -> np.ndarray:
    scale = float(max(4.0, caustic_scale_px))
    web = procedural_cell_pattern(
        int(h),
        int(w),
        cell_scale_px=scale,
        jitter=0.82,
        edge_width=0.18,
        seed=int(seed),
        pattern_mode="cracks",
    )
    pool = procedural_cell_pattern(
        int(h),
        int(w),
        cell_scale_px=scale * 1.08,
        jitter=0.76,
        edge_width=0.18,
        seed=int(seed) + 31,
        pattern_mode="distance",
    )
    ripple = procedural_ripple_pattern(
        int(h),
        int(w),
        ripple_scale_px=max(4.0, scale * 0.88),
        direction_deg=18.0,
        radial_mix=0.62,
        interference=0.58,
        warp_strength=float(np.clip(warp_strength, 0.0, 1.0)),
        seed=int(seed) + 83,
        pattern_mode="interference",
    )
    shimmer_field = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, scale * 0.24),
        octaves=4,
        lacunarity=2.2,
        gain=0.54,
        seed=int(seed) + 127,
        variant="ridged",
    )
    focus_power = 1.0 + (float(np.clip(focus, 0.0, 1.0)) * 3.4)
    web_focus = np.power(np.clip(web, 0.0, 1.0), focus_power).astype(np.float32, copy=False)
    shimmer_mix = float(np.clip(shimmer, 0.0, 1.0))
    resolved_mode = str(pattern_mode).lower()

    if resolved_mode == "pool":
        field = np.clip((pool * 0.76) + (web_focus * 0.36) + (shimmer_field * shimmer_mix * 0.18), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    elif resolved_mode == "flare":
        field = np.clip((web_focus * 0.58) + (ripple * 0.34) + (pool * 0.18) + (shimmer_field * shimmer_mix * 0.20), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
    else:
        field = np.clip((web_focus * 0.82) + (ripple * 0.16) + (shimmer_field * shimmer_mix * 0.14), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    return _enforce_tile_edges(field)


def procedural_crackle_pattern(
    h: int,
    w: int,
    plate_scale_px: float,
    crack_width: float,
    plate_variation: float,
    relief: float,
    seed: int,
    pattern_mode: str = "plates",
) -> np.ndarray:
    scale = float(max(4.0, plate_scale_px))
    variation = float(np.clip(plate_variation, 0.0, 1.0))
    resolved_width = float(np.clip(crack_width, 0.01, 1.0))
    fill = procedural_cell_pattern(
        int(h),
        int(w),
        cell_scale_px=scale,
        jitter=0.28 + (variation * 0.58),
        edge_width=resolved_width,
        seed=int(seed),
        pattern_mode="fill",
    )
    cracks = procedural_cell_pattern(
        int(h),
        int(w),
        cell_scale_px=scale,
        jitter=0.32 + (variation * 0.62),
        edge_width=resolved_width,
        seed=int(seed),
        pattern_mode="cracks",
    )
    bevel = procedural_cell_pattern(
        int(h),
        int(w),
        cell_scale_px=scale,
        jitter=0.30 + (variation * 0.60),
        edge_width=resolved_width,
        seed=int(seed) + 17,
        pattern_mode="bevel",
    )
    dust = procedural_noise_field(
        int(h),
        int(w),
        scale_px=max(8.0, scale * 0.22),
        octaves=4,
        lacunarity=2.05,
        gain=0.55,
        seed=int(seed) + 97,
        variant="fbm",
    )
    relief_mix = float(np.clip(relief, 0.0, 1.0))
    resolved_mode = str(pattern_mode).lower()

    if resolved_mode == "cracks":
        field = np.clip(np.power(cracks, 1.18) + (dust * 0.10), 0.0, 1.0).astype(np.float32, copy=False)
    elif resolved_mode == "mud":
        baked = np.clip((fill * (0.54 + (relief_mix * 0.18))) + (bevel * 0.34) + (dust * 0.12) - (cracks * 0.18), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )
        field = baked
    else:
        field = np.clip((fill * 0.62) + (bevel * (0.20 + (relief_mix * 0.20))) + (cracks * 0.22) + (dust * 0.08), 0.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    return _enforce_tile_edges(field)


__all__ = [
    "grayscale_to_rgb",
    "procedural_cell_pattern",
    "procedural_contour_pattern",
    "procedural_crackle_pattern",
    "procedural_caustic_pattern",
    "procedural_dune_pattern",
    "procedural_hex_pattern",
    "procedural_marble_pattern",
    "procedural_noise_field",
    "procedural_ripple_pattern",
    "procedural_strata_pattern",
    "procedural_weave_pattern",
    "shape_scalar_field",
]
