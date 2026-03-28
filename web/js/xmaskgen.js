import { app } from "../../../scripts/app.js";
import { ensureMkrUIStyles } from "./uiSystem.js";

const EXT = "mkrshift.x1maskgen.preview";
const STATE_KEY = "__mkrX1MaskState";
const SETTINGS_WIDGET_NAME = "settings_json";
const CONTROLS_WIDGET_NAME = "mkr_x1maskgen_controls_ui";
const DOM_WIDGET_NAME = "mkr_x1maskgen_preview_ui";
const RUNTIME_VERSION = "node2-2026-03-01f";
const ACCENT_STYLE_ID = "mkrshift-accent-style";
const ACCENT_STYLE_CSS = `
:root {
  --mkr-accent-lime: #d2fd51;
  --mkr-dark-label: #1f1f1f;
  --mkr-dark-label-highlight: #2e2e2e;
  --mkr-accent-a: #d2fd51;
  --mkr-accent-b: #f39f4d;
  --mkr-accent-c: #d9573b;
}
`;

const DEFAULT_W = 360;
const DEFAULT_H = 400;
const PREVIEW_MIN_H = 178;
const MASK_PREVIEW_HEIGHT = 254;
const PREVIEW_MARGIN = 8;
const LIVE_DEBOUNCE_MS = 90;
const ACCENT_LIME = "#D2FD51";
const LOCAL_PREVIEW_MAX_DIM = 360;
const URL_REFRESH_BUCKET_MS = 900;
const CONTROLS_HEIGHT = 290;
const LAYOUT_TOP = 76;
const LAYOUT_GAP = 8;
const LAYOUT_BOTTOM = 4;
const LEGACY_MASK_WIDGET_ORDER = [
  "mode",
  "channel",
  "threshold",
  "softness",
  "min_value",
  "max_value",
  "hue_center",
  "hue_width",
  "target_r",
  "target_g",
  "target_b",
  "color_tolerance",
  "edge_radius",
  "edge_strength",
  "center_x",
  "center_y",
  "radius",
  "falloff",
  "combine_mode",
  "expand_pixels",
  "blur_radius",
  "mask_gamma",
  "invert_mask",
];
const HIDDEN_WIDGET_NAMES = [SETTINGS_WIDGET_NAME, ...LEGACY_MASK_WIDGET_ORDER];
const MASK_MODE_VALUES = ["luminance", "channel", "hue", "saturation", "value", "skin_tones", "chroma_key", "edge", "radial"];
const MASK_CHANNEL_VALUES = ["luma", "red", "green", "blue", "alpha"];
const MASK_COMBINE_VALUES = ["replace", "multiply", "maximum", "minimum", "add"];
const MASK_DEFAULT_SETTINGS = {
  mode: "luminance",
  channel: "luma",
  threshold: 0.5,
  softness: 0.08,
  min_value: 0.2,
  max_value: 0.8,
  hue_center: 120,
  hue_width: 24,
  target_r: 0,
  target_g: 1,
  target_b: 0,
  color_tolerance: 0.25,
  edge_radius: 1,
  edge_strength: 1,
  center_x: 0.5,
  center_y: 0.5,
  radius: 0.28,
  falloff: 1,
  combine_mode: "replace",
  expand_pixels: 0,
  blur_radius: 0,
  mask_gamma: 1,
  invert_mask: false,
};
const MASK_NUMERIC_SPECS = {
  threshold: { min: 0, max: 1, fallback: 0.5 },
  softness: { min: 0, max: 1, fallback: 0.08 },
  min_value: { min: 0, max: 1, fallback: 0.2 },
  max_value: { min: 0, max: 1, fallback: 0.8 },
  hue_center: { min: 0, max: 360, fallback: 120 },
  hue_width: { min: 0, max: 180, fallback: 24 },
  target_r: { min: 0, max: 1, fallback: 0 },
  target_g: { min: 0, max: 1, fallback: 1 },
  target_b: { min: 0, max: 1, fallback: 0 },
  color_tolerance: { min: 0, max: 1, fallback: 0.25 },
  edge_radius: { min: 0, max: 32, fallback: 1 },
  edge_strength: { min: 0, max: 4, fallback: 1 },
  center_x: { min: 0, max: 1, fallback: 0.5 },
  center_y: { min: 0, max: 1, fallback: 0.5 },
  radius: { min: 0, max: 2, fallback: 0.28 },
  falloff: { min: 0.05, max: 6, fallback: 1 },
  expand_pixels: { min: -64, max: 64, fallback: 0, integer: true },
  blur_radius: { min: 0, max: 64, fallback: 0 },
  mask_gamma: { min: 0.1, max: 4, fallback: 1 },
};
let registered = false;
const OBJECT_IDS = new WeakMap();
let objectIdCounter = 1;

function getApp() {
  return window.comfyAPI?.app?.app || window.app || app || null;
}

function getApi() {
  return window.comfyAPI?.api || window.api || null;
}

function apiUrl(path) {
  const p = String(path || "");
  const api = getApi();
  if (api && typeof api.apiURL === "function") {
    return api.apiURL(p);
  }
  return p;
}

function objectId(value) {
  if (!value || (typeof value !== "object" && typeof value !== "function")) return "null";
  const existing = OBJECT_IDS.get(value);
  if (existing) return existing;
  const next = `obj${objectIdCounter++}`;
  OBJECT_IDS.set(value, next);
  return next;
}

function drawableContentStamp(drawable) {
  try {
    if (!drawable) return "none";
    const dw = drawable.naturalWidth || drawable.videoWidth || drawable.width || 0;
    const dh = drawable.naturalHeight || drawable.videoHeight || drawable.height || 0;
    if (dw <= 0 || dh <= 0) return "empty";

    const size = 10;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return `${dw}x${dh}:ctx`;
    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(drawable, 0, 0, size, size);
    const data = ctx.getImageData(0, 0, size, size).data;

    let hash = 2166136261 >>> 0;
    for (let i = 0; i < data.length; i += 4) {
      hash ^= data[i];
      hash = Math.imul(hash, 16777619) >>> 0;
      hash ^= data[i + 1];
      hash = Math.imul(hash, 16777619) >>> 0;
      hash ^= data[i + 2];
      hash = Math.imul(hash, 16777619) >>> 0;
      hash ^= data[i + 3];
      hash = Math.imul(hash, 16777619) >>> 0;
    }
    return `${dw}x${dh}:${hash.toString(36)}`;
  } catch (error) {
    return "tainted";
  }
}

function stableScalar(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch (error) {
      return "[object]";
    }
  }
  return String(value);
}

function sourceNodeWidgetSignature(sourceNode) {
  const widgets = sourceNode?.widgets;
  if (!Array.isArray(widgets) || widgets.length === 0) return "none";
  const parts = [];
  for (const widget of widgets) {
    const name = String(widget?.name || "").trim();
    if (!name) continue;
    if (name === DOM_WIDGET_NAME) continue;
    parts.push(`${name}=${stableScalar(widget?.value)}`);
  }
  return parts.length ? parts.join("|") : "none";
}

function buildInputImageUrlFromSourceNode(sourceNode) {
  if (!sourceNode) return "";
  const typeToken = [
    sourceNode?.comfyClass,
    sourceNode?.type,
    sourceNode?.title,
    sourceNode?.constructor?.comfyClass,
    sourceNode?.constructor?.type,
    sourceNode?.constructor?.title,
  ].filter(Boolean).join(" ").toLowerCase().replace(/[^a-z0-9]+/g, "");

  const likelyImageLoader =
    typeToken.includes("loadimage") ||
    (typeToken.includes("load") && typeToken.includes("image"));
  if (!likelyImageLoader) return "";

  const widgets = Array.isArray(sourceNode.widgets) ? sourceNode.widgets : [];
  const imageWidget = widgets.find((w) => {
    const name = String(w?.name || "").toLowerCase();
    return name === "image" || name === "filename" || name === "file";
  });
  const rawValue = String(imageWidget?.value || "").trim();
  if (!rawValue) return "";
  if (rawValue.startsWith("http://") || rawValue.startsWith("https://") || rawValue.startsWith("data:")) {
    return rawValue;
  }

  const normalized = rawValue.replace(/\\/g, "/");
  let filename = normalized;
  let subfolder = "";
  const split = normalized.lastIndexOf("/");
  if (split >= 0) {
    filename = normalized.slice(split + 1);
    subfolder = normalized.slice(0, split);
  }
  if (!filename) return "";

  const subfolderQuery = subfolder ? `&subfolder=${encodeURIComponent(subfolder)}` : "";
  return apiUrl(`/view?filename=${encodeURIComponent(filename)}${subfolderQuery}&type=input`);
}

function ensureAccentStylesheet() {
  ensureMkrUIStyles();
  if (document.getElementById(ACCENT_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = ACCENT_STYLE_ID;
  style.textContent = ACCENT_STYLE_CSS;
  document.head.appendChild(style);
}

function matchesMaskNodeName(name) {
  const token = String(name ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!token) return false;
  return token.includes("x1maskgen") || (token.includes("maskgen") && token.includes("mkrshift"));
}

function isMaskNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
    node?.constructor?.title,
  ].filter(Boolean);
  return candidates.some(matchesMaskNodeName);
}

function isMaskNodeDef(nodeData) {
  const candidates = [
    nodeData?.name,
    nodeData?.display_name,
    nodeData?.type,
    nodeData?.category,
  ].filter(Boolean);
  return candidates.some(matchesMaskNodeName);
}

function queueRedraw(node) {
  const appRef = getApp();
  node?.setDirtyCanvas?.(true, true);
  appRef?.graph?.setDirtyCanvas?.(true, true);
}

function ensureMaskNodeShape(node) {
  if (!node) return;
  const width = DEFAULT_W;
  const height = Number(node.__mkrX1MaskLockedHeight || DEFAULT_H);
  if (!node.__mkrX1MaskFixedComputeSize) {
    node.__mkrX1MaskFixedComputeSize = true;
    node.__mkrX1MaskOrigComputeSize = node.computeSize;
    node.computeSize = function computeFixedMaskSize() {
      return [width, Number(this.__mkrX1MaskLockedHeight || DEFAULT_H)];
    };
  }
  node.resizable = false;
  node.flags = typeof node.flags === "object" && node.flags !== null ? node.flags : {};
  node.flags.resizable = false;
  const currentWidth = Number(node.size?.[0] || 0);
  const currentHeight = Number(node.size?.[1] || 0);
  if (Math.abs(currentWidth - width) <= 0.5 && Math.abs(currentHeight - height) <= 0.5) return;
  if (node.__mkrX1MaskSizing) return;
  node.__mkrX1MaskSizing = true;
  try {
    node.setSize?.([width, height]);
    node.size = [width, height];
  } finally {
    node.__mkrX1MaskSizing = false;
  }
}

