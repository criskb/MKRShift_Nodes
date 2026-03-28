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

const EXTENSION_NAME = "MKRShift.MaterialWeatherStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-material-weather-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function safeViewText(getter, node, fallback = "--") {
  try {
    const value = getter?.(node);
    return value ?? fallback;
  } catch (error) {
    console.warn(`[${EXTENSION_NAME}] view getter failed`, error);
    return fallback;
  }
}

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.18)") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(17,20,24,0.98)");
  bg.addColorStop(1, "rgba(29,33,38,0.98)");
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

function drawFallbackPreview(ctx, width, height, accent, title = "Preview") {
  const frame = drawFrame(ctx, width, height, accent);
  ctx.fillStyle = "rgba(255,255,255,0.05)";
  ctx.fillRect(frame.x + 18, frame.y + 18, frame.w - 36, frame.h - 36);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.setLineDash([6, 6]);
  ctx.strokeRect(frame.x + 18, frame.y + 18, frame.w - 36, frame.h - 36);
  ctx.setLineDash([]);
  drawLabel(ctx, title, frame.x + 30, frame.y + 42, "rgba(255,255,255,0.88)", 13);
  drawLabel(ctx, "Preview ready. Controls remain active.", frame.x + 30, frame.y + 64, "rgba(255,255,255,0.56)", 11);
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-surface-weather-select {
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
  select.className = "mkr-surface-weather-select";
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
  node.onConfigure = function onConfigureMaterialWeatherPanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeMaterialWeatherPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedMaterialWeatherPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawDustPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(223,191,132,0.28)");
  const topBias = getNumber(node, "top_bias", 0.52);
  const cavityBias = getNumber(node, "cavity_bias", 0.44);
  const breakup = getNumber(node, "breakup", 0.30);
  const amount = getNumber(node, "amount", 0.82);
  const coverage = getNumber(node, "coverage", 0.54);

  const panelX = frame.x + 30;
  const panelY = frame.y + 30;
  const panelW = frame.w - 60;
  const panelH = frame.h - 60;

  ctx.fillStyle = "rgba(83,88,96,0.90)";
  ctx.fillRect(panelX, panelY, panelW, panelH);
  ctx.fillStyle = "rgba(60,64,70,0.96)";
  ctx.fillRect(panelX + 22, panelY + 26, panelW * 0.32, panelH * 0.70);
  ctx.fillRect(panelX + panelW * 0.48, panelY + 18, panelW * 0.22, panelH * 0.78);
  ctx.fillRect(panelX + panelW * 0.77, panelY + 34, panelW * 0.12, panelH * 0.58);

  const dust = ctx.createLinearGradient(panelX, panelY, panelX, panelY + panelH);
  dust.addColorStop(0, `rgba(222,204,164,${clamp(0.18 + (amount * 0.34), 0.12, 0.58)})`);
  dust.addColorStop(clamp(0.22 + (topBias * 0.22), 0.20, 0.60), `rgba(212,194,156,${clamp(0.10 + (coverage * 0.18), 0.08, 0.34)})`);
  dust.addColorStop(1, "rgba(212,194,156,0.02)");
  ctx.fillStyle = dust;
  ctx.fillRect(panelX, panelY, panelW, panelH);

  ctx.fillStyle = `rgba(230,214,180,${clamp(0.12 + (cavityBias * 0.22), 0.08, 0.34)})`;
  const ledges = [
    [panelX + 16, panelY + 22, panelW * 0.30, 12],
    [panelX + panelW * 0.46, panelY + 14, panelW * 0.22, 10],
    [panelX + panelW * 0.75, panelY + 30, panelW * 0.11, 9],
  ];
  for (const [x, y, w, h] of ledges) {
    ctx.fillRect(x, y, w, h);
  }

  ctx.strokeStyle = `rgba(255,235,192,${clamp(0.16 + (breakup * 0.22), 0.10, 0.34)})`;
  ctx.lineWidth = 1;
  for (let i = 0; i < 11; i += 1) {
    const y = panelY + 18 + (i * ((panelH - 36) / 10));
    ctx.beginPath();
    ctx.moveTo(panelX + 12, y);
    ctx.lineTo(panelX + panelW - 12, y + Math.sin(i * 1.8) * 3.0);
    ctx.stroke();
  }

  drawLabel(ctx, "top deposit", panelX + 8, panelY + 10, "rgba(245,247,250,0.72)", 10);
  drawLabel(ctx, `${formatNumber(amount, 2)} density`, panelX + panelW - 8, panelY + 10, "rgba(245,247,250,0.62)", 10, "right");
}

function drawStreakPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(122,187,214,0.28)");
  const streakLength = getNumber(node, "streak_length", 0.62);
  const anchorBias = getNumber(node, "anchor_bias", 0.56);
  const breakup = getNumber(node, "breakup", 0.42);
  const coverage = getNumber(node, "coverage", 0.46);
  const direction = String(getValue(node, "direction", "down") || "down").toLowerCase();

  const panelX = frame.x + 28;
  const panelY = frame.y + 24;
  const panelW = frame.w - 56;
  const panelH = frame.h - 48;

  ctx.fillStyle = "rgba(74,78,84,0.92)";
  ctx.fillRect(panelX, panelY, panelW, panelH);

  const streakCount = 7;
  const travelSign = direction === "up" ? -1 : 1;
  const anchorY = direction === "up" ? panelY + panelH - 18 : panelY + 18;
  for (let i = 0; i < streakCount; i += 1) {
    const t = i / (streakCount - 1);
    const x = panelX + 24 + (t * (panelW - 48));
    const wobble = Math.sin((i * 1.7) + (breakup * 8.0)) * 8.0;
    const len = panelH * clamp(0.24 + (streakLength * 0.62) + (Math.cos(i * 1.1) * 0.04), 0.22, 0.86);

    ctx.fillStyle = `rgba(219,196,152,${clamp(0.14 + (anchorBias * 0.22), 0.10, 0.40)})`;
    ctx.beginPath();
    ctx.arc(x, anchorY, 5 + (anchorBias * 4), 0, Math.PI * 2);
    ctx.fill();

    const grad = ctx.createLinearGradient(x, anchorY, x + wobble, anchorY + (len * travelSign));
    if (direction === "up") {
      grad.addColorStop(0, `rgba(210,190,152,${clamp(0.18 + (coverage * 0.18), 0.12, 0.34)})`);
      grad.addColorStop(1, "rgba(210,190,152,0.02)");
    } else {
      grad.addColorStop(0, `rgba(210,190,152,${clamp(0.18 + (coverage * 0.18), 0.12, 0.34)})`);
      grad.addColorStop(1, "rgba(210,190,152,0.02)");
    }
    ctx.strokeStyle = grad;
    ctx.lineWidth = 3.0 + (breakup * 1.2);
    ctx.beginPath();
    ctx.moveTo(x, anchorY);
    ctx.bezierCurveTo(
      x + (wobble * 0.28),
      anchorY + ((len * 0.25) * travelSign),
      x - (wobble * 0.22),
      anchorY + ((len * 0.62) * travelSign),
      x + (wobble * 0.38),
      anchorY + (len * travelSign),
    );
    ctx.stroke();
  }

  drawLabel(ctx, direction === "up" ? "reverse streaks" : "gravity streaks", panelX + 8, panelY + 10, "rgba(245,247,250,0.72)", 10);
  drawLabel(ctx, `${formatNumber(streakLength, 2)} length`, panelX + panelW - 8, panelY + 10, "rgba(245,247,250,0.62)", 10, "right");
}

function drawRustPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(196,122,84,0.30)");
  const cavityBias = getNumber(node, "cavity_bias", 0.48);
  const edgeBias = getNumber(node, "edge_bias", 0.60);
  const warmBias = getNumber(node, "warm_bias", 0.34);
  const bloomSpread = getNumber(node, "bloom_spread", 0.52);
  const breakup = getNumber(node, "breakup", 0.34);

  const panelX = frame.x + 24;
  const panelY = frame.y + 20;
  const panelW = frame.w - 48;
  const panelH = frame.h - 44;

  const steel = ctx.createLinearGradient(panelX, panelY, panelX, panelY + panelH);
  steel.addColorStop(0, "rgba(88,93,100,0.96)");
  steel.addColorStop(1, "rgba(52,56,61,0.96)");
  ctx.fillStyle = steel;
  ctx.fillRect(panelX, panelY, panelW, panelH);

  ctx.strokeStyle = "rgba(18,20,23,0.55)";
  ctx.lineWidth = 2;
  for (let i = 1; i < 4; i += 1) {
    const x = panelX + ((panelW * i) / 4);
    ctx.beginPath();
    ctx.moveTo(x, panelY + 8);
    ctx.lineTo(x, panelY + panelH - 8);
    ctx.stroke();
  }

  const spots = [
    [panelX + panelW * 0.18, panelY + panelH * 0.22, 28 + (bloomSpread * 16)],
    [panelX + panelW * 0.48, panelY + panelH * 0.56, 34 + (bloomSpread * 18)],
    [panelX + panelW * 0.78, panelY + panelH * 0.34, 24 + (bloomSpread * 14)],
  ];
  for (const [cx, cy, r] of spots) {
    const rust = ctx.createRadialGradient(cx, cy, 2, cx, cy, r);
    rust.addColorStop(0, `rgba(184,92,44,${clamp(0.26 + (warmBias * 0.34), 0.18, 0.60)})`);
    rust.addColorStop(0.45, `rgba(146,78,36,${clamp(0.18 + (edgeBias * 0.24), 0.12, 0.44)})`);
    rust.addColorStop(1, "rgba(146,78,36,0.00)");
    ctx.fillStyle = rust;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = `rgba(212,122,78,${clamp(0.20 + (edgeBias * 0.26), 0.14, 0.46)})`;
  ctx.lineWidth = 1.6 + (breakup * 1.2);
  for (let i = 0; i < 5; i += 1) {
    const x = panelX + 18 + (i * ((panelW - 36) / 4));
    ctx.beginPath();
    ctx.moveTo(x, panelY + 14);
    ctx.lineTo(x + Math.sin(i * 1.9) * 6, panelY + panelH - 14);
    ctx.stroke();
  }

  ctx.fillStyle = `rgba(232,160,112,${clamp(0.14 + (cavityBias * 0.24), 0.12, 0.36)})`;
  for (let i = 0; i < 14; i += 1) {
    const x = panelX + 12 + ((i / 13) * (panelW - 24));
    const y = panelY + panelH * (0.18 + ((i % 3) * 0.22));
    ctx.beginPath();
    ctx.arc(x, y, 1.2 + ((i % 4) * 0.5), 0, Math.PI * 2);
    ctx.fill();
  }

  drawLabel(ctx, "oxidation bloom", panelX + 8, panelY + 10, "rgba(245,247,250,0.72)", 10);
  drawLabel(ctx, `${formatNumber(bloomSpread, 2)} spread`, panelX + panelW - 8, panelY + 10, "rgba(245,247,250,0.62)", 10, "right");
}

function drawWaterlinePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(124,170,196,0.28)");
  const lineHeight = getNumber(node, "line_height", 0.72);
  const bandWidth = getNumber(node, "band_width", 0.18);
  const capillaryRise = getNumber(node, "capillary_rise", 0.22);
  const breakup = getNumber(node, "breakup", 0.26);
  const orientation = String(getValue(node, "orientation", "bottom") || "bottom").toLowerCase();

  const panelX = frame.x + 24;
  const panelY = frame.y + 20;
  const panelW = frame.w - 48;
  const panelH = frame.h - 44;

  const base = ctx.createLinearGradient(panelX, panelY, panelX, panelY + panelH);
  base.addColorStop(0, "rgba(102,108,114,0.96)");
  base.addColorStop(1, "rgba(70,74,80,0.96)");
  ctx.fillStyle = base;
  ctx.fillRect(panelX, panelY, panelW, panelH);

  const lineY = panelY + (clamp(lineHeight, 0.05, 0.95) * panelH);
  const wobble = 6 + (breakup * 10);
  ctx.beginPath();
  ctx.moveTo(panelX, lineY);
  for (let i = 0; i <= 28; i += 1) {
    const t = i / 28;
    const x = panelX + (t * panelW);
    const y = lineY + (Math.sin((t * 8.0) + 0.8) * wobble) + (Math.cos((t * 21.0) - 0.5) * wobble * 0.35);
    ctx.lineTo(x, y);
  }
  ctx.lineTo(panelX + panelW, orientation === "top" ? panelY : panelY + panelH);
  ctx.lineTo(panelX, orientation === "top" ? panelY : panelY + panelH);
  ctx.closePath();

  const fill = ctx.createLinearGradient(panelX, panelY, panelX, panelY + panelH);
  if (orientation === "top") {
    fill.addColorStop(0, "rgba(190,184,168,0.24)");
    fill.addColorStop(clamp(lineHeight, 0.08, 0.90), `rgba(210,198,170,${clamp(0.18 + (bandWidth * 0.80), 0.16, 0.34)})`);
    fill.addColorStop(1, "rgba(210,198,170,0.02)");
  } else {
    fill.addColorStop(0, "rgba(210,198,170,0.02)");
    fill.addColorStop(clamp(lineHeight, 0.08, 0.90), `rgba(210,198,170,${clamp(0.18 + (bandWidth * 0.80), 0.16, 0.34)})`);
    fill.addColorStop(1, "rgba(190,184,168,0.24)");
  }
  ctx.fillStyle = fill;
  ctx.fill();

  ctx.strokeStyle = `rgba(222,210,182,${clamp(0.22 + (capillaryRise * 0.32), 0.16, 0.48)})`;
  ctx.lineWidth = 2.0;
  ctx.beginPath();
  ctx.moveTo(panelX, lineY);
  for (let i = 0; i <= 32; i += 1) {
    const t = i / 32;
    const x = panelX + (t * panelW);
    const y = lineY + (Math.sin((t * 9.0) + 0.4) * wobble * 0.65);
    ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.lineWidth = 1;
  for (let i = 0; i < 7; i += 1) {
    const y = panelY + 14 + (i * ((panelH - 28) / 6));
    ctx.beginPath();
    ctx.moveTo(panelX + 8, y);
    ctx.lineTo(panelX + panelW - 8, y);
    ctx.stroke();
  }

  drawLabel(ctx, orientation === "top" ? "reverse waterline" : "settled waterline", panelX + 8, panelY + 10, "rgba(245,247,250,0.72)", 10);
  drawLabel(ctx, `${formatNumber(lineHeight, 2)} level`, panelX + panelW - 8, panelY + 10, "rgba(245,247,250,0.62)", 10, "right");
}

