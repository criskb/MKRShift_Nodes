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

const EXTENSION_NAME = "MKRShift.VFXConceptStudios";
const DEPTH_NODE = "x1Depth";
const DEPTH_NODE_ALIASES = new Set([
  DEPTH_NODE,
  "Depth FX",
  "Depth FX • MKRShift Nodes",
]);
const DEPTH_PANEL = "mkr_depth_fx_studio";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-vfx-concept-studios-v1";
const PANEL_WIDTH = 780;
const PANEL_HEIGHT = 860;

const DEPTH_LEGACY_WIDGETS = [
  "depth_mode",
  "focal_depth",
  "depth_range",
  "near_blur",
  "far_blur",
  "depth_contrast",
  "haze_strength",
  "haze_r",
  "haze_g",
  "haze_b",
  "mask_feather",
  "invert_mask",
];
const DEPTH_HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...DEPTH_LEGACY_WIDGETS];

const DEPTH_DEFAULT_SETTINGS = {
  depth_mode: "luma",
  focal_depth: 0.5,
  depth_range: 0.25,
  near_blur: 10.0,
  far_blur: 18.0,
  depth_contrast: 1.0,
  haze_strength: 0.15,
  haze_r: 0.74,
  haze_g: 0.82,
  haze_b: 0.92,
  mask_feather: 12.0,
  invert_mask: false,
};

