import { app } from "../../../scripts/app.js";
import { createPanelShell } from "./uiSystem.js";
import {
  attachPanel,
  ensureCanvasResolution,
  matchesNode,
  normalizePanelNode,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ColorWheelsStudio";
const NODE_NAME = "x1ColorWheels";
const PANEL_NAME = "mkr_color_wheels_dark_studio";
const STYLE_ID = "mkr-color-wheels-dark-v1";
const SETTINGS_WIDGET_NAME = "settings_json";

const LEGACY_WIDGETS = [
  "lift_r", "lift_g", "lift_b",
  "gamma_r", "gamma_g", "gamma_b",
  "gain_r", "gain_g", "gain_b",
  "offset_r", "offset_g", "offset_b",
  "balance",
  "saturation",
  "mix",
  "mask_feather",
  "invert_mask",
];
const HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...LEGACY_WIDGETS];

const WHEELS = [
  { key: "lift", label: "Dark", mode: "centered" },
  { key: "gamma", label: "Shadow", mode: "pivot" },
  { key: "gain", label: "Light", mode: "pivot" },
  { key: "offset", label: "Global", mode: "centered" },
];

const PRESETS = {
  neutral: {
    lift_r: 0.0, lift_g: 0.0, lift_b: 0.0,
    gamma_r: 1.0, gamma_g: 1.0, gamma_b: 1.0,
    gain_r: 1.0, gain_g: 1.0, gain_b: 1.0,
    offset_r: 0.0, offset_g: 0.0, offset_b: 0.0,
    balance: 0.0,
    saturation: 1.0,
    mix: 1.0,
  },
  warm: {
    lift_r: 0.03, lift_g: 0.00, lift_b: -0.05,
    gamma_r: 1.03, gamma_g: 1.00, gamma_b: 0.96,
    gain_r: 1.07, gain_g: 1.02, gain_b: 0.93,
    offset_r: -0.01, offset_g: 0.00, offset_b: -0.01,
    balance: -0.10,
    saturation: 1.06,
    mix: 1.0,
  },
  commercial: {
    lift_r: 0.00, lift_g: 0.00, lift_b: 0.00,
    gamma_r: 0.97, gamma_g: 0.99, gamma_b: 1.02,
    gain_r: 1.10, gain_g: 1.07, gain_b: 1.01,
    offset_r: 0.01, offset_g: 0.01, offset_b: 0.00,
    balance: 0.12,
    saturation: 1.14,
    mix: 1.0,
  },
};

const DEFAULT_SETTINGS = {
  lift_r: 0.0, lift_g: 0.0, lift_b: 0.0,
  gamma_r: 1.0, gamma_g: 1.0, gamma_b: 1.0,
  gain_r: 1.0, gain_g: 1.0, gain_b: 1.0,
  offset_r: 0.0, offset_g: 0.0, offset_b: 0.0,
  balance: 0.0,
  saturation: 1.0,
  mix: 1.0,
  mask_feather: 12.0,
  invert_mask: false,
};

const NUMERIC_SPECS = {
  lift_r: { min: -1, max: 1, fallback: 0 },
  lift_g: { min: -1, max: 1, fallback: 0 },
  lift_b: { min: -1, max: 1, fallback: 0 },
  gamma_r: { min: 0.1, max: 3, fallback: 1 },
  gamma_g: { min: 0.1, max: 3, fallback: 1 },
  gamma_b: { min: 0.1, max: 3, fallback: 1 },
  gain_r: { min: 0, max: 3, fallback: 1 },
  gain_g: { min: 0, max: 3, fallback: 1 },
  gain_b: { min: 0, max: 3, fallback: 1 },
  offset_r: { min: -1, max: 1, fallback: 0 },
  offset_g: { min: -1, max: 1, fallback: 0 },
  offset_b: { min: -1, max: 1, fallback: 0 },
  balance: { min: -1, max: 1, fallback: 0 },
  saturation: { min: 0, max: 2, fallback: 1 },
  mix: { min: 0, max: 1, fallback: 1 },
  mask_feather: { min: 0, max: 256, fallback: 12 },
};