function ensureState(node) {
  if (!node[STATE_KEY]) {
    node[STATE_KEY] = {
      image: null,
      previewSrc: "",
      coverage: null,
      loading: false,
      livePending: false,
      liveTimer: null,
      renderToken: 0,
      sourceSrc: "",
      sourceSig: "",
      sourceImage: null,
      dom: null,
      domWidget: null,
      controlsDom: null,
      controlsWidget: null,
    };
  }
  return node[STATE_KEY];
}

function sanitizeNodeTitle(node) {
  if (!node || typeof node.title !== "string") return;
  const suffix = " [Canvas]";
  if (!node.title.includes(suffix)) return;
  node.title = node.title.split(suffix).join("");
}

function removeDomWidgets(node) {
  if (!Array.isArray(node?.widgets)) return false;
  let changed = false;
  const kept = [];
  for (const widget of node.widgets) {
    const name = String(widget?.name || "");
    if (name === DOM_WIDGET_NAME) {
      try {
        widget?.onRemove?.();
      } catch (error) {
      }
      changed = true;
      continue;
    }
    kept.push(widget);
  }
  if (changed) node.widgets = kept;
  return changed;
}

function resetHooksToPrototype(node) {
  if (!node) return;
  const proto = Object.getPrototypeOf(node) || {};
  const hookNames = [
    "onDrawForeground",
    "onExecuted",
    "onConnectionsChange",
    "onConfigure",
    "onResize",
  ];
  for (const name of hookNames) {
    if (typeof proto[name] === "function") {
      node[name] = proto[name];
    } else {
      delete node[name];
    }
  }
}

function migrateRuntime(node) {
  if (!node) return;
  if (node.__mkrX1MaskRuntimeVersion === RUNTIME_VERSION) return;
  sanitizeNodeTitle(node);
  removeDomWidgets(node);
  resetHooksToPrototype(node);
  delete node.__mkrX1MaskUIAttached;
  delete node.__mkrX1MaskCanvasAttached;
  delete node[STATE_KEY];
  node.__mkrX1MaskRuntimeVersion = RUNTIME_VERSION;
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

function loadPreviewIntoState(node, state, info) {
  const url = buildViewUrl(info);
  if (!url) return;

  state.loading = true;
  updateDomVisuals(node, state);

  const src = `${url}&_ts=${Date.now()}`;
  state.previewSrc = src;

  const img = new Image();
  img.onload = () => {
    state.image = img;
    state.loading = false;
    updateDomVisuals(node, state);
    queueRedraw(node);
  };
  img.onerror = () => {
    state.previewSrc = "";
    state.image = null;
    state.loading = false;
    updateDomVisuals(node, state);
    queueRedraw(node);
  };
  img.src = src;
}

function isDrawableImage(image) {
  if (typeof HTMLCanvasElement !== "undefined" && image instanceof HTMLCanvasElement) {
    return image.width > 0 && image.height > 0;
  }
  return !!(image && image.complete && image.naturalWidth > 0 && image.naturalHeight > 0);
}

function roundRectPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(x, y, w, h, radius);
  } else {
    ctx.rect(x, y, w, h);
  }
}

function drawRoundedFill(ctx, x, y, w, h, r, fill) {
  roundRectPath(ctx, x, y, w, h, r);
  ctx.fillStyle = fill;
  ctx.fill();
}

function drawRoundedStroke(ctx, x, y, w, h, r, stroke, lineWidth = 1) {
  roundRectPath(ctx, x, y, w, h, r);
  ctx.strokeStyle = stroke;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
}

function drawChecker(ctx, rect) {
  const size = 16;
  for (let y = 0; y < rect.h; y += size) {
    for (let x = 0; x < rect.w; x += size) {
      const odd = ((Math.floor(x / size) + Math.floor(y / size)) % 2) === 1;
      ctx.fillStyle = odd ? "rgba(44,44,44,0.52)" : "rgba(31,31,31,0.72)";
      ctx.fillRect(rect.x + x, rect.y + y, size, size);
    }
  }
}

function drawImageContain(ctx, image, rect) {
  if (!isDrawableImage(image)) return;
  const iw = image.naturalWidth || image.videoWidth || image.width;
  const ih = image.naturalHeight || image.videoHeight || image.height;
  if (!iw || !ih) return;

  const scale = Math.min(rect.w / iw, rect.h / ih);
  const dw = iw * scale;
  const dh = ih * scale;
  const dx = rect.x + (rect.w - dw) * 0.5;
  const dy = rect.y + (rect.h - dh) * 0.5;
  ctx.drawImage(image, dx, dy, dw, dh);
}

function previewRectForNode(node) {
  const nodeW = Number.isFinite(node?.size?.[0]) ? Number(node.size[0]) : DEFAULT_W;
  const nodeH = Number.isFinite(node?.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;
  const x = PREVIEW_MARGIN;
  const w = Math.max(1, nodeW - PREVIEW_MARGIN * 2);
  const y = Math.max(76, nodeH - MASK_PREVIEW_HEIGHT - PREVIEW_MARGIN);
  const h = Math.max(1, nodeH - y - PREVIEW_MARGIN);
  return { x, y, w, h };
}

function drawCanvasPreview(node, ctx, state) {
  const rect = previewRectForNode(node);
  drawRoundedFill(ctx, rect.x, rect.y, rect.w, rect.h, 10, "rgba(31,31,31,0.98)");
  drawRoundedStroke(ctx, rect.x, rect.y, rect.w, rect.h, 10, "rgba(88,88,88,0.45)", 1);

  ctx.save();
  roundRectPath(ctx, rect.x, rect.y, rect.w, rect.h, 10);
  ctx.clip();
  drawChecker(ctx, rect);
  if (isDrawableImage(state.image)) drawImageContain(ctx, state.image, rect);
  ctx.restore();

  const badgeH = 16;
  drawRoundedFill(ctx, rect.x + 8, rect.y + 8, 42, badgeH, 8, "#1f1f1f");
  ctx.fillStyle = "rgba(244,248,252,0.92)";
  ctx.font = "700 10px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("MASK", rect.x + 29, rect.y + 16);

  if (Number.isFinite(Number(state.coverage))) {
    const text = `${Number(state.coverage).toFixed(2)}%`;
    const tw = ctx.measureText(text).width;
    const bw = Math.max(38, tw + 16);
    drawRoundedFill(ctx, rect.x + rect.w - bw - 8, rect.y + 8, bw, badgeH, 8, "#1f1f1f");
    ctx.fillStyle = ACCENT_LIME;
    ctx.fillText(text, rect.x + rect.w - bw * 0.5 - 8, rect.y + 16);
  }

  if (!isDrawableImage(state.image)) {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 12px sans-serif";
    ctx.fillStyle = "rgba(224,236,245,0.92)";
    const msg = state.loading
      ? "Loading preview..."
      : state.livePending
        ? "Updating preview..."
        : "Connect image input and tweak controls";
    ctx.fillText(msg, rect.x + rect.w * 0.5, rect.y + rect.h * 0.5);
  }
}

function createDomState(node, state) {
  if (state.dom && !state.domWidget) {
    return true;
  }
  const root = document.createElement("div");
  root.style.cssText = [
    "position:relative",
    "width:100%",
    "height:100%",
    "min-height:0",
    "--comfy-widget-height:100%",
    `--comfy-widget-min-height:${PREVIEW_MIN_H}px`,
    "overflow:hidden",
    "border-radius:10px",
    "border:1px solid var(--mkr-dark-label-highlight, #2e2e2e)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "box-sizing:border-box",
    "touch-action:none",
    "user-select:none",
    `--mkr-accent-lime:${ACCENT_LIME}`,
  ].join(";");

  const checker = document.createElement("div");
  checker.style.cssText = [
    "position:absolute",
    "inset:0",
    "background-image:linear-gradient(45deg, rgba(44,44,44,0.52) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.52) 75%, rgba(44,44,44,0.52)),linear-gradient(45deg, rgba(44,44,44,0.52) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.52) 75%, rgba(44,44,44,0.52))",
    "background-position:0 0, 8px 8px",
    "background-size:16px 16px",
  ].join(";");

  const image = document.createElement("img");
  image.alt = "Mask Preview";
  image.draggable = false;
  image.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:contain",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const badgeMask = document.createElement("div");
  badgeMask.textContent = "MASK";
  badgeMask.style.cssText = [
    "position:absolute",
    "top:8px",
    "left:8px",
    "height:16px",
    "padding:0 10px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
  ].join(";");

  const badgeCoverage = document.createElement("div");
  badgeCoverage.style.cssText = [
    "position:absolute",
    "top:8px",
    "right:8px",
    "height:16px",
    "padding:0 10px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:var(--mkr-accent-lime, #D2FD51)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
  ].join(";");
  badgeCoverage.textContent = "";

  const status = document.createElement("div");
  status.style.cssText = [
    "position:absolute",
    "left:50%",
    "top:50%",
    "transform:translate(-50%, -50%)",
    "font:600 12px sans-serif",
    "color:rgba(244,244,244,0.92)",
    "text-align:center",
    "padding:8px 10px",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "border-radius:8px",
    "pointer-events:none",
    "max-width:90%",
    "white-space:normal",
  ].join(";");
  status.textContent = "Connect image input and tweak controls";

  root.appendChild(checker);
  root.appendChild(image);
  root.appendChild(badgeMask);
  root.appendChild(badgeCoverage);
  root.appendChild(status);

  state.dom = { root, image, status, badgeCoverage };

  const widget = node.addDOMWidget?.(DOM_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => PREVIEW_MIN_H,
    getMaxHeight: () => Number.POSITIVE_INFINITY,
  });
  if (!widget) {
    state.dom = null;
    state.domWidget = null;
    return false;
  }
  widget.serialize = false;
  state.domWidget = widget;
  return true;
}

function isDomMounted(state) {
  const root = state?.dom?.root;
  return !!(root && root.isConnected && root.getClientRects && root.getClientRects().length);
}

