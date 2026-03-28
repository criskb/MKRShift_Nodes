import { app } from "../../../scripts/app.js";
import { createPanelShell } from "./uiSystem.js";
import {
  attachPanel,
  createGradeButton,
  createGradeMetric,
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

const EXTENSION_NAME = "MKRShift.ColorUtilityStudios";
const STYLE_ID = "mkr-color-utility-studios-v1";
const SETTINGS_WIDGET_NAME = "settings_json";

const PALETTE_NODE = "x1PaletteMap";
const MATCH_NODE = "x1ColorMatch";
const FALSE_COLOR_NODE = "x1FalseColor";

const PALETTE_PANEL = "mkr_color_palette_map_studio";
const MATCH_PANEL = "mkr_color_match_studio";
const FALSE_COLOR_PANEL = "mkr_color_false_color_studio";

const PALETTE_SIZE = [780, 820];
const MATCH_SIZE = [760, 700];
const FALSE_COLOR_SIZE = [760, 760];

const PALETTE_DEFAULTS = {
  palette_preset: "teal_orange",
  mapping_mode: "soft",
  softness: 0.5,
  preserve_luma: true,
  amount: 1.0,
  c1_r: 0.08,
  c1_g: 0.22,
  c1_b: 0.28,
  c2_r: 0.18,
  c2_g: 0.52,
  c2_b: 0.62,
  c3_r: 0.84,
  c3_g: 0.52,
  c3_b: 0.22,
  c4_r: 1.0,
  c4_g: 0.8,
  c4_b: 0.55,
  mask_feather: 12.0,
  invert_mask: false,
};

const PALETTE_NUMERIC = {
  softness: { min: 0.01, max: 4.0 },
  amount: { min: 0.0, max: 1.0 },
  c1_r: { min: 0.0, max: 1.0 },
  c1_g: { min: 0.0, max: 1.0 },
  c1_b: { min: 0.0, max: 1.0 },
  c2_r: { min: 0.0, max: 1.0 },
  c2_g: { min: 0.0, max: 1.0 },
  c2_b: { min: 0.0, max: 1.0 },
  c3_r: { min: 0.0, max: 1.0 },
  c3_g: { min: 0.0, max: 1.0 },
  c3_b: { min: 0.0, max: 1.0 },
  c4_r: { min: 0.0, max: 1.0 },
  c4_g: { min: 0.0, max: 1.0 },
  c4_b: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const MATCH_DEFAULTS = {
  method: "mean_std",
  strength: 0.85,
  preserve_luma: false,
  mask_feather: 12.0,
  invert_mask: false,
};

const MATCH_NUMERIC = {
  strength: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const FALSE_COLOR_DEFAULTS = {
  mode: "luma_ramp",
  overlay_opacity: 1.0,
  zebra_threshold: 0.95,
  low_clip: 0.02,
  high_clip: 0.98,
  show_zebra: true,
  mask_feather: 12.0,
  invert_mask: false,
};

const FALSE_COLOR_NUMERIC = {
  overlay_opacity: { min: 0.0, max: 1.0 },
  zebra_threshold: { min: 0.0, max: 1.0 },
  low_clip: { min: 0.0, max: 1.0 },
  high_clip: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const PALETTE_PRESETS = {
  teal_orange: ["#163546", "#347f92", "#d47d32", "#f5c56c"],
  pastel_pop: ["#b5d8ff", "#ffc0d2", "#ffe7a6", "#f8f5ef"],
  neon_night: ["#100f28", "#0d84e6", "#af33ff", "#ff6f4d"],
  earth_film: ["#2c261f", "#74614b", "#a78461", "#dfc1a0"],
  mono_tint: ["#1c1f29", "#59677f", "#b0bac8", "#f1efe8"],
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
    .mkr-color-utility-select {
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

    .mkr-color-utility-preview {
      position: relative;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.08);
      background: linear-gradient(180deg, rgba(12,15,20,0.98), rgba(18,22,28,0.98));
      min-height: 224px;
    }

    .mkr-color-utility-preview canvas {
      display: block;
      width: 100%;
      height: 224px;
    }

    .mkr-color-utility-hint {
      margin-top: 8px;
      font-size: 11px;
      color: rgba(224,231,236,0.62);
      line-height: 1.45;
    }

    .mkr-color-swatch-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .mkr-color-swatch {
      display: grid;
      grid-template-columns: 70px 1fr;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
    }

    .mkr-color-swatch-label {
      font-size: 11px;
      color: rgba(236,241,245,0.86);
      font-weight: 700;
      letter-spacing: 0.01em;
    }

    .mkr-color-swatch-input {
      width: 100%;
      height: 34px;
      padding: 0;
      border: 0;
      background: transparent;
      cursor: pointer;
    }
  `;
  document.head.appendChild(style);
}

function rgbToHex(rgb) {
  const parts = rgb.map((value) => {
    const v = clamp(Math.round(Number(value) * 255), 0, 255);
    return v.toString(16).padStart(2, "0");
  });
  return `#${parts.join("")}`;
}

function hexToRgb(hex) {
  const token = String(hex || "").replace("#", "").trim();
  if (!/^[0-9a-fA-F]{6}$/.test(token)) return [0, 0, 0];
  return [
    parseInt(token.slice(0, 2), 16) / 255,
    parseInt(token.slice(2, 4), 16) / 255,
    parseInt(token.slice(4, 6), 16) / 255,
  ];
}

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;
  const select = document.createElement("select");
  select.className = "mkr-color-utility-select";
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

function createColorSwatchControl({ label, value, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-color-swatch";
  const labelNode = document.createElement("div");
  labelNode.className = "mkr-color-swatch-label";
  labelNode.textContent = label;
  const input = document.createElement("input");
  input.type = "color";
  input.className = "mkr-color-swatch-input";
  input.value = value;
  input.addEventListener("input", () => onChange?.(input.value));
  root.appendChild(labelNode);
  root.appendChild(input);
  return {
    element: root,
    setValue(next) {
      input.value = next;
    },
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

function getPaletteHexes(node) {
  return [1, 2, 3, 4].map((index) =>
    rgbToHex([
      getNumber(node, `c${index}_r`, PALETTE_DEFAULTS[`c${index}_r`]),
      getNumber(node, `c${index}_g`, PALETTE_DEFAULTS[`c${index}_g`]),
      getNumber(node, `c${index}_b`, PALETTE_DEFAULTS[`c${index}_b`]),
    ])
  );
}

function setPaletteColor(node, index, hex) {
  const [r, g, b] = hexToRgb(hex);
  applyValues(node, {
    [`c${index}_r`]: r,
    [`c${index}_g`]: g,
    [`c${index}_b`]: b,
    palette_preset: "custom",
  });
}

function drawPalettePreview(ctx, width, height, settings, paletteHexes) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(16,18,24,1)");
  bg.addColorStop(1, "rgba(28,32,40,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const swatchH = 48;
  const swatchW = width / 4;
  for (let i = 0; i < 4; i += 1) {
    ctx.fillStyle = paletteHexes[i];
    ctx.fillRect(i * swatchW, 0, swatchW, swatchH);
  }

  const grad = ctx.createLinearGradient(0, swatchH + 22, width, swatchH + 22);
  paletteHexes.forEach((hex, index) => {
    grad.addColorStop(index / 3, hex);
  });
  ctx.fillStyle = grad;
  ctx.fillRect(0, swatchH + 14, width, 56);

  const mode = String(settings.mapping_mode || "soft");
  const softness = clamp(Number(settings.softness) || 0.5, 0.01, 4.0);
  const amount = clamp(Number(settings.amount) || 1.0, 0.0, 1.0);
  const preserveLuma = !!settings.preserve_luma;

  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, swatchH + 14.5, width - 1, 55);

  ctx.strokeStyle = mode === "nearest" ? "rgba(255,173,80,0.9)" : "rgba(99,213,255,0.9)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < 120; i += 1) {
    const t = i / 119;
    const x = t * width;
    const base = mode === "nearest"
      ? Math.round(t * 3) / 3
      : t + (Math.sin(t * 8.0) * 0.02 * softness);
    const y = swatchH + 96 - (clamp(base, 0, 1) * 92 * (0.6 + (amount * 0.4)));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = "rgba(240,244,248,0.76)";
  ctx.font = "12px sans-serif";
  ctx.fillText(preserveLuma ? "Preserve Luma" : "Free Luma", 14, height - 16);
}

function drawColorMatchPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "rgba(16,18,22,1)");
  bg.addColorStop(1, "rgba(28,31,36,1)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  const strength = clamp(Number(settings.strength) || 0.85, 0, 1);
  const preserveLuma = !!settings.preserve_luma;
  const method = String(settings.method || "mean_std");

  const barY = 28;
  const barH = 34;
  const bands = [
    ["rgba(70,104,180,1)", "rgba(128,168,232,1)"],
    ["rgba(128,106,82,1)", "rgba(214,160,102,1)"],
    ["rgba(46,122,106,1)", "rgba(102,212,196,1)"],
  ];

  bands.forEach((pair, idx) => {
    const grad = ctx.createLinearGradient(0, 0, width * (0.46 + (idx * 0.06)), 0);
    grad.addColorStop(0, pair[0]);
    grad.addColorStop(1, pair[1]);
    ctx.fillStyle = grad;
    ctx.fillRect(24, barY + (idx * 48), width * 0.42, barH);
  });

  bands.forEach((pair, idx) => {
    const grad = ctx.createLinearGradient(width * 0.54, 0, width - 24, 0);
    grad.addColorStop(0, pair[1]);
    grad.addColorStop(1, pair[0]);
    ctx.fillStyle = grad;
    ctx.fillRect(width * 0.54, barY + (idx * 48), width * 0.30, barH);
  });

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < 90; i += 1) {
    const t = i / 89;
    const x = 26 + (t * (width - 52));
    const blend = method === "mean_only" ? t : Math.pow(t, 0.8 + ((1.0 - strength) * 0.7));
    const y = height - 30 - (blend * (height - 92));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = "rgba(240,244,248,0.78)";
  ctx.font = "12px sans-serif";
  ctx.fillText("Source", 24, 18);
  ctx.fillText("Reference", width * 0.54, 18);
  ctx.fillText(preserveLuma ? "Luma Protected" : "Full Match", 24, height - 16);
}

function drawFalseColorPreview(ctx, width, height, settings) {
  ctx.clearRect(0, 0, width, height);
  const mode = String(settings.mode || "luma_ramp");
  const opacity = clamp(Number(settings.overlay_opacity) || 1.0, 0, 1);
  const lowClip = clamp(Number(settings.low_clip) || 0.02, 0, 1);
  const highClip = clamp(Number(settings.high_clip) || 0.98, 0, 1);
  const zebra = !!settings.show_zebra;

  const grad = ctx.createLinearGradient(0, 0, width, 0);
  if (mode === "exposure_zones") {
    [
      "#000000",
      "#1a1a8c",
      "#2159d6",
      "#28b2f2",
      "#15e65c",
      "#73f11a",
      "#f2ef1a",
      "#f2b312",
      "#f26312",
      "#f20d0d",
    ].forEach((color, index, array) => grad.addColorStop(index / (array.length - 1), color));
  } else if (mode === "clipping") {
    grad.addColorStop(0, "#2469ff");
    grad.addColorStop(lowClip, "#525963");
    grad.addColorStop(highClip, "#8e949b");
    grad.addColorStop(1, "#ff3d2e");
  } else {
    [
      "#000000",
      "#0000cc",
      "#00a4ff",
      "#00f760",
      "#ffea00",
      "#ff7a00",
      "#ff0000",
    ].forEach((color, index, array) => grad.addColorStop(index / (array.length - 1), color));
  }

  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);

  if (zebra) {
    ctx.fillStyle = `rgba(255,255,255,${0.14 + (opacity * 0.18)})`;
    for (let x = Math.floor(width * highClip); x < width + 24; x += 12) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + 18, 0);
      ctx.lineTo(x - height + 18, height);
      ctx.lineTo(x - height, height);
      ctx.closePath();
      ctx.fill();
    }
  }

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.lineWidth = 2;
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function buildPalettePanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Palette Map Studio",
    subtitle: "Push footage into a designed palette with swatches, blending mode, and luma protection.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#8cc8ff");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const presetMetric = createGradeMetric("Preset", "teal_orange");
  const modeMetric = createGradeMetric("Mode", "soft");
  const amountMetric = createGradeMetric("Amount", "1.00");
  metricsWrap.appendChild(presetMetric.element);
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(amountMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Teal/Orange", () => { applyPalettePreset(node, "teal_orange"); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Pastel", () => { applyPalettePreset(node, "pastel_pop"); refreshPanel(); }));
  actions.appendChild(createGradeButton("Neon", () => { applyPalettePreset(node, "neon_night"); refreshPanel(); }));
  actions.appendChild(createGradeButton("Earth", () => { applyPalettePreset(node, "earth_film"); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Palette Preview", "swatch to remap");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-utility-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  const hint = document.createElement("div");
  hint.className = "mkr-color-utility-hint";
  hint.textContent = "Switch to custom and edit the four palette anchors directly when you want to design a bespoke look without a LUT.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const mapSection = createGradeSection("Remap", "blend");
  const mapControls = document.createElement("div");
  mapControls.className = "mkr-grade-controls";
  const presetSelect = createSelectControl({
    label: "Preset",
    value: getValue(node, "palette_preset", PALETTE_DEFAULTS.palette_preset),
    options: [
      { value: "teal_orange", label: "Teal / Orange" },
      { value: "pastel_pop", label: "Pastel Pop" },
      { value: "neon_night", label: "Neon Night" },
      { value: "earth_film", label: "Earth Film" },
      { value: "mono_tint", label: "Mono Tint" },
      { value: "custom", label: "Custom" },
    ],
    onChange: (value) => { applyValues(node, { palette_preset: value }); if (value !== "custom") applyPalettePreset(node, value, false); refreshPanel(); },
  });
  const modeSelect = createSelectControl({
    label: "Map Mode",
    value: getValue(node, "mapping_mode", PALETTE_DEFAULTS.mapping_mode),
    options: [
      { value: "soft", label: "Soft" },
      { value: "nearest", label: "Nearest" },
    ],
    onChange: (value) => { setWidgetValue(node, "mapping_mode", value); refreshPanel(); },
  });
  const softness = createGradeSlider({
    label: "Softness",
    min: 0.01,
    max: 4.0,
    step: 0.01,
    value: getNumber(node, "softness", PALETTE_DEFAULTS.softness),
    onChange: (value) => { setWidgetValue(node, "softness", value); refreshPanel(); },
  });
  const amount = createGradeSlider({
    label: "Amount",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "amount", PALETTE_DEFAULTS.amount),
    onChange: (value) => { setWidgetValue(node, "amount", value); refreshPanel(); },
  });
  const preserve = createGradeToggle({
    label: "Preserve Luma",
    checked: getBoolean(node, "preserve_luma", PALETTE_DEFAULTS.preserve_luma),
    description: "Rescale mapped colors to keep the original luminance feel.",
    onChange: (checked) => { setWidgetValue(node, "preserve_luma", checked); refreshPanel(); },
  });
  mapControls.appendChild(presetSelect.element);
  mapControls.appendChild(modeSelect.element);
  mapControls.appendChild(softness.element);
  mapControls.appendChild(amount.element);
  mapControls.appendChild(preserve.element);
  mapSection.body.appendChild(mapControls);
  panel.appendChild(mapSection.section);

  const swatchSection = createGradeSection("Custom Palette", "four anchors");
  const swatchGrid = document.createElement("div");
  swatchGrid.className = "mkr-color-swatch-grid";
  const swatches = [1, 2, 3, 4].map((index) =>
    createColorSwatchControl({
      label: `Color ${index}`,
      value: getPaletteHexes(node)[index - 1],
      onChange: (hex) => { setPaletteColor(node, index, hex); refreshPanel(); },
    })
  );
  swatches.forEach((swatch) => swatchGrid.appendChild(swatch.element));
  swatchSection.body.appendChild(swatchGrid);
  panel.appendChild(swatchSection.section);

  const maskSection = createGradeSection("Mask Gate", "optional");
  const maskControls = document.createElement("div");
  maskControls.className = "mkr-grade-controls";
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", PALETTE_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", PALETTE_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before the palette remap is blended in.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  maskControls.appendChild(maskFeather.element);
  maskControls.appendChild(invertMask.element);
  maskSection.body.appendChild(maskControls);
  panel.appendChild(maskSection.section);

  function refreshPanel() {
    const settings = {
      palette_preset: getValue(node, "palette_preset", PALETTE_DEFAULTS.palette_preset),
      mapping_mode: getValue(node, "mapping_mode", PALETTE_DEFAULTS.mapping_mode),
      softness: getNumber(node, "softness", PALETTE_DEFAULTS.softness),
      preserve_luma: getBoolean(node, "preserve_luma", PALETTE_DEFAULTS.preserve_luma),
      amount: getNumber(node, "amount", PALETTE_DEFAULTS.amount),
      mask_feather: getNumber(node, "mask_feather", PALETTE_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", PALETTE_DEFAULTS.invert_mask),
    };
    const paletteHexes = getPaletteHexes(node);
    presetMetric.setValue(String(settings.palette_preset));
    modeMetric.setValue(String(settings.mapping_mode));
    amountMetric.setValue(formatNumber(settings.amount, 2));
    presetSelect.setValue(settings.palette_preset);
    modeSelect.setValue(settings.mapping_mode);
    softness.setValue(settings.softness);
    amount.setValue(settings.amount);
    preserve.setValue(settings.preserve_luma);
    swatches.forEach((swatch, idx) => swatch.setValue(paletteHexes[idx]));
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawPalettePreview(ctx, width, height, settings, paletteHexes);
  }

  attachPanel(node, PALETTE_PANEL, panel, PALETTE_SIZE[0], PALETTE_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], PALETTE_PANEL);
  installRefreshHooks(node, "__mkrPaletteStudioHooks", refreshPanel);
  refreshPanel();
}

function buildColorMatchPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Color Match Studio",
    subtitle: "Match a source image to a reference with quick control over method, strength, and luminance handling.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#7be0cf");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const methodMetric = createGradeMetric("Method", "mean_std");
  const strengthMetric = createGradeMetric("Strength", "0.85");
  const lumaMetric = createGradeMetric("Luma", "Off");
  metricsWrap.appendChild(methodMetric.element);
  metricsWrap.appendChild(strengthMetric.element);
  metricsWrap.appendChild(lumaMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Mean+Std", () => { applyValues(node, { method: "mean_std" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Mean Only", () => { applyValues(node, { method: "mean_only" }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Match Preview", "source → reference");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-utility-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  const hint = document.createElement("div");
  hint.className = "mkr-color-utility-hint";
  hint.textContent = "Feed the node a reference image on the graph input. This panel focuses on the response and blend controls while the actual match happens in the node output.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Match Controls", "blend");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const methodSelect = createSelectControl({
    label: "Method",
    value: getValue(node, "method", MATCH_DEFAULTS.method),
    options: [
      { value: "mean_std", label: "Mean + Std" },
      { value: "mean_only", label: "Mean Only" },
    ],
    onChange: (value) => { setWidgetValue(node, "method", value); refreshPanel(); },
  });
  const strength = createGradeSlider({
    label: "Strength",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "strength", MATCH_DEFAULTS.strength),
    onChange: (value) => { setWidgetValue(node, "strength", value); refreshPanel(); },
  });
  const preserve = createGradeToggle({
    label: "Preserve Luma",
    checked: getBoolean(node, "preserve_luma", MATCH_DEFAULTS.preserve_luma),
    description: "Rescale the matched result to stay closer to the source luminance.",
    onChange: (checked) => { setWidgetValue(node, "preserve_luma", checked); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", MATCH_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", MATCH_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it gates the match blend.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  controls.appendChild(methodSelect.element);
  controls.appendChild(strength.element);
  controls.appendChild(preserve.element);
  controls.appendChild(maskFeather.element);
  controls.appendChild(invertMask.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  function refreshPanel() {
    const settings = {
      method: getValue(node, "method", MATCH_DEFAULTS.method),
      strength: getNumber(node, "strength", MATCH_DEFAULTS.strength),
      preserve_luma: getBoolean(node, "preserve_luma", MATCH_DEFAULTS.preserve_luma),
      mask_feather: getNumber(node, "mask_feather", MATCH_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", MATCH_DEFAULTS.invert_mask),
    };
    methodMetric.setValue(String(settings.method));
    strengthMetric.setValue(formatNumber(settings.strength, 2));
    lumaMetric.setValue(settings.preserve_luma ? "On" : "Off");
    methodSelect.setValue(settings.method);
    strength.setValue(settings.strength);
    preserve.setValue(settings.preserve_luma);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawColorMatchPreview(ctx, width, height, settings);
  }

  attachPanel(node, MATCH_PANEL, panel, MATCH_SIZE[0], MATCH_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], MATCH_PANEL);
  installRefreshHooks(node, "__mkrColorMatchStudioHooks", refreshPanel);
  refreshPanel();
}

function buildFalseColorPanel(node) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "False Color Studio",
    subtitle: "Inspect exposure, clipping, and zebra thresholds without leaving the graph.",
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#ff9c58");
  panel.style.paddingBottom = "16px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const modeMetric = createGradeMetric("Mode", "luma_ramp");
  const zebraMetric = createGradeMetric("Zebra", "On");
  const clipMetric = createGradeMetric("High", "0.98");
  metricsWrap.appendChild(modeMetric.element);
  metricsWrap.appendChild(zebraMetric.element);
  metricsWrap.appendChild(clipMetric.element);
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Ramp", () => { applyValues(node, { mode: "luma_ramp" }); refreshPanel(); }, "accent"));
  actions.appendChild(createGradeButton("Zones", () => { applyValues(node, { mode: "exposure_zones" }); refreshPanel(); }));
  actions.appendChild(createGradeButton("Clipping", () => { applyValues(node, { mode: "clipping" }); refreshPanel(); }));
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const previewSection = createGradeSection("Preview", "overlay");
  const previewWrap = document.createElement("div");
  previewWrap.className = "mkr-color-utility-preview";
  const canvas = document.createElement("canvas");
  previewWrap.appendChild(canvas);
  previewSection.body.appendChild(previewWrap);
  const hint = document.createElement("div");
  hint.className = "mkr-color-utility-hint";
  hint.textContent = "Use clipping mode for legal-range checks, exposure zones for quick tonal reading, and zebra to tag highlights over the chosen threshold.";
  previewSection.body.appendChild(hint);
  panel.appendChild(previewSection.section);

  const controlsSection = createGradeSection("Controls", "thresholds");
  const controls = document.createElement("div");
  controls.className = "mkr-grade-controls";
  const modeSelect = createSelectControl({
    label: "Mode",
    value: getValue(node, "mode", FALSE_COLOR_DEFAULTS.mode),
    options: [
      { value: "luma_ramp", label: "Luma Ramp" },
      { value: "exposure_zones", label: "Exposure Zones" },
      { value: "clipping", label: "Clipping" },
    ],
    onChange: (value) => { setWidgetValue(node, "mode", value); refreshPanel(); },
  });
  const opacity = createGradeSlider({
    label: "Opacity",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "overlay_opacity", FALSE_COLOR_DEFAULTS.overlay_opacity),
    onChange: (value) => { setWidgetValue(node, "overlay_opacity", value); refreshPanel(); },
  });
  const zebraThreshold = createGradeSlider({
    label: "Zebra Threshold",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "zebra_threshold", FALSE_COLOR_DEFAULTS.zebra_threshold),
    onChange: (value) => { setWidgetValue(node, "zebra_threshold", value); refreshPanel(); },
  });
  const lowClip = createGradeSlider({
    label: "Low Clip",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "low_clip", FALSE_COLOR_DEFAULTS.low_clip),
    onChange: (value) => { setWidgetValue(node, "low_clip", value); refreshPanel(); },
  });
  const highClip = createGradeSlider({
    label: "High Clip",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "high_clip", FALSE_COLOR_DEFAULTS.high_clip),
    onChange: (value) => { setWidgetValue(node, "high_clip", value); refreshPanel(); },
  });
  const showZebra = createGradeToggle({
    label: "Show Zebra",
    checked: getBoolean(node, "show_zebra", FALSE_COLOR_DEFAULTS.show_zebra),
    description: "Add highlight stripes above the zebra threshold.",
    onChange: (checked) => { setWidgetValue(node, "show_zebra", checked); refreshPanel(); },
  });
  const maskFeather = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", FALSE_COLOR_DEFAULTS.mask_feather),
    decimals: 1,
    onChange: (value) => { setWidgetValue(node, "mask_feather", value); refreshPanel(); },
  });
  const invertMask = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", FALSE_COLOR_DEFAULTS.invert_mask),
    description: "Flip the optional external mask before it gates the overlay.",
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); refreshPanel(); },
  });
  controls.appendChild(modeSelect.element);
  controls.appendChild(opacity.element);
  controls.appendChild(zebraThreshold.element);
  controls.appendChild(lowClip.element);
  controls.appendChild(highClip.element);
  controls.appendChild(showZebra.element);
  controls.appendChild(maskFeather.element);
  controls.appendChild(invertMask.element);
  controlsSection.body.appendChild(controls);
  panel.appendChild(controlsSection.section);

  function refreshPanel() {
    const settings = {
      mode: getValue(node, "mode", FALSE_COLOR_DEFAULTS.mode),
      overlay_opacity: getNumber(node, "overlay_opacity", FALSE_COLOR_DEFAULTS.overlay_opacity),
      zebra_threshold: getNumber(node, "zebra_threshold", FALSE_COLOR_DEFAULTS.zebra_threshold),
      low_clip: getNumber(node, "low_clip", FALSE_COLOR_DEFAULTS.low_clip),
      high_clip: getNumber(node, "high_clip", FALSE_COLOR_DEFAULTS.high_clip),
      show_zebra: getBoolean(node, "show_zebra", FALSE_COLOR_DEFAULTS.show_zebra),
      mask_feather: getNumber(node, "mask_feather", FALSE_COLOR_DEFAULTS.mask_feather),
      invert_mask: getBoolean(node, "invert_mask", FALSE_COLOR_DEFAULTS.invert_mask),
    };
    modeMetric.setValue(String(settings.mode));
    zebraMetric.setValue(settings.show_zebra ? "On" : "Off");
    clipMetric.setValue(formatNumber(settings.high_clip, 2));
    modeSelect.setValue(settings.mode);
    opacity.setValue(settings.overlay_opacity);
    zebraThreshold.setValue(settings.zebra_threshold);
    lowClip.setValue(settings.low_clip);
    highClip.setValue(settings.high_clip);
    showZebra.setValue(settings.show_zebra);
    maskFeather.setValue(settings.mask_feather);
    invertMask.setValue(settings.invert_mask);

    const { ctx, width, height } = ensureCanvasResolution(canvas);
    drawFalseColorPreview(ctx, width, height, settings);
  }

  attachPanel(node, FALSE_COLOR_PANEL, panel, FALSE_COLOR_SIZE[0], FALSE_COLOR_SIZE[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME], FALSE_COLOR_PANEL);
  installRefreshHooks(node, "__mkrFalseColorStudioHooks", refreshPanel);
  refreshPanel();
}

