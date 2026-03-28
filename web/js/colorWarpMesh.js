import { app } from "../../../scripts/app.js";
import { createPanelShell } from "./uiSystem.js";
import {
  attachPanel,
  createGradeButton,
  createGradeMetric,
  createGradeReadout,
  createGradeSection,
  createGradeSlider,
  createGradeToggle,
  ensureCanvasResolution,
  ensureColorGradeStyles,
  formatNumber,
  getBoolean,
  getNumber,
  getValue,
  installBundledSettingsAdapter,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ColorWarpStudio";
const TARGETS = new Set(["x1ColorWarpHueSat", "x1ColorWarpChromaLuma"]);
const PANEL_NAME = "mkr_color_warp_studio";
const SETTINGS_WIDGET_NAME = "settings_json";
const WARP_PANEL_WIDTH = 760;
const WARP_PANEL_HEIGHT = 960;
const LEGACY_WIDGETS = [
  "warp_points_json",
  "strength",
  "falloff",
  "mix",
  "mask_feather",
  "invert_mask",
];
const HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...LEGACY_WIDGETS];
const NUMERIC_SPECS = {
  strength: { min: 0.0, max: 2.0 },
  falloff: { min: 0.4, max: 2.5 },
  mix: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};
const BOOLEAN_KEYS = ["invert_mask"];
const GRID_COLS = 4;
const GRID_ROWS = 4;
const GRID_POINT_COUNT = GRID_COLS * GRID_ROWS;
const GRID_MIN_X = 0.10;
const GRID_MAX_X = 0.90;
const GRID_MIN_Y = 0.14;
const GRID_MAX_Y = 0.86;
const GRID_DEFAULT_RADIUS = 0.22;
const MESH_GRAPH_LEFT = 28;
const MESH_GRAPH_TOP = 18;
const MESH_GRAPH_RIGHT = 18;
const MESH_GRAPH_BOTTOM = 18;
const meshBackgroundCache = new Map();

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function buildGraphRect(width, height) {
  return {
    x: MESH_GRAPH_LEFT,
    y: MESH_GRAPH_TOP,
    w: Math.max(120, width - MESH_GRAPH_LEFT - MESH_GRAPH_RIGHT),
    h: Math.max(120, height - MESH_GRAPH_TOP - MESH_GRAPH_BOTTOM),
  };
}

function hsvToRgb(h, s, v) {
  const hue = ((Number(h) % 1) + 1) % 1;
  const sat = clamp(Number(s) || 0, 0, 1);
  const val = clamp(Number(v) || 0, 0, 1);
  const i = Math.floor(hue * 6);
  const f = (hue * 6) - i;
  const p = val * (1 - sat);
  const q = val * (1 - (f * sat));
  const t = val * (1 - ((1 - f) * sat));
  switch (i % 6) {
    case 0: return [val, t, p];
    case 1: return [q, val, p];
    case 2: return [p, val, t];
    case 3: return [p, q, val];
    case 4: return [t, p, val];
    default: return [val, p, q];
  }
}