function normalizeDomWidgetStack(node, state) {
  if (!Array.isArray(node?.widgets)) return false;
  let changed = false;

  const controlWidgets = node.widgets.filter((w) => String(w?.name || "") === CONTROLS_WIDGET_NAME);
  if (controlWidgets.length > 1 && state?.controlsWidget) {
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== CONTROLS_WIDGET_NAME || w === state.controlsWidget);
    changed = true;
  }

  if (state?.domWidget) {
    const domWidgets = node.widgets.filter((w) => String(w?.name || "") === DOM_WIDGET_NAME);
    if (domWidgets.length > 1) {
      node.widgets = node.widgets.filter((w) => String(w?.name || "") !== DOM_WIDGET_NAME || w === state.domWidget);
      changed = true;
    }
  } else {
    const before = node.widgets.length;
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== DOM_WIDGET_NAME);
    changed = changed || node.widgets.length !== before;
  }

  if (state?.controlsWidget) {
    const controlsIndex = node.widgets.indexOf(state.controlsWidget);
    if (controlsIndex > -1 && controlsIndex !== 0) {
      const [controlsWidget] = node.widgets.splice(controlsIndex, 1);
      node.widgets.unshift(controlsWidget);
      changed = true;
    }
  }

  if (state?.domWidget) {
    const previewIndex = node.widgets.indexOf(state.domWidget);
    const targetIndex = state?.controlsWidget ? 1 : 0;
    if (previewIndex > -1 && previewIndex !== targetIndex) {
      const [previewWidget] = node.widgets.splice(previewIndex, 1);
      node.widgets.splice(targetIndex, 0, previewWidget);
      changed = true;
    }
  }

  if (state?.controlsWidget) {
    const innerWidth = Math.max(220, DEFAULT_W - 20);
    const nodeHeight = Number(node?.__mkrX1MaskLockedHeight || node?.size?.[1] || DEFAULT_H);
    if (state?.domWidget) {
      const controlsHeight = resolveMaskControlsHeight(node, state);
      const previewY = LAYOUT_TOP + controlsHeight + LAYOUT_GAP;
      const previewHeight = Math.max(PREVIEW_MIN_H, nodeHeight - previewY - LAYOUT_BOTTOM);
      changed = applyWidgetBox(state.controlsWidget, innerWidth, controlsHeight, LAYOUT_TOP) || changed;
      changed = applyWidgetBox(state.domWidget, innerWidth, previewHeight, previewY) || changed;
    } else {
      const panelHeight = Math.max(PREVIEW_MIN_H + 120, nodeHeight - LAYOUT_TOP - LAYOUT_BOTTOM);
      changed = applyWidgetBox(state.controlsWidget, innerWidth, panelHeight, LAYOUT_TOP) || changed;
    }
  }
  node.__mkrX1MaskWidgetByName = new Map(
    (node.widgets || [])
      .filter(Boolean)
      .map((widget) => [String(widget.name || ""), widget])
      .filter(([name]) => !!name)
  );
  return changed;
}

function updateDomVisuals(node, state) {
  const dom = state?.dom;
  if (!dom) return;

  const hasImage = !!state.previewSrc;
  if (hasImage) {
    if (dom.image.src !== state.previewSrc) dom.image.src = state.previewSrc;
    dom.image.style.display = "block";
    dom.status.style.display = "none";
  } else {
    dom.image.removeAttribute("src");
    dom.image.style.display = "none";
    dom.status.style.display = "block";
    dom.status.textContent = state.loading
      ? "Loading preview..."
      : state.livePending
        ? "Updating preview..."
        : "Connect image input and tweak controls";
  }

  if (Number.isFinite(Number(state.coverage))) {
    dom.badgeCoverage.textContent = `${Number(state.coverage).toFixed(2)}%`;
  } else {
    dom.badgeCoverage.textContent = "";
  }

  if (normalizeDomWidgetStack(node, state)) {
    queueRedraw(node);
  }
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function numberValue(value, fallback = 0) {
  const n = Number.parseFloat(String(value));
  return Number.isFinite(n) ? n : fallback;
}

function boolValue(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    return text === "true" || text === "1" || text === "yes" || text === "on";
  }
  return fallback;
}

function clampChoice(value, valid, fallback) {
  const token = String(value ?? fallback).trim().toLowerCase();
  return valid.includes(token) ? token : fallback;
}

function parseSettingsWidgetValue(rawValue) {
  const rawText = String(rawValue ?? "").trim();
  if (!rawText) return {};
  try {
    const parsed = JSON.parse(rawText);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    if (typeof parsed === "string" && MASK_MODE_VALUES.includes(parsed.trim().toLowerCase())) {
      return { mode: parsed.trim().toLowerCase() };
    }
  } catch (error) {
    if (MASK_MODE_VALUES.includes(rawText.toLowerCase())) {
      return { mode: rawText.toLowerCase() };
    }
  }
  return {};
}

function normalizeMaskSettings(payload) {
  const source = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const next = { ...MASK_DEFAULT_SETTINGS };
  next.mode = clampChoice(source.mode, MASK_MODE_VALUES, MASK_DEFAULT_SETTINGS.mode);
  next.channel = clampChoice(source.channel, MASK_CHANNEL_VALUES, MASK_DEFAULT_SETTINGS.channel);
  next.combine_mode = clampChoice(source.combine_mode, MASK_COMBINE_VALUES, MASK_DEFAULT_SETTINGS.combine_mode);
  for (const [name, spec] of Object.entries(MASK_NUMERIC_SPECS)) {
    const parsed = Number.parseFloat(String(source[name]));
    const base = Number.isFinite(parsed) ? parsed : Number(spec.fallback);
    const clamped = Math.max(spec.min, Math.min(spec.max, base));
    next[name] = spec.integer ? Math.round(clamped) : clamped;
  }
  next.invert_mask = boolValue(source.invert_mask, MASK_DEFAULT_SETTINGS.invert_mask);
  return next;
}

function serializeMaskSettings(settings) {
  return JSON.stringify(normalizeMaskSettings(settings));
}

function buildLegacyMaskSettingsFromValues(values) {
  if (!Array.isArray(values) || values.length < LEGACY_MASK_WIDGET_ORDER.length) return null;
  const payload = {};
  LEGACY_MASK_WIDGET_ORDER.forEach((name, index) => {
    if (values[index] !== undefined) payload[name] = values[index];
  });
  return normalizeMaskSettings(payload);
}

function migrateLegacyMaskWorkflow(node) {
  if (!node || node.__mkrX1MaskLegacyMigrated) return;
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  if (!settingsWidget) {
    node.__mkrX1MaskLegacyMigrated = true;
    return;
  }
  const legacySettings = buildLegacyMaskSettingsFromValues(node.widgets_values);
  if (!legacySettings) {
    node.__mkrX1MaskLegacyMigrated = true;
    return;
  }
  const serialized = serializeMaskSettings(legacySettings);
  settingsWidget.value = serialized;
  node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
  node.properties[SETTINGS_WIDGET_NAME] = serialized;
  node.widgets_values = [serialized];
  node.__mkrX1MaskLegacyMigrated = true;
}

function readMaskSettings(node) {
  migrateLegacyMaskWorkflow(node);
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  const widgetValue = settingsWidget?.value;
  const propertyValue = node?.properties?.[SETTINGS_WIDGET_NAME];
  const parsed = normalizeMaskSettings(
    parseSettingsWidgetValue(widgetValue !== undefined ? widgetValue : propertyValue)
  );
  const serialized = serializeMaskSettings(parsed);
  if (settingsWidget && settingsWidget.value !== serialized) {
    settingsWidget.value = serialized;
  }
  if (node) {
    node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
    node.properties[SETTINGS_WIDGET_NAME] = serialized;
    node.widgets_values = [serialized];
  }
  return parsed;
}

function writeMaskSettings(node, patch, options = {}) {
  const current = options.replace ? MASK_DEFAULT_SETTINGS : readMaskSettings(node);
  const next = normalizeMaskSettings(
    options.replace
      ? (typeof patch === "string" ? parseSettingsWidgetValue(patch) : patch)
      : { ...current, ...(typeof patch === "string" ? parseSettingsWidgetValue(patch) : patch) }
  );
  const serialized = serializeMaskSettings(next);
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  if (settingsWidget) {
    settingsWidget.value = serialized;
  }
  if (node) {
    node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
    node.properties[SETTINGS_WIDGET_NAME] = serialized;
    node.widgets_values = [serialized];
  }
  if (!options.silent && typeof settingsWidget?.callback === "function") {
    settingsWidget.callback(serialized, getApp()?.graph, node, settingsWidget);
  }
  return next;
}

function getWidget(node, name) {
  const key = String(name || "");
  if (!key) return null;
  const mapped = node?.__mkrX1MaskWidgetByName?.get?.(key);
  if (mapped) return mapped;
  return node.widgets?.find((w) => String(w?.name || "") === key) || null;
}

function setWidgetVisibility(widget, visible) {
  return setWidgetVisibilityInternal(widget, visible, new Set());
}

function setWidgetVisibilityInternal(widget, visible, seen) {
  if (!widget || seen.has(widget)) return false;
  seen.add(widget);
  if (!widget) return false;
  widget.__mkrVisibilityState ??= {
    type: widget.type,
    computeSize: widget.computeSize,
    computeLayoutSize: widget.computeLayoutSize,
    draw: widget.draw,
    disabled: widget.disabled,
    options: widget.options ? { ...widget.options } : undefined,
  };

  const state = widget.__mkrVisibilityState;
  const nextVisible = !!visible;
  const currentVisible = widget.hidden !== true && widget.type !== "hidden";
  let changed = currentVisible !== nextVisible;

  if (nextVisible) {
    widget.hidden = false;
    widget.visible = true;
    widget.type = state.type;
    widget.disabled = state.disabled;
    widget.computeSize = state.computeSize;
    widget.computeLayoutSize = state.computeLayoutSize;
    widget.draw = state.draw;
    widget.last_y = widget.last_y || 0;
    widget.y = widget.y || 0;
    widget.options = {
      ...(state.options || {}),
      hidden: false,
      visible: true,
      serialize: true,
    };
  } else {
    widget.hidden = true;
    widget.visible = false;
    widget.type = "hidden";
    widget.disabled = true;
    widget.computeSize = () => [0, -4];
    widget.computeLayoutSize = () => ({
      minHeight: 0,
      maxHeight: 0,
      minWidth: 0,
      preferredWidth: 0,
    });
    widget.draw = () => {};
    widget.last_y = 0;
    widget.y = 0;
    widget.options = {
      ...(state.options || widget.options || {}),
      hidden: true,
      visible: false,
      serialize: true,
    };
    for (const key of ["element", "inputEl", "textarea", "controlEl"]) {
      const el = widget?.[key];
      if (el?.style) {
        el.style.display = "none";
        el.style.visibility = "hidden";
        el.style.height = "0px";
        el.style.minHeight = "0px";
        el.style.maxHeight = "0px";
        el.style.margin = "0";
        el.style.padding = "0";
        el.style.overflow = "hidden";
      }
    }
  }

  const linked = Array.isArray(widget.linkedWidgets)
    ? widget.linkedWidgets
    : Array.isArray(widget.linked_widgets)
      ? widget.linked_widgets
      : [];
  for (const linkedWidget of linked) {
    changed = setWidgetVisibilityInternal(linkedWidget, visible, seen) || changed;
  }

  return changed;
}

