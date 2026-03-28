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
  matchesNode,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ColorAnalyzeStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-color-analyze-studios-v1";

const WAVEFORM_NODE = "x1WaveformScope";
const VECTORSCOPE_NODE = "x1Vectorscope";
const GAMUT_WARNING_NODE = "x1GamutWarning";
const HISTOGRAM_NODE = "x1HistogramScope";
const SKIN_TONE_NODE = "x1SkinToneCheck";
const RGB_BALANCE_NODE = "x1RGBBalanceScope";
const NEUTRALITY_MAP_NODE = "x1NeutralityMap";
const HUE_BAND_NODE = "x1HueBandScope";
const SAT_LUMA_NODE = "x1SatLumaScope";

const WAVEFORM_PANEL = "mkr_color_waveform_scope_studio";
const VECTORSCOPE_PANEL = "mkr_color_vectorscope_studio";
const GAMUT_WARNING_PANEL = "mkr_color_gamut_warning_studio";
const HISTOGRAM_PANEL = "mkr_color_histogram_scope_studio";
const SKIN_TONE_PANEL = "mkr_color_skin_tone_check_studio";
const RGB_BALANCE_PANEL = "mkr_color_rgb_balance_scope_studio";
const NEUTRALITY_MAP_PANEL = "mkr_color_neutrality_map_studio";
const HUE_BAND_PANEL = "mkr_color_hue_band_scope_studio";
const SAT_LUMA_PANEL = "mkr_color_sat_luma_scope_studio";

const WAVEFORM_SIZE = [860, 760];
const VECTORSCOPE_SIZE = [760, 760];
const GAMUT_WARNING_SIZE = [760, 720];
const HISTOGRAM_SIZE = [820, 740];
const SKIN_TONE_SIZE = [760, 760];
const RGB_BALANCE_SIZE = [820, 760];
const NEUTRALITY_MAP_SIZE = [760, 760];
const HUE_BAND_SIZE = [820, 720];
const SAT_LUMA_SIZE = [760, 760];

const WAVEFORM_DEFAULTS = {
  scope_mode: "rgb_parade",
  gain: 1.15,
  trace_strength: 0.9,
  graticule: 0.38,
  scope_resolution: 560,
  sample_step: 2,
  mask_feather: 12.0,
  invert_mask: false,
};

const WAVEFORM_NUMERIC = {
  gain: { min: 0.25, max: 4.0 },
  trace_strength: { min: 0.05, max: 2.0 },
  graticule: { min: 0.0, max: 1.0 },
  scope_resolution: { min: 256, max: 1024, integer: true },
  sample_step: { min: 1, max: 8, integer: true },
  mask_feather: { min: 0.0, max: 256.0 },
};

const VECTORSCOPE_DEFAULTS = {
  scope_gain: 1.0,
  trace_strength: 0.95,
  graticule: 0.42,
  scope_resolution: 440,
  sample_step: 2,
  show_skin_line: true,
  show_targets: true,
  mask_feather: 12.0,
  invert_mask: false,
};

const VECTORSCOPE_NUMERIC = {
  scope_gain: { min: 0.25, max: 3.0 },
  trace_strength: { min: 0.05, max: 2.0 },
  graticule: { min: 0.0, max: 1.0 },
  scope_resolution: { min: 256, max: 960, integer: true },
  sample_step: { min: 1, max: 8, integer: true },
  mask_feather: { min: 0.0, max: 256.0 },
};

const GAMUT_WARNING_DEFAULTS = {
  warning_mode: "combined",
  low_clip: 0.02,
  high_clip: 0.98,
  saturation_limit: 0.9,
  highlight_gate: 0.55,
  overlay_opacity: 0.82,
  mask_feather: 12.0,
  invert_mask: false,
};