function getMeshBackground(kind, width, height) {
  const key = `${kind}:${width}x${height}`;
  const cached = meshBackgroundCache.get(key);
  if (cached) return cached;

  const surface = document.createElement("canvas");
  surface.width = width;
  surface.height = height;
  const ctx = surface.getContext("2d");
  const image = ctx.createImageData(width, height);
  const data = image.data;

  for (let y = 0; y < height; y += 1) {
    const vertical = 1 - (y / Math.max(1, height - 1));
    for (let x = 0; x < width; x += 1) {
      const horizontal = x / Math.max(1, width - 1);
      let rgb;
      if (kind === "x1ColorWarpHueSat") {
        const sat = 0.06 + (vertical * 0.9);
        const val = 0.74 + (vertical * 0.14);
        rgb = hsvToRgb(horizontal, sat, val);
      } else {
        const luma = 0.12 + (vertical * 0.74);
        const chroma = Math.pow(horizontal, 0.9);
        const neutral = [luma, luma, luma];
        const tint = hsvToRgb(0.53, 0.10 + (chroma * 0.55), luma);
        const blend = 0.10 + (chroma * 0.42);
        rgb = [
          (neutral[0] * (1 - blend)) + (tint[0] * blend),
          (neutral[1] * (1 - blend)) + (tint[1] * blend),
          (neutral[2] * (1 - blend)) + (tint[2] * blend),
        ];
      }

      const index = (y * width + x) * 4;
      data[index] = Math.round(clamp(rgb[0], 0, 1) * 255);
      data[index + 1] = Math.round(clamp(rgb[1], 0, 1) * 255);
      data[index + 2] = Math.round(clamp(rgb[2], 0, 1) * 255);
      data[index + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
  meshBackgroundCache.set(key, surface);
  return surface;
}

function drawLabelChip(ctx, text, x, y, options = {}) {
  const angle = Number(options.angle) || 0;
  const paddingX = options.paddingX ?? 7;
  const paddingY = options.paddingY ?? 4;
  const font = options.font || "600 12px sans-serif";
  const textColor = options.textColor || "rgba(240, 245, 250, 0.92)";
  const fill = options.fill || "rgba(8, 10, 14, 0.46)";
  const border = options.border || "rgba(255, 255, 255, 0.08)";

  ctx.save();
  ctx.translate(x, y);
  if (angle) ctx.rotate(angle);
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const metrics = ctx.measureText(text);
  const width = metrics.width + (paddingX * 2);
  const height = 20 + (paddingY * 2);
  const rx = -width * 0.5;
  const ry = -height * 0.5;
  ctx.fillStyle = fill;
  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(rx, ry, width, height, 8);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = textColor;
  ctx.fillText(text, 0, 1);
  ctx.restore();
}

function clampPoint(point) {
  return {
    src_x: clamp(Number(point?.src_x) || 0.5, 0, 1),
    src_y: clamp(Number(point?.src_y) || 0.5, 0, 1),
    dst_x: clamp(Number(point?.dst_x ?? point?.src_x) || 0.5, 0, 1),
    dst_y: clamp(Number(point?.dst_y ?? point?.src_y) || 0.5, 0, 1),
    radius: clamp(Number(point?.radius) || GRID_DEFAULT_RADIUS, 0.03, 0.5),
    weight: clamp(Number(point?.weight) || 1.0, 0.0, 2.0),
  };
}

function parsePoints(raw) {
  try {
    const payload = JSON.parse(String(raw || "[]"));
    if (!Array.isArray(payload)) return [];
    return payload.slice(0, 64).map((point) => clampPoint(point));
  } catch {
    return [];
  }
}

function gridIndex(row, col) {
  return (row * GRID_COLS) + col;
}

function formatGridLabel(index, compact = false) {
  const row = Math.floor(index / GRID_COLS);
  const col = index % GRID_COLS;
  if (compact) return `${String.fromCharCode(65 + col)}${row + 1}`;
  return `${String.fromCharCode(65 + col)}${row + 1}`;
}

function buildNeutralGrid() {
  const points = [];
  for (let row = 0; row < GRID_ROWS; row += 1) {
    const v = row / Math.max(1, GRID_ROWS - 1);
    const y = GRID_MAX_Y - ((GRID_MAX_Y - GRID_MIN_Y) * v);
    for (let col = 0; col < GRID_COLS; col += 1) {
      const u = col / Math.max(1, GRID_COLS - 1);
      const x = GRID_MIN_X + ((GRID_MAX_X - GRID_MIN_X) * u);
      points.push({
        src_x: x,
        src_y: y,
        dst_x: x,
        dst_y: y,
        radius: GRID_DEFAULT_RADIUS,
        weight: 1.0,
      });
    }
  }
  return points;
}

function applySparseFieldAtPoint(x, y, sparsePoints) {
  let dx = 0;
  let dy = 0;
  let radiusTotal = 0;
  let weightTotal = 0;
  let influenceTotal = 0;

  for (const point of sparsePoints) {
    const sx = Number(point.src_x);
    const sy = Number(point.src_y);
    const tx = Number(point.dst_x);
    const ty = Number(point.dst_y);
    const radius = Math.max(0.0001, Number(point.radius) || GRID_DEFAULT_RADIUS);
    const weight = Number(point.weight) || 1.0;
    const distance = Math.hypot(x - sx, y - sy);
    const norm = clamp(1 - (distance / radius), 0, 1);
    const influence = Math.pow(norm, 2) * weight;
    if (influence <= 0) continue;
    dx += (tx - sx) * influence;
    dy += (ty - sy) * influence;
    radiusTotal += radius * influence;
    weightTotal += weight * influence;
    influenceTotal += influence;
  }

  if (influenceTotal <= 0.00001) {
    return {
      dst_x: x,
      dst_y: y,
      radius: GRID_DEFAULT_RADIUS,
      weight: 1.0,
    };
  }

  return {
    dst_x: clamp(x + (dx / influenceTotal), 0, 1),
    dst_y: clamp(y + (dy / influenceTotal), 0, 1),
    radius: clamp(radiusTotal / influenceTotal, 0.08, 0.4),
    weight: clamp(weightTotal / influenceTotal, 0.5, 1.5),
  };
}

function orderPointsToGrid(points, template) {
  const remaining = points.map((point) => clampPoint(point));
  const ordered = [];
  for (const cell of template) {
    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < remaining.length; index += 1) {
      const candidate = remaining[index];
      const distance = Math.hypot(candidate.src_x - cell.src_x, candidate.src_y - cell.src_y);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    const match = remaining.splice(bestIndex, 1)[0] || cell;
    ordered.push({
      ...cell,
      dst_x: clamp(match.dst_x, 0, 1),
      dst_y: clamp(match.dst_y, 0, 1),
      radius: clamp(match.radius, 0.03, 0.5),
      weight: clamp(match.weight, 0.0, 2.0),
    });
  }
  return ordered;
}

function projectSparsePointsToGrid(sparsePoints) {
  const template = buildNeutralGrid();
  return template.map((cell) => {
    const projected = applySparseFieldAtPoint(cell.src_x, cell.src_y, sparsePoints);
    return {
      ...cell,
      ...projected,
    };
  });
}

function normalizeMeshPoints(points) {
  const normalized = Array.isArray(points) ? points.map((point) => clampPoint(point)) : [];
  if (!normalized.length) return [];
  if (normalized.length === GRID_POINT_COUNT) {
    return orderPointsToGrid(normalized, buildNeutralGrid());
  }
  return projectSparsePointsToGrid(normalized);
}

function writePoints(node, points) {
  const normalized = normalizeMeshPoints(points);
  setWidgetValue(node, "warp_points_json", JSON.stringify(normalized));
  return normalized;
}

function getDefaultSettings(kind) {
  return {
    warp_points_json: "[]",
    strength: kind === "x1ColorWarpHueSat" ? 0.7 : 0.65,
    falloff: 1.0,
    mix: 1.0,
    mask_feather: 12.0,
    invert_mask: false,
  };
}

function installRefreshHooks(node, key, refresh) {
  if (!node || node[key]) return;
  node[key] = true;

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigureRefreshPanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeRefreshPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedRefreshPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function clonePoints(points) {
  return points.map((point) => ({ ...point }));
}

function buildDefaultSparsePoints(kind) {
  if (kind === "x1ColorWarpHueSat") {
    return [
      { src_x: 0.08, src_y: 0.50, dst_x: 0.12, dst_y: 0.56, radius: 0.15, weight: 1.0 },
      { src_x: 0.34, src_y: 0.64, dst_x: 0.30, dst_y: 0.72, radius: 0.16, weight: 1.05 },
      { src_x: 0.68, src_y: 0.60, dst_x: 0.72, dst_y: 0.54, radius: 0.17, weight: 0.95 },
      { src_x: 0.90, src_y: 0.42, dst_x: 0.86, dst_y: 0.48, radius: 0.14, weight: 0.9 },
    ];
  }
  return [
    { src_x: 0.20, src_y: 0.22, dst_x: 0.24, dst_y: 0.18, radius: 0.18, weight: 1.0 },
    { src_x: 0.44, src_y: 0.52, dst_x: 0.40, dst_y: 0.58, radius: 0.16, weight: 0.95 },
    { src_x: 0.72, src_y: 0.72, dst_x: 0.78, dst_y: 0.66, radius: 0.18, weight: 1.05 },
  ];
}

function buildPresetPoints(kind, preset) {
  if (preset === "reset") return projectSparsePointsToGrid(buildDefaultSparsePoints(kind));
  if (preset === "neutral") return buildNeutralGrid();

  if (kind === "x1ColorWarpHueSat") {
    if (preset === "warm_skin") {
      return projectSparsePointsToGrid([
        { src_x: 0.05, src_y: 0.40, dst_x: 0.08, dst_y: 0.48, radius: 0.16, weight: 1.0 },
        { src_x: 0.09, src_y: 0.68, dst_x: 0.11, dst_y: 0.75, radius: 0.13, weight: 1.0 },
        { src_x: 0.13, src_y: 0.52, dst_x: 0.10, dst_y: 0.58, radius: 0.12, weight: 0.9 },
      ]);
    }
    return projectSparsePointsToGrid([
      { src_x: 0.56, src_y: 0.70, dst_x: 0.52, dst_y: 0.82, radius: 0.16, weight: 1.0 },
      { src_x: 0.66, src_y: 0.54, dst_x: 0.70, dst_y: 0.62, radius: 0.14, weight: 0.95 },
      { src_x: 0.34, src_y: 0.52, dst_x: 0.32, dst_y: 0.44, radius: 0.15, weight: 0.85 },
    ]);
  }

  if (preset === "lift_fabric") {
    return projectSparsePointsToGrid([
      { src_x: 0.18, src_y: 0.26, dst_x: 0.22, dst_y: 0.20, radius: 0.18, weight: 1.0 },
      { src_x: 0.42, src_y: 0.44, dst_x: 0.46, dst_y: 0.40, radius: 0.16, weight: 0.9 },
      { src_x: 0.72, src_y: 0.72, dst_x: 0.78, dst_y: 0.66, radius: 0.17, weight: 1.05 },
    ]);
  }
  return projectSparsePointsToGrid([
    { src_x: 0.22, src_y: 0.70, dst_x: 0.18, dst_y: 0.76, radius: 0.16, weight: 0.9 },
    { src_x: 0.56, src_y: 0.54, dst_x: 0.52, dst_y: 0.62, radius: 0.17, weight: 1.0 },
    { src_x: 0.82, src_y: 0.22, dst_x: 0.76, dst_y: 0.28, radius: 0.18, weight: 1.1 },
  ]);
}

function toScreen(graph, x, y) {
  return {
    x: graph.x + (x * graph.w),
    y: graph.y + ((1 - y) * graph.h),
  };
}

function fromScreen(graph, x, y) {
  return {
    x: clamp((x - graph.x) / Math.max(1, graph.w), 0, 1),
    y: 1 - clamp((y - graph.y) / Math.max(1, graph.h), 0, 1),
  };
}

function drawMeshLines(ctx, graph, points, mode, strokeStyle, lineWidth = 1.2, dashed = false) {
  const coordKeyX = mode === "source" ? "src_x" : "dst_x";
  const coordKeyY = mode === "source" ? "src_y" : "dst_y";
  ctx.save();
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = lineWidth;
  if (dashed) ctx.setLineDash([5, 5]);

  for (let row = 0; row < GRID_ROWS; row += 1) {
    ctx.beginPath();
    for (let col = 0; col < GRID_COLS; col += 1) {
      const point = points[gridIndex(row, col)];
      if (!point) continue;
      const screen = toScreen(graph, point[coordKeyX], point[coordKeyY]);
      if (col === 0) ctx.moveTo(screen.x, screen.y);
      else ctx.lineTo(screen.x, screen.y);
    }
    ctx.stroke();
  }

  for (let col = 0; col < GRID_COLS; col += 1) {
    ctx.beginPath();
    for (let row = 0; row < GRID_ROWS; row += 1) {
      const point = points[gridIndex(row, col)];
      if (!point) continue;
      const screen = toScreen(graph, point[coordKeyX], point[coordKeyY]);
      if (row === 0) ctx.moveTo(screen.x, screen.y);
      else ctx.lineTo(screen.x, screen.y);
    }
    ctx.stroke();
  }

  ctx.restore();
}

function buildWarpPanel(node) {
  ensureColorGradeStyles();

  const kind = String(node?.comfyClass || node?.type || "");
  const isHueSat = kind === "x1ColorWarpHueSat";
  const title = isHueSat ? "Hue / Sat Warp Studio" : "Chroma / Luma Warp Studio";
  const subtitle = isHueSat
    ? "Drag mesh handles to remap hue and saturation zones with visual falloff control."
    : "Reshape chroma and luma regions without opening the raw JSON point payload.";

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title,
    subtitle,
    showHeader: false,
  });

  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", isHueSat ? "#ef6c49" : "#2d9c8f");
  panel.style.paddingBottom = "18px";

  let points = normalizeMeshPoints(parsePoints(getValue(node, "warp_points_json", "[]")));
  if (!points.length) {
    points = buildPresetPoints(kind, "reset");
    points = writePoints(node, points);
  }

  let selectedIndex = 0;
  let activeIndex = -1;

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metrics = document.createElement("div");
  metrics.className = "mkr-grade-metrics";
  const pointCountMetric = createGradeMetric("Mesh", `${GRID_COLS} x ${GRID_ROWS}`);
  const strengthMetric = createGradeMetric("Strength", formatNumber(getNumber(node, "strength", isHueSat ? 0.7 : 0.65)));
  const mixMetric = createGradeMetric("Mix", formatNumber(getNumber(node, "mix", 1)));
  metrics.appendChild(pointCountMetric.element);
  metrics.appendChild(strengthMetric.element);
  metrics.appendChild(mixMetric.element);

  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Reset", () => applyPreset("reset"), "accent"));
  actions.appendChild(createGradeButton("Neutral", () => applyPreset("neutral")));
  actions.appendChild(createGradeButton(isHueSat ? "Warm Skin" : "Lift Fabric", () => applyPreset(isHueSat ? "warm_skin" : "lift_fabric")));
  actions.appendChild(createGradeButton(isHueSat ? "Neon Bias" : "Moody Contrast", () => applyPreset(isHueSat ? "neon_bias" : "moody_contrast")));
  topbar.appendChild(metrics);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const meshSection = createGradeSection(isHueSat ? "Hue / Sat Mesh" : "Chroma / Luma Mesh", "drag lattice");
  const canvas = document.createElement("canvas");
  canvas.className = "mkr-grade-canvas";
  canvas.style.height = "286px";
  meshSection.body.appendChild(canvas);

  const readouts = document.createElement("div");
  readouts.className = "mkr-grade-inline";
  const selectionReadout = createGradeReadout("Point", "P1");
  const radiusReadout = createGradeReadout("Radius", "0.16");
  const weightReadout = createGradeReadout("Weight", "1.00");
  readouts.appendChild(selectionReadout.element);
  readouts.appendChild(radiusReadout.element);
  readouts.appendChild(weightReadout.element);
  meshSection.body.appendChild(readouts);

  const note = document.createElement("div");
  note.className = "mkr-grade-note";
  note.textContent = isHueSat
    ? "The lattice is fixed now, so you warp a real hue/saturation mesh instead of adding loose points. Hue runs left to right and saturation rises upward."
    : "The lattice is fixed now, so you warp a real chroma/luma mesh instead of adding loose points. Chroma runs left to right and luminance rises upward.";
  meshSection.body.appendChild(note);
  panel.appendChild(meshSection.section);

  const pointsSection = createGradeSection("Point Inspector", "focused");
  const chipRow = document.createElement("div");
  chipRow.className = "mkr-grade-chip-row";
  pointsSection.body.appendChild(chipRow);
  const inspectorBody = document.createElement("div");
  inspectorBody.style.marginTop = "8px";
  pointsSection.body.appendChild(inspectorBody);

  const controlsSection = createGradeSection("Warp Response", "primary");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const strengthControl = createGradeSlider({
    label: "Strength",
    min: 0,
    max: 2,
    step: 0.01,
    value: getNumber(node, "strength", isHueSat ? 0.7 : 0.65),
    decimals: 2,
    onChange: (value) => {
      setWidgetValue(node, "strength", value);
      strengthMetric.setValue(formatNumber(value));
    },
  });
  const falloffControl = createGradeSlider({
    label: "Falloff",
    min: 0.4,
    max: 2.5,
    step: 0.01,
    value: getNumber(node, "falloff", 1.0),
    decimals: 2,
    onChange: (value) => {
      setWidgetValue(node, "falloff", value);
    },
  });
  const mixControl = createGradeSlider({
    label: "Mix",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "mix", 1),
    decimals: 2,
    onChange: (value) => {
      setWidgetValue(node, "mix", value);
      mixMetric.setValue(formatNumber(value));
    },
  });
  const featherControl = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => {
      setWidgetValue(node, "mask_feather", value);
    },
  });
  const invertControl = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before the warp blend.",
    onChange: (value) => {
      setWidgetValue(node, "invert_mask", value);
    },
  });
  controls.appendChild(strengthControl.element);
  controls.appendChild(falloffControl.element);
  controls.appendChild(mixControl.element);
  controls.appendChild(featherControl.element);
  controls.appendChild(invertControl.element);
  controlsSection.body.appendChild(controls);
  controlsSection.section.style.paddingBottom = "8px";
  panel.appendChild(pointsSection.section);
  panel.appendChild(controlsSection.section);

  function updatePills() {
    pointCountMetric.setValue(`${GRID_COLS} x ${GRID_ROWS}`);
    strengthMetric.setValue(formatNumber(getNumber(node, "strength", isHueSat ? 0.7 : 0.65)));
    mixMetric.setValue(formatNumber(getNumber(node, "mix", 1)));
    const selected = points[selectedIndex];
    selectionReadout.setValue(selected ? formatGridLabel(selectedIndex) : "--");
    radiusReadout.setValue(selected ? formatNumber(selected.radius) : "--");
    weightReadout.setValue(selected ? formatNumber(selected.weight) : "--");
  }

  function syncPoints(nextPoints, nextSelected = selectedIndex) {
    points = writePoints(node, clonePoints(nextPoints));
    selectedIndex = clamp(nextSelected, 0, Math.max(0, points.length - 1));
    updatePills();
    renderPointChips();
    renderInspector();
    draw();
  }

  function applyPreset(name) {
    syncPoints(buildPresetPoints(kind, name), 0);
  }

  function renderPointChips() {
    chipRow.innerHTML = "";
    if (!points.length) {
      const empty = document.createElement("div");
      empty.className = "mkr-grade-note";
      empty.textContent = "Mesh unavailable.";
      chipRow.appendChild(empty);
      return;
    }
    points.forEach((point, index) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "mkr-grade-chip";
      chip.dataset.active = index === selectedIndex ? "true" : "false";
      chip.textContent = formatGridLabel(index, true);
      chip.addEventListener("click", () => {
        selectedIndex = index;
        updatePills();
        renderPointChips();
        renderInspector();
        draw();
      });
      chipRow.appendChild(chip);
    });
  }

  function renderInspector() {
    inspectorBody.innerHTML = "";
    const selected = points[selectedIndex];
    if (!selected) return;

    const inspectorControls = document.createElement("div");
    inspectorControls.className = "mkr-grade-controls";
    const radiusControl = createGradeSlider({
      label: "Radius",
      min: 0.03,
      max: 0.5,
      step: 0.01,
      value: selected.radius,
      decimals: 2,
      onChange: (value) => {
        const nextPoints = clonePoints(points);
        nextPoints[selectedIndex].radius = value;
        syncPoints(nextPoints, selectedIndex);
      },
    });

    const weightControl = createGradeSlider({
      label: "Weight",
      min: 0,
      max: 2,
      step: 0.01,
      value: selected.weight,
      decimals: 2,
      onChange: (value) => {
        const nextPoints = clonePoints(points);
        nextPoints[selectedIndex].weight = value;
        syncPoints(nextPoints, selectedIndex);
      },
    });

    inspectorControls.appendChild(radiusControl.element);
    inspectorControls.appendChild(weightControl.element);
    inspectorBody.appendChild(inspectorControls);

    const actionRow = document.createElement("div");
    actionRow.className = "mkr-grade-actions";
    actionRow.style.marginTop = "8px";
    actionRow.appendChild(createGradeButton("Reset Point", () => {
      const nextPoints = clonePoints(points);
      nextPoints[selectedIndex].dst_x = nextPoints[selectedIndex].src_x;
      nextPoints[selectedIndex].dst_y = nextPoints[selectedIndex].src_y;
      nextPoints[selectedIndex].radius = 0.16;
      nextPoints[selectedIndex].weight = 1.0;
      syncPoints(nextPoints, selectedIndex);
    }));
    actionRow.appendChild(createGradeButton("Delete Point", () => {
      if (points.length <= 1) return;
      const nextPoints = clonePoints(points);
      nextPoints.splice(selectedIndex, 1);
      syncPoints(nextPoints, Math.max(0, selectedIndex - 1));
    }));
    inspectorBody.appendChild(actionRow);

    const metrics = document.createElement("div");
    metrics.className = "mkr-grade-note";
    metrics.textContent = `${formatGridLabel(selectedIndex)} source (${formatNumber(selected.src_x)}, ${formatNumber(selected.src_y)}) -> dest (${formatNumber(selected.dst_x)}, ${formatNumber(selected.dst_y)})`;
    inspectorBody.appendChild(metrics);
  }

  function draw() {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    ctx.clearRect(0, 0, width, height);

    const graph = buildGraphRect(width, height);
    const background = getMeshBackground(kind, Math.round(graph.w), Math.round(graph.h));
    ctx.drawImage(background, graph.x, graph.y, graph.w, graph.h);
    ctx.fillStyle = "rgba(10, 12, 16, 0.10)";
    ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

    ctx.strokeStyle = "rgba(210, 220, 230, 0.18)";
    ctx.lineWidth = 1;
    for (let index = 0; index <= 10; index += 1) {
      const gx = graph.x + (graph.w * index / 10);
      const gy = graph.y + (graph.h * index / 10);
      ctx.beginPath();
      ctx.moveTo(gx, graph.y);
      ctx.lineTo(gx, graph.y + graph.h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(graph.x, gy);
      ctx.lineTo(graph.x + graph.w, gy);
      ctx.stroke();
    }

    drawLabelChip(ctx, isHueSat ? "Hue" : "Chroma", graph.x + 38, graph.y + 18);
    drawLabelChip(ctx, isHueSat ? "Saturation" : "Luma", graph.x + 52, graph.y + graph.h - 16, {
      paddingX: 8,
    });

    drawMeshLines(ctx, graph, points, "source", "rgba(245, 248, 252, 0.18)", 1.0, true);
    drawMeshLines(ctx, graph, points, "destination", isHueSat ? "rgba(255, 128, 92, 0.54)" : "rgba(45, 156, 143, 0.54)", 1.6, false);

    points.forEach((point, index) => {
      const src = toScreen(graph, point.src_x, point.src_y);
      const dst = toScreen(graph, point.dst_x, point.dst_y);
      if (index === selectedIndex) {
        const radius = Math.max(14, Math.min(graph.w, graph.h) * point.radius);
        ctx.beginPath();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.30)";
        ctx.lineWidth = 1;
        ctx.arc(dst.x, dst.y, radius, 0, Math.PI * 2);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(dst.x, dst.y);
        ctx.strokeStyle = "rgba(240, 244, 248, 0.62)";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.fillStyle = index === selectedIndex ? "rgba(246, 249, 252, 0.98)" : "rgba(224, 231, 239, 0.72)";
      ctx.arc(src.x, src.y, index === selectedIndex ? 4.4 : 3.2, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.fillStyle = index === selectedIndex ? "#fffdf8" : (isHueSat ? "#ff7a62" : "#2d9c8f");
      ctx.arc(dst.x, dst.y, index === selectedIndex ? 5.8 : 4.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(18, 24, 32, 0.84)";
      ctx.lineWidth = 1.2;
      ctx.stroke();
    });
  }

  function resolvePoint(event) {
    const rect = canvas.getBoundingClientRect();
    const graph = buildGraphRect(rect.width, rect.height);
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;

    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const dst = toScreen(graph, point.dst_x, point.dst_y);
      if (Math.hypot(pointerX - dst.x, pointerY - dst.y) <= 12) {
        selectedIndex = index;
        renderPointChips();
        renderInspector();
        updatePills();
        draw();
        return index;
      }
    }
    return -1;
  }

  function updateActivePoint(event) {
    if (activeIndex < 0 || !points[activeIndex]) return;
    const rect = canvas.getBoundingClientRect();
    const graph = buildGraphRect(rect.width, rect.height);
    const pointer = fromScreen(graph, event.clientX - rect.left, event.clientY - rect.top);
    const nextPoints = clonePoints(points);
    nextPoints[activeIndex].dst_x = pointer.x;
    nextPoints[activeIndex].dst_y = pointer.y;
    syncPoints(nextPoints, activeIndex);
  }

  canvas.addEventListener("pointerdown", (event) => {
    const resolved = resolvePoint(event);
    if (resolved < 0) return;
    activeIndex = resolved;
    canvas.setPointerCapture?.(event.pointerId);
    updateActivePoint(event);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (activeIndex < 0) return;
    updateActivePoint(event);
  });

  const stopDrag = (event) => {
    if (activeIndex < 0) return;
    activeIndex = -1;
    canvas.releasePointerCapture?.(event.pointerId);
  };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
  }

  function refresh() {
    const latestPoints = normalizeMeshPoints(parsePoints(getValue(node, "warp_points_json", "[]")));
    if (latestPoints.length) {
      points = latestPoints;
    }
    if (!points.length) {
      points = writePoints(node, buildPresetPoints(kind, "reset"));
    }
    selectedIndex = clamp(selectedIndex, 0, Math.max(0, points.length - 1));
    strengthControl.setValue(getNumber(node, "strength", isHueSat ? 0.7 : 0.65));
    falloffControl.setValue(getNumber(node, "falloff", 1.0));
    mixControl.setValue(getNumber(node, "mix", 1.0));
    featherControl.setValue(getNumber(node, "mask_feather", 12.0));
    invertControl.setValue(getBoolean(node, "invert_mask", false));
    updatePills();
    renderPointChips();
    renderInspector();
    draw();
  }

  refresh();
  return { panel, refresh };
}

function installWarpStudio(node) {
  const nodeName = String(node?.comfyClass || node?.type || "");
  if (!TARGETS.has(nodeName)) return;
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: getDefaultSettings(nodeName),
    numericSpecs: NUMERIC_SPECS,
    booleanKeys: BOOLEAN_KEYS,
    legacyNames: LEGACY_WIDGETS,
  });
  if (node.__mkrColorWarpStudioInstalled) {
    node.__mkrColorWarpRefresh?.();
    normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);
    return;
  }
  node.__mkrColorWarpStudioInstalled = true;
  const { panel, refresh } = buildWarpPanel(node);
  node.__mkrColorWarpRefresh = refresh;
  attachPanel(node, PANEL_NAME, panel, WARP_PANEL_WIDTH, WARP_PANEL_HEIGHT);
  normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);
  installRefreshHooks(node, "__mkrColorWarpRefreshHooksInstalled", refresh);
  requestAnimationFrame(() => refresh());
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TARGETS.has(nodeData?.name)) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = originalOnNodeCreated?.apply(this, arguments);
      installWarpStudio(this);
      return result;
    };
  },
  async nodeCreated(node) {
    installWarpStudio(node);
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      installWarpStudio(node);
    }
  },
});