function trySetWidgetY(widget, y) {
  if (!widget) return false;
  let changed = false;
  for (const key of ["y", "last_y", "_y"]) {
    const current = Number(widget?.[key]);
    if (Number.isFinite(current) && Math.abs(current - y) <= 0.5) continue;
    try {
      widget[key] = y;
      changed = true;
    } catch {
    }
  }
  return changed;
}

function applyWidgetBox(widget, width, height, y) {
  if (!widget) return false;
  const w = Math.max(220, Math.round(width));
  const h = Math.max(72, Math.round(height));
  let changed = false;
  widget.computeSize = () => [w, h];
  widget.computeLayoutSize = () => ({
    minHeight: h,
    maxHeight: h,
    minWidth: w,
    preferredWidth: w,
  });
  if (widget.element?.style) {
    widget.element.style.width = `${w}px`;
    widget.element.style.height = `${h}px`;
    widget.element.style.minHeight = `${h}px`;
    widget.element.style.maxHeight = `${h}px`;
    widget.element.style.marginLeft = "auto";
    widget.element.style.marginRight = "auto";
    widget.element.style.boxSizing = "border-box";
    widget.element.style.overflow = "hidden";
  }
  changed = trySetWidgetY(widget, y) || changed;
  return changed;
}

function resolveMaskControlsHeight(node, state) {
  const root = state?.controlsDom?.root;
  const measured = Math.ceil(Number(root?.scrollHeight || root?.getBoundingClientRect?.().height || 0));
  const rows = Array.isArray(state?.controlsDom?.rows)
    ? state.controlsDom.rows.filter((control) => control?.element?.style?.display !== "none").length
    : 0;
  const estimated = rows > 0 ? 82 + (rows * 28) + (Math.max(0, rows - 1) * 8) : CONTROLS_HEIGHT;
  const height = Math.max(estimated, measured > 0 ? measured + 4 : 0, 190);
  const nodeHeight = Number(node?.__mkrX1MaskLockedHeight || node?.size?.[1] || DEFAULT_H);
  return Math.min(height, nodeHeight - LAYOUT_TOP - LAYOUT_GAP - LAYOUT_BOTTOM - MASK_PREVIEW_HEIGHT);
}

function resolveMaskNodeHeightForMode(mode) {
  return DEFAULT_H;
}

function resolveMaskPanelHeight(state) {
  const visibleRows = Array.isArray(state?.controlsDom?.rows)
    ? state.controlsDom.rows.filter((control) => control?.element?.style?.display !== "none").length
    : 0;
  const rows = Math.max(6, visibleRows);
  const controlsEstimate = 48 + (rows * 22) + (Math.max(0, rows - 1) * 8);
  const panelHeight = controlsEstimate + 70 + MASK_PREVIEW_HEIGHT;
  return Math.max(panelHeight, 350);
}

function inputIsConnected(node, inputName) {
  const input = node?.inputs?.find((entry) => String(entry?.name || "") === String(inputName || ""));
  return readInputLinkIds(input).length > 0;
}

function syncMaskWidgetVisibility(node) {
  if (!node) return false;
  let changed = false;
  for (const widget of node.widgets || []) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) continue;
    changed = setWidgetVisibility(widget, false) || changed;
  }
  node.__mkrX1MaskWidgetByName = new Map(
    (node.widgets || [])
      .filter(Boolean)
      .map((widget) => [String(widget.name || ""), widget])
      .filter(([name]) => !!name)
  );
  delete node.__mkrX1MaskSerialWidgets;

  if (changed) {
    queueRedraw(node);
  }
  return changed;
}

function removeGeneratedInputs(node, names) {
  if (!node || !Array.isArray(node.inputs) || node.inputs.length === 0) return false;
  const hiddenNames = new Set((names || []).map((name) => String(name)));
  const keep = [];
  let changed = false;
  for (const input of node.inputs) {
    const name = String(input?.name || "");
    if (hiddenNames.has(name)) {
      changed = true;
      continue;
    }
    keep.push(input);
  }
  if (changed) node.inputs = keep;
  return changed;
}

function getWidgetValue(node, name, fallback) {
  const key = String(name || "");
  if (key && (key === SETTINGS_WIDGET_NAME || Object.prototype.hasOwnProperty.call(MASK_DEFAULT_SETTINGS, key))) {
    const settings = readMaskSettings(node);
    if (key === SETTINGS_WIDGET_NAME) {
      return serializeMaskSettings(settings);
    }
    if (Object.prototype.hasOwnProperty.call(settings, key)) {
      return settings[key];
    }
  }
  const widget = getWidget(node, key);
  if (widget && widget.value !== undefined) return widget.value;
  const prop = node?.properties?.[name];
  if (prop !== undefined) return prop;
  return fallback;
}

function sanitizeMaskNumericValue(name, value) {
  const spec = MASK_NUMERIC_SPECS?.[name];
  if (!spec) return value;
  const fallback = Number(spec.fallback);
  const parsed = Number.parseFloat(String(value));
  const base = Number.isFinite(parsed) ? parsed : fallback;
  const clamped = Math.max(spec.min, Math.min(spec.max, base));
  return spec.integer ? Math.round(clamped) : clamped;
}

function getSanitizedMaskValue(node, name, fallback) {
  const raw = getWidgetValue(node, name, fallback);
  const sanitized = sanitizeMaskNumericValue(name, raw);
  if (sanitized !== raw) {
    writeMaskSettings(node, { [name]: sanitized }, { silent: true });
  }
  return sanitized;
}

function setWidgetValue(node, name, value) {
  const key = String(name || "");
  if (!key) return;
  if (key === SETTINGS_WIDGET_NAME || Object.prototype.hasOwnProperty.call(MASK_DEFAULT_SETTINGS, key)) {
    writeMaskSettings(
      node,
      key === SETTINGS_WIDGET_NAME ? value : { [key]: value },
      { replace: key === SETTINGS_WIDGET_NAME }
    );
    queueRedraw(node);
    return;
  }
  const widget = getWidget(node, key);
  if (!widget) return;
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, getApp()?.graph, node, widget);
  }
  queueRedraw(node);
}

function createMaskLabel(text) {
  const label = document.createElement("div");
  label.style.cssText = "font:600 11px sans-serif;color:rgba(229,235,242,0.82);";
  label.textContent = text;
  return label;
}

function createMaskNumber(value, min, max, step) {
  const input = document.createElement("input");
  input.type = "number";
  input.value = String(value);
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.style.cssText = [
    "width:64px",
    "border-radius:8px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:rgba(9,10,13,0.48)",
    "color:rgba(245,248,252,0.92)",
    "padding:5px 6px",
    "font:600 11px sans-serif",
    "box-sizing:border-box",
  ].join(";");
  return input;
}