const DEPTH_NUMERIC_SPECS = {
  focal_depth: { min: 0.0, max: 1.0 },
  depth_range: { min: 0.02, max: 1.0 },
  near_blur: { min: 0.0, max: 64.0 },
  far_blur: { min: 0.0, max: 64.0 },
  depth_contrast: { min: 0.2, max: 3.0 },
  haze_strength: { min: 0.0, max: 1.0 },
  haze_r: { min: 0.0, max: 1.0 },
  haze_g: { min: 0.0, max: 1.0 },
  haze_b: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const DEPTH_BOOLEAN_KEYS = ["invert_mask"];

const DEPTH_PRESETS = {
  portrait: {
    depth_mode: "luma",
    focal_depth: 0.42,
    depth_range: 0.18,
    near_blur: 8.0,
    far_blur: 24.0,
    depth_contrast: 1.22,
    haze_strength: 0.08,
    haze_r: 0.74,
    haze_g: 0.82,
    haze_b: 0.92,
  },
  macro: {
    depth_mode: "radial",
    focal_depth: 0.34,
    depth_range: 0.12,
    near_blur: 18.0,
    far_blur: 22.0,
    depth_contrast: 1.36,
    haze_strength: 0.0,
    haze_r: 0.74,
    haze_g: 0.82,
    haze_b: 0.92,
  },
  haze: {
    depth_mode: "luma",
    focal_depth: 0.58,
    depth_range: 0.26,
    near_blur: 4.0,
    far_blur: 28.0,
    depth_contrast: 0.94,
    haze_strength: 0.32,
    haze_r: 0.76,
    haze_g: 0.84,
    haze_b: 0.96,
  },
  custom: {
    depth_mode: "custom_map",
    focal_depth: 0.48,
    depth_range: 0.22,
    near_blur: 10.0,
    far_blur: 18.0,
    depth_contrast: 1.0,
    haze_strength: 0.12,
    haze_r: 0.74,
    haze_g: 0.82,
    haze_b: 0.92,
  },
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
    .mkr-depth-select {
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

    .mkr-depth-preview {
      display: block;
      width: 100%;
      height: 258px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(16,18,22,0.96), rgba(28,31,36,0.96));
      box-sizing: border-box;
    }

    .mkr-depth-note {
      margin-top: 6px;
      font-size: 11px;
      line-height: 1.35;
      color: rgba(225,231,238,0.52);
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
  select.className = "mkr-depth-select";
  for (const option of options) {
    const item = document.createElement("option");
    item.value = String(option.value);
    item.textContent = option.label;
    select.appendChild(item);
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

function installDepthAdapter(node) {
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: DEPTH_DEFAULT_SETTINGS,
    numericSpecs: DEPTH_NUMERIC_SPECS,
    booleanKeys: DEPTH_BOOLEAN_KEYS,
    legacyNames: DEPTH_LEGACY_WIDGETS,
  });
}

function isDepthNode(node) {
  if (node?.__mkrDepthEligible) return true;
  const names = [
    node?.comfyClass,
    node?.constructor?.comfyClass,
    node?.type,
    node?.title,
  ];
  return names.some((name) => {
    const text = String(name || "");
    const lower = text.toLowerCase();
    return DEPTH_NODE_ALIASES.has(text) || lower === "x1depth" || lower.includes("depth fx");
  }) || hasDepthSignature(node);
}

function hasNamedPort(entries, target) {
  return Array.isArray(entries) && entries.some((entry) => String(entry?.name || "") === String(target));
}

function hasDepthSignature(node) {
  if (!node) return false;
  const hasSettings = Array.isArray(node.widgets)
    && node.widgets.some((widget) => String(widget?.name || "") === SETTINGS_WIDGET_NAME);
  const hasDepthMapInput = hasNamedPort(node.inputs, "depth_map");
  const hasDepthInfoOutput = hasNamedPort(node.outputs, "depth_info");
  return hasSettings && (hasDepthMapInput || hasDepthInfoOutput);
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

function hasInputLink(node, name) {
  const input = Array.isArray(node?.inputs)
    ? node.inputs.find((item) => String(item?.name || "") === String(name))
    : null;
  if (!input) return false;
  return Boolean(input.link || (Array.isArray(input.links) && input.links.length));
}

function blurForDepth(depth, focus, range, nearBlur, farBlur) {
  const safeRange = Math.max(0.02, range);
  const nearWeight = clamp((focus - depth) / safeRange, 0, 1);
  const farWeight = clamp((depth - focus) / safeRange, 0, 1);
  return (nearBlur * nearWeight * 0.12) + (farBlur * farWeight * 0.12);
}

function drawRoundedRect(ctx, x, y, w, h, radius) {
  const r = Math.min(radius, w * 0.5, h * 0.5);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawFallbackPreview(ctx, width, height, title = "Depth Preview") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(14,17,22,0.98)");
  bg.addColorStop(1, "rgba(28,32,39,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);
  ctx.strokeStyle = "rgba(107,212,255,0.18)";
  ctx.strokeRect(frame.x, frame.y, frame.w, frame.h);
  ctx.fillStyle = "rgba(238,242,246,0.90)";
  ctx.font = "600 13px sans-serif";
  ctx.fillText(title, frame.x + 18, frame.y + 34);
  ctx.fillStyle = "rgba(225,231,238,0.56)";
  ctx.font = "11px sans-serif";
  ctx.fillText("Depth preview active. Controls remain available.", frame.x + 18, frame.y + 58);
}

function drawModeInset(ctx, rect, settings, customDepthLinked) {
  const mode = String(settings.depth_mode || "luma");
  ctx.save();
  drawRoundedRect(ctx, rect.x, rect.y, rect.w, rect.h, 10);
  ctx.clip();

  if (mode === "radial") {
    const radial = ctx.createRadialGradient(
      rect.x + (rect.w * 0.5),
      rect.y + (rect.h * 0.5),
      4,
      rect.x + (rect.w * 0.5),
      rect.y + (rect.h * 0.5),
      rect.w * 0.65,
    );
    radial.addColorStop(0, "rgba(250,250,252,0.94)");
    radial.addColorStop(0.45, "rgba(154,169,184,0.82)");
    radial.addColorStop(1, "rgba(29,34,42,0.96)");
    ctx.fillStyle = radial;
  } else {
    const grad = ctx.createLinearGradient(rect.x, rect.y, rect.x + rect.w, rect.y);
    const invert = mode === "inverted_luma";
    grad.addColorStop(0, invert ? "rgba(236,240,244,0.96)" : "rgba(25,29,36,0.96)");
    grad.addColorStop(1, invert ? "rgba(26,30,37,0.96)" : "rgba(238,242,246,0.96)");
    ctx.fillStyle = grad;
  }
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h);

  if (mode === "custom_map") {
    ctx.fillStyle = "rgba(255,255,255,0.10)";
    for (let band = 0; band < 7; band += 1) {
      const width = rect.w * (0.18 + ((band % 3) * 0.14));
      const x = rect.x + ((rect.w - width) * (band / 6));
      ctx.fillRect(x, rect.y, width, rect.h);
    }
  }

  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const x = rect.x + ((rect.w * step) / 4);
    const y = rect.y + ((rect.h * step) / 4);
    ctx.beginPath();
    ctx.moveTo(x, rect.y);
    ctx.lineTo(x, rect.y + rect.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(rect.x, y);
    ctx.lineTo(rect.x + rect.w, y);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(245,247,249,0.92)";
  ctx.font = "600 11px sans-serif";
  ctx.fillText(mode === "custom_map" ? "Custom Map" : mode === "radial" ? "Radial Map" : "Luma Map", rect.x + 10, rect.y + 16);
  ctx.fillStyle = customDepthLinked ? "rgba(156,245,171,0.92)" : "rgba(255,213,115,0.88)";
  ctx.fillText(customDepthLinked ? "DEPTH IN LIVE" : "DEPTH IN OPEN", rect.x + 10, rect.y + rect.h - 10);
  ctx.restore();
}

function drawSceneLayer(ctx, rect, depth, blurPx, fillStyle, shape) {
  ctx.save();
  ctx.filter = blurPx > 0.35 ? `blur(${blurPx.toFixed(2)}px)` : "none";
  ctx.fillStyle = fillStyle;
  ctx.beginPath();
  shape(rect, depth);
  ctx.fill();
  ctx.restore();
}

function drawDepthPreview(canvas, node) {
  const { ctx, width, height } = ensureCanvasResolution(canvas);
  const settings = {
    depth_mode: String(getValue(node, "depth_mode", "luma")),
    focal_depth: getNumber(node, "focal_depth", 0.5),
    depth_range: getNumber(node, "depth_range", 0.25),
    near_blur: getNumber(node, "near_blur", 10),
    far_blur: getNumber(node, "far_blur", 18),
    depth_contrast: getNumber(node, "depth_contrast", 1),
    haze_strength: getNumber(node, "haze_strength", 0.15),
    haze_r: getNumber(node, "haze_r", 0.74),
    haze_g: getNumber(node, "haze_g", 0.82),
    haze_b: getNumber(node, "haze_b", 0.92),
  };
  const hazeColor = `rgba(${Math.round(clamp(settings.haze_r, 0, 1) * 255)}, ${Math.round(clamp(settings.haze_g, 0, 1) * 255)}, ${Math.round(clamp(settings.haze_b, 0, 1) * 255)}, 1)`;
  const customDepthLinked = hasInputLink(node, "depth_map");

  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(13,16,20,0.98)");
  bg.addColorStop(0.55, "rgba(24,28,35,0.98)");
  bg.addColorStop(1, "rgba(17,20,26,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const scene = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 96, h: frame.h - 36 };
  const gauge = { x: scene.x + scene.w + 18, y: scene.y, w: 34, h: scene.h };
  const inset = { x: scene.x + scene.w - 150, y: scene.y + 12, w: 138, h: 88 };

  const sky = ctx.createLinearGradient(scene.x, scene.y, scene.x, scene.y + scene.h);
  sky.addColorStop(0, "rgba(27,40,58,0.98)");
  sky.addColorStop(0.55, "rgba(42,52,66,0.98)");
  sky.addColorStop(1, "rgba(24,26,31,0.98)");
  ctx.fillStyle = sky;
  ctx.fillRect(scene.x, scene.y, scene.w, scene.h);

  const hazeAlpha = clamp(settings.haze_strength, 0, 1) * 0.55;
  if (hazeAlpha > 0) {
    const mist = ctx.createLinearGradient(scene.x, scene.y + scene.h * 0.25, scene.x, scene.y + scene.h);
    mist.addColorStop(0, hazeColor.replace(", 1)", `, ${hazeAlpha * 0.12})`));
    mist.addColorStop(1, hazeColor.replace(", 1)", `, ${hazeAlpha})`));
    ctx.fillStyle = mist;
    ctx.fillRect(scene.x, scene.y, scene.w, scene.h);
  }

  drawSceneLayer(
    ctx,
    scene,
    0.88,
    blurForDepth(0.88, settings.focal_depth, settings.depth_range, settings.near_blur, settings.far_blur),
    "rgba(86,98,112,0.55)",
    (rect) => {
      ctx.moveTo(rect.x, rect.y + rect.h * 0.64);
      for (let i = 0; i <= 6; i += 1) {
        const t = i / 6;
        const x = rect.x + (rect.w * t);
        const y = rect.y + rect.h * (0.42 + (Math.sin(t * Math.PI * 2.3) * 0.08));
        ctx.lineTo(x, y);
      }
      ctx.lineTo(rect.x + rect.w, rect.y + rect.h);
      ctx.lineTo(rect.x, rect.y + rect.h);
    },
  );

  drawSceneLayer(
    ctx,
    scene,
    0.54,
    blurForDepth(0.54, settings.focal_depth, settings.depth_range, settings.near_blur, settings.far_blur),
    "rgba(123,139,158,0.78)",
    (rect) => {
      ctx.moveTo(rect.x + rect.w * 0.16, rect.y + rect.h * 0.82);
      ctx.lineTo(rect.x + rect.w * 0.30, rect.y + rect.h * 0.48);
      ctx.lineTo(rect.x + rect.w * 0.46, rect.y + rect.h * 0.80);
      ctx.lineTo(rect.x + rect.w * 0.60, rect.y + rect.h * 0.56);
      ctx.lineTo(rect.x + rect.w * 0.74, rect.y + rect.h * 0.82);
      ctx.lineTo(rect.x + rect.w * 0.16, rect.y + rect.h * 0.82);
    },
  );

  drawSceneLayer(
    ctx,
    scene,
    0.22,
    blurForDepth(0.22, settings.focal_depth, settings.depth_range, settings.near_blur, settings.far_blur),
    "rgba(243,194,104,0.92)",
    (rect) => {
      const baseX = rect.x + rect.w * 0.20;
      const baseY = rect.y + rect.h * 0.86;
      ctx.moveTo(baseX, baseY);
      ctx.lineTo(baseX + 18, baseY - 92);
      ctx.lineTo(baseX + 36, baseY - 132);
      ctx.lineTo(baseX + 54, baseY - 76);
      ctx.lineTo(baseX + 74, baseY - 150);
      ctx.lineTo(baseX + 88, baseY);
      ctx.lineTo(baseX, baseY);
    },
  );

  const focusY = scene.y + ((1 - clamp(settings.focal_depth, 0, 1)) * scene.h);
  const focusHeight = clamp(settings.depth_range, 0.02, 1) * scene.h;
  ctx.fillStyle = "rgba(109,212,255,0.08)";
  ctx.fillRect(scene.x, focusY - (focusHeight * 0.5), scene.w, focusHeight);
  ctx.strokeStyle = "rgba(109,212,255,0.72)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(scene.x + 10, focusY);
  ctx.lineTo(scene.x + scene.w - 10, focusY);
  ctx.stroke();

  drawModeInset(ctx, inset, settings, customDepthLinked);

  const gaugeGrad = ctx.createLinearGradient(gauge.x, gauge.y + gauge.h, gauge.x, gauge.y);
  gaugeGrad.addColorStop(0, "rgba(245,246,248,0.10)");
  gaugeGrad.addColorStop(0.5, "rgba(166,177,188,0.38)");
  gaugeGrad.addColorStop(1, "rgba(247,248,250,0.92)");
  ctx.fillStyle = gaugeGrad;
  drawRoundedRect(ctx, gauge.x, gauge.y, gauge.w, gauge.h, 10);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.stroke();

  const gaugeFocusY = gauge.y + ((1 - clamp(settings.focal_depth, 0, 1)) * gauge.h);
  const gaugeBand = clamp(settings.depth_range, 0.02, 1) * gauge.h;
  ctx.fillStyle = "rgba(92,214,255,0.16)";
  ctx.fillRect(gauge.x + 2, gaugeFocusY - (gaugeBand * 0.5), gauge.w - 4, gaugeBand);
  ctx.strokeStyle = "rgba(92,214,255,0.88)";
  ctx.beginPath();
  ctx.moveTo(gauge.x - 6, gaugeFocusY);
  ctx.lineTo(gauge.x + gauge.w + 6, gaugeFocusY);
  ctx.stroke();

  ctx.fillStyle = "rgba(236,241,246,0.86)";
  ctx.font = "600 11px sans-serif";
  ctx.fillText("Near", gauge.x - 6, gauge.y + gauge.h - 10);
  ctx.fillText("Far", gauge.x - 2, gauge.y + 14);
  ctx.fillText("Focus", gauge.x + gauge.w + 10, gaugeFocusY + 4);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  ctx.strokeRect(scene.x, scene.y, scene.w, scene.h);
}

function buildDepthPanel(node) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT VFX",
    title: "Depth FX Studio",
    subtitle: "Stage near, focus, and far response with a visible depth preview instead of juggling raw blur controls.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#6bd4ff");
  panel.style.paddingBottom = "18px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "luma");
  const focusMetric = createGradeMetric("Focus", "0.50");
  const hazeMetric = createGradeMetric("Haze", "0.15");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(focusMetric.element);
  metricsWrap.appendChild(hazeMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Portrait", () => { applyValues(node, DEPTH_PRESETS.portrait); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Macro", () => { applyValues(node, DEPTH_PRESETS.macro); refreshPanel(); }));
  actions.appendChild(createGradeButton("Haze", () => { applyValues(node, DEPTH_PRESETS.haze); refreshPanel(); }));
  actions.appendChild(createGradeButton("Custom", () => { applyValues(node, DEPTH_PRESETS.custom); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Depth Preview", "focus plane / blur split");
  const previewCanvas = document.createElement("canvas");
  previewCanvas.className = "mkr-depth-preview";
  previewSection.body.appendChild(previewCanvas);
  const previewReadouts = document.createElement("div");
  previewReadouts.className = "mkr-grade-inline";
  const rangeReadout = createGradeReadout("Range", "0.25");
  const blurReadout = createGradeReadout("Near/Far", "10 / 18");
  const mapReadout = createGradeReadout("Depth Map", "Open");
  previewReadouts.appendChild(rangeReadout.element);
  previewReadouts.appendChild(blurReadout.element);
  previewReadouts.appendChild(mapReadout.element);
  previewSection.body.appendChild(previewReadouts);
  const previewNote = document.createElement("div");
  previewNote.className = "mkr-depth-note";
  previewNote.textContent = "Use the preview to place the focus plane and see how near and far blur diverge before you render the effect.";
  previewSection.body.appendChild(previewNote);
  panel.appendChild(previewSection.section);

  const depthSection = createGradeSection("Depth Source", "mode + focus");
  const depthControls = document.createElement("div");
  depthControls.className = "mkr-grade-controls";
  const mode = createSelectControl({
    label: "Depth Mode",
    value: String(getValue(node, "depth_mode", "luma")),
    options: [
      { value: "luma", label: "luma" },
      { value: "inverted_luma", label: "inverted_luma" },
      { value: "radial", label: "radial" },
      { value: "custom_map", label: "custom_map" },
    ],
    onChange: (value) => { setWidgetValue(node, "depth_mode", value); refreshPanel(); },
  });
  const focalDepth = createGradeSlider({
    label: "Focal Depth",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "focal_depth", 0.5),
    onChange: (value) => { setWidgetValue(node, "focal_depth", value); refreshPanel(); },
  });
  const depthRange = createGradeSlider({
    label: "Depth Range",
    min: 0.02,
    max: 1,
    step: 0.01,
    value: getNumber(node, "depth_range", 0.25),
    onChange: (value) => { setWidgetValue(node, "depth_range", value); refreshPanel(); },
  });
  const depthContrast = createGradeSlider({
    label: "Depth Contrast",
    min: 0.2,
    max: 3,
    step: 0.01,
    value: getNumber(node, "depth_contrast", 1.0),
    onChange: (value) => { setWidgetValue(node, "depth_contrast", value); refreshPanel(); },
  });
  depthControls.appendChild(mode.element);
  depthControls.appendChild(focalDepth.element);
  depthControls.appendChild(depthRange.element);
  depthControls.appendChild(depthContrast.element);
  depthSection.body.appendChild(depthControls);
  panel.appendChild(depthSection.section);

  const blurSection = createGradeSection("Lens Response", "near / far separation");
  const blurControls = document.createElement("div");
  blurControls.className = "mkr-grade-controls";
  const nearBlur = createGradeSlider({
    label: "Near Blur",
    min: 0,
    max: 64,
    step: 0.5,
    value: getNumber(node, "near_blur", 10),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "near_blur", value); refreshPanel(); },
  });
  const farBlur = createGradeSlider({
    label: "Far Blur",
    min: 0,
    max: 64,
    step: 0.5,
    value: getNumber(node, "far_blur", 18),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "far_blur", value); refreshPanel(); },
  });
  blurControls.appendChild(nearBlur.element);
  blurControls.appendChild(farBlur.element);
  blurSection.body.appendChild(blurControls);
  panel.appendChild(blurSection.section);

  const atmosphereSection = createGradeSection("Atmosphere", "far haze");
  const atmosphereControls = document.createElement("div");
  atmosphereControls.className = "mkr-grade-controls";
  const hazeStrength = createGradeSlider({
    label: "Haze Strength",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "haze_strength", 0.15),
    onChange: (value) => { setWidgetValue(node, "haze_strength", value); refreshPanel(); },
  });
  const hazeR = createGradeSlider({
    label: "Haze R",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "haze_r", 0.74),
    onChange: (value) => { setWidgetValue(node, "haze_r", value); refreshPanel(); },
  });
  const hazeG = createGradeSlider({
    label: "Haze G",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "haze_g", 0.82),
    onChange: (value) => { setWidgetValue(node, "haze_g", value); refreshPanel(); },
  });
  const hazeB = createGradeSlider({
    label: "Haze B",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "haze_b", 0.92),
    onChange: (value) => { setWidgetValue(node, "haze_b", value); refreshPanel(); },
  });
  atmosphereControls.appendChild(hazeStrength.element);
  atmosphereControls.appendChild(hazeR.element);
  atmosphereControls.appendChild(hazeG.element);
  atmosphereControls.appendChild(hazeB.element);
  atmosphereSection.body.appendChild(atmosphereControls);
  panel.appendChild(atmosphereSection.section);

  const maskSection = createGradeSection("Mask Output", "blend gate");
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
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before the depth effect blends in.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => {
      try {
        drawDepthPreview(previewCanvas, node);
      } catch (error) {
        console.error(`[${EXTENSION_NAME}] preview redraw failed`, error);
        const { ctx, width, height } = ensureCanvasResolution(previewCanvas);
        drawFallbackPreview(ctx, width, height);
      }
    });
    observer.observe(previewCanvas);
  }

  function refreshPanel() {
    try {
      const currentMode = String(getValue(node, "depth_mode", "luma"));
      modeMetric.setValue(currentMode);
      focusMetric.setValue(formatNumber(getNumber(node, "focal_depth", 0.5)));
      hazeMetric.setValue(formatNumber(getNumber(node, "haze_strength", 0.15)));
      rangeReadout.setValue(formatNumber(getNumber(node, "depth_range", 0.25)));
      blurReadout.setValue(`${Math.round(getNumber(node, "near_blur", 10))} / ${Math.round(getNumber(node, "far_blur", 18))}`);
      mapReadout.setValue(hasInputLink(node, "depth_map") ? "Live" : "Open");
      mode.setValue(currentMode);
      focalDepth.setValue(getNumber(node, "focal_depth", 0.5));
      depthRange.setValue(getNumber(node, "depth_range", 0.25));
      depthContrast.setValue(getNumber(node, "depth_contrast", 1.0));
      nearBlur.setValue(getNumber(node, "near_blur", 10));
      farBlur.setValue(getNumber(node, "far_blur", 18));
      hazeStrength.setValue(getNumber(node, "haze_strength", 0.15));
      hazeR.setValue(getNumber(node, "haze_r", 0.74));
      hazeG.setValue(getNumber(node, "haze_g", 0.82));
      hazeB.setValue(getNumber(node, "haze_b", 0.92));
      maskFeather.setValue(getNumber(node, "mask_feather", 12));
      invertMask.setValue(getBoolean(node, "invert_mask", false));
    } catch (error) {
      console.error(`[${EXTENSION_NAME}] control refresh failed`, error);
    }

    try {
      drawDepthPreview(previewCanvas, node);
    } catch (error) {
      console.error(`[${EXTENSION_NAME}] preview draw failed`, error);
      const { ctx, width, height } = ensureCanvasResolution(previewCanvas);
      drawFallbackPreview(ctx, width, height);
    }
  }

  const attached = attachPanel(node, DEPTH_PANEL, panel, PANEL_WIDTH, PANEL_HEIGHT);
  if (!attached) {
    throw new Error("Depth FX studio panel failed to attach");
  }
  normalizePanelNode(node, DEPTH_HIDDEN_WIDGETS, DEPTH_PANEL);
  installRefreshHooks(node, "__mkrDepthRefreshHooksInstalled", refreshPanel);
  node.__mkrDepthRefresh = refreshPanel;
  refreshPanel();
  requestAnimationFrame(() => refreshPanel());
}

