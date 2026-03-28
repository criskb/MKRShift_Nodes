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
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.VFXConceptSignalStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-vfx-concept-signal-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
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

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-vfx-concept-select,
    .mkr-vfx-concept-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-vfx-concept-select {
      margin-top: 4px;
    }

    .mkr-vfx-concept-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      margin-top: 4px;
    }

    .mkr-vfx-concept-chip-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      margin-top: 8px;
    }

    .mkr-vfx-concept-chip {
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      padding: 6px 8px;
      font-size: 10px;
      color: rgba(242,246,250,0.88);
      font-weight: 700;
    }

    .mkr-vfx-concept-chip span {
      display: block;
      margin-top: 4px;
      font-size: 9px;
      color: rgba(226,232,238,0.56);
      font-weight: 500;
    }
  `;
  document.head.appendChild(style);
}

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.16)") {
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
  select.className = "mkr-vfx-concept-select";
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

function createSeedControl({ label, value, min, max, onChange, onReseed }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const wrap = document.createElement("div");
  wrap.className = "mkr-vfx-concept-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-vfx-concept-number";
  input.min = String(min);
  input.max = String(max);
  input.step = "1";
  input.value = String(value);

  const button = createGradeButton("Reseed", () => {
    const next = onReseed?.();
    if (Number.isFinite(next)) {
      input.value = String(next);
      head.lastChild.textContent = String(next);
    }
  });

  input.addEventListener("change", () => {
    const parsed = Number.parseInt(String(input.value), 10);
    const next = Number.isFinite(parsed) ? clamp(parsed, min, max) : value;
    input.value = String(next);
    head.lastChild.textContent = String(next);
    onChange?.(next);
  });

  wrap.appendChild(input);
  wrap.appendChild(button);
  root.appendChild(head);
  root.appendChild(wrap);
  return {
    element: root,
    setValue(next) {
      const normalized = Number.isFinite(Number(next)) ? clamp(Math.round(Number(next)), min, max) : value;
      input.value = String(normalized);
      head.lastChild.textContent = String(normalized);
    },
  };
}

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values || {})) {
    setWidgetValue(node, key, value);
  }
}

function hasInputLink(node, name) {
  const input = Array.isArray(node?.inputs)
    ? node.inputs.find((item) => String(item?.name || "") === String(name))
    : null;
  return !!input?.link;
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

function readControlValue(node, spec) {
  if (spec.type === "toggle") return getBoolean(node, spec.key, !!spec.default);
  if (spec.type === "select" || spec.type === "seed") return getValue(node, spec.key, spec.default);
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

  if (spec.type === "seed") {
    const control = createSeedControl({
      label: spec.label,
      value: Math.round(Number(getValue(node, spec.key, 0)) || 0),
      min: spec.min ?? 0,
      max: spec.max ?? 2147483647,
      onChange: (value) => {
        setWidgetValue(node, spec.key, Math.round(value));
        refresh();
      },
      onReseed: () => {
        const next = Math.floor(Math.random() * 2147483647);
        setWidgetValue(node, spec.key, next);
        refresh();
        return next;
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

function getLightLeakRamp(node) {
  const preset = String(getValue(node, "ramp_preset", "warm"));
  if (preset === "sunset") {
    return [[1.0, 0.28, 0.12], [1.0, 0.74, 0.28]];
  }
  if (preset === "teal_orange") {
    return [[0.10, 0.80, 0.72], [1.0, 0.62, 0.18]];
  }
  if (preset === "magenta_cyan") {
    return [[0.95, 0.22, 0.74], [0.34, 0.94, 1.0]];
  }
  if (preset === "custom") {
    return [
      [
        getNumber(node, "custom_start_r", 1.0),
        getNumber(node, "custom_start_g", 0.45),
        getNumber(node, "custom_start_b", 0.10),
      ],
      [
        getNumber(node, "custom_end_r", 1.0),
        getNumber(node, "custom_end_g", 0.86),
        getNumber(node, "custom_end_b", 0.42),
      ],
    ];
  }
  return [[1.0, 0.44, 0.10], [1.0, 0.86, 0.42]];
}

function drawLightLeakPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,170,110,0.22)");
  const [startColor, endColor] = getLightLeakRamp(node);
  const angle = (getNumber(node, "angle", 35) * Math.PI) / 180;
  const strength = clamp(getNumber(node, "strength", 0.35), 0, 2);
  const scale = clamp(getNumber(node, "scale", 1.0), 0.2, 3);
  const softness = clamp(getNumber(node, "softness", 1.0), 0.2, 3);
  const centerX = frame.x + (frame.w * 0.52);
  const centerY = frame.y + (frame.h * 0.48);
  const dirX = Math.cos(angle);
  const dirY = Math.sin(angle);
  const length = Math.max(frame.w, frame.h) * 0.9 * scale;

  const base = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  base.addColorStop(0, "rgba(11,13,16,0.98)");
  base.addColorStop(1, "rgba(28,32,38,0.98)");
  ctx.fillStyle = base;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const grad = ctx.createLinearGradient(
    centerX - (dirX * length),
    centerY - (dirY * length),
    centerX + (dirX * length),
    centerY + (dirY * length),
  );
  grad.addColorStop(0, rgbToCss(startColor, 0.10 + (strength * 0.10)));
  grad.addColorStop(0.48, "rgba(255,255,255,0.02)");
  grad.addColorStop(0.54, rgbToCss(endColor, 0.14 + (strength * 0.10)));
  grad.addColorStop(1, "rgba(255,255,255,0.02)");

  ctx.save();
  ctx.translate(centerX, centerY);
  ctx.rotate(angle);
  ctx.fillStyle = grad;
  ctx.filter = `blur(${(16 * softness).toFixed(1)}px)`;
  ctx.fillRect(-frame.w * 0.68, -frame.h * 0.24, frame.w * 1.36, frame.h * 0.48);
  ctx.filter = "none";
  ctx.restore();

  for (let i = 0; i < 4; i += 1) {
    const spread = (i - 1.5) * frame.h * 0.12;
    ctx.save();
    ctx.translate(centerX + (dirY * spread), centerY - (dirX * spread));
    ctx.rotate(angle);
    ctx.strokeStyle = i % 2 === 0 ? rgbToCss(startColor, 0.15) : rgbToCss(endColor, 0.16);
    ctx.lineWidth = 14 - (i * 2);
    ctx.filter = `blur(${(5 + (softness * 4)).toFixed(1)}px)`;
    ctx.beginPath();
    ctx.moveTo(-frame.w * 0.42, 0);
    ctx.lineTo(frame.w * 0.42, 0);
    ctx.stroke();
    ctx.restore();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(frame.x + 18, frame.y + 18, frame.w - 36, frame.h - 36);
}

function drawSplitTonePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(138,197,255,0.22)");
  const shadowColor = hueToRgb(getNumber(node, "shadow_hue", 210), getNumber(node, "shadow_sat", 0.3), 0.95);
  const highlightColor = hueToRgb(getNumber(node, "highlight_hue", 36), getNumber(node, "highlight_sat", 0.32), 1.0);
  const pivot = clamp(getNumber(node, "pivot", 0.5), 0, 1);
  const balance = clamp(getNumber(node, "balance", 0), -1, 1);
  const mix = clamp(getNumber(node, "mix", 0.75), 0, 1);

  const ramp = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y);
  ramp.addColorStop(0, rgbToCss(shadowColor, 0.88 * mix));
  ramp.addColorStop(clamp(pivot + (balance * 0.18), 0, 1), "rgba(229,232,236,0.92)");
  ramp.addColorStop(1, rgbToCss(highlightColor, 0.88 * mix));
  ctx.fillStyle = ramp;
  ctx.fillRect(frame.x + 16, frame.y + 24, frame.w - 32, frame.h - 48);

  const luma = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  luma.addColorStop(0, "rgba(255,255,255,0.12)");
  luma.addColorStop(1, "rgba(0,0,0,0.46)");
  ctx.fillStyle = luma;
  ctx.fillRect(frame.x + 16, frame.y + 24, frame.w - 32, frame.h - 48);

  const pivotX = frame.x + 16 + ((frame.w - 32) * pivot);
  ctx.strokeStyle = "rgba(255,255,255,0.92)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(pivotX, frame.y + 18);
  ctx.lineTo(pivotX, frame.y + frame.h - 18);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "600 12px sans-serif";
  ctx.fillText("Shadows", frame.x + 24, frame.y + 40);
  ctx.fillText("Highlights", frame.x + frame.w - 90, frame.y + 40);
}

function drawSelectiveColorPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(124,235,184,0.20)");
  const bandX = frame.x + 20;
  const bandW = frame.w - 40;
  const topY = frame.y + 30;
  const bandH = 40;
  const shiftY = topY + 66;
  const currentCenter = clamp(getNumber(node, "custom_hue_center", 220), 0, 360);
  const currentWidth = clamp(getNumber(node, "custom_hue_width", 30), 1, 180);
  const hueShift = getNumber(node, "hue_shift", 0);
  const satShift = getNumber(node, "sat_shift", 0.2);
  const valueShift = getNumber(node, "value_shift", 0);
  const softness = clamp(getNumber(node, "softness", 20), 0, 120);
  const rangeMode = String(getValue(node, "range_mode", "blues"));

  const hueGrad = ctx.createLinearGradient(bandX, 0, bandX + bandW, 0);
  for (let step = 0; step <= 12; step += 1) {
    const t = step / 12;
    hueGrad.addColorStop(t, rgbToCss(hueToRgb(t * 360, 0.9, 0.95), 1));
  }
  ctx.fillStyle = hueGrad;
  ctx.fillRect(bandX, topY, bandW, bandH);

  ctx.fillStyle = "rgba(255,255,255,0.12)";
  ctx.fillRect(bandX, shiftY, bandW, bandH);
  const shiftedGrad = ctx.createLinearGradient(bandX, 0, bandX + bandW, 0);
  for (let step = 0; step <= 12; step += 1) {
    const t = step / 12;
    shiftedGrad.addColorStop(
      t,
      rgbToCss(hueToRgb((t * 360) + hueShift, clamp(0.72 + satShift * 0.22, 0.1, 1), clamp(0.86 + valueShift * 0.18, 0.2, 1)), 1),
    );
  }
  ctx.fillStyle = shiftedGrad;
  ctx.fillRect(bandX, shiftY, bandW, bandH);

  const centerX = bandX + ((currentCenter / 360) * bandW);
  const widthPx = (currentWidth / 360) * bandW;
  ctx.strokeStyle = "rgba(255,255,255,0.95)";
  ctx.lineWidth = 2;
  ctx.strokeRect(centerX - (widthPx * 0.5), topY - 3, widthPx, bandH + 6);
  ctx.fillStyle = "rgba(255,255,255,0.90)";
  ctx.font = "600 12px sans-serif";
  ctx.fillText(rangeMode === "custom" ? "Custom Hue Range" : `Target: ${rangeMode}`, bandX, frame.y + frame.h - 32);
  ctx.fillText(`Softness ${softness.toFixed(0)}°`, bandX + bandW - 80, frame.y + frame.h - 32);
}

function distortPoint(x, y, centerX, centerY, amount) {
  const dx = x - centerX;
  const dy = y - centerY;
  const r2 = (dx * dx) + (dy * dy);
  const scale = 1 + (amount * r2);
  return [centerX + (dx * scale), centerY + (dy * scale)];
}

function drawLensDistortPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(124,196,255,0.20)");
  const amount = getNumber(node, "distortion", 0.12) * 0.12;
  const chroma = clamp(getNumber(node, "chroma_aberration", 0.05), 0, 0.35);
  const vignette = clamp(getNumber(node, "edge_vignette", 0.22), 0, 1);
  const zoomComp = getBoolean(node, "zoom_compensation", true);
  const area = { x: frame.x + 26, y: frame.y + 26, w: frame.w - 52, h: frame.h - 52 };
  const centerX = area.x + (area.w * 0.5);
  const centerY = area.y + (area.h * 0.5);

  const bg = ctx.createLinearGradient(area.x, area.y, area.x, area.y + area.h);
  bg.addColorStop(0, "rgba(8,10,14,0.98)");
  bg.addColorStop(1, "rgba(25,28,36,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const drawGrid = (offset, color, alpha) => {
    ctx.strokeStyle = color.replace(", 1)", `, ${alpha})`);
    ctx.lineWidth = 1;
    for (let step = 0; step <= 8; step += 1) {
      ctx.beginPath();
      for (let t = 0; t <= 24; t += 1) {
        const p = t / 24;
        const x = area.x + ((area.w * step) / 8);
        const y = area.y + (area.h * p);
        const [dx, dy] = distortPoint(x + offset, y, centerX, centerY, amount);
        if (t === 0) ctx.moveTo(dx, dy);
        else ctx.lineTo(dx, dy);
      }
      ctx.stroke();
      ctx.beginPath();
      for (let t = 0; t <= 24; t += 1) {
        const p = t / 24;
        const x = area.x + (area.w * p);
        const y = area.y + ((area.h * step) / 8);
        const [dx, dy] = distortPoint(x + offset, y, centerX, centerY, amount);
        if (t === 0) ctx.moveTo(dx, dy);
        else ctx.lineTo(dx, dy);
      }
      ctx.stroke();
    }
  };

  drawGrid(-chroma * 24, "rgba(255,98,98,1)", 0.28);
  drawGrid(chroma * 24, "rgba(88,186,255,1)", 0.28);
  drawGrid(0, "rgba(240,244,248,1)", 0.34);

  const vignetteGrad = ctx.createRadialGradient(centerX, centerY, area.w * 0.12, centerX, centerY, area.w * 0.68);
  vignetteGrad.addColorStop(0, "rgba(0,0,0,0)");
  vignetteGrad.addColorStop(1, `rgba(0,0,0,${(vignette * 0.72).toFixed(3)})`);
  ctx.fillStyle = vignetteGrad;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  if (zoomComp) {
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(area.x + 16, area.y + 16, area.w - 32, area.h - 32);
    ctx.setLineDash([]);
  }
}

function drawCRTScanPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(135,255,175,0.18)");
  const area = { x: frame.x + 22, y: frame.y + 22, w: frame.w - 44, h: frame.h - 44 };
  const scanStrength = clamp(getNumber(node, "scanline_strength", 0.28), 0, 1);
  const density = clamp(getNumber(node, "scanline_density", 1.0), 0.2, 4);
  const phosphor = clamp(getNumber(node, "phosphor_strength", 0.30), 0, 1);
  const bloom = clamp(getNumber(node, "bloom_bleed", 0.22), 0, 1);
  const warp = clamp(getNumber(node, "warp_strength", 0.12), 0, 1);
  const curvature = clamp(getNumber(node, "curvature", 0.18), 0, 0.8);
  const noise = clamp(getNumber(node, "noise_strength", 0.05), 0, 0.25);
  const centerX = area.x + (area.w * 0.5);
  const centerY = area.y + (area.h * 0.5);

  const bg = ctx.createLinearGradient(area.x, area.y, area.x, area.y + area.h);
  bg.addColorStop(0, "rgba(6,12,10,0.98)");
  bg.addColorStop(1, "rgba(16,22,18,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const content = ctx.createLinearGradient(area.x, area.y, area.x, area.y + area.h);
  content.addColorStop(0, "rgba(108,255,180,0.08)");
  content.addColorStop(0.52, "rgba(54,196,255,0.10)");
  content.addColorStop(1, "rgba(255,170,104,0.09)");
  ctx.fillStyle = content;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  ctx.save();
  ctx.beginPath();
  ctx.rect(area.x, area.y, area.w, area.h);
  ctx.clip();

  ctx.strokeStyle = "rgba(160,255,218,0.18)";
  ctx.lineWidth = 1;
  const rows = Math.max(18, Math.round(area.h / (10 / density)));
  for (let i = 0; i <= rows; i += 1) {
    const t = i / rows;
    const y = area.y + (area.h * t);
    const phase = Math.sin((t * Math.PI * 2) + (warp * 6.0)) * warp * 12;
    ctx.globalAlpha = 0.28 + ((Math.sin(t * Math.PI * rows * density) * 0.5 + 0.5) * scanStrength * 0.65);
    ctx.beginPath();
    ctx.moveTo(area.x + (curvature * 18) + phase, y);
    ctx.bezierCurveTo(
      area.x + (area.w * 0.28) - (curvature * 30),
      y - (curvature * 24),
      area.x + (area.w * 0.72) + (curvature * 30),
      y + (curvature * 24),
      area.x + area.w - (curvature * 18) - phase,
      y,
    );
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  const bands = 36;
  for (let i = 0; i < bands; i += 1) {
    const x = area.x + ((area.w * i) / bands);
    const bandW = area.w / bands;
    const color = i % 3 === 0
      ? "rgba(255,92,92,0.10)"
      : i % 3 === 1
        ? "rgba(88,255,140,0.10)"
        : "rgba(88,186,255,0.10)";
    ctx.fillStyle = color;
    ctx.fillRect(x, area.y, bandW * phosphor, area.h);
  }

  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "700 18px sans-serif";
  ctx.fillText("CRT", area.x + 22, area.y + 34);
  ctx.font = "600 12px sans-serif";
  ctx.fillText("scanline + phosphor", area.x + 22, area.y + 52);

  ctx.strokeStyle = "rgba(255,255,255,0.26)";
  ctx.lineWidth = 2;
  ctx.strokeRect(area.x + 18, area.y + 22, area.w - 36, area.h - 44);

  if (bloom > 0.001) {
    ctx.filter = `blur(${(10 + (bloom * 16)).toFixed(1)}px)`;
    ctx.strokeStyle = `rgba(118,255,176,${(0.06 + bloom * 0.10).toFixed(3)})`;
    ctx.lineWidth = 10 + (bloom * 12);
    ctx.strokeRect(area.x + 18, area.y + 22, area.w - 36, area.h - 44);
    ctx.filter = "none";
  }

  if (noise > 0.001) {
    ctx.fillStyle = `rgba(255,255,255,${(0.05 + noise * 0.35).toFixed(3)})`;
    const count = Math.round(32 + (noise * 260));
    for (let i = 0; i < count; i += 1) {
      const rx = area.x + ((i * 37) % Math.max(1, Math.floor(area.w - 2)));
      const ry = area.y + ((i * 53) % Math.max(1, Math.floor(area.h - 2)));
      ctx.fillRect(rx, ry, 1.5, 1.5);
    }
  }

  ctx.restore();

  const vignette = ctx.createRadialGradient(centerX, centerY, area.w * 0.18, centerX, centerY, area.w * 0.72);
  vignette.addColorStop(0, "rgba(0,0,0,0)");
  vignette.addColorStop(1, `rgba(0,0,0,${(0.28 + curvature * 0.32).toFixed(3)})`);
  ctx.fillStyle = vignette;
  ctx.fillRect(area.x, area.y, area.w, area.h);
}

function drawWarpDisplacePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(106,187,255,0.20)");
  const area = { x: frame.x + 20, y: frame.y + 20, w: frame.w - 40, h: frame.h - 40 };
  const strength = clamp(getNumber(node, "displace_strength", 12.0), 0, 128);
  const baseDirection = (getNumber(node, "base_direction", 0) * Math.PI) / 180;
  const noiseScale = clamp(getNumber(node, "noise_scale", 64.0), 2, 512);
  const noiseMix = clamp(getNumber(node, "noise_mix", 0.35), 0, 1);
  const hasDirectionMap = hasInputLink(node, "direction_map");
  const hasStrengthMap = hasInputLink(node, "strength_map");

  const bg = ctx.createLinearGradient(area.x, area.y, area.x + area.w, area.y + area.h);
  bg.addColorStop(0, "rgba(10,14,20,0.98)");
  bg.addColorStop(1, "rgba(19,28,38,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const cols = 10;
  const rows = 7;
  const amp = (strength / 128) * 20;
  const scale = noiseScale / 58;

  ctx.strokeStyle = "rgba(114,194,255,0.34)";
  ctx.lineWidth = 1.2;
  for (let col = 0; col <= cols; col += 1) {
    ctx.beginPath();
    for (let step = 0; step <= 36; step += 1) {
      const t = step / 36;
      const x = area.x + ((area.w * col) / cols);
      const y = area.y + (area.h * t);
      const wave = Math.sin((t * 6.3 * scale) + (col * 0.8) + baseDirection);
      const swirl = Math.cos((t * 4.8 * scale) - (col * 0.35) + (baseDirection * 0.6));
      const dx = (Math.cos(baseDirection) * amp * (1 - noiseMix)) + (wave * amp * noiseMix);
      const dy = (Math.sin(baseDirection) * amp * (1 - noiseMix)) + (swirl * amp * noiseMix * 0.7);
      const px = x + dx;
      const py = y + dy;
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(218,234,255,0.22)";
  for (let row = 0; row <= rows; row += 1) {
    ctx.beginPath();
    for (let step = 0; step <= 42; step += 1) {
      const t = step / 42;
      const x = area.x + (area.w * t);
      const y = area.y + ((area.h * row) / rows);
      const wave = Math.sin((t * 5.4 * scale) + (row * 0.7) + (baseDirection * 0.8));
      const swirl = Math.cos((t * 4.1 * scale) - (row * 0.5) + baseDirection);
      const dx = (Math.cos(baseDirection) * amp * (1 - noiseMix)) + (wave * amp * noiseMix);
      const dy = (Math.sin(baseDirection) * amp * (1 - noiseMix)) + (swirl * amp * noiseMix * 0.7);
      const px = x + dx;
      const py = y + dy;
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }

  const arrowX = area.x + 34;
  const arrowY = area.y + area.h - 30;
  const arrowLen = 44;
  ctx.strokeStyle = "rgba(255,255,255,0.74)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(arrowX, arrowY);
  ctx.lineTo(arrowX + (Math.cos(baseDirection) * arrowLen), arrowY + (Math.sin(baseDirection) * arrowLen));
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(arrowX + (Math.cos(baseDirection) * arrowLen), arrowY + (Math.sin(baseDirection) * arrowLen));
  ctx.lineTo(
    arrowX + (Math.cos(baseDirection) * arrowLen) - (Math.cos(baseDirection - 0.45) * 12),
    arrowY + (Math.sin(baseDirection) * arrowLen) - (Math.sin(baseDirection - 0.45) * 12),
  );
  ctx.lineTo(
    arrowX + (Math.cos(baseDirection) * arrowLen) - (Math.cos(baseDirection + 0.45) * 12),
    arrowY + (Math.sin(baseDirection) * arrowLen) - (Math.sin(baseDirection + 0.45) * 12),
  );
  ctx.closePath();
  ctx.fillStyle = "rgba(255,255,255,0.74)";
  ctx.fill();

  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "700 15px sans-serif";
  ctx.fillText("Warp Field", area.x + 18, area.y + 28);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "rgba(232,238,246,0.64)";
  ctx.fillText(hasDirectionMap ? "direction map linked" : "procedural direction", area.x + 18, area.y + 46);
  ctx.fillText(hasStrengthMap ? "strength map linked" : "uniform strength", area.x + area.w - 106, area.y + 46);
}

function drawGlowEdgesPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(150,255,244,0.18)");
  const area = { x: frame.x + 18, y: frame.y + 18, w: frame.w - 36, h: frame.h - 36 };
  const threshold = clamp(getNumber(node, "edge_threshold", 0.22), 0, 1);
  const softness = clamp(getNumber(node, "edge_softness", 1.0), 0.1, 4);
  const spread = clamp(getNumber(node, "glow_spread", 8.0), 0, 64);
  const strength = clamp(getNumber(node, "glow_strength", 1.0), 0, 3);
  const mode = String(getValue(node, "composite_mode", "screen"));
  const tint = [
    clamp(getNumber(node, "tint_r", 0.56), 0, 1),
    clamp(getNumber(node, "tint_g", 0.92), 0, 1),
    clamp(getNumber(node, "tint_b", 1.0), 0, 1),
  ];

  const bg = ctx.createLinearGradient(area.x, area.y, area.x, area.y + area.h);
  bg.addColorStop(0, "rgba(10,12,18,0.98)");
  bg.addColorStop(1, "rgba(24,29,37,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(area.x, area.y, area.w, area.h);

  const shapeX = area.x + 52;
  const shapeY = area.y + 30;
  const shapeW = area.w - 104;
  const shapeH = area.h - 60;

  ctx.save();
  ctx.fillStyle = "rgba(32,38,48,0.96)";
  ctx.beginPath();
  ctx.roundRect(shapeX, shapeY, shapeW, shapeH, 22);
  ctx.fill();

  ctx.beginPath();
  ctx.arc(shapeX + shapeW * 0.28, shapeY + shapeH * 0.42, shapeH * 0.18, 0, Math.PI * 2);
  ctx.rect(shapeX + shapeW * 0.50, shapeY + shapeH * 0.24, shapeW * 0.18, shapeH * 0.42);
  ctx.strokeStyle = rgbToCss(tint, 0.72);
  ctx.lineWidth = 2.5 + (threshold * 2.5);
  ctx.filter = `blur(${(6 + spread * 0.3 * softness).toFixed(1)}px)`;
  ctx.stroke();

  ctx.filter = "none";
  if (mode === "ink") {
    ctx.globalAlpha = clamp(getNumber(node, "ink_amount", 0.45), 0, 1) * 0.75;
    ctx.fillStyle = "rgba(0,0,0,0.65)";
    ctx.fillRect(shapeX, shapeY, shapeW, shapeH);
    ctx.globalAlpha = 1;
  } else {
    ctx.globalAlpha = 0.12 + (strength * 0.08);
    ctx.fillStyle = rgbToCss(tint, 1);
    ctx.beginPath();
    ctx.roundRect(shapeX, shapeY, shapeW, shapeH, 22);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  ctx.restore();

  ctx.fillStyle = "rgba(255,255,255,0.90)";
  ctx.font = "700 15px sans-serif";
  ctx.fillText("Edge Glow", area.x + 18, area.y + 28);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "rgba(230,236,242,0.66)";
  ctx.fillText(`mode ${mode}`, area.x + 18, area.y + 46);

  const swatchX = area.x + area.w - 74;
  const swatchY = area.y + 20;
  ctx.fillStyle = rgbToCss(tint, 1);
  ctx.beginPath();
  ctx.roundRect(swatchX, swatchY, 44, 18, 9);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.stroke();
}

function createLightLeakDecorator(node) {
  const wrap = document.createElement("div");
  wrap.className = "mkr-vfx-concept-chip-row";
  const startChip = document.createElement("div");
  startChip.className = "mkr-vfx-concept-chip";
  const endChip = document.createElement("div");
  endChip.className = "mkr-vfx-concept-chip";
  wrap.appendChild(startChip);
  wrap.appendChild(endChip);

  function refresh() {
    const [startColor, endColor] = getLightLeakRamp(node);
    startChip.style.boxShadow = `inset 0 0 0 999px ${rgbToCss(startColor, 0.14)}`;
    endChip.style.boxShadow = `inset 0 0 0 999px ${rgbToCss(endColor, 0.14)}`;
    startChip.innerHTML = `Ramp Start<span>${formatNumber(startColor[0])}, ${formatNumber(startColor[1])}, ${formatNumber(startColor[2])}</span>`;
    endChip.innerHTML = `Ramp End<span>${formatNumber(endColor[0])}, ${formatNumber(endColor[1])}, ${formatNumber(endColor[2])}</span>`;
  }

  refresh();
  return { element: wrap, refresh };
}

const NODE_CONFIGS = {
  x1LightLeak: {
    panelName: "mkr_vfx_light_leak_studio",
    title: "Light Leak Studio",
    subtitle: "Shape leak direction, scale, and ramp color with a visible flare preview instead of managing raw utility sliders.",
    accent: "#ffad74",
    size: [780, 900],
    defaults: {
      strength: 0.35,
      angle: 35.0,
      scale: 1.0,
      softness: 1.0,
      seed: 1337,
      ramp_preset: "warm",
      blend_mode: "screen",
      custom_start_r: 1.0,
      custom_start_g: 0.45,
      custom_start_b: 0.10,
      custom_end_r: 1.0,
      custom_end_g: 0.86,
      custom_end_b: 0.42,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      strength: { min: 0, max: 2 },
      angle: { min: 0, max: 360 },
      scale: { min: 0.2, max: 3 },
      softness: { min: 0.2, max: 3 },
      seed: { min: 0, max: 999999, integer: true },
      custom_start_r: { min: 0, max: 1 },
      custom_start_g: { min: 0, max: 1 },
      custom_start_b: { min: 0, max: 1 },
      custom_end_r: { min: 0, max: 1 },
      custom_end_g: { min: 0, max: 1 },
      custom_end_b: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["strength", "angle", "scale", "softness", "seed", "ramp_preset", "blend_mode", "custom_start_r", "custom_start_g", "custom_start_b", "custom_end_r", "custom_end_g", "custom_end_b", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "strength", 0.35)) },
      { label: "Angle", get: (node) => `${Math.round(getNumber(node, "angle", 35))}°` },
      { label: "Ramp", get: (node) => String(getValue(node, "ramp_preset", "warm")) },
    ],
    presets: [
      { label: "Warm", tone: "accent", values: { strength: 0.42, angle: 28, scale: 1.0, softness: 1.0, ramp_preset: "warm", blend_mode: "screen" } },
      { label: "Sunset", values: { strength: 0.62, angle: 46, scale: 1.25, softness: 1.3, ramp_preset: "sunset", blend_mode: "screen" } },
      { label: "Teal/Orange", values: { strength: 0.55, angle: 92, scale: 1.1, softness: 1.5, ramp_preset: "teal_orange", blend_mode: "soft_light" } },
    ],
    graph: {
      title: "Leak Preview",
      note: "angle + ramp",
      height: 234,
      draw: drawLightLeakPreview,
      readouts: [
        { label: "Blend", get: (node) => String(getValue(node, "blend_mode", "screen")) },
        { label: "Scale", get: (node) => formatNumber(getNumber(node, "scale", 1.0)) },
        { label: "Softness", get: (node) => formatNumber(getNumber(node, "softness", 1.0)) },
      ],
      help: "Presets set both the color ramp and the flare angle. Switch to custom ramp when you want manual endpoint colors.",
      decorate: createLightLeakDecorator,
    },
    sections: [
      {
        title: "Leak Geometry",
        note: "direction + spread",
        controls: [
          { key: "strength", label: "Strength", min: 0, max: 2, step: 0.01 },
          { key: "angle", label: "Angle", min: 0, max: 360, step: 1, decimals: 0 },
          { key: "scale", label: "Scale", min: 0.2, max: 3, step: 0.01 },
          { key: "softness", label: "Softness", min: 0.2, max: 3, step: 0.01 },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 999999 },
        ],
      },
      {
        title: "Ramp & Blend",
        note: "palette + composite",
        controls: [
          { type: "select", key: "ramp_preset", label: "Ramp Preset", options: [{ label: "warm", value: "warm" }, { label: "sunset", value: "sunset" }, { label: "teal_orange", value: "teal_orange" }, { label: "magenta_cyan", value: "magenta_cyan" }, { label: "custom", value: "custom" }] },
          { type: "select", key: "blend_mode", label: "Blend Mode", options: [{ label: "screen", value: "screen" }, { label: "add", value: "add" }, { label: "overlay", value: "overlay" }, { label: "soft_light", value: "soft_light" }] },
          { key: "custom_start_r", label: "Start R", min: 0, max: 1, step: 0.01 },
          { key: "custom_start_g", label: "Start G", min: 0, max: 1, step: 0.01 },
          { key: "custom_start_b", label: "Start B", min: 0, max: 1, step: 0.01 },
          { key: "custom_end_r", label: "End R", min: 0, max: 1, step: 0.01 },
          { key: "custom_end_g", label: "End G", min: 0, max: 1, step: 0.01 },
          { key: "custom_end_b", label: "End B", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the leak blends in." },
        ],
      },
    ],
  },
  x1SplitTone: {
    panelName: "mkr_vfx_split_tone_studio",
    title: "Split Tone Studio",
    subtitle: "Push shadows and highlights with an explicit toning ramp instead of balancing isolated hue and saturation sliders blindly.",
    accent: "#8ac5ff",
    size: [760, 790],
    defaults: {
      shadow_hue: 210.0,
      shadow_sat: 0.30,
      highlight_hue: 36.0,
      highlight_sat: 0.32,
      balance: 0.0,
      pivot: 0.50,
      mix: 0.75,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      shadow_hue: { min: 0, max: 360 },
      shadow_sat: { min: 0, max: 1 },
      highlight_hue: { min: 0, max: 360 },
      highlight_sat: { min: 0, max: 1 },
      balance: { min: -1, max: 1 },
      pivot: { min: 0, max: 1 },
      mix: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["shadow_hue", "shadow_sat", "highlight_hue", "highlight_sat", "balance", "pivot", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Shadows", get: (node) => `${Math.round(getNumber(node, "shadow_hue", 210))}°` },
      { label: "Highlights", get: (node) => `${Math.round(getNumber(node, "highlight_hue", 36))}°` },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 0.75)) },
    ],
    presets: [
      { label: "Film", tone: "accent", values: { shadow_hue: 214, shadow_sat: 0.22, highlight_hue: 42, highlight_sat: 0.26, balance: -0.05, pivot: 0.48, mix: 0.72 } },
      { label: "Teal/Orange", values: { shadow_hue: 198, shadow_sat: 0.40, highlight_hue: 31, highlight_sat: 0.36, balance: 0.02, pivot: 0.50, mix: 0.82 } },
      { label: "Copper", values: { shadow_hue: 246, shadow_sat: 0.18, highlight_hue: 18, highlight_sat: 0.42, balance: 0.08, pivot: 0.52, mix: 0.80 } },
    ],
    graph: {
      title: "Tone Ramp",
      note: "shadows / highlights",
      height: 210,
      draw: drawSplitTonePreview,
      readouts: [
        { label: "Balance", get: (node) => formatSigned(getNumber(node, "balance", 0), 2) },
        { label: "Pivot", get: (node) => formatNumber(getNumber(node, "pivot", 0.5)) },
      ],
      help: "Use balance to lean the handoff toward shadows or highlights. Pivot moves where the handoff happens.",
    },
    sections: [
      {
        title: "Toning",
        note: "shadow / highlight tint",
        controls: [
          { key: "shadow_hue", label: "Shadow Hue", min: 0, max: 360, step: 1, decimals: 0 },
          { key: "shadow_sat", label: "Shadow Sat", min: 0, max: 1, step: 0.01 },
          { key: "highlight_hue", label: "Highlight Hue", min: 0, max: 360, step: 1, decimals: 0 },
          { key: "highlight_sat", label: "Highlight Sat", min: 0, max: 1, step: 0.01 },
          { key: "balance", label: "Balance", min: -1, max: 1, step: 0.01 },
          { key: "pivot", label: "Pivot", min: 0, max: 1, step: 0.01 },
          { key: "mix", label: "Mix", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the split tone blends in." },
        ],
      },
    ],
  },
  x1SelectiveColor: {
    panelName: "mkr_vfx_selective_color_studio",
    title: "Selective Color Studio",
    subtitle: "Target a hue family, see the selection band, and push hue, saturation, and value with a clear region preview.",
    accent: "#7ceb98",
    size: [760, 860],
    defaults: {
      range_mode: "blues",
      custom_hue_center: 220.0,
      custom_hue_width: 30.0,
      hue_shift: 0.0,
      sat_shift: 0.20,
      value_shift: 0.0,
      softness: 20.0,
      amount: 1.0,
      preserve_luma: true,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      custom_hue_center: { min: 0, max: 360 },
      custom_hue_width: { min: 1, max: 180 },
      hue_shift: { min: -180, max: 180 },
      sat_shift: { min: -1, max: 1 },
      value_shift: { min: -1, max: 1 },
      softness: { min: 0, max: 120 },
      amount: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["preserve_luma", "invert_mask"],
    legacyNames: ["range_mode", "custom_hue_center", "custom_hue_width", "hue_shift", "sat_shift", "value_shift", "softness", "amount", "preserve_luma", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Range", get: (node) => String(getValue(node, "range_mode", "blues")) },
      { label: "Hue", get: (node) => formatSigned(getNumber(node, "hue_shift", 0), 1) },
      { label: "Amount", get: (node) => formatNumber(getNumber(node, "amount", 1.0)) },
    ],
    presets: [
      { label: "Blue Pop", tone: "accent", values: { range_mode: "blues", hue_shift: -8, sat_shift: 0.24, value_shift: 0.05, softness: 18, amount: 0.92, preserve_luma: true } },
      { label: "Foliage", values: { range_mode: "greens", hue_shift: 6, sat_shift: 0.16, value_shift: 0.02, softness: 24, amount: 0.84, preserve_luma: true } },
      { label: "Custom", values: { range_mode: "custom", custom_hue_center: 220, custom_hue_width: 42, hue_shift: -12, sat_shift: 0.30, value_shift: 0.08, softness: 30, amount: 0.92 } },
    ],
    graph: {
      title: "Hue Band Preview",
      note: "target / result",
      height: 220,
      draw: drawSelectiveColorPreview,
      readouts: [
        { label: "Sat Shift", get: (node) => formatSigned(getNumber(node, "sat_shift", 0.2), 2) },
        { label: "Val Shift", get: (node) => formatSigned(getNumber(node, "value_shift", 0), 2) },
      ],
      help: "In custom mode, center and width define the target band. Softness feathers the edges of the selection.",
    },
    sections: [
      {
        title: "Target Range",
        note: "selection",
        controls: [
          { type: "select", key: "range_mode", label: "Range", options: [{ label: "reds", value: "reds" }, { label: "yellows", value: "yellows" }, { label: "greens", value: "greens" }, { label: "cyans", value: "cyans" }, { label: "blues", value: "blues" }, { label: "magentas", value: "magentas" }, { label: "custom", value: "custom" }] },
          { key: "custom_hue_center", label: "Custom Center", min: 0, max: 360, step: 1, decimals: 0 },
          { key: "custom_hue_width", label: "Custom Width", min: 1, max: 180, step: 1, decimals: 0 },
          { key: "softness", label: "Softness", min: 0, max: 120, step: 0.5, decimals: 1 },
        ],
      },
      {
        title: "Color Moves",
        note: "hue / sat / value",
        controls: [
          { key: "hue_shift", label: "Hue Shift", min: -180, max: 180, step: 0.5, decimals: 1 },
          { key: "sat_shift", label: "Sat Shift", min: -1, max: 1, step: 0.01 },
          { key: "value_shift", label: "Value Shift", min: -1, max: 1, step: 0.01 },
          { key: "amount", label: "Amount", min: 0, max: 1, step: 0.01 },
          { type: "toggle", key: "preserve_luma", label: "Preserve Luma", description: "Keep luminance steadier while the hue range is pushed." },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the selective color blends in." },
        ],
      },
    ],
  },
  x1LensDistort: {
    panelName: "mkr_vfx_lens_distort_studio",
    title: "Lens Distort Studio",
    subtitle: "Shape barrel or pincushion response with visible grid warp, chromatic edge spread, and vignette instead of a bare optics utility form.",
    accent: "#79c3ff",
    size: [760, 720],
    defaults: {
      distortion: 0.12,
      chroma_aberration: 0.05,
      edge_vignette: 0.22,
      zoom_compensation: true,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      distortion: { min: -0.8, max: 0.8 },
      chroma_aberration: { min: 0, max: 0.35 },
      edge_vignette: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["zoom_compensation", "invert_mask"],
    legacyNames: ["distortion", "chroma_aberration", "edge_vignette", "zoom_compensation", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Distort", get: (node) => formatSigned(getNumber(node, "distortion", 0.12), 3) },
      { label: "CA", get: (node) => formatNumber(getNumber(node, "chroma_aberration", 0.05), 3) },
      { label: "Vignette", get: (node) => formatNumber(getNumber(node, "edge_vignette", 0.22)) },
    ],
    presets: [
      { label: "Barrel", tone: "accent", values: { distortion: 0.18, chroma_aberration: 0.07, edge_vignette: 0.26, zoom_compensation: true } },
      { label: "Pincushion", values: { distortion: -0.18, chroma_aberration: 0.06, edge_vignette: 0.12, zoom_compensation: true } },
      { label: "Vintage", values: { distortion: 0.10, chroma_aberration: 0.12, edge_vignette: 0.34, zoom_compensation: false } },
    ],
    graph: {
      title: "Lens Grid",
      note: "distort / CA",
      height: 214,
      draw: drawLensDistortPreview,
      readouts: [
        { label: "Zoom Comp", get: (node) => getBoolean(node, "zoom_compensation", true) ? "On" : "Off" },
      ],
      help: "Positive distortion gives a barrel response, negative distortion pulls toward pincushion. Zoom compensation tries to hold the frame size steadier.",
    },
    sections: [
      {
        title: "Lens Model",
        note: "shape + aberration",
        controls: [
          { key: "distortion", label: "Distortion", min: -0.8, max: 0.8, step: 0.001, decimals: 3 },
          { key: "chroma_aberration", label: "Chroma Aberration", min: 0, max: 0.35, step: 0.001, decimals: 3 },
          { key: "edge_vignette", label: "Edge Vignette", min: 0, max: 1, step: 0.01 },
          { type: "toggle", key: "zoom_compensation", label: "Zoom Compensation", description: "Scale inward slightly to keep more of the frame in view." },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the distortion blends in." },
        ],
      },
    ],
  },
  x1CRTScan: {
    panelName: "mkr_vfx_crt_scan_studio",
    title: "CRT Scan Studio",
    subtitle: "Dial scanline density, phosphor breakup, bloom bleed, and tube warp with a live monitor-style preview instead of tuning old utility sliders blind.",
    accent: "#8cffb1",
    size: [760, 860],
    defaults: {
      scanline_strength: 0.28,
      scanline_density: 1.0,
      phosphor_strength: 0.30,
      bloom_bleed: 0.22,
      warp_strength: 0.12,
      curvature: 0.18,
      noise_strength: 0.05,
      seed: 777,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      scanline_strength: { min: 0, max: 1 },
      scanline_density: { min: 0.2, max: 4 },
      phosphor_strength: { min: 0, max: 1 },
      bloom_bleed: { min: 0, max: 1 },
      warp_strength: { min: 0, max: 1 },
      curvature: { min: 0, max: 0.8 },
      noise_strength: { min: 0, max: 0.25 },
      seed: { min: 0, max: 999999, integer: true },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["scanline_strength", "scanline_density", "phosphor_strength", "bloom_bleed", "warp_strength", "curvature", "noise_strength", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Scan", get: (node) => formatNumber(getNumber(node, "scanline_strength", 0.28)) },
      { label: "Density", get: (node) => formatNumber(getNumber(node, "scanline_density", 1.0)) },
      { label: "Noise", get: (node) => formatNumber(getNumber(node, "noise_strength", 0.05), 3) },
    ],
    presets: [
      { label: "Broadcast", tone: "accent", values: { scanline_strength: 0.26, scanline_density: 0.95, phosphor_strength: 0.22, bloom_bleed: 0.12, warp_strength: 0.08, curvature: 0.10, noise_strength: 0.02 } },
      { label: "Arcade", values: { scanline_strength: 0.42, scanline_density: 1.45, phosphor_strength: 0.52, bloom_bleed: 0.30, warp_strength: 0.16, curvature: 0.22, noise_strength: 0.04 } },
      { label: "Late Night", values: { scanline_strength: 0.36, scanline_density: 1.20, phosphor_strength: 0.40, bloom_bleed: 0.42, warp_strength: 0.20, curvature: 0.28, noise_strength: 0.10 } },
    ],
    graph: {
      title: "CRT Preview",
      note: "scan / phosphor / warp",
      height: 240,
      draw: drawCRTScanPreview,
      readouts: [
        { label: "Phosphor", get: (node) => formatNumber(getNumber(node, "phosphor_strength", 0.30)) },
        { label: "Bloom", get: (node) => formatNumber(getNumber(node, "bloom_bleed", 0.22)) },
        { label: "Curve", get: (node) => formatNumber(getNumber(node, "curvature", 0.18)) },
      ],
      help: "Density changes line spacing, phosphor adds RGB triad breakup, and warp + curvature shape the tube feel together.",
    },
    sections: [
      {
        title: "Scan Structure",
        note: "lines + phosphor",
        controls: [
          { key: "scanline_strength", label: "Scanline Strength", min: 0, max: 1, step: 0.01 },
          { key: "scanline_density", label: "Scanline Density", min: 0.2, max: 4, step: 0.01 },
          { key: "phosphor_strength", label: "Phosphor Strength", min: 0, max: 1, step: 0.01 },
          { key: "bloom_bleed", label: "Bloom Bleed", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Tube Warp",
        note: "screen / noise",
        controls: [
          { key: "warp_strength", label: "Warp Strength", min: 0, max: 1, step: 0.01 },
          { key: "curvature", label: "Curvature", min: 0, max: 0.8, step: 0.01 },
          { key: "noise_strength", label: "Noise Strength", min: 0, max: 0.25, step: 0.005, decimals: 3 },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 999999 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the CRT pass blends in." },
        ],
      },
    ],
  },
  x1WarpDisplace: {
    panelName: "mkr_vfx_warp_displace_studio",
    title: "Warp Displace Studio",
    subtitle: "Push procedural or map-guided displacement with a visible field preview and keep advanced control maps as optional graph inputs.",
    accent: "#7bc9ff",
    size: [760, 780],
    defaults: {
      displace_strength: 12.0,
      base_direction: 0.0,
      noise_scale: 64.0,
      noise_mix: 0.35,
      seed: 321,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      displace_strength: { min: 0, max: 128 },
      base_direction: { min: 0, max: 360 },
      noise_scale: { min: 2, max: 512 },
      noise_mix: { min: 0, max: 1 },
      seed: { min: 0, max: 999999, integer: true },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["displace_strength", "base_direction", "noise_scale", "noise_mix", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => `${Math.round(getNumber(node, "displace_strength", 12.0))} px` },
      { label: "Direction", get: (node) => `${Math.round(getNumber(node, "base_direction", 0))}°` },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "noise_mix", 0.35)) },
    ],
    presets: [
      { label: "Heat Drift", tone: "accent", values: { displace_strength: 8.0, base_direction: 90, noise_scale: 96, noise_mix: 0.72 } },
      { label: "Shear", values: { displace_strength: 18.0, base_direction: 0, noise_scale: 46, noise_mix: 0.18 } },
      { label: "Liquid Warp", values: { displace_strength: 26.0, base_direction: 36, noise_scale: 72, noise_mix: 0.68 } },
    ],
    graph: {
      title: "Displacement Field",
      note: "direction / noise",
      height: 226,
      draw: drawWarpDisplacePreview,
      readouts: [
        { label: "Noise Scale", get: (node) => formatNumber(getNumber(node, "noise_scale", 64.0), 1) },
        { label: "Dir Map", get: (node) => hasInputLink(node, "direction_map") ? "Live" : "Proc" },
        { label: "Strength Map", get: (node) => hasInputLink(node, "strength_map") ? "Live" : "Uniform" },
      ],
      help: "Use the advanced inputs only when you need art-directed warp. Without them, the node stays compact and procedural.",
    },
    sections: [
      {
        title: "Field Motion",
        note: "strength + flow",
        controls: [
          { key: "displace_strength", label: "Strength", min: 0, max: 128, step: 0.1, decimals: 1 },
          { key: "base_direction", label: "Base Direction", min: 0, max: 360, step: 1, decimals: 0 },
          { key: "noise_scale", label: "Noise Scale", min: 2, max: 512, step: 1, decimals: 0 },
          { key: "noise_mix", label: "Noise Mix", min: 0, max: 1, step: 0.01 },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 999999 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the warp blends in." },
        ],
      },
    ],
  },
  x1GlowEdges: {
    panelName: "mkr_vfx_glow_edges_studio",
    title: "Glow Edges Studio",
    subtitle: "Extract contour energy, spread it into a colored glow, and preview the edge composite instead of juggling threshold and tint fields in a raw form.",
    accent: "#93fff0",
    size: [760, 880],
    defaults: {
      edge_threshold: 0.22,
      edge_softness: 1.0,
      glow_spread: 8.0,
      glow_strength: 1.0,
      tint_r: 0.56,
      tint_g: 0.92,
      tint_b: 1.0,
      composite_mode: "screen",
      ink_amount: 0.45,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      edge_threshold: { min: 0, max: 1 },
      edge_softness: { min: 0.1, max: 4 },
      glow_spread: { min: 0, max: 64 },
      glow_strength: { min: 0, max: 3 },
      tint_r: { min: 0, max: 1 },
      tint_g: { min: 0, max: 1 },
      tint_b: { min: 0, max: 1 },
      ink_amount: { min: 0, max: 1 },
      mask_feather: { min: 0, max: 256 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["edge_threshold", "edge_softness", "glow_spread", "glow_strength", "tint_r", "tint_g", "tint_b", "composite_mode", "ink_amount", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Threshold", get: (node) => formatNumber(getNumber(node, "edge_threshold", 0.22)) },
      { label: "Spread", get: (node) => formatNumber(getNumber(node, "glow_spread", 8.0), 1) },
      { label: "Mode", get: (node) => String(getValue(node, "composite_mode", "screen")) },
    ],
    presets: [
      { label: "Screen Glow", tone: "accent", values: { edge_threshold: 0.22, edge_softness: 1.2, glow_spread: 9.0, glow_strength: 1.0, tint_r: 0.56, tint_g: 0.92, tint_b: 1.0, composite_mode: "screen", ink_amount: 0.45 } },
      { label: "Soft Add", values: { edge_threshold: 0.16, edge_softness: 1.4, glow_spread: 14.0, glow_strength: 1.6, tint_r: 1.0, tint_g: 0.82, tint_b: 0.44, composite_mode: "add", ink_amount: 0.30 } },
      { label: "Ink Trace", values: { edge_threshold: 0.28, edge_softness: 0.9, glow_spread: 4.0, glow_strength: 0.8, tint_r: 0.52, tint_g: 0.96, tint_b: 1.0, composite_mode: "ink", ink_amount: 0.62 } },
    ],
    graph: {
      title: "Edge Composite",
      note: "glow / contour",
      height: 224,
      draw: drawGlowEdgesPreview,
      readouts: [
        { label: "Strength", get: (node) => formatNumber(getNumber(node, "glow_strength", 1.0)) },
        { label: "Softness", get: (node) => formatNumber(getNumber(node, "edge_softness", 1.0)) },
        { label: "Ink", get: (node) => formatNumber(getNumber(node, "ink_amount", 0.45)) },
      ],
      help: "Threshold finds the contour energy, spread controls the halo radius, and ink mode uses the same edge key to darken instead of glow.",
    },
    sections: [
      {
        title: "Edge Key",
        note: "threshold + spread",
        controls: [
          { key: "edge_threshold", label: "Threshold", min: 0, max: 1, step: 0.01 },
          { key: "edge_softness", label: "Softness", min: 0.1, max: 4, step: 0.01 },
          { key: "glow_spread", label: "Spread", min: 0, max: 64, step: 0.5, decimals: 1 },
          { key: "glow_strength", label: "Strength", min: 0, max: 3, step: 0.01 },
        ],
      },
      {
        title: "Tint & Composite",
        note: "color + mode",
        controls: [
          { key: "tint_r", label: "Tint R", min: 0, max: 1, step: 0.01 },
          { key: "tint_g", label: "Tint G", min: 0, max: 1, step: 0.01 },
          { key: "tint_b", label: "Tint B", min: 0, max: 1, step: 0.01 },
          { type: "select", key: "composite_mode", label: "Composite Mode", options: [{ label: "screen", value: "screen" }, { label: "add", value: "add" }, { label: "soft_light", value: "soft_light" }, { label: "ink", value: "ink" }] },
          { key: "ink_amount", label: "Ink Amount", min: 0, max: 1, step: 0.01 },
        ],
      },
      {
        title: "Mask Output",
        note: "delivery",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the edge composite blends in." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

function buildPanel(node, config) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT VFX",
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

  let decorator = null;
  if (typeof config.graph.decorate === "function") {
    decorator = config.graph.decorate(node);
    if (decorator?.element) graphSection.body.appendChild(decorator.element);
  }

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
    try {
      decorator?.refresh?.();
    } catch (error) {
      console.warn(`[${EXTENSION_NAME}] decorator refresh failed`, error);
    }
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

  if (node.__mkrVfxConceptSignalPanelInstalled) {
    node.__mkrVfxConceptSignalRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrVfxConceptSignalPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrVfxConceptSignalRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrVfxConceptSignalRefreshHooksInstalled", refresh);
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
      const nodeName = String(node?.comfyClass || node?.type || "");
      if (TARGET_NAMES.has(nodeName)) {
        prepareNode(node);
      }
    }
  },
});
