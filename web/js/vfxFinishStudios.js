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

const EXTENSION_NAME = "MKRShift.VFXFinishStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-vfx-finish-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function average(values) {
  if (!Array.isArray(values) || !values.length) return 0;
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length;
}

function safeViewText(getter, node, fallback = "--") {
  try {
    const value = getter?.(node);
    return value ?? fallback;
  } catch (error) {
    console.warn("[MKRShift.VFXFinishStudios] view getter failed", error);
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
    .mkr-vfx-finish-select {
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

    .mkr-vfx-finish-chip-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 6px;
      margin-top: 8px;
    }

    .mkr-vfx-finish-chip {
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      padding: 6px 8px;
      font-size: 10px;
      color: rgba(242,246,250,0.86);
      text-align: center;
      font-weight: 700;
    }

    .mkr-vfx-finish-chip span {
      display: block;
      margin-top: 4px;
      font-size: 9px;
      color: rgba(223,230,236,0.58);
      font-weight: 500;
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
  select.className = "mkr-vfx-finish-select";
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

function drawAnamorphicPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,181,115,0.22)");
  const horizontal = String(getValue(node, "orientation", "horizontal")) !== "vertical";
  const threshold = getNumber(node, "threshold", 0.74);
  const softness = getNumber(node, "softness", 0.10);
  const lengthPx = getNumber(node, "length_px", 48);
  const strength = getNumber(node, "strength", 0.75);
  const coreBoost = getNumber(node, "core_boost", 1.0);
  const tailSoftness = getNumber(node, "tail_softness", 1.0);
  const tint = [
    clamp(getNumber(node, "tint_r", 0.92), 0, 1),
    clamp(getNumber(node, "tint_g", 0.86), 0, 1),
    clamp(getNumber(node, "tint_b", 1.0), 0, 1),
  ];
  const tintCss = `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, 1)`;
  const glowAlpha = 0.16 + (strength * 0.12);
  const streakLength = horizontal
    ? lerp(frame.w * 0.24, frame.w * 0.92, clamp(lengthPx / 512, 0, 1))
    : lerp(frame.h * 0.24, frame.h * 0.92, clamp(lengthPx / 512, 0, 1));
  const centers = horizontal
    ? [
      [frame.x + frame.w * 0.24, frame.y + frame.h * 0.32],
      [frame.x + frame.w * 0.58, frame.y + frame.h * 0.54],
      [frame.x + frame.w * 0.78, frame.y + frame.h * 0.24],
    ]
    : [
      [frame.x + frame.w * 0.28, frame.y + frame.h * 0.24],
      [frame.x + frame.w * 0.58, frame.y + frame.h * 0.52],
      [frame.x + frame.w * 0.72, frame.y + frame.h * 0.76],
    ];

  const lensBg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  lensBg.addColorStop(0, "rgba(9,11,15,0.96)");
  lensBg.addColorStop(0.55, "rgba(22,26,34,0.94)");
  lensBg.addColorStop(1, "rgba(12,14,20,0.98)");
  ctx.fillStyle = lensBg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const horizon = ctx.createLinearGradient(frame.x, frame.y + frame.h * 0.22, frame.x + frame.w, frame.y + frame.h * 0.78);
  horizon.addColorStop(0, "rgba(65,84,112,0.16)");
  horizon.addColorStop(0.5, "rgba(255,186,122,0.06)");
  horizon.addColorStop(1, "rgba(42,58,91,0.14)");
  ctx.fillStyle = horizon;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  ctx.strokeRect(frame.x + 14, frame.y + 14, frame.w - 28, frame.h - 28);

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 2;
  if (horizontal) {
    ctx.beginPath();
    ctx.moveTo(frame.x + 22, frame.y + frame.h * 0.5);
    ctx.lineTo(frame.x + frame.w - 22, frame.y + frame.h * 0.5);
    ctx.stroke();
  } else {
    ctx.beginPath();
    ctx.moveTo(frame.x + frame.w * 0.5, frame.y + 22);
    ctx.lineTo(frame.x + frame.w * 0.5, frame.y + frame.h - 22);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,255,255,0.04)";
  for (const [cx, cy] of centers) {
    const radius = 7 + (coreBoost * 4.5);
    const glow = ctx.createRadialGradient(cx, cy, radius * 0.2, cx, cy, horizontal ? streakLength * 0.42 : streakLength * 0.42);
    glow.addColorStop(0, `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, ${0.48 + glowAlpha})`);
    glow.addColorStop(0.22, `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, ${0.22 + glowAlpha * 0.55})`);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    if (horizontal) {
      ctx.fillRect(cx - (streakLength * 0.5), cy - 20, streakLength, 40);
    } else {
      ctx.fillRect(cx - 20, cy - (streakLength * 0.5), 40, streakLength);
    }

    const line = ctx.createLinearGradient(
      horizontal ? cx - (streakLength * 0.5) : cx,
      horizontal ? cy : cy - (streakLength * 0.5),
      horizontal ? cx + (streakLength * 0.5) : cx,
      horizontal ? cy : cy + (streakLength * 0.5)
    );
    line.addColorStop(0, "rgba(0,0,0,0)");
    line.addColorStop(clamp(0.32 - (softness * 0.3), 0.08, 0.44), `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, ${0.18 + glowAlpha})`);
    line.addColorStop(0.5, `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, ${0.55 + strength * 0.18})`);
    line.addColorStop(clamp(0.68 + (tailSoftness * 0.08), 0.56, 0.92), `rgba(${Math.round(tint[0] * 255)}, ${Math.round(tint[1] * 255)}, ${Math.round(tint[2] * 255)}, 0.18)`);
    line.addColorStop(1, "rgba(0,0,0,0)");
    ctx.strokeStyle = line;
    ctx.lineWidth = 3 + (coreBoost * 1.8);
    ctx.beginPath();
    if (horizontal) {
      ctx.moveTo(cx - (streakLength * 0.5), cy);
      ctx.lineTo(cx + (streakLength * 0.5), cy);
    } else {
      ctx.moveTo(cx, cy - (streakLength * 0.5));
      ctx.lineTo(cx, cy + (streakLength * 0.5));
    }
    ctx.stroke();

    ctx.strokeStyle = `rgba(255,255,255,${0.14 + softness * 0.42})`;
    ctx.lineWidth = 1.2 + (softness * 1.8);
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 7 + threshold * 10, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = tintCss;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "rgba(255,255,255,0.96)";
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.38, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.font = "11px sans-serif";
  ctx.fillText(horizontal ? "Horizontal sweep" : "Vertical sweep", frame.x + 10, frame.y + frame.h - 12);
  ctx.fillStyle = `rgba(255,255,255,${0.22 + threshold * 0.3})`;
  ctx.fillRect(frame.x + frame.w - 70, frame.y + 10, 52, 8);
  ctx.fillStyle = "rgba(255,255,255,0.42)";
  ctx.fillRect(frame.x + 14, frame.y + frame.h - 24, frame.w * clamp(1.0 - threshold + 0.12, 0.08, 0.92), 6);
}

function drawHeatHazePreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(108,231,255,0.22)");
  const direction = String(getValue(node, "direction", "up"));
  const strength = getNumber(node, "strength_px", 8);
  const scale = getNumber(node, "scale", 3.2);
  const phase = (getNumber(node, "phase_deg", 0) * Math.PI) / 180;
  const turbulence = getNumber(node, "turbulence", 0.55);
  const edgeFalloff = getNumber(node, "edge_falloff", 0.35);
  const split = getNumber(node, "chroma_split_px", 0.8);
  const lines = 9;
  const horizontalFlow = direction === "up" || direction === "down";
  const sign = direction === "up" || direction === "left" ? -1 : 1;

  const horizon = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  horizon.addColorStop(0, "rgba(255,182,120,0.18)");
  horizon.addColorStop(1, "rgba(36,98,160,0.08)");
  ctx.fillStyle = horizon;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const drawHorizontalBand = (line, accentAlpha) => {
    ctx.beginPath();
    for (let step = 0; step <= 72; step += 1) {
      const t = step / 72;
      const xBase = frame.x + (frame.w * t);
      const yBase = frame.y + ((frame.h * line) / lines);
      const along = (yBase - frame.y) / Math.max(frame.h, 1);
      const cross = t;
      const waveA = Math.sin((along * scale * Math.PI * 2.15) + phase);
      const waveB = Math.sin((along * scale * Math.PI * 4.35) - (phase * 1.7) + (cross * Math.PI * 1.1));
      const waveC = Math.cos((cross * scale * Math.PI * 0.85) + (phase * 0.35));
      const field = (waveA * (0.76 - (0.28 * turbulence))) + (waveB * (0.18 + turbulence * 0.58)) + (waveC * (0.06 + (0.18 * turbulence)));
      const edgeWeight = lerp(1.0, Math.abs((line / lines) - 0.5) * 2.0, edgeFalloff);
      const mainOffset = field * strength * 0.54 * edgeWeight;
      const driftOffset = waveB * strength * 0.12 * sign * edgeWeight;
      const px = xBase + (horizontalFlow ? mainOffset : driftOffset);
      const py = yBase + (horizontalFlow ? driftOffset : mainOffset);
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = `rgba(255,255,255,${accentAlpha})`;
    ctx.stroke();
  };

  const drawVerticalBand = (line, accentAlpha) => {
    ctx.beginPath();
    for (let step = 0; step <= 72; step += 1) {
      const t = step / 72;
      const xBase = frame.x + ((frame.w * line) / lines);
      const yBase = frame.y + (frame.h * t);
      const along = (xBase - frame.x) / Math.max(frame.w, 1);
      const cross = t;
      const waveA = Math.sin((along * scale * Math.PI * 2.15) + phase);
      const waveB = Math.sin((along * scale * Math.PI * 4.35) - (phase * 1.7) + (cross * Math.PI * 1.1));
      const waveC = Math.cos((cross * scale * Math.PI * 0.85) + (phase * 0.35));
      const field = (waveA * (0.76 - (0.28 * turbulence))) + (waveB * (0.18 + turbulence * 0.58)) + (waveC * (0.06 + (0.18 * turbulence)));
      const edgeWeight = lerp(1.0, Math.abs((line / lines) - 0.5) * 2.0, edgeFalloff);
      const mainOffset = field * strength * 0.54 * edgeWeight;
      const driftOffset = waveB * strength * 0.12 * sign * edgeWeight;
      const px = xBase + (horizontalFlow ? driftOffset : mainOffset);
      const py = yBase + (horizontalFlow ? mainOffset : driftOffset);
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = `rgba(176,233,255,${accentAlpha})`;
    ctx.stroke();
  };

  ctx.lineWidth = 1.15;
  for (let line = 0; line <= lines; line += 1) {
    drawHorizontalBand(line, 0.14 + (line % 2) * 0.03);
  }

  for (let line = 0; line <= lines; line += 1) {
    drawVerticalBand(line, 0.06 + (line % 2) * 0.02);
  }

  if (split > 0.01) {
    ctx.fillStyle = "rgba(255,94,142,0.12)";
    ctx.fillRect(frame.x + 10, frame.y + 14, frame.w - 20, 10);
    ctx.fillStyle = "rgba(85,236,255,0.12)";
    ctx.fillRect(frame.x + 10, frame.y + frame.h - 24, frame.w - 20, 10);
  }

  const arrowCx = frame.x + frame.w - 34;
  const arrowCy = frame.y + 30;
  ctx.strokeStyle = "rgba(255,255,255,0.82)";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  if (direction === "up" || direction === "down") {
    const headY = arrowCy + (direction === "up" ? -10 : 10);
    const tailY = arrowCy + (direction === "up" ? 10 : -10);
    ctx.moveTo(arrowCx, tailY);
    ctx.lineTo(arrowCx, headY);
    ctx.lineTo(arrowCx - 5, headY + (direction === "up" ? 5 : -5));
    ctx.moveTo(arrowCx, headY);
    ctx.lineTo(arrowCx + 5, headY + (direction === "up" ? 5 : -5));
  } else {
    const headX = arrowCx + (direction === "left" ? -10 : 10);
    const tailX = arrowCx + (direction === "left" ? 10 : -10);
    ctx.moveTo(tailX, arrowCy);
    ctx.lineTo(headX, arrowCy);
    ctx.lineTo(headX + (direction === "left" ? 5 : -5), arrowCy - 5);
    ctx.moveTo(headX, arrowCy);
    ctx.lineTo(headX + (direction === "left" ? 5 : -5), arrowCy + 5);
  }
  ctx.stroke();
}

function drawLightWrapPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,214,114,0.22)");
  const radius = getNumber(node, "wrap_radius", 18);
  const strength = getNumber(node, "wrap_strength", 0.65);
  const holdout = getNumber(node, "inside_holdout", 0.75);
  const blur = getNumber(node, "background_blur", 0);
  const gamma = getNumber(node, "wrap_gamma", 1.0);

  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h);
  bg.addColorStop(0, "rgba(29,59,105,0.95)");
  bg.addColorStop(0.48, "rgba(242,126,69,0.65)");
  bg.addColorStop(1, "rgba(41,21,55,0.95)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.fillStyle = "rgba(255,255,255,0.06)";
  ctx.fillRect(frame.x + 18, frame.y + 26, frame.w * 0.28, frame.h * 0.22);
  ctx.fillRect(frame.x + frame.w * 0.68, frame.y + frame.h * 0.14, frame.w * 0.18, frame.h * 0.46);
  ctx.fillRect(frame.x + frame.w * 0.14, frame.y + frame.h * 0.64, frame.w * 0.22, frame.h * 0.16);

  const silhouette = {
    x: frame.x + frame.w * 0.35,
    y: frame.y + frame.h * 0.17,
    w: frame.w * 0.28,
    h: frame.h * 0.66,
  };

  const backlight = ctx.createRadialGradient(
    frame.x + frame.w * 0.66,
    frame.y + frame.h * 0.36,
    4,
    frame.x + frame.w * 0.66,
    frame.y + frame.h * 0.36,
    frame.w * 0.42
  );
  backlight.addColorStop(0, `rgba(255,245,198,${0.20 + strength * 0.16})`);
  backlight.addColorStop(0.45, `rgba(255,205,114,${0.12 + strength * 0.10})`);
  backlight.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = backlight;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  const halo = ctx.createRadialGradient(
    silhouette.x + (silhouette.w * 0.45),
    silhouette.y + (silhouette.h * 0.52),
    silhouette.w * 0.2,
    silhouette.x + (silhouette.w * 0.45),
    silhouette.y + (silhouette.h * 0.52),
    silhouette.w * (1.1 + radius / 80)
  );
  halo.addColorStop(0, `rgba(255,241,198,${0.0})`);
  halo.addColorStop(clamp(0.34 / gamma, 0.08, 0.52), `rgba(255,231,154,${0.18 + strength * 0.26})`);
  halo.addColorStop(1, "rgba(255,218,128,0)");
  ctx.fillStyle = halo;
  ctx.fillRect(silhouette.x - 60, silhouette.y - 40, silhouette.w + 120, silhouette.h + 80);

  ctx.fillStyle = `rgba(11,12,14,${0.92 - holdout * 0.22})`;
  ctx.beginPath();
  ctx.moveTo(silhouette.x + silhouette.w * 0.2, silhouette.y + silhouette.h);
  ctx.quadraticCurveTo(silhouette.x - 8, silhouette.y + silhouette.h * 0.64, silhouette.x + silhouette.w * 0.2, silhouette.y + silhouette.h * 0.34);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.24, silhouette.y + 2, silhouette.x + silhouette.w * 0.52, silhouette.y);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.82, silhouette.y + 4, silhouette.x + silhouette.w * 0.84, silhouette.y + silhouette.h * 0.34);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w + 12, silhouette.y + silhouette.h * 0.66, silhouette.x + silhouette.w * 0.78, silhouette.y + silhouette.h);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = `rgba(255,233,160,${0.26 + strength * 0.36})`;
  ctx.lineWidth = 2.4 + (radius / 48);
  ctx.beginPath();
  ctx.moveTo(silhouette.x + silhouette.w * 0.16, silhouette.y + silhouette.h * 0.94);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.04, silhouette.y + silhouette.h * 0.62, silhouette.x + silhouette.w * 0.18, silhouette.y + silhouette.h * 0.34);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.24, silhouette.y + silhouette.h * 0.08, silhouette.x + silhouette.w * 0.54, silhouette.y + silhouette.h * 0.06);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.82, silhouette.y + silhouette.h * 0.10, silhouette.x + silhouette.w * 0.84, silhouette.y + silhouette.h * 0.34);
  ctx.quadraticCurveTo(silhouette.x + silhouette.w * 0.96, silhouette.y + silhouette.h * 0.68, silhouette.x + silhouette.w * 0.78, silhouette.y + silhouette.h * 0.94);
  ctx.stroke();

  if (blur > 0.01) {
    ctx.strokeStyle = `rgba(255,255,255,${0.08 + blur / 120})`;
    ctx.lineWidth = 3;
    ctx.strokeRect(frame.x + 12, frame.y + 12, frame.w - 24, frame.h - 24);
  }

  ctx.fillStyle = "rgba(255,255,255,0.68)";
  ctx.font = "11px sans-serif";
  ctx.fillText("FG", silhouette.x + silhouette.w * 0.4, silhouette.y + silhouette.h + 18);
  ctx.fillText("BG wrap", frame.x + frame.w * 0.08, frame.y + 20);
}