function prepareNode(node) {
  if (!isDepthNode(node) && !matchesNode(node, DEPTH_NODE)) return;
  installDepthAdapter(node);

  const hasPanel = Boolean(node?.[`__${DEPTH_PANEL}`]);
  if (node.__mkrDepthPanelReady && hasPanel) {
    node.__mkrDepthRefresh?.();
    normalizePanelNode(node, DEPTH_HIDDEN_WIDGETS, DEPTH_PANEL);
    return;
  }

  try {
    buildDepthPanel(node);
    node.__mkrDepthPanelReady = true;
  } catch (error) {
    node.__mkrDepthPanelReady = false;
    console.error("[MKRShift.VFXConceptStudios] failed to build Depth FX studio", error);
  }
}

function schedulePrepareNode(node, attempt = 0) {
  if (!node) return;
  prepareNode(node);
  if (node?.[`__${DEPTH_PANEL}`]) return;
  if (attempt >= 8) return;
  requestAnimationFrame(() => schedulePrepareNode(node, attempt + 1));
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const rawName = String(nodeData?.name || nodeData?.type || nodeData?.display_name || "");
    if (!(rawName === DEPTH_NODE || rawName.includes("Depth FX"))) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = typeof originalOnNodeCreated === "function"
        ? originalOnNodeCreated.apply(this, arguments)
        : undefined;
      this.__mkrDepthEligible = true;
      this.comfyClass ??= DEPTH_NODE;
      schedulePrepareNode(this);
      return result;
    };
  },
  async nodeCreated(node) {
    if (matchesNode(node, DEPTH_NODE) || isDepthNode(node)) {
      node.__mkrDepthEligible = true;
      schedulePrepareNode(node);
    }
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      if (matchesNode(node, DEPTH_NODE) || isDepthNode(node)) {
        node.__mkrDepthEligible = true;
        schedulePrepareNode(node);
      }
    }
  },
  async setup() {
    const scan = () => {
      for (const node of app.graph?._nodes || []) {
        if (matchesNode(node, DEPTH_NODE) || isDepthNode(node)) {
          node.__mkrDepthEligible = true;
          schedulePrepareNode(node);
        }
      }
    };
    requestAnimationFrame(scan);
    setTimeout(scan, 150);
    setTimeout(scan, 600);
  },
});
