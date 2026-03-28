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

const EXTENSION_NAME = "MKRShift.TextureStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-texture-studios-v1";
const MAX_SEED = 2147483647;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function fract(value) {
  return value - Math.floor(value);
}

function noise2D(x, y, seed = 0) {
  return fract(Math.sin((x * 127.1) + (y * 311.7) + (seed * 17.13)) * 43758.5453123);
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

function fillChecker(ctx, frame, tileSize = 18, a = "rgba(255,255,255,0.035)", b = "rgba(255,255,255,0.012)") {
  const rows = Math.ceil(frame.h / tileSize);
  const cols = Math.ceil(frame.w / tileSize);
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      ctx.fillStyle = (row + col) % 2 === 0 ? a : b;
      ctx.fillRect(frame.x + (col * tileSize), frame.y + (row * tileSize), tileSize, tileSize);
    }
  }
}

function fillMacroField(ctx, frame, seed, hueShift = 0, satAmount = 0.1, valueAmount = 0.2) {
  const cellsX = 8;
  const cellsY = 5;
  const cellW = frame.w / cellsX;
  const cellH = frame.h / cellsY;
  for (let row = 0; row < cellsY; row += 1) {
    for (let col = 0; col < cellsX; col += 1) {
      const n = noise2D(col * 0.8, row * 0.9, seed);
      const hue = ((208 + (hueShift * 420) + (n * 92)) % 360 + 360) % 360;
      const sat = clamp(22 + (satAmount * 68) + (n * 18), 10, 96);
      const light = clamp(20 + (n * (18 + (valueAmount * 44))), 12, 84);
      ctx.fillStyle = `hsl(${hue} ${sat}% ${light}%)`;
      ctx.fillRect(frame.x + (col * cellW), frame.y + (row * cellH), Math.ceil(cellW) + 1, Math.ceil(cellH) + 1);
    }
  }
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

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-texture-select,
    .mkr-texture-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-texture-select {
      margin-top: 4px;
    }

    .mkr-texture-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      margin-top: 4px;
    }

    .mkr-texture-callout {
      margin-top: 6px;
      padding: 7px 8px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.035);
      font-size: 10px;
      color: rgba(233,239,244,0.62);
      line-height: 1.35;
    }
  `;
  document.head.appendChild(style);
}

function createSeedControl({ label, value, min, max, onChange, onReseed }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const wrap = document.createElement("div");
  wrap.className = "mkr-texture-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-texture-number";
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

function createNumberControl({ label, value, min, max, step, decimals = 2, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${Number(value).toFixed(decimals)}</span>`;

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-texture-number";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  input.addEventListener("change", () => {
    const parsed = Number.parseFloat(String(input.value));
    const next = Number.isFinite(parsed) ? clamp(parsed, min, max) : Number(value);
    input.value = String(next);
    head.lastChild.textContent = Number(next).toFixed(decimals);
    onChange?.(next);
  });

  root.appendChild(head);
  root.appendChild(input);
  return {
    element: root,
    setValue(next) {
      const normalized = Number.isFinite(Number(next)) ? clamp(Number(next), min, max) : Number(value);
      input.value = String(normalized);
      head.lastChild.textContent = normalized.toFixed(decimals);
    },
  };
}

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const select = document.createElement("select");
  select.className = "mkr-texture-select";
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
  node.onConfigure = function onConfigureTexturePanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeTexturePanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedTexturePanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawOffsetPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(116,209,255,0.32)");
  fillChecker(ctx, frame, 22);

  const shiftX = getNumber(node, "offset_x", config.defaults.offset_x);
  const shiftY = getNumber(node, "offset_y", config.defaults.offset_y);
  const seamWidth = getNumber(node, "seam_width", config.defaults.seam_width);
  const seamSoftness = getNumber(node, "seam_softness", config.defaults.seam_softness);
  const mode = String(getValue(node, "mode", config.defaults.mode));

  const modeScale = mode === "half_tile" ? 0.5 : (mode === "pixels" ? clamp(shiftX / 256, -1, 1) : shiftX);
  const modeScaleY = mode === "half_tile" ? 0.5 : (mode === "pixels" ? clamp(shiftY / 256, -1, 1) : shiftY);
  const splitX = frame.x + (frame.w * fract(Math.abs(modeScale)));
  const splitY = frame.y + (frame.h * fract(Math.abs(modeScaleY)));

  const tex = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  tex.addColorStop(0, "rgba(145,121,89,0.38)");
  tex.addColorStop(0.5, "rgba(116,128,141,0.18)");
  tex.addColorStop(1, "rgba(70,95,130,0.28)");
  ctx.fillStyle = tex;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.strokeStyle = "rgba(244,248,252,0.16)";
  ctx.lineWidth = 1;
  for (let step = 1; step < 4; step += 1) {
    const x = frame.x + ((frame.w * step) / 4);
    const y = frame.y + ((frame.h * step) / 4);
    ctx.beginPath();
    ctx.moveTo(x, frame.y);
    ctx.lineTo(x, frame.y + frame.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(frame.x, y);
    ctx.lineTo(frame.x + frame.w, y);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,162,87,0.12)";
  ctx.fillRect(splitX - (seamWidth * 0.5), frame.y, Math.max(2, seamWidth), frame.h);
  ctx.fillRect(frame.x, splitY - (seamWidth * 0.5), frame.w, Math.max(2, seamWidth));

  ctx.strokeStyle = "rgba(255,214,138,0.85)";
  ctx.lineWidth = Math.max(1, seamSoftness * 0.25);
  ctx.beginPath();
  ctx.moveTo(splitX, frame.y);
  ctx.lineTo(splitX, frame.y + frame.h);
  ctx.moveTo(frame.x, splitY);
  ctx.lineTo(frame.x + frame.w, splitY);
  ctx.stroke();

  ctx.strokeStyle = "rgba(122,220,255,0.78)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(frame.x + 34, frame.y + frame.h - 26);
  ctx.lineTo(frame.x + 84, frame.y + frame.h - 26);
  ctx.lineTo(frame.x + 76, frame.y + frame.h - 34);
  ctx.moveTo(frame.x + 84, frame.y + frame.h - 26);
  ctx.lineTo(frame.x + 76, frame.y + frame.h - 18);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(frame.x + 34, frame.y + frame.h - 26);
  ctx.lineTo(frame.x + 34, frame.y + frame.h - 76);
  ctx.lineTo(frame.x + 26, frame.y + frame.h - 68);
  ctx.moveTo(frame.x + 34, frame.y + frame.h - 76);
  ctx.lineTo(frame.x + 42, frame.y + frame.h - 68);
  ctx.stroke();

  drawLabel(ctx, "offset tile split", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.8)", 10);
}

function drawSeamlessPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(123,245,199,0.28)");
  fillChecker(ctx, frame, 20, "rgba(255,255,255,0.03)", "rgba(255,255,255,0.01)");

  const blendWidth = getNumber(node, "blend_width", config.defaults.blend_width);
  const seamBlur = getNumber(node, "seam_blur", config.defaults.seam_blur);
  const seamSoftness = getNumber(node, "seam_softness", config.defaults.seam_softness);
  const edgeMatch = getNumber(node, "edge_match_strength", config.defaults.edge_match_strength);
  const detail = getNumber(node, "detail_preserve", config.defaults.detail_preserve);

  const midX = frame.x + (frame.w / 2);
  const midY = frame.y + (frame.h / 2);
  const bandX = clamp((blendWidth / 96) * frame.w * 0.24, 10, frame.w * 0.28);
  const bandY = clamp((blendWidth / 96) * frame.h * 0.24, 10, frame.h * 0.28);

  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  bg.addColorStop(0, "rgba(97,123,154,0.20)");
  bg.addColorStop(0.5, "rgba(95,117,91,0.10)");
  bg.addColorStop(1, "rgba(145,123,94,0.20)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const cross = ctx.createRadialGradient(midX, midY, 2, midX, midY, Math.max(bandX, bandY) + (seamBlur * 0.6));
  cross.addColorStop(0, "rgba(255,255,255,0.24)");
  cross.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = cross;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.fillStyle = `rgba(122,245,201,${0.10 + (edgeMatch * 0.15)})`;
  ctx.fillRect(midX - bandX, frame.y, bandX * 2, frame.h);
  ctx.fillRect(frame.x, midY - bandY, frame.w, bandY * 2);

  ctx.strokeStyle = "rgba(255,255,255,0.48)";
  ctx.lineWidth = Math.max(1, seamSoftness * 0.12);
  ctx.beginPath();
  ctx.moveTo(midX, frame.y + 8);
  ctx.lineTo(midX, frame.y + frame.h - 8);
  ctx.moveTo(frame.x + 8, midY);
  ctx.lineTo(frame.x + frame.w - 8, midY);
  ctx.stroke();

  ctx.strokeStyle = "rgba(122,245,201,0.92)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(frame.x + 18, frame.y + frame.h - 26);
  ctx.bezierCurveTo(frame.x + 68, frame.y + frame.h - 66, midX - 34, frame.y + 54, midX, midY);
  ctx.bezierCurveTo(midX + 34, frame.y + 54, frame.x + frame.w - 68, frame.y + frame.h - 66, frame.x + frame.w - 18, frame.y + frame.h - 26);
  ctx.stroke();

  drawLabel(ctx, `detail ${formatNumber(detail, 2)}`, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.76)", 10);
}

function drawEdgePadPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(204,248,120,0.28)");
  fillChecker(ctx, frame, 20);

  const padPixels = getNumber(node, "pad_pixels", config.defaults.pad_pixels);
  const threshold = getNumber(node, "alpha_threshold", config.defaults.alpha_threshold);
  const expandAlpha = getBoolean(node, "expand_alpha", config.defaults.expand_alpha);
  const sourceMode = String(getValue(node, "source_mode", config.defaults.source_mode));

  ctx.fillStyle = "rgba(35,42,49,0.92)";
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const centerX = frame.x + (frame.w * 0.48);
  const centerY = frame.y + (frame.h * 0.54);
  const radius = Math.min(frame.w, frame.h) * 0.24;
  const halo = clamp(padPixels / 72, 0.08, 0.48) * radius;

  ctx.fillStyle = "rgba(182,248,99,0.18)";
  ctx.beginPath();
  ctx.moveTo(centerX - radius * 1.05 - halo, centerY + radius * 0.1);
  ctx.bezierCurveTo(centerX - radius * 0.95, centerY - radius * 1.15 - halo, centerX + radius * 0.76 + halo, centerY - radius * 1.0, centerX + radius * 0.92 + halo, centerY + radius * 0.16);
  ctx.bezierCurveTo(centerX + radius * 0.72, centerY + radius * 1.04 + halo, centerX - radius * 0.9 - halo, centerY + radius * 0.92, centerX - radius * 1.05 - halo, centerY + radius * 0.1);
  ctx.fill();

  ctx.fillStyle = sourceMode === "mask" ? "rgba(116,209,255,0.78)" : "rgba(255,255,255,0.90)";
  ctx.beginPath();
  ctx.moveTo(centerX - radius, centerY + radius * 0.12);
  ctx.bezierCurveTo(centerX - radius * 0.88, centerY - radius * 0.92, centerX + radius * 0.62, centerY - radius * 0.82, centerX + radius * 0.78, centerY + radius * 0.1);
  ctx.bezierCurveTo(centerX + radius * 0.54, centerY + radius * 0.76, centerX - radius * 0.76, centerY + radius * 0.66, centerX - radius, centerY + radius * 0.12);
  ctx.fill();

  if (expandAlpha) {
    ctx.strokeStyle = "rgba(255,206,102,0.92)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  drawLabel(ctx, `threshold ${formatNumber(threshold, 3)}`, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.76)", 10);
}

function drawDelightPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,218,121,0.30)");
  const flatten = getNumber(node, "flatten_strength", config.defaults.flatten_strength);
  const shadow = getNumber(node, "shadow_lift", config.defaults.shadow_lift);
  const highlight = getNumber(node, "highlight_compress", config.defaults.highlight_compress);
  const saturationRestore = getNumber(node, "saturation_restore", config.defaults.saturation_restore);
  const detail = getNumber(node, "detail_preserve", config.defaults.detail_preserve);

  const grad = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y);
  grad.addColorStop(0, "rgba(66,72,84,1)");
  grad.addColorStop(0.35, "rgba(122,126,132,1)");
  grad.addColorStop(1, "rgba(245,232,188,1)");
  ctx.fillStyle = grad;
  ctx.fillRect(frame.x, frame.y + frame.h - 28, frame.w, 16);

  ctx.strokeStyle = "rgba(255,255,255,0.38)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(frame.x, frame.y + frame.h - 18);
  ctx.lineTo(frame.x + frame.w, frame.y + 16);
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,206,126,0.96)";
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  for (let step = 0; step <= 96; step += 1) {
    const t = step / 96;
    const x = frame.x + (frame.w * t);
    let y = t;
    y = Math.pow(y, Math.max(0.35, 1.0 - (shadow * 0.25)));
    y = 1.0 - Math.pow(1.0 - y, Math.max(0.45, 1.0 - (highlight * 0.20)));
    y = clamp((y * (1.0 - (flatten * 0.18))) + (flatten * 0.09), 0, 1);
    const py = frame.y + ((1 - y) * (frame.h - 48));
    if (step === 0) ctx.moveTo(x, py);
    else ctx.lineTo(x, py);
  }
  ctx.stroke();

  ctx.fillStyle = `rgba(255,214,112,${0.16 + (saturationRestore * 0.16)})`;
  ctx.fillRect(frame.x + 14, frame.y + 16, frame.w - 28, 18);
  drawLabel(ctx, `detail ${formatNumber(detail, 2)}`, frame.x + 14, frame.y + 25, "rgba(22,25,31,0.82)", 10);
}

function drawMacroVariationPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(155,118,255,0.28)");
  const seed = Math.round(getNumber(node, "seed", config.defaults.seed));
  const hueVar = getNumber(node, "hue_variation", config.defaults.hue_variation);
  const satVar = getNumber(node, "saturation_variation", config.defaults.saturation_variation);
  const valueVar = getNumber(node, "value_variation", config.defaults.value_variation);
  const contrastVar = getNumber(node, "contrast_variation", config.defaults.contrast_variation);

  fillMacroField(ctx, frame, seed, hueVar, satVar, valueVar);

  ctx.fillStyle = `rgba(255,255,255,${0.04 + (contrastVar * 0.12)})`;
  for (let i = 0; i < 7; i += 1) {
    const bandX = frame.x + (frame.w * noise2D(i + 0.2, 1.4, seed + 9));
    const bandW = 18 + (noise2D(i + 0.6, 2.1, seed + 11) * 46);
    ctx.fillRect(bandX, frame.y, bandW, frame.h);
  }

  drawLabel(ctx, "macro breakup field", frame.x + 10, frame.y + 14, "rgba(245,247,250,0.76)", 10);
}

function drawDetilePreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(115,231,202,0.28)");
  fillChecker(ctx, frame, 20, "rgba(255,255,255,0.04)", "rgba(255,255,255,0.012)");

  const blendStrength = getNumber(node, "blend_strength", config.defaults.blend_strength);
  const colorMatchBlur = getNumber(node, "color_match_blur", config.defaults.color_match_blur);
  const breakup = getNumber(node, "variation_breakup", config.defaults.variation_breakup);
  const seed = Math.round(getNumber(node, "seed", config.defaults.seed));

  const tilesX = 6;
  const tilesY = 4;
  const cellW = frame.w / tilesX;
  const cellH = frame.h / tilesY;
  for (let row = 0; row < tilesY; row += 1) {
    for (let col = 0; col < tilesX; col += 1) {
      const base = noise2D(col, row, seed);
      ctx.fillStyle = `hsl(${200 + (base * 28)} 28% ${26 + (base * 15)}%)`;
      ctx.fillRect(frame.x + (col * cellW), frame.y + (row * cellH), Math.ceil(cellW), Math.ceil(cellH));
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.strokeRect(frame.x + (col * cellW), frame.y + (row * cellH), Math.ceil(cellW), Math.ceil(cellH));
    }
  }

  const overlay = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  overlay.addColorStop(0, `rgba(116,231,204,${0.10 + (blendStrength * 0.18)})`);
  overlay.addColorStop(1, `rgba(255,192,107,${0.04 + (breakup * 0.16)})`);
  ctx.fillStyle = overlay;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.strokeStyle = "rgba(255,255,255,0.42)";
  ctx.setLineDash([8, 6]);
  ctx.beginPath();
  ctx.moveTo(frame.x + (frame.w * 0.5), frame.y);
  ctx.lineTo(frame.x + (frame.w * 0.5), frame.y + frame.h);
  ctx.moveTo(frame.x, frame.y + (frame.h * 0.5));
  ctx.lineTo(frame.x + frame.w, frame.y + (frame.h * 0.5));
  ctx.stroke();
  ctx.setLineDash([]);

  drawLabel(ctx, `match blur ${formatNumber(colorMatchBlur, 1)} px`, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.76)", 10);
}

function drawAlbedoPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,228,150,0.30)");
  const black = getNumber(node, "target_black", config.defaults.target_black);
  const white = getNumber(node, "target_white", config.defaults.target_white);
  const satLimit = getNumber(node, "saturation_limit", config.defaults.saturation_limit);
  const shadowLift = getNumber(node, "shadow_lift", config.defaults.shadow_lift);
  const highlight = getNumber(node, "highlight_rolloff", config.defaults.highlight_rolloff);
  const midtone = getNumber(node, "midtone_preserve", config.defaults.midtone_preserve);

  const grad = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y);
  grad.addColorStop(0, "rgba(41,43,48,1)");
  grad.addColorStop(0.45, "rgba(148,136,112,1)");
  grad.addColorStop(1, "rgba(240,233,214,1)");
  ctx.fillStyle = grad;
  ctx.fillRect(frame.x, frame.y + frame.h - 24, frame.w, 14);

  ctx.strokeStyle = "rgba(255,255,255,0.34)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(frame.x, frame.y + frame.h - 18);
  ctx.lineTo(frame.x + frame.w, frame.y + 20);
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,217,122,0.95)";
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  for (let step = 0; step <= 90; step += 1) {
    const t = step / 90;
    const x = frame.x + (frame.w * t);
    let y = black + (t * Math.max(0.001, white - black));
    y = clamp((y * (1 - (midtone * 0.12))) + (((1 - Math.abs((t - 0.5) / 0.5)) * midtone) * 0.08), 0, 1);
    y = clamp((y * (1 + (shadowLift * 0.08))) - (highlight * 0.05 * t), 0, 1);
    const py = frame.y + ((1 - y) * (frame.h - 46));
    if (step === 0) ctx.moveTo(x, py);
    else ctx.lineTo(x, py);
  }
  ctx.stroke();

  ctx.fillStyle = `rgba(145,228,173,${0.12 + (satLimit * 0.12)})`;
  ctx.fillRect(frame.x + 12, frame.y + 16, frame.w - 24, 18);
  drawLabel(ctx, `sat limit ${formatNumber(satLimit, 2)}`, frame.x + 18, frame.y + 25, "rgba(25,28,34,0.84)", 10);
}

function drawNoisePreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(133,196,255,0.28)");
  const seed = Math.round(getNumber(node, "seed", config.defaults.seed));
  const balance = getNumber(node, "balance", config.defaults.balance);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const detailMix = getNumber(node, "detail_mix", config.defaults.detail_mix);
  const invert = getBoolean(node, "invert", config.defaults.invert);
  const variant = String(getValue(node, "variant", config.defaults.variant));

  const cells = 18;
  const cellW = frame.w / cells;
  const cellH = frame.h / cells;
  for (let y = 0; y < cells; y += 1) {
    for (let x = 0; x < cells; x += 1) {
      const base = noise2D(x * 0.8, y * 0.8, seed);
      const fine = noise2D((x * 2.4) + 0.3, (y * 2.4) + 0.8, seed + 17);
      let value = lerp(base, fine, detailMix * 0.65);
      value = clamp(((value - 0.5) * contrast) + 0.5 + (balance * 0.2), 0, 1);
      if (invert) value = 1 - value;
      const shade = Math.round(value * 255);
      ctx.fillStyle = `rgb(${shade}, ${shade}, ${shade})`;
      ctx.fillRect(frame.x + (x * cellW), frame.y + (y * cellH), Math.ceil(cellW) + 1, Math.ceil(cellH) + 1);
    }
  }

  drawLabel(ctx, variant, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
}

function drawCellPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(122,245,201,0.28)");
  fillChecker(ctx, frame, 22, "rgba(255,255,255,0.03)", "rgba(255,255,255,0.012)");
  const seed = Math.round(getNumber(node, "seed", config.defaults.seed));
  const jitter = getNumber(node, "jitter", config.defaults.jitter);
  const edge = getNumber(node, "edge_width", config.defaults.edge_width);
  const softness = getNumber(node, "softness", config.defaults.softness);
  const mode = String(getValue(node, "pattern_mode", config.defaults.pattern_mode));

  const points = [];
  for (let i = 0; i < 10; i += 1) {
    points.push({
      x: frame.x + 24 + ((i % 5) * (frame.w / 5)) + ((noise2D(i, 1.2, seed) - 0.5) * 40 * jitter),
      y: frame.y + 24 + (Math.floor(i / 5) * (frame.h / 2.2)) + ((noise2D(i, 2.8, seed + 3) - 0.5) * 40 * jitter),
    });
  }

  ctx.strokeStyle = `rgba(244,248,252,${0.34 + (edge * 0.45)})`;
  ctx.lineWidth = 1 + (edge * 5);
  for (let i = 0; i < points.length; i += 1) {
    const point = points[i];
    const radius = 28 + (noise2D(i, 0.7, seed + 9) * 30);
    ctx.beginPath();
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
    ctx.stroke();
    if (mode === "fill" || mode === "bevel") {
      ctx.fillStyle = `rgba(122,245,201,${0.04 + (softness * 0.14)})`;
      ctx.fill();
    }
  }

  drawLabel(ctx, mode, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
}

function drawStrataPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,181,113,0.28)");
  const direction = getNumber(node, "direction_deg", config.defaults.direction_deg);
  const warp = getNumber(node, "warp_strength", config.defaults.warp_strength);
  const breakup = getNumber(node, "breakup_strength", config.defaults.breakup_strength);
  const micro = getNumber(node, "micro_breakup", config.defaults.micro_breakup);
  const profile = String(getValue(node, "profile", config.defaults.profile));

  ctx.save();
  ctx.translate(frame.x + (frame.w / 2), frame.y + (frame.h / 2));
  ctx.rotate((direction * Math.PI) / 180);
  ctx.translate(-(frame.x + (frame.w / 2)), -(frame.y + (frame.h / 2)));
  for (let i = -3; i < 8; i += 1) {
    const y = frame.y + (i * 24);
    const offset = Math.sin((i * 0.65) + warp * 4.2) * 16;
    ctx.strokeStyle = `rgba(245,208,142,${0.18 + (breakup * 0.28)})`;
    ctx.lineWidth = 8 + (micro * 8);
    ctx.beginPath();
    ctx.moveTo(frame.x - 30, y + offset);
    ctx.bezierCurveTo(frame.x + (frame.w * 0.35), y - offset, frame.x + (frame.w * 0.65), y + offset, frame.x + frame.w + 30, y - offset);
    ctx.stroke();
  }
  ctx.restore();

  drawLabel(ctx, profile, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
}