function ensureDarkWheelStyles() {
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-wheels-dark {
      width: 100%;
      max-width: none;
      max-height: none;
      overflow: hidden;
      padding: 4px 4px 12px;
      border-radius: 0;
      border: 0;
      background: transparent;
      color: #eef1f4;
      box-shadow: none;
      box-sizing: border-box;
      font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", sans-serif;
    }

    .mkr-wheels-dark .mkr-kicker {
      color: rgba(245,248,252,0.44);
      font-size: 9px;
      letter-spacing: 0.12em;
      margin-bottom: 3px;
    }

    .mkr-wheels-dark .mkr-title {
      color: #f5f7fa;
      font-size: 16px;
      line-height: 1.05;
      letter-spacing: -0.02em;
      margin: 0;
    }

    .mkr-wheels-dark .mkr-subtitle {
      margin-top: 4px;
      color: rgba(226,231,237,0.58);
      font-size: 11px;
      line-height: 1.3;
    }

    .mkr-wheels-topbar {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }

    .mkr-wheels-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      flex: 1 1 auto;
    }

    .mkr-wheels-metric {
      min-width: 0;
      padding: 5px 7px;
      border-radius: 8px;
      background: rgba(255,255,255,0.035);
      border: 1px solid rgba(255,255,255,0.05);
    }

    .mkr-wheels-metric-label {
      color: rgba(225,232,238,0.42);
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 2px;
    }

    .mkr-wheels-metric-value {
      color: #f4f7fb;
      font-size: 14px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    .mkr-wheels-presets {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .mkr-wheels-preset {
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      color: rgba(241,245,248,0.88);
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
    }

    .mkr-wheels-preset:hover {
      background: rgba(255,255,255,0.07);
    }

    .mkr-wheels-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }

    .mkr-wheels-unit {
      min-width: 0;
    }

    .mkr-wheels-unit-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 5px;
    }

    .mkr-wheels-unit-title {
      font-size: 11px;
      font-weight: 700;
      color: rgba(245,248,252,0.96);
    }

    .mkr-wheels-unit-mode {
      font-size: 9px;
      color: rgba(221,228,234,0.42);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .mkr-wheels-canvas {
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      border-radius: 999px;
      background:
        radial-gradient(circle at 50% 45%, rgba(255,255,255,0.06), rgba(255,255,255,0.00) 52%),
        linear-gradient(180deg, rgba(17,18,21,0.98), rgba(26,28,31,0.98));
      border: 1px solid rgba(255,255,255,0.08);
      box-sizing: border-box;
      cursor: crosshair;
    }

    .mkr-wheels-readout {
      margin-top: 7px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 4px;
    }

    .mkr-wheels-readout-cell {
      padding: 3px 4px;
      border-radius: 6px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.04);
      text-align: center;
    }

    .mkr-wheels-readout-label {
      color: rgba(221,228,234,0.38);
      font-size: 8px;
      margin-bottom: 2px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .mkr-wheels-readout-value {
      color: #f0f4f8;
      font-size: 10px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    .mkr-wheels-controls {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
      padding-top: 10px;
      border-top: 1px solid rgba(255,255,255,0.08);
    }

    .mkr-wheels-control {
      min-width: 0;
    }

    .mkr-wheels-control-label {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
      color: rgba(237,242,247,0.84);
      font-size: 10px;
      font-weight: 600;
    }

    .mkr-wheels-control-value {
      color: rgba(237,242,247,0.50);
      font-variant-numeric: tabular-nums;
    }

    .mkr-wheels-range {
      width: 100%;
      accent-color: #ff7b31;
      margin: 0;
    }

    .mkr-wheels-number {
      width: 100%;
      margin-top: 4px;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 4px 6px;
      font-size: 10px;
      box-sizing: border-box;
      font-variant-numeric: tabular-nums;
    }

    .mkr-wheels-toggle {
      display: flex;
      flex-direction: column;
      gap: 6px;
      justify-content: flex-end;
    }

    .mkr-wheels-toggle-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 58px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
      box-sizing: border-box;
    }

    .mkr-wheels-toggle-wrap input {
      accent-color: #ff7b31;
    }

    .mkr-wheels-toggle-text {
      color: rgba(237,242,247,0.72);
      font-size: 10px;
      line-height: 1.25;
    }

    @media (max-width: 860px) {
      .mkr-wheels-strip {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .mkr-wheels-controls {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .mkr-wheels-topbar {
        flex-direction: column;
        align-items: stretch;
      }
    }
  `;

  document.head.appendChild(style);
}

function formatSigned(value, decimals = 2) {
  const number = Number(value) || 0;
  const fixed = number.toFixed(decimals);
  return number > 0 ? `+${fixed}` : fixed;
}

function formatNumber(value, decimals = 2) {
  return (Number(value) || 0).toFixed(decimals);
}

function getWidget(node, name) {
  const mapped = node?.__mkrColorWidgetByName?.get?.(String(name || ""));
  if (mapped) return mapped;
  return Array.isArray(node?.widgets) ? node.widgets.find((widget) => String(widget?.name || "") === name) : null;
}

function normalizeSettings(payload) {
  const source = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const next = { ...DEFAULT_SETTINGS };
  for (const [key, spec] of Object.entries(NUMERIC_SPECS)) {
    const parsed = Number.parseFloat(String(source[key]));
    const value = Number.isFinite(parsed) ? parsed : spec.fallback;
    next[key] = Math.max(spec.min, Math.min(spec.max, value));
  }
  next.invert_mask = (() => {
    const value = source.invert_mask;
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      const token = value.trim().toLowerCase();
      if (["true", "1", "yes", "on"].includes(token)) return true;
      if (["false", "0", "no", "off"].includes(token)) return false;
    }
    return DEFAULT_SETTINGS.invert_mask;
  })();
  return next;
}

function parseSettingsValue(rawValue) {
  const text = String(rawValue ?? "").trim();
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
  }
  return {};
}

function serializeSettings(settings) {
  return JSON.stringify(normalizeSettings(settings));
}

function buildLegacySettings(values, node) {
  const payload = {};
  let found = false;
  if (Array.isArray(values) && values.length >= LEGACY_WIDGETS.length) {
    LEGACY_WIDGETS.forEach((name, index) => {
      if (values[index] !== undefined) {
        payload[name] = values[index];
        found = true;
      }
    });
  }
  if (!found && node?.properties && typeof node.properties === "object") {
    for (const name of LEGACY_WIDGETS) {
      if (node.properties[name] !== undefined) {
        payload[name] = node.properties[name];
        found = true;
      }
    }
  }
  return found ? normalizeSettings(payload) : null;
}

function migrateLegacyWorkflow(node) {
  if (!node || node.__mkrColorWheelsLegacyMigrated) return;
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  if (!settingsWidget) {
    node.__mkrColorWheelsLegacyMigrated = true;
    return;
  }
  const legacy = buildLegacySettings(node.widgets_values, node);
  if (!legacy) {
    node.__mkrColorWheelsLegacyMigrated = true;
    return;
  }
  const serialized = serializeSettings(legacy);
  settingsWidget.value = serialized;
  node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
  node.properties[SETTINGS_WIDGET_NAME] = serialized;
  node.widgets_values = [serialized];
  node.__mkrColorWheelsLegacyMigrated = true;
}

function readSettings(node) {
  migrateLegacyWorkflow(node);
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  const raw = settingsWidget?.value ?? node?.properties?.[SETTINGS_WIDGET_NAME];
  const settings = normalizeSettings(parseSettingsValue(raw));
  const serialized = serializeSettings(settings);
  if (settingsWidget && settingsWidget.value !== serialized) {
    settingsWidget.value = serialized;
  }
  if (node) {
    node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
    node.properties[SETTINGS_WIDGET_NAME] = serialized;
    node.widgets_values = [serialized];
  }
  return settings;
}

function writeSettings(node, patch) {
  const next = normalizeSettings({ ...readSettings(node), ...(patch || {}) });
  const serialized = serializeSettings(next);
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  if (settingsWidget) {
    settingsWidget.value = serialized;
    if (typeof settingsWidget.callback === "function") {
      settingsWidget.callback(serialized, app?.graph, node, settingsWidget);
    }
  }
  if (node) {
    node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
    node.properties[SETTINGS_WIDGET_NAME] = serialized;
    node.widgets_values = [serialized];
    node.setDirtyCanvas?.(true, true);
    app?.graph?.setDirtyCanvas?.(true, true);
  }
  return next;
}

function getNumber(node, name, fallback = 0) {
  const settings = readSettings(node);
  const value = Number(settings?.[name]);
  return Number.isFinite(value) ? value : fallback;
}

function getBoolean(node, name, fallback = false) {
  const settings = readSettings(node);
  return settings?.[name] !== undefined ? Boolean(settings[name]) : fallback;
}

function setSettingValue(node, name, value) {
  writeSettings(node, { [name]: value });
}

function rgbFromPoint(x, y, mode) {
  const r = x;
  const g = (-0.5 * x) + (0.8660254 * y);
  const b = (-0.5 * x) - (0.8660254 * y);
  if (mode === "pivot") {
    return {
      r: Math.max(0.1, Math.min(3.0, 1.0 + r)),
      g: Math.max(0.1, Math.min(3.0, 1.0 + g)),
      b: Math.max(0.1, Math.min(3.0, 1.0 + b)),
    };
  }
  return {
    r: Math.max(-1.0, Math.min(1.0, r)),
    g: Math.max(-1.0, Math.min(1.0, g)),
    b: Math.max(-1.0, Math.min(1.0, b)),
  };
}

function pointFromRgb(r, g, b, mode) {
  const rr = mode === "pivot" ? (r - 1.0) : r;
  const gg = mode === "pivot" ? (g - 1.0) : g;
  const bb = mode === "pivot" ? (b - 1.0) : b;
  const x = rr;
  const y = (gg - bb) / 1.7320508;
  const length = Math.hypot(x, y);
  if (length > 1.0) {
    return { x: x / length, y: y / length };
  }
  return { x, y };
}

function drawWheel(ctx, cx, cy, radius) {
  const ring = Math.max(8, radius * 0.16);
  for (let index = 0; index < 96; index += 1) {
    const a0 = (Math.PI * 2 * index) / 96;
    const a1 = (Math.PI * 2 * (index + 1)) / 96;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, a0, a1);
    ctx.strokeStyle = `hsl(${Math.round((360 * index) / 96)} 88% 54%)`;
    ctx.lineWidth = ring;
    ctx.stroke();
  }

  const inner = radius - ring * 0.8;
  const glow = ctx.createRadialGradient(cx, cy, inner * 0.05, cx, cy, inner);
  glow.addColorStop(0, "rgba(255,255,255,0.12)");
  glow.addColorStop(0.5, "rgba(255,255,255,0.04)");
  glow.addColorStop(1, "rgba(0,0,0,0.00)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, inner, 0, Math.PI * 2);
  ctx.fill();

  ctx.beginPath();
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.lineWidth = 1;
  ctx.arc(cx, cy, inner, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.beginPath();
  ctx.moveTo(cx - inner + 8, cy);
  ctx.lineTo(cx + inner - 8, cy);
  ctx.moveTo(cx, cy - inner + 8);
  ctx.lineTo(cx, cy + inner - 8);
  ctx.stroke();
}

function applyValues(node, values) {
  writeSettings(node, values);
}

function createMetric(label, value) {
  const root = document.createElement("div");
  root.className = "mkr-wheels-metric";

  const labelNode = document.createElement("div");
  labelNode.className = "mkr-wheels-metric-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("div");
  valueNode.className = "mkr-wheels-metric-value";
  valueNode.textContent = value;

  root.appendChild(labelNode);
  root.appendChild(valueNode);

  return {
    element: root,
    setValue(next) {
      valueNode.textContent = next;
    },
  };
}

function createCompactSlider({ label, min, max, step, value, decimals = 2, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-wheels-control";

  const head = document.createElement("div");
  head.className = "mkr-wheels-control-label";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("span");
  valueNode.className = "mkr-wheels-control-value";
  head.appendChild(labelNode);
  head.appendChild(valueNode);

  const range = document.createElement("input");
  range.type = "range";
  range.className = "mkr-wheels-range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);

  const number = document.createElement("input");
  number.type = "number";
  number.className = "mkr-wheels-number";
  number.min = String(min);
  number.max = String(max);
  number.step = String(step);

  const setDisplay = (next) => {
    const normalized = Number.isFinite(next) ? Number(next.toFixed(decimals)) : value;
    range.value = String(normalized);
    number.value = String(normalized);
    valueNode.textContent = normalized.toFixed(decimals);
  };

  const commit = (raw) => {
    const parsed = Number.parseFloat(String(raw));
    const next = Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : value;
    setDisplay(next);
    onChange?.(next);
  };

  setDisplay(Number(value));
  range.addEventListener("input", () => commit(range.value));
  number.addEventListener("change", () => commit(number.value));

  root.appendChild(head);
  root.appendChild(range);
  root.appendChild(number);

  return {
    element: root,
    setValue(next) {
      setDisplay(Number(next));
    },
  };
}

function createToggle({ label, checked, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-wheels-toggle";

  const title = document.createElement("div");
  title.className = "mkr-wheels-control-label";
  title.innerHTML = `<span>${label}</span><span class="mkr-wheels-control-value">${checked ? "On" : "Off"}</span>`;

  const wrap = document.createElement("label");
  wrap.className = "mkr-wheels-toggle-wrap";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = checked;
  const text = document.createElement("div");
  text.className = "mkr-wheels-toggle-text";
  text.textContent = "Invert the external mask before blending the grade.";
  wrap.appendChild(input);
  wrap.appendChild(text);

  input.addEventListener("change", () => {
    title.lastChild.textContent = input.checked ? "On" : "Off";
    onChange?.(input.checked);
  });

  root.appendChild(title);
  root.appendChild(wrap);
  return {
    element: root,
    setValue(next) {
      input.checked = !!next;
      title.lastChild.textContent = input.checked ? "On" : "Off";
    },
  };
}

function buildWheelUnit(node, wheel, onUpdate) {
  const root = document.createElement("div");
  root.className = "mkr-wheels-unit";

  const head = document.createElement("div");
  head.className = "mkr-wheels-unit-head";
  head.innerHTML = `<div class="mkr-wheels-unit-title">${wheel.label}</div><div class="mkr-wheels-unit-mode">${wheel.mode === "pivot" ? "pivot" : "offset"}</div>`;
  root.appendChild(head);

  const canvas = document.createElement("canvas");
  canvas.className = "mkr-wheels-canvas";
  root.appendChild(canvas);

  const readout = document.createElement("div");
  readout.className = "mkr-wheels-readout";
  const rCell = document.createElement("div");
  const gCell = document.createElement("div");
  const bCell = document.createElement("div");
  for (const cell of [rCell, gCell, bCell]) {
    cell.className = "mkr-wheels-readout-cell";
  }
  readout.appendChild(rCell);
  readout.appendChild(gCell);
  readout.appendChild(bCell);
  root.appendChild(readout);

  const setCell = (element, label, value) => {
    element.innerHTML = `<div class="mkr-wheels-readout-label">${label}</div><div class="mkr-wheels-readout-value">${value}</div>`;
  };

  let dragging = false;

  const redraw = () => {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    ctx.clearRect(0, 0, width, height);

    const radius = Math.max(34, Math.min(width, height) * 0.42);
    const cx = width * 0.5;
    const cy = height * 0.5;
    drawWheel(ctx, cx, cy, radius);

    const r = getNumber(node, `${wheel.key}_r`, wheel.mode === "pivot" ? 1.0 : 0.0);
    const g = getNumber(node, `${wheel.key}_g`, wheel.mode === "pivot" ? 1.0 : 0.0);
    const b = getNumber(node, `${wheel.key}_b`, wheel.mode === "pivot" ? 1.0 : 0.0);
    const point = pointFromRgb(r, g, b, wheel.mode);
    const handleRadius = Math.max(18, radius - 12);
    const px = cx + (point.x * handleRadius);
    const py = cy + (point.y * handleRadius);

    ctx.beginPath();
    ctx.strokeStyle = "rgba(255,255,255,0.18)";
    ctx.lineWidth = 1.3;
    ctx.moveTo(cx, cy);
    ctx.lineTo(px, py);
    ctx.stroke();

    ctx.beginPath();
    ctx.fillStyle = "rgba(250,252,255,0.98)";
    ctx.arc(px, py, 5.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(14,16,19,0.92)";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.beginPath();
    ctx.fillStyle = "rgba(255,255,255,0.56)";
    ctx.arc(cx, cy, 2, 0, Math.PI * 2);
    ctx.fill();

    setCell(rCell, "R", formatSigned(wheel.mode === "pivot" ? r - 1.0 : r));
    setCell(gCell, "G", formatSigned(wheel.mode === "pivot" ? g - 1.0 : g));
    setCell(bCell, "B", formatSigned(wheel.mode === "pivot" ? b - 1.0 : b));
  };

  const updateFromPointer = (event) => {
    const rect = canvas.getBoundingClientRect();
    const cx = rect.width * 0.5;
    const cy = rect.height * 0.5;
    const radius = Math.max(34, Math.min(rect.width, rect.height) * 0.42 - 8);
    const dx = event.clientX - rect.left - cx;
    const dy = event.clientY - rect.top - cy;
    const length = Math.max(1e-6, Math.hypot(dx, dy));
    const clamped = Math.min(radius, length);
    const nx = (dx / length) * (clamped / radius);
    const ny = (dy / length) * (clamped / radius);
    const rgb = rgbFromPoint(nx, ny, wheel.mode);
    writeSettings(node, {
      [`${wheel.key}_r`]: Number(rgb.r.toFixed(4)),
      [`${wheel.key}_g`]: Number(rgb.g.toFixed(4)),
      [`${wheel.key}_b`]: Number(rgb.b.toFixed(4)),
    });
    onUpdate();
    redraw();
  };

  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    canvas.setPointerCapture?.(event.pointerId);
    updateFromPointer(event);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    updateFromPointer(event);
  });

  const stop = (event) => {
    if (!dragging) return;
    dragging = false;
    canvas.releasePointerCapture?.(event.pointerId);
  };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => redraw());
    observer.observe(canvas);
  }

  redraw();
  return { element: root, redraw };
}

function buildPanel(node) {
  ensureDarkWheelStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "High Dynamic Range",
    subtitle: "Direct dark/shadow/light/global wheel grading inside the node.",
    showHeader: false,
  });

  panel.classList.add("mkr-wheels-dark");

  const topbar = document.createElement("div");
  topbar.className = "mkr-wheels-topbar";
  const metrics = document.createElement("div");
  metrics.className = "mkr-wheels-metrics";
  const energyMetric = createMetric("Energy", "0.00");
  const balanceMetric = createMetric("Balance", "0.00");
  const satMetric = createMetric("Sat", "1.00");
  metrics.appendChild(energyMetric.element);
  metrics.appendChild(balanceMetric.element);
  metrics.appendChild(satMetric.element);

  const presets = document.createElement("div");
  presets.className = "mkr-wheels-presets";
  for (const preset of [
    { id: "neutral", label: "Neutral" },
    { id: "warm", label: "Warm" },
    { id: "commercial", label: "Commercial" },
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mkr-wheels-preset";
    button.textContent = preset.label;
    button.addEventListener("click", () => {
      applyValues(node, PRESETS[preset.id]);
      refresh();
    });
    presets.appendChild(button);
  }
  topbar.appendChild(metrics);
  topbar.appendChild(presets);
  panel.appendChild(topbar);

  const strip = document.createElement("div");
  strip.className = "mkr-wheels-strip";
  const units = [];

  const refreshMetrics = () => {
    let energy = 0;
    for (const wheel of WHEELS) {
      const base = wheel.mode === "pivot" ? 1.0 : 0.0;
      energy += Math.abs(getNumber(node, `${wheel.key}_r`, base) - base);
      energy += Math.abs(getNumber(node, `${wheel.key}_g`, base) - base);
      energy += Math.abs(getNumber(node, `${wheel.key}_b`, base) - base);
    }
    energyMetric.setValue(formatNumber(energy / 12, 2));
    balanceMetric.setValue(formatSigned(getNumber(node, "balance", 0)));
    satMetric.setValue(formatNumber(getNumber(node, "saturation", 1)));
  };

  const refresh = () => {
    refreshMetrics();
    for (const unit of units) {
      unit.redraw();
    }
    balanceControl.setValue(getNumber(node, "balance", 0));
    saturationControl.setValue(getNumber(node, "saturation", 1));
    mixControl.setValue(getNumber(node, "mix", 1));
    featherControl.setValue(getNumber(node, "mask_feather", 12));
    invertControl.setValue(getBoolean(node, "invert_mask", false));
  };

  for (const wheel of WHEELS) {
    const unit = buildWheelUnit(node, wheel, refreshMetrics);
    units.push(unit);
    strip.appendChild(unit.element);
  }
  panel.appendChild(strip);

  const controls = document.createElement("div");
  controls.className = "mkr-wheels-controls";

  const balanceControl = createCompactSlider({
    label: "Balance",
    min: -1,
    max: 1,
    step: 0.01,
    value: getNumber(node, "balance", 0),
    decimals: 2,
    onChange: (value) => {
      setSettingValue(node, "balance", value);
      refreshMetrics();
    },
  });

  const saturationControl = createCompactSlider({
    label: "Saturation",
    min: 0,
    max: 2,
    step: 0.01,
    value: getNumber(node, "saturation", 1),
    decimals: 2,
    onChange: (value) => {
      setSettingValue(node, "saturation", value);
      refreshMetrics();
    },
  });

  const mixControl = createCompactSlider({
    label: "Mix",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "mix", 1),
    decimals: 2,
    onChange: (value) => {
      setSettingValue(node, "mix", value);
    },
  });

  const featherControl = createCompactSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => {
      setSettingValue(node, "mask_feather", value);
    },
  });

  const invertControl = createToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    onChange: (value) => {
      setSettingValue(node, "invert_mask", value);
    },
  });

  controls.appendChild(balanceControl.element);
  controls.appendChild(saturationControl.element);
  controls.appendChild(mixControl.element);
  controls.appendChild(featherControl.element);
  controls.appendChild(invertControl.element);
  panel.appendChild(controls);

  refresh();
  return { panel, refresh };
}

function installColorWheelsStudio(node) {
  if (!matchesNode(node, NODE_NAME)) return;
  if (node.__mkrColorWheelsStudioInstalled) {
    node.__mkrColorWheelsRefresh?.();
    normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);
    return;
  }
  node.__mkrColorWheelsStudioInstalled = true;
  const built = buildPanel(node);
  node.__mkrColorWheelsRefresh = built.refresh;
  attachPanel(node, PANEL_NAME, built.panel, 930, 580);
  normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigureColorWheelsStudio() {
    const result = originalConfigure?.apply(this, arguments);
    this.__mkrColorWheelsRefresh?.();
    normalizePanelNode(this, HIDDEN_WIDGETS, PANEL_NAME);
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedColorWheelsStudio() {
    const result = originalExecuted?.apply(this, arguments);
    this.__mkrColorWheelsRefresh?.();
    return result;
  };
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_NAME) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = originalOnNodeCreated?.apply(this, arguments);
      installColorWheelsStudio(this);
      return result;
    };
  },
  async nodeCreated(node) {
    installColorWheelsStudio(node);
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      installColorWheelsStudio(node);
    }
  },
});