function createMaskRangeRow({ label, min, max, step, value, decimals = 2, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:92px 1fr 64px;gap:8px;align-items:center;";
  row.appendChild(createMaskLabel(label));

  const range = document.createElement("input");
  range.type = "range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);
  range.value = String(value);
  range.style.cssText = `width:100%;accent-color:${ACCENT_LIME};`;

  const number = createMaskNumber(Number(value).toFixed(decimals), min, max, step);
  const commit = (raw) => {
    const parsed = Number.parseFloat(String(raw));
    const next = Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : Number(value);
    range.value = String(next);
    number.value = next.toFixed(decimals);
    onChange?.(next);
  };
  range.addEventListener("input", () => commit(range.value));
  number.addEventListener("change", () => commit(number.value));

  row.appendChild(range);
  row.appendChild(number);
  return {
    element: row,
    setValue(next) {
      const parsed = Number.parseFloat(String(next));
      const normalized = Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : Math.max(min, Math.min(max, Number(value) || 0));
      range.value = String(normalized);
      number.value = normalized.toFixed(decimals);
    },
    setVisible(visible) {
      row.style.display = visible ? "grid" : "none";
    },
  };
}

function createMaskSelectRow({ label, options, value, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:92px 1fr;gap:8px;align-items:center;";
  row.appendChild(createMaskLabel(label));
  const select = document.createElement("select");
  select.style.cssText = [
    "width:100%",
    "border-radius:9px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:rgba(9,10,13,0.48)",
    "color:rgba(245,248,252,0.92)",
    "padding:7px 8px",
    "font:600 11px sans-serif",
    "box-sizing:border-box",
  ].join(";");
  for (const optionValue of options) {
    const option = document.createElement("option");
    option.value = String(optionValue);
    option.textContent = String(optionValue);
    select.appendChild(option);
  }
  select.value = String(value);
  select.addEventListener("change", () => onChange?.(select.value));
  row.appendChild(select);
  return {
    element: row,
    setValue(next) {
      select.value = String(next);
    },
    setVisible(visible) {
      row.style.display = visible ? "grid" : "none";
    },
  };
}

function createMaskToggleRow({ label, checked, onChange }) {
  const row = document.createElement("label");
  row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;";
  row.appendChild(createMaskLabel(label));
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = !!checked;
  input.style.cssText = `accent-color:${ACCENT_LIME};`;
  input.addEventListener("change", () => onChange?.(input.checked));
  row.appendChild(input);
  return {
    element: row,
    setValue(next) {
      input.checked = !!next;
    },
  };
}

function ensureControlsDom(node, state) {
  const controlsReady =
    !!state.controlsDom &&
    !!state.controlsWidget &&
    !!state.dom &&
    Array.isArray(node?.widgets) &&
    node.widgets.includes(state.controlsWidget);
  if (controlsReady) return;
  state.controlsDom = null;
  state.controlsWidget = null;
  state.dom = null;
  state.domWidget = null;

  const root = document.createElement("div");
  root.className = "mkr-seamless-panel";

  const controls = document.createElement("div");
  controls.style.cssText = "display:grid;gap:8px;";
  root.appendChild(controls);

  const mode = createMaskSelectRow({
    label: "Mode",
    options: ["luminance", "channel", "hue", "saturation", "value", "skin_tones", "chroma_key", "edge", "radial"],
    value: getWidgetValue(node, "mode", "luminance"),
    onChange: (next) => { setWidgetValue(node, "mode", next); updateMaskControls(node, state); scheduleLivePreview(node, state); },
  });
  const channel = createMaskSelectRow({
    label: "Channel",
    options: ["luma", "red", "green", "blue", "alpha"],
    value: getWidgetValue(node, "channel", "luma"),
    onChange: (next) => { setWidgetValue(node, "channel", next); scheduleLivePreview(node, state); },
  });
  const threshold = createMaskRangeRow({
    label: "Threshold",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "threshold", 0.5),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "threshold", next); scheduleLivePreview(node, state); },
  });
  const softness = createMaskRangeRow({
    label: "Softness",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "softness", 0.08),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "softness", next); scheduleLivePreview(node, state); },
  });
  const minValue = createMaskRangeRow({
    label: "Min",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "min_value", 0.2),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "min_value", next); scheduleLivePreview(node, state); },
  });
  const maxValue = createMaskRangeRow({
    label: "Max",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "max_value", 0.8),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "max_value", next); scheduleLivePreview(node, state); },
  });
  const hueCenter = createMaskRangeRow({
    label: "Hue",
    min: 0,
    max: 360,
    step: 0.1,
    value: getWidgetValue(node, "hue_center", 120),
    decimals: 1,
    onChange: (next) => { setWidgetValue(node, "hue_center", next); scheduleLivePreview(node, state); },
  });
  const hueWidth = createMaskRangeRow({
    label: "Hue Width",
    min: 0,
    max: 180,
    step: 0.1,
    value: getWidgetValue(node, "hue_width", 24),
    decimals: 1,
    onChange: (next) => { setWidgetValue(node, "hue_width", next); scheduleLivePreview(node, state); },
  });
  const colorTolerance = createMaskRangeRow({
    label: "Tolerance",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "color_tolerance", 0.25),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "color_tolerance", next); scheduleLivePreview(node, state); },
  });
  const targetR = createMaskRangeRow({
    label: "Target R",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "target_r", 0),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "target_r", next); scheduleLivePreview(node, state); },
  });
  const targetG = createMaskRangeRow({
    label: "Target G",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "target_g", 1),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "target_g", next); scheduleLivePreview(node, state); },
  });
  const targetB = createMaskRangeRow({
    label: "Target B",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "target_b", 0),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "target_b", next); scheduleLivePreview(node, state); },
  });
  const edgeRadius = createMaskRangeRow({
    label: "Edge Rad",
    min: 0,
    max: 32,
    step: 0.1,
    value: getWidgetValue(node, "edge_radius", 1),
    decimals: 1,
    onChange: (next) => { setWidgetValue(node, "edge_radius", next); scheduleLivePreview(node, state); },
  });
  const edgeStrength = createMaskRangeRow({
    label: "Edge Gain",
    min: 0,
    max: 4,
    step: 0.01,
    value: getWidgetValue(node, "edge_strength", 1),
    onChange: (next) => { setWidgetValue(node, "edge_strength", next); scheduleLivePreview(node, state); },
  });
  const radius = createMaskRangeRow({
    label: "Radius",
    min: 0,
    max: 2,
    step: 0.001,
    value: getWidgetValue(node, "radius", 0.28),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "radius", next); scheduleLivePreview(node, state); },
  });
  const centerX = createMaskRangeRow({
    label: "Center X",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "center_x", 0.5),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "center_x", next); scheduleLivePreview(node, state); },
  });
  const centerY = createMaskRangeRow({
    label: "Center Y",
    min: 0,
    max: 1,
    step: 0.001,
    value: getWidgetValue(node, "center_y", 0.5),
    decimals: 3,
    onChange: (next) => { setWidgetValue(node, "center_y", next); scheduleLivePreview(node, state); },
  });
  const falloff = createMaskRangeRow({
    label: "Falloff",
    min: 0.05,
    max: 6,
    step: 0.01,
    value: getWidgetValue(node, "falloff", 1),
    onChange: (next) => { setWidgetValue(node, "falloff", next); scheduleLivePreview(node, state); },
  });
  const expandPixels = createMaskRangeRow({
    label: "Expand",
    min: -64,
    max: 64,
    step: 1,
    value: getWidgetValue(node, "expand_pixels", 0),
    decimals: 0,
    onChange: (next) => { setWidgetValue(node, "expand_pixels", Math.round(next)); scheduleLivePreview(node, state); },
  });
  const blurRadius = createMaskRangeRow({
    label: "Blur",
    min: 0,
    max: 64,
    step: 0.1,
    value: getWidgetValue(node, "blur_radius", 0),
    decimals: 1,
    onChange: (next) => { setWidgetValue(node, "blur_radius", next); scheduleLivePreview(node, state); },
  });
  const maskGamma = createMaskRangeRow({
    label: "Gamma",
    min: 0.1,
    max: 4,
    step: 0.01,
    value: getWidgetValue(node, "mask_gamma", 1),
    onChange: (next) => { setWidgetValue(node, "mask_gamma", next); scheduleLivePreview(node, state); },
  });
  const invertMask = createMaskToggleRow({
    label: "Invert",
    checked: !!getWidgetValue(node, "invert_mask", false),
    onChange: (checked) => { setWidgetValue(node, "invert_mask", checked); scheduleLivePreview(node, state); },
  });

  [
    mode, channel, threshold, softness, minValue, maxValue, hueCenter, hueWidth,
    colorTolerance, targetR, targetG, targetB, edgeRadius, edgeStrength, centerX, centerY,
    radius, falloff, expandPixels, blurRadius, maskGamma, invertMask,
  ].forEach((control) => controls.appendChild(control.element));

  const previewRoot = document.createElement("div");
  previewRoot.style.cssText = [
    "position:relative",
    `flex:0 0 ${MASK_PREVIEW_HEIGHT}px`,
    `min-height:${MASK_PREVIEW_HEIGHT}px`,
    `max-height:${MASK_PREVIEW_HEIGHT}px`,
    "overflow:hidden",
    "border-radius:10px",
    "border:1px solid var(--mkr-dark-label-highlight, #2e2e2e)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "box-sizing:border-box",
    "touch-action:none",
    "user-select:none",
    `--mkr-accent-lime:${ACCENT_LIME}`,
  ].join(";");

  const checker = document.createElement("div");
  checker.style.cssText = [
    "position:absolute",
    "inset:0",
    "background-image:linear-gradient(45deg, rgba(44,44,44,0.52) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.52) 75%, rgba(44,44,44,0.52)),linear-gradient(45deg, rgba(44,44,44,0.52) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.52) 75%, rgba(44,44,44,0.52))",
    "background-position:0 0, 8px 8px",
    "background-size:16px 16px",
  ].join(";");

  const image = document.createElement("img");
  image.alt = "Mask Preview";
  image.draggable = false;
  image.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:contain",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const badgeMask = document.createElement("div");
  badgeMask.textContent = "MASK";
  badgeMask.style.cssText = [
    "position:absolute",
    "top:8px",
    "left:8px",
    "height:16px",
    "padding:0 10px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
  ].join(";");

  const badgeCoverage = document.createElement("div");
  badgeCoverage.style.cssText = [
    "position:absolute",
    "top:8px",
    "right:8px",
    "height:16px",
    "padding:0 10px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:var(--mkr-accent-lime, #D2FD51)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
  ].join(";");
  badgeCoverage.textContent = "";

  const status = document.createElement("div");
  status.style.cssText = [
    "position:absolute",
    "left:50%",
    "top:50%",
    "transform:translate(-50%, -50%)",
    "font:600 12px sans-serif",
    "color:rgba(244,244,244,0.92)",
    "text-align:center",
    "padding:8px 10px",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "border-radius:8px",
    "pointer-events:none",
    "max-width:90%",
    "white-space:normal",
  ].join(";");
  status.textContent = "Connect image input and tweak controls";

  previewRoot.appendChild(checker);
  previewRoot.appendChild(image);
  previewRoot.appendChild(badgeMask);
  previewRoot.appendChild(badgeCoverage);
  previewRoot.appendChild(status);
  root.appendChild(previewRoot);

  state.dom = { root: previewRoot, image, status, badgeCoverage };

  const widget = node.addDOMWidget?.(CONTROLS_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => 290,
    getMaxHeight: () => 360,
  });
  if (widget) widget.serialize = false;

  state.controlsWidget = widget;
  state.controlsDom = {
    root,
    mode,
    channel,
    threshold,
    softness,
    minValue,
    maxValue,
    hueCenter,
    hueWidth,
    colorTolerance,
    targetR,
    targetG,
    targetB,
    edgeRadius,
    edgeStrength,
    centerX,
    centerY,
    radius,
    falloff,
    expandPixels,
    blurRadius,
    maskGamma,
    invertMask,
    rows: [
      mode,
      channel,
      threshold,
      softness,
      minValue,
      maxValue,
      hueCenter,
      hueWidth,
      colorTolerance,
      targetR,
      targetG,
      targetB,
      edgeRadius,
      edgeStrength,
      centerX,
      centerY,
      radius,
      falloff,
      expandPixels,
      blurRadius,
      maskGamma,
      invertMask,
    ],
  };
}

function updateMaskControls(node, state) {
  const mode = String(getWidgetValue(node, "mode", "luminance")).toLowerCase();
  node.__mkrX1MaskLockedHeight = resolveMaskNodeHeightForMode(mode);
  ensureMaskNodeShape(node);
  syncMaskWidgetVisibility(node);
  removeGeneratedInputs(node, HIDDEN_WIDGET_NAMES);
  ensureControlsDom(node, state);
  const dom = state.controlsDom;
  if (!dom) return;

  dom.mode.setValue(mode);
  dom.channel.setValue(getWidgetValue(node, "channel", "luma"));
  dom.threshold.setValue(getSanitizedMaskValue(node, "threshold", 0.5));
  dom.softness.setValue(getSanitizedMaskValue(node, "softness", 0.08));
  dom.minValue.setValue(getSanitizedMaskValue(node, "min_value", 0.2));
  dom.maxValue.setValue(getSanitizedMaskValue(node, "max_value", 0.8));
  dom.hueCenter.setValue(getSanitizedMaskValue(node, "hue_center", 120));
  dom.hueWidth.setValue(getSanitizedMaskValue(node, "hue_width", 24));
  dom.colorTolerance.setValue(getSanitizedMaskValue(node, "color_tolerance", 0.25));
  dom.targetR.setValue(getSanitizedMaskValue(node, "target_r", 0));
  dom.targetG.setValue(getSanitizedMaskValue(node, "target_g", 1));
  dom.targetB.setValue(getSanitizedMaskValue(node, "target_b", 0));
  dom.edgeRadius.setValue(getSanitizedMaskValue(node, "edge_radius", 1));
  dom.edgeStrength.setValue(getSanitizedMaskValue(node, "edge_strength", 1));
  dom.centerX.setValue(getSanitizedMaskValue(node, "center_x", 0.5));
  dom.centerY.setValue(getSanitizedMaskValue(node, "center_y", 0.5));
  dom.radius.setValue(getSanitizedMaskValue(node, "radius", 0.28));
  dom.falloff.setValue(getSanitizedMaskValue(node, "falloff", 1));
  dom.expandPixels.setValue(getSanitizedMaskValue(node, "expand_pixels", 0));
  dom.blurRadius.setValue(getSanitizedMaskValue(node, "blur_radius", 0));
  dom.maskGamma.setValue(getSanitizedMaskValue(node, "mask_gamma", 1));
  dom.invertMask.setValue(!!getWidgetValue(node, "invert_mask", false));

  dom.channel.setVisible(mode === "channel");
  dom.threshold.setVisible(mode === "channel" || mode === "luminance" || mode === "edge" || mode === "skin_tones");
  dom.minValue.setVisible(mode === "saturation" || mode === "value");
  dom.maxValue.setVisible(mode === "saturation" || mode === "value");
  dom.hueCenter.setVisible(mode === "hue");
  dom.hueWidth.setVisible(mode === "hue");
  dom.colorTolerance.setVisible(mode === "chroma_key");
  dom.targetR.setVisible(mode === "chroma_key");
  dom.targetG.setVisible(mode === "chroma_key");
  dom.targetB.setVisible(mode === "chroma_key");
  dom.edgeRadius.setVisible(mode === "edge");
  dom.edgeStrength.setVisible(mode === "edge");
  dom.centerX.setVisible(mode === "radial");
  dom.centerY.setVisible(mode === "radial");
  dom.radius.setVisible(mode === "radial");
  dom.falloff.setVisible(mode === "radial");
  node.__mkrX1MaskLockedHeight = LAYOUT_TOP + resolveMaskPanelHeight(state) + LAYOUT_BOTTOM;
  ensureMaskNodeShape(node);
  normalizeDomWidgetStack(node, state);
}