const NODE_CONFIGS = {
  x1TextureOffset: {
    panelName: "mkrX1TextureOffsetStudio",
    size: [760, 640],
    accent: "#74d1ff",
    title: "Texture Offset Studio",
    subtitle: "Shift a tile target, inspect the split, and tune seam coverage without hunting through primitive controls.",
    defaults: {
      mode: "half_tile",
      offset_x: 0.5,
      offset_y: 0.5,
      seam_width: 6.0,
      seam_softness: 3.0,
    },
    numericSpecs: {
      offset_x: { min: -4096.0, max: 4096.0 },
      offset_y: { min: -4096.0, max: 4096.0 },
      seam_width: { min: 0.0, max: 256.0 },
      seam_softness: { min: 0.0, max: 256.0 },
    },
    booleanKeys: [],
    legacyNames: ["mode", "offset_x", "offset_y", "seam_width", "seam_softness"],
    metrics: [
      { label: "Shift X", get: (node) => formatSigned(getNumber(node, "offset_x", 0), 2) },
      { label: "Shift Y", get: (node) => formatSigned(getNumber(node, "offset_y", 0), 2) },
      { label: "Seam", get: (node) => `${formatNumber(getNumber(node, "seam_width", 6), 1)} px` },
    ],
    presets: [
      { label: "Half Tile", tone: "accent", values: { mode: "half_tile", offset_x: 0.5, offset_y: 0.5, seam_width: 6.0, seam_softness: 3.0 } },
      { label: "Quarter", values: { mode: "fraction", offset_x: 0.25, offset_y: 0.25, seam_width: 4.0, seam_softness: 2.0 } },
      { label: "Brick", values: { mode: "fraction", offset_x: 0.5, offset_y: 0.0, seam_width: 5.0, seam_softness: 2.5 } },
    ],
    graph: {
      title: "Offset Preview",
      note: "tile split",
      height: 214,
      help: "The preview sketches where the seam cross lands after the roll so you can set up a tile-safe working position before seam cleanup.",
      readouts: [
        { label: "Mode", get: (node) => String(getValue(node, "mode", "half_tile")) },
        { label: "Softness", get: (node) => `${formatNumber(getNumber(node, "seam_softness", 3), 1)} px` },
      ],
      draw: drawOffsetPreview,
    },
    sections: [
      {
        title: "Offset",
        note: "shift target",
        controls: [
          { key: "mode", type: "select", label: "Mode", options: [{ label: "Half Tile", value: "half_tile" }, { label: "Fraction", value: "fraction" }, { label: "Pixels", value: "pixels" }] },
          { key: "offset_x", type: "number", label: "Offset X", min: -4096.0, max: 4096.0, step: 0.01, decimals: 2 },
          { key: "offset_y", type: "number", label: "Offset Y", min: -4096.0, max: 4096.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Seam Mask",
        note: "preview coverage",
        controls: [
          { key: "seam_width", label: "Seam Width", min: 0.0, max: 48.0, step: 0.5, decimals: 1 },
          { key: "seam_softness", label: "Seam Softness", min: 0.0, max: 48.0, step: 0.5, decimals: 1 },
        ],
      },
    ],
  },
  x1TextureSeamless: {
    panelName: "mkrX1TextureSeamlessStudio",
    size: [780, 810],
    accent: "#7cf5c9",
    title: "Texture Seamless Studio",
    subtitle: "Tune cross-blend and low-frequency edge matching together so seam removal feels deliberate instead of trial and error.",
    defaults: {
      blend_width: 24.0,
      edge_match_strength: 0.85,
      edge_match_blur: 18.0,
      detail_preserve: 0.65,
      seam_blur: 12.0,
      seam_softness: 12.0,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      blend_width: { min: 1.0, max: 512.0 },
      edge_match_strength: { min: 0.0, max: 1.0 },
      edge_match_blur: { min: 0.0, max: 256.0 },
      detail_preserve: { min: 0.0, max: 1.0 },
      seam_blur: { min: 0.0, max: 256.0 },
      seam_softness: { min: 0.5, max: 256.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["blend_width", "edge_match_strength", "edge_match_blur", "detail_preserve", "seam_blur", "seam_softness", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Blend", get: (node) => `${formatNumber(getNumber(node, "blend_width", 24), 1)} px` },
      { label: "Edge Match", get: (node) => formatNumber(getNumber(node, "edge_match_strength", 0.85), 2) },
      { label: "Detail", get: (node) => formatNumber(getNumber(node, "detail_preserve", 0.65), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { blend_width: 24.0, edge_match_strength: 0.85, edge_match_blur: 18.0, detail_preserve: 0.65, seam_blur: 12.0, seam_softness: 12.0, mask_feather: 8.0, invert_mask: false } },
      { label: "Soft Fabric", values: { blend_width: 32.0, edge_match_strength: 0.72, edge_match_blur: 26.0, detail_preserve: 0.74, seam_blur: 18.0, seam_softness: 16.0, mask_feather: 10.0, invert_mask: false } },
      { label: "Hard Surface", values: { blend_width: 14.0, edge_match_strength: 0.94, edge_match_blur: 10.0, detail_preserve: 0.82, seam_blur: 6.0, seam_softness: 8.0, mask_feather: 6.0, invert_mask: false } },
    ],
    graph: {
      title: "Cross Blend",
      note: "seam field",
      height: 224,
      help: "This preview sketches the center seam field and the low-frequency matching pass, so width and blur feel like part of one system.",
      readouts: [
        { label: "Blur", get: (node) => `${formatNumber(getNumber(node, "seam_blur", 12), 1)} px` },
        { label: "Softness", get: (node) => `${formatNumber(getNumber(node, "seam_softness", 12), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawSeamlessPreview,
    },
    sections: [
      {
        title: "Seam Blend",
        note: "crossfade",
        controls: [
          { key: "blend_width", label: "Blend Width", min: 1.0, max: 96.0, step: 0.5, decimals: 1 },
          { key: "seam_softness", label: "Seam Softness", min: 0.5, max: 64.0, step: 0.5, decimals: 1 },
          { key: "seam_blur", label: "Seam Blur", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
        ],
      },
      {
        title: "Edge Match",
        note: "low frequency",
        controls: [
          { key: "edge_match_strength", label: "Strength", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "edge_match_blur", label: "Blur Radius", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "detail_preserve", label: "Detail Preserve", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask Output",
        note: "selective apply",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional mask before the seamless pass blends in." },
        ],
      },
    ],
  },
  x1TextureEdgePad: {
    panelName: "mkrX1TextureEdgePadStudio",
    size: [720, 660],
    accent: "#c6f76b",
    title: "Texture Edge Pad Studio",
    subtitle: "Grow usable texels from alpha, mask, or luma selection without leaving a raw utility node in the graph.",
    defaults: {
      source_mode: "alpha",
      pad_pixels: 16,
      alpha_threshold: 0.01,
      expand_alpha: false,
    },
    numericSpecs: {
      pad_pixels: { min: 1, max: 512, integer: true },
      alpha_threshold: { min: 0.0, max: 1.0 },
    },
    booleanKeys: ["expand_alpha"],
    legacyNames: ["source_mode", "pad_pixels", "alpha_threshold", "expand_alpha"],
    metrics: [
      { label: "Source", get: (node) => String(getValue(node, "source_mode", "alpha")) },
      { label: "Pad", get: (node) => `${Math.round(getNumber(node, "pad_pixels", 16))} px` },
      { label: "Alpha", get: (node) => getBoolean(node, "expand_alpha", false) ? "Expand" : "Keep" },
    ],
    presets: [
      { label: "Alpha", tone: "accent", values: { source_mode: "alpha", pad_pixels: 16, alpha_threshold: 0.01, expand_alpha: false } },
      { label: "Mask Drive", values: { source_mode: "mask", pad_pixels: 24, alpha_threshold: 0.05, expand_alpha: true } },
      { label: "Luma Fill", values: { source_mode: "luma_nonzero", pad_pixels: 12, alpha_threshold: 0.02, expand_alpha: false } },
    ],
    graph: {
      title: "Pad Preview",
      note: "fill halo",
      height: 210,
      help: "The white island is your source region. The green halo shows how much padded texel growth the current settings will attempt around it.",
      readouts: [
        { label: "Threshold", get: (node) => formatNumber(getNumber(node, "alpha_threshold", 0.01), 3) },
        { label: "Expand Alpha", get: (node) => getBoolean(node, "expand_alpha", false) ? "On" : "Off" },
      ],
      draw: drawEdgePadPreview,
    },
    sections: [
      {
        title: "Source",
        note: "valid region",
        controls: [
          { key: "source_mode", type: "select", label: "Source Mode", options: [{ label: "Alpha", value: "alpha" }, { label: "Mask", value: "mask" }, { label: "Luma Nonzero", value: "luma_nonzero" }] },
          { key: "alpha_threshold", label: "Threshold", min: 0.0, max: 0.5, step: 0.001, decimals: 3 },
        ],
      },
      {
        title: "Fill",
        note: "edge growth",
        controls: [
          { key: "pad_pixels", label: "Pad Pixels", min: 1, max: 96, step: 1, decimals: 0 },
          { key: "expand_alpha", type: "toggle", label: "Expand Alpha", description: "Let the fill mask push alpha coverage too." },
        ],
      },
    ],
  },
  x1TextureDelight: {
    panelName: "mkrX1TextureDelightStudio",
    size: [780, 760],
    accent: "#ffd26d",
    title: "Texture Delight Studio",
    subtitle: "Flatten baked lighting while protecting texture contrast and restoring just enough chroma to keep surfaces believable.",
    defaults: {
      blur_radius: 32.0,
      flatten_strength: 0.85,
      detail_preserve: 0.8,
      shadow_lift: 0.3,
      highlight_compress: 0.2,
      saturation_restore: 0.18,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      blur_radius: { min: 1.0, max: 512.0 },
      flatten_strength: { min: 0.0, max: 2.0 },
      detail_preserve: { min: 0.0, max: 1.0 },
      shadow_lift: { min: 0.0, max: 2.0 },
      highlight_compress: { min: 0.0, max: 2.0 },
      saturation_restore: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["blur_radius", "flatten_strength", "detail_preserve", "shadow_lift", "highlight_compress", "saturation_restore", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Flatten", get: (node) => formatNumber(getNumber(node, "flatten_strength", 0.85), 2) },
      { label: "Detail", get: (node) => formatNumber(getNumber(node, "detail_preserve", 0.8), 2) },
      { label: "Sat Restore", get: (node) => formatNumber(getNumber(node, "saturation_restore", 0.18), 2) },
    ],
    presets: [
      { label: "Neutralize", tone: "accent", values: { blur_radius: 32.0, flatten_strength: 0.85, detail_preserve: 0.8, shadow_lift: 0.3, highlight_compress: 0.2, saturation_restore: 0.18, mask_feather: 8.0, invert_mask: false } },
      { label: "Overcast", values: { blur_radius: 44.0, flatten_strength: 1.1, detail_preserve: 0.74, shadow_lift: 0.42, highlight_compress: 0.12, saturation_restore: 0.24, mask_feather: 10.0, invert_mask: false } },
      { label: "Sun Baked", values: { blur_radius: 26.0, flatten_strength: 0.72, detail_preserve: 0.86, shadow_lift: 0.22, highlight_compress: 0.42, saturation_restore: 0.12, mask_feather: 6.0, invert_mask: false } },
    ],
    graph: {
      title: "Light Flattening",
      note: "response",
      height: 224,
      help: "The pale curve shows the incoming light ramp. The warm curve shows the current flattening response with shadow lift and highlight compression applied.",
      readouts: [
        { label: "Blur", get: (node) => `${formatNumber(getNumber(node, "blur_radius", 32), 1)} px` },
        { label: "Mask Feather", get: (node) => `${formatNumber(getNumber(node, "mask_feather", 8), 1)} px` },
      ],
      draw: drawDelightPreview,
    },
    sections: [
      {
        title: "Delight Response",
        note: "lighting flatten",
        controls: [
          { key: "blur_radius", label: "Blur Radius", min: 1.0, max: 96.0, step: 0.5, decimals: 1 },
          { key: "flatten_strength", label: "Flatten Strength", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
          { key: "detail_preserve", label: "Detail Preserve", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Tone Recovery",
        note: "shadow and highlight",
        controls: [
          { key: "shadow_lift", label: "Shadow Lift", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
          { key: "highlight_compress", label: "Highlight Compress", min: 0.0, max: 2.0, step: 0.01, decimals: 2 },
          { key: "saturation_restore", label: "Sat Restore", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask",
        note: "optional image mask input",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional mask before delighting the surface." },
        ],
      },
    ],
  },
  x1TextureAlbedoSafe: {
    panelName: "mkrX1TextureAlbedoSafeStudio",
    size: [780, 760],
    accent: "#ffe07c",
    title: "Albedo Safe Studio",
    subtitle: "Clamp reflectance and chroma into game-ready territory while protecting the midtone read that still makes the material feel alive.",
    defaults: {
      target_black: 0.04,
      target_white: 0.82,
      saturation_limit: 0.85,
      shadow_lift: 0.35,
      highlight_rolloff: 0.55,
      midtone_preserve: 0.28,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      target_black: { min: 0.0, max: 0.5 },
      target_white: { min: 0.1, max: 1.0 },
      saturation_limit: { min: 0.0, max: 1.0 },
      shadow_lift: { min: 0.0, max: 1.0 },
      highlight_rolloff: { min: 0.0, max: 1.0 },
      midtone_preserve: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["target_black", "target_white", "saturation_limit", "shadow_lift", "highlight_rolloff", "midtone_preserve", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Black", get: (node) => formatNumber(getNumber(node, "target_black", 0.04), 3) },
      { label: "White", get: (node) => formatNumber(getNumber(node, "target_white", 0.82), 3) },
      { label: "Sat", get: (node) => formatNumber(getNumber(node, "saturation_limit", 0.85), 2) },
    ],
    presets: [
      { label: "PBR Safe", tone: "accent", values: { target_black: 0.04, target_white: 0.82, saturation_limit: 0.85, shadow_lift: 0.35, highlight_rolloff: 0.55, midtone_preserve: 0.28, mask_feather: 8.0, invert_mask: false } },
      { label: "Painted", values: { target_black: 0.06, target_white: 0.78, saturation_limit: 0.72, shadow_lift: 0.22, highlight_rolloff: 0.44, midtone_preserve: 0.36, mask_feather: 6.0, invert_mask: false } },
      { label: "Rough Stone", values: { target_black: 0.03, target_white: 0.70, saturation_limit: 0.58, shadow_lift: 0.41, highlight_rolloff: 0.62, midtone_preserve: 0.18, mask_feather: 10.0, invert_mask: false } },
    ],
    graph: {
      title: "Reflectance Guard",
      note: "target range",
      height: 220,
      help: "The preview shows the desired black-to-white reflectance band and how much of the midtone character is being held back from full normalization.",
      readouts: [
        { label: "Rolloff", get: (node) => formatNumber(getNumber(node, "highlight_rolloff", 0.55), 2) },
        { label: "Midtone", get: (node) => formatNumber(getNumber(node, "midtone_preserve", 0.28), 2) },
      ],
      draw: drawAlbedoPreview,
    },
    sections: [
      {
        title: "Reflectance Targets",
        note: "value range",
        controls: [
          { key: "target_black", label: "Target Black", min: 0.0, max: 0.2, step: 0.005, decimals: 3 },
          { key: "target_white", label: "Target White", min: 0.4, max: 1.0, step: 0.005, decimals: 3 },
          { key: "saturation_limit", label: "Sat Limit", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Tone Protection",
        note: "preserve form",
        controls: [
          { key: "shadow_lift", label: "Shadow Lift", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "highlight_rolloff", label: "Highlight Rolloff", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "midtone_preserve", label: "Midtone Preserve", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask",
        note: "optional image mask input",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional mask before the albedo-safe pass." },
        ],
      },
    ],
  },
  x1TextureMacroVariation: {
    panelName: "mkrX1TextureMacroVariationStudio",
    size: [780, 780],
    accent: "#b57dff",
    title: "Macro Variation Studio",
    subtitle: "Author large-scale hue, saturation, value, and contrast breakup so repeated surfaces stop reading as stamped copies.",
    defaults: {
      macro_scale_px: 160.0,
      strength: 0.55,
      hue_variation: 0.02,
      saturation_variation: 0.12,
      value_variation: 0.12,
      contrast_variation: 0.18,
      seed: 11,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      macro_scale_px: { min: 16.0, max: 2048.0 },
      strength: { min: 0.0, max: 1.0 },
      hue_variation: { min: 0.0, max: 0.25 },
      saturation_variation: { min: 0.0, max: 1.0 },
      value_variation: { min: 0.0, max: 1.0 },
      contrast_variation: { min: 0.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["macro_scale_px", "strength", "hue_variation", "saturation_variation", "value_variation", "contrast_variation", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Scale", get: (node) => `${Math.round(getNumber(node, "macro_scale_px", 160))} px` },
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "strength", 0.55), 2) },
      { label: "Seed", get: (node) => String(Math.round(getNumber(node, "seed", 11))) },
    ],
    presets: [
      { label: "Terrain", tone: "accent", values: { macro_scale_px: 160.0, strength: 0.55, hue_variation: 0.02, saturation_variation: 0.12, value_variation: 0.12, contrast_variation: 0.18, seed: 11, mask_feather: 8.0, invert_mask: false } },
      { label: "Mossy", values: { macro_scale_px: 210.0, strength: 0.62, hue_variation: 0.04, saturation_variation: 0.22, value_variation: 0.18, contrast_variation: 0.16, seed: 28, mask_feather: 10.0, invert_mask: false } },
      { label: "Dry Stone", values: { macro_scale_px: 132.0, strength: 0.46, hue_variation: 0.01, saturation_variation: 0.08, value_variation: 0.09, contrast_variation: 0.22, seed: 7, mask_feather: 8.0, invert_mask: false } },
    ],
    graph: {
      title: "Macro Field",
      note: "color drift",
      height: 234,
      help: "The preview exaggerates the current hue, saturation, and value breakup so you can judge whether the macro field is subtle enough for tileable production work.",
      readouts: [
        { label: "Hue", get: (node) => formatNumber(getNumber(node, "hue_variation", 0.02), 3) },
        { label: "Saturation", get: (node) => formatNumber(getNumber(node, "saturation_variation", 0.12), 2) },
        { label: "Value", get: (node) => formatNumber(getNumber(node, "value_variation", 0.12), 2) },
      ],
      draw: drawMacroVariationPreview,
    },
    sections: [
      {
        title: "Macro Field",
        note: "large scale breakup",
        controls: [
          { key: "macro_scale_px", label: "Macro Scale", min: 16.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "strength", label: "Strength", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "seed", type: "seed", label: "Seed", min: 0, max: MAX_SEED },
        ],
      },
      {
        title: "Color Breakup",
        note: "hsv and contrast",
        controls: [
          { key: "hue_variation", label: "Hue Variation", min: 0.0, max: 0.12, step: 0.001, decimals: 3 },
          { key: "saturation_variation", label: "Saturation Variation", min: 0.0, max: 0.5, step: 0.01, decimals: 2 },
          { key: "value_variation", label: "Value Variation", min: 0.0, max: 0.5, step: 0.01, decimals: 2 },
          { key: "contrast_variation", label: "Contrast Variation", min: 0.0, max: 0.5, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask",
        note: "optional image mask input",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional mask before applying macro breakup." },
        ],
      },
    ],
  },
  x1TextureNoiseField: {
    panelName: "mkrX1TextureNoiseFieldStudio",
    size: [780, 760],
    accent: "#87c6ff",
    title: "Noise Field Studio",
    subtitle: "Build grayscale noise patterns with richer shaping, seeded detail layering, and a clearer sense of how the field will read at texture scale.",
    defaults: {
      width: 1024,
      height: 1024,
      variant: "fbm",
      scale_px: 160.0,
      octaves: 5,
      lacunarity: 2.0,
      gain: 0.55,
      detail_mix: 0.18,
      contrast: 1.15,
      balance: 0.0,
      invert: false,
      seed: 17,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      scale_px: { min: 2.0, max: 4096.0 },
      octaves: { min: 1, max: 8, integer: true },
      lacunarity: { min: 1.1, max: 4.0 },
      gain: { min: 0.01, max: 1.0 },
      detail_mix: { min: 0.0, max: 1.0 },
      contrast: { min: 0.05, max: 4.0 },
      balance: { min: -1.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
    },
    booleanKeys: ["invert"],
    legacyNames: ["width", "height", "variant", "scale_px", "octaves", "lacunarity", "gain", "detail_mix", "contrast", "balance", "invert", "seed"],
    metrics: [
      { label: "Size", get: (node) => `${Math.round(getNumber(node, "width", 1024))}x${Math.round(getNumber(node, "height", 1024))}` },
      { label: "Variant", get: (node) => String(getValue(node, "variant", "fbm")) },
      { label: "Seed", get: (node) => String(Math.round(getNumber(node, "seed", 17))) },
    ],
    presets: [
      { label: "FBM", tone: "accent", values: { width: 1024, height: 1024, variant: "fbm", scale_px: 160.0, octaves: 5, lacunarity: 2.0, gain: 0.55, detail_mix: 0.18, contrast: 1.15, balance: 0.0, invert: false, seed: 17 } },
      { label: "Ridged", values: { width: 1024, height: 1024, variant: "ridged", scale_px: 118.0, octaves: 5, lacunarity: 2.2, gain: 0.52, detail_mix: 0.24, contrast: 1.48, balance: -0.08, invert: false, seed: 24 } },
      { label: "Cloud", values: { width: 1024, height: 1024, variant: "turbulence", scale_px: 220.0, octaves: 4, lacunarity: 1.9, gain: 0.60, detail_mix: 0.10, contrast: 0.92, balance: 0.04, invert: false, seed: 31 } },
    ],
    graph: {
      title: "Noise Preview",
      note: "field",
      height: 226,
      help: "The preview exaggerates contrast and fine detail mix so you can judge whether the field will survive into a real material map without becoming mushy.",
      readouts: [
        { label: "Detail Mix", get: (node) => formatNumber(getNumber(node, "detail_mix", 0.18), 2) },
        { label: "Contrast", get: (node) => formatNumber(getNumber(node, "contrast", 1.15), 2) },
      ],
      draw: drawNoisePreview,
    },
    sections: [
      {
        title: "Output Size",
        note: "map resolution",
        controls: [
          { key: "width", type: "number", label: "Width", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "height", type: "number", label: "Height", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "variant", type: "select", label: "Variant", options: [{ label: "FBM", value: "fbm" }, { label: "Value", value: "value" }, { label: "Turbulence", value: "turbulence" }, { label: "Ridged", value: "ridged" }] },
        ],
      },
      {
        title: "Structure",
        note: "frequency stack",
        controls: [
          { key: "scale_px", label: "Scale", min: 2.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "octaves", label: "Octaves", min: 1, max: 8, step: 1, decimals: 0 },
          { key: "lacunarity", label: "Lacunarity", min: 1.1, max: 4.0, step: 0.05, decimals: 2 },
          { key: "gain", label: "Gain", min: 0.01, max: 1.0, step: 0.01, decimals: 2 },
          { key: "detail_mix", label: "Detail Mix", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "seed", type: "seed", label: "Seed", min: 0, max: MAX_SEED },
        ],
      },
      {
        title: "Shaping",
        note: "output curve",
        controls: [
          { key: "contrast", label: "Contrast", min: 0.05, max: 4.0, step: 0.01, decimals: 2 },
          { key: "balance", label: "Balance", min: -1.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "invert", type: "toggle", label: "Invert", description: "Flip the field after shaping." },
        ],
      },
    ],
  },
  x1TextureCellPattern: {
    panelName: "mkrX1TextureCellPatternStudio",
    size: [780, 760],
    accent: "#7cf5c9",
    title: "Cell Pattern Studio",
    subtitle: "Shape cell structures for stone, grout, damage, and bevel reads with clearer previews and a softer post-pattern response.",
    defaults: {
      width: 1024,
      height: 1024,
      pattern_mode: "fill",
      cell_scale_px: 96.0,
      jitter: 0.85,
      edge_width: 0.18,
      softness: 0.0,
      contrast: 1.2,
      balance: 0.0,
      invert: false,
      seed: 31,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      cell_scale_px: { min: 4.0, max: 4096.0 },
      jitter: { min: 0.0, max: 1.0 },
      edge_width: { min: 0.01, max: 1.0 },
      softness: { min: 0.0, max: 1.0 },
      contrast: { min: 0.05, max: 4.0 },
      balance: { min: -1.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
    },
    booleanKeys: ["invert"],
    legacyNames: ["width", "height", "pattern_mode", "cell_scale_px", "jitter", "edge_width", "softness", "contrast", "balance", "invert", "seed"],
    metrics: [
      { label: "Mode", get: (node) => String(getValue(node, "pattern_mode", "fill")) },
      { label: "Scale", get: (node) => `${Math.round(getNumber(node, "cell_scale_px", 96))} px` },
      { label: "Soft", get: (node) => formatNumber(getNumber(node, "softness", 0), 2) },
    ],
    presets: [
      { label: "Fill", tone: "accent", values: { width: 1024, height: 1024, pattern_mode: "fill", cell_scale_px: 96.0, jitter: 0.85, edge_width: 0.18, softness: 0.0, contrast: 1.2, balance: 0.0, invert: false, seed: 31 } },
      { label: "Cracks", values: { width: 1024, height: 1024, pattern_mode: "cracks", cell_scale_px: 120.0, jitter: 0.92, edge_width: 0.10, softness: 0.08, contrast: 1.6, balance: -0.12, invert: false, seed: 44 } },
      { label: "Bevel", values: { width: 1024, height: 1024, pattern_mode: "bevel", cell_scale_px: 82.0, jitter: 0.70, edge_width: 0.24, softness: 0.18, contrast: 1.18, balance: 0.02, invert: false, seed: 16 } },
    ],
    graph: {
      title: "Cell Layout",
      note: "pattern",
      height: 226,
      help: "The preview shows how jitter, edge width, and softness change the cell network before you even pipe it into a material map workflow.",
      readouts: [
        { label: "Jitter", get: (node) => formatNumber(getNumber(node, "jitter", 0.85), 2) },
        { label: "Edge", get: (node) => formatNumber(getNumber(node, "edge_width", 0.18), 2) },
      ],
      draw: drawCellPreview,
    },
    sections: [
      {
        title: "Output Size",
        note: "map resolution",
        controls: [
          { key: "width", type: "number", label: "Width", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "height", type: "number", label: "Height", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "pattern_mode", type: "select", label: "Mode", options: [{ label: "Fill", value: "fill" }, { label: "Edge", value: "edge" }, { label: "Cracks", value: "cracks" }, { label: "Distance", value: "distance" }, { label: "Bevel", value: "bevel" }] },
        ],
      },
      {
        title: "Cell Structure",
        note: "layout",
        controls: [
          { key: "cell_scale_px", label: "Cell Scale", min: 4.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "jitter", label: "Jitter", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "edge_width", label: "Edge Width", min: 0.01, max: 1.0, step: 0.01, decimals: 2 },
          { key: "softness", label: "Softness", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "seed", type: "seed", label: "Seed", min: 0, max: MAX_SEED },
        ],
      },
      {
        title: "Shaping",
        note: "output curve",
        controls: [
          { key: "contrast", label: "Contrast", min: 0.05, max: 4.0, step: 0.01, decimals: 2 },
          { key: "balance", label: "Balance", min: -1.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "invert", type: "toggle", label: "Invert", description: "Flip the field after shaping." },
        ],
      },
    ],
  },
  x1TextureStrata: {
    panelName: "mkrX1TextureStrataStudio",
    size: [780, 780],
    accent: "#ffbf7b",
    title: "Strata Studio",
    subtitle: "Build layered sediment, veins, and terraces with directional control, breakup shaping, and finer micro-detail drift.",
    defaults: {
      width: 1024,
      height: 1024,
      profile: "soft",
      band_scale_px: 180.0,
      direction_deg: 24.0,
      warp_strength: 0.32,
      breakup_scale_px: 112.0,
      breakup_strength: 0.38,
      micro_breakup: 0.18,
      contrast: 1.15,
      balance: 0.0,
      invert: false,
      seed: 53,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      band_scale_px: { min: 4.0, max: 4096.0 },
      direction_deg: { min: -180.0, max: 180.0 },
      warp_strength: { min: 0.0, max: 1.0 },
      breakup_scale_px: { min: 4.0, max: 4096.0 },
      breakup_strength: { min: 0.0, max: 1.0 },
      micro_breakup: { min: 0.0, max: 1.0 },
      contrast: { min: 0.05, max: 4.0 },
      balance: { min: -1.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
    },
    booleanKeys: ["invert"],
    legacyNames: ["width", "height", "profile", "band_scale_px", "direction_deg", "warp_strength", "breakup_scale_px", "breakup_strength", "micro_breakup", "contrast", "balance", "invert", "seed"],
    metrics: [
      { label: "Profile", get: (node) => String(getValue(node, "profile", "soft")) },
      { label: "Direction", get: (node) => `${formatNumber(getNumber(node, "direction_deg", 24), 1)} deg` },
      { label: "Breakup", get: (node) => formatNumber(getNumber(node, "micro_breakup", 0.18), 2) },
    ],
    presets: [
      { label: "Soft", tone: "accent", values: { width: 1024, height: 1024, profile: "soft", band_scale_px: 180.0, direction_deg: 24.0, warp_strength: 0.32, breakup_scale_px: 112.0, breakup_strength: 0.38, micro_breakup: 0.18, contrast: 1.15, balance: 0.0, invert: false, seed: 53 } },
      { label: "Veins", values: { width: 1024, height: 1024, profile: "veins", band_scale_px: 124.0, direction_deg: -14.0, warp_strength: 0.46, breakup_scale_px: 92.0, breakup_strength: 0.44, micro_breakup: 0.24, contrast: 1.34, balance: -0.05, invert: false, seed: 62 } },
      { label: "Terrace", values: { width: 1024, height: 1024, profile: "terrace", band_scale_px: 212.0, direction_deg: 8.0, warp_strength: 0.20, breakup_scale_px: 138.0, breakup_strength: 0.28, micro_breakup: 0.12, contrast: 1.26, balance: 0.02, invert: false, seed: 41 } },
    ],
    graph: {
      title: "Layer Bands",
      note: "directional strata",
      height: 226,
      help: "The preview leans into band direction and breakup so you can quickly tune whether the strata feels sedimentary, veiny, or stylized.",
      readouts: [
        { label: "Warp", get: (node) => formatNumber(getNumber(node, "warp_strength", 0.32), 2) },
        { label: "Breakup", get: (node) => formatNumber(getNumber(node, "breakup_strength", 0.38), 2) },
      ],
      draw: drawStrataPreview,
    },
    sections: [
      {
        title: "Output Size",
        note: "map resolution",
        controls: [
          { key: "width", type: "number", label: "Width", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "height", type: "number", label: "Height", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "profile", type: "select", label: "Profile", options: [{ label: "Soft", value: "soft" }, { label: "Veins", value: "veins" }, { label: "Terrace", value: "terrace" }] },
        ],
      },
      {
        title: "Band Layout",
        note: "primary structure",
        controls: [
          { key: "band_scale_px", label: "Band Scale", min: 4.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "direction_deg", label: "Direction", min: -180.0, max: 180.0, step: 0.5, decimals: 1 },
          { key: "warp_strength", label: "Warp Strength", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Breakup",
        note: "secondary detail",
        controls: [
          { key: "breakup_scale_px", label: "Breakup Scale", min: 4.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "breakup_strength", label: "Breakup Strength", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "micro_breakup", label: "Micro Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "seed", type: "seed", label: "Seed", min: 0, max: MAX_SEED },
        ],
      },
      {
        title: "Shaping",
        note: "output curve",
        controls: [
          { key: "contrast", label: "Contrast", min: 0.05, max: 4.0, step: 0.01, decimals: 2 },
          { key: "balance", label: "Balance", min: -1.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "invert", type: "toggle", label: "Invert", description: "Flip the field after shaping." },
        ],
      },
    ],
  },
  x1TextureDetileBlend: {
    panelName: "mkrX1TextureDetileBlendStudio",
    size: [780, 760],
    accent: "#73e8ca",
    title: "Detile Blend Studio",
    subtitle: "Blend against an offset variant with color matching and breakup control so repetition suppression feels authored instead of smeared.",
    defaults: {
      macro_scale_px: 196.0,
      blend_strength: 0.55,
      color_match_blur: 20.0,
      detail_preserve: 0.72,
      variation_breakup: 0.22,
      seed: 101,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      macro_scale_px: { min: 16.0, max: 2048.0 },
      blend_strength: { min: 0.0, max: 1.0 },
      color_match_blur: { min: 0.0, max: 256.0 },
      detail_preserve: { min: 0.0, max: 1.0 },
      variation_breakup: { min: 0.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["macro_scale_px", "blend_strength", "color_match_blur", "detail_preserve", "variation_breakup", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Blend", get: (node) => formatNumber(getNumber(node, "blend_strength", 0.55), 2) },
      { label: "Match Blur", get: (node) => `${formatNumber(getNumber(node, "color_match_blur", 20), 1)} px` },
      { label: "Breakup", get: (node) => formatNumber(getNumber(node, "variation_breakup", 0.22), 2) },
    ],
    presets: [
      { label: "Balanced", tone: "accent", values: { macro_scale_px: 196.0, blend_strength: 0.55, color_match_blur: 20.0, detail_preserve: 0.72, variation_breakup: 0.22, seed: 101, mask_feather: 8.0, invert_mask: false } },
      { label: "Organic", values: { macro_scale_px: 240.0, blend_strength: 0.66, color_match_blur: 28.0, detail_preserve: 0.78, variation_breakup: 0.34, seed: 117, mask_feather: 10.0, invert_mask: false } },
      { label: "Crisp", values: { macro_scale_px: 144.0, blend_strength: 0.42, color_match_blur: 10.0, detail_preserve: 0.86, variation_breakup: 0.12, seed: 88, mask_feather: 6.0, invert_mask: false } },
    ],
    graph: {
      title: "Detile Field",
      note: "offset mix",
      height: 224,
      help: "The preview combines a tile grid with a soft blend mask so you can tune detiling without losing track of how much original detail remains.",
      readouts: [
        { label: "Scale", get: (node) => `${Math.round(getNumber(node, "macro_scale_px", 196))} px` },
        { label: "Detail", get: (node) => formatNumber(getNumber(node, "detail_preserve", 0.72), 2) },
      ],
      draw: drawDetilePreview,
    },
    sections: [
      {
        title: "Blend Field",
        note: "macro suppression",
        controls: [
          { key: "macro_scale_px", label: "Macro Scale", min: 16.0, max: 512.0, step: 1.0, decimals: 0 },
          { key: "blend_strength", label: "Blend Strength", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "variation_breakup", label: "Variation Breakup", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "seed", type: "seed", label: "Seed", min: 0, max: MAX_SEED },
        ],
      },
      {
        title: "Color Match",
        note: "preserve structure",
        controls: [
          { key: "color_match_blur", label: "Color Match Blur", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "detail_preserve", label: "Detail Preserve", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask",
        note: "optional image mask input",
        controls: [
          { key: "mask_feather", label: "Mask Feather", min: 0.0, max: 64.0, step: 0.5, decimals: 1 },
          { key: "invert_mask", type: "toggle", label: "Invert Mask", description: "Flip the optional mask before suppressing visible tiling." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

function readControlValue(node, spec) {
  if (spec.type === "toggle") return getBoolean(node, spec.key, !!spec.default);
  if (spec.type === "seed" || spec.type === "select") return getValue(node, spec.key, spec.default);
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

  if (spec.type === "seed") {
    const control = createSeedControl({
      label: spec.label,
      value: Math.round(Number(getValue(node, spec.key, 0)) || 0),
      min: spec.min ?? 0,
      max: spec.max ?? MAX_SEED,
      onChange: (value) => {
        setWidgetValue(node, spec.key, Math.round(value));
        refresh();
      },
      onReseed: () => {
        const next = Math.floor(Math.random() * (spec.max ?? MAX_SEED));
        setWidgetValue(node, spec.key, next);
        refresh();
        return next;
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

  if (spec.type === "number") {
    const control = createNumberControl({
      label: spec.label,
      value: getNumber(node, spec.key, spec.default ?? 0),
      min: spec.min,
      max: spec.max,
      step: spec.step ?? 1,
      decimals: spec.decimals ?? 2,
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
    if (sectionSpec.help) {
      const note = document.createElement("div");
      note.className = "mkr-texture-callout";
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

  if (node.__mkrTexturePanelInstalled) {
    node.__mkrTextureRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrTexturePanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrTextureRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrTextureRefreshHooksInstalled", refresh);
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