function drawAberrationPreview(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(156,142,255,0.22)");
  const strength = getNumber(node, "strength_px", 2.4);
  const radialBias = getNumber(node, "radial_bias", 0.65);
  const greenShift = getNumber(node, "green_shift", 0.0);
  const falloff = getNumber(node, "falloff", 0.65);
  const edgeThreshold = getNumber(node, "edge_threshold", 0.10);

  const inset = lerp(24, 80, clamp(1 - falloff, 0, 1));
  const inner = { x: frame.x + inset, y: frame.y + inset * 0.72, w: frame.w - inset * 2, h: frame.h - inset * 1.44 };
  const spread = 4 + strength * 1.8;

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  ctx.strokeRect(inner.x, inner.y, inner.w, inner.h);

  const shiftX = spread * radialBias;
  const shiftY = spread * greenShift * 0.8;
  ctx.lineWidth = 2.4;
  ctx.strokeStyle = "rgba(255,77,116,0.78)";
  ctx.strokeRect(inner.x + shiftX, inner.y, inner.w, inner.h);
  ctx.strokeStyle = "rgba(111,255,154,0.68)";
  ctx.strokeRect(inner.x, inner.y + shiftY, inner.w, inner.h);
  ctx.strokeStyle = "rgba(66,183,255,0.78)";
  ctx.strokeRect(inner.x - shiftX, inner.y, inner.w, inner.h);

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  const gateWidth = frame.w * clamp(edgeThreshold, 0.02, 0.4);
  ctx.fillRect(frame.x, frame.y, gateWidth, frame.h);
  ctx.fillRect(frame.x + frame.w - gateWidth, frame.y, gateWidth, frame.h);
}

