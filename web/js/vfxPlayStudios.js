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

const EXTENSION_NAME = "MKRShift.VFXPlayStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-vfx-play-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function seededValue(seed) {
  let state = (Math.imul(seed, 1103515245) + 12345) >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

function safeViewText(getter, node, fallback = "--") {
  try {
    const value = getter?.(node);
    return value ?? fallback;
  } catch (error) {
    console.warn("[MKRShift.VFXPlayStudios] view getter failed", error);
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
    .mkr-play-select,
    .mkr-play-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-play-select {
      margin-top: 4px;
    }

    .mkr-play-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
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
  select.className = "mkr-play-select";
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
  wrap.className = "mkr-play-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-play-number";
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

function drawKaleidoPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(138,188,255,0.22)");
  const segments = Math.max(2, Math.round(getNumber(node, "segments", 6)));
  const rotation = (getNumber(node, "rotation", 0) * Math.PI) / 180;
  const spin = getNumber(node, "spin", 35);
  const sourceAngle = (getNumber(node, "source_angle", 0) * Math.PI) / 180;
  const sourceSpread = getNumber(node, "source_spread", 0.75);
  const sourceOrbit = getNumber(node, "source_orbit", 0.0);
  const prismSplit = getNumber(node, "prism_split", 0.08);
  const cx = frame.x + (frame.w * getNumber(node, "center_x", 0.5));
  const cy = frame.y + (frame.h * getNumber(node, "center_y", 0.5));
  const radius = Math.min(frame.w, frame.h) * 0.44;
  const sector = (Math.PI * 2) / segments;
  const orbitRadius = radius * 0.62 * Math.max(0, Math.min(1, sourceOrbit));
  const sourceX = cx + Math.cos(sourceAngle) * orbitRadius;
  const sourceY = cy + Math.sin(sourceAngle) * orbitRadius;

  const bg = ctx.createRadialGradient(cx, cy, radius * 0.16, cx, cy, radius * 1.16);
  bg.addColorStop(0, "rgba(26,33,58,0.98)");
  bg.addColorStop(0.56, "rgba(24,44,88,0.72)");
  bg.addColorStop(1, "rgba(10,14,22,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const bloom = ctx.createRadialGradient(cx, cy, radius * 0.08, cx, cy, radius * 1.08);
  bloom.addColorStop(0, "rgba(132,194,255,0.24)");
  bloom.addColorStop(0.38, "rgba(68,105,255,0.10)");
  bloom.addColorStop(1, "rgba(0,0,0,0.0)");
  ctx.fillStyle = bloom;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  for (let i = 0; i < segments; i += 1) {
    const start = rotation + (i * sector);
    const end = start + sector;
    const sweep = sourceSpread * 220;
    const hue = (i / segments) * sweep + spin * 0.4 + 210;
    const fill = ctx.createLinearGradient(cx, cy, cx + Math.cos(start) * radius, cy + Math.sin(start) * radius);
    fill.addColorStop(0, `hsla(${hue}, 96%, 68%, 0.92)`);
    fill.addColorStop(0.5, `hsla(${hue + 40}, 92%, 52%, 0.34)`);
    fill.addColorStop(1, `hsla(${hue + 72}, 88%, 38%, 0.10)`);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, end);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();

    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(start + sector * 0.5) * radius * 0.92, cy + Math.sin(start + sector * 0.5) * radius * 0.92);
    ctx.stroke();
  }

  ctx.strokeStyle = `rgba(255,255,255,${0.12 + prismSplit * 0.26})`;
  ctx.lineWidth = 1.5;
  for (let i = 0; i < segments; i += 1) {
    const angle = rotation + (i * sector);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 1; i <= 3; i += 1) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius * (i / 3), 0, Math.PI * 2);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  for (let ring = 0; ring < 3; ring += 1) {
    const ringT = ring / 2;
    const rr = radius * (0.28 + ringT * 0.26);
    for (let i = 0; i < segments; i += 1) {
      const angle = rotation + (i * sector) + (sector * 0.5);
      const px = cx + Math.cos(angle) * rr;
      const py = cy + Math.sin(angle) * rr;
      ctx.beginPath();
      ctx.arc(px, py, 2.6 + prismSplit * 6, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (orbitRadius > 1.5) {
    ctx.save();
    ctx.setLineDash([6, 6]);
    ctx.strokeStyle = "rgba(138,188,255,0.32)";
    ctx.beginPath();
    ctx.arc(cx, cy, orbitRadius, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.34)";
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(sourceX, sourceY);
  ctx.stroke();

  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.beginPath();
  ctx.arc(sourceX, sourceY, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(138,188,255,0.62)";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.arc(sourceX, sourceY, 10 + sourceSpread * 8, sourceAngle - 0.34, sourceAngle + 0.34);
  ctx.stroke();

  const sourceCard = {
    x: clamp(sourceX + 14, frame.x + 14, frame.x + frame.w - 74),
    y: clamp(sourceY - 18, frame.y + 14, frame.y + frame.h - 48),
    w: 56,
    h: 30,
  };
  const sourceGrad = ctx.createLinearGradient(sourceCard.x, sourceCard.y, sourceCard.x + sourceCard.w, sourceCard.y + sourceCard.h);
  sourceGrad.addColorStop(0, "rgba(129,195,255,0.88)");
  sourceGrad.addColorStop(0.5, "rgba(255,154,226,0.72)");
  sourceGrad.addColorStop(1, "rgba(255,215,122,0.80)");
  ctx.fillStyle = sourceGrad;
  ctx.fillRect(sourceCard.x, sourceCard.y, sourceCard.w, sourceCard.h);
  ctx.strokeStyle = "rgba(255,255,255,0.24)";
  ctx.lineWidth = 1;
  ctx.strokeRect(sourceCard.x, sourceCard.y, sourceCard.w, sourceCard.h);
  ctx.fillStyle = "rgba(9,13,22,0.78)";
  ctx.beginPath();
  ctx.moveTo(sourceCard.x + 10, sourceCard.y + sourceCard.h - 8);
  ctx.lineTo(sourceCard.x + sourceCard.w * 0.5, sourceCard.y + 8);
  ctx.lineTo(sourceCard.x + sourceCard.w - 10, sourceCard.y + sourceCard.h - 8);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.beginPath();
  ctx.arc(cx, cy, 4, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "rgba(255,255,255,0.22)";
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (let i = 0; i < segments * 2; i += 1) {
    const angle = rotation + (i * sector * 0.5);
    const rr = i % 2 === 0 ? radius * 0.12 : radius * 0.28;
    const px = cx + Math.cos(angle) * rr;
    const py = cy + Math.sin(angle) * rr;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.stroke();
}

function drawGlitchPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,112,168,0.20)");
  const direction = String(getValue(node, "direction", "both"));
  const sliceCount = Math.max(1, Math.round(getNumber(node, "slice_count", 28)));
  const split = getNumber(node, "channel_split", 0.35);
  const seed = Math.round(getNumber(node, "seed", 1337));
  const rnd = seededValue(seed);

  const base = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  base.addColorStop(0, "rgba(30,125,255,0.58)");
  base.addColorStop(0.5, "rgba(31,245,214,0.22)");
  base.addColorStop(1, "rgba(255,64,166,0.46)");
  ctx.fillStyle = base;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const slices = Math.max(3, Math.min(26, Math.round(sliceCount / 10)));
  for (let i = 0; i < slices; i += 1) {
    const horizontal = direction === "horizontal" || (direction === "both" && rnd() > 0.4);
    const size = horizontal ? frame.h * (0.04 + rnd() * 0.12) : frame.w * (0.04 + rnd() * 0.12);
    const pos = horizontal ? frame.y + rnd() * (frame.h - size) : frame.x + rnd() * (frame.w - size);
    const shift = ((rnd() - 0.5) * frame.w * 0.18);
    ctx.save();
    ctx.beginPath();
    if (horizontal) ctx.rect(frame.x, pos, frame.w, size);
    else ctx.rect(pos, frame.y, size, frame.h);
    ctx.clip();
    ctx.translate(horizontal ? shift : 0, horizontal ? 0 : shift * 0.35);
    ctx.fillStyle = `rgba(255,255,255,${0.08 + rnd() * 0.12})`;
    ctx.fillRect(frame.x, frame.y, frame.w, frame.h);
    ctx.restore();
  }

  if (split > 0.001) {
    const offset = split * 18;
    ctx.fillStyle = "rgba(255,60,105,0.18)";
    ctx.fillRect(frame.x + offset, frame.y + 10, frame.w * 0.84, frame.h - 20);
    ctx.fillStyle = "rgba(70,225,255,0.18)";
    ctx.fillRect(frame.x - offset, frame.y + 18, frame.w * 0.84, frame.h - 36);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  for (let i = 0; i < 18; i += 1) {
    const y = frame.y + ((frame.h * i) / 18);
    ctx.beginPath();
    ctx.moveTo(frame.x, y);
    ctx.lineTo(frame.x + frame.w, y);
    ctx.stroke();
  }
}

function paletteForAura(name) {
  const palettes = {
    aurora: ["#0f245c", "#3bd1ff", "#7df9aa"],
    sunset: ["#3f1028", "#ff5b55", "#ffc45c"],
    cyber: ["#120b35", "#864cff", "#31f6de"],
    toxic: ["#12240c", "#7ceb2e", "#f6ff60"],
    mono: ["#0f0f10", "#89898e", "#f4f4f5"],
  };
  return palettes[name] || palettes.aurora;
}

function drawAuraPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(80,235,205,0.22)");
  const palette = paletteForAura(String(getValue(node, "palette", "aurora")));
  const glow = getNumber(node, "glow", 0.45);
  const swirl = getNumber(node, "swirl", 1.1);
  const drift = getNumber(node, "drift", 0.15);
  const intensity = getNumber(node, "intensity", 1);

  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, palette[0]);
  bg.addColorStop(0.55, palette[1]);
  bg.addColorStop(1, palette[2]);
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.globalCompositeOperation = "screen";
  for (let i = 0; i < 5; i += 1) {
    const t = i / 4;
    const waveY = frame.y + frame.h * (0.18 + t * 0.18);
    ctx.beginPath();
    for (let x = 0; x <= frame.w; x += 8) {
      const xx = x / frame.w;
      const y = waveY + Math.sin((xx * Math.PI * (1.6 + swirl)) + drift * 6 + t * 2.4) * (18 + glow * 22 + t * 14);
      if (x === 0) ctx.moveTo(frame.x + x, y);
      else ctx.lineTo(frame.x + x, y);
    }
    ctx.strokeStyle = `rgba(255,255,255,${0.12 + intensity * 0.12})`;
    ctx.lineWidth = 14 - t * 2;
    ctx.stroke();
  }
  ctx.globalCompositeOperation = "source-over";
}

function drawPrismEchoPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,198,94,0.22)");
  const echoes = Math.max(1, Math.round(getNumber(node, "echoes", 4)));
  const distance = getNumber(node, "distance", 36);
  const angle = (getNumber(node, "angle", 24) * Math.PI) / 180;
  const split = getNumber(node, "chroma_split", 0.45);
  const decay = getNumber(node, "decay", 0.62);
  const dx = Math.cos(angle) * distance * 0.22;
  const dy = Math.sin(angle) * distance * 0.22;
  const baseX = frame.x + frame.w * 0.36;
  const baseY = frame.y + frame.h * 0.34;
  const shapeW = frame.w * 0.28;
  const shapeH = frame.h * 0.38;

  for (let i = echoes; i >= 1; i -= 1) {
    const t = i / echoes;
    const alpha = Math.pow(decay, i - 1) * 0.42;
    const offX = dx * i;
    const offY = dy * i;
    ctx.fillStyle = `rgba(255,70,120,${alpha * (0.3 + split * 0.4)})`;
    ctx.fillRect(baseX + offX + split * 12, baseY + offY, shapeW, shapeH);
    ctx.fillStyle = `rgba(66,220,255,${alpha * (0.28 + split * 0.35)})`;
    ctx.fillRect(baseX + offX - split * 12, baseY + offY, shapeW, shapeH);
    ctx.fillStyle = `rgba(255,240,170,${alpha * 0.26})`;
    ctx.fillRect(baseX + offX, baseY + offY, shapeW, shapeH);
  }

  ctx.fillStyle = "rgba(255,255,255,0.90)";
  ctx.fillRect(baseX, baseY, shapeW, shapeH);
}

function drawRipplePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(106,220,255,0.20)");
  const amp = getNumber(node, "amplitude", 28);
  const freq = getNumber(node, "frequency", 6);
  const phase = (getNumber(node, "phase", 0) * Math.PI) / 180;
  const twist = getNumber(node, "twist", 0.35);
  const centerX = frame.x + frame.w * getNumber(node, "center_x", 0.5);
  const centerY = frame.y + frame.h * getNumber(node, "center_y", 0.5);
  const lines = 10;

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1.2;
  for (let iy = 0; iy <= lines; iy += 1) {
    ctx.beginPath();
    for (let ix = 0; ix <= 60; ix += 1) {
      const x = frame.x + frame.w * (ix / 60);
      const yBase = frame.y + frame.h * (iy / lines);
      const dx = (x - centerX) / Math.max(frame.w, 1);
      const dy = (yBase - centerY) / Math.max(frame.h, 1);
      const r = Math.sqrt(dx * dx + dy * dy);
      const a = Math.atan2(dy, dx);
      const offset = Math.sin(r * freq * Math.PI * 4 + phase + a * twist) * amp * 0.18 * Math.max(0, 1 - r * 1.3);
      const y = yBase + offset;
      if (ix === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  for (let ix = 0; ix <= lines; ix += 1) {
    ctx.beginPath();
    for (let iy = 0; iy <= 60; iy += 1) {
      const y = frame.y + frame.h * (iy / 60);
      const xBase = frame.x + frame.w * (ix / lines);
      const dx = (xBase - centerX) / Math.max(frame.w, 1);
      const dy = (y - centerY) / Math.max(frame.h, 1);
      const r = Math.sqrt(dx * dx + dy * dy);
      const a = Math.atan2(dy, dx);
      const offset = Math.sin(r * freq * Math.PI * 4 + phase + a * twist) * amp * 0.18 * Math.max(0, 1 - r * 1.3);
      const x = xBase + offset;
      if (iy === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.beginPath();
  ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
  ctx.fill();
}

const NODE_CONFIGS = {
  x1Kaleido: {
    panelName: "mkr_vfx_kaleido_studio",
    size: [790, 930],
    accent: "#8abcff",
    title: "Kaleido Studio",
    subtitle: "Turn a source image into a mirrored prism with fold control, broader source pickup, chroma splitting, and softer edge treatment.",
    defaults: {
      segments: 6,
      rotation: 0.0,
      spin: 35.0,
      zoom: 1.0,
      center_x: 0.5,
      center_y: 0.5,
      source_angle: 0.0,
      source_spread: 0.75,
      source_orbit: 0.0,
      prism_split: 0.08,
      edge_fade: 0.18,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      segments: { min: 2, max: 32, integer: true },
      rotation: { min: -180.0, max: 180.0 },
      spin: { min: -540.0, max: 540.0 },
      zoom: { min: 0.1, max: 4.0 },
      center_x: { min: 0.0, max: 1.0 },
      center_y: { min: 0.0, max: 1.0 },
      source_angle: { min: -180.0, max: 180.0 },
      source_spread: { min: 0.0, max: 1.0 },
      source_orbit: { min: 0.0, max: 1.0 },
      prism_split: { min: 0.0, max: 1.0 },
      edge_fade: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["segments", "rotation", "spin", "zoom", "center_x", "center_y", "source_angle", "source_spread", "source_orbit", "prism_split", "edge_fade", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Segments", get: (node) => String(Math.round(getNumber(node, "segments", 6))) },
      { label: "Spread", get: (node) => formatNumber(getNumber(node, "source_spread", 0.75)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Crystal", tone: "accent", values: { segments: 8, spin: 42, zoom: 1.15, source_spread: 0.82, prism_split: 0.16, edge_fade: 0.14 } },
      { label: "Bloom", values: { segments: 6, rotation: 16, spin: 22, zoom: 0.92, source_angle: -26, source_spread: 0.68, source_orbit: 0.14, prism_split: 0.22, edge_fade: 0.28 } },
      { label: "Tunnel", values: { segments: 12, rotation: -8, spin: 70, zoom: 1.35, source_spread: 1.0, prism_split: 0.06, edge_fade: 0.08 } },
    ],
    graph: {
      title: "Prism Preview",
      note: "source pickup",
      height: 226,
      draw: drawKaleidoPreview,
      readouts: [
        { label: "Rot", get: (node) => formatSigned(getNumber(node, "rotation", 0), 1) },
        { label: "Spread", get: (node) => formatNumber(getNumber(node, "source_spread", 0.75)) },
        { label: "Orbit", get: (node) => formatNumber(getNumber(node, "source_orbit", 0.0)) },
      ],
      help: "The preview shows both the mirrored sectors and the source pickup orbit, so off-center images are easier to target instead of collapsing into an empty prism.",
    },
    sections: [
      {
        title: "Pattern Core",
        note: "primary",
        controls: [
          { type: "slider", key: "segments", label: "Segments", min: 2, max: 32, step: 1, decimals: 0 },
          { type: "slider", key: "rotation", label: "Rotation", min: -180, max: 180, step: 0.1, decimals: 1 },
          { type: "slider", key: "spin", label: "Spin", min: -540, max: 540, step: 0.1, decimals: 1 },
          { type: "slider", key: "zoom", label: "Zoom", min: 0.1, max: 4, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Placement",
        note: "framing",
        controls: [
          { type: "slider", key: "center_x", label: "Center X", min: 0, max: 1, step: 0.001, decimals: 3 },
          { type: "slider", key: "center_y", label: "Center Y", min: 0, max: 1, step: 0.001, decimals: 3 },
          { type: "slider", key: "source_angle", label: "Source Angle", min: -180, max: 180, step: 0.1, decimals: 1 },
          { type: "slider", key: "source_orbit", label: "Source Orbit", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "source_spread", label: "Source Spread", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Prism Finish",
        note: "blend",
        controls: [
          { type: "slider", key: "prism_split", label: "Prism Split", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "edge_fade", label: "Edge Fade", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the prism effect is blended." },
        ],
      },
    ],
  },
  x1Glitch: {
    panelName: "mkr_vfx_glitch_studio",
    size: [790, 930],
    accent: "#ff70a8",
    title: "Glitch Studio",
    subtitle: "Build directional data tears with slice shifts, RGB splits, analogue ghosting, and signal-gated breakup.",
    defaults: {
      slice_count: 28,
      max_shift: 80,
      direction: "both",
      channel_split: 0.35,
      scanline_jitter: 0.25,
      grain: 0.08,
      ghosting: 0.16,
      luma_gate: 0.0,
      mix: 1.0,
      seed: 1337,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      slice_count: { min: 1, max: 512, integer: true },
      max_shift: { min: 0, max: 1024, integer: true },
      channel_split: { min: 0.0, max: 1.0 },
      scanline_jitter: { min: 0.0, max: 1.0 },
      grain: { min: 0.0, max: 0.5 },
      ghosting: { min: 0.0, max: 1.0 },
      luma_gate: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      seed: { min: 0, max: 99999999, integer: true },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["slice_count", "max_shift", "direction", "channel_split", "scanline_jitter", "grain", "ghosting", "luma_gate", "mix", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Slices", get: (node) => String(Math.round(getNumber(node, "slice_count", 28))) },
      { label: "Shift", get: (node) => `${Math.round(getNumber(node, "max_shift", 80))}px` },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "CRT Tear", tone: "accent", values: { slice_count: 24, max_shift: 56, direction: "horizontal", channel_split: 0.18, scanline_jitter: 0.42, ghosting: 0.18, luma_gate: 0.12 } },
      { label: "Data Melt", values: { slice_count: 52, max_shift: 120, direction: "both", channel_split: 0.58, scanline_jitter: 0.28, ghosting: 0.34, grain: 0.10 } },
      { label: "Vertical Burst", values: { slice_count: 18, max_shift: 96, direction: "vertical", channel_split: 0.42, scanline_jitter: 0.12, ghosting: 0.24, luma_gate: 0.28 } },
    ],
    graph: {
      title: "Signal Preview",
      note: "slice breakup",
      height: 230,
      draw: drawGlitchPreview,
      readouts: [
        { label: "Dir", get: (node) => String(getValue(node, "direction", "both")).slice(0, 3).toUpperCase() },
        { label: "Ghost", get: (node) => formatNumber(getNumber(node, "ghosting", 0.16)) },
        { label: "Gate", get: (node) => formatNumber(getNumber(node, "luma_gate", 0.0)) },
      ],
      help: "The preview sketches slice orientation, RGB split, and scanline breakup so the node reads like a signal tool instead of a parameter dump.",
    },
    sections: [
      {
        title: "Slice Layout",
        note: "primary",
        controls: [
          { type: "slider", key: "slice_count", label: "Slices", min: 1, max: 512, step: 1, decimals: 0 },
          { type: "slider", key: "max_shift", label: "Max Shift", min: 0, max: 1024, step: 1, decimals: 0 },
          { type: "select", key: "direction", label: "Direction", options: [{ label: "horizontal", value: "horizontal" }, { label: "vertical", value: "vertical" }, { label: "both", value: "both" }] },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 99999999 },
        ],
      },
      {
        title: "Signal Breakup",
        note: "texture",
        controls: [
          { type: "slider", key: "channel_split", label: "RGB Split", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "scanline_jitter", label: "Scanline", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "ghosting", label: "Ghosting", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "luma_gate", label: "Luma Gate", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Finish",
        note: "delivery",
        controls: [
          { type: "slider", key: "grain", label: "Grain", min: 0, max: 0.5, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the glitch pass is blended." },
        ],
      },
    ],
  },
  x1AuraFlow: {
    panelName: "mkr_vfx_aura_flow_studio",
    size: [820, 980],
    accent: "#59e8cc",
    title: "Aura Flow Studio",
    subtitle: "Generate or composite flowing light fields with palette direction, glow energy, and blend behavior under one roof.",
    defaults: {
      width: 1024,
      height: 1024,
      batch_size: 1,
      palette: "aurora",
      intensity: 1.0,
      contrast: 1.1,
      noise_scale: 92.0,
      swirl: 1.1,
      sparkle: 0.35,
      glow: 0.45,
      drift: 0.15,
      composite_mode: "replace",
      mix: 1.0,
      seed: 2024,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      width: { min: 64, max: 4096, integer: true },
      height: { min: 64, max: 4096, integer: true },
      batch_size: { min: 1, max: 24, integer: true },
      intensity: { min: 0.0, max: 2.0 },
      contrast: { min: 0.2, max: 3.0 },
      noise_scale: { min: 2.0, max: 512.0 },
      swirl: { min: 0.0, max: 3.0 },
      sparkle: { min: 0.0, max: 1.5 },
      glow: { min: 0.0, max: 2.0 },
      drift: { min: -1.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      seed: { min: 0, max: 99999999, integer: true },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["width", "height", "batch_size", "palette", "intensity", "contrast", "noise_scale", "swirl", "sparkle", "glow", "drift", "composite_mode", "mix", "seed", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Palette", get: (node) => String(getValue(node, "palette", "aurora")) },
      { label: "Mode", get: (node) => String(getValue(node, "composite_mode", "replace")) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Aurora", tone: "accent", values: { palette: "aurora", intensity: 1.0, contrast: 1.1, swirl: 1.1, sparkle: 0.35, glow: 0.45, drift: 0.15 } },
      { label: "Cyber", values: { palette: "cyber", intensity: 1.15, contrast: 1.32, swirl: 1.48, sparkle: 0.18, glow: 0.66, drift: 0.24, composite_mode: "screen" } },
      { label: "Toxic", values: { palette: "toxic", intensity: 0.92, contrast: 1.48, swirl: 0.86, sparkle: 0.52, glow: 0.72, drift: -0.18, composite_mode: "overlay" } },
    ],
    graph: {
      title: "Energy Preview",
      note: "flow field",
      height: 236,
      draw: drawAuraPreview,
      readouts: [
        { label: "Int", get: (node) => formatNumber(getNumber(node, "intensity", 1.0)) },
        { label: "Glow", get: (node) => formatNumber(getNumber(node, "glow", 0.45)) },
        { label: "Drift", get: (node) => formatSigned(getNumber(node, "drift", 0.15), 2) },
      ],
      help: "The preview shows palette energy and flow direction. If an image input is connected, the selected composite mode determines how the aura sits over it.",
    },
    sections: [
      {
        title: "Render Target",
        note: "generator",
        controls: [
          { type: "slider", key: "width", label: "Width", min: 64, max: 4096, step: 8, decimals: 0 },
          { type: "slider", key: "height", label: "Height", min: 64, max: 4096, step: 8, decimals: 0 },
          { type: "slider", key: "batch_size", label: "Batch", min: 1, max: 24, step: 1, decimals: 0 },
          { type: "select", key: "palette", label: "Palette", options: [{ label: "aurora", value: "aurora" }, { label: "sunset", value: "sunset" }, { label: "cyber", value: "cyber" }, { label: "toxic", value: "toxic" }, { label: "mono", value: "mono" }] },
        ],
      },
      {
        title: "Flow Core",
        note: "primary",
        controls: [
          { type: "slider", key: "intensity", label: "Intensity", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "contrast", label: "Contrast", min: 0.2, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "noise_scale", label: "Scale", min: 2, max: 512, step: 1, decimals: 0 },
          { type: "slider", key: "swirl", label: "Swirl", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Glow Finish",
        note: "blend",
        controls: [
          { type: "slider", key: "sparkle", label: "Sparkle", min: 0, max: 1.5, step: 0.01, decimals: 2 },
          { type: "slider", key: "glow", label: "Glow", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "drift", label: "Drift", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "select", key: "composite_mode", label: "Composite", options: [{ label: "replace", value: "replace" }, { label: "screen", value: "screen" }, { label: "add", value: "add" }, { label: "overlay", value: "overlay" }] },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 99999999 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the aura is applied." },
        ],
      },
    ],
  },
  x1PrismEcho: {
    panelName: "mkr_vfx_prism_echo_studio",
    size: [800, 880],
    accent: "#ffc65f",
    title: "Prism Echo Studio",
    subtitle: "Layer angled RGB echoes behind the image for music-video trails, ghosted highlights, and neon lag.",
    defaults: {
      echoes: 4,
      distance: 36.0,
      angle: 24.0,
      decay: 0.62,
      chroma_split: 0.45,
      glow: 0.28,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      echoes: { min: 1, max: 8, integer: true },
      distance: { min: 0.0, max: 512.0 },
      angle: { min: -180.0, max: 180.0 },
      decay: { min: 0.0, max: 1.0 },
      chroma_split: { min: 0.0, max: 1.0 },
      glow: { min: 0.0, max: 2.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["echoes", "distance", "angle", "decay", "chroma_split", "glow", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Echoes", get: (node) => String(Math.round(getNumber(node, "echoes", 4))) },
      { label: "Distance", get: (node) => `${formatNumber(getNumber(node, "distance", 36), 0)}px` },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Music Vid", tone: "accent", values: { echoes: 5, distance: 52, angle: 18, decay: 0.72, chroma_split: 0.62, glow: 0.42 } },
      { label: "Soft Ghost", values: { echoes: 3, distance: 18, angle: 42, decay: 0.48, chroma_split: 0.28, glow: 0.16 } },
      { label: "Neon Trail", values: { echoes: 6, distance: 68, angle: -12, decay: 0.82, chroma_split: 0.78, glow: 0.58 } },
    ],
    graph: {
      title: "Trail Preview",
      note: "echo layout",
      height: 228,
      draw: drawPrismEchoPreview,
      readouts: [
        { label: "Angle", get: (node) => formatSigned(getNumber(node, "angle", 24), 1) },
        { label: "Decay", get: (node) => formatNumber(getNumber(node, "decay", 0.62)) },
        { label: "Glow", get: (node) => formatNumber(getNumber(node, "glow", 0.28)) },
      ],
      help: "This preview maps the echo trail direction and RGB split so you can shape the lag before testing it on the full image.",
    },
    sections: [
      {
        title: "Trail Core",
        note: "primary",
        controls: [
          { type: "slider", key: "echoes", label: "Echoes", min: 1, max: 8, step: 1, decimals: 0 },
          { type: "slider", key: "distance", label: "Distance", min: 0, max: 512, step: 1, decimals: 0 },
          { type: "slider", key: "angle", label: "Angle", min: -180, max: 180, step: 0.1, decimals: 1 },
          { type: "slider", key: "decay", label: "Decay", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Color Lag",
        note: "chromatic offset",
        controls: [
          { type: "slider", key: "chroma_split", label: "RGB Split", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "glow", label: "Glow", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the echo pass is blended." },
        ],
      },
    ],
  },
  x1RippleWarp: {
    panelName: "mkr_vfx_ripple_warp_studio",
    size: [790, 880],
    accent: "#6ad8ff",
    title: "Ripple Warp Studio",
    subtitle: "Push playful wave distortion from a chosen center with controllable ring density, phase, and falloff.",
    defaults: {
      amplitude: 28.0,
      frequency: 6.0,
      phase: 0.0,
      twist: 0.35,
      center_x: 0.5,
      center_y: 0.5,
      falloff: 0.45,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      amplitude: { min: 0.0, max: 256.0 },
      frequency: { min: 0.5, max: 24.0 },
      phase: { min: -360.0, max: 360.0 },
      twist: { min: -2.0, max: 2.0 },
      center_x: { min: 0.0, max: 1.0 },
      center_y: { min: 0.0, max: 1.0 },
      falloff: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["amplitude", "frequency", "phase", "twist", "center_x", "center_y", "falloff", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Amp", get: (node) => `${formatNumber(getNumber(node, "amplitude", 28), 0)}px` },
      { label: "Freq", get: (node) => formatNumber(getNumber(node, "frequency", 6), 2) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Pond", tone: "accent", values: { amplitude: 22, frequency: 5.5, phase: 18, twist: 0.18, falloff: 0.38 } },
      { label: "Heat Ring", values: { amplitude: 36, frequency: 9.0, phase: -30, twist: 0.56, falloff: 0.62 } },
      { label: "Hypno", values: { amplitude: 18, frequency: 13.5, phase: 90, twist: 1.1, falloff: 0.22 } },
    ],
    graph: {
      title: "Warp Preview",
      note: "ripple field",
      height: 228,
      draw: drawRipplePreview,
      readouts: [
        { label: "Phase", get: (node) => formatSigned(getNumber(node, "phase", 0), 1) },
        { label: "Twist", get: (node) => formatSigned(getNumber(node, "twist", 0.35), 2) },
        { label: "Falloff", get: (node) => formatNumber(getNumber(node, "falloff", 0.45)) },
      ],
      help: "The preview shows the ripple field itself, so amplitude and frequency changes read as deformation rather than abstract numbers.",
    },
    sections: [
      {
        title: "Wave Core",
        note: "primary",
        controls: [
          { type: "slider", key: "amplitude", label: "Amplitude", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "slider", key: "frequency", label: "Frequency", min: 0.5, max: 24, step: 0.01, decimals: 2 },
          { type: "slider", key: "phase", label: "Phase", min: -360, max: 360, step: 0.1, decimals: 1 },
          { type: "slider", key: "twist", label: "Twist", min: -2, max: 2, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Placement",
        note: "field center",
        controls: [
          { type: "slider", key: "center_x", label: "Center X", min: 0, max: 1, step: 0.001, decimals: 3 },
          { type: "slider", key: "center_y", label: "Center Y", min: 0, max: 1, step: 0.001, decimals: 3 },
          { type: "slider", key: "falloff", label: "Falloff", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the ripple warp is blended." },
        ],
      },
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(NODE_CONFIGS));

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
        const next = Math.floor(Math.random() * (spec.max ?? 2147483647));
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

function buildPanel(node, config) {
  ensureLocalStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT PLAY",
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

  if (node.__mkrVfxPlayPanelInstalled) {
    node.__mkrVfxPlayRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrVfxPlayPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrVfxPlayRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrVfxPlayRefreshHooksInstalled", refresh);
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
