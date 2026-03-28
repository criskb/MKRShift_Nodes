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

const EXTENSION_NAME = "MKRShift.XProcessStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-xprocess-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function safeViewText(getter, node, fallback = "--") {
  try {
    const value = getter?.(node);
    return value ?? fallback;
  } catch (error) {
    console.warn("[MKRShift.XProcessStudios] view getter failed", error);
    return fallback;
  }
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

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.18)") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(18,21,26,0.98)");
  bg.addColorStop(1, "rgba(29,33,40,0.98)");
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

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-xprocess-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-xprocess-select {
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

    .mkr-xprocess-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      margin-top: 4px;
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
  wrap.className = "mkr-xprocess-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-xprocess-number";
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

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${value}</span>`;

  const select = document.createElement("select");
  select.className = "mkr-xprocess-select";
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

function drawTonePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,186,112,0.22)");
  const exposure = getNumber(node, "exposure", 0);
  const contrast = getNumber(node, "contrast", 1);
  const saturation = getNumber(node, "saturation", 1);
  const warmth = getNumber(node, "tone_warmth", 0);
  const fade = getNumber(node, "tone_fade", 0);

  const grad = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y);
  grad.addColorStop(0, warmth >= 0 ? `rgba(${Math.round(92 + warmth * 60)}, ${Math.round(108 + warmth * 32)}, ${Math.round(142 - warmth * 34)}, 1)` : `rgba(${Math.round(100 - warmth * 28)}, ${Math.round(112 - warmth * 12)}, ${Math.round(150 + (-warmth) * 50)}, 1)`);
  grad.addColorStop(0.5, "rgba(198,205,214,1)");
  grad.addColorStop(1, warmth >= 0 ? `rgba(${Math.round(255)}, ${Math.round(198 + warmth * 18)}, ${Math.round(132 - warmth * 50)}, 1)` : `rgba(${Math.round(198 - (-warmth) * 34)}, ${Math.round(210 - (-warmth) * 12)}, ${Math.round(255)}, 1)`);
  ctx.fillStyle = grad;
  ctx.fillRect(frame.x, frame.y + frame.h - 26, frame.w, 14);

  ctx.strokeStyle = "rgba(255,255,255,0.86)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let step = 0; step <= 72; step += 1) {
    const t = step / 72;
    const px = frame.x + (frame.w * t);
    let y = t;
    y = clamp((y * Math.pow(2, exposure * 0.55)), 0, 1);
    y = clamp(((y - 0.5) * contrast) + 0.5, 0, 1);
    y = clamp((y * (1 - fade * 0.16)) + (fade * 0.08), 0, 1);
    const py = frame.y + (1 - y) * (frame.h - 48);
    if (step === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.14)";
  ctx.fillRect(frame.x + 10, frame.y + 10, 44, 16);
  ctx.fillStyle = "rgba(255,255,255,0.86)";
  ctx.font = "11px sans-serif";
  ctx.fillText(`Sat ${formatNumber(saturation)}`, frame.x + 14, frame.y + 22);
}

function drawFilmPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(244,226,153,0.22)");
  const grain = getNumber(node, "film_grain_strength", 0);
  const size = getNumber(node, "film_grain_size", 32);
  const chroma = getNumber(node, "film_grain_chroma", 0.35);
  const vignette = getNumber(node, "vignette_strength", 0);
  const roundness = getNumber(node, "vignette_roundness", 1.2);

  const plate = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  plate.addColorStop(0, "rgba(34,32,26,0.98)");
  plate.addColorStop(0.52, "rgba(56,50,38,0.92)");
  plate.addColorStop(1, "rgba(20,19,17,0.98)");
  ctx.fillStyle = plate;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const vignetteGrad = ctx.createRadialGradient(
    frame.x + frame.w * 0.5,
    frame.y + frame.h * 0.5,
    frame.w * 0.12,
    frame.x + frame.w * 0.5,
    frame.y + frame.h * 0.5,
    frame.w * (0.65 + roundness * 0.08)
  );
  vignetteGrad.addColorStop(0, "rgba(255,255,255,0.04)");
  vignetteGrad.addColorStop(1, `rgba(0,0,0,${0.18 + vignette * 0.44})`);
  ctx.fillStyle = vignetteGrad;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const dotStep = clamp(size * 0.22, 6, 18);
  const baseAlpha = 0.10 + grain * 0.18;
  for (let y = frame.y + 10; y <= frame.y + frame.h - 10; y += dotStep) {
    for (let x = frame.x + 10; x <= frame.x + frame.w - 10; x += dotStep) {
      const n = Math.sin((x * 0.13) + (y * 0.19) + size * 0.015) * Math.cos((x * 0.07) - (y * 0.11) + chroma * 2.5);
      const intensity = (n * 0.5) + 0.5;
      const r = Math.round(178 + chroma * 52 + intensity * 20);
      const g = Math.round(176 - chroma * 32 + intensity * 14);
      const b = Math.round(170 + chroma * 42 + intensity * 18);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${baseAlpha * intensity})`;
      ctx.fillRect(x, y, 1.4 + grain * 1.8, 1.4 + grain * 1.8);
    }
  }

  const lineCount = 10;
  for (let line = 0; line < lineCount; line += 1) {
    const y = frame.y + ((frame.h * line) / lineCount) + 8;
    const jitter = Math.sin((line + 1) * 1.73) * (6 + grain * 14);
    ctx.strokeStyle = `rgba(255,244,212,${0.06 + grain * 0.12})`;
    ctx.lineWidth = 0.8 + grain * 1.2;
    ctx.beginPath();
    ctx.moveTo(frame.x + 14 + jitter, y);
    ctx.lineTo(frame.x + frame.w - 14 - jitter, y);
    ctx.stroke();
  }

  const gateW = clamp(size / 2, 6, 34);
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1.2;
  ctx.strokeRect(frame.x + gateW, frame.y + gateW * 0.65, frame.w - gateW * 2, frame.h - gateW * 1.3);

  ctx.fillStyle = "rgba(0,0,0,0.42)";
  ctx.fillRect(frame.x + 8, frame.y + 10, 10, frame.h - 20);
  ctx.fillRect(frame.x + frame.w - 18, frame.y + 10, 10, frame.h - 20);
  for (let i = 0; i < 5; i += 1) {
    const py = frame.y + 18 + (i * (frame.h - 36) / 4);
    ctx.fillStyle = "rgba(255,246,214,0.58)";
    ctx.fillRect(frame.x + 10, py, 6, 10);
    ctx.fillRect(frame.x + frame.w - 16, py, 6, 10);
  }
}

function drawBloomPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,202,121,0.22)");
  const strength = getNumber(node, "bloom_strength", 0);
  const radius = getNumber(node, "bloom_radius", 14);
  const threshold = getNumber(node, "bloom_threshold", 0.7);
  const softness = getNumber(node, "bloom_softness", 0.4);
  const warmth = getNumber(node, "bloom_warmth", 0);

  const warmR = warmth >= 0 ? 255 : Math.round(255 - (-warmth) * 64);
  const warmG = warmth >= 0 ? Math.round(218 + warmth * 22) : Math.round(228 - (-warmth) * 18);
  const warmB = warmth >= 0 ? Math.round(174 - warmth * 62) : 255;
  const centers = [
    [frame.x + frame.w * 0.28, frame.y + frame.h * 0.42, 0.9],
    [frame.x + frame.w * 0.62, frame.y + frame.h * 0.34, 0.7],
    [frame.x + frame.w * 0.78, frame.y + frame.h * 0.62, 0.55],
  ];

  for (const [cx, cy, scale] of centers) {
    const glow = ctx.createRadialGradient(cx, cy, 4, cx, cy, (radius * (1.2 + softness)) * scale + 18);
    glow.addColorStop(0, `rgba(${warmR},${warmG},${warmB},${0.22 + strength * 0.22})`);
    glow.addColorStop(clamp(0.24 + threshold * 0.2, 0.12, 0.58), `rgba(${warmR},${warmG},${warmB},${0.10 + strength * 0.12})`);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(cx - 120, cy - 120, 240, 240);

    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.beginPath();
    ctx.arc(cx, cy, 3 + scale * 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawChromaticPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(173,134,255,0.22)");
  const shiftX = getNumber(node, "rgb_shift_x", 0);
  const shiftY = getNumber(node, "rgb_shift_y", 0);
  const prism = getNumber(node, "prismatic_strength", 0);
  const distance = getNumber(node, "prismatic_distance", 5);
  const angle = (getNumber(node, "prismatic_angle", 25) * Math.PI) / 180;
  const edgeWeight = getNumber(node, "chromatic_edge_weight", 0.65);
  const greenShift = getNumber(node, "chromatic_green_shift", 0);
  const inset = lerp(18, 70, 1 - edgeWeight);
  const box = { x: frame.x + inset, y: frame.y + inset * 0.75, w: frame.w - inset * 2, h: frame.h - inset * 1.5 };
  const dx = shiftX * 0.22 + Math.cos(angle) * distance * prism * 0.12;
  const dy = shiftY * 0.22 + Math.sin(angle) * distance * prism * 0.12;

  ctx.lineWidth = 2.2;
  ctx.strokeStyle = "rgba(255,76,112,0.82)";
  ctx.strokeRect(box.x + dx, box.y + dy, box.w, box.h);
  ctx.strokeStyle = "rgba(95,255,157,0.72)";
  ctx.strokeRect(box.x + dx * greenShift * 0.45, box.y + dy * greenShift * 0.45, box.w, box.h);
  ctx.strokeStyle = "rgba(72,177,255,0.82)";
  ctx.strokeRect(box.x - dx, box.y - dy, box.w, box.h);

  ctx.fillStyle = "rgba(255,255,255,0.07)";
  ctx.fillRect(frame.x + 12, frame.y + frame.h - 24, frame.w - 24, 10);
}

function drawStylizePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,125,176,0.22)");
  const bits = Math.round(getNumber(node, "posterize_bits", 8));
  const halftone = getNumber(node, "halftone_strength", 0);
  const dotSize = getNumber(node, "halftone_size", 8);
  const ink = getNumber(node, "stylize_ink_strength", 0);
  const inkThreshold = getNumber(node, "stylize_ink_threshold", 0.28);
  const levels = Math.max(2, bits);

  for (let i = 0; i < levels; i += 1) {
    const t = i / Math.max(1, levels - 1);
    ctx.fillStyle = `hsl(${lerp(22, 312, t)}, ${lerp(74, 48, t)}%, ${lerp(62, 42, t)}%)`;
    ctx.fillRect(frame.x + (frame.w * t), frame.y + 20, frame.w / levels + 1, frame.h - 40);
  }

  const spacing = clamp(dotSize, 4, 22);
  ctx.fillStyle = `rgba(14,16,20,${0.08 + halftone * 0.34})`;
  for (let y = frame.y + 24; y < frame.y + frame.h - 16; y += spacing) {
    for (let x = frame.x + 24; x < frame.x + frame.w - 16; x += spacing) {
      const offset = ((Math.floor((x + y) / spacing) % 2) * spacing * 0.35);
      ctx.beginPath();
      ctx.arc(x + offset, y, 1.2 + halftone * 2.3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.strokeStyle = `rgba(0,0,0,${0.18 + ink * 0.5})`;
  ctx.lineWidth = 1.6 + ink * 1.6;
  for (let i = 0; i < 4; i += 1) {
    const y = frame.y + 34 + i * ((frame.h - 68) / 3);
    ctx.beginPath();
    for (let step = 0; step <= 48; step += 1) {
      const t = step / 48;
      const x = frame.x + 18 + t * (frame.w - 36);
      const wave = Math.sin(t * Math.PI * 4 + i) * (6 + inkThreshold * 10);
      const py = y + wave;
      if (step === 0) ctx.moveTo(x, py);
      else ctx.lineTo(x, py);
    }
    ctx.stroke();
  }
}

function drawPixelatePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(111,230,255,0.22)");
  const px = Math.max(1, Math.round(getNumber(node, "pixel_size_x", 8)));
  const py = Math.max(1, Math.round(getNumber(node, "pixel_size_y", 8)));
  const blend = getNumber(node, "cell_blend", 0);
  const levels = Math.round(getNumber(node, "color_levels", 0));
  const gridStrength = getNumber(node, "grid_strength", 0);
  const cols = clamp(Math.round(14 - Math.min(px, 40) / 4), 5, 16);
  const rows = clamp(Math.round(11 - Math.min(py, 40) / 4), 4, 12);
  const cellW = frame.w / cols;
  const cellH = frame.h / rows;

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      let r = 70 + ((col / Math.max(1, cols - 1)) * 145);
      let g = 85 + ((row / Math.max(1, rows - 1)) * 110);
      let b = 145 + (((row + col) / Math.max(1, rows + cols - 2)) * 80);
      if (levels >= 2) {
        const quant = (value) => Math.round((value / 255) * (levels - 1)) / Math.max(1, levels - 1);
        r = quant(r) * 255;
        g = quant(g) * 255;
        b = quant(b) * 255;
      }
      ctx.fillStyle = `rgba(${Math.round(lerp(r, 230, blend * 0.18))}, ${Math.round(lerp(g, 230, blend * 0.18))}, ${Math.round(lerp(b, 230, blend * 0.18))}, 1)`;
      ctx.fillRect(frame.x + col * cellW, frame.y + row * cellH, Math.ceil(cellW), Math.ceil(cellH));
    }
  }

  if (gridStrength > 0.001) {
    ctx.strokeStyle = `rgba(10,12,16,${0.12 + gridStrength * 0.55})`;
    ctx.lineWidth = 1 + getNumber(node, "grid_width", 1) * 0.35;
    for (let col = 0; col <= cols; col += 1) {
      const x = frame.x + col * cellW;
      ctx.beginPath();
      ctx.moveTo(x, frame.y);
      ctx.lineTo(x, frame.y + frame.h);
      ctx.stroke();
    }
    for (let row = 0; row <= rows; row += 1) {
      const y = frame.y + row * cellH;
      ctx.beginPath();
      ctx.moveTo(frame.x, y);
      ctx.lineTo(frame.x + frame.w, y);
      ctx.stroke();
    }
  }
}

function drawFractalPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(123,255,193,0.22)");
  const strength = getNumber(node, "fractal_strength", 0);
  const scale = getNumber(node, "fractal_scale", 96);
  const contrast = getNumber(node, "fractal_contrast", 1.0);
  const drift = getNumber(node, "fractal_drift", 0.1);
  const octaves = Math.round(getNumber(node, "fractal_octaves", 4));
  const bands = 7 + octaves;

  for (let y = 0; y < bands; y += 1) {
    ctx.beginPath();
    for (let step = 0; step <= 72; step += 1) {
      const t = step / 72;
      const px = frame.x + t * frame.w;
      const wave = Math.sin(t * (scale / 18) + y * 0.7) * (8 + contrast * 4)
        + Math.cos(t * (scale / 42) + y * 1.3 + drift * 8) * (5 + strength * 7);
      const py = frame.y + ((y + 1) / (bands + 1)) * frame.h + wave;
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = `hsla(${140 + y * 18 + drift * 40}, 85%, ${50 + y * 2}%, ${0.22 + strength * 0.32})`;
    ctx.lineWidth = 1.2 + strength * 1.6;
    ctx.stroke();
  }
}

function drawBokehPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,221,159,0.22)");
  const strength = getNumber(node, "bokeh_strength", 0);
  const radius = getNumber(node, "bokeh_radius", 10);
  const threshold = getNumber(node, "bokeh_threshold", 0.72);
  const softness = getNumber(node, "bokeh_softness", 0.5);
  const warmth = getNumber(node, "bokeh_warmth", 0);
  const tint = warmth >= 0
    ? [255, 224 + warmth * 18, 184 - warmth * 40]
    : [232 - (-warmth) * 20, 238 - (-warmth) * 8, 255];
  const spots = [
    [0.24, 0.38, 1.0],
    [0.58, 0.28, 0.74],
    [0.78, 0.58, 0.92],
    [0.46, 0.68, 0.58],
  ];

  for (const [tx, ty, scale] of spots) {
    const cx = frame.x + frame.w * tx;
    const cy = frame.y + frame.h * ty;
    const glow = ctx.createRadialGradient(cx, cy, 3, cx, cy, radius * (1.2 + softness) * scale + 12);
    glow.addColorStop(0, `rgba(${Math.round(tint[0])},${Math.round(tint[1])},${Math.round(tint[2])},${0.16 + strength * 0.26})`);
    glow.addColorStop(clamp(0.18 + threshold * 0.25, 0.1, 0.6), `rgba(${Math.round(tint[0])},${Math.round(tint[1])},${Math.round(tint[2])},${0.08 + strength * 0.16})`);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, radius * scale + 14, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawFocusPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(121,203,255,0.22)");
  const blur = getNumber(node, "blur_radius", 0);
  const sharpen = getNumber(node, "sharpen", 0);
  const center = { x: frame.x + frame.w * 0.5, y: frame.y + frame.h * 0.5 };
  const box = { x: frame.x + frame.w * 0.26, y: frame.y + frame.h * 0.22, w: frame.w * 0.48, h: frame.h * 0.56 };

  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  bg.addColorStop(0, "rgba(21,28,40,0.98)");
  bg.addColorStop(0.52, "rgba(31,53,78,0.94)");
  bg.addColorStop(1, "rgba(15,19,28,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const haze = ctx.createRadialGradient(center.x, center.y, 8, center.x, center.y, frame.w * 0.56);
  haze.addColorStop(0, "rgba(255,255,255,0.06)");
  haze.addColorStop(1, `rgba(0,0,0,${0.18 + blur * 0.03})`);
  ctx.fillStyle = haze;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.save();
  ctx.shadowColor = `rgba(120,203,255,${0.16 + blur * 0.03})`;
  ctx.shadowBlur = 8 + blur * 1.6;
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.fillRect(box.x + 18, box.y + 14, box.w - 36, box.h - 28);
  ctx.restore();

  ctx.strokeStyle = "rgba(255,255,255,0.24)";
  ctx.lineWidth = 1;
  ctx.strokeRect(box.x, box.y, box.w, box.h);

  ctx.strokeStyle = "rgba(255,255,255,0.28)";
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(box.x + box.w * 0.5, box.y + 12);
  ctx.lineTo(box.x + box.w * 0.5, box.y + box.h - 12);
  ctx.moveTo(box.x + 12, box.y + box.h * 0.5);
  ctx.lineTo(box.x + box.w - 12, box.y + box.h * 0.5);
  ctx.stroke();

  ctx.strokeStyle = `rgba(255,255,255,${0.18 + sharpen * 0.24})`;
  ctx.lineWidth = 1.6 + sharpen * 0.9;
  ctx.beginPath();
  ctx.arc(center.x, center.y, 16 + sharpen * 7, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.beginPath();
  ctx.arc(center.x, center.y, 4, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = `rgba(255,255,255,${0.12 + sharpen * 0.18})`;
  ctx.lineWidth = 1.4 + sharpen * 0.8;
  for (let i = 0; i < 5; i += 1) {
    const inset = i * 8;
    ctx.strokeRect(box.x + inset, box.y + inset, box.w - inset * 2, box.h - inset * 2);
  }

  ctx.strokeStyle = `rgba(121,203,255,${0.14 + blur * 0.04})`;
  ctx.setLineDash([5, 6]);
  ctx.beginPath();
  ctx.arc(center.x, center.y, 34 + blur * 2.6, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
}

const NODE_CONFIGS = {
  x1Tone: {
    panelName: "mkr_xprocess_tone_studio",
    size: [760, 860],
    accent: "#ffba70",
    title: "Tone Studio",
    subtitle: "Balance exposure, contrast, saturation, warmth, and fade with a cleaner photo-finishing surface.",
    defaults: {
      exposure: 0.0,
      contrast: 1.0,
      saturation: 1.0,
      tone_warmth: 0.0,
      tone_fade: 0.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      exposure: { min: -2.0, max: 2.0 },
      contrast: { min: 0.0, max: 3.0 },
      saturation: { min: 0.0, max: 3.0 },
      tone_warmth: { min: -1.0, max: 1.0 },
      tone_fade: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["exposure", "contrast", "saturation", "tone_warmth", "tone_fade", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Exposure", get: (node) => formatSigned(getNumber(node, "exposure", 0), 2) },
      { label: "Warmth", get: (node) => formatSigned(getNumber(node, "tone_warmth", 0), 2) },
      { label: "Fade", get: (node) => formatNumber(getNumber(node, "tone_fade", 0)) },
    ],
    presets: [
      { label: "Clean Pop", tone: "accent", values: { exposure: 0.16, contrast: 1.14, saturation: 1.08, tone_warmth: 0.08, tone_fade: 0.0 } },
      { label: "Soft Print", values: { exposure: 0.08, contrast: 0.94, saturation: 0.96, tone_warmth: 0.18, tone_fade: 0.18 } },
      { label: "Cool Wash", values: { exposure: -0.04, contrast: 0.92, saturation: 0.88, tone_warmth: -0.26, tone_fade: 0.12 } },
    ],
    graph: {
      title: "Tone Curve",
      note: "response",
      height: 210,
      draw: drawTonePreview,
      readouts: [
        { label: "Con", get: (node) => formatNumber(getNumber(node, "contrast", 1.0)) },
        { label: "Sat", get: (node) => formatNumber(getNumber(node, "saturation", 1.0)) },
        { label: "Warm", get: (node) => formatSigned(getNumber(node, "tone_warmth", 0.0), 2) },
      ],
      help: "The preview shows the tonal response and warmth balance together, so the node reads like a grade tool instead of a plain utility form.",
    },
    sections: [
      {
        title: "Base Tone",
        note: "primary",
        controls: [
          { type: "slider", key: "exposure", label: "Exposure", min: -2, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "contrast", label: "Contrast", min: 0, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "saturation", label: "Saturation", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Character",
        note: "look",
        controls: [
          { type: "slider", key: "tone_warmth", label: "Warmth", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tone_fade", label: "Fade", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the tone pass is blended." },
        ],
      },
    ],
  },
  x1Film: {
    panelName: "mkr_xprocess_film_studio",
    size: [760, 900],
    accent: "#f4e299",
    title: "Film Finish Studio",
    subtitle: "Shape grain and vignette with finer chroma behavior and faster look presets.",
    defaults: {
      film_grain_strength: 0.0,
      film_grain_size: 32.0,
      film_grain_seed: 42,
      film_grain_chroma: 0.35,
      vignette_strength: 0.0,
      vignette_roundness: 1.2,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      film_grain_strength: { min: 0.0, max: 1.5 },
      film_grain_size: { min: 2.0, max: 256.0 },
      film_grain_seed: { min: 0, max: 999999, integer: true },
      film_grain_chroma: { min: 0.0, max: 1.0 },
      vignette_strength: { min: 0.0, max: 1.0 },
      vignette_roundness: { min: 0.2, max: 3.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["film_grain_strength", "film_grain_size", "film_grain_seed", "film_grain_chroma", "vignette_strength", "vignette_roundness", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Grain", get: (node) => formatNumber(getNumber(node, "film_grain_strength", 0)) },
      { label: "Chroma", get: (node) => formatNumber(getNumber(node, "film_grain_chroma", 0.35)) },
      { label: "Vignette", get: (node) => formatNumber(getNumber(node, "vignette_strength", 0)) },
    ],
    presets: [
      { label: "35mm", tone: "accent", values: { film_grain_strength: 0.28, film_grain_size: 26, film_grain_seed: 42, film_grain_chroma: 0.44, vignette_strength: 0.12, vignette_roundness: 1.08 } },
      { label: "Rough Stock", values: { film_grain_strength: 0.54, film_grain_size: 20, film_grain_seed: 144, film_grain_chroma: 0.62, vignette_strength: 0.24, vignette_roundness: 1.42 } },
      { label: "Clean Gate", values: { film_grain_strength: 0.14, film_grain_size: 42, film_grain_seed: 12, film_grain_chroma: 0.18, vignette_strength: 0.08, vignette_roundness: 0.96 } },
    ],
    graph: {
      title: "Film Preview",
      note: "grain field",
      height: 216,
      draw: drawFilmPreview,
      readouts: [
        { label: "Size", get: (node) => formatNumber(getNumber(node, "film_grain_size", 32), 0) },
        { label: "Seed", get: (node) => String(Math.round(getNumber(node, "film_grain_seed", 42))) },
        { label: "Round", get: (node) => formatNumber(getNumber(node, "vignette_roundness", 1.2)) },
      ],
      help: "The preview sketches the grain texture and vignette falloff so stock changes feel intentional instead of blind tweaking.",
    },
    sections: [
      {
        title: "Grain",
        note: "primary",
        controls: [
          { type: "slider", key: "film_grain_strength", label: "Strength", min: 0, max: 1.5, step: 0.01, decimals: 2 },
          { type: "slider", key: "film_grain_size", label: "Size", min: 2, max: 256, step: 1, decimals: 0 },
          { type: "seed", key: "film_grain_seed", label: "Seed", min: 0, max: 999999 },
          { type: "slider", key: "film_grain_chroma", label: "Grain Chroma", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Vignette",
        note: "frame",
        controls: [
          { type: "slider", key: "vignette_strength", label: "Strength", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "vignette_roundness", label: "Roundness", min: 0.2, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the film pass is blended." },
        ],
      },
    ],
  },
  x1Bloom: {
    panelName: "mkr_xprocess_bloom_studio",
    size: [760, 900],
    accent: "#ffca79",
    title: "Bloom Studio",
    subtitle: "Shape soft thresholded glow with extra softness and warm/cool tint control.",
    defaults: {
      bloom_strength: 0.0,
      bloom_radius: 14.0,
      bloom_threshold: 0.7,
      bloom_softness: 0.4,
      bloom_warmth: 0.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      bloom_strength: { min: 0.0, max: 2.0 },
      bloom_radius: { min: 0.0, max: 128.0 },
      bloom_threshold: { min: 0.0, max: 1.0 },
      bloom_softness: { min: 0.0, max: 1.0 },
      bloom_warmth: { min: -1.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["bloom_strength", "bloom_radius", "bloom_threshold", "bloom_softness", "bloom_warmth", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "bloom_strength", 0)) },
      { label: "Soft", get: (node) => formatNumber(getNumber(node, "bloom_softness", 0.4)) },
      { label: "Warm", get: (node) => formatSigned(getNumber(node, "bloom_warmth", 0), 2) },
    ],
    presets: [
      { label: "Dream", tone: "accent", values: { bloom_strength: 0.46, bloom_radius: 24, bloom_threshold: 0.66, bloom_softness: 0.72, bloom_warmth: 0.12 } },
      { label: "Neon Pop", values: { bloom_strength: 0.74, bloom_radius: 18, bloom_threshold: 0.78, bloom_softness: 0.28, bloom_warmth: -0.18 } },
      { label: "Golden Mist", values: { bloom_strength: 0.58, bloom_radius: 34, bloom_threshold: 0.62, bloom_softness: 0.82, bloom_warmth: 0.34 } },
    ],
    graph: {
      title: "Bloom Preview",
      note: "highlight glow",
      height: 216,
      draw: drawBloomPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "bloom_threshold", 0.7)) },
        { label: "Radius", get: (node) => formatNumber(getNumber(node, "bloom_radius", 14), 0) },
        { label: "Warm", get: (node) => formatSigned(getNumber(node, "bloom_warmth", 0), 2) },
      ],
      help: "The preview shows how the bloom pool opens up, so threshold, softness, and warmth read as one lighting decision.",
    },
    sections: [
      {
        title: "Glow Core",
        note: "primary",
        controls: [
          { type: "slider", key: "bloom_strength", label: "Strength", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "bloom_radius", label: "Radius", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "bloom_threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Character",
        note: "shape",
        controls: [
          { type: "slider", key: "bloom_softness", label: "Softness", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "bloom_warmth", label: "Warmth", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the bloom pass is blended." },
        ],
      },
    ],
  },
  x1Chromatic: {
    panelName: "mkr_xprocess_chromatic_studio",
    size: [760, 940],
    accent: "#c08cff",
    title: "Chromatic Studio",
    subtitle: "Push RGB split and prism drift with edge weighting and green-channel bias for a more lens-like result.",
    defaults: {
      rgb_shift_x: 0,
      rgb_shift_y: 0,
      prismatic_strength: 0.0,
      prismatic_distance: 5.0,
      prismatic_angle: 25.0,
      chromatic_edge_weight: 0.65,
      chromatic_green_shift: 0.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      rgb_shift_x: { min: -128, max: 128, integer: true },
      rgb_shift_y: { min: -128, max: 128, integer: true },
      prismatic_strength: { min: 0.0, max: 2.0 },
      prismatic_distance: { min: 0.0, max: 128.0 },
      prismatic_angle: { min: 0.0, max: 360.0 },
      chromatic_edge_weight: { min: 0.0, max: 1.0 },
      chromatic_green_shift: { min: -1.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["rgb_shift_x", "rgb_shift_y", "prismatic_strength", "prismatic_distance", "prismatic_angle", "chromatic_edge_weight", "chromatic_green_shift", "mask_feather", "invert_mask"],
    metrics: [
      { label: "RGB X", get: (node) => String(Math.round(getNumber(node, "rgb_shift_x", 0))) },
      { label: "Prism", get: (node) => formatNumber(getNumber(node, "prismatic_strength", 0)) },
      { label: "Edge", get: (node) => formatNumber(getNumber(node, "chromatic_edge_weight", 0.65)) },
    ],
    presets: [
      { label: "Lens Drift", tone: "accent", values: { rgb_shift_x: 2, rgb_shift_y: 0, prismatic_strength: 0.28, prismatic_distance: 8, prismatic_angle: 18, chromatic_edge_weight: 0.82, chromatic_green_shift: 0.08 } },
      { label: "Arcade Split", values: { rgb_shift_x: 5, rgb_shift_y: 2, prismatic_strength: 0.72, prismatic_distance: 18, prismatic_angle: 35, chromatic_edge_weight: 0.48, chromatic_green_shift: -0.22 } },
      { label: "Subtle Lens", values: { rgb_shift_x: 1, rgb_shift_y: 0, prismatic_strength: 0.16, prismatic_distance: 5, prismatic_angle: 22, chromatic_edge_weight: 0.9, chromatic_green_shift: 0.02 } },
    ],
    graph: {
      title: "RGB Split Preview",
      note: "channel separation",
      height: 220,
      draw: drawChromaticPreview,
      readouts: [
        { label: "ShiftY", get: (node) => String(Math.round(getNumber(node, "rgb_shift_y", 0))) },
        { label: "Angle", get: (node) => formatNumber(getNumber(node, "prismatic_angle", 25), 0) },
        { label: "Green", get: (node) => formatSigned(getNumber(node, "chromatic_green_shift", 0), 2) },
      ],
      help: "The preview shows channel offset and edge weighting together, so the node behaves more like an optical fringe tool than a raw RGB offset utility.",
    },
    sections: [
      {
        title: "RGB Shift",
        note: "primary",
        controls: [
          { type: "slider", key: "rgb_shift_x", label: "Shift X", min: -128, max: 128, step: 1, decimals: 0 },
          { type: "slider", key: "rgb_shift_y", label: "Shift Y", min: -128, max: 128, step: 1, decimals: 0 },
          { type: "slider", key: "chromatic_green_shift", label: "Green Bias", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "chromatic_edge_weight", label: "Edge Weight", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Prism",
        note: "secondary",
        controls: [
          { type: "slider", key: "prismatic_strength", label: "Prism Strength", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "prismatic_distance", label: "Distance", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "prismatic_angle", label: "Angle", min: 0, max: 360, step: 1, decimals: 0 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the chromatic pass is blended." },
        ],
      },
    ],
  },
  x1Stylize: {
    panelName: "mkr_xprocess_stylize_studio",
    size: [760, 920],
    accent: "#ff7db0",
    title: "Stylize Studio",
    subtitle: "Push posterization, halftone breakup, and ink contours from one compact graphic-treatment panel.",
    defaults: {
      posterize_bits: 8,
      halftone_strength: 0.0,
      halftone_size: 8,
      stylize_ink_strength: 0.0,
      stylize_ink_threshold: 0.28,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      posterize_bits: { min: 1, max: 8, integer: true },
      halftone_strength: { min: 0.0, max: 1.0 },
      halftone_size: { min: 2, max: 128, integer: true },
      stylize_ink_strength: { min: 0.0, max: 1.0 },
      stylize_ink_threshold: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["posterize_bits", "halftone_strength", "halftone_size", "stylize_ink_strength", "stylize_ink_threshold", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Bits", get: (node) => String(Math.round(getNumber(node, "posterize_bits", 8))) },
      { label: "Dots", get: (node) => formatNumber(getNumber(node, "halftone_strength", 0)) },
      { label: "Ink", get: (node) => formatNumber(getNumber(node, "stylize_ink_strength", 0)) },
    ],
    presets: [
      { label: "Graphic Pop", tone: "accent", values: { posterize_bits: 5, halftone_strength: 0.18, halftone_size: 10, stylize_ink_strength: 0.12, stylize_ink_threshold: 0.24 } },
      { label: "Print Dot", values: { posterize_bits: 4, halftone_strength: 0.56, halftone_size: 16, stylize_ink_strength: 0.24, stylize_ink_threshold: 0.30 } },
      { label: "Comic Edge", values: { posterize_bits: 6, halftone_strength: 0.22, halftone_size: 8, stylize_ink_strength: 0.52, stylize_ink_threshold: 0.18 } },
    ],
    graph: {
      title: "Stylize Preview",
      note: "graphic breakup",
      height: 220,
      draw: drawStylizePreview,
      readouts: [
        { label: "DotSize", get: (node) => String(Math.round(getNumber(node, "halftone_size", 8))) },
        { label: "InkThr", get: (node) => formatNumber(getNumber(node, "stylize_ink_threshold", 0.28)) },
        { label: "Bits", get: (node) => String(Math.round(getNumber(node, "posterize_bits", 8))) },
      ],
      help: "The preview combines banding, dot breakup, and contour ink so the node reads like a deliberate illustration tool rather than a loose effect stack.",
    },
    sections: [
      {
        title: "Posterize",
        note: "base",
        controls: [
          { type: "slider", key: "posterize_bits", label: "Posterize Bits", min: 1, max: 8, step: 1, decimals: 0 },
          { type: "slider", key: "halftone_strength", label: "Halftone", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "halftone_size", label: "Dot Size", min: 2, max: 128, step: 1, decimals: 0 },
        ],
      },
      {
        title: "Ink",
        note: "edge",
        controls: [
          { type: "slider", key: "stylize_ink_strength", label: "Ink Strength", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "stylize_ink_threshold", label: "Ink Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the stylize pass is blended." },
        ],
      },
    ],
  },
  x1Pixelate: {
    panelName: "mkr_xprocess_pixelate_studio",
    size: [760, 980],
    accent: "#6fe6ff",
    title: "Pixelate Studio",
    subtitle: "Build chunkier mosaic looks with quantization, filter choices, grid treatment, and smoother cell blending.",
    defaults: {
      pixel_size_x: 8,
      pixel_size_y: 8,
      downsample_mode: "box",
      upscale_mode: "nearest",
      cell_blend: 0.0,
      color_levels: 0,
      grid_strength: 0.0,
      grid_width: 1,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      pixel_size_x: { min: 1, max: 256, integer: true },
      pixel_size_y: { min: 1, max: 256, integer: true },
      cell_blend: { min: 0.0, max: 1.0 },
      color_levels: { min: 0, max: 64, integer: true },
      grid_strength: { min: 0.0, max: 1.0 },
      grid_width: { min: 0, max: 16, integer: true },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["pixel_size_x", "pixel_size_y", "downsample_mode", "upscale_mode", "cell_blend", "color_levels", "grid_strength", "grid_width", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Cell X", get: (node) => String(Math.round(getNumber(node, "pixel_size_x", 8))) },
      { label: "Levels", get: (node) => String(Math.round(getNumber(node, "color_levels", 0))) },
      { label: "Grid", get: (node) => formatNumber(getNumber(node, "grid_strength", 0)) },
    ],
    presets: [
      { label: "Arcade", tone: "accent", values: { pixel_size_x: 10, pixel_size_y: 10, downsample_mode: "box", upscale_mode: "nearest", cell_blend: 0.0, color_levels: 12, grid_strength: 0.12, grid_width: 1 } },
      { label: "Block Print", values: { pixel_size_x: 18, pixel_size_y: 14, downsample_mode: "hamming", upscale_mode: "nearest", cell_blend: 0.12, color_levels: 6, grid_strength: 0.22, grid_width: 2 } },
      { label: "LCD Soft", values: { pixel_size_x: 7, pixel_size_y: 9, downsample_mode: "lanczos", upscale_mode: "bicubic", cell_blend: 0.56, color_levels: 24, grid_strength: 0.08, grid_width: 1 } },
    ],
    graph: {
      title: "Pixel Preview",
      note: "cell grid",
      height: 220,
      draw: drawPixelatePreview,
      readouts: [
        { label: "CellY", get: (node) => String(Math.round(getNumber(node, "pixel_size_y", 8))) },
        { label: "Blend", get: (node) => formatNumber(getNumber(node, "cell_blend", 0)) },
        { label: "Width", get: (node) => String(Math.round(getNumber(node, "grid_width", 1))) },
      ],
      help: "The preview shows cell density, palette stepping, and grid emphasis together, which makes mode choices easier to judge at a glance.",
    },
    sections: [
      {
        title: "Cell Size",
        note: "primary",
        controls: [
          { type: "slider", key: "pixel_size_x", label: "Pixel X", min: 1, max: 256, step: 1, decimals: 0 },
          { type: "slider", key: "pixel_size_y", label: "Pixel Y", min: 1, max: 256, step: 1, decimals: 0 },
          { type: "select", key: "downsample_mode", label: "Downsample", options: [{ label: "box", value: "box" }, { label: "bilinear", value: "bilinear" }, { label: "bicubic", value: "bicubic" }, { label: "nearest", value: "nearest" }, { label: "hamming", value: "hamming" }, { label: "lanczos", value: "lanczos" }] },
          { type: "select", key: "upscale_mode", label: "Upscale", options: [{ label: "nearest", value: "nearest" }, { label: "bilinear", value: "bilinear" }, { label: "bicubic", value: "bicubic" }] },
        ],
      },
      {
        title: "Palette",
        note: "look",
        controls: [
          { type: "slider", key: "cell_blend", label: "Cell Blend", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "color_levels", label: "Color Levels", min: 0, max: 64, step: 1, decimals: 0 },
          { type: "slider", key: "grid_strength", label: "Grid Strength", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "grid_width", label: "Grid Width", min: 0, max: 16, step: 1, decimals: 0 },
        ],
      },
      {
        title: "Blend",
        note: "delivery",
        controls: [
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the pixelate pass is blended." },
        ],
      },
    ],
  },
  x1Fractal: {
    panelName: "mkr_xprocess_fractal_studio",
    size: [760, 940],
    accent: "#7bffc1",
    title: "Fractal Texture Studio",
    subtitle: "Inject layered noise with stronger contrast and channel drift so the texture feels designed, not generic.",
    defaults: {
      fractal_strength: 0.0,
      fractal_scale: 96.0,
      fractal_octaves: 4,
      fractal_seed: 23,
      fractal_contrast: 1.0,
      fractal_drift: 0.1,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      fractal_strength: { min: 0.0, max: 1.0 },
      fractal_scale: { min: 2.0, max: 1024.0 },
      fractal_octaves: { min: 1, max: 8, integer: true },
      fractal_seed: { min: 0, max: 999999, integer: true },
      fractal_contrast: { min: 0.1, max: 3.0 },
      fractal_drift: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["fractal_strength", "fractal_scale", "fractal_octaves", "fractal_seed", "fractal_contrast", "fractal_drift", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "fractal_strength", 0)) },
      { label: "Contrast", get: (node) => formatNumber(getNumber(node, "fractal_contrast", 1)) },
      { label: "Drift", get: (node) => formatNumber(getNumber(node, "fractal_drift", 0.1)) },
    ],
    presets: [
      { label: "Nebula", tone: "accent", values: { fractal_strength: 0.32, fractal_scale: 148, fractal_octaves: 5, fractal_seed: 23, fractal_contrast: 1.34, fractal_drift: 0.26 } },
      { label: "Dust Pass", values: { fractal_strength: 0.18, fractal_scale: 84, fractal_octaves: 4, fractal_seed: 144, fractal_contrast: 0.86, fractal_drift: 0.08 } },
      { label: "Energy Vein", values: { fractal_strength: 0.46, fractal_scale: 44, fractal_octaves: 6, fractal_seed: 61, fractal_contrast: 1.82, fractal_drift: 0.42 } },
    ],
    graph: {
      title: "Fractal Preview",
      note: "layered field",
      height: 220,
      draw: drawFractalPreview,
      readouts: [
        { label: "Scale", get: (node) => formatNumber(getNumber(node, "fractal_scale", 96), 0) },
        { label: "Oct", get: (node) => String(Math.round(getNumber(node, "fractal_octaves", 4))) },
        { label: "Seed", get: (node) => String(Math.round(getNumber(node, "fractal_seed", 23))) },
      ],
      help: "The preview emphasizes layered motion and color drift so the node feels like a controllable texture generator instead of a single noise slider.",
    },
    sections: [
      {
        title: "Noise Core",
        note: "primary",
        controls: [
          { type: "slider", key: "fractal_strength", label: "Strength", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "fractal_scale", label: "Scale", min: 2, max: 1024, step: 1, decimals: 0 },
          { type: "slider", key: "fractal_octaves", label: "Octaves", min: 1, max: 8, step: 1, decimals: 0 },
          { type: "seed", key: "fractal_seed", label: "Seed", min: 0, max: 999999 },
        ],
      },
      {
        title: "Character",
        note: "texture",
        controls: [
          { type: "slider", key: "fractal_contrast", label: "Contrast", min: 0.1, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "fractal_drift", label: "Channel Drift", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the fractal pass is blended." },
        ],
      },
    ],
  },
  x1Bokeh: {
    panelName: "mkr_xprocess_bokeh_studio",
    size: [760, 920],
    accent: "#ffdc9f",
    title: "Bokeh Studio",
    subtitle: "Grow highlight bloom discs with softer falloff and subtle warm or cool tinting.",
    defaults: {
      bokeh_strength: 0.0,
      bokeh_radius: 10.0,
      bokeh_threshold: 0.72,
      bokeh_softness: 0.5,
      bokeh_warmth: 0.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      bokeh_strength: { min: 0.0, max: 2.0 },
      bokeh_radius: { min: 0.0, max: 128.0 },
      bokeh_threshold: { min: 0.0, max: 1.0 },
      bokeh_softness: { min: 0.0, max: 1.0 },
      bokeh_warmth: { min: -1.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["bokeh_strength", "bokeh_radius", "bokeh_threshold", "bokeh_softness", "bokeh_warmth", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "bokeh_strength", 0)) },
      { label: "Soft", get: (node) => formatNumber(getNumber(node, "bokeh_softness", 0.5)) },
      { label: "Warm", get: (node) => formatSigned(getNumber(node, "bokeh_warmth", 0), 2) },
    ],
    presets: [
      { label: "Wedding", tone: "accent", values: { bokeh_strength: 0.42, bokeh_radius: 18, bokeh_threshold: 0.74, bokeh_softness: 0.68, bokeh_warmth: 0.16 } },
      { label: "Neon Balls", values: { bokeh_strength: 0.84, bokeh_radius: 22, bokeh_threshold: 0.82, bokeh_softness: 0.34, bokeh_warmth: -0.18 } },
      { label: "Street Glow", values: { bokeh_strength: 0.56, bokeh_radius: 14, bokeh_threshold: 0.68, bokeh_softness: 0.58, bokeh_warmth: 0.08 } },
    ],
    graph: {
      title: "Bokeh Preview",
      note: "highlight discs",
      height: 220,
      draw: drawBokehPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "bokeh_threshold", 0.72)) },
        { label: "Radius", get: (node) => formatNumber(getNumber(node, "bokeh_radius", 10), 0) },
        { label: "Warm", get: (node) => formatSigned(getNumber(node, "bokeh_warmth", 0), 2) },
      ],
      help: "The preview turns threshold, softness, and warmth into readable highlight discs, so the node feels like a focus-light tool instead of a blurred bloom clone.",
    },
    sections: [
      {
        title: "Disc Shape",
        note: "primary",
        controls: [
          { type: "slider", key: "bokeh_strength", label: "Strength", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "bokeh_radius", label: "Radius", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "bokeh_threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Character",
        note: "look",
        controls: [
          { type: "slider", key: "bokeh_softness", label: "Softness", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "bokeh_warmth", label: "Warmth", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the bokeh pass is blended." },
        ],
      },
    ],
  },
  x1Focus: {
    panelName: "mkr_xprocess_focus_studio",
    size: [760, 860],
    accent: "#79cbff",
    title: "Focus Studio",
    subtitle: "Balance blur and sharpening in a cleaner finishing panel with quick preset behavior.",
    defaults: {
      blur_radius: 0.0,
      sharpen: 0.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      blur_radius: { min: 0.0, max: 128.0 },
      sharpen: { min: 0.0, max: 2.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["blur_radius", "sharpen", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Blur", get: (node) => formatNumber(getNumber(node, "blur_radius", 0), 1) },
      { label: "Sharp", get: (node) => formatNumber(getNumber(node, "sharpen", 0), 2) },
      { label: "Mask", get: (node) => formatNumber(getNumber(node, "mask_feather", 12), 1) },
    ],
    presets: [
      { label: "Portrait", tone: "accent", values: { blur_radius: 1.2, sharpen: 0.18 } },
      { label: "Crunch", values: { blur_radius: 0.0, sharpen: 0.74 } },
      { label: "Soft Lens", values: { blur_radius: 2.8, sharpen: 0.08 } },
    ],
    graph: {
      title: "Focus Preview",
      note: "clarity window",
      height: 208,
      draw: drawFocusPreview,
      readouts: [
        { label: "Blur", get: (node) => formatNumber(getNumber(node, "blur_radius", 0), 1) },
        { label: "Sharp", get: (node) => formatNumber(getNumber(node, "sharpen", 0), 2) },
        { label: "Mix", get: () => "local" },
      ],
      help: "The preview illustrates sharp-center versus soft-frame bias so the node reads like a focus finishing tool instead of two bare sliders.",
    },
    sections: [
      {
        title: "Focus",
        note: "primary",
        controls: [
          { type: "slider", key: "blur_radius", label: "Blur Radius", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "sharpen", label: "Sharpen", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the focus pass is blended." },
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
      max: spec.max ?? 99999999,
      onChange: (value) => {
        setWidgetValue(node, spec.key, Math.round(value));
        refresh();
      },
      onReseed: () => {
        const next = Math.floor(Math.random() * (spec.max ?? 99999999));
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
    kicker: "MKR SHIFT PROCESS",
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

  if (node.__mkrXProcessPanelInstalled) {
    node.__mkrXProcessRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrXProcessPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrXProcessRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrXProcessRefreshHooksInstalled", refresh);
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