function applyPalettePreset(node, presetName, setPresetKey = true) {
  const preset = PALETTE_PRESETS[presetName];
  if (!preset) return;
  const patch = {};
  preset.forEach((hex, idx) => {
    const [r, g, b] = hexToRgb(hex);
    patch[`c${idx + 1}_r`] = r;
    patch[`c${idx + 1}_g`] = g;
    patch[`c${idx + 1}_b`] = b;
  });
  if (setPresetKey) {
    patch.palette_preset = presetName;
  }
  applyValues(node, patch);
}

function prepareNode(node) {
  if (matchesNode(node, PALETTE_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: PALETTE_DEFAULTS,
      numericSpecs: PALETTE_NUMERIC,
      booleanKeys: ["preserve_luma", "invert_mask"],
      legacyNames: Object.keys(PALETTE_DEFAULTS),
    });
    if (!node.__mkrPaletteStudioBuilt) {
      node.__mkrPaletteStudioBuilt = true;
      buildPalettePanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], PALETTE_PANEL);
    }
    return;
  }

  if (matchesNode(node, MATCH_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: MATCH_DEFAULTS,
      numericSpecs: MATCH_NUMERIC,
      booleanKeys: ["preserve_luma", "invert_mask"],
      legacyNames: Object.keys(MATCH_DEFAULTS),
    });
    if (!node.__mkrColorMatchStudioBuilt) {
      node.__mkrColorMatchStudioBuilt = true;
      buildColorMatchPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], MATCH_PANEL);
    }
    return;
  }

  if (matchesNode(node, FALSE_COLOR_NODE)) {
    installBundledSettingsAdapter(node, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: FALSE_COLOR_DEFAULTS,
      numericSpecs: FALSE_COLOR_NUMERIC,
      booleanKeys: ["show_zebra", "invert_mask"],
      legacyNames: Object.keys(FALSE_COLOR_DEFAULTS),
    });
    if (!node.__mkrFalseColorStudioBuilt) {
      node.__mkrFalseColorStudioBuilt = true;
      buildFalseColorPanel(node);
    } else {
      normalizePanelNode(node, [SETTINGS_WIDGET_NAME], FALSE_COLOR_PANEL);
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
