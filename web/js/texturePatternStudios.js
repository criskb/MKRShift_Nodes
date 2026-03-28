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

const EXTENSION_NAME = "MKRShift.TexturePatternStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-texture-pattern-studios-v1";
const MAX_SEED = 2147483647;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function fract(value) {
  return value - Math.floor(value);
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
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
    .mkr-texture-pattern-select,
    .mkr-texture-pattern-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-texture-pattern-select {
      margin-top: 4px;
    }

    .mkr-texture-pattern-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      margin-top: 4px;
    }

    .mkr-texture-pattern-callout {
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
  wrap.className = "mkr-texture-pattern-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-texture-pattern-number";
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
  input.className = "mkr-texture-pattern-number";
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
  select.className = "mkr-texture-pattern-select";
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
  node.onConfigure = function onConfigureTexturePatternPanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeTexturePatternPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedTexturePatternPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawTilePreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(134,208,255,0.28)");
  fillChecker(ctx, frame, 16, "rgba(255,255,255,0.04)", "rgba(255,255,255,0.014)");

  const tilesX = Math.max(1, Math.round(getNumber(node, "tiles_x", config.defaults.tiles_x)));
  const tilesY = Math.max(1, Math.round(getNumber(node, "tiles_y", config.defaults.tiles_y)));
  const showSeams = getBoolean(node, "show_seams", config.defaults.show_seams);
  const seamWidth = getNumber(node, "seam_width", config.defaults.seam_width);
  const seamOpacity = getNumber(node, "seam_opacity", config.defaults.seam_opacity);
  const seamSoftness = getNumber(node, "seam_softness", config.defaults.seam_softness);

  const cellW = frame.w / tilesX;
  const cellH = frame.h / tilesY;
  for (let row = 0; row < tilesY; row += 1) {
    for (let col = 0; col < tilesX; col += 1) {
      const x = frame.x + (col * cellW);
      const y = frame.y + (row * cellH);
      const grad = ctx.createLinearGradient(x, y, x + cellW, y + cellH);
      const hue = 204 + ((col / Math.max(1, tilesX - 1)) * 56) + ((row / Math.max(1, tilesY - 1)) * 22);
      grad.addColorStop(0, `hsla(${hue} 44% 40% / 0.84)`);
      grad.addColorStop(1, `hsla(${hue + 18} 28% 22% / 0.94)`);
      ctx.fillStyle = grad;
      ctx.fillRect(x, y, Math.ceil(cellW) + 1, Math.ceil(cellH) + 1);

      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.strokeRect(x + 0.5, y + 0.5, Math.max(0, cellW - 1), Math.max(0, cellH - 1));

      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + 10, y + (cellH * 0.72));
      ctx.bezierCurveTo(x + (cellW * 0.34), y + (cellH * 0.26), x + (cellW * 0.66), y + (cellH * 0.94), x + cellW - 10, y + (cellH * 0.34));
      ctx.stroke();
    }
  }

  if (showSeams) {
    ctx.save();
    ctx.shadowColor = `rgba(198, 246, 255, ${0.18 + (seamOpacity * 0.42)})`;
    ctx.shadowBlur = 6 + (seamSoftness * 1.4);
    ctx.strokeStyle = `rgba(255, 244, 192, ${0.18 + (seamOpacity * 0.78)})`;
    ctx.lineWidth = Math.max(1, seamWidth);
    for (let col = 1; col < tilesX; col += 1) {
      const x = frame.x + (col * cellW);
      ctx.beginPath();
      ctx.moveTo(x, frame.y + 4);
      ctx.lineTo(x, frame.y + frame.h - 4);
      ctx.stroke();
    }
    for (let row = 1; row < tilesY; row += 1) {
      const y = frame.y + (row * cellH);
      ctx.beginPath();
      ctx.moveTo(frame.x + 4, y);
      ctx.lineTo(frame.x + frame.w - 4, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawLabel(ctx, `${tilesX} x ${tilesY} repeat`, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
  drawLabel(ctx, showSeams ? "seam overlay" : "clean preview", frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.64)", 10, "right");
}

function traceHexPath(ctx, cx, cy, radius) {
  for (let i = 0; i < 6; i += 1) {
    const angle = ((Math.PI / 180) * (60 * i - 30));
    const x = cx + (Math.cos(angle) * radius);
    const y = cy + (Math.sin(angle) * radius);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
}

function drawHexPreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(130,255,199,0.28)");
  const mode = String(getValue(node, "pattern_mode", config.defaults.pattern_mode));
  const scalePx = getNumber(node, "hex_scale_px", config.defaults.hex_scale_px);
  const lineWidth = getNumber(node, "line_width", config.defaults.line_width);
  const softness = getNumber(node, "softness", config.defaults.softness);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const balance = getNumber(node, "balance", config.defaults.balance);
  const invert = getBoolean(node, "invert", config.defaults.invert);
  const seed = Math.round(getNumber(node, "seed", config.defaults.seed));

  const radius = clamp(scalePx * 0.18, 16, 42);
  const xStep = radius * 1.68;
  const yStep = radius * 1.46;
  const baseLight = invert ? 24 : 68;
  const fillLight = invert ? 22 : 44;
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  bg.addColorStop(0, `hsla(194 34% ${baseLight - (balance * 10)}% / 0.16)`);
  bg.addColorStop(1, `hsla(46 28% ${36 + (balance * 8)}% / 0.12)`);
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  for (let row = -1; row < Math.ceil(frame.h / yStep) + 2; row += 1) {
    for (let col = -1; col < Math.ceil(frame.w / xStep) + 2; col += 1) {
      const cx = frame.x + 22 + (col * xStep) + ((row % 2) * (xStep * 0.5));
      const cy = frame.y + 22 + (row * yStep);
      const n = noise2D(col * 0.7, row * 0.7, seed);
      const hue = 176 + (n * 32);
      const highlight = clamp(42 + (contrast * 10) + (n * 14), 18, 78);
      const shadow = clamp(fillLight - (softness * 10) + (n * 8), 10, 72);

      ctx.beginPath();
      traceHexPath(ctx, cx, cy, radius);

      if (mode === "fill" || mode === "bevel") {
        const fill = ctx.createRadialGradient(cx - (radius * 0.24), cy - (radius * 0.34), 3, cx, cy, radius * 1.12);
        fill.addColorStop(0, `hsla(${hue} 40% ${highlight}% / 0.82)`);
        fill.addColorStop(1, `hsla(${hue + 12} 26% ${shadow}% / 0.94)`);
        ctx.fillStyle = fill;
        ctx.fill();
      }

      if (mode === "bevel") {
        ctx.strokeStyle = "rgba(255,255,255,0.20)";
        ctx.lineWidth = 1 + (softness * 2.4);
        ctx.stroke();
        ctx.beginPath();
        traceHexPath(ctx, cx, cy, radius * 0.74);
        ctx.strokeStyle = "rgba(18,22,28,0.42)";
        ctx.lineWidth = 1;
        ctx.stroke();
      } else {
        ctx.strokeStyle = `rgba(244,248,252,${0.18 + (lineWidth * 0.64)})`;
        ctx.lineWidth = 1.1 + (lineWidth * 4.4);
        ctx.stroke();
      }

      if (mode === "centers") {
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 0.22, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${0.48 + (contrast * 0.08)})`;
        ctx.fill();
      }
    }
  }

  drawLabel(ctx, mode, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
  drawLabel(ctx, `${Math.round(scalePx)} px`, frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.64)", 10, "right");
}

function weavePatternValue(style, row, col) {
  if (style === "twill") return ((row + col) % 4) < 2;
  if (style === "basket") return ((Math.floor(row / 2) + Math.floor(col / 2)) % 2) === 0;
  return ((row + col) % 2) === 0;
}

function drawWeaveThread(ctx, x, y, w, h, hue, relief, fiber, vertical, bright) {
  const grad = vertical
    ? ctx.createLinearGradient(x, y, x + w, y)
    : ctx.createLinearGradient(x, y, x, y + h);
  const edgeDark = bright ? 28 : 18;
  const centerLight = bright ? 56 + (relief * 12) : 42 + (relief * 8);
  grad.addColorStop(0, `hsla(${hue} 24% ${edgeDark}% / 0.96)`);
  grad.addColorStop(0.5, `hsla(${hue} 28% ${centerLight}% / 0.98)`);
  grad.addColorStop(1, `hsla(${hue} 24% ${edgeDark}% / 0.96)`);
  ctx.fillStyle = grad;
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = `rgba(255,255,255,${0.08 + (relief * 0.12)})`;
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, Math.max(0, w - 1), Math.max(0, h - 1));

  if (fiber > 1e-6) {
    const streaks = Math.max(2, Math.round(2 + (fiber * 7)));
    ctx.strokeStyle = `rgba(255,255,255,${0.05 + (fiber * 0.10)})`;
    ctx.lineWidth = 0.8;
    for (let i = 0; i < streaks; i += 1) {
      const t = (i + 1) / (streaks + 1);
      ctx.beginPath();
      if (vertical) {
        const px = x + (w * t);
        ctx.moveTo(px, y + 1);
        ctx.lineTo(px + ((noise2D(px, y, i) - 0.5) * 2.5), y + h - 1);
      } else {
        const py = y + (h * t);
        ctx.moveTo(x + 1, py);
        ctx.lineTo(x + w - 1, py + ((noise2D(x, py, i) - 0.5) * 2.5));
      }
      ctx.stroke();
    }
  }
}

function drawWeavePreview(ctx, width, height, node, config) {
  const frame = drawFrame(ctx, width, height, "rgba(255,193,122,0.28)");
  fillChecker(ctx, frame, 16, "rgba(255,255,255,0.028)", "rgba(255,255,255,0.012)");

  const style = String(getValue(node, "style", config.defaults.style));
  const warpScale = getNumber(node, "warp_scale_px", config.defaults.warp_scale_px);
  const weftScale = getNumber(node, "weft_scale_px", config.defaults.weft_scale_px);
  const threadWidth = getNumber(node, "thread_width", config.defaults.thread_width);
  const relief = getNumber(node, "relief", config.defaults.relief);
  const fiber = getNumber(node, "fiber_variation", config.defaults.fiber_variation);
  const contrast = getNumber(node, "contrast", config.defaults.contrast);
  const balance = getNumber(node, "balance", config.defaults.balance);
  const invert = getBoolean(node, "invert", config.defaults.invert);

  const cols = clamp(Math.round(frame.w / clamp(warpScale, 8, 320) * 1.9), 5, 18);
  const rows = clamp(Math.round(frame.h / clamp(weftScale, 8, 320) * 1.9), 5, 18);
  const colW = frame.w / cols;
  const rowH = frame.h / rows;
  const bandW = Math.max(4, colW * clamp(threadWidth, 0.12, 0.98));
  const bandH = Math.max(4, rowH * clamp(threadWidth, 0.12, 0.98));
  const hue = invert ? 210 : 34;

  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  bg.addColorStop(0, `hsla(${hue} 18% ${invert ? 58 : 22}% / 0.18)`);
  bg.addColorStop(1, `hsla(${hue + 24} 18% ${invert ? 28 : 14}% / 0.22)`);
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const x = frame.x + (col * colW);
      const y = frame.y + (row * rowH);
      const overWarp = weavePatternValue(style, row, col);
      const offsetX = x + ((colW - bandW) * 0.5);
      const offsetY = y + ((rowH - bandH) * 0.5);

      if (!overWarp) {
        drawWeaveThread(ctx, x, offsetY, colW, bandH, hue + 2 + (contrast * 2), relief, fiber, false, false);
        drawWeaveThread(ctx, offsetX, y, bandW, rowH, hue + 8, relief, fiber, true, true);
      } else {
        drawWeaveThread(ctx, offsetX, y, bandW, rowH, hue + 8, relief, fiber, true, false);
        drawWeaveThread(ctx, x, offsetY, colW, bandH, hue + 2 + (contrast * 2), relief, fiber, false, true);
      }
    }
  }

  if (Math.abs(balance) > 1e-6) {
    ctx.fillStyle = `rgba(255,255,255,${Math.abs(balance) * 0.08})`;
    ctx.fillRect(frame.x, frame.y, frame.w, frame.h);
  }

  drawLabel(ctx, style, frame.x + 10, frame.y + 14, "rgba(245,247,250,0.78)", 10);
  drawLabel(ctx, `${Math.round(warpScale)} x ${Math.round(weftScale)} px`, frame.x + frame.w - 10, frame.y + 14, "rgba(245,247,250,0.64)", 10, "right");
}

const NODE_CONFIGS = {
  x1TextureTilePreview: {
    panelName: "mkrX1TextureTilePreviewStudio",
    size: [720, 700],
    accent: "#86d0ff",
    title: "Tile Preview Studio",
    subtitle: "Inspect repeated layout and seam visibility before the texture leaves lookdev.",
    defaults: {
      tiles_x: 3,
      tiles_y: 3,
      show_seams: true,
      seam_width: 2.0,
      seam_opacity: 0.65,
      seam_softness: 1.0,
    },
    numericSpecs: {
      tiles_x: { min: 1, max: 8, integer: true },
      tiles_y: { min: 1, max: 8, integer: true },
      seam_width: { min: 0.0, max: 32.0 },
      seam_opacity: { min: 0.0, max: 1.0 },
      seam_softness: { min: 0.0, max: 32.0 },
    },
    booleanKeys: ["show_seams"],
    legacyNames: ["tiles_x", "tiles_y", "show_seams", "seam_width", "seam_opacity", "seam_softness"],
    metrics: [
      { label: "Grid", get: (node) => `${Math.round(getNumber(node, "tiles_x", 3))}x${Math.round(getNumber(node, "tiles_y", 3))}` },
      { label: "Seams", get: (node) => getBoolean(node, "show_seams", true) ? "Visible" : "Hidden" },
      { label: "Opacity", get: (node) => formatNumber(getNumber(node, "seam_opacity", 0.65), 2) },
    ],
    presets: [
      { label: "3x3", tone: "accent", values: { tiles_x: 3, tiles_y: 3, show_seams: true, seam_width: 2.0, seam_opacity: 0.65, seam_softness: 1.0 } },
      { label: "4x2", values: { tiles_x: 4, tiles_y: 2, show_seams: true, seam_width: 3.0, seam_opacity: 0.55, seam_softness: 1.6 } },
      { label: "Seam Inspect", values: { tiles_x: 2, tiles_y: 2, show_seams: true, seam_width: 5.0, seam_opacity: 0.82, seam_softness: 3.4 } },
      { label: "Clean Grid", values: { tiles_x: 3, tiles_y: 3, show_seams: false, seam_width: 2.0, seam_opacity: 0.0, seam_softness: 1.0 } },
    ],
    graph: {
      title: "Tile Mosaic",
      note: "repeat layout",
      height: 258,
      help: "Use this to inspect repeat breakup and seam readability before you commit to export or material assembly.",
      readouts: [
        { label: "Seam Width", get: (node) => `${formatNumber(getNumber(node, "seam_width", 2), 1)} px` },
        { label: "Softness", get: (node) => `${formatNumber(getNumber(node, "seam_softness", 1), 1)} px` },
      ],
      draw: drawTilePreview,
    },
    sections: [
      {
        title: "Grid Layout",
        note: "repeat count",
        controls: [
          { key: "tiles_x", type: "number", label: "Tiles X", min: 1, max: 8, step: 1, decimals: 0 },
          { key: "tiles_y", type: "number", label: "Tiles Y", min: 1, max: 8, step: 1, decimals: 0 },
          { key: "show_seams", type: "toggle", label: "Show Seams", description: "Overlay seam guides on top of the tiled layout." },
        ],
      },
      {
        title: "Seam Overlay",
        note: "inspection",
        controls: [
          { key: "seam_width", label: "Seam Width", min: 0.0, max: 16.0, step: 0.1, decimals: 1 },
          { key: "seam_softness", label: "Seam Softness", min: 0.0, max: 16.0, step: 0.1, decimals: 1 },
          { key: "seam_opacity", label: "Seam Opacity", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
        ],
      },
    ],
  },
  x1TextureHexTiles: {
    panelName: "mkrX1TextureHexTilesStudio",
    size: [780, 820],
    accent: "#7ff1c6",
    title: "Hex Tiles Studio",
    subtitle: "Author honeycomb, cells, and beveled scale fields with clearer pattern previews and shaping controls.",
    defaults: {
      width: 1024,
      height: 1024,
      pattern_mode: "fill",
      hex_scale_px: 84.0,
      line_width: 0.18,
      softness: 0.0,
      contrast: 1.15,
      balance: 0.0,
      invert: false,
      seed: 67,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      hex_scale_px: { min: 4.0, max: 4096.0 },
      line_width: { min: 0.01, max: 1.0 },
      softness: { min: 0.0, max: 1.0 },
      contrast: { min: 0.05, max: 4.0 },
      balance: { min: -1.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
    },
    booleanKeys: ["invert"],
    legacyNames: ["width", "height", "pattern_mode", "hex_scale_px", "line_width", "softness", "contrast", "balance", "invert", "seed"],
    metrics: [
      { label: "Mode", get: (node) => String(getValue(node, "pattern_mode", "fill")) },
      { label: "Scale", get: (node) => `${Math.round(getNumber(node, "hex_scale_px", 84))} px` },
      { label: "Seed", get: (node) => String(Math.round(getNumber(node, "seed", 67))) },
    ],
    presets: [
      { label: "Fill", tone: "accent", values: { width: 1024, height: 1024, pattern_mode: "fill", hex_scale_px: 84.0, line_width: 0.18, softness: 0.0, contrast: 1.15, balance: 0.0, invert: false, seed: 67 } },
      { label: "Lines", values: { width: 1024, height: 1024, pattern_mode: "lines", hex_scale_px: 92.0, line_width: 0.28, softness: 0.10, contrast: 1.34, balance: -0.08, invert: false, seed: 81 } },
      { label: "Bevel", values: { width: 1024, height: 1024, pattern_mode: "bevel", hex_scale_px: 74.0, line_width: 0.16, softness: 0.22, contrast: 1.22, balance: 0.04, invert: false, seed: 52 } },
    ],
    graph: {
      title: "Honeycomb Preview",
      note: "pattern field",
      height: 284,
      help: "The sketch exaggerates cell scale, line weight, and bevel softness so you can judge the pattern read before generating the final map.",
      readouts: [
        { label: "Line Width", get: (node) => formatNumber(getNumber(node, "line_width", 0.18), 2) },
        { label: "Softness", get: (node) => formatNumber(getNumber(node, "softness", 0), 2) },
      ],
      draw: drawHexPreview,
    },
    sections: [
      {
        title: "Output Size",
        note: "map resolution",
        controls: [
          { key: "width", type: "number", label: "Width", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "height", type: "number", label: "Height", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "pattern_mode", type: "select", label: "Mode", options: [{ label: "Fill", value: "fill" }, { label: "Lines", value: "lines" }, { label: "Centers", value: "centers" }, { label: "Bevel", value: "bevel" }] },
        ],
      },
      {
        title: "Hex Layout",
        note: "cell structure",
        controls: [
          { key: "hex_scale_px", label: "Hex Scale", min: 4.0, max: 384.0, step: 1.0, decimals: 0 },
          { key: "line_width", label: "Line Width", min: 0.01, max: 1.0, step: 0.01, decimals: 2 },
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
  x1TextureWeavePattern: {
    panelName: "mkrX1TextureWeavePatternStudio",
    size: [780, 840],
    accent: "#ffbf7c",
    title: "Weave Pattern Studio",
    subtitle: "Shape cloth, carbon, and woven technical patterns with clearer warp-weft behavior and richer fiber breakup controls.",
    defaults: {
      width: 1024,
      height: 1024,
      style: "plain",
      warp_scale_px: 32.0,
      weft_scale_px: 32.0,
      thread_width: 0.72,
      relief: 0.82,
      fiber_variation: 0.22,
      contrast: 1.2,
      balance: 0.0,
      invert: false,
      seed: 79,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      warp_scale_px: { min: 4.0, max: 4096.0 },
      weft_scale_px: { min: 4.0, max: 4096.0 },
      thread_width: { min: 0.05, max: 0.98 },
      relief: { min: 0.0, max: 1.0 },
      fiber_variation: { min: 0.0, max: 1.0 },
      contrast: { min: 0.05, max: 4.0 },
      balance: { min: -1.0, max: 1.0 },
      seed: { min: 0, max: MAX_SEED, integer: true },
    },
    booleanKeys: ["invert"],
    legacyNames: ["width", "height", "style", "warp_scale_px", "weft_scale_px", "thread_width", "relief", "fiber_variation", "contrast", "balance", "invert", "seed"],
    metrics: [
      { label: "Style", get: (node) => String(getValue(node, "style", "plain")) },
      { label: "Thread", get: (node) => formatNumber(getNumber(node, "thread_width", 0.72), 2) },
      { label: "Relief", get: (node) => formatNumber(getNumber(node, "relief", 0.82), 2) },
    ],
    presets: [
      { label: "Plain", tone: "accent", values: { width: 1024, height: 1024, style: "plain", warp_scale_px: 32.0, weft_scale_px: 32.0, thread_width: 0.72, relief: 0.82, fiber_variation: 0.22, contrast: 1.2, balance: 0.0, invert: false, seed: 79 } },
      { label: "Twill", values: { width: 1024, height: 1024, style: "twill", warp_scale_px: 28.0, weft_scale_px: 34.0, thread_width: 0.76, relief: 0.88, fiber_variation: 0.28, contrast: 1.28, balance: -0.04, invert: false, seed: 94 } },
      { label: "Basket", values: { width: 1024, height: 1024, style: "basket", warp_scale_px: 40.0, weft_scale_px: 40.0, thread_width: 0.80, relief: 0.74, fiber_variation: 0.18, contrast: 1.12, balance: 0.03, invert: false, seed: 58 } },
    ],
    graph: {
      title: "Weave Preview",
      note: "warp and weft",
      height: 294,
      help: "The preview emphasizes over-under structure, thread width, and fiber breakup so the pattern reads like a real woven surface before export.",
      readouts: [
        { label: "Fiber", get: (node) => formatNumber(getNumber(node, "fiber_variation", 0.22), 2) },
        { label: "Balance", get: (node) => formatNumber(getNumber(node, "balance", 0.0), 2) },
      ],
      draw: drawWeavePreview,
    },
    sections: [
      {
        title: "Output Size",
        note: "map resolution",
        controls: [
          { key: "width", type: "number", label: "Width", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "height", type: "number", label: "Height", min: 64, max: 4096, step: 1, decimals: 0 },
          { key: "style", type: "select", label: "Style", options: [{ label: "Plain", value: "plain" }, { label: "Twill", value: "twill" }, { label: "Basket", value: "basket" }] },
        ],
      },
      {
        title: "Weave Layout",
        note: "thread structure",
        controls: [
          { key: "warp_scale_px", label: "Warp Scale", min: 4.0, max: 256.0, step: 1.0, decimals: 0 },
          { key: "weft_scale_px", label: "Weft Scale", min: 4.0, max: 256.0, step: 1.0, decimals: 0 },
          { key: "thread_width", label: "Thread Width", min: 0.05, max: 0.98, step: 0.01, decimals: 2 },
          { key: "relief", label: "Relief", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
          { key: "fiber_variation", label: "Fiber Variation", min: 0.0, max: 1.0, step: 0.01, decimals: 2 },
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
      note.className = "mkr-texture-pattern-callout";
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

  if (node.__mkrTexturePatternPanelInstalled) {
    node.__mkrTexturePatternRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrTexturePatternPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrTexturePatternRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrTexturePatternRefreshHooksInstalled", refresh);
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
