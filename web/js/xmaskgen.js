import { app } from "../../../scripts/app.js";

const EXT = "mkrshift.x1maskgen.preview";
const STATE_KEY = "__mkrX1MaskState";
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
const DEFAULT_H = 520;
const PREVIEW_MIN_H = 178;
const PREVIEW_MARGIN = 8;
const LIVE_DEBOUNCE_MS = 90;
const ACCENT_LIME = "#D2FD51";
const LOCAL_PREVIEW_MAX_DIM = 360;
const URL_REFRESH_BUCKET_MS = 900;
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
  const y = Math.max(76, nodeH - PREVIEW_MIN_H - PREVIEW_MARGIN);
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
  if (!Array.isArray(node?.widgets) || !state?.domWidget) return false;
  let changed = false;

  const domWidgets = node.widgets.filter((w) => String(w?.name || "") === DOM_WIDGET_NAME);
  if (domWidgets.length > 1) {
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== DOM_WIDGET_NAME || w === state.domWidget);
    changed = true;
  }

  const idx = node.widgets.indexOf(state.domWidget);
  if (idx > -1 && idx !== node.widgets.length - 1) {
    node.widgets.splice(idx, 1);
    node.widgets.push(state.domWidget);
    changed = true;
  }
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

function getWidget(node, name) {
  return node.widgets?.find((w) => String(w?.name || "") === name);
}

function getWidgetValue(node, name, fallback) {
  const widget = getWidget(node, name);
  if (widget && widget.value !== undefined) return widget.value;
  const prop = node?.properties?.[name];
  if (prop !== undefined) return prop;
  return fallback;
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
    threshold: numberValue(getWidgetValue(node, "threshold", 0.5), 0.5),
    softness: numberValue(getWidgetValue(node, "softness", 0.08), 0.08),
    minValue: numberValue(getWidgetValue(node, "min_value", 0.2), 0.2),
    maxValue: numberValue(getWidgetValue(node, "max_value", 0.8), 0.8),
    hueCenter: numberValue(getWidgetValue(node, "hue_center", 120.0), 120.0),
    hueWidth: numberValue(getWidgetValue(node, "hue_width", 24.0), 24.0),
    targetR: numberValue(getWidgetValue(node, "target_r", 0.0), 0.0),
    targetG: numberValue(getWidgetValue(node, "target_g", 1.0), 1.0),
    targetB: numberValue(getWidgetValue(node, "target_b", 0.0), 0.0),
    colorTolerance: numberValue(getWidgetValue(node, "color_tolerance", 0.25), 0.25),
    edgeRadius: numberValue(getWidgetValue(node, "edge_radius", 1.0), 1.0),
    edgeStrength: numberValue(getWidgetValue(node, "edge_strength", 1.0), 1.0),
    centerX: numberValue(getWidgetValue(node, "center_x", 0.5), 0.5),
    centerY: numberValue(getWidgetValue(node, "center_y", 0.5), 0.5),
    radius: numberValue(getWidgetValue(node, "radius", 0.28), 0.28),
    falloff: numberValue(getWidgetValue(node, "falloff", 1.0), 1.0),
    expandPixels: numberValue(getWidgetValue(node, "expand_pixels", 0), 0),
    blurRadius: numberValue(getWidgetValue(node, "blur_radius", 0.0), 0.0),
    maskGamma: numberValue(getWidgetValue(node, "mask_gamma", 1.0), 1.0),
    invertMask: boolValue(getWidgetValue(node, "invert_mask", false), false),
  };
}

function skinToneConfidence(r, g, b, params) {
  const [hue, sat, val] = rgbToHsv(r, g, b);
  const hueCenter = 24 / 360;
  const hueHalfWidth = 28 / 360;
  const hueSoftness = Math.max(6 / 360, Math.max(0, params.softness) * 0.35);
  const hueWrapped = ((hue - hueCenter + 1.5) % 1) - 0.5;
  const hueSel = 1 - smoothstep(hueHalfWidth, hueHalfWidth + hueSoftness, Math.abs(hueWrapped));

  const satSel = softRange(sat, 0.10, 0.68, Math.max(0.05, Math.max(0, params.softness) * 1.5));
  const valSel = softRange(val, 0.18, 0.98, Math.max(0.06, Math.max(0, params.softness) * 1.25));

  const y = (0.299 * r) + (0.587 * g) + (0.114 * b);
  const cb = clamp01(((b - y) * 0.564) + 0.5);
  const cr = clamp01(((r - y) * 0.713) + 0.5);
  const cbSel = 1 - smoothstep(0.06, 0.17, Math.abs(cb - 0.43));
  const crSel = 1 - smoothstep(0.06, 0.17, Math.abs(cr - 0.56));

  const warmth = clamp01(((r - b) * 1.25) + ((r - g) * 0.35) + 0.15);
  const warmthSel = softThreshold(warmth, 0.18, Math.max(0.05, params.softness));

  const confidence = clamp01(hueSel * satSel * valSel * cbSel * crSel * warmthSel);
  return softThreshold(confidence, params.threshold, Math.max(0.04, params.softness));
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
      } else if (mode === "skin_tones") {
        m = skinToneConfidence(r, g, b, params);
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
  if (!Array.isArray(node?.widgets)) return "";
  const parts = [];
  for (const widget of node.widgets) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME) continue;
    const value = widget?.value;
    parts.push(`${name}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`);
  }
  return parts.join("|");
}

function wrapWidgetCallbacks(node, state) {
  for (const widget of node.widgets || []) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME) continue;
    if (widget.__mkrX1MaskWrapped) continue;
    const original = widget.callback;
    widget.callback = function wrappedCallback() {
      if (typeof original === "function") {
        original.apply(this, arguments);
      }
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
  node.resizable = true;

  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [DEFAULT_W, DEFAULT_H];
  }
  node.size[0] = Math.max(DEFAULT_W, Number(node.size[0] || DEFAULT_W));
  node.size[1] = Math.max(DEFAULT_H, Number(node.size[1] || DEFAULT_H));

  const state = ensureState(node);
  if (typeof node.addDOMWidget === "function") {
    createDomState(node, state);
  }

  normalizeDomWidgetStack(node, state);
  wrapWidgetCallbacks(node, state);
  state.widgetSig = `${widgetSignature(node)}|image=${resolveLinkedImageSource(node, "image").signature}`;
  ensureCanvasHooks(node, state);

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    if (typeof originalExecuted === "function") {
      originalExecuted.apply(this, arguments);
    }
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
    wrapWidgetCallbacks(this, state);
    scheduleLivePreview(this, state);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    if (typeof originalConfigure === "function") {
      originalConfigure.apply(this, arguments);
    }
    wrapWidgetCallbacks(this, state);
    scheduleLivePreview(this, state);
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    if (typeof originalResize === "function") {
      originalResize.apply(this, arguments);
    }
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  if (!state.pollTimer) {
    state.pollTimer = setInterval(() => {
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
