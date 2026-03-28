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

const EXTENSION_NAME = "MKRShift.CineMotionStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-cine-motion-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-cine-motion-select {
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
  select.className = "mkr-cine-motion-select";
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

function drawGateWeavePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(166,220,255,0.18)");
  const area = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 36, h: frame.h - 36 };
  const sx = clamp(getNumber(node, "shift_x_px", 2), 0, 64);
  const sy = clamp(getNumber(node, "shift_y_px", 1.4), 0, 64);
  const rot = getNumber(node, "rotation_deg", 0.35);
  const scaleJitter = clamp(getNumber(node, "scale_jitter", 0.01), 0, 0.2);
  const mode = String(getValue(node, "jitter_mode", "gaussian"));

  ctx.fillStyle = "rgba(10,13,18,0.98)";
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const filmRect = { x: area.x + 34, y: area.y + 22, w: area.w - 68, h: area.h - 44 };
  ctx.fillStyle = "rgba(28,32,38,1)";
  ctx.fillRect(filmRect.x, filmRect.y, filmRect.w, filmRect.h);

  const offsetX = (sx / 64) * 18;
  const offsetY = (sy / 64) * 12;
  const theta = (rot / 8) * 0.12;
  const scale = 1 + scaleJitter * 1.6;
  const cx = filmRect.x + filmRect.w * 0.5;
  const cy = filmRect.y + filmRect.h * 0.5;

  ctx.save();
  ctx.translate(cx + offsetX, cy - offsetY);
  ctx.rotate(theta);
  ctx.scale(scale, scale);
  const gx = -filmRect.w * 0.5;
  const gy = -filmRect.h * 0.5;
  const grad = ctx.createLinearGradient(gx, gy, gx + filmRect.w, gy + filmRect.h);
  grad.addColorStop(0, "rgba(74,96,130,0.28)");
  grad.addColorStop(0.5, "rgba(204,180,112,0.14)");
  grad.addColorStop(1, "rgba(72,112,138,0.20)");
  ctx.fillStyle = grad;
  ctx.fillRect(gx, gy, filmRect.w, filmRect.h);

  ctx.strokeStyle = "rgba(240,244,248,0.72)";
  ctx.lineWidth = 2;
  ctx.strokeRect(gx + 14, gy + 14, filmRect.w - 28, filmRect.h - 28);

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  for (let i = 0; i <= 5; i += 1) {
    const x = gx + (filmRect.w * i / 5);
    ctx.beginPath();
    ctx.moveTo(x, gy + 14);
    ctx.lineTo(x, gy + filmRect.h - 14);
    ctx.stroke();
  }
  ctx.restore();

  ctx.fillStyle = "rgba(255,255,255,0.85)";
  ctx.font = "700 13px sans-serif";
  ctx.fillText(mode === "uniform" ? "Uniform jitter" : "Gaussian jitter", area.x + 16, area.y + 18);
}

function drawFilmDamagePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,195,116,0.18)");
  const area = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 36, h: frame.h - 36 };
  const dust = clamp(getNumber(node, "dust_amount", 0.25), 0, 1);
  const scratches = clamp(getNumber(node, "scratch_amount", 0.22), 0, 1);
  const burn = clamp(getNumber(node, "burn_amount", 0.10), 0, 1);
  const flicker = clamp(getNumber(node, "flicker_amount", 0.08), 0, 0.5);
  const seed = Math.round(getNumber(node, "seed", 1977));

  ctx.fillStyle = `rgba(${Math.round(24 + flicker * 80)}, ${Math.round(22 + flicker * 70)}, ${Math.round(16 + flicker * 40)}, 0.98)`;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const rngCount = Math.round(20 + dust * 90);
  ctx.fillStyle = "rgba(255,250,238,0.34)";
  for (let i = 0; i < rngCount; i += 1) {
    const rx = area.x + ((i * 47 + seed) % Math.max(1, Math.floor(area.w - 3)));
    const ry = area.y + ((i * 61 + seed * 3) % Math.max(1, Math.floor(area.h - 3)));
    const rr = 1 + ((i + seed) % 3) * dust;
    ctx.beginPath();
    ctx.arc(rx, ry, rr, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = "rgba(28,18,12,0.62)";
  ctx.lineWidth = 1.5 + scratches * 2.5;
  const lines = Math.round(2 + scratches * 10);
  for (let i = 0; i < lines; i += 1) {
    const x = area.x + 20 + (((i * 83) + seed) % Math.max(1, Math.floor(area.w - 40)));
    ctx.beginPath();
    ctx.moveTo(x, area.y + 10);
    ctx.lineTo(x + Math.sin(i + seed) * 14, area.y + area.h - 10);
    ctx.stroke();
  }

  if (burn > 0.01) {
    const burnGrad = ctx.createRadialGradient(area.x + area.w, area.y, 10, area.x + area.w, area.y, area.w * 0.65);
    burnGrad.addColorStop(0, `rgba(255,188,96,${0.12 + burn * 0.25})`);
    burnGrad.addColorStop(0.5, `rgba(176,62,14,${0.08 + burn * 0.16})`);
    burnGrad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = burnGrad;
    ctx.fillRect(area.x, area.y, area.w, area.h);
  }
}

function drawLensBreathingPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(159,225,255,0.18)");
  const area = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 36, h: frame.h - 36 };
  const breath = getNumber(node, "breath_amount", 0.08);
  const edge = clamp(getNumber(node, "edge_response", 0.72), 0, 1);
  const aniso = getNumber(node, "anisotropy", 0);
  const centerX = area.x + area.w * clamp(getNumber(node, "center_x", 0.5), 0, 1);
  const centerY = area.y + area.h * clamp(getNumber(node, "center_y", 0.5), 0, 1);
  const chroma = clamp(getNumber(node, "chroma", 0.16), 0, 1);

  ctx.fillStyle = "rgba(9,12,17,0.98)";
  ctx.fillRect(area.x, area.y, area.w, area.h);
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  for (let i = 0; i <= 6; i += 1) {
    const inset = i * 18;
    const rx = area.x + inset;
    const ry = area.y + inset * (1 - aniso * 0.18);
    const rw = area.w - inset * 2;
    const rh = area.h - inset * 2 * (1 - aniso * 0.18);
    if (rw <= 0 || rh <= 0) break;
    ctx.beginPath();
    ctx.ellipse(centerX, centerY, rw * 0.5 * (1 + breath * edge * 0.8), rh * 0.5 * (1 - breath * aniso * 0.35), 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.strokeStyle = `rgba(255,102,102,${0.12 + chroma * 0.18})`;
  ctx.beginPath();
  ctx.ellipse(centerX, centerY, area.w * 0.34 * (1 + breath * 0.6), area.h * 0.26, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = `rgba(102,180,255,${0.12 + chroma * 0.18})`;
  ctx.beginPath();
  ctx.ellipse(centerX, centerY, area.w * 0.30 * (1 - breath * 0.5), area.h * 0.22, 0, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.font = "700 13px sans-serif";
  ctx.fillText(hasInputLink(node, "depth_map") ? "Depth-weighted breathing" : "Uniform breathing", area.x + 14, area.y + 18);
}

function drawShockwavePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(124,197,255,0.18)");
  const area = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 36, h: frame.h - 36 };
  const cx = area.x + area.w * clamp(getNumber(node, "center_x", 0.5), 0, 1);
  const cy = area.y + area.h * clamp(getNumber(node, "center_y", 0.5), 0, 1);
  const radius = clamp(getNumber(node, "radius", 0.22), 0, 1.5);
  const widthBand = clamp(getNumber(node, "width", 0.08), 0.001, 0.75);
  const amp = getNumber(node, "amplitude_px", 14);
  const hardness = clamp(getNumber(node, "ring_hardness", 1.5), 0.5, 6);
  const chroma = clamp(getNumber(node, "chroma_split_px", 1.2), 0, 16);

  ctx.fillStyle = "rgba(10,12,18,0.98)";
  ctx.fillRect(area.x, area.y, area.w, area.h);
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  for (let i = 0; i <= 4; i += 1) {
    const x = area.x + ((area.w * i) / 4);
    const y = area.y + ((area.h * i) / 4);
    ctx.beginPath();
    ctx.moveTo(x, area.y);
    ctx.lineTo(x, area.y + area.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(area.x, y);
    ctx.lineTo(area.x + area.w, y);
    ctx.stroke();
  }

  const rPx = Math.min(area.w, area.h) * 0.42 * (radius / 0.5);
  const bandPx = Math.max(4, Math.min(area.w, area.h) * 0.18 * (widthBand / 0.1));
  ctx.lineWidth = bandPx;
  ctx.strokeStyle = `rgba(145,207,255,${0.18 + Math.min(Math.abs(amp) / 128, 1) * 0.28})`;
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(12, rPx), 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 2 + hardness;
  ctx.strokeStyle = `rgba(255,255,255,${0.38 + chroma / 40})`;
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(12, rPx), 0, Math.PI * 2);
  ctx.stroke();
}

const NODE_CONFIGS = {
  x1GateWeave: {
    panelName: "mkr_cine_gate_weave_studio",
    title: "Gate Weave Studio",
    subtitle: "Shape analog frame jitter with visible transport drift instead of treating weave like a stack of disconnected offsets.",
    accent: "#a6dcff",
    size: [760, 760],
    defaults: {
      shift_x_px: 2.0,
      shift_y_px: 1.4,
      rotation_deg: 0.35,
      scale_jitter: 0.010,
      jitter_mode: "gaussian",
      seed: 2048,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      shift_x_px: { min: 0, max: 64 },
      shift_y_px: { min: 0, max: 64 },
      rotation_deg: { min: 0, max: 8 },
      scale_jitter: { min: 0, max: 0.2 },
      seed: { min: 0, max: 99999999, integer: true },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["shift_x_px", "shift_y_px", "rotation_deg", "scale_jitter", "jitter_mode", "seed", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Shift X", get: (node) => `${formatNumber(getNumber(node, "shift_x_px", 2), 1)} px` },
      { label: "Rotation", get: (node) => `${formatNumber(getNumber(node, "rotation_deg", 0.35), 2)}°` },
      { label: "Mode", get: (node) => String(getValue(node, "jitter_mode", "gaussian")) },
    ],
    presets: [
      { label: "Subtle", tone: "accent", values: { shift_x_px: 1.2, shift_y_px: 0.8, rotation_deg: 0.18, scale_jitter: 0.006, jitter_mode: "gaussian" } },
      { label: "16mm", values: { shift_x_px: 2.4, shift_y_px: 1.8, rotation_deg: 0.44, scale_jitter: 0.012, jitter_mode: "gaussian" } },
      { label: "Wild", values: { shift_x_px: 5.0, shift_y_px: 3.4, rotation_deg: 1.2, scale_jitter: 0.028, jitter_mode: "uniform" } },
    ],
    graph: {
      title: "Transport Preview",
      note: "frame drift",
      height: 214,
      draw: drawGateWeavePreview,
      readouts: [
        { label: "Shift Y", get: (node) => `${formatNumber(getNumber(node, "shift_y_px", 1.4), 1)} px` },
        { label: "Scale", get: (node) => formatNumber(getNumber(node, "scale_jitter", 0.010), 3) },
      ],
      help: "Use gaussian for more natural organic weave. Uniform works better when you want obvious projector instability.",
    },
    sections: [
      {
        title: "Transport Drift",
        note: "frame motion",
        controls: [
          { key: "shift_x_px", label: "Shift X", min: 0, max: 64, step: 0.1, decimals: 1 },
          { key: "shift_y_px", label: "Shift Y", min: 0, max: 64, step: 0.1, decimals: 1 },
          { key: "rotation_deg", label: "Rotation", min: 0, max: 8, step: 0.01, decimals: 2 },
          { key: "scale_jitter", label: "Scale Jitter", min: 0, max: 0.2, step: 0.001, decimals: 3 },
          { type: "select", key: "jitter_mode", label: "Jitter Mode", options: [{ label: "gaussian", value: "gaussian" }, { label: "uniform", value: "uniform" }] },
        ],
      },
      {
        title: "Finish",
        note: "blend",
        controls: [
          { key: "seed", label: "Seed", min: 0, max: 99999999, step: 1, decimals: 0 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before weave is blended." },
        ],
      },
    ],
  },
  x1FilmDamage: {
    panelName: "mkr_cine_film_damage_studio",
    title: "Film Damage Studio",
    subtitle: "Balance dust, scratches, burn, and flicker from one authored distress panel instead of pushing isolated damage sliders.",
    accent: "#ffc374",
    size: [760, 800],
    defaults: {
      dust_amount: 0.25,
      scratch_amount: 0.22,
      burn_amount: 0.10,
      flicker_amount: 0.08,
      seed: 1977,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      dust_amount: { min: 0, max: 1 },
      scratch_amount: { min: 0, max: 1 },
      burn_amount: { min: 0, max: 1 },
      flicker_amount: { min: 0, max: 0.5 },
      seed: { min: 0, max: 99999999, integer: true },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["dust_amount", "scratch_amount", "burn_amount", "flicker_amount", "seed", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Dust", get: (node) => formatNumber(getNumber(node, "dust_amount", 0.25)) },
      { label: "Scratches", get: (node) => formatNumber(getNumber(node, "scratch_amount", 0.22)) },
      { label: "Burn", get: (node) => formatNumber(getNumber(node, "burn_amount", 0.10)) },
    ],
    presets: [
      { label: "Archive", tone: "accent", values: { dust_amount: 0.18, scratch_amount: 0.14, burn_amount: 0.04, flicker_amount: 0.05 } },
      { label: "Drive-In", values: { dust_amount: 0.34, scratch_amount: 0.28, burn_amount: 0.12, flicker_amount: 0.10 } },
      { label: "Destroyed", values: { dust_amount: 0.72, scratch_amount: 0.66, burn_amount: 0.38, flicker_amount: 0.22 } },
    ],
    graph: {
      title: "Damage Sketch",
      note: "dust / scratches / burn",
      height: 220,
      draw: drawFilmDamagePreview,
      readouts: [
        { label: "Flicker", get: (node) => formatNumber(getNumber(node, "flicker_amount", 0.08), 3) },
        { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
      ],
      help: "Burn adds hot edge damage, scratches cut into contrast, and flicker changes the exposure character between frames.",
    },
    sections: [
      {
        title: "Damage Mix",
        note: "elements",
        controls: [
          { key: "dust_amount", label: "Dust", min: 0, max: 1, step: 0.01 },
          { key: "scratch_amount", label: "Scratches", min: 0, max: 1, step: 0.01 },
          { key: "burn_amount", label: "Burn", min: 0, max: 1, step: 0.01 },
          { key: "flicker_amount", label: "Flicker", min: 0, max: 0.5, step: 0.005, decimals: 3 },
        ],
      },
      {
        title: "Finish",
        note: "seed / blend",
        controls: [
          { key: "seed", label: "Seed", min: 0, max: 99999999, step: 1, decimals: 0 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the film damage blends in." },
        ],
      },
    ],
  },
  x1LensBreathing: {
    panelName: "mkr_cine_lens_breathing_studio",
    title: "Lens Breathing Studio",
    subtitle: "Author radial lens breathing with center, anisotropy, chroma fringe, and optional depth weighting in one optics-focused panel.",
    accent: "#9fe1ff",
    size: [760, 860],
    defaults: {
      breath_amount: 0.08,
      edge_response: 0.72,
      anisotropy: 0.0,
      center_x: 0.5,
      center_y: 0.5,
      chroma: 0.16,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      breath_amount: { min: -0.35, max: 0.35 },
      edge_response: { min: 0, max: 1 },
      anisotropy: { min: -1, max: 1 },
      center_x: { min: 0, max: 1 },
      center_y: { min: 0, max: 1 },
      chroma: { min: 0, max: 1 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["breath_amount", "edge_response", "anisotropy", "center_x", "center_y", "chroma", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Breath", get: (node) => formatSigned(getNumber(node, "breath_amount", 0.08), 3) },
      { label: "Edge", get: (node) => formatNumber(getNumber(node, "edge_response", 0.72)) },
      { label: "Depth", get: (node) => hasInputLink(node, "depth_map") ? "Live" : "Off" },
    ],
    presets: [
      { label: "Subtle", tone: "accent", values: { breath_amount: 0.05, edge_response: 0.58, anisotropy: 0.0, chroma: 0.08 } },
      { label: "Focus Pull", values: { breath_amount: 0.14, edge_response: 0.78, anisotropy: 0.12, chroma: 0.18 } },
      { label: "Reverse", values: { breath_amount: -0.12, edge_response: 0.82, anisotropy: -0.16, chroma: 0.22 } },
    ],
    graph: {
      title: "Breathing Field",
      note: "radial response",
      height: 220,
      draw: drawLensBreathingPreview,
      readouts: [
        { label: "Aniso", get: (node) => formatSigned(getNumber(node, "anisotropy", 0), 2) },
        { label: "Chroma", get: (node) => formatNumber(getNumber(node, "chroma", 0.16)) },
      ],
      help: "Positive breath expands toward the edges, negative breath pulls inward. Depth input biases the effect where focus change is stronger.",
    },
    sections: [
      {
        title: "Breathing Core",
        note: "radial response",
        controls: [
          { key: "breath_amount", label: "Breath Amount", min: -0.35, max: 0.35, step: 0.001, decimals: 3 },
          { key: "edge_response", label: "Edge Response", min: 0, max: 1, step: 0.01 },
          { key: "anisotropy", label: "Anisotropy", min: -1, max: 1, step: 0.01 },
          { key: "chroma", label: "Chroma", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Lens Center",
        note: "origin",
        controls: [
          { key: "center_x", label: "Center X", min: 0, max: 1, step: 0.001, decimals: 3 },
          { key: "center_y", label: "Center Y", min: 0, max: 1, step: 0.001, decimals: 3 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the breathing distortion blends in." },
        ],
      },
    ],
  },
  x1ShockwaveDistort: {
    panelName: "mkr_cine_shockwave_distort_studio",
    title: "Shockwave Distort Studio",
    subtitle: "Control the ring center, band width, displacement force, and chroma split from a visible wavefront panel instead of treating the effect like a generic distortion form.",
    accent: "#7cc5ff",
    size: [760, 840],
    defaults: {
      center_x: 0.5,
      center_y: 0.5,
      radius: 0.22,
      width: 0.08,
      amplitude_px: 14.0,
      ring_hardness: 1.5,
      chroma_split_px: 1.2,
      mix: 1.0,
      mask_feather: 4.0,
      invert_mask: false,
    },
    numericSpecs: {
      center_x: { min: 0, max: 1 },
      center_y: { min: 0, max: 1 },
      radius: { min: 0, max: 1.5 },
      width: { min: 0.001, max: 0.75 },
      amplitude_px: { min: -128, max: 128 },
      ring_hardness: { min: 0.5, max: 6 },
      chroma_split_px: { min: 0, max: 16 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["center_x", "center_y", "radius", "width", "amplitude_px", "ring_hardness", "chroma_split_px", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Radius", get: (node) => formatNumber(getNumber(node, "radius", 0.22), 3) },
      { label: "Amp", get: (node) => `${formatSigned(getNumber(node, "amplitude_px", 14), 1)} px` },
      { label: "Split", get: (node) => formatNumber(getNumber(node, "chroma_split_px", 1.2), 2) },
    ],
    presets: [
      { label: "Soft Ring", tone: "accent", values: { radius: 0.22, width: 0.09, amplitude_px: 10, ring_hardness: 1.1, chroma_split_px: 0.8 } },
      { label: "Blast", values: { radius: 0.18, width: 0.06, amplitude_px: 24, ring_hardness: 2.1, chroma_split_px: 2.2 } },
      { label: "Reverse", values: { radius: 0.28, width: 0.10, amplitude_px: -18, ring_hardness: 1.7, chroma_split_px: 1.4 } },
    ],
    graph: {
      title: "Wavefront Preview",
      note: "ring band",
      height: 220,
      draw: drawShockwavePreview,
      readouts: [
        { label: "Width", get: (node) => formatNumber(getNumber(node, "width", 0.08), 3) },
        { label: "Hardness", get: (node) => formatNumber(getNumber(node, "ring_hardness", 1.5), 2) },
      ],
      help: "Radius moves the ring out from the center, width controls its band, and amplitude determines whether the wave expands or compresses the image.",
    },
    sections: [
      {
        title: "Wavefront",
        note: "center + band",
        controls: [
          { key: "center_x", label: "Center X", min: 0, max: 1, step: 0.001, decimals: 3 },
          { key: "center_y", label: "Center Y", min: 0, max: 1, step: 0.001, decimals: 3 },
          { key: "radius", label: "Radius", min: 0, max: 1.5, step: 0.001, decimals: 3 },
          { key: "width", label: "Width", min: 0.001, max: 0.75, step: 0.001, decimals: 3 },
        ],
      },
      {
        title: "Distortion",
        note: "force + fringe",
        controls: [
          { key: "amplitude_px", label: "Amplitude", min: -128, max: 128, step: 0.25, decimals: 2 },
          { key: "ring_hardness", label: "Ring Hardness", min: 0.5, max: 6, step: 0.05, decimals: 2 },
          { key: "chroma_split_px", label: "Chroma Split", min: 0, max: 16, step: 0.05, decimals: 2 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the shockwave blends in." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

function buildPanel(node, config) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT MOTION",
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

  if (node.__mkrCineMotionPanelInstalled) {
    node.__mkrCineMotionRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrCineMotionPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrCineMotionRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrCineMotionRefreshHooksInstalled", refresh);
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
