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
  formatSigned,
  getBoolean,
  getNumber,
  installBundledSettingsAdapter,
  matchesNode,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ColorQualifierBalanceStudio";
const QUALIFIER_NODE = "x1HSLQualifier";
const BALANCE_NODE = "x1ColorBalance";
const GAMUT_NODE = "x1GamutMap";
const QUALIFIER_PANEL = "mkr_color_hsl_qualifier_studio";
const BALANCE_PANEL = "mkr_color_balance_studio";
const GAMUT_PANEL = "mkr_color_gamut_map_studio";
const STYLE_ID = "mkr-qualifier-balance-v1";
const SETTINGS_WIDGET_NAME = "settings_json";
const QUALIFIER_PANEL_WIDTH = 760;
const QUALIFIER_PANEL_HEIGHT = 900;
const GAMUT_PANEL_WIDTH = 780;
const GAMUT_PANEL_HEIGHT = 830;

const QUALIFIER_LEGACY_WIDGETS = [
  "hue_center",
  "hue_width",
  "sat_min",
  "sat_max",
  "val_min",
  "val_max",
  "feather",
  "hue_shift",
  "sat_shift",
  "val_shift",
  "amount",
  "show_matte",
  "mask_feather",
  "invert_mask",
];
const QUALIFIER_HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...QUALIFIER_LEGACY_WIDGETS];

const BALANCE_LEGACY_WIDGETS = [
  "slope_r",
  "slope_g",
  "slope_b",
  "offset_r",
  "offset_g",
  "offset_b",
  "power_r",
  "power_g",
  "power_b",
  "saturation",
  "mix",
  "preserve_luma",
  "mask_feather",
  "invert_mask",
];
const BALANCE_HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...BALANCE_LEGACY_WIDGETS];

const GAMUT_LEGACY_WIDGETS = [
  "compression",
  "rolloff",
  "saturation",
  "highlight_protect",
  "neutral_protect",
  "preserve_luma",
  "mix",
  "mask_feather",
  "invert_mask",
];
const GAMUT_HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...GAMUT_LEGACY_WIDGETS];

const QUALIFIER_DEFAULT_SETTINGS = {
  hue_center: 220.0,
  hue_width: 40.0,
  sat_min: 0.08,
  sat_max: 1.0,
  val_min: 0.05,
  val_max: 1.0,
  feather: 18.0,
  hue_shift: 0.0,
  sat_shift: 0.25,
  val_shift: 0.0,
  amount: 1.0,
  show_matte: false,
  mask_feather: 12.0,
  invert_mask: false,
};