function createTintDecoration(node) {
  const row = document.createElement("div");
  row.className = "mkr-vfx-finish-chip-row";
  const labels = ["Red", "Green", "Blue", "Avg"];
  const chips = labels.map((label) => {
    const chip = document.createElement("div");
    chip.className = "mkr-vfx-finish-chip";
    chip.innerHTML = `${label}<span>0.00</span>`;
    row.appendChild(chip);
    return chip;
  });
  return {
    element: row,
    refresh() {
      const r = clamp(getNumber(node, "tint_r", 0.92), 0, 1);
      const g = clamp(getNumber(node, "tint_g", 0.86), 0, 1);
      const b = clamp(getNumber(node, "tint_b", 1.0), 0, 1);
      const avg = average([r, g, b]);
      const values = [r, g, b, avg];
      chips.forEach((chip, index) => {
        chip.style.borderColor = `rgba(${Math.round((index === 0 ? r : index === 1 ? g : index === 2 ? b : avg) * 255)},255,255,0.08)`;
        chip.querySelector("span").textContent = values[index].toFixed(2);
      });
    },
  };
}

const NODE_CONFIGS = {
  x1AnamorphicStreaks: {
    panelName: "mkr_vfx_anamorphic_streaks_studio",
    size: [790, 960],
    accent: "#ffb573",
    title: "Anamorphic Streaks Studio",
    subtitle: "Shape highlight streak extraction with softer tails, core boost, tint balance, and delivery blend in one panel.",
    defaults: {
      orientation: "horizontal",
      threshold: 0.74,
      softness: 0.10,
      length_px: 48.0,
      strength: 0.75,
      core_boost: 1.0,
      tail_softness: 1.0,
      tint_r: 0.92,
      tint_g: 0.86,
      tint_b: 1.0,
      mix: 1.0,
      mask_feather: 10.0,
      invert_mask: false,
    },
    numericSpecs: {
      threshold: { min: 0.0, max: 1.0 },
      softness: { min: 0.0, max: 0.5 },
      length_px: { min: 1.0, max: 512.0 },
      strength: { min: 0.0, max: 3.0 },
      core_boost: { min: 0.0, max: 3.0 },
      tail_softness: { min: 0.2, max: 2.0 },
      tint_r: { min: 0.0, max: 1.0 },
      tint_g: { min: 0.0, max: 1.0 },
      tint_b: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["orientation", "threshold", "softness", "length_px", "strength", "core_boost", "tail_softness", "tint_r", "tint_g", "tint_b", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Length", get: (node) => `${Math.round(getNumber(node, "length_px", 48))}px` },
      { label: "Boost", get: (node) => formatNumber(getNumber(node, "core_boost", 1.0)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Blue Sweep", tone: "accent", values: { orientation: "horizontal", length_px: 92, strength: 1.05, core_boost: 1.22, tint_r: 0.76, tint_g: 0.84, tint_b: 1.0 } },
      { label: "Copper Flare", values: { orientation: "horizontal", threshold: 0.68, softness: 0.16, length_px: 84, strength: 0.88, tint_r: 1.0, tint_g: 0.78, tint_b: 0.52 } },
      { label: "Tower Beam", values: { orientation: "vertical", threshold: 0.72, length_px: 128, strength: 1.1, core_boost: 1.35, tail_softness: 1.4 } },
    ],
    graph: {
      title: "Streak Preview",
      note: "highlight extraction",
      height: 220,
      draw: drawAnamorphicPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "threshold", 0.74)) },
        { label: "Soft", get: (node) => formatNumber(getNumber(node, "softness", 0.10), 3) },
        { label: "Tail", get: (node) => formatNumber(getNumber(node, "tail_softness", 1.0)) },
      ],
      help: "The preview shows extraction hotspots and streak tail behavior so the tint and tail controls read like optics, not just sliders.",
      decorate: createTintDecoration,
    },
    sections: [
      {
        title: "Highlight Gate",
        note: "pickup",
        controls: [
          { type: "select", key: "orientation", label: "Orientation", options: [{ label: "horizontal", value: "horizontal" }, { label: "vertical", value: "vertical" }] },
          { type: "slider", key: "threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "softness", label: "Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { type: "slider", key: "core_boost", label: "Core Boost", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Streak Shape",
        note: "tail",
        controls: [
          { type: "slider", key: "length_px", label: "Length", min: 1, max: 512, step: 1, decimals: 0 },
          { type: "slider", key: "strength", label: "Strength", min: 0, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "tail_softness", label: "Tail Softness", min: 0.2, max: 2, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Tint & Blend",
        note: "delivery",
        controls: [
          { type: "slider", key: "tint_r", label: "Tint R", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_g", label: "Tint G", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_b", label: "Tint B", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the streak pass is blended." },
        ],
      },
    ],
  },
  x1HeatHaze: {
    panelName: "mkr_vfx_heat_haze_studio",
    size: [790, 930],
    accent: "#6ce7ff",
    title: "Heat Haze Studio",
    subtitle: "Drive atmospheric shimmer with turbulence, edge falloff, chroma splitting, and direction-aware distortion.",
    defaults: {
      direction: "up",
      strength_px: 8.0,
      scale: 3.2,
      phase_deg: 0.0,
      turbulence: 0.55,
      edge_falloff: 0.35,
      chroma_split_px: 0.8,
      mix: 1.0,
      mask_feather: 6.0,
      invert_mask: false,
    },
    numericSpecs: {
      strength_px: { min: 0.0, max: 128.0 },
      scale: { min: 0.25, max: 16.0 },
      phase_deg: { min: 0.0, max: 360.0 },
      turbulence: { min: 0.0, max: 1.0 },
      edge_falloff: { min: 0.0, max: 1.0 },
      chroma_split_px: { min: 0.0, max: 12.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["direction", "strength_px", "scale", "phase_deg", "turbulence", "edge_falloff", "chroma_split_px", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => `${formatNumber(getNumber(node, "strength_px", 8), 1)}px` },
      { label: "Turb", get: (node) => formatNumber(getNumber(node, "turbulence", 0.55)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Mirage", tone: "accent", values: { direction: "up", strength_px: 12, scale: 4.4, turbulence: 0.72, edge_falloff: 0.46, chroma_split_px: 1.1 } },
      { label: "Jetwash", values: { direction: "right", strength_px: 10, scale: 6.2, phase_deg: 42, turbulence: 0.62, edge_falloff: 0.28, chroma_split_px: 0.65 } },
      { label: "Street Heat", values: { direction: "up", strength_px: 7.5, scale: 2.8, phase_deg: 18, turbulence: 0.38, edge_falloff: 0.62, chroma_split_px: 0.4 } },
    ],
    graph: {
      title: "Distortion Preview",
      note: "flow field",
      height: 220,
      draw: drawHeatHazePreview,
      readouts: [
        { label: "Dir", get: (node) => String(getValue(node, "direction", "up")).slice(0, 2).toUpperCase() },
        { label: "Phase", get: (node) => formatSigned(getNumber(node, "phase_deg", 0), 1) },
        { label: "Split", get: (node) => formatNumber(getNumber(node, "chroma_split_px", 0.8), 1) },
      ],
      help: "The preview sketches the shimmer field and edge rolloff so direction, turbulence, and chroma splitting stay readable together.",
    },
    sections: [
      {
        title: "Distortion Core",
        note: "primary",
        controls: [
          { type: "select", key: "direction", label: "Direction", options: [{ label: "up", value: "up" }, { label: "down", value: "down" }, { label: "left", value: "left" }, { label: "right", value: "right" }] },
          { type: "slider", key: "strength_px", label: "Strength", min: 0, max: 128, step: 0.25, decimals: 2 },
          { type: "slider", key: "scale", label: "Scale", min: 0.25, max: 16, step: 0.05, decimals: 2 },
          { type: "slider", key: "phase_deg", label: "Phase", min: 0, max: 360, step: 1, decimals: 0 },
        ],
      },
      {
        title: "Flow Shape",
        note: "field",
        controls: [
          { type: "slider", key: "turbulence", label: "Turbulence", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "edge_falloff", label: "Edge Falloff", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "chroma_split_px", label: "Chroma Split", min: 0, max: 12, step: 0.05, decimals: 2 },
        ],
      },
      {
        title: "Blend",
        note: "delivery",
        controls: [
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the haze distortion is blended." },
        ],
      },
    ],
  },
  x1LightWrapComposite: {
    panelName: "mkr_vfx_light_wrap_composite_studio",
    size: [790, 900],
    accent: "#ffd672",
    title: "Light Wrap Composite Studio",
    subtitle: "Dial in matte-driven wrap with edge shaping, background preblur, halo gamma, and cleaner integration control.",
    defaults: {
      wrap_radius: 18.0,
      wrap_strength: 0.65,
      edge_bias: 0.55,
      inside_holdout: 0.75,
      background_blur: 0.0,
      wrap_gamma: 1.0,
      mix: 1.0,
    },
    numericSpecs: {
      wrap_radius: { min: 0.0, max: 256.0 },
      wrap_strength: { min: 0.0, max: 3.0 },
      edge_bias: { min: 0.0, max: 1.0 },
      inside_holdout: { min: 0.0, max: 1.0 },
      background_blur: { min: 0.0, max: 64.0 },
      wrap_gamma: { min: 0.3, max: 3.0 },
      mix: { min: 0.0, max: 1.0 },
    },
    booleanKeys: [],
    legacyNames: ["wrap_radius", "wrap_strength", "edge_bias", "inside_holdout", "background_blur", "wrap_gamma", "mix"],
    metrics: [
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "wrap_radius", 18), 0)}px` },
      { label: "Gamma", get: (node) => formatNumber(getNumber(node, "wrap_gamma", 1.0)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Soft Plate", tone: "accent", values: { wrap_radius: 28, wrap_strength: 0.56, edge_bias: 0.46, inside_holdout: 0.82, background_blur: 4.0, wrap_gamma: 1.08 } },
      { label: "Hot Rim", values: { wrap_radius: 22, wrap_strength: 1.12, edge_bias: 0.68, inside_holdout: 0.54, background_blur: 2.0, wrap_gamma: 0.82 } },
      { label: "Diffused Fill", values: { wrap_radius: 44, wrap_strength: 0.74, edge_bias: 0.34, inside_holdout: 0.88, background_blur: 8.0, wrap_gamma: 1.28 } },
    ],
    graph: {
      title: "Wrap Preview",
      note: "matte halo",
      height: 220,
      draw: drawLightWrapPreview,
      readouts: [
        { label: "Bias", get: (node) => formatNumber(getNumber(node, "edge_bias", 0.55)) },
        { label: "Hold", get: (node) => formatNumber(getNumber(node, "inside_holdout", 0.75)) },
        { label: "Blur", get: (node) => formatNumber(getNumber(node, "background_blur", 0), 1) },
      ],
      help: "The preview shows the wrap halo around a matte silhouette so radius, holdout, and gamma changes stay legible together.",
    },
    sections: [
      {
        title: "Wrap Core",
        note: "primary",
        controls: [
          { type: "slider", key: "wrap_radius", label: "Wrap Radius", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "slider", key: "wrap_strength", label: "Wrap Strength", min: 0, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "edge_bias", label: "Edge Bias", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "inside_holdout", label: "Inside Holdout", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Halo Shaping",
        note: "integration",
        controls: [
          { type: "slider", key: "background_blur", label: "Background Blur", min: 0, max: 64, step: 0.5, decimals: 1 },
          { type: "slider", key: "wrap_gamma", label: "Wrap Gamma", min: 0.3, max: 3, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
    ],
  },
  x1EdgeAberration: {
    panelName: "mkr_vfx_edge_aberration_studio",
    size: [790, 930],
    accent: "#c18cff",
    title: "Edge Aberration Studio",
    subtitle: "Build a cleaner edge-fringe look with green shift, falloff shaping, threshold control, and lens-weighted bias.",
    defaults: {
      strength_px: 2.4,
      edge_threshold: 0.10,
      edge_softness: 0.18,
      radial_bias: 0.65,
      green_shift: 0.0,
      falloff: 0.65,
      mix: 1.0,
      mask_feather: 4.0,
      invert_mask: false,
    },
    numericSpecs: {
      strength_px: { min: 0.0, max: 24.0 },
      edge_threshold: { min: 0.0, max: 1.0 },
      edge_softness: { min: 0.0, max: 1.0 },
      radial_bias: { min: 0.0, max: 1.0 },
      green_shift: { min: -1.0, max: 1.0 },
      falloff: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["strength_px", "edge_threshold", "edge_softness", "radial_bias", "green_shift", "falloff", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Strength", get: (node) => `${formatNumber(getNumber(node, "strength_px", 2.4), 1)}px` },
      { label: "Green", get: (node) => formatSigned(getNumber(node, "green_shift", 0.0), 2) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Lens Edge", tone: "accent", values: { strength_px: 2.8, edge_threshold: 0.08, edge_softness: 0.22, radial_bias: 0.76, green_shift: 0.12, falloff: 0.72 } },
      { label: "Retro Fringe", values: { strength_px: 5.2, edge_threshold: 0.06, edge_softness: 0.28, radial_bias: 0.52, green_shift: -0.28, falloff: 0.46 } },
      { label: "Subtle Scan", values: { strength_px: 1.4, edge_threshold: 0.12, edge_softness: 0.16, radial_bias: 0.82, green_shift: 0.04, falloff: 0.82 } },
    ],
    graph: {
      title: "Fringe Preview",
      note: "edge separation",
      height: 220,
      draw: drawAberrationPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "edge_threshold", 0.10), 2) },
        { label: "Soft", get: (node) => formatNumber(getNumber(node, "edge_softness", 0.18), 2) },
        { label: "Fall", get: (node) => formatNumber(getNumber(node, "falloff", 0.65), 2) },
      ],
      help: "The preview shows how the RGB channels separate around the edge gate so strength and falloff read like lens behavior instead of arbitrary offsets.",
    },
    sections: [
      {
        title: "Edge Gate",
        note: "pickup",
        controls: [
          { type: "slider", key: "strength_px", label: "Strength", min: 0, max: 24, step: 0.05, decimals: 2 },
          { type: "slider", key: "edge_threshold", label: "Edge Threshold", min: 0, max: 1, step: 0.005, decimals: 3 },
          { type: "slider", key: "edge_softness", label: "Edge Softness", min: 0, max: 1, step: 0.005, decimals: 3 },
          { type: "slider", key: "falloff", label: "Falloff", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Lens Bias",
        note: "fringe",
        controls: [
          { type: "slider", key: "radial_bias", label: "Radial Bias", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "green_shift", label: "Green Shift", min: -1, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the edge fringe is blended." },
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

  if (node.__mkrVfxFinishPanelInstalled) {
    node.__mkrVfxFinishRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrVfxFinishPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrVfxFinishRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrVfxFinishRefreshHooksInstalled", refresh);
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