const GAMUT_WARNING_NUMERIC = {
  low_clip: { min: 0.0, max: 1.0 },
  high_clip: { min: 0.0, max: 1.0 },
  saturation_limit: { min: 0.0, max: 1.0 },
  highlight_gate: { min: 0.0, max: 1.0 },
  overlay_opacity: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const HISTOGRAM_DEFAULTS = {
  histogram_mode: "rgb_overlay",
  bins: 128,
  contrast: 1.25,
  fill_opacity: 0.30,
  normalize_mode: "peak",
  mask_feather: 12.0,
  invert_mask: false,
};

const HISTOGRAM_NUMERIC = {
  bins: { min: 32, max: 512, integer: true },
  contrast: { min: 0.25, max: 3.0 },
  fill_opacity: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const SKIN_TONE_DEFAULTS = {
  target_hue: 28.0,
  hue_width: 52.0,
  sat_min: 0.10,
  sat_max: 0.82,
  val_min: 0.15,
  line_tolerance: 0.18,
  overlay_opacity: 0.82,
  show_isolation: false,
  mask_feather: 12.0,
  invert_mask: false,
};

const SKIN_TONE_NUMERIC = {
  target_hue: { min: 0.0, max: 360.0 },
  hue_width: { min: 5.0, max: 160.0 },
  sat_min: { min: 0.0, max: 1.0 },
  sat_max: { min: 0.0, max: 1.0 },
  val_min: { min: 0.0, max: 1.0 },
  line_tolerance: { min: 0.01, max: 0.6 },
  overlay_opacity: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const RGB_BALANCE_DEFAULTS = {
  analysis_mode: "zones",
  shadow_point: 0.22,
  highlight_point: 0.78,
  zone_softness: 0.12,
  response_gain: 1.15,
  neutral_tolerance: 0.08,
  show_reference: true,
  mask_feather: 12.0,
  invert_mask: false,
};

const RGB_BALANCE_NUMERIC = {
  shadow_point: { min: 0.0, max: 1.0 },
  highlight_point: { min: 0.0, max: 1.0 },
  zone_softness: { min: 0.02, max: 0.35 },
  response_gain: { min: 0.25, max: 3.0 },
  neutral_tolerance: { min: 0.02, max: 0.25 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const NEUTRALITY_MAP_DEFAULTS = {
  sat_ceiling: 0.18,
  luma_floor: 0.10,
  luma_ceiling: 0.92,
  cast_gain: 1.35,
  warmth_bias: 0.0,
  overlay_opacity: 0.82,
  show_isolation: false,
  mask_feather: 12.0,
  invert_mask: false,
};

const NEUTRALITY_MAP_NUMERIC = {
  sat_ceiling: { min: 0.02, max: 0.60 },
  luma_floor: { min: 0.0, max: 1.0 },
  luma_ceiling: { min: 0.0, max: 1.0 },
  cast_gain: { min: 0.2, max: 3.0 },
  warmth_bias: { min: -0.35, max: 0.35 },
  overlay_opacity: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const HUE_BAND_DEFAULTS = {
  bins: 192,
  density_gain: 1.10,
  sat_floor: 0.08,
  val_floor: 0.10,
  graticule: 0.34,
  sample_step: 2,
  mask_feather: 12.0,
  invert_mask: false,
};

const HUE_BAND_NUMERIC = {
  bins: { min: 48, max: 512, integer: true },
  density_gain: { min: 0.2, max: 3.0 },
  sat_floor: { min: 0.0, max: 1.0 },
  val_floor: { min: 0.0, max: 1.0 },
  graticule: { min: 0.0, max: 1.0 },
  sample_step: { min: 1, max: 8, integer: true },
  mask_feather: { min: 0.0, max: 256.0 },
};

const SAT_LUMA_DEFAULTS = {
  density_gain: 1.00,
  sat_floor: 0.04,
  graticule: 0.40,
  sample_step: 2,
  mask_feather: 12.0,
  invert_mask: false,
};

const SAT_LUMA_NUMERIC = {
  density_gain: { min: 0.2, max: 3.0 },
  sat_floor: { min: 0.0, max: 0.5 },
  graticule: { min: 0.0, max: 1.0 },
  sample_step: { min: 1, max: 8, integer: true },
  mask_feather: { min: 0.0, max: 256.0 },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-color-analyze-select {
      width: 100%;
      margin-top: 4px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.22);
      color: #eef2f6;
      padding: 8px 9px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-color-analyze-preview {
      position: relative;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(12,15,20,0.98), rgba(18,22,28,0.98));
      min-height: 248px;
    }

    .mkr-color-analyze-preview canvas {
      display: block;
      width: 100%;
      height: 248px;
    }

    .mkr-color-analyze-hint {
      margin-top: 8px;
      font-size: 11px;
      color: rgba(224,231,236,0.62);
      line-height: 1.45;
    }

    .mkr-color-analyze-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }

    .mkr-color-analyze-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      font-size: 10px;
      color: rgba(238,242,246,0.88);
    }

    .mkr-color-analyze-chip-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      flex: 0 0 auto;
    }
  `;
  document.head.appendChild(style);
}

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const select = document.createElement("select");
  select.className = "mkr-color-analyze-select";
  for (const option of options) {
    const opt = document.createElement("option");
    opt.value = String(option.value);
    opt.textContent = option.label;
    select.appendChild(opt);
  }
  select.value = String(value);
  select.addEventListener("change", () => {
    head.lastChild.textContent = String(select.value);
    onChange?.(select.value);
  });

  root.appendChild(head);
  root.appendChild(select);
  return {
    element: root,
    setValue(next) {
      select.value = String(next);
      head.lastChild.textContent = String(next);
    },
  };
}

function createLegend(entries) {
  const legend = document.createElement("div");
  legend.className = "mkr-color-analyze-legend";
  for (const entry of entries) {
    const chip = document.createElement("div");
    chip.className = "mkr-color-analyze-chip";
    const dot = document.createElement("span");
    dot.className = "mkr-color-analyze-chip-dot";
    dot.style.background = entry.color;
    const label = document.createElement("span");
    label.textContent = entry.label;
    chip.appendChild(dot);
    chip.appendChild(label);
    legend.appendChild(chip);
  }
  return legend;
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

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedRefreshPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeRefreshPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };
}

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values || {})) {
    setWidgetValue(node, key, value);
  }
}

function drawWaveformPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "rgba(15,18,24,1)");
  bg.addColorStop(1, "rgba(24,28,35,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const graticule = clamp(Number(settings.graticule) || 0, 0, 1);
  ctx.strokeStyle = `rgba(192,205,220,${0.10 + (graticule * 0.12)})`;
  ctx.lineWidth = 1;
  for (const stop of [0, 0.25, 0.5, 0.75, 1]) {
    const y = Math.round((height - 1) * stop) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  for (const stop of [0.25, 0.5, 0.75]) {
    const x = Math.round((width - 1) * stop) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }

  const mode = String(settings.scope_mode || "rgb_parade");
  const gain = clamp(Number(settings.gain) || 1, 0.25, 4);
  const strength = clamp(Number(settings.trace_strength) || 1, 0.05, 2);

  function drawTrace(color, offset = 0, scale = 1, jitter = 0) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (let i = 0; i < 150; i += 1) {
      const t = i / 149;
      const x = offset + (t * scale * width);
      const y = height - (height * clamp((0.14 + (0.72 * t) + (Math.sin((t * 9.5) + jitter) * 0.11 * strength)) * gain * 0.74, 0.02, 0.98));
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  if (mode === "luma") {
    drawTrace("rgba(240,244,250,0.92)", 0, 1, 0.0);
  } else if (mode === "rgb_overlay") {
    drawTrace("rgba(255,88,62,0.90)", 0, 1, 0.0);
    drawTrace("rgba(98,255,138,0.78)", 0, 1, 1.8);
    drawTrace("rgba(84,156,255,0.78)", 0, 1, 3.6);
  } else {
    const gap = width * 0.045;
    const span = (width - (gap * 2)) / 3;
    drawTrace("rgba(255,88,62,0.90)", 0, span / width, 0.0);
    drawTrace("rgba(98,255,138,0.82)", span + gap, span / width, 1.8);
    drawTrace("rgba(84,156,255,0.82)", (span * 2) + (gap * 2), span / width, 3.6);
  }
}

function drawVectorscopePreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const size = Math.min(width, height);
  const cx = width * 0.5;
  const cy = height * 0.5;
  const radius = size * 0.36;
  const bg = ctx.createRadialGradient(cx, cy, radius * 0.1, cx, cy, radius * 1.2);
  bg.addColorStop(0, "rgba(36,40,48,1)");
  bg.addColorStop(1, "rgba(14,17,22,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const graticule = clamp(Number(settings.graticule) || 0, 0, 1);
  ctx.strokeStyle = `rgba(210,220,232,${0.08 + (graticule * 0.14)})`;
  ctx.lineWidth = 1;
  for (const ring of [0.25, 0.5, 0.75, 1.0]) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius * ring, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(cx - radius, cy);
  ctx.lineTo(cx + radius, cy);
  ctx.moveTo(cx, cy - radius);
  ctx.lineTo(cx, cy + radius);
  ctx.stroke();

  if (getBoolean({ __mkrColorSettingsAdapter: null, properties: settings }, "show_targets", true)) {
    ctx.fillStyle = "rgba(255,255,255,0.12)";
    for (const angle of [0, 60, 120, 180, 240, 300]) {
      const rad = angle * (Math.PI / 180);
      const tx = cx + (Math.cos(rad) * radius * 0.82);
      const ty = cy - (Math.sin(rad) * radius * 0.82);
      ctx.beginPath();
      ctx.arc(tx, ty, 4.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (getBoolean({ __mkrColorSettingsAdapter: null, properties: settings }, "show_skin_line", true)) {
    const skin = 123 * (Math.PI / 180);
    ctx.strokeStyle = "rgba(255,183,94,0.58)";
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + (Math.cos(skin) * radius), cy - (Math.sin(skin) * radius));
    ctx.stroke();
  }

  const gain = clamp(Number(settings.scope_gain) || 1, 0.25, 3.0);
  const strength = clamp(Number(settings.trace_strength) || 1, 0.05, 2.0);
  const clusters = [
    { angle: 34, sat: 0.68, color: "rgba(255,101,74,0.82)" },
    { angle: 132, sat: 0.56, color: "rgba(236,208,102,0.74)" },
    { angle: 212, sat: 0.62, color: "rgba(78,186,255,0.80)" },
    { angle: 302, sat: 0.72, color: "rgba(122,255,162,0.68)" },
  ];
  for (const cluster of clusters) {
    const angle = cluster.angle * (Math.PI / 180);
    ctx.strokeStyle = cluster.color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < 90; i += 1) {
      const t = i / 89;
      const wobble = Math.sin((t * 8.0) + cluster.angle) * 0.06 * strength;
      const r = radius * clamp((cluster.sat + wobble) * gain * 0.78, 0.05, 1.0);
      const x = cx + (Math.cos(angle + (t * 0.9)) * r);
      const y = cy - (Math.sin(angle + (t * 0.9)) * r);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
}

function drawGamutWarningPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(20,23,29,1)");
  bg.addColorStop(1, "rgba(30,35,43,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const bands = [
    ["#0d1320", "#2a3e74"],
    ["#274f84", "#3d7f87"],
    ["#7d9656", "#d0ab4f"],
    ["#d77b31", "#e24b3e"],
  ];
  const bandWidth = width / bands.length;
  for (let i = 0; i < bands.length; i += 1) {
    const grad = ctx.createLinearGradient(i * bandWidth, 0, (i + 1) * bandWidth, height);
    grad.addColorStop(0, bands[i][0]);
    grad.addColorStop(1, bands[i][1]);
    ctx.fillStyle = grad;
    ctx.fillRect(i * bandWidth, 0, bandWidth, height);
  }

  const mode = String(settings.warning_mode || "combined");
  const highClip = clamp(Number(settings.high_clip) || 0.98, 0, 1);
  const lowClip = clamp(Number(settings.low_clip) || 0.02, 0, 1);
  const satLimit = clamp(Number(settings.saturation_limit) || 0.9, 0, 1);
  const opacity = clamp(Number(settings.overlay_opacity) || 0.82, 0, 1);

  if (mode === "broadcast_safe" || mode === "combined") {
    ctx.fillStyle = `rgba(255,72,48,${opacity * 0.44})`;
    ctx.fillRect(width * (highClip - 0.02), 0, width * (1.02 - highClip), height);
    ctx.fillStyle = `rgba(72,138,255,${opacity * 0.38})`;
    ctx.fillRect(0, 0, width * (lowClip + 0.02), height);
  }

  if (mode === "chroma_stress" || mode === "combined") {
    ctx.fillStyle = `rgba(255,214,88,${opacity * 0.42})`;
    ctx.beginPath();
    ctx.ellipse(width * 0.70, height * lerp(0.78, 0.26, satLimit), width * 0.20, height * 0.18, -0.6, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function drawHistogramPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "rgba(16,19,24,1)");
  bg.addColorStop(1, "rgba(24,28,34,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(210,220,232,0.10)";
  ctx.lineWidth = 1;
  for (const stop of [0.25, 0.5, 0.75]) {
    const y = Math.round((height - 1) * (1.0 - stop)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  const bins = clamp(Math.round(Number(settings.bins) || 128), 32, 512);
  const mode = String(settings.histogram_mode || "rgb_overlay");
  const contrast = clamp(Number(settings.contrast) || 1.25, 0.25, 3.0);
  const fillOpacity = clamp(Number(settings.fill_opacity) || 0.30, 0.0, 1.0);
  const normalize = String(settings.normalize_mode || "peak");
  const curveScale = normalize === "area" ? 0.78 : 1.0;

  function drawCurve(color, seed, bandTop = 0, bandHeight = height) {
    const points = [];
    for (let i = 0; i < bins; i += 1) {
      const t = i / (bins - 1);
      const wobble = (Math.sin((t * (5.4 + seed)) + seed) * 0.18) + (Math.cos((t * (11.2 + seed)) - seed) * 0.08);
      const peakA = Math.exp(-Math.pow((t - (0.18 + (seed * 0.08))), 2) / (0.004 + (seed * 0.001)));
      const peakB = Math.exp(-Math.pow((t - (0.78 - (seed * 0.05))), 2) / (0.012 + (seed * 0.001)));
      const value = clamp((0.08 + (peakA * 0.72) + (peakB * 0.46) + wobble * 0.10) * curveScale, 0.02, 0.98);
      const x = (t * width);
      const y = bandTop + bandHeight - (value * bandHeight * 0.92 * contrast);
      points.push([x, y]);
    }

    ctx.fillStyle = color.replace("1)", `${0.20 + (fillOpacity * 0.55)})`);
    ctx.beginPath();
    ctx.moveTo(points[0][0], bandTop + bandHeight);
    for (const [x, y] of points) ctx.lineTo(x, y);
    ctx.lineTo(points[points.length - 1][0], bandTop + bandHeight);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < points.length; i += 1) {
      const [x, y] = points[i];
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  if (mode === "luma") {
    drawCurve("rgba(244,247,251,1)", 0.2);
  } else if (mode === "rgb_stack") {
    const third = height / 3;
    drawCurve("rgba(255,89,70,1)", 0.4, 0, third);
    drawCurve("rgba(96,255,145,1)", 1.2, third, third);
    drawCurve("rgba(83,156,255,1)", 2.2, third * 2, third);
  } else {
    drawCurve("rgba(255,89,70,1)", 0.4);
    drawCurve("rgba(96,255,145,1)", 1.2);
    drawCurve("rgba(83,156,255,1)", 2.2);
  }
}

function drawSkinTonePreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(26,24,21,1)");
  bg.addColorStop(1, "rgba(40,32,28,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const bands = [
    ["#5c3d31", "#9a6b55"],
    ["#7b5844", "#c29072"],
    ["#8d6a56", "#d3aa85"],
    ["#4a5870", "#7597c0"],
  ];
  const bandWidth = width / bands.length;
  for (let i = 0; i < bands.length; i += 1) {
    const grad = ctx.createLinearGradient(i * bandWidth, 0, (i + 1) * bandWidth, height);
    grad.addColorStop(0, bands[i][0]);
    grad.addColorStop(1, bands[i][1]);
    ctx.fillStyle = grad;
    ctx.fillRect(i * bandWidth, 0, bandWidth, height);
  }

  const targetHue = clamp(Number(settings.target_hue) || 28, 0, 360);
  const hueWidth = clamp(Number(settings.hue_width) || 52, 5, 160);
  const tolerance = clamp(Number(settings.line_tolerance) || 0.18, 0.01, 0.6);
  const overlayOpacity = clamp(Number(settings.overlay_opacity) || 0.82, 0, 1);
  const showIsolation = !!settings.show_isolation;

  const zoneX = ((targetHue / 360) * width);
  const zoneW = Math.max(width * (hueWidth / 360), 18);
  const left = clamp(zoneX - (zoneW * 0.5), 0, width);
  const right = clamp(zoneX + (zoneW * 0.5), 0, width);

  ctx.fillStyle = showIsolation ? `rgba(88,255,156,${0.20 + (overlayOpacity * 0.25)})` : `rgba(88,255,156,${0.12 + (overlayOpacity * 0.18)})`;
  ctx.fillRect(left, 0, Math.max(0, right - left), height);
  ctx.fillStyle = `rgba(255,190,80,${0.16 + (tolerance * 0.40)})`;
  ctx.fillRect(clamp(left - (width * tolerance * 0.35), 0, width), 0, Math.max(0, (right - left) + (width * tolerance * 0.70)), height);

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function drawRGBBalancePreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "rgba(17,20,25,1)");
  bg.addColorStop(1, "rgba(27,31,38,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const mode = String(settings.analysis_mode || "zones");
  const responseGain = clamp(Number(settings.response_gain) || 1.15, 0.25, 3.0);
  const tolerance = clamp(Number(settings.neutral_tolerance) || 0.08, 0.02, 0.25);
  const showReference = !!settings.show_reference;
  const segments = mode === "columns" ? 12 : 3;
  const centerY = height * 0.5;
  const tolPx = height * tolerance * 0.9;

  ctx.strokeStyle = "rgba(228,234,241,0.14)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, centerY + 0.5);
  ctx.lineTo(width, centerY + 0.5);
  ctx.stroke();

  if (showReference) {
    ctx.strokeStyle = "rgba(228,234,241,0.08)";
    for (const y of [centerY - tolPx, centerY + tolPx]) {
      ctx.beginPath();
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(width, y + 0.5);
      ctx.stroke();
    }
  }

  const gap = segments >= 8 ? 4 : 10;
  const segmentWidth = (width - (gap * (segments + 1))) / segments;
  const colors = ["rgba(255,92,70,0.95)", "rgba(102,255,148,0.95)", "rgba(87,160,255,0.95)"];

  function drawSegmentBars(segmentIndex, offsets) {
    const x0 = gap + (segmentIndex * (segmentWidth + gap));
    const x1 = x0 + segmentWidth;
    ctx.fillStyle = segmentIndex % 2 === 0 ? "rgba(255,255,255,0.02)" : "rgba(255,255,255,0.01)";
    ctx.fillRect(x0, 0, segmentWidth, height);

    const laneGap = Math.max(4, segmentWidth * 0.05);
    const laneWidth = ((segmentWidth - (laneGap * 4)) / 3);
    offsets.forEach((offset, channel) => {
      const laneX = x0 + laneGap + (channel * (laneWidth + laneGap));
      const bar = Math.abs(offset) * height * 0.72;
      const y = offset >= 0 ? centerY - bar : centerY;
      const h = Math.max(2, bar);
      ctx.fillStyle = colors[channel].replace("0.95", "0.32");
      ctx.fillRect(laneX, y, laneWidth, h);
      ctx.fillStyle = colors[channel];
      ctx.fillRect(laneX, offset >= 0 ? y : y + h - 2, laneWidth, 2);
    });
  }

  if (mode === "columns") {
    for (let i = 0; i < segments; i += 1) {
      const t = i / Math.max(segments - 1, 1);
      const offsets = [
        Math.sin((t * 7.2) + 0.4) * 0.14 * responseGain,
        Math.cos((t * 5.0) + 1.2) * 0.10 * responseGain,
        Math.sin((t * 6.1) + 2.2) * -0.12 * responseGain,
      ].map((value) => clamp(value, -0.46, 0.46));
      drawSegmentBars(i, offsets);
    }
  } else {
    const shadow = clamp((0.18 + (Number(settings.shadow_point) || 0.22)) * responseGain * 0.42, -0.46, 0.46);
    const highlight = clamp((Number(settings.highlight_point) || 0.78) * responseGain * 0.24, -0.46, 0.46);
    drawSegmentBars(0, [shadow, 0.02, -shadow * 0.68]);
    drawSegmentBars(1, [0.02, 0.0, -0.03]);
    drawSegmentBars(2, [-highlight * 0.35, 0.01, highlight]);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function drawNeutralityMapPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(30,30,31,1)");
  bg.addColorStop(1, "rgba(49,46,43,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const plates = [
    ["#827a72", "#928a82"],
    ["#6f7277", "#888d94"],
    ["#62564e", "#83766d"],
    ["#7c7f81", "#97999c"],
  ];
  const plateWidth = width / plates.length;
  for (let i = 0; i < plates.length; i += 1) {
    const grad = ctx.createLinearGradient(i * plateWidth, 0, (i + 1) * plateWidth, height);
    grad.addColorStop(0, plates[i][0]);
    grad.addColorStop(1, plates[i][1]);
    ctx.fillStyle = grad;
    ctx.fillRect(i * plateWidth, 0, plateWidth, height);
  }

  const satCeiling = clamp(Number(settings.sat_ceiling) || 0.18, 0.02, 0.60);
  const castGain = clamp(Number(settings.cast_gain) || 1.35, 0.2, 3.0);
  const warmthBias = clamp(Number(settings.warmth_bias) || 0.0, -0.35, 0.35);
  const opacity = clamp(Number(settings.overlay_opacity) || 0.82, 0.0, 1.0);
  const showIsolation = !!settings.show_isolation;

  const swatches = [
    { x: width * 0.18, y: height * 0.36, color: `rgba(255,182,92,${0.18 + (castGain * 0.10)})` },
    { x: width * 0.40, y: height * 0.58, color: `rgba(112,255,146,${0.12 + (satCeiling * 0.40)})` },
    { x: width * 0.68, y: height * 0.30, color: `rgba(96,162,255,${0.16 + (Math.abs(warmthBias) * 0.8)})` },
    { x: width * 0.80, y: height * 0.64, color: `rgba(255,112,212,${0.12 + (opacity * 0.34)})` },
  ];
  for (const swatch of swatches) {
    ctx.fillStyle = swatch.color;
    ctx.beginPath();
    ctx.ellipse(swatch.x, swatch.y, width * 0.14, height * 0.18, -0.35, 0, Math.PI * 2);
    ctx.fill();
  }

  if (showIsolation) {
    ctx.fillStyle = "rgba(8,10,12,0.58)";
    ctx.fillRect(0, 0, width, height);
    for (const swatch of swatches) {
      ctx.fillStyle = swatch.color.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, "rgba($1,$2,$3,0.92)");
      ctx.beginPath();
      ctx.ellipse(swatch.x, swatch.y, width * 0.12, height * 0.15, -0.35, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function hueColor(t) {
  const h = ((t % 1) + 1) % 1;
  const sector = h * 6;
  const c = 1;
  const x = c * (1 - Math.abs((sector % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (sector < 1) [r, g, b] = [c, x, 0];
  else if (sector < 2) [r, g, b] = [x, c, 0];
  else if (sector < 3) [r, g, b] = [0, c, x];
  else if (sector < 4) [r, g, b] = [0, x, c];
  else if (sector < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
}

function drawHueBandPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "rgba(16,18,23,1)");
  bg.addColorStop(1, "rgba(24,28,34,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const bandHeight = Math.max(28, height * 0.18);
  for (let x = 0; x < width; x += 1) {
    ctx.fillStyle = hueColor(x / Math.max(width - 1, 1));
    ctx.fillRect(x, height - bandHeight, 1, bandHeight);
  }

  const graticule = clamp(Number(settings.graticule) || 0.34, 0, 1);
  ctx.strokeStyle = `rgba(210,220,232,${0.08 + (graticule * 0.14)})`;
  ctx.lineWidth = 1;
  for (const stop of [0.25, 0.5, 0.75]) {
    const y = Math.round((height - bandHeight - 1) * (1 - stop)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  for (let i = 0; i <= 6; i += 1) {
    const x = Math.round((width - 1) * (i / 6)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }

  const bins = clamp(Math.round(Number(settings.bins) || 192), 48, 512);
  const density = clamp(Number(settings.density_gain) || 1.1, 0.2, 3.0);
  const satFloor = clamp(Number(settings.sat_floor) || 0.08, 0, 1);
  const valFloor = clamp(Number(settings.val_floor) || 0.10, 0, 1);

  const points = [];
  for (let i = 0; i < bins; i += 1) {
    const t = i / Math.max(bins - 1, 1);
    const peakA = Math.exp(-Math.pow((t - 0.08), 2) / 0.004);
    const peakB = Math.exp(-Math.pow((t - 0.33), 2) / 0.010);
    const peakC = Math.exp(-Math.pow((t - 0.67), 2) / 0.008);
    const peakD = Math.exp(-Math.pow((t - 0.91), 2) / 0.006);
    const activity = clamp((0.10 + (peakA * (0.45 + satFloor)) + (peakB * 0.30) + (peakC * (0.22 + valFloor)) + (peakD * 0.52)) * density * 0.56, 0.01, 0.98);
    const x = t * width;
    const y = (height - bandHeight) - (activity * (height - bandHeight - 8));
    points.push([x, y, t]);
  }

  ctx.beginPath();
  ctx.moveTo(points[0][0], height - bandHeight);
  for (const [x, y] of points) ctx.lineTo(x, y);
  ctx.lineTo(points[points.length - 1][0], height - bandHeight);
  ctx.closePath();
  const fill = ctx.createLinearGradient(0, 0, 0, height - bandHeight);
  fill.addColorStop(0, "rgba(255,255,255,0.16)");
  fill.addColorStop(1, "rgba(255,255,255,0.03)");
  ctx.fillStyle = fill;
  ctx.fill();

  ctx.lineWidth = 2;
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const curr = points[i];
    ctx.strokeStyle = hueColor(curr[2]);
    ctx.beginPath();
    ctx.moveTo(prev[0], prev[1]);
    ctx.lineTo(curr[0], curr[1]);
    ctx.stroke();
  }
}

function drawSatLumaPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(18,21,26,1)");
  bg.addColorStop(1, "rgba(28,31,38,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const graticule = clamp(Number(settings.graticule) || 0.40, 0, 1);
  ctx.strokeStyle = `rgba(212,220,230,${0.08 + (graticule * 0.12)})`;
  ctx.lineWidth = 1;
  for (const stop of [0.25, 0.5, 0.75]) {
    const x = Math.round((width - 1) * stop) + 0.5;
    const y = Math.round((height - 1) * stop) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  const density = clamp(Number(settings.density_gain) || 1.0, 0.2, 3.0);
  const satFloor = clamp(Number(settings.sat_floor) || 0.04, 0, 0.5);
  const clusters = [
    { sat: 0.12 + satFloor, luma: 0.82, color: "rgba(190,205,255,0.66)" },
    { sat: 0.28 + satFloor, luma: 0.58, color: "rgba(255,208,98,0.72)" },
    { sat: 0.72, luma: 0.36, color: "rgba(255,96,82,0.78)" },
    { sat: 0.84, luma: 0.72, color: "rgba(98,255,162,0.68)" },
  ];
  for (const cluster of clusters) {
    ctx.strokeStyle = cluster.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < 80; i += 1) {
      const t = i / 79;
      const wobbleX = Math.sin((t * 7.2) + (cluster.sat * 4.0)) * 0.05 * density;
      const wobbleY = Math.cos((t * 6.0) + (cluster.luma * 5.0)) * 0.06 * density;
      const x = clamp(cluster.sat + wobbleX + (t * 0.08), 0, 1) * width;
      const y = (1 - clamp(cluster.luma + wobbleY - (t * 0.06), 0, 1)) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function buildWaveformPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Waveform Scope Studio",
    subtitle: "Inspect luma, RGB overlay, or parade scopes without leaving the graph.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#6dd3ff");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "Parade");
  const resMetric = createGradeMetric("Res", "560");
  const stepMetric = createGradeMetric("Step", "2");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(resMetric.element);
  metricsWrap.appendChild(stepMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Luma", () => { applyValues(node, { scope_mode: "luma" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Overlay", () => { applyValues(node, { scope_mode: "rgb_overlay" }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Parade", () => { applyValues(node, { scope_mode: "rgb_parade" }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Scope Preview", "luma / rgb");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#f4f7fb", label: "Luma" },
      { color: "#ff5a44", label: "Red" },
      { color: "#63ff8d", label: "Green" },
      { color: "#5a9cff", label: "Blue" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "Use RGB parade for channel alignment checks or switch to luma when you want a single exposure trace.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Scope Response", "sampling");
  const scopeControls = document.createElement("div");
  scopeControls.className = "mkr-grade-controls";
  const modeSelect = createSelectControl({
    label: "Scope Mode",
    value: getValue(node, "scope_mode", WAVEFORM_DEFAULTS.scope_mode),
    options: [
      { value: "luma", label: "Luma" },
      { value: "rgb_overlay", label: "RGB Overlay" },
      { value: "rgb_parade", label: "RGB Parade" },
    ],
    onChange: (value) => { setWidgetValue(node, "scope_mode", value); refreshPanel(); },
  });
  const gain = createGradeSlider({
    label: "Gain",
    min: 0.25,
    max: 4.0,
    step: 0.01,
    value: getNumber(node, "gain", WAVEFORM_DEFAULTS.gain),
    onChange: (value) => { setWidgetValue(node, "gain", value); refreshPanel(); },
  });
  const traceStrength = createGradeSlider({
    label: "Trace",
    min: 0.05,
    max: 2.0,
    step: 0.01,
    value: getNumber(node, "trace_strength", WAVEFORM_DEFAULTS.trace_strength),
    onChange: (value) => { setWidgetValue(node, "trace_strength", value); refreshPanel(); },
  });
  const graticule = createGradeSlider({
    label: "Graticule",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "graticule", WAVEFORM_DEFAULTS.graticule),
    onChange: (value) => { setWidgetValue(node, "graticule", value); refreshPanel(); },
  });
  const resolution = createGradeSlider({
    label: "Resolution",
    min: 256,
    max: 1024,
    step: 1,
    value: getNumber(node, "scope_resolution", WAVEFORM_DEFAULTS.scope_resolution),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "scope_resolution", Math.round(value)); refreshPanel(); },
  });
  const sampleStep = createGradeSlider({
    label: "Sample Step",
    min: 1,
    max: 8,
    step: 1,
    value: getNumber(node, "sample_step", WAVEFORM_DEFAULTS.sample_step),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "sample_step", Math.round(value)); refreshPanel(); },
  });
  scopeControls.appendChild(modeSelect.element);
  scopeControls.appendChild(gain.element);
  scopeControls.appendChild(traceStrength.element);
  scopeControls.appendChild(graticule.element);
  scopeControls.appendChild(resolution.element);
  scopeControls.appendChild(sampleStep.element);
  controlsSection.body.appendChild(scopeControls);
  panel.appendChild(controlsSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", WAVEFORM_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", WAVEFORM_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the scope sample.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      scope_mode: getValue(node, "scope_mode", WAVEFORM_DEFAULTS.scope_mode),
      gain: getNumber(node, "gain", WAVEFORM_DEFAULTS.gain),
      trace_strength: getNumber(node, "trace_strength", WAVEFORM_DEFAULTS.trace_strength),
      graticule: getNumber(node, "graticule", WAVEFORM_DEFAULTS.graticule),
      scope_resolution: getNumber(node, "scope_resolution", WAVEFORM_DEFAULTS.scope_resolution),
      sample_step: getNumber(node, "sample_step", WAVEFORM_DEFAULTS.sample_step),
      mask_feather: getNumber(node, "mask_feather", WAVEFORM_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", WAVEFORM_DEFAULTS.invert_mask),
    };

    modeMetric.setValue(String(settings.scope_mode).replace("rgb_", "").replace("_", " "));
    resMetric.setValue(String(Math.round(settings.scope_resolution)));
    stepMetric.setValue(String(Math.round(settings.sample_step)));
    modeSelect.setValue(settings.scope_mode);
    gain.setValue(settings.gain);
    traceStrength.setValue(settings.trace_strength);
    graticule.setValue(settings.graticule);
    resolution.setValue(settings.scope_resolution);
    sampleStep.setValue(settings.sample_step);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawWaveformPreview(ctx, width, height, settings);
  }

  attachPanel(node, WAVEFORM_PANEL, panel, WAVEFORM_SIZE[0], WAVEFORM_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], WAVEFORM_PANEL);
  installRefreshHooks(node, "__mkrWaveformStudioHooks", refreshPanel);
  refreshPanel();
}

function buildVectorscopePanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Vectorscope Studio",
    subtitle: "Read hue distribution and saturation spread with a dedicated chroma scope.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#8ad86d");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const gainMetric = createGradeMetric("Gain", "1.00");
  const resMetric = createGradeMetric("Res", "440");
  const targetMetric = createGradeMetric("Targets", "On");
  metricsWrap.appendChild(gainMetric.element);
  metricsWrap.appendChild(resMetric.element);
  metricsWrap.appendChild(targetMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Clean", () => { applyValues(node, { scope_gain: 0.9, trace_strength: 0.8 }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Skin", () => { applyValues(node, { show_skin_line: true, show_targets: true, scope_gain: 1.1 }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Dense", () => { applyValues(node, { trace_strength: 1.3, graticule: 0.52 }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Scope Preview", "hue / saturation");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#ff6b52", label: "Reds" },
      { color: "#f0cb72", label: "Skins" },
      { color: "#56bfff", label: "Cyans" },
      { color: "#77ffaf", label: "Greens" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "Turn on targets when matching brand color zones, or disable them for a cleaner scope silhouette while balancing a shot.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Scope Response", "readability");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const gain = createGradeSlider({
    label: "Scope Gain",
    min: 0.25,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "scope_gain", VECTORSCOPE_DEFAULTS.scope_gain),
    onChange: (value) => { setWidgetValue(node, "scope_gain", value); refreshPanel(); },
  });
  const traceStrength = createGradeSlider({
    label: "Trace",
    min: 0.05,
    max: 2.0,
    step: 0.01,
    value: getNumber(node, "trace_strength", VECTORSCOPE_DEFAULTS.trace_strength),
    onChange: (value) => { setWidgetValue(node, "trace_strength", value); refreshPanel(); },
  });
  const graticule = createGradeSlider({
    label: "Graticule",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "graticule", VECTORSCOPE_DEFAULTS.graticule),
    onChange: (value) => { setWidgetValue(node, "graticule", value); refreshPanel(); },
  });
  const resolution = createGradeSlider({
    label: "Resolution",
    min: 256,
    max: 960,
    step: 1,
    value: getNumber(node, "scope_resolution", VECTORSCOPE_DEFAULTS.scope_resolution),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "scope_resolution", Math.round(value)); refreshPanel(); },
  });
  const sampleStep = createGradeSlider({
    label: "Sample Step",
    min: 1,
    max: 8,
    step: 1,
    value: getNumber(node, "sample_step", VECTORSCOPE_DEFAULTS.sample_step),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "sample_step", Math.round(value)); refreshPanel(); },
  });
  const showSkin = createGradeToggle({
    label: "Skin Line",
    checked: getBoolean(node, "show_skin_line", VECTORSCOPE_DEFAULTS.show_skin_line),
    description: "Show the classic skin-tone guide line.",
    onChange: (checked) => { setWidgetValue(node, "show_skin_line", checked); refreshPanel(); },
  });
  const showTargets = createGradeToggle({
    label: "Targets",
    checked: getBoolean(node, "show_targets", VECTORSCOPE_DEFAULTS.show_targets),
    description: "Draw hue target points around the scope ring.",
    onChange: (checked) => { setWidgetValue(node, "show_targets", checked); refreshPanel(); },
  });
  controls.appendChild(gain.element);
  controls.appendChild(traceStrength.element);
  controls.appendChild(graticule.element);
  controls.appendChild(resolution.element);
  controls.appendChild(sampleStep.element);
  controls.appendChild(showSkin.element);
  controls.appendChild(showTargets.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", VECTORSCOPE_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", VECTORSCOPE_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the chroma sample.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      scope_gain: getNumber(node, "scope_gain", VECTORSCOPE_DEFAULTS.scope_gain),
      trace_strength: getNumber(node, "trace_strength", VECTORSCOPE_DEFAULTS.trace_strength),
      graticule: getNumber(node, "graticule", VECTORSCOPE_DEFAULTS.graticule),
      scope_resolution: getNumber(node, "scope_resolution", VECTORSCOPE_DEFAULTS.scope_resolution),
      sample_step: getNumber(node, "sample_step", VECTORSCOPE_DEFAULTS.sample_step),
      show_skin_line: getBoolean(node, "show_skin_line", VECTORSCOPE_DEFAULTS.show_skin_line),
      show_targets: getBoolean(node, "show_targets", VECTORSCOPE_DEFAULTS.show_targets),
      mask_feather: getNumber(node, "mask_feather", VECTORSCOPE_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", VECTORSCOPE_DEFAULTS.invert_mask),
    };

    gainMetric.setValue(formatNumber(settings.scope_gain, 2));
    resMetric.setValue(String(Math.round(settings.scope_resolution)));
    targetMetric.setValue(settings.show_targets ? "On" : "Off");
    gain.setValue(settings.scope_gain);
    traceStrength.setValue(settings.trace_strength);
    graticule.setValue(settings.graticule);
    resolution.setValue(settings.scope_resolution);
    sampleStep.setValue(settings.sample_step);
    showSkin.setValue(settings.show_skin_line);
    showTargets.setValue(settings.show_targets);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawVectorscopePreview(ctx, width, height, settings);
  }

  attachPanel(node, VECTORSCOPE_PANEL, panel, VECTORSCOPE_SIZE[0], VECTORSCOPE_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], VECTORSCOPE_PANEL);
  installRefreshHooks(node, "__mkrVectorscopeStudioHooks", refreshPanel);
  refreshPanel();
}

function buildGamutWarningPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Gamut Warning Studio",
    subtitle: "Flag clipped channels and oversaturated highlight zones before a grade leaves safe territory.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ff9d52");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "Combined");
  const highMetric = createGradeMetric("High", "0.98");
  const satMetric = createGradeMetric("Sat", "0.90");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(highMetric.element);
  metricsWrap.appendChild(satMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Broadcast", () => { applyValues(node, { warning_mode: "broadcast_safe" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Chroma", () => { applyValues(node, { warning_mode: "chroma_stress" }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Combined", () => { applyValues(node, { warning_mode: "combined" }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Warning Preview", "clip / chroma");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#ff5b3d", label: "High Clip" },
      { color: "#4f93ff", label: "Low Clip" },
      { color: "#ffd65c", label: "Chroma Stress" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "Use combined mode to catch both legal-range violations and saturated highlight patches in the same pass.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Warning Rules", "thresholds");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const modeSelect = createSelectControl({
    label: "Mode",
    value: getValue(node, "warning_mode", GAMUT_WARNING_DEFAULTS.warning_mode),
    options: [
      { value: "broadcast_safe", label: "Broadcast Safe" },
      { value: "chroma_stress", label: "Chroma Stress" },
      { value: "combined", label: "Combined" },
    ],
    onChange: (value) => { setWidgetValue(node, "warning_mode", value); refreshPanel(); },
  });
  const lowClip = createGradeSlider({
    label: "Low Clip",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "low_clip", GAMUT_WARNING_DEFAULTS.low_clip),
    onChange: (value) => { setWidgetValue(node, "low_clip", value); refreshPanel(); },
  });
  const highClip = createGradeSlider({
    label: "High Clip",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "high_clip", GAMUT_WARNING_DEFAULTS.high_clip),
    onChange: (value) => { setWidgetValue(node, "high_clip", value); refreshPanel(); },
  });
  const satLimit = createGradeSlider({
    label: "Sat Limit",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "saturation_limit", GAMUT_WARNING_DEFAULTS.saturation_limit),
    onChange: (value) => { setWidgetValue(node, "saturation_limit", value); refreshPanel(); },
  });
  const highlightGate = createGradeSlider({
    label: "Highlight Gate",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "highlight_gate", GAMUT_WARNING_DEFAULTS.highlight_gate),
    onChange: (value) => { setWidgetValue(node, "highlight_gate", value); refreshPanel(); },
  });
  const opacity = createGradeSlider({
    label: "Overlay",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "overlay_opacity", GAMUT_WARNING_DEFAULTS.overlay_opacity),
    onChange: (value) => { setWidgetValue(node, "overlay_opacity", value); refreshPanel(); },
  });
  controls.appendChild(modeSelect.element);
  controls.appendChild(lowClip.element);
  controls.appendChild(highClip.element);
  controls.appendChild(satLimit.element);
  controls.appendChild(highlightGate.element);
  controls.appendChild(opacity.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", GAMUT_WARNING_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", GAMUT_WARNING_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it gates the warning overlay.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      warning_mode: getValue(node, "warning_mode", GAMUT_WARNING_DEFAULTS.warning_mode),
      low_clip: getNumber(node, "low_clip", GAMUT_WARNING_DEFAULTS.low_clip),
      high_clip: getNumber(node, "high_clip", GAMUT_WARNING_DEFAULTS.high_clip),
      saturation_limit: getNumber(node, "saturation_limit", GAMUT_WARNING_DEFAULTS.saturation_limit),
      highlight_gate: getNumber(node, "highlight_gate", GAMUT_WARNING_DEFAULTS.highlight_gate),
      overlay_opacity: getNumber(node, "overlay_opacity", GAMUT_WARNING_DEFAULTS.overlay_opacity),
      mask_feather: getNumber(node, "mask_feather", GAMUT_WARNING_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", GAMUT_WARNING_DEFAULTS.invert_mask),
    };

    modeMetric.setValue(String(settings.warning_mode).replace("_", " "));
    highMetric.setValue(formatNumber(settings.high_clip, 2));
    satMetric.setValue(formatNumber(settings.saturation_limit, 2));
    modeSelect.setValue(settings.warning_mode);
    lowClip.setValue(settings.low_clip);
    highClip.setValue(settings.high_clip);
    satLimit.setValue(settings.saturation_limit);
    highlightGate.setValue(settings.highlight_gate);
    opacity.setValue(settings.overlay_opacity);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawGamutWarningPreview(ctx, width, height, settings);
  }

  attachPanel(node, GAMUT_WARNING_PANEL, panel, GAMUT_WARNING_SIZE[0], GAMUT_WARNING_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], GAMUT_WARNING_PANEL);
  installRefreshHooks(node, "__mkrGamutWarningStudioHooks", refreshPanel);
  refreshPanel();
}

function buildHistogramPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Histogram Scope Studio",
    subtitle: "Check tonal distribution with luma, overlay, or stacked RGB histograms in-node.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#9f8dff");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "Overlay");
  const binsMetric = createGradeMetric("Bins", "128");
  const normMetric = createGradeMetric("Norm", "Peak");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(binsMetric.element);
  metricsWrap.appendChild(normMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Luma", () => { applyValues(node, { histogram_mode: "luma" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Overlay", () => { applyValues(node, { histogram_mode: "rgb_overlay" }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Stack", () => { applyValues(node, { histogram_mode: "rgb_stack" }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Histogram Preview", "distribution");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#f4f7fb", label: "Luma" },
      { color: "#ff5946", label: "Red" },
      { color: "#60ff91", label: "Green" },
      { color: "#539cff", label: "Blue" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "Overlay is fastest for balance checks. Switch to stacked RGB when you want cleaner channel separation in dense images.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Histogram Response", "shape");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const modeSelect = createSelectControl({
    label: "Mode",
    value: getValue(node, "histogram_mode", HISTOGRAM_DEFAULTS.histogram_mode),
    options: [
      { value: "luma", label: "Luma" },
      { value: "rgb_overlay", label: "RGB Overlay" },
      { value: "rgb_stack", label: "RGB Stack" },
    ],
    onChange: (value) => { setWidgetValue(node, "histogram_mode", value); refreshPanel(); },
  });
  const bins = createGradeSlider({
    label: "Bins",
    min: 32,
    max: 512,
    step: 1,
    value: getNumber(node, "bins", HISTOGRAM_DEFAULTS.bins),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "bins", Math.round(value)); refreshPanel(); },
  });
  const contrast = createGradeSlider({
    label: "Contrast",
    min: 0.25,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "contrast", HISTOGRAM_DEFAULTS.contrast),
    onChange: (value) => { setWidgetValue(node, "contrast", value); refreshPanel(); },
  });
  const fillOpacity = createGradeSlider({
    label: "Fill",
    min: 0.0,
    max: 1.0,
    step: 0.01,
    value: getNumber(node, "fill_opacity", HISTOGRAM_DEFAULTS.fill_opacity),
    onChange: (value) => { setWidgetValue(node, "fill_opacity", value); refreshPanel(); },
  });
  const normalizeSelect = createSelectControl({
    label: "Normalize",
    value: getValue(node, "normalize_mode", HISTOGRAM_DEFAULTS.normalize_mode),
    options: [
      { value: "peak", label: "Peak" },
      { value: "area", label: "Area" },
    ],
    onChange: (value) => { setWidgetValue(node, "normalize_mode", value); refreshPanel(); },
  });
  controls.appendChild(modeSelect.element);
  controls.appendChild(bins.element);
  controls.appendChild(contrast.element);
  controls.appendChild(fillOpacity.element);
  controls.appendChild(normalizeSelect.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", HISTOGRAM_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", HISTOGRAM_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the histogram sample.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      histogram_mode: getValue(node, "histogram_mode", HISTOGRAM_DEFAULTS.histogram_mode),
      bins: getNumber(node, "bins", HISTOGRAM_DEFAULTS.bins),
      contrast: getNumber(node, "contrast", HISTOGRAM_DEFAULTS.contrast),
      fill_opacity: getNumber(node, "fill_opacity", HISTOGRAM_DEFAULTS.fill_opacity),
      normalize_mode: getValue(node, "normalize_mode", HISTOGRAM_DEFAULTS.normalize_mode),
      mask_feather: getNumber(node, "mask_feather", HISTOGRAM_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", HISTOGRAM_DEFAULTS.invert_mask),
    };

    modeMetric.setValue(String(settings.histogram_mode).replace("rgb_", "").replace("_", " "));
    binsMetric.setValue(String(Math.round(settings.bins)));
    normMetric.setValue(String(settings.normalize_mode));
    modeSelect.setValue(settings.histogram_mode);
    bins.setValue(settings.bins);
    contrast.setValue(settings.contrast);
    fillOpacity.setValue(settings.fill_opacity);
    normalizeSelect.setValue(settings.normalize_mode);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawHistogramPreview(ctx, width, height, settings);
  }

  attachPanel(node, HISTOGRAM_PANEL, panel, HISTOGRAM_SIZE[0], HISTOGRAM_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], HISTOGRAM_PANEL);
  installRefreshHooks(node, "__mkrHistogramStudioHooks", refreshPanel);
  refreshPanel();
}

function buildSkinTonePanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Skin Tone Check Studio",
    subtitle: "Spot likely skin regions and see how tightly they sit inside your target hue corridor.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ffb772");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const hueMetric = createGradeMetric("Hue", "28°");
  const widthMetric = createGradeMetric("Width", "52°");
  const overlayMetric = createGradeMetric("Overlay", "0.82");
  metricsWrap.appendChild(hueMetric.element);
  metricsWrap.appendChild(widthMetric.element);
  metricsWrap.appendChild(overlayMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Portrait", () => { applyValues(node, { target_hue: 28, hue_width: 52, line_tolerance: 0.18 }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Warm", () => { applyValues(node, { target_hue: 34, hue_width: 60, line_tolerance: 0.20 }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Tight", () => { applyValues(node, { hue_width: 36, line_tolerance: 0.10 }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Skin Preview", "confidence");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#5cff9a", label: "In Corridor" },
      { color: "#ffcc6a", label: "Near Corridor" },
      { color: "#ff6248", label: "Off Corridor" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "This is a quick on-node skin sanity check, not a replacement for the qualifier. Use it to see whether faces stay inside the intended hue lane as you grade.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Detection", "target band");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const targetHue = createGradeSlider({
    label: "Target Hue",
    min: 0,
    max: 360,
    step: 0.5,
    value: getNumber(node, "target_hue", SKIN_TONE_DEFAULTS.target_hue),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "target_hue", value); refreshPanel(); },
  });
  const hueWidth = createGradeSlider({
    label: "Hue Width",
    min: 5,
    max: 160,
    step: 0.5,
    value: getNumber(node, "hue_width", SKIN_TONE_DEFAULTS.hue_width),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "hue_width", value); refreshPanel(); },
  });
  const satMin = createGradeSlider({
    label: "Sat Min",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "sat_min", SKIN_TONE_DEFAULTS.sat_min),
    onChange: (value) => { setWidgetValue(node, "sat_min", value); refreshPanel(); },
  });
  const satMax = createGradeSlider({
    label: "Sat Max",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "sat_max", SKIN_TONE_DEFAULTS.sat_max),
    onChange: (value) => { setWidgetValue(node, "sat_max", value); refreshPanel(); },
  });
  const valMin = createGradeSlider({
    label: "Val Min",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "val_min", SKIN_TONE_DEFAULTS.val_min),
    onChange: (value) => { setWidgetValue(node, "val_min", value); refreshPanel(); },
  });
  const tolerance = createGradeSlider({
    label: "Tolerance",
    min: 0.01,
    max: 0.6,
    step: 0.01,
    value: getNumber(node, "line_tolerance", SKIN_TONE_DEFAULTS.line_tolerance),
    onChange: (value) => { setWidgetValue(node, "line_tolerance", value); refreshPanel(); },
  });
  controls.appendChild(targetHue.element);
  controls.appendChild(hueWidth.element);
  controls.appendChild(satMin.element);
  controls.appendChild(satMax.element);
  controls.appendChild(valMin.element);
  controls.appendChild(tolerance.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  const outputSection = createGradeSection("Output", "overlay");
  const outputControls = document.createElement("div");
  outputControls.className = "mkr-grade-controls";
  const overlayOpacity = createGradeSlider({
    label: "Overlay",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "overlay_opacity", SKIN_TONE_DEFAULTS.overlay_opacity),
    onChange: (value) => { setWidgetValue(node, "overlay_opacity", value); refreshPanel(); },
  });
  const isolation = createGradeToggle({
    label: "Isolation",
    checked: getBoolean(node, "show_isolation", SKIN_TONE_DEFAULTS.show_isolation),
    description: "Show only the diagnostic heat map instead of overlaying it on the source.",
    onChange: (checked) => { setWidgetValue(node, "show_isolation", checked); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", SKIN_TONE_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", SKIN_TONE_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it gates the diagnostic.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  outputControls.appendChild(overlayOpacity.element);
  outputControls.appendChild(isolation.element);
  outputControls.appendChild(maskFeather.element);
  outputControls.appendChild(invertMask.element);
  outputSection.body.appendChild(outputControls);
  panel.appendChild(outputSection.section);

  function refreshPanel() {
    const settings = {
      target_hue: getNumber(node, "target_hue", SKIN_TONE_DEFAULTS.target_hue),
      hue_width: getNumber(node, "hue_width", SKIN_TONE_DEFAULTS.hue_width),
      sat_min: getNumber(node, "sat_min", SKIN_TONE_DEFAULTS.sat_min),
      sat_max: getNumber(node, "sat_max", SKIN_TONE_DEFAULTS.sat_max),
      val_min: getNumber(node, "val_min", SKIN_TONE_DEFAULTS.val_min),
      line_tolerance: getNumber(node, "line_tolerance", SKIN_TONE_DEFAULTS.line_tolerance),
      overlay_opacity: getNumber(node, "overlay_opacity", SKIN_TONE_DEFAULTS.overlay_opacity),
      show_isolation: getBoolean(node, "show_isolation", SKIN_TONE_DEFAULTS.show_isolation),
      mask_feather: getNumber(node, "mask_feather", SKIN_TONE_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", SKIN_TONE_DEFAULTS.invert_mask),
    };

    hueMetric.setValue(`${formatNumber(settings.target_hue, 1)}°`);
    widthMetric.setValue(`${formatNumber(settings.hue_width, 1)}°`);
    overlayMetric.setValue(formatNumber(settings.overlay_opacity, 2));
    targetHue.setValue(settings.target_hue);
    hueWidth.setValue(settings.hue_width);
    satMin.setValue(settings.sat_min);
    satMax.setValue(settings.sat_max);
    valMin.setValue(settings.val_min);
    tolerance.setValue(settings.line_tolerance);
    overlayOpacity.setValue(settings.overlay_opacity);
    isolation.setValue(settings.show_isolation);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawSkinTonePreview(ctx, width, height, settings);
  }

  attachPanel(node, SKIN_TONE_PANEL, panel, SKIN_TONE_SIZE[0], SKIN_TONE_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], SKIN_TONE_PANEL);
  installRefreshHooks(node, "__mkrSkinToneStudioHooks", refreshPanel);
  refreshPanel();
}

function buildRGBBalancePanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "RGB Balance Scope Studio",
    subtitle: "Track red, green, and blue bias through tonal zones or a fast column scan.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#a4b8ff");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "zones");
  const gainMetric = createGradeMetric("Response", "1.15");
  const tolMetric = createGradeMetric("Tol", "0.08");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(gainMetric.element);
  metricsWrap.appendChild(tolMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Zones", () => { applyValues(node, { analysis_mode: "zones" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Columns", () => { applyValues(node, { analysis_mode: "columns" }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Neutral", () => { applyValues(node, { response_gain: 1.0, neutral_tolerance: 0.07, show_reference: true }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Balance Preview", "rgb bias");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#ff6146", label: "Red Bias" },
      { color: "#64ff96", label: "Green Bias" },
      { color: "#5d9fff", label: "Blue Bias" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "Use Zones when you want a quick shadow/mid/high read. Switch to Columns when you want to spot a left-to-right white-balance drift through the frame.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const analysisSection = createGradeSection("Analysis Layout", "zones");
  const analysisControls = document.createElement("div");
  analysisControls.className = "mkr-grade-controls";
  const modeSelect = createSelectControl({
    label: "Analysis Mode",
    value: getValue(node, "analysis_mode", RGB_BALANCE_DEFAULTS.analysis_mode),
    options: [
      { value: "zones", label: "Shadow / Mid / High" },
      { value: "columns", label: "Column Scan" },
    ],
    onChange: (value) => { setWidgetValue(node, "analysis_mode", value); refreshPanel(); },
  });
  const shadowPoint = createGradeSlider({
    label: "Shadow Split",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "shadow_point", RGB_BALANCE_DEFAULTS.shadow_point),
    onChange: (value) => { setWidgetValue(node, "shadow_point", value); refreshPanel(); },
  });
  const highlightPoint = createGradeSlider({
    label: "Highlight Split",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "highlight_point", RGB_BALANCE_DEFAULTS.highlight_point),
    onChange: (value) => { setWidgetValue(node, "highlight_point", value); refreshPanel(); },
  });
  const softness = createGradeSlider({
    label: "Zone Softness",
    min: 0.02,
    max: 0.35,
    step: 0.01,
    value: getNumber(node, "zone_softness", RGB_BALANCE_DEFAULTS.zone_softness),
    onChange: (value) => { setWidgetValue(node, "zone_softness", value); refreshPanel(); },
  });
  analysisControls.appendChild(modeSelect.element);
  analysisControls.appendChild(shadowPoint.element);
  analysisControls.appendChild(highlightPoint.element);
  analysisControls.appendChild(softness.element);
  analysisSection.body.appendChild(analysisControls);
  panel.appendChild(analysisSection.section);

  const responseSection = createGradeSection("Scope Response", "reference");
  const responseControls = document.createElement("div");
  responseControls.className = "mkr-grade-controls";
  const responseGain = createGradeSlider({
    label: "Response Gain",
    min: 0.25,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "response_gain", RGB_BALANCE_DEFAULTS.response_gain),
    onChange: (value) => { setWidgetValue(node, "response_gain", value); refreshPanel(); },
  });
  const neutralTolerance = createGradeSlider({
    label: "Neutral Tol",
    min: 0.02,
    max: 0.25,
    step: 0.01,
    value: getNumber(node, "neutral_tolerance", RGB_BALANCE_DEFAULTS.neutral_tolerance),
    onChange: (value) => { setWidgetValue(node, "neutral_tolerance", value); refreshPanel(); },
  });
  const showReference = createGradeToggle({
    label: "Reference Lines",
    checked: getBoolean(node, "show_reference", RGB_BALANCE_DEFAULTS.show_reference),
    description: "Draw center and tolerance lines so neutral balance is easier to read.",
    onChange: (checked) => { setWidgetValue(node, "show_reference", checked); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", RGB_BALANCE_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", RGB_BALANCE_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the sampled image area.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  responseControls.appendChild(responseGain.element);
  responseControls.appendChild(neutralTolerance.element);
  responseControls.appendChild(showReference.element);
  responseControls.appendChild(maskFeather.element);
  responseControls.appendChild(invertMask.element);
  responseSection.body.appendChild(responseControls);
  panel.appendChild(responseSection.section);

  function refreshPanel() {
    const settings = {
      analysis_mode: getValue(node, "analysis_mode", RGB_BALANCE_DEFAULTS.analysis_mode),
      shadow_point: getNumber(node, "shadow_point", RGB_BALANCE_DEFAULTS.shadow_point),
      highlight_point: getNumber(node, "highlight_point", RGB_BALANCE_DEFAULTS.highlight_point),
      zone_softness: getNumber(node, "zone_softness", RGB_BALANCE_DEFAULTS.zone_softness),
      response_gain: getNumber(node, "response_gain", RGB_BALANCE_DEFAULTS.response_gain),
      neutral_tolerance: getNumber(node, "neutral_tolerance", RGB_BALANCE_DEFAULTS.neutral_tolerance),
      show_reference: getBoolean(node, "show_reference", RGB_BALANCE_DEFAULTS.show_reference),
      mask_feather: getNumber(node, "mask_feather", RGB_BALANCE_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", RGB_BALANCE_DEFAULTS.invert_mask),
    };

    modeMetric.setValue(settings.analysis_mode);
    gainMetric.setValue(formatNumber(settings.response_gain, 2));
    tolMetric.setValue(formatNumber(settings.neutral_tolerance, 2));
    modeSelect.setValue(settings.analysis_mode);
    shadowPoint.setValue(settings.shadow_point);
    highlightPoint.setValue(settings.highlight_point);
    softness.setValue(settings.zone_softness);
    responseGain.setValue(settings.response_gain);
    neutralTolerance.setValue(settings.neutral_tolerance);
    showReference.setValue(settings.show_reference);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawRGBBalancePreview(ctx, width, height, settings);
  }

  attachPanel(node, RGB_BALANCE_PANEL, panel, RGB_BALANCE_SIZE[0], RGB_BALANCE_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], RGB_BALANCE_PANEL);
  installRefreshHooks(node, "__mkrRGBBalanceStudioHooks", refreshPanel);
  refreshPanel();
}

function buildNeutralityMapPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Neutrality Map Studio",
    subtitle: "Reveal near-neutral regions and show whether they lean warm, cool, green, or magenta.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#d9c38a");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const satMetric = createGradeMetric("Sat", "0.18");
  const gainMetric = createGradeMetric("Cast", "1.35");
  const viewMetric = createGradeMetric("View", "Overlay");
  metricsWrap.appendChild(satMetric.element);
  metricsWrap.appendChild(gainMetric.element);
  metricsWrap.appendChild(viewMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Whites", () => { applyValues(node, { sat_ceiling: 0.12, luma_floor: 0.35, luma_ceiling: 1.0 }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Mids", () => { applyValues(node, { sat_ceiling: 0.18, luma_floor: 0.10, luma_ceiling: 0.82 }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Isolation", () => { applyValues(node, { show_isolation: true, overlay_opacity: 0.9 }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Neutral Preview", "cast map");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#ffb05e", label: "Warm" },
      { color: "#69a8ff", label: "Cool" },
      { color: "#72ff9f", label: "Green" },
      { color: "#ff80d9", label: "Magenta" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "This is best used on walls, wardrobe neutrals, practical whites, or product surfaces when you want to catch a subtle cast before it spreads through the grade.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const gateSection = createGradeSection("Neutral Gate", "candidate range");
  const gateControls = document.createElement("div");
  gateControls.className = "mkr-grade-controls";
  const satCeiling = createGradeSlider({
    label: "Sat Ceiling",
    min: 0.02,
    max: 0.60,
    step: 0.01,
    value: getNumber(node, "sat_ceiling", NEUTRALITY_MAP_DEFAULTS.sat_ceiling),
    onChange: (value) => { setWidgetValue(node, "sat_ceiling", value); refreshPanel(); },
  });
  const lumaFloor = createGradeSlider({
    label: "Luma Floor",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "luma_floor", NEUTRALITY_MAP_DEFAULTS.luma_floor),
    onChange: (value) => { setWidgetValue(node, "luma_floor", value); refreshPanel(); },
  });
  const lumaCeiling = createGradeSlider({
    label: "Luma Ceiling",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "luma_ceiling", NEUTRALITY_MAP_DEFAULTS.luma_ceiling),
    onChange: (value) => { setWidgetValue(node, "luma_ceiling", value); refreshPanel(); },
  });
  const castGain = createGradeSlider({
    label: "Cast Gain",
    min: 0.2,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "cast_gain", NEUTRALITY_MAP_DEFAULTS.cast_gain),
    onChange: (value) => { setWidgetValue(node, "cast_gain", value); refreshPanel(); },
  });
  const warmthBias = createGradeSlider({
    label: "Warm Bias",
    min: -0.35,
    max: 0.35,
    step: 0.01,
    value: getNumber(node, "warmth_bias", NEUTRALITY_MAP_DEFAULTS.warmth_bias),
    onChange: (value) => { setWidgetValue(node, "warmth_bias", value); refreshPanel(); },
  });
  gateControls.appendChild(satCeiling.element);
  gateControls.appendChild(lumaFloor.element);
  gateControls.appendChild(lumaCeiling.element);
  gateControls.appendChild(castGain.element);
  gateControls.appendChild(warmthBias.element);
  gateSection.body.appendChild(gateControls);
  panel.appendChild(gateSection.section);

  const outputSection = createGradeSection("Output", "overlay");
  const outputControls = document.createElement("div");
  outputControls.className = "mkr-grade-controls";
  const overlayOpacity = createGradeSlider({
    label: "Overlay",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "overlay_opacity", NEUTRALITY_MAP_DEFAULTS.overlay_opacity),
    onChange: (value) => { setWidgetValue(node, "overlay_opacity", value); refreshPanel(); },
  });
  const isolation = createGradeToggle({
    label: "Isolation",
    checked: getBoolean(node, "show_isolation", NEUTRALITY_MAP_DEFAULTS.show_isolation),
    description: "Show only the neutrality diagnostic map instead of overlaying it on the source.",
    onChange: (checked) => { setWidgetValue(node, "show_isolation", checked); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", NEUTRALITY_MAP_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", NEUTRALITY_MAP_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it gates the neutrality analysis.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  outputControls.appendChild(overlayOpacity.element);
  outputControls.appendChild(isolation.element);
  outputControls.appendChild(maskFeather.element);
  outputControls.appendChild(invertMask.element);
  outputSection.body.appendChild(outputControls);
  panel.appendChild(outputSection.section);

  function refreshPanel() {
    const settings = {
      sat_ceiling: getNumber(node, "sat_ceiling", NEUTRALITY_MAP_DEFAULTS.sat_ceiling),
      luma_floor: getNumber(node, "luma_floor", NEUTRALITY_MAP_DEFAULTS.luma_floor),
      luma_ceiling: getNumber(node, "luma_ceiling", NEUTRALITY_MAP_DEFAULTS.luma_ceiling),
      cast_gain: getNumber(node, "cast_gain", NEUTRALITY_MAP_DEFAULTS.cast_gain),
      warmth_bias: getNumber(node, "warmth_bias", NEUTRALITY_MAP_DEFAULTS.warmth_bias),
      overlay_opacity: getNumber(node, "overlay_opacity", NEUTRALITY_MAP_DEFAULTS.overlay_opacity),
      show_isolation: getBoolean(node, "show_isolation", NEUTRALITY_MAP_DEFAULTS.show_isolation),
      mask_feather: getNumber(node, "mask_feather", NEUTRALITY_MAP_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", NEUTRALITY_MAP_DEFAULTS.invert_mask),
    };

    satMetric.setValue(formatNumber(settings.sat_ceiling, 2));
    gainMetric.setValue(formatNumber(settings.cast_gain, 2));
    viewMetric.setValue(settings.show_isolation ? "Isolation" : "Overlay");
    satCeiling.setValue(settings.sat_ceiling);
    lumaFloor.setValue(settings.luma_floor);
    lumaCeiling.setValue(settings.luma_ceiling);
    castGain.setValue(settings.cast_gain);
    warmthBias.setValue(settings.warmth_bias);
    overlayOpacity.setValue(settings.overlay_opacity);
    isolation.setValue(settings.show_isolation);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawNeutralityMapPreview(ctx, width, height, settings);
  }

  attachPanel(node, NEUTRALITY_MAP_PANEL, panel, NEUTRALITY_MAP_SIZE[0], NEUTRALITY_MAP_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], NEUTRALITY_MAP_PANEL);
  installRefreshHooks(node, "__mkrNeutralityMapStudioHooks", refreshPanel);
  refreshPanel();
}

function buildHueBandPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Hue Band Scope Studio",
    subtitle: "Read hue density as a spectral band so dominant ranges jump out immediately.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ffb35b");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const binsMetric = createGradeMetric("Bins", "192");
  const densityMetric = createGradeMetric("Density", "1.10");
  const sampleMetric = createGradeMetric("Step", "2");
  metricsWrap.appendChild(binsMetric.element);
  metricsWrap.appendChild(densityMetric.element);
  metricsWrap.appendChild(sampleMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Dense", () => { applyValues(node, { density_gain: 1.4, sat_floor: 0.06 }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Clean", () => { applyValues(node, { density_gain: 0.95, val_floor: 0.18 }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Fast", () => { applyValues(node, { sample_step: 4, bins: 128 }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Hue Preview", "spectrum");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#ff5a44", label: "Warm Peaks" },
      { color: "#8aff67", label: "Green Peaks" },
      { color: "#5f9fff", label: "Cool Peaks" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "This sits between histogram and vectorscope: it shows which hue families dominate, without hiding the density behind a circular readout.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const densitySection = createGradeSection("Density", "sampling");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const bins = createGradeSlider({
    label: "Bins",
    min: 48,
    max: 512,
    step: 1,
    value: getNumber(node, "bins", HUE_BAND_DEFAULTS.bins),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "bins", Math.round(value)); refreshPanel(); },
  });
  const densityGain = createGradeSlider({
    label: "Density Gain",
    min: 0.2,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "density_gain", HUE_BAND_DEFAULTS.density_gain),
    onChange: (value) => { setWidgetValue(node, "density_gain", value); refreshPanel(); },
  });
  const satFloor = createGradeSlider({
    label: "Sat Floor",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "sat_floor", HUE_BAND_DEFAULTS.sat_floor),
    onChange: (value) => { setWidgetValue(node, "sat_floor", value); refreshPanel(); },
  });
  const valFloor = createGradeSlider({
    label: "Val Floor",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "val_floor", HUE_BAND_DEFAULTS.val_floor),
    onChange: (value) => { setWidgetValue(node, "val_floor", value); refreshPanel(); },
  });
  const graticule = createGradeSlider({
    label: "Graticule",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "graticule", HUE_BAND_DEFAULTS.graticule),
    onChange: (value) => { setWidgetValue(node, "graticule", value); refreshPanel(); },
  });
  const sampleStep = createGradeSlider({
    label: "Sample Step",
    min: 1,
    max: 8,
    step: 1,
    value: getNumber(node, "sample_step", HUE_BAND_DEFAULTS.sample_step),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "sample_step", Math.round(value)); refreshPanel(); },
  });
  controls.appendChild(bins.element);
  controls.appendChild(densityGain.element);
  controls.appendChild(satFloor.element);
  controls.appendChild(valFloor.element);
  controls.appendChild(graticule.element);
  controls.appendChild(sampleStep.element);
  densitySection.body.appendChild(controls);
  panel.appendChild(densitySection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", HUE_BAND_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", HUE_BAND_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the hue sample.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      bins: getNumber(node, "bins", HUE_BAND_DEFAULTS.bins),
      density_gain: getNumber(node, "density_gain", HUE_BAND_DEFAULTS.density_gain),
      sat_floor: getNumber(node, "sat_floor", HUE_BAND_DEFAULTS.sat_floor),
      val_floor: getNumber(node, "val_floor", HUE_BAND_DEFAULTS.val_floor),
      graticule: getNumber(node, "graticule", HUE_BAND_DEFAULTS.graticule),
      sample_step: getNumber(node, "sample_step", HUE_BAND_DEFAULTS.sample_step),
      mask_feather: getNumber(node, "mask_feather", HUE_BAND_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", HUE_BAND_DEFAULTS.invert_mask),
    };

    binsMetric.setValue(String(Math.round(settings.bins)));
    densityMetric.setValue(formatNumber(settings.density_gain, 2));
    sampleMetric.setValue(String(Math.round(settings.sample_step)));
    bins.setValue(settings.bins);
    densityGain.setValue(settings.density_gain);
    satFloor.setValue(settings.sat_floor);
    valFloor.setValue(settings.val_floor);
    graticule.setValue(settings.graticule);
    sampleStep.setValue(settings.sample_step);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawHueBandPreview(ctx, width, height, settings);
  }

  attachPanel(node, HUE_BAND_PANEL, panel, HUE_BAND_SIZE[0], HUE_BAND_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], HUE_BAND_PANEL);
  installRefreshHooks(node, "__mkrHueBandStudioHooks", refreshPanel);
  refreshPanel();
}

function buildSatLumaPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Sat / Luma Scope Studio",
    subtitle: "Plot chroma density against luminance to see where vivid color really lives in the frame.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#7bd7ff");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const densityMetric = createGradeMetric("Density", "1.00");
  const floorMetric = createGradeMetric("Sat Floor", "0.04");
  const sampleMetric = createGradeMetric("Step", "2");
  metricsWrap.appendChild(densityMetric.element);
  metricsWrap.appendChild(floorMetric.element);
  metricsWrap.appendChild(sampleMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Rich Color", () => { applyValues(node, { density_gain: 1.35, sat_floor: 0.02 }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Cleaner", () => { applyValues(node, { density_gain: 0.9, sat_floor: 0.10 }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Fast", () => { applyValues(node, { sample_step: 4 }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Scope Preview", "sat vs luma");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-analyze-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  previewSection.body.appendChild(
    createLegend([
      { color: "#c6d7ff", label: "Low Sat / High Luma" },
      { color: "#ffd76d", label: "Mid Density" },
      { color: "#ff6d56", label: "High Sat" },
    ])
  );
  const hint = document.createElement("div");
  hint.className = "mkr-color-analyze-hint";
  hint.textContent = "This is useful when a grade feels too loud or too flat: it reveals whether saturation is piling up in highlights, mids, or darker parts of the image.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const scopeSection = createGradeSection("Scope Response", "density");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const densityGain = createGradeSlider({
    label: "Density Gain",
    min: 0.2,
    max: 3.0,
    step: 0.01,
    value: getNumber(node, "density_gain", SAT_LUMA_DEFAULTS.density_gain),
    onChange: (value) => { setWidgetValue(node, "density_gain", value); refreshPanel(); },
  });
  const satFloor = createGradeSlider({
    label: "Sat Floor",
    min: 0,
    max: 0.5,
    step: 0.01,
    value: getNumber(node, "sat_floor", SAT_LUMA_DEFAULTS.sat_floor),
    onChange: (value) => { setWidgetValue(node, "sat_floor", value); refreshPanel(); },
  });
  const graticule = createGradeSlider({
    label: "Graticule",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "graticule", SAT_LUMA_DEFAULTS.graticule),
    onChange: (value) => { setWidgetValue(node, "graticule", value); refreshPanel(); },
  });
  const sampleStep = createGradeSlider({
    label: "Sample Step",
    min: 1,
    max: 8,
    step: 1,
    value: getNumber(node, "sample_step", SAT_LUMA_DEFAULTS.sample_step),
    decimals: 0,
    onChange: (value) => { setWidgetValue(node, "sample_step", Math.round(value)); refreshPanel(); },
  });
  controls.appendChild(densityGain.element);
  controls.appendChild(satFloor.element);
  controls.appendChild(graticule.element);
  controls.appendChild(sampleStep.element);
  scopeSection.body.appendChild(controls);
  panel.appendChild(scopeSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", SAT_LUMA_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", SAT_LUMA_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it limits the sat/luma sample.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      density_gain: getNumber(node, "density_gain", SAT_LUMA_DEFAULTS.density_gain),
      sat_floor: getNumber(node, "sat_floor", SAT_LUMA_DEFAULTS.sat_floor),
      graticule: getNumber(node, "graticule", SAT_LUMA_DEFAULTS.graticule),
      sample_step: getNumber(node, "sample_step", SAT_LUMA_DEFAULTS.sample_step),
      mask_feather: getNumber(node, "mask_feather", SAT_LUMA_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", SAT_LUMA_DEFAULTS.invert_mask),
    };

    densityMetric.setValue(formatNumber(settings.density_gain, 2));
    floorMetric.setValue(formatNumber(settings.sat_floor, 2));
    sampleMetric.setValue(String(Math.round(settings.sample_step)));
    densityGain.setValue(settings.density_gain);
    satFloor.setValue(settings.sat_floor);
    graticule.setValue(settings.graticule);
    sampleStep.setValue(settings.sample_step);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawSatLumaPreview(ctx, width, height, settings);
  }

  attachPanel(node, SAT_LUMA_PANEL, panel, SAT_LUMA_SIZE[0], SAT_LUMA_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], SAT_LUMA_PANEL);
  installRefreshHooks(node, "__mkrSatLumaStudioHooks", refreshPanel);
  refreshPanel();
}

function prepareNode(node) {
  if (matchesNode(node, WAVEFORM_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: WAVEFORM_DEFAULTS,
      numericSpecs: WAVEFORM_NUMERIC,
      booleanKeys: ["invert_mask"],
      legacyNames: Object.keys(WAVEFORM_DEFAULTS),
    });
    if (!node.__mkrWaveformScopeStudioBuilt) {
      node.__mkrWaveformScopeStudioBuilt = true;
      buildWaveformPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], WAVEFORM_PANEL);
    }
    return;
  }

  if (matchesNode(node, VECTORSCOPE_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: VECTORSCOPE_DEFAULTS,
      numericSpecs: VECTORSCOPE_NUMERIC,
      booleanKeys: ["show_skin_line", "show_targets", "invert_mask"],
      legacyNames: Object.keys(VECTORSCOPE_DEFAULTS),
    });
    if (!node.__mkrVectorscopeStudioBuilt) {
      node.__mkrVectorscopeStudioBuilt = true;
      buildVectorscopePanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], VECTORSCOPE_PANEL);
    }
    return;
  }

  if (matchesNode(node, GAMUT_WARNING_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: GAMUT_WARNING_DEFAULTS,
      numericSpecs: GAMUT_WARNING_NUMERIC,
      booleanKeys: ["invert_mask"],
      legacyNames: Object.keys(GAMUT_WARNING_DEFAULTS),
    });
    if (!node.__mkrGamutWarningStudioBuilt) {
      node.__mkrGamutWarningStudioBuilt = true;
      buildGamutWarningPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], GAMUT_WARNING_PANEL);
    }
    return;
  }

  if (matchesNode(node, HISTOGRAM_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: HISTOGRAM_DEFAULTS,
      numericSpecs: HISTOGRAM_NUMERIC,
      booleanKeys: ["invert_mask"],
      legacyNames: Object.keys(HISTOGRAM_DEFAULTS),
    });
    if (!node.__mkrHistogramStudioBuilt) {
      node.__mkrHistogramStudioBuilt = true;
      buildHistogramPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], HISTOGRAM_PANEL);
    }
    return;
  }

  if (matchesNode(node, SKIN_TONE_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: SKIN_TONE_DEFAULTS,
      numericSpecs: SKIN_TONE_NUMERIC,
      booleanKeys: ["show_isolation", "invert_mask"],
      legacyNames: Object.keys(SKIN_TONE_DEFAULTS),
    });
    if (!node.__mkrSkinToneStudioBuilt) {
      node.__mkrSkinToneStudioBuilt = true;
      buildSkinTonePanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], SKIN_TONE_PANEL);
    }
    return;
  }

  if (matchesNode(node, RGB_BALANCE_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: RGB_BALANCE_DEFAULTS,
      numericSpecs: RGB_BALANCE_NUMERIC,
      booleanKeys: ["show_reference", "invert_mask"],
      legacyNames: Object.keys(RGB_BALANCE_DEFAULTS),
    });
    if (!node.__mkrRGBBalanceStudioBuilt) {
      node.__mkrRGBBalanceStudioBuilt = true;
      buildRGBBalancePanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], RGB_BALANCE_PANEL);
    }
    return;
  }

  if (matchesNode(node, NEUTRALITY_MAP_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: NEUTRALITY_MAP_DEFAULTS,
      numericSpecs: NEUTRALITY_MAP_NUMERIC,
      booleanKeys: ["show_isolation", "invert_mask"],
      legacyNames: Object.keys(NEUTRALITY_MAP_DEFAULTS),
    });
    if (!node.__mkrNeutralityMapStudioBuilt) {
      node.__mkrNeutralityMapStudioBuilt = true;
      buildNeutralityMapPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], NEUTRALITY_MAP_PANEL);
    }
    return;
  }

  if (matchesNode(node, HUE_BAND_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: HUE_BAND_DEFAULTS,
      numericSpecs: HUE_BAND_NUMERIC,
      booleanKeys: ["invert_mask"],
      legacyNames: Object.keys(HUE_BAND_DEFAULTS),
    });
    if (!node.__mkrHueBandStudioBuilt) {
      node.__mkrHueBandStudioBuilt = true;
      buildHueBandPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], HUE_BAND_PANEL);
    }
    return;
  }

  if (matchesNode(node, SAT_LUMA_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: SAT_LUMA_DEFAULTS,
      numericSpecs: SAT_LUMA_NUMERIC,
      booleanKeys: ["invert_mask"],
      legacyNames: Object.keys(SAT_LUMA_DEFAULTS),
    });
    if (!node.__mkrSatLumaStudioBuilt) {
      node.__mkrSatLumaStudioBuilt = true;
      buildSatLumaPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], SAT_LUMA_PANEL);
    }
  }
}

function scanGraphNodes() {
  const nodes = app?.graph?._nodes || [];
  for (const node of nodes) {
    prepareNode(node);
  }
}

app.registerExtension({
  name: EXTENSION_NAME,
  nodeCreated(node) {
    requestAnimationFrame(() => prepareNode(node));
  },
  async afterConfigureGraph() {
    scanGraphNodes();
  },
  async setup() {
    requestAnimationFrame(scanGraphNodes);
    setTimeout(scanGraphNodes, 180);
    setTimeout(scanGraphNodes, 700);
  },
});
