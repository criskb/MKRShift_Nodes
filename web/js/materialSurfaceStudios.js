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

const EXTENSION_NAME = "MKRShift.MaterialSurfaceStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-material-surface-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.18)") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(18,21,26,0.98)");
  bg.addColorStop(1, "rgba(30,34,40,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i += 1) {
    const x = frame.x + ((frame.w * i) / 5);
    const y = frame.y + ((frame.h * i) / 5);
    ctx.beginPath();
    ctx.moveTo(x, frame.y);
    ctx.lineTo(x, frame.y + frame.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(frame.x, y);
    ctx.lineTo(frame.x + frame.w, y);
    ctx.stroke();
  }

  ctx.strokeStyle = accent;
  ctx.strokeRect(frame.x, frame.y, frame.w, frame.h);
  return frame;
}

function drawLabel(ctx, text, x, y, color = "rgba(244,248,252,0.88)", size = 11, align = "left") {
  ctx.save();
  ctx.font = `600 ${size}px sans-serif`;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
  ctx.restore();
}

function drawScalarResponseCurve(ctx, frame, curveColor, sampleFn) {
  ctx.strokeStyle = curveColor;
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  for (let step = 0; step <= 96; step += 1) {
    const t = step / 96;
    const x = frame.x + (frame.w * t);
    const y = sampleFn(t);
    const py = frame.y + ((1 - clamp(y, 0, 1)) * (frame.h - 44)) + 18;
    if (step === 0) ctx.moveTo(x, py);
    else ctx.lineTo(x, py);
  }
  ctx.stroke();
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-surface-select {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
      margin-top: 4px;
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
  select.className = "mkr-surface-select";
  for (const option of options) {
    const opt = document.createElement("option");
    opt.value = String(option.value);
    opt.textContent = option.label;
    select.appendChild(opt);
  }
  select.value = String(value);
  select.addEventListener("change", () => {
    head.lastChild.textContent = select.value;
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

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values || {})) {
    setWidgetValue(node, key, value);
  }
}

function installRefreshHooks(node, key, refresh) {
  if (!node || node[key]) return;
  node[key] = true;

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigureMaterialSurfacePanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeMaterialSurfacePanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedMaterialSurfacePanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawRoughnessPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(144,208,255,0.30)");
  const gamma = getNumber(node, "gamma", config.defaults.gamma);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const blur = getNumber(node, "blur_radius", config.defaults.blur_radius);
  const detail = getNumber(node, "detail_strength", config.defaults.detail_strength);
  const invert = getBoolean(node, "invert_values", config.defaults.invert_values);

  const grad = ctx.createLinearGradient(frame.x, frame.y + frame.h - 24, frame.x + frame.w, frame.y + frame.h - 24);
  grad.addColorStop(0, invert ? "rgba(236,239,244,1)" : "rgba(28,32,38,1)");
  grad.addColorStop(1, invert ? "rgba(28,32,38,1)" : "rgba(236,239,244,1)");
  ctx.fillStyle = grad;
  ctx.fillRect(frame.x, frame.y + frame.h - 26, frame.w, 16);

  ctx.fillStyle = `rgba(144,208,255,${0.06 + (detail * 0.10)})`;
  ctx.fillRect(frame.x + 12, frame.y + 16, frame.w - 24, 18);

  drawScalarResponseCurve(ctx, frame, "rgba(154,214,255,0.96)", (t) => {
    const contrasted = clamp(((t - 0.5) * contrast) + 0.5, 0, 1);
    const shaped = Math.pow(contrasted, 1 / Math.max(0.1, gamma));
    return invert ? 1 - shaped : shaped;
  });

  ctx.strokeStyle = "rgba(255,255,255,0.20)";
  ctx.setLineDash([6, 6]);
  ctx.beginPath();
  ctx.moveTo(frame.x + 12, frame.y + frame.h - 54);
  ctx.lineTo(frame.x + frame.w - 12, frame.y + 20);
  ctx.stroke();
  ctx.setLineDash([]);

  drawLabel(ctx, "gloss", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.66)", 10);
  drawLabel(ctx, "rough", frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.82)", 10, "right");
  drawLabel(ctx, `${formatNumber(blur, 1)} px blur`, frame.x + frame.w - 10, frame.y + frame.h - 10, "rgba(245,247,250,0.60)", 10, "right");
}

function drawSpecularPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,221,131,0.30)");
  const gamma = getNumber(node, "gamma", config.defaults.gamma);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const suppress = getNumber(node, "saturation_suppress", config.defaults.saturation_suppress);
  const detail = getNumber(node, "detail_strength", config.defaults.detail_strength);

  ctx.fillStyle = "rgba(17,19,24,0.96)";
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const hotspot = ctx.createRadialGradient(frame.x + (frame.w * 0.72), frame.y + (frame.h * 0.34), 2, frame.x + (frame.w * 0.72), frame.y + (frame.h * 0.34), frame.w * 0.38);
  hotspot.addColorStop(0, `rgba(255,255,255,${0.62 + (detail * 0.18)})`);
  hotspot.addColorStop(0.35, `rgba(255,230,170,${0.22 + ((1 - suppress) * 0.18)})`);
  hotspot.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = hotspot;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  drawScalarResponseCurve(ctx, frame, "rgba(255,221,131,0.98)", (t) => {
    const sharpened = Math.pow(clamp(((t - 0.5) * contrast) + 0.5, 0, 1), 1 / Math.max(0.1, gamma));
    return clamp(Math.pow(sharpened, 0.7 + (suppress * 0.5)), 0, 1);
  });

  drawLabel(ctx, "specular response", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.82)", 10);
  drawLabel(ctx, `sat suppress ${formatNumber(suppress, 2)}`, frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.64)", 10, "right");
}

function drawMetalnessPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(119,255,214,0.28)");
  const detail = getNumber(node, "detail_strength", config.defaults.detail_strength);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const gamma = getNumber(node, "gamma", config.defaults.gamma);

  const left = frame.x + 24;
  const mid = frame.x + (frame.w * 0.52);
  const right = frame.x + frame.w - 24;
  const top = frame.y + 36;
  const bottom = frame.y + frame.h - 44;

  ctx.fillStyle = "rgba(109,125,138,0.48)";
  ctx.fillRect(left, top, mid - left, bottom - top);
  ctx.fillStyle = "rgba(189,174,124,0.56)";
  ctx.fillRect(mid, top, right - mid, bottom - top);

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1;
  ctx.strokeRect(left, top, right - left, bottom - top);
  ctx.beginPath();
  ctx.moveTo(mid, top);
  ctx.lineTo(mid, bottom);
  ctx.stroke();

  drawScalarResponseCurve(ctx, frame, "rgba(119,255,214,0.95)", (t) => {
    const biased = clamp(((t - 0.5) * contrast) + 0.5, 0, 1);
    return Math.pow(biased, 1 / Math.max(0.1, gamma * (1 + (detail * 0.18))));
  });

  drawLabel(ctx, "dielectric", left + 8, top - 14, "rgba(245,247,250,0.66)", 10);
  drawLabel(ctx, "metal", right - 8, top - 14, "rgba(245,247,250,0.82)", 10, "right");
}

function drawCavityPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(182,158,255,0.28)");
  const polarity = String(getValue(node, "polarity", config.defaults.polarity));
  const radius = getNumber(node, "radius", config.defaults.radius);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 10;
  ctx.lineCap = "round";
  for (let i = 0; i < 5; i += 1) {
    const y = frame.y + 24 + (i * ((frame.h - 48) / 4));
    ctx.beginPath();
    ctx.moveTo(frame.x + 28, y + 8);
    ctx.bezierCurveTo(frame.x + (frame.w * 0.28), y - 22, frame.x + (frame.w * 0.58), y + 30, frame.x + frame.w - 28, y - 6);
    ctx.stroke();
  }

  const wearColor = polarity === "convex" ? "rgba(255,181,120,0.96)" : (polarity === "both" ? "rgba(218,196,255,0.96)" : "rgba(150,216,255,0.96)");
  drawScalarResponseCurve(ctx, frame, wearColor, (t) => {
    const wave = Math.abs(Math.sin((t * Math.PI * 5.2) + 0.2));
    return clamp(Math.pow(wave, 1.4 - (contrast * 0.18)) * (0.65 + (radius * 0.03)), 0, 1);
  });

  drawLabel(ctx, polarity, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.82)", 10);
}

function drawEdgeWearPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,171,122,0.28)");
  const edgeRadius = getNumber(node, "edge_radius", config.defaults.edge_radius);
  const detail = getNumber(node, "detail_strength", config.defaults.detail_strength);
  const blur = getNumber(node, "blur_radius", config.defaults.blur_radius);

  const box = {
    x: frame.x + 42,
    y: frame.y + 32,
    w: frame.w - 84,
    h: frame.h - 76,
  };
  ctx.fillStyle = "rgba(78,84,92,0.48)";
  ctx.fillRect(box.x, box.y, box.w, box.h);
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.lineWidth = 1.2;
  ctx.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);

  const glow = ctx.createLinearGradient(box.x, box.y, box.x + box.w, box.y + box.h);
  glow.addColorStop(0, `rgba(255,193,140,${0.16 + (detail * 0.12)})`);
  glow.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(box.x, box.y, box.w, box.h);

  ctx.strokeStyle = "rgba(255,186,136,0.96)";
  ctx.lineWidth = Math.max(2, edgeRadius * 0.45);
  ctx.strokeRect(box.x + 8, box.y + 8, box.w - 16, box.h - 16);

  ctx.strokeStyle = "rgba(255,255,255,0.24)";
  ctx.lineWidth = Math.max(1, blur * 0.12);
  ctx.setLineDash([8, 6]);
  ctx.strokeRect(box.x + 20, box.y + 20, box.w - 40, box.h - 40);
  ctx.setLineDash([]);

  drawLabel(ctx, "edge band", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.82)", 10);
}

function drawNormalPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(120,196,255,0.30)");
  const strength = getNumber(node, "strength", config.defaults.strength);
  const blur = getNumber(node, "blur_radius", config.defaults.blur_radius);
  const convention = String(getValue(node, "convention", config.defaults.convention));
  const invertX = getBoolean(node, "invert_x", config.defaults.invert_x);
  const invertHeight = getBoolean(node, "invert_height", config.defaults.invert_height);

  const cx = frame.x + (frame.w * 0.34);
  const cy = frame.y + (frame.h * 0.56);
  const r = Math.min(frame.w, frame.h) * 0.28;
  const sphere = ctx.createRadialGradient(cx - (r * 0.35), cy - (r * 0.45), 4, cx, cy, r);
  sphere.addColorStop(0, "rgba(210,228,255,0.96)");
  sphere.addColorStop(0.55, "rgba(116,168,255,0.94)");
  sphere.addColorStop(1, "rgba(46,74,132,0.98)");
  ctx.fillStyle = sphere;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();

  const rampX = frame.x + (frame.w * 0.58);
  const rampW = frame.w * 0.28;
  const ramp = ctx.createLinearGradient(rampX, frame.y + 32, rampX, frame.y + frame.h - 32);
  ramp.addColorStop(0, invertHeight ? "rgba(24,28,36,1)" : "rgba(234,238,245,1)");
  ramp.addColorStop(1, invertHeight ? "rgba(234,238,245,1)" : "rgba(24,28,36,1)");
  ctx.fillStyle = ramp;
  ctx.fillRect(rampX, frame.y + 32, rampW, frame.h - 64);

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.strokeRect(rampX + 0.5, frame.y + 32.5, rampW - 1, frame.h - 65);

  const arrowDx = (invertX ? -1 : 1) * clamp(strength / 12, 0.24, 0.9) * r;
  const arrowDy = (convention === "directx" ? 1 : -1) * clamp(strength / 12, 0.24, 0.9) * r * 0.65;
  ctx.strokeStyle = "rgba(255,255,255,0.92)";
  ctx.lineWidth = 2.4;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + arrowDx, cy + arrowDy);
  ctx.stroke();

  drawLabel(ctx, convention, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.82)", 10);
  drawLabel(ctx, `${formatNumber(blur, 1)} px blur`, frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.62)", 10, "right");
}

function drawEmissivePreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,121,191,0.30)");
  const threshold = getNumber(node, "threshold", config.defaults.threshold);
  const softness = getNumber(node, "softness", config.defaults.softness);
  const satGate = getNumber(node, "saturation_gate", config.defaults.saturation_gate);
  const intensity = getNumber(node, "intensity", config.defaults.intensity);

  ctx.fillStyle = "rgba(14,15,19,0.98)";
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const hotspots = [
    [frame.x + (frame.w * 0.28), frame.y + (frame.h * 0.38), 0.24],
    [frame.x + (frame.w * 0.63), frame.y + (frame.h * 0.56), 0.20],
    [frame.x + (frame.w * 0.74), frame.y + (frame.h * 0.24), 0.14],
  ];
  for (const [cx, cy, t] of hotspots) {
    const glow = ctx.createRadialGradient(cx, cy, 2, cx, cy, frame.w * (0.12 + (intensity * 0.03) + t));
    glow.addColorStop(0, `rgba(255,255,255,${0.44 + (intensity * 0.08)})`);
    glow.addColorStop(0.18, `rgba(255,182,105,${0.36 + ((1 - satGate) * 0.24)})`);
    glow.addColorStop(0.45, `rgba(255,92,190,${0.18 + (softness * 0.38)})`);
    glow.addColorStop(1, "rgba(255,92,190,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(frame.x, frame.y, frame.w, frame.h);
  }

  drawScalarResponseCurve(ctx, frame, "rgba(255,133,206,0.96)", (t) => clamp((t - threshold + softness) / Math.max(0.02, 1 - threshold + softness), 0, 1));
  drawLabel(ctx, "emissive gate", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.82)", 10);
  drawLabel(ctx, `intensity ${formatNumber(intensity, 2)}`, frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.64)", 10, "right");
}