function smoothstep(edge0, edge1, x) {
  if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3 - (2 * t));
}

function softThreshold(x, threshold, softness) {
  const t = numberValue(threshold, 0.5);
  const s = Math.max(0, numberValue(softness, 0));
  if (s <= 1e-6) return x >= t ? 1 : 0;
  const half = s * 0.5;
  return smoothstep(t - half, t + half, x);
}

function softRange(x, minV, maxV, softness) {
  const lo = Math.min(numberValue(minV, 0), numberValue(maxV, 1));
  const hi = Math.max(numberValue(minV, 0), numberValue(maxV, 1));
  const lower = softThreshold(x, lo, softness);
  const upper = 1 - softThreshold(x, hi, softness);
  return clamp01(lower * upper);
}

function rgbToHsv(r, g, b) {
  const maxc = Math.max(r, g, b);
  const minc = Math.min(r, g, b);
  const delta = maxc - minc;

  let h = 0;
  if (delta > 1e-8) {
    if (maxc === r) {
      h = ((g - b) / delta) % 6;
    } else if (maxc === g) {
      h = ((b - r) / delta) + 2;
    } else {
      h = ((r - g) / delta) + 4;
    }
    h = (h / 6 + 1) % 1;
  }

  const s = maxc > 1e-8 ? (delta / maxc) : 0;
  const v = maxc;
  return [h, s, v];
}

function boxBlurGray(input, w, h, radius) {
  const r = Math.max(1, Math.round(numberValue(radius, 0)));
  if (r <= 0) return input;

  const size = (2 * r) + 1;
  const temp = new Float32Array(input.length);
  const out = new Float32Array(input.length);

  for (let y = 0; y < h; y += 1) {
    let sum = 0;
    for (let i = -r; i <= r; i += 1) {
      const sx = Math.max(0, Math.min(w - 1, i));
      sum += input[(y * w) + sx];
    }
    for (let x = 0; x < w; x += 1) {
      temp[(y * w) + x] = sum / size;
      const removeX = Math.max(0, Math.min(w - 1, x - r));
      const addX = Math.max(0, Math.min(w - 1, x + r + 1));
      sum += input[(y * w) + addX] - input[(y * w) + removeX];
    }
  }

  for (let x = 0; x < w; x += 1) {
    let sum = 0;
    for (let i = -r; i <= r; i += 1) {
      const sy = Math.max(0, Math.min(h - 1, i));
      sum += temp[(sy * w) + x];
    }
    for (let y = 0; y < h; y += 1) {
      out[(y * w) + x] = sum / size;
      const removeY = Math.max(0, Math.min(h - 1, y - r));
      const addY = Math.max(0, Math.min(h - 1, y + r + 1));
      sum += temp[(addY * w) + x] - temp[(removeY * w) + x];
    }
  }

  return out;
}

function morphMask(mask, w, h, pixels) {
  const p = Math.trunc(numberValue(pixels, 0));
  if (p === 0) return mask;
  const radius = Math.min(Math.abs(p), 10);
  if (radius <= 0) return mask;

  const out = new Float32Array(mask.length);
  const dilate = p > 0;

  for (let y = 0; y < h; y += 1) {
    const y0 = Math.max(0, y - radius);
    const y1 = Math.min(h - 1, y + radius);
    for (let x = 0; x < w; x += 1) {
      const x0 = Math.max(0, x - radius);
      const x1 = Math.min(w - 1, x + radius);
      let v = dilate ? 0 : 1;
      for (let yy = y0; yy <= y1; yy += 1) {
        const row = yy * w;
        for (let xx = x0; xx <= x1; xx += 1) {
          const sample = mask[row + xx];
          if (dilate) {
            if (sample > v) v = sample;
          } else if (sample < v) {
            v = sample;
          }
        }
      }
      out[(y * w) + x] = v;
    }
  }
  return out;
}

function readInputLinkIds(input) {
  if (!input || typeof input !== "object") return [];
  const values = [];
  const pushVal = (value) => {
    if (Array.isArray(value)) {
      for (const v of value) pushVal(v);
      return;
    }
    if (value === null || value === undefined) return;
    const n = Number.parseInt(String(value), 10);
    if (Number.isFinite(n)) values.push(n);
  };
  pushVal(input.links);
  pushVal(input.link);
  pushVal(input.linkId);
  pushVal(input.link_id);
  pushVal(input.last_link);
  pushVal(input.lastLink);
  return [...new Set(values)];
}

function resolveLinkedImageSource(node, inputName) {
  const index = node.inputs?.findIndex((entry) => String(entry?.name || "") === inputName) ?? -1;
  if (index < 0) {
    return { connected: false, linkSig: "none", sourceId: "none", src: "", drawable: null, signature: "none" };
  }

  const input = node.inputs?.[index];
  const links = readInputLinkIds(input);
  const linkSig = links.length ? links.join(",") : "none";
  const graph = node?.graph || getApp()?.graph || null;
  const graphLinks = graph?.links || {};
  let sourceIdFromLinks = "";
  for (const linkId of links) {
    const linkInfo = graphLinks?.[linkId];
    if (linkInfo?.origin_id !== undefined && linkInfo?.origin_id !== null) {
      sourceIdFromLinks = String(linkInfo.origin_id);
      break;
    }
  }

  let sourceNode = node.getInputNode?.(index) || null;
  if (!sourceNode && sourceIdFromLinks && graph?.getNodeById) {
    sourceNode = graph.getNodeById(Number.parseInt(sourceIdFromLinks, 10)) || null;
  }

  const sourceId = sourceNode
    ? String(sourceNode.id ?? "none")
    : (sourceIdFromLinks || "none");
  const sourceWidgetSig = sourceNodeWidgetSignature(sourceNode);
  const samples = Array.isArray(sourceNode?.imgs) ? sourceNode.imgs : [];
  const sample = samples.length ? samples[0] : null;

  let src = "";
  let drawable = null;
  if (sample instanceof HTMLImageElement || (typeof HTMLCanvasElement !== "undefined" && sample instanceof HTMLCanvasElement)) {
    drawable = sample;
    src = sample.src || "";
  } else if (sample && typeof sample === "object") {
    if (typeof sample.src === "string") src = sample.src;
    if (sample.image instanceof HTMLImageElement || (typeof HTMLCanvasElement !== "undefined" && sample.image instanceof HTMLCanvasElement)) {
      drawable = sample.image;
    } else if (typeof HTMLCanvasElement !== "undefined" && sample.canvas instanceof HTMLCanvasElement) {
      drawable = sample.canvas;
    }
  } else if (typeof sample === "string") {
    src = sample;
  }

  const widgetUrl = buildInputImageUrlFromSourceNode(sourceNode);
  if (widgetUrl) {
    src = widgetUrl;
    drawable = null;
  }

  let drawMeta = "none";
  if (drawable) {
    const dw = drawable.naturalWidth || drawable.videoWidth || drawable.width || 0;
    const dh = drawable.naturalHeight || drawable.videoHeight || drawable.height || 0;
    const dsrc = drawable.currentSrc || drawable.src || "";
    drawMeta = `${dw}x${dh}:${dsrc}`;
  }
  const drawStamp = drawable ? drawableContentStamp(drawable) : "none";
  const drawableSig = drawable ? objectId(drawable) : "none";
  const srcSig = src || "none";
  const connected = linkSig !== "none" || !!sourceNode || sourceId !== "none";
  const signature = `link=${linkSig}|source=${sourceId}|wsig=${sourceWidgetSig}|draw=${drawableSig}|stamp=${drawStamp}|meta=${drawMeta}|src=${srcSig}`;
  return { connected, linkSig, sourceId, src, drawable, signature };
}

function readMaskParams(node) {
  return {
    mode: String(getWidgetValue(node, "mode", "luminance")).toLowerCase(),
    channel: String(getWidgetValue(node, "channel", "luma")).toLowerCase(),
    threshold: numberValue(getSanitizedMaskValue(node, "threshold", 0.5), 0.5),
    softness: numberValue(getSanitizedMaskValue(node, "softness", 0.08), 0.08),
    minValue: numberValue(getSanitizedMaskValue(node, "min_value", 0.2), 0.2),
    maxValue: numberValue(getSanitizedMaskValue(node, "max_value", 0.8), 0.8),
    hueCenter: numberValue(getSanitizedMaskValue(node, "hue_center", 120.0), 120.0),
    hueWidth: numberValue(getSanitizedMaskValue(node, "hue_width", 24.0), 24.0),
    targetR: numberValue(getSanitizedMaskValue(node, "target_r", 0.0), 0.0),
    targetG: numberValue(getSanitizedMaskValue(node, "target_g", 1.0), 1.0),
    targetB: numberValue(getSanitizedMaskValue(node, "target_b", 0.0), 0.0),
    colorTolerance: numberValue(getSanitizedMaskValue(node, "color_tolerance", 0.25), 0.25),
    edgeRadius: numberValue(getSanitizedMaskValue(node, "edge_radius", 1.0), 1.0),
    edgeStrength: numberValue(getSanitizedMaskValue(node, "edge_strength", 1.0), 1.0),
    centerX: numberValue(getSanitizedMaskValue(node, "center_x", 0.5), 0.5),
    centerY: numberValue(getSanitizedMaskValue(node, "center_y", 0.5), 0.5),
    radius: numberValue(getSanitizedMaskValue(node, "radius", 0.28), 0.28),
    falloff: numberValue(getSanitizedMaskValue(node, "falloff", 1.0), 1.0),
    expandPixels: numberValue(getSanitizedMaskValue(node, "expand_pixels", 0), 0),
    blurRadius: numberValue(getSanitizedMaskValue(node, "blur_radius", 0.0), 0.0),
    maskGamma: numberValue(getSanitizedMaskValue(node, "mask_gamma", 1.0), 1.0),
    invertMask: boolValue(getWidgetValue(node, "invert_mask", false), false),
  };
}

