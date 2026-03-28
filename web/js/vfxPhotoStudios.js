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
  matchesNode,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.VFXPhotoStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-vfx-photo-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function smoothstep(edge0, edge1, x) {
  if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - (2 * t));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function average(values) {
  if (!Array.isArray(values) || !values.length) return 0;
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length;
}

function drawGraphFrame(ctx, width, height) {
  const graph = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(graph.x, graph.y, graph.x, graph.y + graph.h);
  bg.addColorStop(0, "rgba(19,22,26,0.98)");
  bg.addColorStop(1, "rgba(33,36,41,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const x = graph.x + ((graph.w * index) / 4);
    const y = graph.y + ((graph.h * index) / 4);
    ctx.beginPath();
    ctx.moveTo(x, graph.y);
    ctx.lineTo(x, graph.y + graph.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(graph.x, y);
    ctx.lineTo(graph.x + graph.w, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);
  return graph;
}

function plotCurve(ctx, graph, color, fn, steps = 120, lineWidth = 2) {
  ctx.beginPath();
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    const x = graph.x + (graph.w * t);
    const y = graph.y + ((1 - clamp(fn(t), 0, 1)) * graph.h);
    if (step === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-vfx-select,
    .mkr-vfx-number {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
    }

    .mkr-vfx-select {
      margin-top: 4px;
    }

    .mkr-vfx-seed-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      margin-top: 4px;
    }

    .mkr-vfx-inline-note {
      margin-top: 6px;
      font-size: 10px;
      color: rgba(236,241,246,0.54);
      line-height: 1.35;
    }

    .mkr-vfx-tint-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      margin-top: 6px;
    }

    .mkr-vfx-tint-chip {
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      padding: 6px 8px;
      font-size: 10px;
      color: rgba(242,246,250,0.86);
      text-align: center;
      font-weight: 700;
    }

    .mkr-vfx-tint-chip span {
      display: block;
      margin-top: 3px;
      font-size: 9px;
      color: rgba(223,230,236,0.55);
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
  select.className = "mkr-vfx-select";
  for (const option of options) {
    const node = document.createElement("option");
    node.value = String(option.value);
    node.textContent = option.label;
    select.appendChild(node);
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
  wrap.className = "mkr-vfx-seed-row";

  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-vfx-number";
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

function drawHighlightRecoveryGraph(ctx, width, height, node) {
  const graph = drawGraphFrame(ctx, width, height);
  const threshold = getNumber(node, "threshold", 0.72);
  const softness = getNumber(node, "softness", 0.10);
  const recovery = getNumber(node, "recovery", 0.72);

  const left = clamp(threshold - softness, 0, 1);
  const right = clamp(threshold + softness, 0, 1);
  ctx.fillStyle = "rgba(255, 207, 120, 0.10)";
  ctx.fillRect(graph.x + (graph.w * left), graph.y, graph.w * Math.max(0.02, right - left), graph.h);

  plotCurve(ctx, graph, "rgba(230,236,242,0.78)", (x) => x, 96, 1.6);
  plotCurve(ctx, graph, "rgba(255,181,88,0.94)", (x) => {
    const over = Math.max(x - threshold, 0);
    const comp = over / (1 + ((recovery * 10 * over) / Math.max(1e-6, 1 - threshold)));
    return x - over + comp;
  });

  ctx.fillStyle = "rgba(248, 244, 238, 0.88)";
  ctx.font = "600 12px sans-serif";
  ctx.fillText("Original", graph.x + 12, graph.y + 18);
  ctx.fillStyle = "rgba(255,181,88,0.92)";
  ctx.fillText("Recovered", graph.x + 12, graph.y + 34);
}

function drawLocalContrastGraph(ctx, width, height, node) {
  const graph = drawGraphFrame(ctx, width, height);
  const shW = getNumber(node, "shadow_weight", 0.70);
  const midW = getNumber(node, "midtone_boost", 0.70);
  const hiW = getNumber(node, "highlight_weight", 0.55);
  const amount = getNumber(node, "amount", 0.55);

  plotCurve(ctx, graph, "rgba(103, 179, 255, 0.86)", (x) => (1 - smoothstep(0.20, 0.55, x)) * (shW / 2));
  plotCurve(ctx, graph, "rgba(255, 167, 83, 0.90)", (x) => {
    const sh = 1 - smoothstep(0.20, 0.55, x);
    const hi = smoothstep(0.45, 0.82, x);
    return (1 - clamp(sh + hi, 0, 1)) * (midW / 2);
  });
  plotCurve(ctx, graph, "rgba(255, 105, 126, 0.84)", (x) => smoothstep(0.45, 0.82, x) * (hiW / 2));
  plotCurve(ctx, graph, "rgba(248, 244, 238, 0.94)", (x) => {
    const sh = (1 - smoothstep(0.20, 0.55, x)) * shW;
    const hi = smoothstep(0.45, 0.82, x) * hiW;
    const mid = (1 - clamp((1 - smoothstep(0.20, 0.55, x)) + smoothstep(0.45, 0.82, x), 0, 1)) * midW;
    return clamp((sh + hi + mid) * 0.34 * (0.5 + amount), 0, 1);
  }, 120, 2.2);
}

function drawSharpenGraph(ctx, width, height, node) {
  const graph = drawGraphFrame(ctx, width, height);
  const threshold = getNumber(node, "threshold", 0.015);
  const amount = getNumber(node, "amount", 1.05);
  const halo = getNumber(node, "halo_suppress", 0.40);
  const mode = String(getValue(node, "mode", "unsharp") || "unsharp");

  const gateEdge = threshold + Math.max(0.004, (threshold * 1.8) + 0.004);
  ctx.fillStyle = "rgba(120, 186, 255, 0.08)";
  ctx.fillRect(graph.x + (graph.w * clamp(threshold / 0.2, 0, 1)), graph.y, graph.w * clamp((gateEdge - threshold) / 0.2, 0.02, 1), graph.h);

  plotCurve(ctx, graph, "rgba(121, 188, 255, 0.96)", (x) => smoothstep(threshold, gateEdge, x * 0.2));
  plotCurve(ctx, graph, "rgba(255, 165, 82, 0.88)", (x) => clamp((smoothstep(threshold, gateEdge, x * 0.2) * amount) * (1 - (halo * 0.35)), 0, 1));

  ctx.fillStyle = "rgba(239,243,247,0.86)";
  ctx.font = "600 12px sans-serif";
  ctx.fillText(mode === "highpass" ? "High Pass" : "Unsharp", graph.x + 12, graph.y + 18);
}

function drawSpotPreview(ctx, width, height, options) {
  const graph = drawGraphFrame(ctx, width, height);
  const centerX = graph.x + (graph.w * 0.50);
  const centerY = graph.y + (graph.h * 0.50);

  const bg = ctx.createRadialGradient(centerX, centerY, 8, centerX, centerY, graph.w * 0.48);
  bg.addColorStop(0, "rgba(255,255,255,0.10)");
  bg.addColorStop(1, "rgba(0,0,0,0.0)");
  ctx.fillStyle = bg;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  const core = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, graph.w * 0.08);
  core.addColorStop(0, options.coreColor || "rgba(255,244,232,0.95)");
  core.addColorStop(1, "rgba(255,255,255,0.0)");
  ctx.fillStyle = core;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  const halo = ctx.createRadialGradient(centerX, centerY, graph.w * 0.04, centerX, centerY, graph.w * options.radiusScale);
  halo.addColorStop(0, options.haloInner || "rgba(255,120,84,0.28)");
  halo.addColorStop(0.5, options.haloMid || "rgba(255,120,84,0.12)");
  halo.addColorStop(1, "rgba(255,120,84,0.0)");
  ctx.fillStyle = halo;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);
}

function drawHalationPreview(ctx, width, height, node) {
  const radius = getNumber(node, "radius", 14);
  const strength = getNumber(node, "strength", 0.45);
  const tintR = getNumber(node, "tint_r", 1.0);
  const tintG = getNumber(node, "tint_g", 0.34);
  const tintB = getNumber(node, "tint_b", 0.08);
  drawSpotPreview(ctx, width, height, {
    radiusScale: clamp(0.18 + (radius / 160), 0.16, 0.46),
    coreColor: "rgba(255,250,244,0.95)",
    haloInner: `rgba(${Math.round(tintR * 255)}, ${Math.round(tintG * 255)}, ${Math.round(tintB * 255)}, ${clamp(0.22 + (strength * 0.20), 0.10, 0.54)})`,
    haloMid: `rgba(${Math.round(tintR * 255)}, ${Math.round(tintG * 255)}, ${Math.round(tintB * 255)}, ${clamp(0.10 + (strength * 0.10), 0.04, 0.22)})`,
  });
}

function drawDiffusionPreview(ctx, width, height, node) {
  const radius = getNumber(node, "radius", 12);
  const glow = getNumber(node, "highlight_strength", 0.48);
  const diffusion = getNumber(node, "diffusion_strength", 0.45);
  const graph = drawGraphFrame(ctx, width, height);
  const x = graph.x + (graph.w * 0.50);
  const y = graph.y + (graph.h * 0.42);

  const bloom = ctx.createRadialGradient(x, y, 0, x, y, graph.w * clamp(0.12 + (radius / 180), 0.12, 0.44));
  bloom.addColorStop(0, `rgba(255,245,232,${clamp(0.35 + (glow * 0.18), 0.18, 0.56)})`);
  bloom.addColorStop(1, "rgba(255,245,232,0)");
  ctx.fillStyle = bloom;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  const veil = ctx.createLinearGradient(graph.x, graph.y, graph.x, graph.y + graph.h);
  veil.addColorStop(0, `rgba(245, 225, 208, ${clamp(0.06 + (diffusion * 0.22), 0.04, 0.24)})`);
  veil.addColorStop(1, "rgba(245, 225, 208, 0)");
  ctx.fillStyle = veil;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

  ctx.fillStyle = "rgba(255,255,255,0.94)";
  ctx.beginPath();
  ctx.arc(x, y, 10, 0, Math.PI * 2);
  ctx.fill();
}

function seededNoise(seed) {
  let state = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0xFFFFFFFF;
  };
}

function drawLensDirtPreview(ctx, width, height, node) {
  const graph = drawGraphFrame(ctx, width, height);
  const seed = Math.round(getNumber(node, "seed", 23));
  const dirtAmount = getNumber(node, "dirt_amount", 0.65);
  const dirtContrast = getNumber(node, "dirt_contrast", 1.35);
  const bloomStrength = getNumber(node, "bloom_strength", 0.75);
  const tintR = getNumber(node, "tint_r", 1.0);
  const tintG = getNumber(node, "tint_g", 0.96);
  const tintB = getNumber(node, "tint_b", 0.88);
  const rnd = seededNoise(seed);

  ctx.save();
  ctx.beginPath();
  ctx.rect(graph.x, graph.y, graph.w, graph.h);
  ctx.clip();

  for (let i = 0; i < 220; i += 1) {
    const size = lerp(1.5, 10, Math.pow(rnd(), 2.2));
    const x = graph.x + (rnd() * graph.w);
    const y = graph.y + (rnd() * graph.h);
    const alpha = clamp((0.04 + (rnd() * 0.12)) * dirtAmount * dirtContrast * 0.5, 0.02, 0.24);
    ctx.fillStyle = `rgba(255,255,255,${alpha})`;
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fill();
  }

  const glow = ctx.createRadialGradient(
    graph.x + graph.w * 0.5,
    graph.y + graph.h * 0.42,
    0,
    graph.x + graph.w * 0.5,
    graph.y + graph.h * 0.42,
    graph.w * 0.36
  );
  glow.addColorStop(0, `rgba(${Math.round(tintR * 255)}, ${Math.round(tintG * 255)}, ${Math.round(tintB * 255)}, ${clamp(0.22 + (bloomStrength * 0.16), 0.10, 0.46)})`);
  glow.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(graph.x, graph.y, graph.w, graph.h);
  ctx.restore();
}

const NODE_CONFIGS = {
  x1HighlightRecovery: {
    panelName: "mkr_vfx_highlight_recovery_studio",
    size: [780, 760],
    accent: "#d7a860",
    title: "Highlight Recovery Studio",
    subtitle: "Recover clipped highlights with chroma-aware rebuild, softer rolloff, and better finishing control.",
    defaults: {
      threshold: 0.72,
      softness: 0.10,
      recovery: 0.72,
      chroma_preserve: 0.60,
      desaturate_clips: 0.18,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      threshold: { min: 0.0, max: 1.0 },
      softness: { min: 0.0, max: 0.5 },
      recovery: { min: 0.0, max: 1.0 },
      chroma_preserve: { min: 0.0, max: 1.0 },
      desaturate_clips: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["threshold", "softness", "recovery", "chroma_preserve", "desaturate_clips", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Threshold", get: (node) => formatNumber(getNumber(node, "threshold", 0.72)) },
      { label: "Recovery", get: (node) => formatNumber(getNumber(node, "recovery", 0.72)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Clean", values: { threshold: 0.78, softness: 0.08, recovery: 0.58, chroma_preserve: 0.72, desaturate_clips: 0.10 } },
      { label: "Rescue", tone: "accent", values: { threshold: 0.68, softness: 0.14, recovery: 0.86, chroma_preserve: 0.78, desaturate_clips: 0.28 } },
      { label: "Soft Roll", values: { threshold: 0.74, softness: 0.18, recovery: 0.65, chroma_preserve: 0.55, desaturate_clips: 0.16 } },
    ],
    graph: {
      title: "Recovery Response",
      note: "clip rolloff",
      height: 228,
      draw: drawHighlightRecoveryGraph,
      readouts: [
        { label: "Threshold", get: (node) => formatNumber(getNumber(node, "threshold", 0.72)) },
        { label: "Soft", get: (node) => formatNumber(getNumber(node, "softness", 0.10), 3) },
        { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
      ],
      help: "The amber curve shows the rebuilt highlight rolloff after the threshold and recovery settings kick in.",
    },
    sections: [
      {
        title: "Recovery Core",
        note: "primary",
        controls: [
          { type: "slider", key: "threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "softness", label: "Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { type: "slider", key: "recovery", label: "Recovery", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "chroma_preserve", label: "Chroma", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Clip Finish",
        note: "blend",
        controls: [
          { type: "slider", key: "desaturate_clips", label: "Desaturate", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before highlight recovery is applied." },
        ],
      },
    ],
  },
  x1LocalContrast: {
    panelName: "mkr_vfx_local_contrast_studio",
    size: [780, 790],
    accent: "#d67c45",
    title: "Local Contrast Studio",
    subtitle: "Shape micro-contrast by tone zone instead of balancing a raw list of weights and toggles.",
    defaults: {
      radius: 28.0,
      amount: 0.55,
      shadow_weight: 0.70,
      highlight_weight: 0.55,
      midtone_boost: 0.70,
      preserve_luma: true,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      radius: { min: 1.0, max: 256.0 },
      amount: { min: -1.0, max: 2.0 },
      shadow_weight: { min: 0.0, max: 2.0 },
      highlight_weight: { min: 0.0, max: 2.0 },
      midtone_boost: { min: 0.0, max: 2.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["preserve_luma", "invert_mask"],
    legacyNames: ["radius", "amount", "shadow_weight", "highlight_weight", "midtone_boost", "preserve_luma", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "radius", 28), 1)}px` },
      { label: "Amount", get: (node) => formatNumber(getNumber(node, "amount", 0.55)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Editorial", values: { radius: 32, amount: 0.62, shadow_weight: 0.70, midtone_boost: 0.78, highlight_weight: 0.48, preserve_luma: true } },
      { label: "Micro", tone: "accent", values: { radius: 14, amount: 0.88, shadow_weight: 0.52, midtone_boost: 1.12, highlight_weight: 0.56, preserve_luma: true } },
      { label: "Matte", values: { radius: 42, amount: 0.34, shadow_weight: 0.92, midtone_boost: 0.52, highlight_weight: 0.28, preserve_luma: true } },
    ],
    graph: {
      title: "Tone Weighting",
      note: "response map",
      height: 230,
      draw: drawLocalContrastGraph,
      readouts: [
        { label: "Shadows", get: (node) => formatNumber(getNumber(node, "shadow_weight", 0.70)) },
        { label: "Mids", get: (node) => formatNumber(getNumber(node, "midtone_boost", 0.70)) },
        { label: "Highlights", get: (node) => formatNumber(getNumber(node, "highlight_weight", 0.55)) },
      ],
      help: "Blue, orange, and pink curves show how contrast weighting is distributed through the tonal range.",
    },
    sections: [
      {
        title: "Contrast Core",
        note: "primary",
        controls: [
          { type: "slider", key: "radius", label: "Radius", min: 1, max: 256, step: 0.5, decimals: 1 },
          { type: "slider", key: "amount", label: "Amount", min: -1, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "shadow_weight", label: "Shadows", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "slider", key: "midtone_boost", label: "Midtones", min: 0, max: 2, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Finish",
        note: "tonal balance",
        controls: [
          { type: "slider", key: "highlight_weight", label: "Highlights", min: 0, max: 2, step: 0.01, decimals: 2 },
          { type: "toggle", key: "preserve_luma", label: "Preserve Luma", description: "Keep the source luminance structure while micro-contrast is increased." },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before local contrast is blended." },
        ],
      },
    ],
  },
  x1SharpenPro: {
    panelName: "mkr_vfx_sharpen_pro_studio",
    size: [780, 810],
    accent: "#78b9ff",
    title: "Sharpen Pro Studio",
    subtitle: "Tune edge gating, halo control, and sharpen character from a single finishing panel.",
    defaults: {
      mode: "unsharp",
      radius: 1.6,
      amount: 1.05,
      threshold: 0.015,
      halo_suppress: 0.40,
      luma_only: true,
      mix: 1.0,
      mask_feather: 8.0,
      invert_mask: false,
    },
    numericSpecs: {
      radius: { min: 0.1, max: 32.0 },
      amount: { min: 0.0, max: 4.0 },
      threshold: { min: 0.0, max: 0.2 },
      halo_suppress: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["luma_only", "invert_mask"],
    legacyNames: ["mode", "radius", "amount", "threshold", "halo_suppress", "luma_only", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Mode", get: (node) => String(getValue(node, "mode", "unsharp")).toUpperCase() },
      { label: "Amount", get: (node) => formatNumber(getNumber(node, "amount", 1.05)) },
      { label: "Threshold", get: (node) => formatNumber(getNumber(node, "threshold", 0.015), 3) },
    ],
    presets: [
      { label: "Crisp", values: { mode: "unsharp", radius: 1.4, amount: 1.18, threshold: 0.012, halo_suppress: 0.42, luma_only: true } },
      { label: "Hi Pass", tone: "accent", values: { mode: "highpass", radius: 2.2, amount: 0.92, threshold: 0.020, halo_suppress: 0.54, luma_only: true } },
      { label: "Portrait", values: { mode: "unsharp", radius: 2.8, amount: 0.72, threshold: 0.025, halo_suppress: 0.66, luma_only: true } },
    ],
    graph: {
      title: "Edge Gate",
      note: "detail response",
      height: 224,
      draw: drawSharpenGraph,
      readouts: [
        { label: "Mode", get: (node) => String(getValue(node, "mode", "unsharp")).slice(0, 2).toUpperCase() },
        { label: "Halo", get: (node) => formatNumber(getNumber(node, "halo_suppress", 0.40)) },
        { label: "Luma", get: (node) => getBoolean(node, "luma_only", true) ? "On" : "Off" },
      ],
      help: "The blue gate curve shows where detail starts being sharpened. Halo suppression limits the strongest edge overshoot.",
    },
    sections: [
      {
        title: "Sharpen Core",
        note: "primary",
        controls: [
          { type: "select", key: "mode", label: "Mode", options: [{ label: "unsharp", value: "unsharp" }, { label: "highpass", value: "highpass" }] },
          { type: "slider", key: "radius", label: "Radius", min: 0.1, max: 32, step: 0.1, decimals: 1 },
          { type: "slider", key: "amount", label: "Amount", min: 0, max: 4, step: 0.01, decimals: 2 },
          { type: "slider", key: "threshold", label: "Threshold", min: 0, max: 0.2, step: 0.001, decimals: 3 },
        ],
      },
      {
        title: "Finish",
        note: "edge control",
        controls: [
          { type: "slider", key: "halo_suppress", label: "Halo Suppress", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "toggle", key: "luma_only", label: "Luma Only", description: "Confine sharpening to the luminance structure so color channels stay cleaner." },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before sharpening is blended." },
        ],
      },
    ],
  },
  x1Halation: {
    panelName: "mkr_vfx_halation_studio",
    size: [790, 860],
    accent: "#ff7856",
    title: "Halation Studio",
    subtitle: "Build film-style red halo response with threshold shaping, glow radius, and tint balance.",
    defaults: {
      threshold: 0.72,
      softness: 0.10,
      radius: 14.0,
      strength: 0.45,
      tint_r: 1.0,
      tint_g: 0.34,
      tint_b: 0.08,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      threshold: { min: 0.0, max: 1.0 },
      softness: { min: 0.0, max: 0.5 },
      radius: { min: 0.0, max: 128.0 },
      strength: { min: 0.0, max: 3.0 },
      tint_r: { min: 0.0, max: 1.0 },
      tint_g: { min: 0.0, max: 1.0 },
      tint_b: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["threshold", "softness", "radius", "strength", "tint_r", "tint_g", "tint_b", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "radius", 14), 1)}px` },
      { label: "Strength", get: (node) => formatNumber(getNumber(node, "strength", 0.45)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Kodak", tone: "accent", values: { threshold: 0.72, softness: 0.10, radius: 14, strength: 0.48, tint_r: 1.0, tint_g: 0.34, tint_b: 0.08 } },
      { label: "Soft", values: { threshold: 0.76, softness: 0.14, radius: 18, strength: 0.34, tint_r: 1.0, tint_g: 0.42, tint_b: 0.12 } },
      { label: "Hot Gate", values: { threshold: 0.62, softness: 0.08, radius: 22, strength: 0.78, tint_r: 1.0, tint_g: 0.28, tint_b: 0.05 } },
    ],
    graph: {
      title: "Halation Preview",
      note: "tinted glow",
      height: 230,
      draw: drawHalationPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "threshold", 0.72)) },
        { label: "Soft", get: (node) => formatNumber(getNumber(node, "softness", 0.10), 3) },
        { label: "Tint", get: (node) => `${formatNumber(getNumber(node, "tint_r", 1.0))}/${formatNumber(getNumber(node, "tint_g", 0.34))}/${formatNumber(getNumber(node, "tint_b", 0.08))}` },
      ],
      help: "The preview shows the character of the glow rather than the exact image result, so you can shape radius and tint quickly.",
    },
    sections: [
      {
        title: "Glow Core",
        note: "primary",
        controls: [
          { type: "slider", key: "threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "softness", label: "Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { type: "slider", key: "radius", label: "Radius", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "strength", label: "Strength", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Tint Balance",
        note: "rgb glow",
        controls: [
          { type: "slider", key: "tint_r", label: "Tint R", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_g", label: "Tint G", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_b", label: "Tint B", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask Finish",
        note: "delivery",
        controls: [
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before halation is blended." },
        ],
      },
    ],
  },
  x1Diffusion: {
    panelName: "mkr_vfx_diffusion_studio",
    size: [790, 880],
    accent: "#efb38d",
    title: "Diffusion Studio",
    subtitle: "Dial in highlight bloom, soft contrast, and lifted shadows from one soft-focus finishing panel.",
    defaults: {
      radius: 12.0,
      highlight_threshold: 0.68,
      highlight_softness: 0.10,
      highlight_strength: 0.48,
      diffusion_strength: 0.45,
      contrast_softness: 0.25,
      shadow_lift: 0.10,
      mix: 1.0,
      mask_feather: 12.0,
      invert_mask: false,
    },
    numericSpecs: {
      radius: { min: 0.0, max: 128.0 },
      highlight_threshold: { min: 0.0, max: 1.0 },
      highlight_softness: { min: 0.0, max: 0.5 },
      highlight_strength: { min: 0.0, max: 3.0 },
      diffusion_strength: { min: 0.0, max: 1.0 },
      contrast_softness: { min: 0.0, max: 1.0 },
      shadow_lift: { min: 0.0, max: 1.0 },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["radius", "highlight_threshold", "highlight_softness", "highlight_strength", "diffusion_strength", "contrast_softness", "shadow_lift", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "radius", 12), 1)}px` },
      { label: "Glow", get: (node) => formatNumber(getNumber(node, "highlight_strength", 0.48)) },
      { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
    ],
    presets: [
      { label: "Portrait", tone: "accent", values: { radius: 14, highlight_threshold: 0.72, highlight_softness: 0.12, highlight_strength: 0.36, diffusion_strength: 0.42, contrast_softness: 0.28, shadow_lift: 0.08 } },
      { label: "Dream", values: { radius: 22, highlight_threshold: 0.62, highlight_softness: 0.16, highlight_strength: 0.74, diffusion_strength: 0.62, contrast_softness: 0.42, shadow_lift: 0.14 } },
      { label: "Clean Bloom", values: { radius: 10, highlight_threshold: 0.70, highlight_softness: 0.08, highlight_strength: 0.52, diffusion_strength: 0.28, contrast_softness: 0.18, shadow_lift: 0.05 } },
    ],
    graph: {
      title: "Diffusion Preview",
      note: "soft glow",
      height: 230,
      draw: drawDiffusionPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "highlight_threshold", 0.68)) },
        { label: "Soft", get: (node) => formatNumber(getNumber(node, "highlight_softness", 0.10), 3) },
        { label: "Lift", get: (node) => formatNumber(getNumber(node, "shadow_lift", 0.10)) },
      ],
      help: "This preview biases toward glow character, contrast softening, and shadow lift so the node feels more like an optical tool than a spreadsheet.",
    },
    sections: [
      {
        title: "Glow Core",
        note: "primary",
        controls: [
          { type: "slider", key: "radius", label: "Radius", min: 0, max: 128, step: 0.5, decimals: 1 },
          { type: "slider", key: "highlight_threshold", label: "Hi Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "highlight_softness", label: "Hi Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { type: "slider", key: "highlight_strength", label: "Hi Strength", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Diffusion Body",
        note: "contrast response",
        controls: [
          { type: "slider", key: "diffusion_strength", label: "Diffusion", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "contrast_softness", label: "Contrast Soft", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "shadow_lift", label: "Shadow Lift", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Mask Finish",
        note: "delivery",
        controls: [
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before diffusion is blended." },
        ],
      },
    ],
  },
  x1LensDirtBloom: {
    panelName: "mkr_vfx_lens_dirt_bloom_studio",
    size: [810, 940],
    accent: "#dbc06a",
    title: "Lens Dirt Bloom Studio",
    subtitle: "Shape bloom threshold, dirt texture, and lens tint together so the optics feel authored instead of accidental.",
    defaults: {
      threshold: 0.72,
      softness: 0.10,
      bloom_radius: 18.0,
      bloom_strength: 0.75,
      dirt_amount: 0.65,
      dirt_scale: 72.0,
      dirt_contrast: 1.35,
      tint_r: 1.0,
      tint_g: 0.96,
      tint_b: 0.88,
      seed: 23,
      mix: 1.0,
      mask_feather: 10.0,
      invert_mask: false,
    },
    numericSpecs: {
      threshold: { min: 0.0, max: 1.0 },
      softness: { min: 0.0, max: 0.5 },
      bloom_radius: { min: 0.0, max: 256.0 },
      bloom_strength: { min: 0.0, max: 3.0 },
      dirt_amount: { min: 0.0, max: 1.0 },
      dirt_scale: { min: 8.0, max: 512.0 },
      dirt_contrast: { min: 0.2, max: 4.0 },
      tint_r: { min: 0.0, max: 1.0 },
      tint_g: { min: 0.0, max: 1.0 },
      tint_b: { min: 0.0, max: 1.0 },
      seed: { min: 0, max: 2147483647, integer: true },
      mix: { min: 0.0, max: 1.0 },
      mask_feather: { min: 0.0, max: 256.0 },
    },
    booleanKeys: ["invert_mask"],
    legacyNames: ["threshold", "softness", "bloom_radius", "bloom_strength", "dirt_amount", "dirt_scale", "dirt_contrast", "tint_r", "tint_g", "tint_b", "seed", "mix", "mask_feather", "invert_mask"],
    metrics: [
      { label: "Bloom", get: (node) => formatNumber(getNumber(node, "bloom_strength", 0.75)) },
      { label: "Dirt", get: (node) => formatNumber(getNumber(node, "dirt_amount", 0.65)) },
      { label: "Seed", get: (node) => String(Math.round(getNumber(node, "seed", 23))) },
    ],
    presets: [
      { label: "Clean", values: { threshold: 0.76, softness: 0.08, bloom_radius: 14, bloom_strength: 0.48, dirt_amount: 0.24, dirt_scale: 92, dirt_contrast: 1.10 } },
      { label: "Cinema", tone: "accent", values: { threshold: 0.72, softness: 0.10, bloom_radius: 18, bloom_strength: 0.78, dirt_amount: 0.68, dirt_scale: 72, dirt_contrast: 1.35 } },
      { label: "Dirty Lens", values: { threshold: 0.64, softness: 0.14, bloom_radius: 24, bloom_strength: 0.92, dirt_amount: 0.92, dirt_scale: 48, dirt_contrast: 1.86 } },
    ],
    graph: {
      title: "Optics Preview",
      note: "dirt + bloom",
      height: 240,
      draw: drawLensDirtPreview,
      readouts: [
        { label: "Thr", get: (node) => formatNumber(getNumber(node, "threshold", 0.72)) },
        { label: "Scale", get: (node) => `${formatNumber(getNumber(node, "dirt_scale", 72), 0)}px` },
        { label: "Mix", get: (node) => formatNumber(getNumber(node, "mix", 1.0)) },
      ],
      help: "The preview uses the current seed to sketch the dirt texture character, then layers the bloom tint over it.",
    },
    sections: [
      {
        title: "Bloom Core",
        note: "primary",
        controls: [
          { type: "slider", key: "threshold", label: "Threshold", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "softness", label: "Softness", min: 0, max: 0.5, step: 0.005, decimals: 3 },
          { type: "slider", key: "bloom_radius", label: "Bloom Radius", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "slider", key: "bloom_strength", label: "Bloom Strength", min: 0, max: 3, step: 0.01, decimals: 2 },
        ],
      },
      {
        title: "Dirt Texture",
        note: "texture field",
        controls: [
          { type: "slider", key: "dirt_amount", label: "Dirt Amount", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "dirt_scale", label: "Dirt Scale", min: 8, max: 512, step: 1, decimals: 0 },
          { type: "slider", key: "dirt_contrast", label: "Dirt Contrast", min: 0.2, max: 4, step: 0.01, decimals: 2 },
          { type: "seed", key: "seed", label: "Seed", min: 0, max: 2147483647 },
        ],
      },
      {
        title: "Tint And Finish",
        note: "lens tone",
        controls: [
          { type: "slider", key: "tint_r", label: "Tint R", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_g", label: "Tint G", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "tint_b", label: "Tint B", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mix", label: "Mix", min: 0, max: 1, step: 0.01, decimals: 2 },
          { type: "slider", key: "mask_feather", label: "Mask Feather", min: 0, max: 256, step: 0.5, decimals: 1 },
          { type: "toggle", key: "invert_mask", label: "Invert Mask", description: "Flip the external mask before the optics pass is blended." },
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
  if (readoutViews.length) {
    graphSection.body.appendChild(readoutWrap);
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
    section.section.style.paddingBottom = "8px";
    panel.appendChild(section.section);
  }

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => drawCanvas());
    observer.observe(canvas);
  }

  function drawCanvas() {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    ctx.clearRect(0, 0, width, height);
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

  if (node.__mkrVfxPhotoPanelInstalled) {
    node.__mkrVfxPhotoRefresh?.();
    normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
    return;
  }

  node.__mkrVfxPhotoPanelInstalled = true;
  const { panel, refresh } = buildPanel(node, config);
  node.__mkrVfxPhotoRefresh = refresh;
  attachPanel(node, config.panelName, panel, config.size[0], config.size[1]);
  normalizePanelNode(node, [SETTINGS_WIDGET_NAME, ...config.legacyNames], config.panelName);
  installRefreshHooks(node, "__mkrVfxPhotoRefreshHooksInstalled", refresh);
  requestAnimationFrame(() => refresh());
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TARGET_NAMES.has(String(nodeData?.name || nodeData?.type || ""))) return;
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