const NODE_CONFIGS = {
  x1RoughnessMap: {
    panelName: "mkrX1RoughnessMapStudio",
    size: [790, 860],
    accent: "#90d0ff",
    title: "Roughness Studio",
    subtitle: "Build matte-versus-gloss structure from image cues with clearer source analysis and response shaping.",
    defaults: {
      source_mode: "combined_roughness",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      detail_radius: 2.0,
      detail_strength: 0.45,
      gamma: 1.0,
      contrast: 1.1,
      blur_radius: 0.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      detail_radius: { min: 0.1, max: 64.0 },
      detail_strength: { min: 0.0, max: 2.0 },
      gamma: { min: 0.1, max: 4.0 },
      contrast: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "detail_radius", "detail_strength", "gamma", "contrast", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_roughness")) },
      { label: "Gamma", get: (node) => formatNumber(getNumber(node, "gamma", 1), 2) },
      { label: "Contrast", get: (node) => formatNumber(getNumber(node, "contrast", 1.1), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { source_mode: "combined_roughness", normalize_mode: "auto_percentile", detail_radius: 2.0, detail_strength: 0.45, gamma: 1.0, contrast: 1.1, blur_radius: 0.0, invert_values: false } },
      { label: "Gloss Paint", values: { source_mode: "value", normalize_mode: "auto_percentile", detail_radius: 1.0, detail_strength: 0.12, gamma: 0.78, contrast: 1.24, blur_radius: 0.0, invert_values: true } },
      { label: "Dry Stone", values: { source_mode: "detail", normalize_mode: "auto_percentile", detail_radius: 3.8, detail_strength: 0.82, gamma: 1.18, contrast: 1.36, blur_radius: 0.6, invert_values: false } },
    ],
    graph: {
      title: "Surface Response",
      note: "matte versus gloss",
      height: 238,
      help: "The sketch shows how the current curve pushes the map toward gloss or roughness before you even pipe it into a shader.",
      readouts: [
        { label: "Detail Radius", get: (node) => `${formatNumber(getNumber(node, "detail_radius", 2), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawRoughnessPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Roughness", value: "combined_roughness" }, { label: "Luma", value: "luma" }, { label: "Value", value: "value" }, { label: "Saturation", value: "saturation" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "detail_radius", label: "Detail Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
          { key: "detail_strength", label: "Detail Strength", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Normalize",
        note: "range shaping",
        controls: [
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Output",
        note: "final map",
        controls: [
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Swap matte and gloss interpretation after normalization." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1SpecularMap: {
    panelName: "mkrX1SpecularMapStudio",
    size: [790, 880],
    accent: "#ffdd83",
    title: "Specular Studio",
    subtitle: "Shape highlight response from value, luma, or combined heuristics without manually juggling every primitive control.",
    defaults: {
      source_mode: "combined_specular",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      detail_radius: 2.0,
      detail_strength: 0.35,
      saturation_suppress: 0.75,
      gamma: 0.75,
      contrast: 1.25,
      blur_radius: 0.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      detail_radius: { min: 0.1, max: 64.0 },
      detail_strength: { min: 0.0, max: 2.0 },
      saturation_suppress: { min: 0.0, max: 1.0 },
      gamma: { min: 0.1, max: 4.0 },
      contrast: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "detail_radius", "detail_strength", "saturation_suppress", "gamma", "contrast", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_specular")) },
      { label: "Sat Suppress", get: (node) => formatNumber(getNumber(node, "saturation_suppress", 0.75), 2) },
      { label: "Gamma", get: (node) => formatNumber(getNumber(node, "gamma", 0.75), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { source_mode: "combined_specular", normalize_mode: "auto_percentile", detail_radius: 2.0, detail_strength: 0.35, saturation_suppress: 0.75, gamma: 0.75, contrast: 1.25, blur_radius: 0.0, invert_values: false } },
      { label: "Wet", values: { source_mode: "value", normalize_mode: "auto_percentile", detail_radius: 1.4, detail_strength: 0.20, saturation_suppress: 0.92, gamma: 0.58, contrast: 1.52, blur_radius: 0.0, invert_values: false } },
      { label: "Dusty", values: { source_mode: "detail", normalize_mode: "auto_percentile", detail_radius: 3.0, detail_strength: 0.62, saturation_suppress: 0.40, gamma: 1.12, contrast: 1.14, blur_radius: 0.8, invert_values: true } },
    ],
    graph: {
      title: "Highlight Response",
      note: "specular gate",
      height: 242,
      help: "This preview leans into hotspot response and color suppression so the specular read is easier to judge without a live shader.",
      readouts: [
        { label: "Detail Radius", get: (node) => `${formatNumber(getNumber(node, "detail_radius", 2), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawSpecularPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Specular", value: "combined_specular" }, { label: "Value", value: "value" }, { label: "Luma", value: "luma" }, { label: "Saturation", value: "saturation" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "detail_radius", label: "Detail Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
          { key: "detail_strength", label: "Detail Strength", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
          { key: "saturation_suppress", label: "Sat Suppress", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Normalize",
        note: "range shaping",
        controls: [
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Output",
        note: "final map",
        controls: [
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final specular map after shaping." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1MetalnessMap: {
    panelName: "mkrX1MetalnessMapStudio",
    size: [790, 860],
    accent: "#77ffd6",
    title: "Metalness Studio",
    subtitle: "Separate dielectric and metallic intent from broad image cues with a clearer surface-response preview.",
    defaults: {
      source_mode: "combined_metalness",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      detail_radius: 2.0,
      detail_strength: 0.25,
      gamma: 1.0,
      contrast: 1.15,
      blur_radius: 0.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      detail_radius: { min: 0.1, max: 64.0 },
      detail_strength: { min: 0.0, max: 2.0 },
      gamma: { min: 0.1, max: 4.0 },
      contrast: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "detail_radius", "detail_strength", "gamma", "contrast", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_metalness")) },
      { label: "Detail", get: (node) => formatNumber(getNumber(node, "detail_strength", 0.25), 2) },
      { label: "Contrast", get: (node) => formatNumber(getNumber(node, "contrast", 1.15), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { source_mode: "combined_metalness", normalize_mode: "auto_percentile", detail_radius: 2.0, detail_strength: 0.25, gamma: 1.0, contrast: 1.15, blur_radius: 0.0, invert_values: false } },
      { label: "Hard Surface", values: { source_mode: "value", normalize_mode: "auto_percentile", detail_radius: 1.4, detail_strength: 0.18, gamma: 0.92, contrast: 1.28, blur_radius: 0.0, invert_values: false } },
      { label: "Stylized", values: { source_mode: "combined_metalness", normalize_mode: "manual_range", value_min: 0.18, value_max: 0.84, detail_radius: 2.8, detail_strength: 0.46, gamma: 1.08, contrast: 1.42, blur_radius: 0.4, invert_values: false } },
    ],
    graph: {
      title: "Surface Split",
      note: "dielectric versus metal",
      height: 238,
      help: "This sketch emphasizes the transition between painted or dielectric areas and metallic response so threshold tuning feels less blind.",
      readouts: [
        { label: "Detail Radius", get: (node) => `${formatNumber(getNumber(node, "detail_radius", 2), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawMetalnessPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Metalness", value: "combined_metalness" }, { label: "Value", value: "value" }, { label: "Luma", value: "luma" }, { label: "Saturation", value: "saturation" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "detail_radius", label: "Detail Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
          { key: "detail_strength", label: "Detail Strength", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Normalize",
        note: "range shaping",
        controls: [
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Output",
        note: "final map",
        controls: [
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final metalness field after shaping." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1CavityMap: {
    panelName: "mkrX1CavityMapStudio",
    size: [790, 840],
    accent: "#c1a2ff",
    title: "Cavity Studio",
    subtitle: "Isolate concave, convex, or balanced cavity detail with a clearer local-contrast preview.",
    defaults: {
      source_mode: "luma",
      polarity: "concave",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      radius: 2.5,
      gamma: 1.0,
      contrast: 1.35,
      blur_radius: 0.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      radius: { min: 0.1, max: 64.0 },
      gamma: { min: 0.1, max: 4.0 },
      contrast: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "polarity", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "radius", "gamma", "contrast", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Polarity", get: (node) => String(getValue(node, "polarity", "concave")) },
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "radius", 2.5), 1)} px` },
      { label: "Contrast", get: (node) => formatNumber(getNumber(node, "contrast", 1.35), 2) },
    ],
    presets: [
      { label: "Concave", tone: "accent", values: { source_mode: "luma", polarity: "concave", normalize_mode: "auto_percentile", radius: 2.5, gamma: 1.0, contrast: 1.35, blur_radius: 0.0, invert_values: false } },
      { label: "Convex", values: { source_mode: "luma", polarity: "convex", normalize_mode: "auto_percentile", radius: 3.2, gamma: 1.0, contrast: 1.26, blur_radius: 0.0, invert_values: false } },
      { label: "Both", values: { source_mode: "value", polarity: "both", normalize_mode: "manual_range", value_min: 0.10, value_max: 0.92, radius: 2.0, gamma: 0.92, contrast: 1.52, blur_radius: 0.4, invert_values: false } },
    ],
    graph: {
      title: "Local Contrast",
      note: "cavity extraction",
      height: 230,
      help: "The preview exaggerates valleys, peaks, or both so you can judge the cavity intent before baking it into a material workflow.",
      readouts: [
        { label: "Blur Radius", get: (node) => `${formatNumber(getNumber(node, "blur_radius", 0), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawCavityPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Luma", value: "luma" }, { label: "Red", value: "red" }, { label: "Green", value: "green" }, { label: "Blue", value: "blue" }, { label: "Max RGB", value: "max_rgb" }, { label: "Value", value: "value" }, { label: "Alpha", value: "alpha" }, { label: "Mask", value: "mask" }] },
          { key: "polarity", type: "select", label: "Polarity", options: [{ label: "Concave", value: "concave" }, { label: "Convex", value: "convex" }, { label: "Both", value: "both" }] },
          { key: "radius", label: "Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Normalize",
        note: "range shaping",
        controls: [
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Output",
        note: "final map",
        controls: [
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final cavity field after shaping." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1EdgeWearMask: {
    panelName: "mkrX1EdgeWearMaskStudio",
    size: [790, 880],
    accent: "#ffab7a",
    title: "Edge Wear Studio",
    subtitle: "Build chipped-edge masks with clearer edge-band previews instead of juggling a flat stack of primitive sliders.",
    defaults: {
      source_mode: "combined_edge_wear",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      edge_radius: 5.0,
      detail_radius: 2.0,
      detail_strength: 0.50,
      gamma: 1.0,
      contrast: 1.25,
      blur_radius: 0.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      edge_radius: { min: 0.1, max: 128.0 },
      detail_radius: { min: 0.1, max: 64.0 },
      detail_strength: { min: 0.0, max: 2.0 },
      gamma: { min: 0.1, max: 4.0 },
      contrast: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "edge_radius", "detail_radius", "detail_strength", "gamma", "contrast", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_edge_wear")) },
      { label: "Edge Radius", get: (node) => `${formatNumber(getNumber(node, "edge_radius", 5), 1)} px` },
      { label: "Detail", get: (node) => formatNumber(getNumber(node, "detail_strength", 0.5), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { source_mode: "combined_edge_wear", normalize_mode: "auto_percentile", edge_radius: 5.0, detail_radius: 2.0, detail_strength: 0.50, gamma: 1.0, contrast: 1.25, blur_radius: 0.0, invert_values: false } },
      { label: "Chipped Paint", values: { source_mode: "inverse_luma", normalize_mode: "auto_percentile", edge_radius: 7.0, detail_radius: 2.6, detail_strength: 0.72, gamma: 0.92, contrast: 1.48, blur_radius: 0.4, invert_values: false } },
      { label: "Soft Rub", values: { source_mode: "detail", normalize_mode: "manual_range", value_min: 0.12, value_max: 0.90, edge_radius: 3.8, detail_radius: 1.6, detail_strength: 0.34, gamma: 1.10, contrast: 1.08, blur_radius: 0.8, invert_values: false } },
    ],
    graph: {
      title: "Wear Preview",
      note: "edge band",
      height: 236,
      help: "The graphic exaggerates edge thickness and inner cleanup so you can feel whether the wear mask is too harsh or too soft before export.",
      readouts: [
        { label: "Detail Radius", get: (node) => `${formatNumber(getNumber(node, "detail_radius", 2), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawEdgeWearPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Edge Wear", value: "combined_edge_wear" }, { label: "Luma", value: "luma" }, { label: "Inverse Luma", value: "inverse_luma" }, { label: "Value", value: "value" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "edge_radius", label: "Edge Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
          { key: "detail_radius", label: "Detail Radius", min: 0.1, max: 32.0, step: 0.1, decimals: 1 },
          { key: "detail_strength", label: "Detail Strength", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Normalize",
        note: "range shaping",
        controls: [
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Output",
        note: "final mask",
        controls: [
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final wear mask after shaping." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1NormalMap: {
    panelName: "mkrX1NormalMapStudio",
    size: [820, 860],
    accent: "#78c4ff",
    title: "Normal Map Studio",
    subtitle: "Turn grayscale height cues into tangent-space normals with a clearer build preview and less guesswork.",
    defaults: {
      source_mode: "luma",
      normalize_mode: "auto_percentile",
      value_min: 0.0,
      value_max: 1.0,
      percentile_low: 2.0,
      percentile_high: 98.0,
      gamma: 1.0,
      blur_radius: 0.0,
      strength: 4.0,
      convention: "opengl",
      invert_height: false,
      invert_x: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      value_min: { min: 0.0, max: 1.0 },
      value_max: { min: 0.0, max: 1.0 },
      percentile_low: { min: 0.0, max: 100.0 },
      percentile_high: { min: 0.0, max: 100.0 },
      gamma: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      strength: { min: 0.0, max: 64.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_height", "invert_x", "invert_mask"],
    legacyNames: ["source_mode", "normalize_mode", "value_min", "value_max", "percentile_low", "percentile_high", "gamma", "blur_radius", "strength", "convention", "invert_height", "invert_x", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "luma")) },
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "strength", 4), 2) },
      { label: "Convention", get: (node) => String(getValue(node, "convention", "opengl")) },
    ],
    presets: [
      { label: "OpenGL", tone: "accent", values: { source_mode: "luma", normalize_mode: "auto_percentile", gamma: 1.0, blur_radius: 0.0, strength: 4.0, convention: "opengl", invert_height: false, invert_x: false } },
      { label: "DirectX", values: { source_mode: "luma", normalize_mode: "auto_percentile", gamma: 1.0, blur_radius: 0.0, strength: 4.0, convention: "directx", invert_height: false, invert_x: false } },
      { label: "Soft Relief", values: { source_mode: "value", normalize_mode: "manual_range", value_min: 0.08, value_max: 0.92, gamma: 1.08, blur_radius: 1.2, strength: 2.4, convention: "opengl", invert_height: false, invert_x: false } },
    ],
    graph: {
      title: "Normal Build",
      note: "height to tangent",
      height: 246,
      help: "The sphere-and-ramp preview helps you judge strength, blur, and tangent convention without needing a separate viewer node for every tweak.",
      readouts: [
        { label: "Invert Height", get: (node) => getBoolean(node, "invert_height", false) ? "On" : "Off" },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawNormalPreview,
    },
    sections: [
      {
        title: "Height Source",
        note: "grayscale analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Luma", value: "luma" }, { label: "Red", value: "red" }, { label: "Green", value: "green" }, { label: "Blue", value: "blue" }, { label: "Max RGB", value: "max_rgb" }, { label: "Saturation", value: "saturation" }, { label: "Value", value: "value" }, { label: "Alpha", value: "alpha" }, { label: "Mask", value: "mask" }] },
          { key: "normalize_mode", type: "select", label: "Normalize", options: [{ label: "Auto Percentile", value: "auto_percentile" }, { label: "Manual Range", value: "manual_range" }, { label: "Auto Range", value: "auto_range" }] },
          { key: "value_min", label: "Value Min", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "value_max", label: "Value Max", min: 0.0, max: 1.0, step: 0.001, decimals: 3 },
          { key: "percentile_low", label: "Percentile Low", min: 0.0, max: 20.0, step: 0.1, decimals: 1 },
          { key: "percentile_high", label: "Percentile High", min: 80.0, max: 100.0, step: 0.1, decimals: 1 },
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Normal Solve",
        note: "tangent build",
        controls: [
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "strength", label: "Strength", min: 0.0, max: 24.0, step: 0.1, decimals: 1 },
          { key: "convention", type: "select", label: "Convention", options: [{ label: "OpenGL", value: "opengl" }, { label: "DirectX", value: "directx" }] },
          { key: "invert_height", type: "toggle", label: "Invert Height", description: "Flip the source height before building the normal." },
          { key: "invert_x", type: "toggle", label: "Invert X", description: "Mirror the X component after solving the normal." },
        ],
      },
      {
        title: "Mask",
        note: "optional effect mask",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1EmissiveMap: {
    panelName: "mkrX1EmissiveMapStudio",
    size: [780, 760],
    accent: "#ff79bf",
    title: "Emissive Studio",
    subtitle: "Gate bright or saturated regions into glow-ready emissive maps with a clearer hotspot preview.",
    defaults: {
      source_mode: "combined_emissive",
      threshold: 0.6,
      softness: 0.1,
      saturation_gate: 0.35,
      intensity: 1.5,
      blur_radius: 0.0,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      threshold: { min: 0.0, max: 1.0 },
      softness: { min: 0.0, max: 0.5 },
      saturation_gate: { min: 0.0, max: 1.0 },
      intensity: { min: 0.0, max: 8.0 },
      blur_radius: { min: 0.0, max: 64.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["source_mode", "threshold", "softness", "saturation_gate", "intensity", "blur_radius", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_emissive")) },
      { label: "Threshold", get: (node) => formatNumber(getNumber(node, "threshold", 0.6), 2) },
      { label: "Intensity", get: (node) => formatNumber(getNumber(node, "intensity", 1.5), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { source_mode: "combined_emissive", threshold: 0.6, softness: 0.1, saturation_gate: 0.35, intensity: 1.5, blur_radius: 0.0, mask_feather: 8.0, invert_mask: false } },
      { label: "Neon", values: { source_mode: "saturated_color", threshold: 0.42, softness: 0.12, saturation_gate: 0.58, intensity: 2.6, blur_radius: 2.0, mask_feather: 10.0, invert_mask: false } },
      { label: "Hotspots", values: { source_mode: "white_hotspots", threshold: 0.74, softness: 0.08, saturation_gate: 0.12, intensity: 3.2, blur_radius: 1.2, mask_feather: 6.0, invert_mask: false } },
    ],
    graph: {
      title: "Glow Gate",
      note: "hotspot response",
      height: 228,
      help: "The preview leans into threshold, softness, and intensity so it’s easier to judge whether the emissive pass will feel subtle, neon, or blown out.",
      readouts: [
        { label: "Softness", get: (node) => formatNumber(getNumber(node, "softness", 0.1), 2) },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawEmissivePreview,
    },
    sections: [
      {
        title: "Gate",
        note: "source isolation",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Emissive", value: "combined_emissive" }, { label: "Bright Color", value: "bright_color" }, { label: "Saturated Color", value: "saturated_color" }, { label: "Mask Color", value: "mask_color" }, { label: "White Hotspots", value: "white_hotspots" }] },
          { key: "threshold", label: "Threshold", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "softness", label: "Softness", min: 0.0, max: 0.5, step: 0.01, decimals: 2 },
          { key: "saturation_gate", label: "Saturation Gate", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Glow",
        note: "energy",
        controls: [
          { key: "intensity", label: "Intensity", min: 0.0, max: 8.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
        ],
      },
      {
        title: "Mask",
        note: "optional effect mask",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

function readControlValue(node, spec) {
  if (spec.type === "toggle") return getBoolean(node, spec.key, !!spec.default);
  if (spec.type === "select") return getValue(node, spec.key, spec.default);
  return getNumber(node, spec.key, Number(spec.default || 0));
}

function createControl(node, spec, refresh) {
  if (spec.type === "toggle") {
    const control = createGradeToggle({
      label: spec.label,
      checked: getBoolean(node, spec.key, !!spec.default),
      description: spec.description || "",
      onChange: (value) => {
        setWidgetValue(node, spec.key, value);
        refresh();
      },
    });
    return { key: spec.key, ...control };
  }

  if (spec.type === "select") {
    const control = createSelectControl({
      label: spec.label,
      value: String(getValue(node, spec.key, spec.options?.[0]?.value ?? "")),
      options: spec.options || [],
      onChange: (value) => {
        setWidgetValue(node, spec.key, value);
        refresh();
      },
    });
    return { key: spec.key, ...control };
  }

  const control = createGradeSlider({
    label: spec.label,
    min: spec.min,
    max: spec.max,
    step: spec.step,
    value: getNumber(node, spec.key, spec.default ?? spec.min),
    decimals: spec.decimals ?? 2,
    onChange: (value) => {
      setWidgetValue(node, spec.key, value);
      refresh();
    },
  });
  return { key: spec.key, ...control };
}

function buildPanel(node, config) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT SURFACE",
    title: config.title,
    subtitle: config.subtitle,
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", config.accent);
  panel.style.paddingBottom = "18px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";

  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const metricViews = (config.metrics || []).map((metric) => {
    const view = createGradeMetric(metric.label, metric.get(node));
    metricsWrap.appendChild(view.element);
    return { ...metric, view };
  });

  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  for (const preset of config.presets || []) {
    actions.appendChild(createGradeButton(preset.label, () => {
      applyValues(node, preset.values);
      refresh();
    }, preset.tone || ""));
  }

  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const graphSection = createGradeSection(config.graph.title, config.graph.note || "");
  const canvas = document.createElement("canvas");
  canvas.className = "mkr-grade-canvas";
  canvas.style.height = `${config.graph.height || 224}px`;
  graphSection.body.appendChild(canvas);

  const readoutWrap = document.createElement("div");
  readoutWrap.className = "mkr-grade-inline";
  const readoutViews = (config.graph.readouts || []).map((readout) => {
    const view = createGradeReadout(readout.label, readout.get(node));
    readoutWrap.appendChild(view.element);
    return { ...readout, view };
  });
  if (readoutViews.length) graphSection.body.appendChild(readoutWrap);

  if (config.graph.help) {
    const help = document.createElement("div");
    help.className = "mkr-grade-note";
    help.textContent = config.graph.help;
    graphSection.body.appendChild(help);
  }
  panel.appendChild(graphSection.section);

  const controlViews = [];
  for (const sectionSpec of config.sections || []) {
    const section = createGradeSection(sectionSpec.title, sectionSpec.note || "");
    const grid = document.createElement("div");
    grid.className = "mkr-grade-controls";
    for (const controlSpec of sectionSpec.controls || []) {
      const spec = { ...controlSpec };
      if (spec.default === undefined) spec.default = config.defaults[spec.key];
      const control = createControl(node, spec, refresh);
      grid.appendChild(control.element);
      controlViews.push({ spec, control });
    }
    section.body.appendChild(grid);
    panel.appendChild(section.section);
  }

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => drawCanvas());
    observer.observe(canvas);
  }

  function drawCanvas() {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    config.graph.draw(ctx, width, height, node, config);
  }

  function refresh() {
    metricViews.forEach((metric) => metric.view.setValue(metric.get(node)));
    readoutViews.forEach((readout) => readout.view.setValue(readout.get(node)));
    controlViews.forEach(({ spec, control }) => control.setValue(readControlValue(node, spec)));
    drawCanvas();
  }

  refresh();
  return { panel, refresh };
}

function prepareNode(node) {
  const nodeName = String(node?.comfyClass || node?.type || "");
  const config = NODE_CONFIGS[nodeName];
  if (!config) return;

  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: config.defaults,
    numericSpecs: config.numericSpecs,
    booleanKeys: config.booleanKeys,
    legacyNames: config.legacyNames,
  });

  if (node.__mkrMaterialSurfacePanelInstalled) {
    node.__mkrMaterialSurfaceRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrMaterialSurfacePanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrMaterialSurfaceRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrMaterialSurfaceRefreshHooksInstalled", refresh);
  requestAnimationFrame(() => refresh());
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const nodeName = String(nodeData?.name || nodeData?.type || "");
    if (!TARGET_NAMES.has(nodeName)) return;
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
      const name = String(node?.comfyClass || node?.type || "");
      if (TARGET_NAMES.has(name)) {
        prepareNode(node);
      }
    }
  },
});
