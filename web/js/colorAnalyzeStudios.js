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

const WAVEFORM_PANEL = "mkr_color_waveform_scope_studio";
const VECTORSCOPE_PANEL = "mkr_color_vectorscope_studio";
const GAMUT_WARNING_PANEL = "mkr_color_gamut_warning_studio";
const HISTOGRAM_PANEL = "mkr_color_histogram_scope_studio";
const SKIN_TONE_PANEL = "mkr_color_skin_tone_check_studio";

const WAVEFORM_SIZE = [860, 760];
const VECTORSCOPE_SIZE = [760, 760];
const GAMUT_WARNING_SIZE = [760, 720];
const HISTOGRAM_SIZE = [820, 740];
const SKIN_TONE_SIZE = [760, 760];

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