function buildLocalMaskPreview(sourceImage, params) {
  // Fast local preview path for Node 2.0: renders from current widget values without graph execution.
  const iw = sourceImage.naturalWidth || sourceImage.width || 1;
  const ih = sourceImage.naturalHeight || sourceImage.height || 1;
  const scale = Math.min(1, LOCAL_PREVIEW_MAX_DIM / Math.max(iw, ih));
  const w = Math.max(1, Math.round(iw * scale));
  const h = Math.max(1, Math.round(ih * scale));
  const len = w * h;

  const srcCanvas = document.createElement("canvas");
  srcCanvas.width = w;
  srcCanvas.height = h;
  const srcCtx = srcCanvas.getContext("2d", { willReadFrequently: true });
  if (!srcCtx) return { canvas: srcCanvas, coverage: 0 };
  srcCtx.drawImage(sourceImage, 0, 0, w, h);

  const srcData = srcCtx.getImageData(0, 0, w, h);
  const data = srcData.data;
  let mask = new Float32Array(len);

  if (params.mode === "edge") {
    let luma = new Float32Array(len);
    for (let i = 0, p = 0; i < len; i += 1, p += 4) {
      const a = data[p + 3] / 255;
      const invA = a > 1e-6 ? (1 / a) : 0;
      const r = clamp01((data[p] / 255) * invA);
      const g = clamp01((data[p + 1] / 255) * invA);
      const b = clamp01((data[p + 2] / 255) * invA);
      luma[i] = (0.2126 * r) + (0.7152 * g) + (0.0722 * b);
    }
    if (params.edgeRadius > 1e-3) {
      luma = boxBlurGray(luma, w, h, Math.min(params.edgeRadius, 12));
    }
    let maxMag = 1e-6;
    const mag = new Float32Array(len);
    for (let y = 0; y < h; y += 1) {
      const ym1 = Math.max(0, y - 1);
      const yp1 = Math.min(h - 1, y + 1);
      for (let x = 0; x < w; x += 1) {
        const xm1 = Math.max(0, x - 1);
        const xp1 = Math.min(w - 1, x + 1);
        const gx = (luma[(y * w) + xp1] - luma[(y * w) + xm1]) * 0.5;
        const gy = (luma[(yp1 * w) + x] - luma[(ym1 * w) + x]) * 0.5;
        const m = Math.sqrt((gx * gx) + (gy * gy));
        const idx = (y * w) + x;
        mag[idx] = m;
        if (m > maxMag) maxMag = m;
      }
    }
    for (let i = 0; i < len; i += 1) {
      const v = clamp01((mag[i] / maxMag) * Math.max(0, params.edgeStrength));
      mask[i] = softThreshold(v, params.threshold, params.softness);
    }
  } else {
    const mode = params.mode;
    const hueCenter = ((params.hueCenter % 360) + 360) % 360 / 360;
    const hueHalfWidth = Math.max(0, Math.min(180, params.hueWidth)) / 360;
    const hueSoftness = Math.max(1 / 360, (Math.max(0, params.softness) * 0.5) / 360);
    const chromaNorm = Math.sqrt(3);

    for (let i = 0, p = 0; i < len; i += 1, p += 4) {
      const a = data[p + 3] / 255;
      const invA = a > 1e-6 ? (1 / a) : 0;
      const r = clamp01((data[p] / 255) * invA);
      const g = clamp01((data[p + 1] / 255) * invA);
      const b = clamp01((data[p + 2] / 255) * invA);
      let m = 0;

      if (mode === "radial") {
        const x = w > 1 ? ((i % w) / (w - 1)) : 0.5;
        const y = h > 1 ? (Math.floor(i / w) / (h - 1)) : 0.5;
        const dx = x - params.centerX;
        const dy = y - params.centerY;
        const dist = Math.sqrt((dx * dx) + (dy * dy));
        const softness = Math.max(1e-6, params.softness);
        const band = 1 - smoothstep(Math.max(0, params.radius), Math.max(0, params.radius) + softness, dist);
        m = Math.pow(clamp01(band), Math.max(0.05, params.falloff));
      } else if (mode === "hue" || mode === "saturation" || mode === "value") {
        const [hue, sat, val] = rgbToHsv(r, g, b);
        if (mode === "hue") {
          const wrapped = ((hue - hueCenter + 1.5) % 1) - 0.5;
          const dist = Math.abs(wrapped);
          m = 1 - smoothstep(hueHalfWidth, hueHalfWidth + hueSoftness, dist);
        } else if (mode === "saturation") {
          m = softRange(sat, params.minValue, params.maxValue, params.softness);
        } else {
          m = softRange(val, params.minValue, params.maxValue, params.softness);
        }
      } else if (mode === "chroma_key") {
        const dr = r - params.targetR;
        const dg = g - params.targetG;
        const db = b - params.targetB;
        const dist = Math.sqrt((dr * dr) + (dg * dg) + (db * db)) / chromaNorm;
        m = 1 - softThreshold(dist, Math.max(0, params.colorTolerance), params.softness);
      } else {
        let v = (0.2126 * r) + (0.7152 * g) + (0.0722 * b);
        if (mode === "channel") {
          if (params.channel === "red") v = r;
          else if (params.channel === "green") v = g;
          else if (params.channel === "blue") v = b;
          else if (params.channel === "alpha") v = a;
        }
        m = softThreshold(v, params.threshold, params.softness);
      }

      mask[i] = clamp01(m);
    }
  }

  if (Math.trunc(params.expandPixels) !== 0) {
    mask = morphMask(mask, w, h, params.expandPixels);
  }
  if (params.blurRadius > 1e-3) {
    mask = boxBlurGray(mask, w, h, Math.min(params.blurRadius, 24));
  }

  const gamma = Math.max(0.1, params.maskGamma);
  const invert = !!params.invertMask;
  let sumMask = 0;
  const out = new Uint8ClampedArray(len * 4);
  const overlayR = 0.16;
  const overlayG = 0.98;
  const overlayB = 0.42;

  for (let i = 0, p = 0; i < len; i += 1, p += 4) {
    let m = clamp01(mask[i]);
    if (Math.abs(gamma - 1) > 1e-6) m = Math.pow(m, gamma);
    if (invert) m = 1 - m;
    m = clamp01(m);
    sumMask += m;

    const a = data[p + 3] / 255;
    const invA = a > 1e-6 ? (1 / a) : 0;
    const r = clamp01((data[p] / 255) * invA);
    const g = clamp01((data[p + 1] / 255) * invA);
    const b = clamp01((data[p + 2] / 255) * invA);
    const mix = m * 0.55 * a;
    out[p] = Math.round(clamp01((r * (1 - mix)) + (overlayR * mix)) * 255);
    out[p + 1] = Math.round(clamp01((g * (1 - mix)) + (overlayG * mix)) * 255);
    out[p + 2] = Math.round(clamp01((b * (1 - mix)) + (overlayB * mix)) * 255);
    out[p + 3] = Math.round(clamp01(a) * 255);
  }

  const outCanvas = document.createElement("canvas");
  outCanvas.width = w;
  outCanvas.height = h;
  const outCtx = outCanvas.getContext("2d");
  if (outCtx) {
    outCtx.putImageData(new ImageData(out, w, h), 0, 0);
  }

  return {
    canvas: outCanvas,
    coverage: (sumMask / Math.max(1, len)) * 100,
  };
}

function loadImageFromSrc(state, src, sourceSig) {
  if (state.sourceImage && state.sourceSrc === src && state.sourceSig === sourceSig && isDrawableImage(state.sourceImage)) {
    return Promise.resolve(state.sourceImage);
  }
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      state.sourceSrc = src;
      state.sourceSig = sourceSig;
      state.sourceImage = img;
      resolve(img);
    };
    img.onerror = () => resolve(null);
    if (String(src).startsWith("data:")) {
      img.src = src;
    } else {
      const joiner = src.includes("?") ? "&" : "?";
      img.src = `${src}${joiner}_mkrmasksig=${encodeURIComponent(sourceSig)}&_ts=${Date.now()}`;
    }
  });
}

async function renderLocalPreview(node, state, token) {
  if (token !== state.renderToken) return;
  state.loading = true;
  updateDomVisuals(node, state);
  queueRedraw(node);

  const source = resolveLinkedImageSource(node, "image");
  if (!source.connected) {
    if (token !== state.renderToken) return;
    state.loading = false;
    state.livePending = false;
    state.previewSrc = "";
    state.image = null;
    state.coverage = null;
    state.sourceImage = null;
    state.sourceSrc = "";
    state.sourceSig = "";
    updateDomVisuals(node, state);
    queueRedraw(node);
    return;
  }

  let sourceImage = null;
  if (source.drawable && isDrawableImage(source.drawable)) {
    sourceImage = source.drawable;
  } else if (source.src) {
    const bucket = Math.floor(Date.now() / URL_REFRESH_BUCKET_MS);
    sourceImage = await loadImageFromSrc(state, source.src, `${source.signature}|bucket=${bucket}`);
  }

  if (token !== state.renderToken) return;
  if (!sourceImage) {
    state.loading = false;
    state.livePending = false;
    state.previewSrc = "";
    state.image = null;
    state.coverage = null;
    updateDomVisuals(node, state);
    queueRedraw(node);
    return;
  }

  try {
    const params = readMaskParams(node);
    const rendered = buildLocalMaskPreview(sourceImage, params);
    if (token !== state.renderToken) return;
    state.image = rendered.canvas;
    state.previewSrc = rendered.canvas.toDataURL("image/png");
    state.coverage = Number(rendered.coverage);
  } catch (error) {
    state.previewSrc = "";
    state.image = null;
    state.coverage = null;
  }

  state.loading = false;
  state.livePending = false;
  updateDomVisuals(node, state);
  queueRedraw(node);
}