const NODE_CONFIGS = {
  x1SurfaceDustMask: {
    panelName: "mkrX1SurfaceDustMaskStudio",
    size: [790, 860],
    accent: "#dfbf84",
    title: "Surface Dust Studio",
    subtitle: "Build dust accumulation masks with top bias, crevice weighting, breakup, and controlled coverage from one authored panel.",
    defaults: {
      source_mode: "combined_dust",
      top_bias: 0.52,
      cavity_bias: 0.44,
      breakup: 0.30,
      amount: 0.82,
      coverage: 0.54,
      contrast: 1.20,
      gamma: 1.0,
      blur_radius: 1.2,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      top_bias: { min: 0.0, max: 1.0 },
      cavity_bias: { min: 0.0, max: 1.0 },
      breakup: { min: 0.0, max: 1.0 },
      amount: { min: 0.0, max: 1.0 },
      coverage: { min: 0.0, max: 1.0 },
      contrast: { min: 0.1, max: 4.0 },
      gamma: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "top_bias", "cavity_bias", "breakup", "amount", "coverage", "contrast", "gamma", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_dust")) },
      { label: "Coverage", get: (node) => formatNumber(getNumber(node, "coverage", 0.54), 2) },
      { label: "Amount", get: (node) => formatNumber(getNumber(node, "amount", 0.82), 2) },
    ],
    presets: [
      { label: "Workshop", tone: "accent", values: { source_mode: "combined_dust", top_bias: 0.52, cavity_bias: 0.44, breakup: 0.30, amount: 0.82, coverage: 0.54, contrast: 1.20, gamma: 1.0, blur_radius: 1.2, invert_values: false } },
      { label: "Shelf Dust", values: { source_mode: "combined_dust", top_bias: 0.74, cavity_bias: 0.28, breakup: 0.22, amount: 0.70, coverage: 0.42, contrast: 1.08, gamma: 1.0, blur_radius: 0.8, invert_values: false } },
      { label: "Heavy Deposit", values: { source_mode: "inverse_luma", top_bias: 0.60, cavity_bias: 0.62, breakup: 0.46, amount: 0.94, coverage: 0.70, contrast: 1.36, gamma: 0.92, blur_radius: 1.8, invert_values: false } },
    ],
    graph: {
      title: "Deposit Preview",
      note: "surface accumulation",
      height: 236,
      help: "The sketch favors ledges, top-facing regions, and crevices so you can judge whether the dust read is subtle shelf residue or a heavy settled layer.",
      readouts: [
        { label: "Top Bias", get: (node) => formatNumber(getNumber(node, "top_bias", 0.52), 2) },
        { label: "Cavity", get: (node) => formatNumber(getNumber(node, "cavity_bias", 0.44), 2) },
        { label: "Breakup", get: (node) => formatNumber(getNumber(node, "breakup", 0.30), 2) },
      ],
      draw: drawDustPreview,
    },
    sections: [
      {
        title: "Source",
        note: "analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Dust", value: "combined_dust" }, { label: "Luma", value: "luma" }, { label: "Inverse Luma", value: "inverse_luma" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "top_bias", label: "Top Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "cavity_bias", label: "Cavity Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "breakup", label: "Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Deposit",
        note: "coverage shaping",
        controls: [
          { key: "amount", label: "Amount", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "coverage", label: "Coverage", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Output",
        note: "final mask",
        controls: [
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the dust mask after the deposition model is built." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1SurfaceStreakMask: {
    panelName: "mkrX1SurfaceStreakMaskStudio",
    size: [790, 860],
    accent: "#7abbd6",
    title: "Surface Streak Studio",
    subtitle: "Build leak and grime streak masks with directional travel, anchor weighting, breakup, and coverage control.",
    defaults: {
      source_mode: "combined_streak",
      direction: "down",
      streak_length: 0.62,
      anchor_bias: 0.56,
      breakup: 0.42,
      coverage: 0.46,
      contrast: 1.25,
      gamma: 1.0,
      blur_radius: 1.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      streak_length: { min: 0.0, max: 1.0 },
      anchor_bias: { min: 0.0, max: 1.0 },
      breakup: { min: 0.0, max: 1.0 },
      coverage: { min: 0.0, max: 1.0 },
      contrast: { min: 0.1, max: 4.0 },
      gamma: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "direction", "streak_length", "anchor_bias", "breakup", "coverage", "contrast", "gamma", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Direction", get: (node) => String(getValue(node, "direction", "down")) },
      { label: "Length", get: (node) => formatNumber(getNumber(node, "streak_length", 0.62), 2) },
      { label: "Coverage", get: (node) => formatNumber(getNumber(node, "coverage", 0.46), 2) },
    ],
    presets: [
      { label: "Rain Marks", tone: "accent", values: { source_mode: "combined_streak", direction: "down", streak_length: 0.62, anchor_bias: 0.56, breakup: 0.42, coverage: 0.46, contrast: 1.25, gamma: 1.0, blur_radius: 1.0, invert_values: false } },
      { label: "Oil Runs", values: { source_mode: "inverse_luma", direction: "down", streak_length: 0.82, anchor_bias: 0.66, breakup: 0.28, coverage: 0.54, contrast: 1.40, gamma: 0.92, blur_radius: 1.4, invert_values: false } },
      { label: "Reverse Drag", values: { source_mode: "detail", direction: "up", streak_length: 0.58, anchor_bias: 0.48, breakup: 0.54, coverage: 0.38, contrast: 1.16, gamma: 1.08, blur_radius: 0.8, invert_values: false } },
    ],
    graph: {
      title: "Travel Preview",
      note: "directional grime",
      height: 236,
      help: "The preview shows how anchors seed the streaks and how far the grime travels before fading, so length and breakup feel easier to tune in context.",
      readouts: [
        { label: "Anchors", get: (node) => formatNumber(getNumber(node, "anchor_bias", 0.56), 2) },
        { label: "Breakup", get: (node) => formatNumber(getNumber(node, "breakup", 0.42), 2) },
        { label: "Blur", get: (node) => `${formatNumber(getNumber(node, "blur_radius", 1.0), 1)} px` },
      ],
      draw: drawStreakPreview,
    },
    sections: [
      {
        title: "Source",
        note: "anchor analysis",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Streak", value: "combined_streak" }, { label: "Luma", value: "luma" }, { label: "Inverse Luma", value: "inverse_luma" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "direction", type: "select", label: "Direction", options: [{ label: "Down", value: "down" }, { label: "Up", value: "up" }] },
          { key: "anchor_bias", label: "Anchor Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "breakup", label: "Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Travel",
        note: "flow shaping",
        controls: [
          { key: "streak_length", label: "Streak Length", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "coverage", label: "Coverage", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Output",
        note: "final mask",
        controls: [
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final streak mask after the directional build." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1SurfaceRustBloomMask: {
    panelName: "mkrX1SurfaceRustBloomMaskStudio",
    size: [790, 880],
    accent: "#c97a56",
    title: "Surface Rust Bloom Studio",
    subtitle: "Build oxidation masks from crevices, exposed edges, warm contamination, and bloom spread with one tuned weather panel.",
    defaults: {
      source_mode: "combined_rust",
      cavity_bias: 0.48,
      edge_bias: 0.60,
      warm_bias: 0.34,
      bloom_spread: 0.52,
      breakup: 0.34,
      amount: 0.86,
      coverage: 0.48,
      contrast: 1.28,
      gamma: 1.0,
      blur_radius: 1.2,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      cavity_bias: { min: 0.0, max: 1.0 },
      edge_bias: { min: 0.0, max: 1.0 },
      warm_bias: { min: 0.0, max: 1.0 },
      bloom_spread: { min: 0.0, max: 1.0 },
      breakup: { min: 0.0, max: 1.0 },
      amount: { min: 0.0, max: 1.0 },
      coverage: { min: 0.0, max: 1.0 },
      contrast: { min: 0.1, max: 4.0 },
      gamma: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "cavity_bias", "edge_bias", "warm_bias", "bloom_spread", "breakup", "amount", "coverage", "contrast", "gamma", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "combined_rust")) },
      { label: "Spread", get: (node) => formatNumber(getNumber(node, "bloom_spread", 0.52), 2) },
      { label: "Coverage", get: (node) => formatNumber(getNumber(node, "coverage", 0.48), 2) },
    ],
    presets: [
      { label: "Oxide Edge", tone: "accent", values: { source_mode: "combined_rust", cavity_bias: 0.42, edge_bias: 0.72, warm_bias: 0.26, bloom_spread: 0.44, breakup: 0.28, amount: 0.82, coverage: 0.42, contrast: 1.34, gamma: 1.0, blur_radius: 0.9, invert_values: false } },
      { label: "Warm Patina", values: { source_mode: "combined_rust", cavity_bias: 0.48, edge_bias: 0.42, warm_bias: 0.58, bloom_spread: 0.62, breakup: 0.34, amount: 0.78, coverage: 0.50, contrast: 1.18, gamma: 1.0, blur_radius: 1.3, invert_values: false } },
      { label: "Corrosion Bloom", values: { source_mode: "inverse_luma", cavity_bias: 0.62, edge_bias: 0.66, warm_bias: 0.32, bloom_spread: 0.76, breakup: 0.44, amount: 0.94, coverage: 0.62, contrast: 1.46, gamma: 0.92, blur_radius: 1.8, invert_values: false } },
    ],
    graph: {
      title: "Oxidation Preview",
      note: "rust spread",
      height: 236,
      help: "The sketch favors seams, pits, and already warm regions so you can tune whether the corrosion sits on exposed edges or blooms outward into broader oxidation.",
      readouts: [
        { label: "Cavity", get: (node) => formatNumber(getNumber(node, "cavity_bias", 0.48), 2) },
        { label: "Edge", get: (node) => formatNumber(getNumber(node, "edge_bias", 0.60), 2) },
        { label: "Warmth", get: (node) => formatNumber(getNumber(node, "warm_bias", 0.34), 2) },
      ],
      draw: drawRustPreview,
    },
    sections: [
      {
        title: "Sources",
        note: "oxidation seeding",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Rust", value: "combined_rust" }, { label: "Luma", value: "luma" }, { label: "Inverse Luma", value: "inverse_luma" }, { label: "Saturation", value: "saturation" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "cavity_bias", label: "Cavity Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "edge_bias", label: "Edge Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "warm_bias", label: "Warm Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Bloom",
        note: "growth shaping",
        controls: [
          { key: "bloom_spread", label: "Bloom Spread", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "breakup", label: "Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "amount", label: "Amount", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "coverage", label: "Coverage", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Output",
        note: "final mask",
        controls: [
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the corrosion mask after the bloom model is built." },
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional effect mask before output." },
        ],
      },
    ],
  },
  x1SurfaceWaterlineMask: {
    panelName: "mkrX1SurfaceWaterlineMaskStudio",
    size: [790, 880],
    accent: "#7caac4",
    title: "Surface Waterline Studio",
    subtitle: "Build mineral rings and tide lines with level, band width, capillary creep, and cavity weighting in one authored mask panel.",
    defaults: {
      source_mode: "combined_waterline",
      orientation: "bottom",
      line_height: 0.72,
      band_width: 0.18,
      capillary_rise: 0.22,
      cavity_bias: 0.44,
      breakup: 0.26,
      amount: 0.84,
      coverage: 0.50,
      contrast: 1.20,
      gamma: 1.0,
      blur_radius: 1.0,
      invert_values: false,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      line_height: { min: 0.0, max: 1.0 },
      band_width: { min: 0.04, max: 0.50 },
      capillary_rise: { min: 0.0, max: 1.0 },
      cavity_bias: { min: 0.0, max: 1.0 },
      breakup: { min: 0.0, max: 1.0 },
      amount: { min: 0.0, max: 1.0 },
      coverage: { min: 0.0, max: 1.0 },
      contrast: { min: 0.1, max: 4.0 },
      gamma: { min: 0.1, max: 4.0 },
      blur_radius: { min: 0.0, max: 128.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_values", "invert_mask"],
    legacyNames: ["source_mode", "orientation", "line_height", "band_width", "capillary_rise", "cavity_bias", "breakup", "amount", "coverage", "contrast", "gamma", "blur_radius", "invert_values", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Side", get: (node) => String(getValue(node, "orientation", "bottom")) },
      { label: "Level", get: (node) => formatNumber(getNumber(node, "line_height", 0.72), 2) },
      { label: "Band", get: (node) => formatNumber(getNumber(node, "band_width", 0.18), 2) },
    ],
    presets: [
      { label: "Basement Ring", tone: "accent", values: { source_mode: "combined_waterline", orientation: "bottom", line_height: 0.74, band_width: 0.20, capillary_rise: 0.18, cavity_bias: 0.44, breakup: 0.20, amount: 0.84, coverage: 0.48, contrast: 1.24, gamma: 1.0, blur_radius: 1.0, invert_values: false } },
      { label: "Tide Mark", values: { source_mode: "combined_waterline", orientation: "bottom", line_height: 0.60, band_width: 0.14, capillary_rise: 0.32, cavity_bias: 0.52, breakup: 0.32, amount: 0.88, coverage: 0.56, contrast: 1.16, gamma: 1.0, blur_radius: 1.2, invert_values: false } },
      { label: "Overhead Stain", values: { source_mode: "inverse_luma", orientation: "top", line_height: 0.30, band_width: 0.16, capillary_rise: 0.26, cavity_bias: 0.40, breakup: 0.34, amount: 0.80, coverage: 0.44, contrast: 1.12, gamma: 1.0, blur_radius: 1.1, invert_values: false } },
    ],
    graph: {
      title: "Waterline Preview",
      note: "tide ring",
      height: 236,
      help: "The preview shows a living waterline with capillary creep so you can place the level precisely and judge whether the stain feels like a soft mineral ring or a broader damp tide line.",
      readouts: [
        { label: "Capillary", get: (node) => formatNumber(getNumber(node, "capillary_rise", 0.22), 2) },
        { label: "Cavity", get: (node) => formatNumber(getNumber(node, "cavity_bias", 0.44), 2) },
        { label: "Breakup", get: (node) => formatNumber(getNumber(node, "breakup", 0.26), 2) },
      ],
      draw: drawWaterlinePreview,
    },
    sections: [
      {
        title: "Placement",
        note: "line position",
        controls: [
          { key: "source_mode", type: "select", label: "Source", options: [{ label: "Combined Waterline", value: "combined_waterline" }, { label: "Luma", value: "luma" }, { label: "Inverse Luma", value: "inverse_luma" }, { label: "Detail", value: "detail" }, { label: "Mask", value: "mask" }] },
          { key: "orientation", type: "select", label: "Orientation", options: [{ label: "Bottom", value: "bottom" }, { label: "Top", value: "top" }] },
          { key: "line_height", label: "Line Height", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "band_width", label: "Band Width", min: 0.04, max: 0.50, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Creep",
        note: "capillary shaping",
        controls: [
          { key: "capillary_rise", label: "Capillary Rise", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "cavity_bias", label: "Cavity Bias", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "breakup", label: "Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "amount", label: "Amount", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Output",
        note: "final mask",
        controls: [
          { key: "coverage", label: "Coverage", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "contrast", label: "Contrast", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "gamma", label: "Gamma", min: 0.1, max: 4.0, step: 0.01, decimals: 2 },
          { key: "blur_radius", label: "Blur Radius", min: 0.0, max: 32.0, step: 0.1, decimals: 1 },
          { key: "invert_values", type: "toggle", label: "Invert Values", description: "Flip the final waterline mask after the band is built." },
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
    const view = createGradeMetric(metric.label, safeViewText(metric.get, node));
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
    const view = createGradeReadout(readout.label, safeViewText(readout.get, node));
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
    if (sectionSpec.help) {
      const note = document.createElement("div");
      note.className = "mkr-grade-note";
      note.textContent = sectionSpec.help;
      section.body.appendChild(note);
    }
    panel.appendChild(section.section);
  }

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => drawCanvas());
    observer.observe(canvas);
  }

  function drawCanvas() {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    try {
      config.graph.draw(ctx, width, height, node, config);
    } catch (error) {
      console.error(`[${EXTENSION_NAME}] preview draw failed for ${config.title}`, error);
      drawFallbackPreview(ctx, width, height, config.accent, config.graph.title || config.title);
    }
  }

  function refresh() {
    metricViews.forEach((metric) => metric.view.setValue(safeViewText(metric.get, node)));
    readoutViews.forEach((readout) => readout.view.setValue(safeViewText(readout.get, node)));
    controlViews.forEach(({ spec, control }) => {
      try {
        control.setValue(readControlValue(node, spec));
      } catch (error) {
        console.warn(`[${EXTENSION_NAME}] control refresh failed for ${spec.key}`, error);
      }
    });
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

  if (node.__mkrMaterialWeatherPanelInstalled) {
    node.__mkrMaterialWeatherRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  const { panel, refresh } = buildPanel(node, config);
  node.__mkrMaterialWeatherRefresh = refresh;
  node.__mkrMaterialWeatherPanelInstalled = true;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrMaterialWeatherRefreshHooksInstalled", refresh);
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
      if (TARGET_NAMES.has(String(node?.comfyClass || node?.type || "")) || TARGET_NAMES.has(String(node?.type || ""))) {
        prepareNode(node);
      }
    }
  },
});
