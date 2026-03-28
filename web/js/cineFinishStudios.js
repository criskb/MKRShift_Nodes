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
  getValue,
  installBundledSettingsAdapter,
  matchesNode,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.CineFinishStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-cine-finish-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function hueToRgb(hue, sat, value = 1) {
  const h = ((Number(hue) % 360) + 360) % 360;
  const s = clamp(Number(sat), 0, 1);
  const v = clamp(Number(value), 0, 1);
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return [r + m, g + m, b + m];
}

function rgbToCss(rgb, alpha = 1) {
  return `rgba(${Math.round(clamp(rgb[0], 0, 1) * 255)}, ${Math.round(clamp(rgb[1], 0, 1) * 255)}, ${Math.round(clamp(rgb[2], 0, 1) * 255)}, ${alpha})`;
}

function smoothstep(edge0, edge1, x) {
  if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - (2 * t));
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-cine-finish-select {
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

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.18)") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(18,21,26,0.98)");
  bg.addColorStop(1, "rgba(31,35,42,0.98)");
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

function drawFallbackPreview(ctx, width, height, accent, title = "Preview") {
  const frame = drawFrame(ctx, width, height, accent);
  ctx.fillStyle = "rgba(255,255,255,0.06)";
  ctx.fillRect(frame.x + 18, frame.y + 18, frame.w - 36, frame.h - 36);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.setLineDash([6, 6]);
  ctx.strokeRect(frame.x + 18, frame.y + 18, frame.w - 36, frame.h - 36);
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "600 13px sans-serif";
  ctx.fillText(title, frame.x + 28, frame.y + 42);
  ctx.fillStyle = "rgba(255,255,255,0.54)";
  ctx.font = "11px sans-serif";
  ctx.fillText("Preview ready. Controls remain active.", frame.x + 28, frame.y + 64);
}

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const select = document.createElement("select");
  select.className = "mkr-cine-finish-select";
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

function safeViewText(getter, node, fallback = "--") {
  try {
    const value = getter?.(node);
    return value ?? fallback;
  } catch (error) {
    console.warn(`[${EXTENSION_NAME}] view getter failed`, error);
    return fallback;
  }
}

function hasInputLink(node, name) {
  const input = Array.isArray(node?.inputs)
    ? node.inputs.find((item) => String(item?.name || "") === String(name))
    : null;
  return !!input?.link;
}

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

function drawFilmPrintPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,189,118,0.20)");
  const area = { x: frame.x + 22, y: frame.y + 22, w: frame.w - 44, h: frame.h - 44 };
  const stock = String(getValue(node, "stock", "kodak_2383"));
  const density = getNumber(node, "density", 0);
  const contrast = getNumber(node, "contrast", 1);
  const saturation = getNumber(node, "saturation", 1);
  const warmth = getNumber(node, "warmth", 0);
  const toe = getNumber(node, "toe", 0.2);
  const shoulder = getNumber(node, "shoulder", 0.22);
  const fade = getNumber(node, "fade", 0);

  const base = ctx.createLinearGradient(area.x, area.y, area.x, area.y + area.h);
  base.addColorStop(0, "rgba(22,18,14,0.98)");
  base.addColorStop(1, "rgba(34,28,22,0.98)");
  ctx.fillStyle = base;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const tint = stock === "fuji_3513"
    ? ["rgba(100,255,198,0.08)", "rgba(255,212,108,0.10)"]
    : stock === "bleach_bypass"
      ? ["rgba(186,198,222,0.06)", "rgba(255,255,255,0.04)"]
      : stock === "silver_fade"
        ? ["rgba(138,154,194,0.08)", "rgba(228,210,180,0.09)"]
        : ["rgba(255,120,82,0.08)", "rgba(255,206,124,0.10)"];
  const wash = ctx.createLinearGradient(area.x, area.y, area.x + area.w, area.y + area.h);
  wash.addColorStop(0, tint[0]);
  wash.addColorStop(1, tint[1]);
  ctx.fillStyle = wash;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const rampY = area.y + 20;
  const rampH = 34;
  const ramp = ctx.createLinearGradient(area.x + 14, 0, area.x + area.w - 14, 0);
  ramp.addColorStop(0, `rgba(20,20,24,${0.92 - fade * 0.3})`);
  ramp.addColorStop(0.5, rgbToCss(hueToRgb(34 + warmth * 28, clamp(0.08 + saturation * 0.12, 0, 1), clamp(0.52 + density * 0.12, 0.2, 1)), 0.88));
  ramp.addColorStop(1, rgbToCss(hueToRgb(48 + warmth * 22, clamp(0.14 + saturation * 0.22, 0, 1), clamp(0.90 + density * 0.08, 0.2, 1)), 0.92));
  ctx.fillStyle = ramp;
  ctx.fillRect(area.x + 14, rampY, area.w - 28, rampH);

  const plot = {
    x: area.x + 18,
    y: rampY + rampH + 22,
    w: area.w - 36,
    h: area.h - (rampH + 58),
  };
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  for (let i = 0; i <= 4; i += 1) {
    const x = plot.x + ((plot.w * i) / 4);
    const y = plot.y + ((plot.h * i) / 4);
    ctx.beginPath();
    ctx.moveTo(x, plot.y);
    ctx.lineTo(x, plot.y + plot.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(plot.x, y);
    ctx.lineTo(plot.x + plot.w, y);
    ctx.stroke();
  }

  const curve = (t) => {
    const toeLift = t / Math.max(0.05, t + (toe * (1 - t)));
    const contrasted = clamp(((toeLift - 0.5) * contrast) + 0.5, 0, 1);
    const over = Math.max(contrasted - 0.5, 0);
    const comp = over / (1 + shoulder * 8 * over / 0.5);
    return clamp(contrasted - over + comp + fade * 0.04, 0, 1);
  };
  ctx.beginPath();
  for (let i = 0; i <= 120; i += 1) {
    const t = i / 120;
    const x = plot.x + plot.w * t;
    const y = plot.y + ((1 - curve(t)) * plot.h);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = "rgba(255,213,144,0.92)";
  ctx.lineWidth = 2.4;
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "700 14px sans-serif";
  ctx.fillText(stock.replaceAll("_", " "), area.x + 14, area.y + area.h - 12);
}

function drawHighlightRollOffPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(176,208,255,0.18)");
  const area = { x: frame.x + 20, y: frame.y + 20, w: frame.w - 40, h: frame.h - 40 };
  const pivot = clamp(getNumber(node, "pivot", 0.68), 0, 1);
  const softness = clamp(getNumber(node, "softness", 0.10), 0, 0.5);
  const amount = clamp(getNumber(node, "amount", 0.65), 0, 1);
  const preserve = getBoolean(node, "preserve_color", true);

  ctx.fillStyle = "rgba(10,13,18,0.98)";
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const band = ctx.createLinearGradient(area.x, 0, area.x + area.w, 0);
  band.addColorStop(0, "rgba(42,52,64,0.96)");
  band.addColorStop(pivot, "rgba(250,250,250,0.96)");
  band.addColorStop(1, preserve ? "rgba(142,188,255,0.90)" : "rgba(230,230,230,0.90)");
  ctx.fillStyle = band;
  ctx.fillRect(area.x + 16, area.y + 18, area.w - 32, 28);

  const plot = { x: area.x + 18, y: area.y + 66, w: area.w - 36, h: area.h - 84 };
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  for (let i = 0; i <= 4; i += 1) {
    const x = plot.x + ((plot.w * i) / 4);
    const y = plot.y + ((plot.h * i) / 4);
    ctx.beginPath();
    ctx.moveTo(x, plot.y);
    ctx.lineTo(x, plot.y + plot.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(plot.x, y);
    ctx.lineTo(plot.x + plot.w, y);
    ctx.stroke();
  }

  const roll = (t) => {
    const hi = smoothstep(pivot - softness, pivot + softness, t);
    const over = Math.max(t - pivot, 0);
    const comp = over / (1 + amount * 8 * over / Math.max(1e-3, 1 - pivot));
    const target = t - over + comp;
    return clamp((t * (1 - hi)) + (target * hi), 0, 1);
  };

  ctx.beginPath();
  for (let i = 0; i <= 120; i += 1) {
    const t = i / 120;
    const x = plot.x + plot.w * t;
    const y = plot.y + ((1 - t) * plot.h);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = "rgba(255,255,255,0.20)";
  ctx.lineWidth = 1.2;
  ctx.stroke();

  ctx.beginPath();
  for (let i = 0; i <= 120; i += 1) {
    const t = i / 120;
    const x = plot.x + plot.w * t;
    const y = plot.y + ((1 - roll(t)) * plot.h);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = preserve ? "rgba(138,198,255,0.94)" : "rgba(255,233,188,0.94)";
  ctx.lineWidth = 2.6;
  ctx.stroke();
}

function drawSkinToneProtectPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,190,154,0.20)");
  const area = { x: frame.x + 20, y: frame.y + 20, w: frame.w - 40, h: frame.h - 40 };
  const hueCenter = clamp(getNumber(node, "hue_center", 28), 0, 360);
  const hueWidth = clamp(getNumber(node, "hue_width", 40), 1, 180);
  const satMin = clamp(getNumber(node, "sat_min", 0.1), 0, 1);
  const satMax = clamp(getNumber(node, "sat_max", 0.8), 0, 1);
  const valMin = clamp(getNumber(node, "val_min", 0.08), 0, 1);
  const valMax = clamp(getNumber(node, "val_max", 1.0), 0, 1);
  const softness = clamp(getNumber(node, "softness", 16), 0, 120);
  const warmth = getNumber(node, "warmth_balance", 0);
  const hasReference = hasInputLink(node, "reference_image");

  const bandX = area.x + 16;
  const bandY = area.y + 16;
  const bandW = area.w - 32;
  const bandH = 28;
  const hueGrad = ctx.createLinearGradient(bandX, 0, bandX + bandW, 0);
  for (let step = 0; step <= 12; step += 1) {
    const t = step / 12;
    hueGrad.addColorStop(t, rgbToCss(hueToRgb(t * 360, 0.85, 0.95)));
  }
  ctx.fillStyle = hueGrad;
  ctx.fillRect(bandX, bandY, bandW, bandH);
  const centerX = bandX + ((hueCenter / 360) * bandW);
  const widthPx = (hueWidth / 360) * bandW;
  ctx.strokeStyle = "rgba(255,255,255,0.95)";
  ctx.lineWidth = 2;
  ctx.strokeRect(centerX - widthPx * 0.5, bandY - 3, widthPx, bandH + 6);

  const plot = { x: area.x + 16, y: area.y + 64, w: area.w - 32, h: area.h - 82 };
  const sv = ctx.createLinearGradient(plot.x, plot.y, plot.x + plot.w, plot.y);
  sv.addColorStop(0, "rgba(28,28,30,1)");
  sv.addColorStop(1, rgbToCss(hueToRgb(hueCenter + warmth * 24, 0.72, 0.94)));
  ctx.fillStyle = sv;
  ctx.fillRect(plot.x, plot.y, plot.w, plot.h);
  const valueGrad = ctx.createLinearGradient(plot.x, plot.y + plot.h, plot.x, plot.y);
  valueGrad.addColorStop(0, "rgba(0,0,0,1)");
  valueGrad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = valueGrad;
  ctx.fillRect(plot.x, plot.y, plot.w, plot.h);

  const selX = plot.x + plot.w * satMin;
  const selY = plot.y + plot.h * (1 - valMax);
  const selW = plot.w * Math.max(0.02, satMax - satMin);
  const selH = plot.h * Math.max(0.02, valMax - valMin);
  ctx.strokeStyle = "rgba(255,245,220,0.96)";
  ctx.lineWidth = 2;
  ctx.strokeRect(selX, selY, selW, selH);
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  ctx.font = "700 12px sans-serif";
  ctx.fillText(hasReference ? "Reference restore" : "Naturalize corridor", plot.x + 8, plot.y + 18);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "rgba(240,244,248,0.60)";
  ctx.fillText(`Softness ${formatNumber(softness, 1)}°`, plot.x + plot.w - 82, plot.y + 18);
}

const NODE_CONFIGS = {
  x1FilmPrint: {
    panelName: "mkr_cine_film_print_studio",
    title: "Film Print Studio",
    subtitle: "Shape print-stock density, tone curve, fade, and warmth from one authored finishing panel instead of a raw list of lab controls.",
    accent: "#ffbd76",
    size: [780, 920],
    defaults: {
      stock: "kodak_2383",
      density: 0.0,
      contrast: 1.0,
      saturation: 1.0,
      warmth: 0.0,
      toe: 0.20,
      shoulder: 0.22,
      fade: 0.0,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      density: { min: -1, max: 1 },
      contrast: { min: 0.3, max: 2 },
      saturation: { min: 0, max: 2 },
      warmth: { min: -1, max: 1 },
      toe: { min: 0, max: 1 },
      shoulder: { min: 0, max: 1 },
      fade: { min: 0, max: 0.6 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["stock", "density", "contrast", "saturation", "warmth", "toe", "shoulder", "fade", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Stock", get: (node) => String(getValue(node, "stock", "kodak_2383")).replaceAll("_", " ") },
      { label: "Density", get: (node) => `${formatSigned(getNumber(node, "density", 0), 2)} ev` },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Kodak", tone: "accent", values: { stock: "kodak_2383", density: 0.05, contrast: 1.0, saturation: 1.0, warmth: 0.08, toe: 0.20, shoulder: 0.24, fade: 0.02 } },
      { label: "Fuji", values: { stock: "fuji_3513", density: 0.0, contrast: 0.96, saturation: 0.96, warmth: -0.06, toe: 0.22, shoulder: 0.18, fade: 0.03 } },
      { label: "Bleach", values: { stock: "bleach_bypass", density: 0.12, contrast: 1.18, saturation: 0.64, warmth: -0.02, toe: 0.14, shoulder: 0.30, fade: 0.00 } },
    ],
    graph: {
      title: "Print Response",
      note: "stock / curve",
      height: 228,
      draw: drawFilmPrintPreview,
      readouts: [
        { label: "Contrast", get: (node) => formatNumber(getNumber(node, "contrast", 1.0)) },
        { label: "Warmth", get: (node) => formatSigned(getNumber(node, "warmth", 0), 2) },
        { label: "Fade", get: (node) => formatNumber(getNumber(node, "fade", 0)) },
      ],
      help: "Stock sets the base print character, then density, toe, shoulder, and fade let you push the lab response without leaving the node.",
    },
    sections: [
      {
        title: "Stock Body",
        note: "stock + tone",
        controls: [
          { type: "select", key: "stock", label: "Stock", options: [{ label: "kodak_2383", value: "kodak_2383" }, { label: "fuji_3513", value: "fuji_3513" }, { label: "bleach_bypass", value: "bleach_bypass" }, { label: "silver_fade", value: "silver_fade" }, { label: "neutral_clean", value: "neutral_clean" }] },
          { key: "density", label: "Density", min: -1, max: 1, step: 0.01 },
          { key: "contrast", label: "Contrast", min: 0.3, max: 2, step: 0.01 },
          { key: "saturation", label: "Saturation", min: 0, max: 2, step: 0.01 },
        ],
      },
      {
        title: "Curve Finish",
        note: "lab trim",
        controls: [
          { key: "warmth", label: "Warmth", min: -1, max: 1, step: 0.01 },
          { key: "toe", label: "Toe", min: 0, max: 1, step: 0.01 },
          { key: "shoulder", label: "Shoulder", min: 0, max: 1, step: 0.01 },
          { key: "fade", label: "Fade", min: 0, max: 0.6, step: 0.01 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the print emulation blends in." },
        ],
      },
    ],
  },
  x1HighlightRollOff: {
    panelName: "mkr_cine_highlight_rolloff_studio",
    title: "Highlight Roll-Off Studio",
    subtitle: "Compress hot values with a visible shoulder curve instead of nudging pivot and softness without seeing the highlight handoff.",
    accent: "#9ec8ff",
    size: [760, 720],
    defaults: {
      pivot: 0.68,
      softness: 0.10,
      amount: 0.65,
      preserve_color: true,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      pivot: { min: 0, max: 1 },
      softness: { min: 0, max: 0.5 },
      amount: { min: 0, max: 1 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["preserve_color", "invert_mask"],
    legacyNames: ["pivot", "softness", "amount", "preserve_color", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Pivot", get: (node) => formatNumber(getNumber(node, "pivot", 0.68)) },
      { label: "Amount", get: (node) => formatNumber(getNumber(node, "amount", 0.65)) },
      { label: "Color", get: (node) => getBoolean(node, "preserve_color", true) ? "Preserve" : "Luma" },
    ],
    presets: [
      { label: "Soft Clip", tone: "accent", values: { pivot: 0.74, softness: 0.08, amount: 0.46, preserve_color: true, mix: 1.0 } },
      { label: "Film Shoulder", values: { pivot: 0.66, softness: 0.12, amount: 0.74, preserve_color: true, mix: 1.0 } },
      { label: "Neutral Rescue", values: { pivot: 0.62, softness: 0.16, amount: 0.58, preserve_color: false, mix: 0.88 } },
    ],
    graph: {
      title: "Rolloff Curve",
      note: "shoulder response",
      height: 206,
      draw: drawHighlightRollOffPreview,
      readouts: [
        { label: "Softness", get: (node) => formatNumber(getNumber(node, "softness", 0.10), 3) },
        { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
      ],
      help: "Pivot marks where compression starts, softness feathers that zone, and amount controls how hard the shoulder leans on hot highlights.",
    },
    sections: [
      {
        title: "Highlight Compression",
        note: "curve",
        controls: [
          { key: "pivot", label: "Pivot", min: 0, max: 1, step: 0.01 },
          { key: "softness", label: "Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { key: "amount", label: "Amount", min: 0, max: 1, step: 0.01 },
          { type: "toggle", key: "preserve_color", label: "Preserve Color", description: "Scale color with the highlight luma instead of flattening channels directly." },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the highlight rolloff blends in." },
        ],
      },
    ],
  },
  x1SkinToneProtect: {
    panelName: "mkr_cine_skin_tone_protect_studio",
    title: "Skin Tone Protect Studio",
    subtitle: "Define the skin corridor, keep saturation in bounds, and optionally restore from a reference without leaving the node surface.",
    accent: "#ffba9a",
    size: [780, 960],
    defaults: {
      mode: "auto",
      protect_strength: 0.70,
      hue_center: 28.0,
      hue_width: 40.0,
      sat_min: 0.10,
      sat_max: 0.80,
      val_min: 0.08,
      val_max: 1.00,
      softness: 16.0,
      saturation_limit: 0.75,
      warmth_balance: 0.0,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      protect_strength: { min: 0, max: 1 },
      hue_center: { min: 0, max: 360 },
      hue_width: { min: 1, max: 180 },
      sat_min: { min: 0, max: 1 },
      sat_max: { min: 0, max: 1 },
      val_min: { min: 0, max: 1 },
      val_max: { min: 0, max: 1 },
      softness: { min: 0, max: 120 },
      saturation_limit: { min: 0.2, max: 1 },
      warmth_balance: { min: -1, max: 1 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["mode", "protect_strength", "hue_center", "hue_width", "sat_min", "sat_max", "val_min", "val_max", "softness", "saturation_limit", "warmth_balance", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Mode", get: (node) => String(getValue(node, "mode", "auto")) },
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "protect_strength", 0.70)) },
      { label: "Reference", get: (node) => hasInputLink(node, "reference_image") ? "Live" : "Off" },
    ],
    presets: [
      { label: "Natural", tone: "accent", values: { mode: "naturalize", protect_strength: 0.68, hue_center: 28, hue_width: 38, sat_min: 0.10, sat_max: 0.78, softness: 16, saturation_limit: 0.72, warmth_balance: 0.0 } },
      { label: "Warm Clean", values: { mode: "naturalize", protect_strength: 0.74, hue_center: 30, hue_width: 42, sat_min: 0.08, sat_max: 0.82, softness: 20, saturation_limit: 0.76, warmth_balance: 0.14 } },
      { label: "Reference", values: { mode: "reference_restore", protect_strength: 0.84, hue_center: 28, hue_width: 38, sat_min: 0.10, sat_max: 0.80, softness: 18, saturation_limit: 0.74, warmth_balance: 0.0 } },
    ],
    graph: {
      title: "Skin Corridor",
      note: "hue / sat / value",
      height: 232,
      draw: drawSkinToneProtectPreview,
      readouts: [
        { label: "Hue", get: (node) => `${Math.round(getNumber(node, "hue_center", 28))}°` },
        { label: "Width", get: (node) => `${Math.round(getNumber(node, "hue_width", 40))}°` },
        { label: "Warmth", get: (node) => formatSigned(getNumber(node, "warmth_balance", 0), 2) },
      ],
      help: "The hue band selects candidate skin tones, then the sat/value box trims the corridor. Plug a reference only when you want restore behavior.",
    },
    sections: [
      {
        title: "Selection Corridor",
        note: "hue gate",
        controls: [
          { type: "select", key: "mode", label: "Mode", options: [{ label: "auto", value: "auto" }, { label: "naturalize", value: "naturalize" }, { label: "reference_restore", value: "reference_restore" }] },
          { key: "protect_strength", label: "Protect Strength", min: 0, max: 1, step: 0.01 },
          { key: "hue_center", label: "Hue Center", min: 0, max: 360, step: 0.5, decimals: 1 },
          { key: "hue_width", label: "Hue Width", min: 1, max: 180, step: 0.5, decimals: 1 },
          { key: "softness", label: "Softness", min: 0, max: 120, step: 0.5, decimals: 1 },
        ],
      },
      {
        title: "Sat / Value Gate",
        note: "range trim",
        controls: [
          { key: "sat_min", label: "Sat Min", min: 0, max: 1, step: 0.01 },
          { key: "sat_max", label: "Sat Max", min: 0, max: 1, step: 0.01 },
          { key: "val_min", label: "Val Min", min: 0, max: 1, step: 0.01 },
          { key: "val_max", label: "Val Max", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Protection Response",
        note: "limit / warmth",
        controls: [
          { key: "saturation_limit", label: "Sat Limit", min: 0.2, max: 1, step: 0.01 },
          { key: "warmth_balance", label: "Warmth Balance", min: -1, max: 1, step: 0.01 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the skin protection blends in." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

function buildPanel(node, config) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT CINE",
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
  canvas.style.height = `${config.graph.height || 220}px`;
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
  const config = Object.entries(NODE_CONFIGS).find(([name]) => matchesNode(node, name))?.[1];
  if (!config) return;

  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: config.defaults,
    numericSpecs: config.numericSpecs,
    booleanKeys: config.booleanKeys,
    legacyNames: config.legacyNames,
  });

  if (node.__mkrCineFinishPanelInstalled) {
    node.__mkrCineFinishRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrCineFinishPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrCineFinishRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrCineFinishRefreshHooksInstalled", refresh);
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
      if ([...TARGET_NAMES].some((name) => matchesNode(node, name))) {
        prepareNode(node);
      }
    }
  },
});