function scheduleLivePreview(node, state) {
  const source = resolveLinkedImageSource(node, "image");
  if (state.liveTimer) {
    clearTimeout(state.liveTimer);
    state.liveTimer = null;
  }
  state.widgetSig = `${widgetSignature(node)}|image=${source.signature}`;

  if (!source.connected) {
    state.loading = false;
    state.livePending = false;
    state.previewSrc = "";
    state.image = null;
    state.coverage = null;
    state.sourceImage = null;
    state.sourceSrc = "";
    state.sourceSig = "";
    updateDomVisuals(node, state);
    queueRedraw(node);
    return;
  }

  state.livePending = true;
  updateDomVisuals(node, state);
  queueRedraw(node);

  const token = (state.renderToken || 0) + 1;
  state.renderToken = token;
  state.liveTimer = setTimeout(() => {
    state.liveTimer = null;
    renderLocalPreview(node, state, token);
  }, LIVE_DEBOUNCE_MS);
}

function widgetSignature(node) {
  const widgets = Array.isArray(node?.widgets) ? node.widgets : [];
  if (!widgets.length) return "";
  const parts = [];
  for (const widget of widgets) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) continue;
    const value = widget?.value;
    parts.push(`${name}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`);
  }
  return parts.join("|");
}

function wrapWidgetCallbacks(node, state) {
  for (const widget of node.widgets || []) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) continue;
    if (widget.__mkrX1MaskWrapped) continue;
    const original = widget.callback;
    widget.callback = function wrappedCallback() {
      if (typeof original === "function") {
        original.apply(this, arguments);
      }
      updateMaskControls(node, state);
      scheduleLivePreview(node, state);
    };
    widget.__mkrX1MaskWrapped = true;
  }
}

function applyOutputMessage(node, state, message) {
  const previewInfo = message?.mask_preview?.[0] ?? message?.ui?.mask_preview?.[0] ?? null;
  const stats = message?.mask_stats?.[0] ?? message?.ui?.mask_stats?.[0] ?? null;

  if (previewInfo) loadPreviewIntoState(node, state, previewInfo);
  if (stats && Number.isFinite(Number(stats.coverage))) {
    state.coverage = Number(stats.coverage);
  }
  state.livePending = false;

  updateDomVisuals(node, state);
  queueRedraw(node);
}

function ensureCanvasHooks(node, state) {
  if (node.__mkrX1MaskCanvasAttached) return;
  node.__mkrX1MaskCanvasAttached = true;

  const originalDraw = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    ensureMaskNodeShape(this);
    if (typeof originalDraw === "function") {
      originalDraw.apply(this, arguments);
    }
    if (this.flags?.collapsed) return;
    if (isDomMounted(state)) return;
    drawCanvasPreview(this, ctx, state);
  };
}

function ensureMaskUI(node) {
  if (!node) return;
  migrateRuntime(node);
  if (node.__mkrX1MaskUIAttached) return;
  node.__mkrX1MaskUIAttached = true;
  ensureMaskNodeShape(node);

  const state = ensureState(node);
  if (typeof node.addDOMWidget === "function") {
    ensureControlsDom(node, state);
    createDomState(node, state);
  }

  updateMaskControls(node, state);
  normalizeDomWidgetStack(node, state);
  wrapWidgetCallbacks(node, state);
  state.widgetSig = `${widgetSignature(node)}|image=${resolveLinkedImageSource(node, "image").signature}`;
  ensureCanvasHooks(node, state);

  const isHiddenBackendWidget = (widget) => {
    const name = String(widget?.name || "");
    if (!name) return false;
    if (name === CONTROLS_WIDGET_NAME || name === DOM_WIDGET_NAME) return false;
    return HIDDEN_WIDGET_NAMES.includes(name) || widget?.hidden === true || widget?.type === "hidden";
  };

  if (!node.__mkrX1MaskWidgetHitPatched) {
    node.__mkrX1MaskWidgetHitPatched = true;

    const originalGetWidgetOnPos = typeof node.getWidgetOnPos === "function" ? node.getWidgetOnPos : null;
    if (originalGetWidgetOnPos) {
      node.getWidgetOnPos = function getWidgetOnPosMasked() {
        const widget = originalGetWidgetOnPos.apply(this, arguments);
        return isHiddenBackendWidget(widget) ? null : widget;
      };
    }

    const originalGetWidgetAtPos = typeof node.getWidgetAtPos === "function" ? node.getWidgetAtPos : null;
    if (originalGetWidgetAtPos) {
      node.getWidgetAtPos = function getWidgetAtPosMasked() {
        const widget = originalGetWidgetAtPos.apply(this, arguments);
        return isHiddenBackendWidget(widget) ? null : widget;
      };
    }

    const originalMouseDown = typeof node.onMouseDown === "function" ? node.onMouseDown : null;
    node.onMouseDown = function onMouseDownMasked() {
      const hitOnPos = originalGetWidgetOnPos?.apply(this, arguments);
      if (isHiddenBackendWidget(hitOnPos)) {
        return true;
      }
      const hitAtPos = originalGetWidgetAtPos?.apply(this, arguments);
      if (isHiddenBackendWidget(hitAtPos)) {
        return true;
      }
      return originalMouseDown?.apply(this, arguments) ?? false;
    };
  }

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    if (typeof originalExecuted === "function") {
      originalExecuted.apply(this, arguments);
    }
    ensureMaskNodeShape(this);
    applyOutputMessage(this, state, message || {});
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    if (typeof originalConnectionsChange === "function") {
      originalConnectionsChange.apply(this, arguments);
    }
    state.sourceImage = null;
    state.sourceSrc = "";
    state.sourceSig = "";
    updateMaskControls(this, state);
    wrapWidgetCallbacks(this, state);
    scheduleLivePreview(this, state);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    if (typeof originalConfigure === "function") {
      originalConfigure.apply(this, arguments);
    }
    ensureMaskNodeShape(this);
    updateMaskControls(this, state);
    wrapWidgetCallbacks(this, state);
    scheduleLivePreview(this, state);
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    if (typeof originalResize === "function") {
      originalResize.apply(this, arguments);
    }
    ensureMaskNodeShape(this);
    updateMaskControls(this, state);
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  if (!state.pollTimer) {
    state.pollTimer = setInterval(() => {
      ensureMaskNodeShape(node);
      const inputSig = resolveLinkedImageSource(node, "image").signature;
      const next = `${widgetSignature(node)}|image=${inputSig}`;
      if (next !== state.widgetSig) {
        state.widgetSig = next;
        scheduleLivePreview(node, state);
      }
    }, 120);
  }

  const originalRemoved = node.onRemoved;
  node.onRemoved = function onRemoved() {
    if (state.liveTimer) {
      clearTimeout(state.liveTimer);
      state.liveTimer = null;
    }
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    if (typeof originalRemoved === "function") {
      return originalRemoved.apply(this, arguments);
    }
    return undefined;
  };

  scheduleLivePreview(node, state);
}

function findNodeByLocator(locatorId) {
  const appRef = getApp();
  const graph = appRef?.graph;
  if (!graph) return null;

  const raw = String(locatorId ?? "");
  if (!raw) return null;

  const directId = Number.parseInt(raw, 10);
  if (Number.isFinite(directId)) {
    const direct = graph.getNodeById?.(directId);
    if (direct) return direct;
  }

  const tail = raw.includes(":") ? raw.split(":").pop() : raw;
  const tailId = Number.parseInt(String(tail), 10);
  if (Number.isFinite(tailId)) {
    const byTail = graph.getNodeById?.(tailId);
    if (byTail) return byTail;
  }

  const nodes = graph._nodes || [];
  for (const node of nodes) {
    if (!node) continue;
    if (String(node.id) === raw || String(node.id) === String(tail)) {
      return node;
    }
  }

  return null;
}

function attachAllKnownNodes() {
  const appRef = getApp();
  const nodes = appRef?.graph?._nodes || [];
  for (const node of nodes) {
    if (isMaskNode(node)) {
      ensureMaskUI(node);
    }
  }
}

function getLinkedInputNodeId(node, inputName) {
  const source = resolveLinkedImageSource(node, inputName);
  return source?.sourceId && source.sourceId !== "none" ? String(source.sourceId) : "";
}

function buildExtension() {
  return {
    name: EXT,

    async setup() {
      attachAllKnownNodes();
      setTimeout(attachAllKnownNodes, 1200);
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
      if (!isMaskNodeDef(nodeData)) return;
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function onNodeCreated() {
        if (typeof originalOnNodeCreated === "function") {
          originalOnNodeCreated.apply(this, arguments);
        }
        ensureMaskUI(this);
      };
    },

    async nodeCreated(node) {
      if (isMaskNode(node)) {
        ensureMaskUI(node);
        return;
      }

      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (isMaskNode(node)) {
          ensureMaskUI(node);
          clearInterval(timer);
          return;
        }
        if (tries >= 30) {
          clearInterval(timer);
        }
      }, 100);
    },

    loadedGraphNode(node) {
      if (!isMaskNode(node)) return;
      ensureMaskUI(node);
    },

    onNodeOutputsUpdated(nodeOutputs) {
      if (!nodeOutputs || typeof nodeOutputs !== "object") return;
      const allNodes = getApp()?.graph?._nodes || [];

      for (const [locatorId, output] of Object.entries(nodeOutputs)) {
        if (!output || typeof output !== "object") continue;
        const sourceNode = findNodeByLocator(locatorId);
        const sourceNodeId = sourceNode ? String(sourceNode.id ?? "") : "";
        if (sourceNodeId) {
          for (const candidate of allNodes) {
            if (!candidate || !isMaskNode(candidate)) continue;
            if (getLinkedInputNodeId(candidate, "image") !== sourceNodeId) continue;
            ensureMaskUI(candidate);
            const candidateState = ensureState(candidate);
            scheduleLivePreview(candidate, candidateState);
          }
        }

        if (!("mask_preview" in output || "mask_stats" in output || ("ui" in output))) continue;

        const node = findNodeByLocator(locatorId);
        if (!node || !isMaskNode(node)) continue;

        ensureMaskUI(node);
        const state = ensureState(node);
        applyOutputMessage(node, state, output);
      }
    },
  };
}

function registerWhenReady(tries = 0) {
  if (registered) return;

  ensureAccentStylesheet();

  const appRef = getApp();
  if (!appRef?.registerExtension) {
    if (tries < 400) {
      setTimeout(() => registerWhenReady(tries + 1), 100);
    }
    return;
  }

  appRef.registerExtension(buildExtension());
  registered = true;
}

registerWhenReady();