const QUALIFIER_NUMERIC_SPECS = {
  hue_center: { min: 0.0, max: 360.0 },
  hue_width: { min: 1.0, max: 180.0 },
  sat_min: { min: 0.0, max: 1.0 },
  sat_max: { min: 0.0, max: 1.0 },
  val_min: { min: 0.0, max: 1.0 },
  val_max: { min: 0.0, max: 1.0 },
  feather: { min: 0.0, max: 120.0 },
  hue_shift: { min: -180.0, max: 180.0 },
  sat_shift: { min: -1.0, max: 1.0 },
  val_shift: { min: -1.0, max: 1.0 },
  amount: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const QUALIFIER_BOOLEAN_KEYS = ["show_matte", "invert_mask"];

const BALANCE_DEFAULT_SETTINGS = {
  slope_r: 1.0,
  slope_g: 1.0,
  slope_b: 1.0,
  offset_r: 0.0,
  offset_g: 0.0,
  offset_b: 0.0,
  power_r: 1.0,
  power_g: 1.0,
  power_b: 1.0,
  saturation: 1.0,
  mix: 1.0,
  preserve_luma: true,
  mask_feather: 12.0,
  invert_mask: false,
};

const BALANCE_NUMERIC_SPECS = {
  slope_r: { min: 0.0, max: 3.0 },
  slope_g: { min: 0.0, max: 3.0 },
  slope_b: { min: 0.0, max: 3.0 },
  offset_r: { min: -1.0, max: 1.0 },
  offset_g: { min: -1.0, max: 1.0 },
  offset_b: { min: -1.0, max: 1.0 },
  power_r: { min: 0.1, max: 3.0 },
  power_g: { min: 0.1, max: 3.0 },
  power_b: { min: 0.1, max: 3.0 },
  saturation: { min: 0.0, max: 2.0 },
  mix: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const BALANCE_BOOLEAN_KEYS = ["preserve_luma", "invert_mask"];

const GAMUT_DEFAULT_SETTINGS = {
  compression: 0.25,
  rolloff: 0.35,
  saturation: 1.0,
  highlight_protect: 0.25,
  neutral_protect: 0.35,
  preserve_luma: true,
  mix: 1.0,
  mask_feather: 12.0,
  invert_mask: false,
};

const GAMUT_NUMERIC_SPECS = {
  compression: { min: -1.0, max: 1.0 },
  rolloff: { min: 0.0, max: 1.0 },
  saturation: { min: 0.0, max: 2.0 },
  highlight_protect: { min: 0.0, max: 1.0 },
  neutral_protect: { min: 0.0, max: 1.0 },
  mix: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const GAMUT_BOOLEAN_KEYS = ["preserve_luma", "invert_mask"];

const QUALIFIER_PRESETS = {
  skin: {
    hue_center: 28,
    hue_width: 54,
    sat_min: 0.12,
    sat_max: 0.82,
    val_min: 0.18,
    val_max: 1.0,
    feather: 20,
    hue_shift: -6,
    sat_shift: 0.08,
    val_shift: 0.03,
    amount: 1.0,
  },
  sky: {
    hue_center: 210,
    hue_width: 58,
    sat_min: 0.14,
    sat_max: 1.0,
    val_min: 0.20,
    val_max: 1.0,
    feather: 18,
    hue_shift: -10,
    sat_shift: 0.12,
    val_shift: 0.02,
    amount: 1.0,
  },
  foliage: {
    hue_center: 118,
    hue_width: 50,
    sat_min: 0.10,
    sat_max: 1.0,
    val_min: 0.08,
    val_max: 0.96,
    feather: 22,
    hue_shift: 5,
    sat_shift: 0.10,
    val_shift: -0.02,
    amount: 1.0,
  },
  magenta: {
    hue_center: 320,
    hue_width: 44,
    sat_min: 0.12,
    sat_max: 1.0,
    val_min: 0.10,
    val_max: 1.0,
    feather: 16,
    hue_shift: 12,
    sat_shift: 0.14,
    val_shift: 0.04,
    amount: 1.0,
  },
};

const BALANCE_PRESETS = {
  neutral: {
    slope_r: 1.0,
    slope_g: 1.0,
    slope_b: 1.0,
    offset_r: 0.0,
    offset_g: 0.0,
    offset_b: 0.0,
    power_r: 1.0,
    power_g: 1.0,
    power_b: 1.0,
    saturation: 1.0,
    mix: 1.0,
    preserve_luma: true,
  },
  warm_print: {
    slope_r: 1.08,
    slope_g: 1.02,
    slope_b: 0.95,
    offset_r: 0.01,
    offset_g: 0.0,
    offset_b: -0.015,
    power_r: 0.96,
    power_g: 1.0,
    power_b: 1.04,
    saturation: 1.06,
    mix: 1.0,
    preserve_luma: true,
  },
  cool_lift: {
    slope_r: 0.96,
    slope_g: 1.0,
    slope_b: 1.08,
    offset_r: -0.01,
    offset_g: 0.0,
    offset_b: 0.02,
    power_r: 1.02,
    power_g: 1.0,
    power_b: 0.95,
    saturation: 0.98,
    mix: 1.0,
    preserve_luma: true,
  },
  silver_punch: {
    slope_r: 1.03,
    slope_g: 1.03,
    slope_b: 1.03,
    offset_r: -0.02,
    offset_g: -0.02,
    offset_b: -0.02,
    power_r: 1.08,
    power_g: 1.08,
    power_b: 1.08,
    saturation: 0.78,
    mix: 1.0,
    preserve_luma: true,
  },
};

const GAMUT_PRESETS = {
  safe: {
    compression: 0.30,
    rolloff: 0.58,
    saturation: 0.96,
    highlight_protect: 0.56,
    neutral_protect: 0.52,
    preserve_luma: true,
    mix: 1.0,
  },
  print: {
    compression: 0.44,
    rolloff: 0.76,
    saturation: 0.90,
    highlight_protect: 0.42,
    neutral_protect: 0.46,
    preserve_luma: true,
    mix: 1.0,
  },
  neon_relax: {
    compression: 0.64,
    rolloff: 0.42,
    saturation: 1.02,
    highlight_protect: 0.12,
    neutral_protect: 0.18,
    preserve_luma: false,
    mix: 1.0,
  },
  open_up: {
    compression: -0.18,
    rolloff: 0.26,
    saturation: 1.08,
    highlight_protect: 0.20,
    neutral_protect: 0.24,
    preserve_luma: true,
    mix: 0.88,
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-qualifier-canvases {
      display: grid;
      gap: 10px;
    }

    .mkr-qualifier-band,
    .mkr-qualifier-box,
    .mkr-balance-graph {
      display: block;
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(16,18,22,0.96), rgba(28,31,36,0.96));
      box-sizing: border-box;
    }

    .mkr-qualifier-band {
      height: 88px;
      cursor: ew-resize;
    }

    .mkr-qualifier-box {
      height: 218px;
      cursor: move;
    }

    .mkr-qualifier-hint {
      margin-top: 6px;
      font-size: 11px;
      line-height: 1.35;
      color: rgba(225,231,238,0.52);
    }

    .mkr-balance-graph {
      height: 224px;
    }

    .mkr-gamut-graph {
      display: block;
      width: 100%;
      height: 236px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(16,18,22,0.96), rgba(28,31,36,0.96));
      box-sizing: border-box;
    }

    .mkr-balance-triplets {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .mkr-balance-card {
      padding: 8px;
      border-radius: 12px;
      background: rgba(255,255,255,0.035);
      border: 1px solid rgba(255,255,255,0.06);
    }

    .mkr-balance-card-title {
      margin-bottom: 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(236,242,246,0.76);
    }

    .mkr-balance-row {
      display: grid;
      grid-template-columns: 26px 1fr 58px;
      gap: 8px;
      align-items: center;
    }

    .mkr-balance-row + .mkr-balance-row {
      margin-top: 8px;
    }

    .mkr-balance-chip {
      height: 22px;
      border-radius: 999px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      font-weight: 700;
      color: rgba(255,255,255,0.88);
    }

    .mkr-balance-chip[data-channel="r"] {
      background: rgba(255,91,82,0.24);
      border: 1px solid rgba(255,91,82,0.36);
    }

    .mkr-balance-chip[data-channel="g"] {
      background: rgba(57,198,109,0.20);
      border: 1px solid rgba(57,198,109,0.32);
    }

    .mkr-balance-chip[data-channel="b"] {
      background: rgba(76,141,255,0.20);
      border: 1px solid rgba(76,141,255,0.32);
    }

    .mkr-balance-row input[type="range"] {
      width: 100%;
      accent-color: var(--mkr-grade-accent, #4c8dff);
    }

    .mkr-balance-row input[type="number"] {
      width: 100%;
      border-radius: 9px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(7,8,10,0.48);
      color: rgba(244,248,252,0.92);
      padding: 6px 7px;
      font-size: 11px;
      box-sizing: border-box;
    }

    @media (max-width: 760px) {
      .mkr-balance-triplets {
        grid-template-columns: 1fr;
      }
    }
  `;
  document.head.appendChild(style);
}

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values)) {
    setWidgetValue(node, key, value);
  }
}

function installQualifierAdapter(node) {
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: QUALIFIER_DEFAULT_SETTINGS,
    numericSpecs: QUALIFIER_NUMERIC_SPECS,
    booleanKeys: QUALIFIER_BOOLEAN_KEYS,
    legacyNames: QUALIFIER_LEGACY_WIDGETS,
  });
}

function installBalanceAdapter(node) {
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: BALANCE_DEFAULT_SETTINGS,
    numericSpecs: BALANCE_NUMERIC_SPECS,
    booleanKeys: BALANCE_BOOLEAN_KEYS,
    legacyNames: BALANCE_LEGACY_WIDGETS,
  });
}

function installGamutAdapter(node) {
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: GAMUT_DEFAULT_SETTINGS,
    numericSpecs: GAMUT_NUMERIC_SPECS,
    booleanKeys: GAMUT_BOOLEAN_KEYS,
    legacyNames: GAMUT_LEGACY_WIDGETS,
  });
}

function smoothstep(edge0, edge1, value) {
  if (edge1 <= edge0) return value >= edge1 ? 1 : 0;
  const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - (2 * t));
}

function computeGamutKnee(rolloff) {
  return clamp(0.72 - (rolloff * 0.48), 0.12, 0.84);
}

function computeGamutMappedSaturation(sourceSat, sourceValue, settings) {
  const compression = settings.compression;
  const rolloff = settings.rolloff;
  const saturation = settings.saturation;
  const highlightProtect = settings.highlight_protect;
  const neutralProtect = settings.neutral_protect;
  const knee = computeGamutKnee(rolloff);
  const onset = smoothstep(knee, 1.0, sourceSat);
  const rollShape = Math.pow(onset, 0.85 + ((1.0 - rolloff) * 0.95));
  const highlightGuard = 1.0 - (highlightProtect * smoothstep(0.56 - (rolloff * 0.10), 1.0, sourceValue));
  const neutralGuard = 1.0 - (neutralProtect * (1.0 - smoothstep(0.04, 0.30, sourceSat)));
  const effect = clamp(rollShape * highlightGuard * neutralGuard, 0, 1);
  let mapped = compression >= 0
    ? sourceSat - (Math.max(sourceSat - knee, 0) * compression * effect)
    : sourceSat + ((1 - sourceSat) * Math.abs(compression) * effect);
  mapped *= saturation;
  return clamp(mapped, 0, 1);
}

function hueGradient(width) {
  const gradientStops = [
    [0.0, "#ff4f4f"],
    [0.17, "#ffd447"],
    [0.33, "#4cff68"],
    [0.5, "#42d6ff"],
    [0.67, "#4b72ff"],
    [0.83, "#d34dff"],
    [1.0, "#ff4f4f"],
  ];
  return { width, gradientStops };
}

function hueToColor(hueDegrees) {
  const h = ((Number(hueDegrees) % 360) + 360) % 360;
  return `hsl(${h}deg 86% 58%)`;
}

function hueToX(hue, graph) {
  return graph.x + ((((hue % 360) + 360) % 360) / 360) * graph.w;
}

function xToHue(x, graph) {
  return clamp((x - graph.x) / Math.max(1, graph.w), 0, 1) * 360;
}

function wrapHueDistance(a, b) {
  return ((((a - b) % 360) + 540) % 360) - 180;
}

function setHueMetrics(node, metrics) {
  const center = getNumber(node, "hue_center", 220);
  const width = getNumber(node, "hue_width", 40);
  metrics.center.setValue(`${Math.round(center)}°`);
  metrics.width.setValue(`${Math.round(width)}°`);
  metrics.amount.setValue(formatNumber(getNumber(node, "amount", 1)));
}

function drawHueBand(canvas, node) {
  const { ctx, width, height } = ensureCanvasResolution(canvas);
  ctx.clearRect(0, 0, width, height);
  const graph = { x: 16, y: 18, w: width - 32, h: height - 36 };

  const bg = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y);
  for (const [stop, color] of hueGradient(graph.w).gradientStops) bg.addColorStop(stop, color);
  ctx.fillStyle = bg;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.fillStyle = "rgba(10,12,16,0.28)";
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  const center = getNumber(node, "hue_center", 220);
  const widthDeg = clamp(getNumber(node, "hue_width", 40), 1, 180);
  const feather = clamp(getNumber(node, "feather", 18), 0, 120);
  const left = hueToX(center - (widthDeg * 0.5), graph);
  const right = hueToX(center + (widthDeg * 0.5), graph);
  const centerX = hueToX(center, graph);

  const drawBand = (x0, x1) => {
    const bandWidth = Math.max(2, x1 - x0);
    ctx.fillStyle = "rgba(255,255,255,0.16)";
    ctx.fillRect(x0, graph.y, bandWidth, graph.h);
    const fringe = Math.max(8, (feather / 120) * 44);
    const fadeLeft = ctx.createLinearGradient(x0 - fringe, 0, x0, 0);
    fadeLeft.addColorStop(0, "rgba(255,255,255,0)");
    fadeLeft.addColorStop(1, "rgba(255,255,255,0.22)");
    ctx.fillStyle = fadeLeft;
    ctx.fillRect(x0 - fringe, graph.y, fringe, graph.h);
    const fadeRight = ctx.createLinearGradient(x1, 0, x1 + fringe, 0);
    fadeRight.addColorStop(0, "rgba(255,255,255,0.22)");
    fadeRight.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = fadeRight;
    ctx.fillRect(x1, graph.y, fringe, graph.h);
  };

  if (left <= right) {
    drawBand(left, right);
  } else {
    drawBand(graph.x, right);
    drawBand(left, graph.x + graph.w);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.72)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(centerX, graph.y - 3);
  ctx.lineTo(centerX, graph.y + graph.h + 3);
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);
}

function drawQualifierBox(canvas, node) {
  const { ctx, width, height } = ensureCanvasResolution(canvas);
  ctx.clearRect(0, 0, width, height);
  const graph = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const hue = getNumber(node, "hue_center", 220);

  const satGradient = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y);
  satGradient.addColorStop(0, "rgba(255,255,255,0.06)");
  satGradient.addColorStop(1, hueToColor(hue));
  ctx.fillStyle = satGradient;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  const valueGradient = ctx.createLinearGradient(graph.x, graph.y + graph.h, graph.x, graph.y);
  valueGradient.addColorStop(0, "rgba(0,0,0,0.82)");
  valueGradient.addColorStop(0.55, "rgba(0,0,0,0.16)");
  valueGradient.addColorStop(1, "rgba(255,255,255,0.08)");
  ctx.fillStyle = valueGradient;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const x = graph.x + (graph.w * step / 4);
    const y = graph.y + (graph.h * step / 4);
    ctx.beginPath();
    ctx.moveTo(x, graph.y);
    ctx.lineTo(x, graph.y + graph.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(graph.x, y);
    ctx.lineTo(graph.x + graph.w, y);
    ctx.stroke();
  }

  const satMin = clamp(getNumber(node, "sat_min", 0.08), 0, 1);
  const satMax = clamp(getNumber(node, "sat_max", 1.0), 0, 1);
  const valMin = clamp(getNumber(node, "val_min", 0.05), 0, 1);
  const valMax = clamp(getNumber(node, "val_max", 1.0), 0, 1);
  const x = graph.x + (satMin * graph.w);
  const y = graph.y + ((1 - valMax) * graph.h);
  const w = Math.max(2, (satMax - satMin) * graph.w);
  const h = Math.max(2, (valMax - valMin) * graph.h);

  ctx.fillStyle = "rgba(255,255,255,0.10)";
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.80)";
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, w, h);

  const handle = 8;
  ctx.fillStyle = hueToColor(hue);
  for (const [hx, hy] of [
    [x, y],
    [x + w, y],
    [x, y + h],
    [x + w, y + h],
  ]) {
    ctx.beginPath();
    ctx.arc(hx, hy, handle * 0.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(12,14,18,0.9)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);
}

function buildQualifierPanel(node) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "HSL Qualifier Studio",
    subtitle: "Pull a hue key with a real qualifier surface instead of scanning a long widget stack.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#45d68c");
  panel.style.paddingBottom = "18px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const centerMetric = createGradeMetric("Center", "220°");
  const widthMetric = createGradeMetric("Width", "40°");
  const amountMetric = createGradeMetric("Amount", "1.00");
  metricsWrap.appendChild(centerMetric.element);
  metricsWrap.appendChild(widthMetric.element);
  metricsWrap.appendChild(amountMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Skin", () => { applyValues(node, QUALIFIER_PRESETS.skin); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Sky", () => { applyValues(node, QUALIFIER_PRESETS.sky); refreshPanel(); }));
  actions.appendChild(createGradeButton("Foliage", () => { applyValues(node, QUALIFIER_PRESETS.foliage); refreshPanel(); }));
  actions.appendChild(createGradeButton("Magenta", () => { applyValues(node, QUALIFIER_PRESETS.magenta); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const qualifierSection = createGradeSection("Qualifier Surfaces", "drag center • shift drag range");
  const canvases = document.createElement("div");
  canvases.className = "mkr-qualifier-canvases";
  const hueCanvas = document.createElement("canvas");
  hueCanvas.className = "mkr-qualifier-band";
  const svCanvas = document.createElement("canvas");
  svCanvas.className = "mkr-qualifier-box";
  canvases.appendChild(hueCanvas);
  canvases.appendChild(svCanvas);
  qualifierSection.body.appendChild(canvases);

  const readouts = document.createElement("div");
  readouts.className = "mkr-grade-inline";
  const hueReadout = createGradeReadout("Hue", "220°");
  const satReadout = createGradeReadout("Sat", "0.08-1.00");
  const valReadout = createGradeReadout("Val", "0.05-1.00");
  readouts.appendChild(hueReadout.element);
  readouts.appendChild(satReadout.element);
  readouts.appendChild(valReadout.element);
  qualifierSection.body.appendChild(readouts);
  const hint = document.createElement("div");
  hint.className = "mkr-qualifier-hint";
  hint.textContent = "Drag the hue band to move the key. Hold Shift on either surface to resize the range around the current center instead of moving it.";
  qualifierSection.body.appendChild(hint);
  panel.appendChild(qualifierSection.section);

  const shiftSection = createGradeSection("Qualifier Shift", "secondary response");
  const shiftControls = document.createElement("div");
  shiftControls.className = "mkr-grade-controls";
  const hueShift = createGradeSlider({
    label: "Hue Shift",
    min: -180,
    max: 180,
    step: 0.5,
    value: getNumber(node, "hue_shift", 0),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "hue_shift", value); refreshPanel(); },
  });
  const satShift = createGradeSlider({
    label: "Sat Shift",
    min: -1,
    max: 1,
    step: 0.01,
    value: getNumber(node, "sat_shift", 0.25),
    onChange: (value) => { setWidgetValue(node, "sat_shift", value); refreshPanel(); },
  });
  const valShift = createGradeSlider({
    label: "Val Shift",
    min: -1,
    max: 1,
    step: 0.01,
    value: getNumber(node, "val_shift", 0),
    onChange: (value) => { setWidgetValue(node, "val_shift", value); refreshPanel(); },
  });
  const amount = createGradeSlider({
    label: "Amount",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "amount", 1),
    onChange: (value) => { setWidgetValue(node, "amount", value); refreshPanel(); },
  });
  const feather = createGradeSlider({
    label: "Feather",
    min: 0,
    max: 120,
    step: 0.5,
    value: getNumber(node, "feather", 18),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "feather", value); refreshPanel(); },
  });
  shiftControls.appendChild(hueShift.element);
  shiftControls.appendChild(satShift.element);
  shiftControls.appendChild(valShift.element);
  shiftControls.appendChild(amount.element);
  shiftControls.appendChild(feather.element);
  shiftSection.body.appendChild(shiftControls);
  panel.appendChild(shiftSection.section);

  const maskSection = createGradeSection("Mask Response", "delivery");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const showMatte = createGradeToggle({
    label: "Show Matte",
    checked: getBoolean(node, "show_matte", false),
    description: "Display the qualifier matte instead of the graded result.",
    onChange: (checked) => { setWidgetValue(node, "show_matte", checked); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before it gates the qualifier.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(showMatte.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  maskSection.section.style.paddingBottom = "8px";
  panel.appendChild(maskSection.section);

  let hueDragMode = null;
  const onHuePointer = (event) => {
    const rect = hueCanvas.getBoundingClientRect();
    if (!rect.width) return;
    const localX = clamp(event.clientX - rect.left, 0, rect.width);
    const graph = { x: 16, y: 18, w: rect.width - 32, h: rect.height - 36 };
    const hue = xToHue(localX, graph);
    if (hueDragMode === "range") {
      const center = getNumber(node, "hue_center", 220);
      const width = clamp(Math.abs(wrapHueDistance(hue, center)) * 2, 1, 180);
      setWidgetValue(node, "hue_width", width);
    } else {
      setWidgetValue(node, "hue_center", hue);
    }
    refreshPanel();
  };

  hueCanvas.addEventListener("pointerdown", (event) => {
    hueDragMode = event.shiftKey ? "range" : "center";
    hueCanvas.setPointerCapture?.(event.pointerId);
    onHuePointer(event);
  });
  hueCanvas.addEventListener("pointermove", (event) => {
    if (!hueDragMode) return;
    onHuePointer(event);
  });
  const stopHueDrag = (event) => {
    if (!hueDragMode) return;
    hueDragMode = null;
    hueCanvas.releasePointerCapture?.(event.pointerId);
  };
  hueCanvas.addEventListener("pointerup", stopHueDrag);
  hueCanvas.addEventListener("pointercancel", stopHueDrag);

  let boxDragMode = null;
  const onBoxPointer = (event) => {
    const rect = svCanvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const localX = clamp(event.clientX - rect.left, 0, rect.width);
    const localY = clamp(event.clientY - rect.top, 0, rect.height);
    const graph = { x: 18, y: 18, w: rect.width - 36, h: rect.height - 36 };
    const sat = clamp((localX - graph.x) / Math.max(1, graph.w), 0, 1);
    const val = 1 - clamp((localY - graph.y) / Math.max(1, graph.h), 0, 1);
    let satMin = clamp(getNumber(node, "sat_min", 0.08), 0, 1);
    let satMax = clamp(getNumber(node, "sat_max", 1.0), 0, 1);
    let valMin = clamp(getNumber(node, "val_min", 0.05), 0, 1);
    let valMax = clamp(getNumber(node, "val_max", 1.0), 0, 1);

    if (boxDragMode === "range") {
      const satCenter = (satMin + satMax) * 0.5;
      const valCenter = (valMin + valMax) * 0.5;
      const satHalf = clamp(Math.abs(sat - satCenter), 0.04, 0.5);
      const valHalf = clamp(Math.abs(val - valCenter), 0.04, 0.5);
      satMin = clamp(satCenter - satHalf, 0, 1);
      satMax = clamp(satCenter + satHalf, 0, 1);
      valMin = clamp(valCenter - valHalf, 0, 1);
      valMax = clamp(valCenter + valHalf, 0, 1);
    } else {
      const satHalf = (satMax - satMin) * 0.5;
      const valHalf = (valMax - valMin) * 0.5;
      const satCenter = clamp(sat, satHalf, 1 - satHalf);
      const valCenter = clamp(val, valHalf, 1 - valHalf);
      satMin = clamp(satCenter - satHalf, 0, 1);
      satMax = clamp(satCenter + satHalf, 0, 1);
      valMin = clamp(valCenter - valHalf, 0, 1);
      valMax = clamp(valCenter + valHalf, 0, 1);
    }

    setWidgetValue(node, "sat_min", Math.min(satMin, satMax));
    setWidgetValue(node, "sat_max", Math.max(satMin, satMax));
    setWidgetValue(node, "val_min", Math.min(valMin, valMax));
    setWidgetValue(node, "val_max", Math.max(valMin, valMax));
    refreshPanel();
  };

  svCanvas.addEventListener("pointerdown", (event) => {
    boxDragMode = event.shiftKey ? "range" : "move";
    svCanvas.setPointerCapture?.(event.pointerId);
    onBoxPointer(event);
  });
  svCanvas.addEventListener("pointermove", (event) => {
    if (!boxDragMode) return;
    onBoxPointer(event);
  });
  const stopBoxDrag = (event) => {
    if (!boxDragMode) return;
    boxDragMode = null;
    svCanvas.releasePointerCapture?.(event.pointerId);
  };
  svCanvas.addEventListener("pointerup", stopBoxDrag);
  svCanvas.addEventListener("pointercancel", stopBoxDrag);

  function refreshPanel() {
    setHueMetrics(node, {
      center: centerMetric,
      width: widthMetric,
      amount: amountMetric,
    });
    drawHueBand(hueCanvas, node);
    drawQualifierBox(svCanvas, node);
    const hueCenter = getNumber(node, "hue_center", 220);
    hueReadout.setValue(`${Math.round(hueCenter)}°`);
    satReadout.setValue(`${formatNumber(getNumber(node, "sat_min", 0.08))}-${formatNumber(getNumber(node, "sat_max", 1.0))}`);
    valReadout.setValue(`${formatNumber(getNumber(node, "val_min", 0.05))}-${formatNumber(getNumber(node, "val_max", 1.0))}`);
    hueShift.setValue(getNumber(node, "hue_shift", 0));
    satShift.setValue(getNumber(node, "sat_shift", 0.25));
    valShift.setValue(getNumber(node, "val_shift", 0));
    amount.setValue(getNumber(node, "amount", 1));
    feather.setValue(getNumber(node, "feather", 18));
    maskFeather.setValue(getNumber(node, "mask_feather", 12));
    showMatte.setValue(getBoolean(node, "show_matte", false));
    invertMask.setValue(getBoolean(node, "invert_mask", false));
  }

  refreshPanel();
  attachPanel(node, QUALIFIER_PANEL, panel, QUALIFIER_PANEL_WIDTH, QUALIFIER_PANEL_HEIGHT);
  normalizePanelNode(node, QUALIFIER_HIDDEN_WIDGETS, QUALIFIER_PANEL);
  installRefreshHooks(node, "__mkrQualifierRefreshHooksInstalled", refreshPanel);
  requestAnimationFrame(() => refreshPanel());
  node.__mkrQualifierRefresh = refreshPanel;
}

function createTripletCard({ title, min, max, step, decimals = 2, accent, rows }) {
  const card = document.createElement("div");
  card.className = "mkr-balance-card";
  const titleNode = document.createElement("div");
  titleNode.className = "mkr-balance-card-title";
  titleNode.textContent = title;
  card.appendChild(titleNode);

  const controls = [];
  for (const row of rows) {
    const line = document.createElement("div");
    line.className = "mkr-balance-row";

    const chip = document.createElement("div");
    chip.className = "mkr-balance-chip";
    chip.dataset.channel = row.channel;
    chip.textContent = row.channel.toUpperCase();

    const range = document.createElement("input");
    range.type = "range";
    range.min = String(min);
    range.max = String(max);
    range.step = String(step);
    range.value = String(row.value);
    if (accent) range.style.accentColor = accent;

    const number = document.createElement("input");
    number.type = "number";
    number.min = String(min);
    number.max = String(max);
    number.step = String(step);
    number.value = Number(row.value).toFixed(decimals);

    const commit = (raw) => {
      const parsed = Number.parseFloat(String(raw));
      const next = Number.isFinite(parsed) ? clamp(parsed, min, max) : row.value;
      range.value = String(next);
      number.value = next.toFixed(decimals);
      row.onChange(next);
    };

    range.addEventListener("input", () => commit(range.value));
    number.addEventListener("change", () => commit(number.value));

    line.appendChild(chip);
    line.appendChild(range);
    line.appendChild(number);
    card.appendChild(line);

    controls.push({
      setValue(next) {
        const normalized = clamp(Number(next) || 0, min, max);
        range.value = String(normalized);
        number.value = normalized.toFixed(decimals);
      },
    });
  }

  return { element: card, controls };
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

function readGamutSettings(node) {
  return {
    compression: getNumber(node, "compression", 0.25),
    rolloff: getNumber(node, "rolloff", 0.35),
    saturation: getNumber(node, "saturation", 1.0),
    highlight_protect: getNumber(node, "highlight_protect", 0.25),
    neutral_protect: getNumber(node, "neutral_protect", 0.35),
    preserve_luma: getBoolean(node, "preserve_luma", true),
    mix: getNumber(node, "mix", 1.0),
    mask_feather: getNumber(node, "mask_feather", 12.0),
    invert_mask: getBoolean(node, "invert_mask", false),
  };
}

function drawGamutGraph(canvas, node) {
  const settings = readGamutSettings(node);
  const { ctx, width, height } = ensureCanvasResolution(canvas);
  ctx.clearRect(0, 0, width, height);
  const graph = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const knee = computeGamutKnee(settings.rolloff);

  const bg = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y + graph.h);
  bg.addColorStop(0, "rgba(11,13,16,0.98)");
  bg.addColorStop(1, "rgba(25,28,34,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.fillStyle = "rgba(255,255,255,0.028)";
  ctx.fillRect(graph.x, graph.y, graph.w * knee, graph.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 5; step += 1) {
    const x = graph.x + (graph.w * step / 5);
    const y = graph.y + (graph.h * step / 5);
    ctx.beginPath();
    ctx.moveTo(x, graph.y);
    ctx.lineTo(x, graph.y + graph.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(graph.x, y);
    ctx.lineTo(graph.x + graph.w, y);
    ctx.stroke();
  }

  const satStripY = graph.y + graph.h - 20;
  const satStrip = ctx.createLinearGradient(graph.x, satStripY, graph.x + graph.w, satStripY);
  satStrip.addColorStop(0, "rgba(181,189,197,0.12)");
  satStrip.addColorStop(0.5, "rgba(89,143,255,0.18)");
  satStrip.addColorStop(1, "rgba(255,134,78,0.24)");
  ctx.fillStyle = satStrip;
  ctx.fillRect(graph.x, satStripY, graph.w, 20);

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.lineWidth = 1.2;
  ctx.setLineDash([5, 5]);
  ctx.beginPath();
  ctx.moveTo(graph.x, graph.y + graph.h);
  ctx.lineTo(graph.x + graph.w, graph.y);
  ctx.stroke();
  ctx.setLineDash([]);

  const drawCurve = (previewValue, color, widthPx) => {
    ctx.beginPath();
    for (let index = 0; index <= 120; index += 1) {
      const sourceSat = index / 120;
      const mappedSat = computeGamutMappedSaturation(sourceSat, previewValue, settings);
      const x = graph.x + (sourceSat * graph.w);
      const y = graph.y + ((1 - mappedSat) * graph.h);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = widthPx;
    ctx.stroke();
  };

  drawCurve(0.92, "rgba(255,182,96,0.72)", 1.5);
  drawCurve(0.50, "#67d0ff", 2.4);

  const kneeX = graph.x + (knee * graph.w);
  ctx.strokeStyle = "rgba(255,255,255,0.24)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(kneeX, graph.y);
  ctx.lineTo(kneeX, graph.y + graph.h);
  ctx.stroke();

  ctx.fillStyle = "rgba(238,243,247,0.86)";
  ctx.font = "600 11px 'IBM Plex Sans', sans-serif";
  ctx.fillText("Mapped Sat", graph.x + 10, graph.y + 16);
  ctx.fillText("Neutral", graph.x + 8, graph.y + graph.h - 5);
  ctx.fillText("Edge", graph.x + graph.w - 30, graph.y + graph.h - 5);
  ctx.fillText("Knee", kneeX + 6, graph.y + 16);
  ctx.fillStyle = "rgba(255,182,96,0.72)";
  ctx.fillText("Protected highs", graph.x + graph.w - 102, graph.y + 16);

  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 1;
  ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);
}

function buildGamutPanel(node) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Gamut Map Studio",
    subtitle: "Compress vivid edges with a visible rolloff curve and highlight protection instead of guessing from a flat control list.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ff9a55");
  panel.style.paddingBottom = "18px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const compressionMetric = createGradeMetric("Compression", "0.25");
  const kneeMetric = createGradeMetric("Knee", "0.55");
  const mixMetric = createGradeMetric("Mix", "1.00");
  metricsWrap.appendChild(compressionMetric.element);
  metricsWrap.appendChild(kneeMetric.element);
  metricsWrap.appendChild(mixMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Safe", () => { applyValues(node, GAMUT_PRESETS.safe); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Print", () => { applyValues(node, GAMUT_PRESETS.print); refreshPanel(); }));
  actions.appendChild(createGradeButton("Neon Relax", () => { applyValues(node, GAMUT_PRESETS.neon_relax); refreshPanel(); }));
  actions.appendChild(createGradeButton("Open Up", () => { applyValues(node, GAMUT_PRESETS.open_up); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const graphSection = createGradeSection("Gamut Response", "source sat -> mapped sat");
  const graphCanvas = document.createElement("canvas");
  graphCanvas.className = "mkr-gamut-graph";
  graphSection.body.appendChild(graphCanvas);
  const graphReadouts = document.createElement("div");
  graphReadouts.className = "mkr-grade-inline";
  const highlightReadout = createGradeReadout("Highlights", "0.25");
  const neutralReadout = createGradeReadout("Neutrals", "0.35");
  const satReadout = createGradeReadout("Sat", "1.00");
  graphReadouts.appendChild(highlightReadout.element);
  graphReadouts.appendChild(neutralReadout.element);
  graphReadouts.appendChild(satReadout.element);
  graphSection.body.appendChild(graphReadouts);
  panel.appendChild(graphSection.section);

  const mapSection = createGradeSection("Mapping Curve", "compression core");
  const mapControls = document.createElement("div");
  mapControls.className = "mkr-grade-controls";
  const compression = createGradeSlider({
    label: "Compression",
    min: -1,
    max: 1,
    step: 0.01,
    value: getNumber(node, "compression", 0.25),
    onChange: (value) => { setWidgetValue(node, "compression", value); refreshPanel(); },
  });
  const rolloff = createGradeSlider({
    label: "Rolloff",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "rolloff", 0.35),
    onChange: (value) => { setWidgetValue(node, "rolloff", value); refreshPanel(); },
  });
  const saturation = createGradeSlider({
    label: "Saturation",
    min: 0,
    max: 2,
    step: 0.01,
    value: getNumber(node, "saturation", 1),
    onChange: (value) => { setWidgetValue(node, "saturation", value); refreshPanel(); },
  });
  mapControls.appendChild(compression.element);
  mapControls.appendChild(rolloff.element);
  mapControls.appendChild(saturation.element);
  mapSection.body.appendChild(mapControls);
  panel.appendChild(mapSection.section);

  const protectSection = createGradeSection("Protection", "guard rails");
  const protectControls = document.createElement("div");
  protectControls.className = "mkr-grade-controls";
  const highlightProtect = createGradeSlider({
    label: "Highlight Protect",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "highlight_protect", 0.25),
    onChange: (value) => { setWidgetValue(node, "highlight_protect", value); refreshPanel(); },
  });
  const neutralProtect = createGradeSlider({
    label: "Neutral Protect",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "neutral_protect", 0.35),
    onChange: (value) => { setWidgetValue(node, "neutral_protect", value); refreshPanel(); },
  });
  const mix = createGradeSlider({
    label: "Mix",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "mix", 1),
    onChange: (value) => { setWidgetValue(node, "mix", value); refreshPanel(); },
  });
  protectControls.appendChild(highlightProtect.element);
  protectControls.appendChild(neutralProtect.element);
  protectControls.appendChild(mix.element);
  protectSection.body.appendChild(protectControls);
  panel.appendChild(protectSection.section);

  const outputSection = createGradeSection("Output", "delivery");
  const outputControls = document.createElement("div");
  outputControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const preserveLuma = createGradeToggle({
    label: "Preserve Luma",
    checked: getBoolean(node, "preserve_luma", true),
    description: "Restore original luminance after the gamut pass.",
    onChange: (checked) => { setWidgetValue(node, "preserve_luma", checked); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before the gamut map blends in.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  outputControls.appendChild(maskFeather.element);
  outputControls.appendChild(preserveLuma.element);
  outputControls.appendChild(invertMask.element);
  outputSection.body.appendChild(outputControls);
  panel.appendChild(outputSection.section);

  function refreshPanel() {
    const settings = readGamutSettings(node);
    compressionMetric.setValue(formatSigned(settings.compression));
    kneeMetric.setValue(formatNumber(computeGamutKnee(settings.rolloff)));
    mixMetric.setValue(formatNumber(settings.mix));
    highlightReadout.setValue(formatNumber(settings.highlight_protect));
    neutralReadout.setValue(formatNumber(settings.neutral_protect));
    satReadout.setValue(formatNumber(settings.saturation));
    compression.setValue(settings.compression);
    rolloff.setValue(settings.rolloff);
    saturation.setValue(settings.saturation);
    highlightProtect.setValue(settings.highlight_protect);
    neutralProtect.setValue(settings.neutral_protect);
    mix.setValue(settings.mix);
    maskFeather.setValue(settings.mask_feather);
    preserveLuma.setValue(settings.preserve_luma);
    invertMask.setValue(settings.invert_mask);
    drawGamutGraph(graphCanvas, node);
  }

  refreshPanel();
  attachPanel(node, GAMUT_PANEL, panel, GAMUT_PANEL_WIDTH, GAMUT_PANEL_HEIGHT);
  normalizePanelNode(node, GAMUT_HIDDEN_WIDGETS, GAMUT_PANEL);
  installRefreshHooks(node, "__mkrGamutRefreshHooksInstalled", refreshPanel);
  requestAnimationFrame(() => refreshPanel());
  node.__mkrGamutRefresh = refreshPanel;
}

function drawBalanceGraph(canvas, node) {
  const { ctx, width, height } = ensureCanvasResolution(canvas);
  ctx.clearRect(0, 0, width, height);
  const graph = { x: 18, y: 18, w: width - 36, h: height - 36 };

  const bg = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y + graph.h);
  bg.addColorStop(0, "rgba(12,16,20,0.98)");
  bg.addColorStop(1, "rgba(30,34,39,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const x = graph.x + (graph.w * step / 4);
    const y = graph.y + (graph.h * step / 4);
    ctx.beginPath();
    ctx.moveTo(x, graph.y);
    ctx.lineTo(x, graph.y + graph.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(graph.x, y);
    ctx.lineTo(graph.x + graph.w, y);
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.moveTo(graph.x, graph.y + graph.h);
  ctx.lineTo(graph.x + graph.w, graph.y);
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1.2;
  ctx.stroke();

  const channels = [
    {
      color: "#ff5b52",
      slope: getNumber(node, "slope_r", 1),
      offset: getNumber(node, "offset_r", 0),
      power: getNumber(node, "power_r", 1),
    },
    {
      color: "#39c66d",
      slope: getNumber(node, "slope_g", 1),
      offset: getNumber(node, "offset_g", 0),
      power: getNumber(node, "power_g", 1),
    },
    {
      color: "#4c8dff",
      slope: getNumber(node, "slope_b", 1),
      offset: getNumber(node, "offset_b", 0),
      power: getNumber(node, "power_b", 1),
    },
  ];

  for (const channel of channels) {
    ctx.beginPath();
    for (let index = 0; index <= 96; index += 1) {
      const t = index / 96;
      const shaped = Math.pow(clamp((t * channel.slope) + channel.offset, 0, 1), Math.max(0.1, channel.power));
      const x = graph.x + (t * graph.w);
      const y = graph.y + ((1 - shaped) * graph.h);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = channel.color;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 1;
  ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);
}

function buildBalancePanel(node) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Color Balance Studio",
    subtitle: "Balance slope, offset, and power from one grading panel with live transfer feedback.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ff7b31");

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const slopeMetric = createGradeMetric("Slope Avg", "1.00");
  const offsetMetric = createGradeMetric("Offset Bias", "0.00");
  const satMetric = createGradeMetric("Sat", "1.00");
  metricsWrap.appendChild(slopeMetric.element);
  metricsWrap.appendChild(offsetMetric.element);
  metricsWrap.appendChild(satMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Neutral", () => { applyValues(node, BALANCE_PRESETS.neutral); refreshPanel(); }));
  actions.appendChild(createGradeButton("Warm Print", () => { applyValues(node, BALANCE_PRESETS.warm_print); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Cool Lift", () => { applyValues(node, BALANCE_PRESETS.cool_lift); refreshPanel(); }));
  actions.appendChild(createGradeButton("Silver Punch", () => { applyValues(node, BALANCE_PRESETS.silver_punch); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const graphSection = createGradeSection("Transfer Curves", "rgb response");
  const graphCanvas = document.createElement("canvas");
  graphCanvas.className = "mkr-balance-graph";
  graphSection.body.appendChild(graphCanvas);
  const graphReadouts = document.createElement("div");
  graphReadouts.className = "mkr-grade-inline";
  const powerReadout = createGradeReadout("Power", "1.00");
  const mixReadout = createGradeReadout("Mix", "1.00");
  const lumaReadout = createGradeReadout("Luma", "On");
  graphReadouts.appendChild(powerReadout.element);
  graphReadouts.appendChild(mixReadout.element);
  graphReadouts.appendChild(lumaReadout.element);
  graphSection.body.appendChild(graphReadouts);
  panel.appendChild(graphSection.section);

  const tripletsSection = createGradeSection("RGB Controls", "compact triplets");
  const triplets = document.createElement("div");
  triplets.className = "mkr-balance-triplets";
  const slopeCard = createTripletCard({
    title: "Slope",
    min: 0,
    max: 3,
    step: 0.01,
    accent: "#ff7b31",
    rows: [
      { channel: "r", value: getNumber(node, "slope_r", 1), onChange: (value) => { setWidgetValue(node, "slope_r", value); refreshPanel(); } },
      { channel: "g", value: getNumber(node, "slope_g", 1), onChange: (value) => { setWidgetValue(node, "slope_g", value); refreshPanel(); } },
      { channel: "b", value: getNumber(node, "slope_b", 1), onChange: (value) => { setWidgetValue(node, "slope_b", value); refreshPanel(); } },
    ],
  });
  const offsetCard = createTripletCard({
    title: "Offset",
    min: -1,
    max: 1,
    step: 0.01,
    accent: "#ff7b31",
    rows: [
      { channel: "r", value: getNumber(node, "offset_r", 0), onChange: (value) => { setWidgetValue(node, "offset_r", value); refreshPanel(); } },
      { channel: "g", value: getNumber(node, "offset_g", 0), onChange: (value) => { setWidgetValue(node, "offset_g", value); refreshPanel(); } },
      { channel: "b", value: getNumber(node, "offset_b", 0), onChange: (value) => { setWidgetValue(node, "offset_b", value); refreshPanel(); } },
    ],
  });
  const powerCard = createTripletCard({
    title: "Power",
    min: 0.1,
    max: 3,
    step: 0.01,
    accent: "#ff7b31",
    rows: [
      { channel: "r", value: getNumber(node, "power_r", 1), onChange: (value) => { setWidgetValue(node, "power_r", value); refreshPanel(); } },
      { channel: "g", value: getNumber(node, "power_g", 1), onChange: (value) => { setWidgetValue(node, "power_g", value); refreshPanel(); } },
      { channel: "b", value: getNumber(node, "power_b", 1), onChange: (value) => { setWidgetValue(node, "power_b", value); refreshPanel(); } },
    ],
  });
  triplets.appendChild(slopeCard.element);
  triplets.appendChild(offsetCard.element);
  triplets.appendChild(powerCard.element);
  tripletsSection.body.appendChild(triplets);
  panel.appendChild(tripletsSection.section);

  const responseSection = createGradeSection("Output Response", "finishing");
  const responseControls = document.createElement("div");
  responseControls.className = "mkr-grade-controls";
  const saturation = createGradeSlider({
    label: "Saturation",
    min: 0,
    max: 2,
    step: 0.01,
    value: getNumber(node, "saturation", 1),
    onChange: (value) => { setWidgetValue(node, "saturation", value); refreshPanel(); },
  });
  const mix = createGradeSlider({
    label: "Mix",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "mix", 1),
    onChange: (value) => { setWidgetValue(node, "mix", value); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const preserveLuma = createGradeToggle({
    label: "Preserve Luma",
    checked: getBoolean(node, "preserve_luma", true),
    description: "Maintain source luminance after the balance pass.",
    onChange: (checked) => { setWidgetValue(node, "preserve_luma", checked); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before the balance is blended.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  responseControls.appendChild(saturation.element);
  responseControls.appendChild(mix.element);
  responseControls.appendChild(maskFeather.element);
  responseControls.appendChild(preserveLuma.element);
  responseControls.appendChild(invertMask.element);
  responseSection.body.appendChild(responseControls);
  panel.appendChild(responseSection.section);

  function refreshPanel() {
    const slopeValues = [
      getNumber(node, "slope_r", 1),
      getNumber(node, "slope_g", 1),
      getNumber(node, "slope_b", 1),
    ];
    const offsetValues = [
      getNumber(node, "offset_r", 0),
      getNumber(node, "offset_g", 0),
      getNumber(node, "offset_b", 0),
    ];
    const powerValues = [
      getNumber(node, "power_r", 1),
      getNumber(node, "power_g", 1),
      getNumber(node, "power_b", 1),
    ];

    slopeMetric.setValue(formatNumber((slopeValues[0] + slopeValues[1] + slopeValues[2]) / 3));
    offsetMetric.setValue(formatSigned((offsetValues[0] + offsetValues[1] + offsetValues[2]) / 3));
    satMetric.setValue(formatNumber(getNumber(node, "saturation", 1)));
    powerReadout.setValue(formatNumber((powerValues[0] + powerValues[1] + powerValues[2]) / 3));
    mixReadout.setValue(formatNumber(getNumber(node, "mix", 1)));
    lumaReadout.setValue(getBoolean(node, "preserve_luma", true) ? "On" : "Off");

    slopeCard.controls[0].setValue(slopeValues[0]);
    slopeCard.controls[1].setValue(slopeValues[1]);
    slopeCard.controls[2].setValue(slopeValues[2]);
    offsetCard.controls[0].setValue(offsetValues[0]);
    offsetCard.controls[1].setValue(offsetValues[1]);
    offsetCard.controls[2].setValue(offsetValues[2]);
    powerCard.controls[0].setValue(powerValues[0]);
    powerCard.controls[1].setValue(powerValues[1]);
    powerCard.controls[2].setValue(powerValues[2]);
    saturation.setValue(getNumber(node, "saturation", 1));
    mix.setValue(getNumber(node, "mix", 1));
    maskFeather.setValue(getNumber(node, "mask_feather", 12));
    preserveLuma.setValue(getBoolean(node, "preserve_luma", true));
    invertMask.setValue(getBoolean(node, "invert_mask", false));
    drawBalanceGraph(graphCanvas, node);
  }

  refreshPanel();
  attachPanel(node, BALANCE_PANEL, panel, 780, 860);
  normalizePanelNode(node, BALANCE_HIDDEN_WIDGETS, BALANCE_PANEL);
  installRefreshHooks(node, "__mkrBalanceRefreshHooksInstalled", refreshPanel);
  requestAnimationFrame(() => refreshPanel());
  node.__mkrBalanceRefresh = refreshPanel;
}

function prepareNode(node) {
  if (matchesNode(node, GAMUT_NODE)) {
    installGamutAdapter(node);
    if (!node.__mkrGamutPanelReady) {
      node.__mkrGamutPanelReady = true;
      buildGamutPanel(node);
    } else {
      node.__mkrGamutRefresh?.();
    }
    return;
  }

  if (matchesNode(node, QUALIFIER_NODE)) {
    installQualifierAdapter(node);
    if (!node.__mkrQualifierPanelReady) {
      node.__mkrQualifierPanelReady = true;
      buildQualifierPanel(node);
    } else {
      node.__mkrQualifierRefresh?.();
    }
    return;
  }

  if (matchesNode(node, BALANCE_NODE)) {
    installBalanceAdapter(node);
    if (!node.__mkrBalancePanelReady) {
      node.__mkrBalancePanelReady = true;
      buildBalancePanel(node);
    } else {
      node.__mkrBalanceRefresh?.();
    }
  }
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (![GAMUT_NODE, QUALIFIER_NODE, BALANCE_NODE].includes(String(nodeData?.name || nodeData?.type || ""))) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = typeof originalOnNodeCreated === "function"
        ? originalOnNodeCreated.apply(this, arguments)
        : undefined;
      prepareNode(this);
      return result;
    };
  },
  async nodeCreated(node) {
    prepareNode(node);
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      prepareNode(node);
    }
  },
});
