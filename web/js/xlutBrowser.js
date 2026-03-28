import { app } from "../../../scripts/app.js";
import { api as comfyApiModule } from "../../../scripts/api.js";
import { ensureMkrUIStyles } from "./uiSystem.js";

const EXTENSION_NAME = "mkrshift.xlut_browser";
const LUT_NONE = "None";
const SETTINGS_WIDGET_NAME = "settings_json";
const CONTROLS_WIDGET_NAME = "mkr_xlut_controls_ui";
const PREVIEW_WIDGET_NAME = "mkr_xlut_preview_ui";
const PREVIEW_MIN_H = 178;
const PREVIEW_POLL_MS = 220;
const LIVE_IMAGE_BUCKET_MS = 1500;
const ACCENT_LIME = "#D2FD51";
const DEFAULT_NODE_WIDTH = 420;
const DEFAULT_NODE_HEIGHT = 520;
const CONTROLS_HEIGHT = 198;
const LAYOUT_TOP = 76;
const LAYOUT_GAP = 8;
const LAYOUT_BOTTOM = 8;
const LEGACY_WIDGET_NAMES = [
  "lut_name",
  "strength",
  "generated_lut_size",
  "generated_style_strength",
  "apply_generated_lut",
];
const HIDDEN_WIDGET_NAMES = [SETTINGS_WIDGET_NAME, ...LEGACY_WIDGET_NAMES];
const XLUT_DEFAULT_SETTINGS = {
  lut_name: LUT_NONE,
  strength: 1,
  generated_lut_size: 33,
  generated_style_strength: 1,
  apply_generated_lut: true,
};

let activePopupState = null;
const OBJECT_IDS = new WeakMap();
let objectIdCounter = 1;

function getApi() {
  return globalThis?.api || globalThis?.comfyAPI?.api || comfyApiModule || null;
}

ensureMkrUIStyles();

function apiUrl(path) {
  const p = String(path || "");
  const apiObj = getApi();
  if (apiObj && typeof apiObj.apiURL === "function") {
    return apiObj.apiURL(p);
  }
  return p;
}

function fetchApiCompat(path, init = undefined) {
  const comfyApi = getApi();
  if (comfyApi && typeof comfyApi.fetchApi === "function") {
    return comfyApi.fetchApi(path, init);
  }
  if (comfyApiModule && typeof comfyApiModule.fetchApi === "function") {
    return comfyApiModule.fetchApi(path, init);
  }
  return fetch(path, init);
}

function objectId(value) {
  if (!value || (typeof value !== "object" && typeof value !== "function")) return "none";
  const existing = OBJECT_IDS.get(value);
  if (existing) return existing;
  const next = `obj${objectIdCounter++}`;
  OBJECT_IDS.set(value, next);
  return next;
}

function stableScalar(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "[object]";
  }
}

function hashString(value) {
  let hash = 2166136261 >>> 0;
  const text = String(value || "");
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(36);
}

function normalizeToken(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function withQueryParam(url, key, value) {
  const base = String(url || "");
  if (!base) return "";
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}${encodeURIComponent(key)}=${encodeURIComponent(String(value ?? ""))}`;
}

function toLiveImageUrl(src, signature, bucketMs = LIVE_IMAGE_BUCKET_MS) {
  let base = String(src || "").trim();
  if (!base) return "";
  if (!base.startsWith("data:") && !base.startsWith("http://") && !base.startsWith("https://")) {
    if (base.startsWith("/")) base = apiUrl(base);
  }
  if (base.startsWith("data:")) return base;
  const sigHash = hashString(signature);
  const bucket = Math.floor(Date.now() / Math.max(250, Number(bucketMs) || LIVE_IMAGE_BUCKET_MS));
  return withQueryParam(withQueryParam(base, "_mkrsig", sigHash), "_mkrt", bucket);
}

function matchesXLUTName(name) {
  const token = normalizeToken(name);
  if (!token) return false;
  if (token === "xlut" || token === "xlutmkrshift" || token === "xlutmkrshiftnodes") return true;
  return token.endsWith("xlut");
}

function isXLUTNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
  ].filter(Boolean);
  return candidates.some(matchesXLUTName);
}

function isXLUTNodeDef(nodeData) {
  const candidates = [nodeData?.name, nodeData?.display_name, nodeData?.type].filter(Boolean);
  return candidates.some(matchesXLUTName);
}

function getWidget(node, name) {
  return node?.widgets?.find((w) => String(w?.name || "") === name);
}

function parseBoolean(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const token = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(token)) return true;
    if (["false", "0", "no", "off"].includes(token)) return false;
  }
  return fallback;
}

function normalizeXLUTSettings(payload) {
  const source = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const next = { ...XLUT_DEFAULT_SETTINGS };
  next.lut_name = String(source.lut_name ?? next.lut_name).trim() || LUT_NONE;
  next.strength = Math.max(0, Math.min(1, Number.parseFloat(String(source.strength ?? next.strength)) || next.strength));
  next.generated_lut_size = Math.max(4, Math.min(64, Math.round(Number.parseFloat(String(source.generated_lut_size ?? next.generated_lut_size)) || next.generated_lut_size)));
  next.generated_style_strength = Math.max(0, Math.min(2, Number.parseFloat(String(source.generated_style_strength ?? next.generated_style_strength)) || next.generated_style_strength));
  next.apply_generated_lut = parseBoolean(source.apply_generated_lut, next.apply_generated_lut);
  return next;
}

function parseXLUTSettingsValue(rawValue) {
  const rawText = String(rawValue ?? "").trim();
  if (!rawText) return {};
  try {
    const parsed = JSON.parse(rawText);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    if (typeof parsed === "string" && parsed.trim()) {
      return { lut_name: parsed.trim() };
    }
  } catch {
    return { lut_name: rawText };
  }
  return {};
}

function serializeXLUTSettings(settings) {
  return JSON.stringify(normalizeXLUTSettings(settings));
}

function buildLegacyXLUTSettings(values) {
  if (!Array.isArray(values) || values.length < LEGACY_WIDGET_NAMES.length) return null;
  const payload = {};
  LEGACY_WIDGET_NAMES.forEach((name, index) => {
    if (values[index] !== undefined) payload[name] = values[index];
  });
  return normalizeXLUTSettings(payload);
}

function migrateLegacyXLUTWorkflow(node) {
  if (!node || node.__mkrXLUTLegacyMigrated) return;
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  if (!settingsWidget) {
    node.__mkrXLUTLegacyMigrated = true;
    return;
  }
  const legacy = buildLegacyXLUTSettings(node.widgets_values);
  if (!legacy) {
    node.__mkrXLUTLegacyMigrated = true;
    return;
  }
  const serialized = serializeXLUTSettings(legacy);
  settingsWidget.value = serialized;
  node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
  node.properties[SETTINGS_WIDGET_NAME] = serialized;
  node.widgets_values = [serialized];
  node.__mkrXLUTLegacyMigrated = true;
}

function readXLUTSettings(node) {
  migrateLegacyXLUTWorkflow(node);
  const settingsWidget = getWidget(node, SETTINGS_WIDGET_NAME);
  const raw = settingsWidget?.value ?? node?.properties?.[SETTINGS_WIDGET_NAME];
  const settings = normalizeXLUTSettings(parseXLUTSettingsValue(raw));
  const serialized = serializeXLUTSettings(settings);
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

function writeXLUTSettings(node, patch, options = {}) {
  const current = options.replace ? XLUT_DEFAULT_SETTINGS : readXLUTSettings(node);
  const next = normalizeXLUTSettings(
    options.replace
      ? (typeof patch === "string" ? parseXLUTSettingsValue(patch) : patch)
      : { ...current, ...(typeof patch === "string" ? parseXLUTSettingsValue(patch) : patch) }
  );
  const serialized = serializeXLUTSettings(next);
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
    settingsWidget.callback(serialized, app.graph, node, settingsWidget);
  }
  return next;
}

function getWidgetChoices(widget) {
  if (!widget) return [];
  if (Array.isArray(widget.options?.values)) return widget.options.values;
  if (Array.isArray(widget.values)) return widget.values;
  if (Array.isArray(widget.options)) return widget.options;
  return [];
}

function setWidgetChoices(widget, values) {
  if (!widget) return;
  const list = Array.isArray(values) ? values.map((v) => String(v)) : [];
  if (Array.isArray(widget.options?.values)) {
    widget.options.values = list;
    return;
  }
  if (Array.isArray(widget.values)) {
    widget.values = list;
    return;
  }
  if (Array.isArray(widget.options)) {
    widget.options = list;
    return;
  }
  widget.options = { ...(widget.options || {}), values: list };
}

function setWidgetValue(node, widget, value) {
  if (!widget) return;
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app.graph, node, widget);
  }
}

function getXLUTSetting(node, name, fallback) {
  const settings = readXLUTSettings(node);
  if (Object.prototype.hasOwnProperty.call(settings, name)) {
    return settings[name];
  }
  return fallback;
}

function setXLUTSetting(node, name, value) {
  writeXLUTSettings(node, { [name]: value });
  markDirty(node);
}

function setWidgetVisibility(widget, visible) {
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
    widget.element.style.boxSizing = "border-box";
    widget.element.style.overflow = "hidden";
  }
  changed = trySetWidgetY(widget, y) || changed;
  return changed;
}

function resolveXLUTControlsHeight(state) {
  const root = state?.controlsDom?.root;
  const measured = Math.ceil(Number(root?.scrollHeight || root?.getBoundingClientRect?.().height || 0));
  if (measured > 0) {
    return Math.max(CONTROLS_HEIGHT, measured + 4);
  }
  return CONTROLS_HEIGHT;
}

function markDirty(node) {
  node?.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
}

function ensureNodeShape(node) {
  if (!node) return;
  const width = DEFAULT_NODE_WIDTH;
  const height = DEFAULT_NODE_HEIGHT;
  if (!node.__mkrXLUTFixedComputeSize) {
    node.__mkrXLUTFixedComputeSize = true;
    node.__mkrXLUTOrigComputeSize = node.computeSize;
    node.computeSize = function computeFixedXLUTSize() {
      return [width, height];
    };
  }
  node.resizable = false;
  node.flags = typeof node.flags === "object" && node.flags !== null ? node.flags : {};
  node.flags.resizable = false;
  const currentWidth = Number(node.size?.[0] || 0);
  const currentHeight = Number(node.size?.[1] || 0);
  if (Math.abs(currentWidth - width) <= 0.5 && Math.abs(currentHeight - height) <= 0.5) return;
  if (node.__mkrXLUTSizing) return;
  node.__mkrXLUTSizing = true;
  try {
    node.setSize?.([width, height]);
    node.size = [width, height];
  } finally {
    node.__mkrXLUTSizing = false;
  }
}

function getLocalPos(node, event, pos) {
  if (Array.isArray(pos) && pos.length >= 2) {
    return { x: pos[0], y: pos[1] };
  }
  if (event && typeof event.canvasX === "number" && typeof event.canvasY === "number") {
    return {
      x: event.canvasX - node.pos[0],
      y: event.canvasY - node.pos[1],
    };
  }
  return null;
}

function pointInRect(point, rect) {
  if (!point || !rect) return false;
  return (
    point.x >= rect.x &&
    point.x <= rect.x + rect.w &&
    point.y >= rect.y &&
    point.y <= rect.y + rect.h
  );
}

function estimateWidgetY(node, targetWidget) {
  const widgets = Array.isArray(node?.widgets) ? node.widgets : [];
  if (!widgets.length || !targetWidget) return NaN;
  let y = Number.isFinite(node?.widgets_start_y) ? Number(node.widgets_start_y) : 24;
  for (const widget of widgets) {
    if (!widget || widget.hidden) continue;
    const h = Number.isFinite(widget?.computedHeight) ? Number(widget.computedHeight) : 24;
    if (widget === targetWidget) {
      return y;
    }
    y += Math.max(20, Math.min(40, h)) + 4;
  }
  return NaN;
}

function widgetRect(node, widget) {
  if (!node || !widget) return null;
  const yRaw = Number.isFinite(widget?.last_y)
    ? Number(widget.last_y)
    : Number.isFinite(widget?.y)
      ? Number(widget.y)
      : estimateWidgetY(node, widget);
  if (!Number.isFinite(yRaw)) return null;

  const hRaw = Number.isFinite(widget?.computedHeight) ? Number(widget.computedHeight) : 24;
  const h = Math.max(20, Math.min(40, hRaw));
  const w = Math.max(80, Math.round((Number(node?.size?.[0]) || 280) - 20));
  const x = 10;
  return { x, y: yRaw, w, h };
}

function selectedLutValue(node) {
  return String(getXLUTSetting(node, "lut_name", LUT_NONE));
}

function inputIsConnected(node, inputName) {
  const input = node?.inputs?.find((entry) => String(entry?.name || "") === String(inputName || ""));
  return readInputLinkIds(input).length > 0;
}

function syncXLUTWidgetVisibility(node) {
  if (!node) return false;
  let changed = false;
  for (const widget of node.widgets || []) {
    const name = String(widget?.name || "");
    if (!name || name === PREVIEW_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) continue;
    changed = setWidgetVisibility(widget, false) || changed;
  }

  if (changed) {
    markDirty(node);
  }
  return changed;
}

function buildCatalogUrl(folder) {
  const clean = String(folder ?? "").trim();
  if (!clean) return "/mkrshift_lut/list";
  return `/mkrshift_lut/list?folder=${encodeURIComponent(clean)}`;
}

async function fetchCatalog(folder) {
  const response = await fetchApiCompat(buildCatalogUrl(folder));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function sourceNodeWidgetSignature(sourceNode) {
  const widgets = sourceNode?.widgets;
  if (!Array.isArray(widgets) || widgets.length === 0) return "none";
  const parts = [];
  for (const widget of widgets) {
    const name = String(widget?.name || "").trim();
    if (!name) continue;
    if (name === PREVIEW_WIDGET_NAME) continue;
    parts.push(`${name}=${stableScalar(widget?.value)}`);
  }
  return parts.length ? parts.join("|") : "none";
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

  const likelyImageLoader = typeToken.includes("loadimage") || (typeToken.includes("load") && typeToken.includes("image"));
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

function resolveLinkedImageSource(node, inputName) {
  const index = node.inputs?.findIndex((entry) => String(entry?.name || "") === inputName) ?? -1;
  if (index < 0) {
    return { connected: false, src: "", drawable: null, signature: "none" };
  }

  const input = node.inputs?.[index];
  const links = readInputLinkIds(input);
  const linkSig = links.length ? links.join(",") : "none";

  const graph = node?.graph || app?.graph || null;
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

  const sourceId = sourceNode ? String(sourceNode.id ?? "none") : (sourceIdFromLinks || "none");
  const sourceWidgetSig = sourceNodeWidgetSignature(sourceNode);

  let src = "";
  let drawable = null;
  const samples = Array.isArray(sourceNode?.imgs) ? sourceNode.imgs : [];
  const sample = samples.length ? samples[0] : null;
  if (sample instanceof HTMLImageElement) {
    src = sample.currentSrc || sample.src || "";
    drawable = sample;
  } else if (typeof HTMLCanvasElement !== "undefined" && sample instanceof HTMLCanvasElement) {
    drawable = sample;
  } else if (sample && typeof sample === "object") {
    if (typeof sample.src === "string") src = sample.src;
    if (!src && sample.image instanceof HTMLImageElement) {
      src = sample.image.currentSrc || sample.image.src || "";
    }
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
    drawMeta = `${objectId(drawable)}:${dw}x${dh}:${dsrc}`;
  }
  const connected = linkSig !== "none" || !!sourceNode || sourceId !== "none";
  const signature = `link=${linkSig}|source=${sourceId}|wsig=${sourceWidgetSig}|draw=${drawMeta}|src=${src || "none"}`;
  return { connected, src, drawable, signature };
}

function makeState(node) {
  if (node.__mkrXLUTBrowserState) return node.__mkrXLUTBrowserState;
  const state = {
    node,
    folder: "",
    folders: [],
    entries: [],
    catalogStamp: 0,
    requestNonce: 0,
    loadedOnce: false,

    popupRoot: null,
    folderSelect: null,
    statusEl: null,
    listEl: null,

    previewDom: null,
    previewWidget: null,
    controlsDom: null,
    controlsWidget: null,
    previewTimer: null,
    previewSplit: 0.5,
    lastPreviewSig: "",

    teardown: [],
  };
  node.__mkrXLUTBrowserState = state;
  return state;
}

function hideXLUTWidgets(node) {
  let changed = false;
  for (const name of HIDDEN_WIDGET_NAMES) {
    changed = setWidgetVisibility(getWidget(node, name), false) || changed;
  }
  if (changed) markDirty(node);
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

function createRowLabel(text) {
  const label = document.createElement("div");
  label.style.cssText = "font:600 11px sans-serif;color:rgba(229,235,242,0.82);";
  label.textContent = text;
  return label;
}

function createNumber(value, min, max, step) {
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

function createRangeRow({ label, min, max, step, value, decimals = 2, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:88px 1fr 64px;gap:8px;align-items:center;";
  row.appendChild(createRowLabel(label));

  const range = document.createElement("input");
  range.type = "range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);
  range.value = String(value);
  range.style.cssText = `width:100%;accent-color:${ACCENT_LIME};`;

  const number = createNumber(Number(value).toFixed(decimals), min, max, step);
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
      const normalized = Number(next) || 0;
      range.value = String(normalized);
      number.value = normalized.toFixed(decimals);
    },
    setVisible(visible) {
      row.style.display = visible ? "grid" : "none";
    },
  };
}

function createToggleRow({ label, checked, onChange }) {
  const row = document.createElement("label");
  row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;";
  row.appendChild(createRowLabel(label));
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
    setVisible(visible) {
      row.style.display = visible ? "flex" : "none";
    },
  };
}

function ensureControlsWidget(node, state) {
  const controlsReady =
    !!state.controlsDom &&
    !!state.controlsWidget &&
    !!state.previewDom &&
    Array.isArray(node?.widgets) &&
    node.widgets.includes(state.controlsWidget);
  if (controlsReady) return;
  state.controlsDom = null;
  state.controlsWidget = null;
  state.previewDom = null;
  state.previewWidget = null;

  const root = document.createElement("div");
  root.className = "mkr-seamless-panel";

  const settings = readXLUTSettings(node);

  const selectRow = document.createElement("div");
  selectRow.style.cssText = "display:grid;grid-template-columns:88px 1fr auto;gap:8px;align-items:center;margin-bottom:8px;";
  selectRow.appendChild(createRowLabel("LUT"));
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
  const browseButton = document.createElement("button");
  browseButton.type = "button";
  browseButton.textContent = "Browse";
  browseButton.style.cssText = [
    "padding:7px 10px",
    "border-radius:9px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:rgba(9,10,13,0.48)",
    "color:rgba(245,248,252,0.92)",
    "font:600 11px sans-serif",
    "cursor:pointer",
  ].join(";");
  selectRow.appendChild(select);
  selectRow.appendChild(browseButton);
  root.appendChild(selectRow);

  const controls = document.createElement("div");
  controls.style.cssText = "display:grid;gap:8px;";
  const strength = createRangeRow({
    label: "Strength",
    min: 0,
    max: 1,
    step: 0.01,
    value: settings.strength ?? 1,
    onChange: (value) => setXLUTSetting(node, "strength", value),
  });
  const size = createRangeRow({
    label: "Gen Size",
    min: 4,
    max: 64,
    step: 1,
    value: settings.generated_lut_size ?? 33,
    decimals: 0,
    onChange: (value) => setXLUTSetting(node, "generated_lut_size", Math.round(value)),
  });
  const styleStrength = createRangeRow({
    label: "Style",
    min: 0,
    max: 2,
    step: 0.01,
    value: settings.generated_style_strength ?? 1,
    onChange: (value) => setXLUTSetting(node, "generated_style_strength", value),
  });
  const applyToggle = createToggleRow({
    label: "Apply Gen",
    checked: !!settings.apply_generated_lut,
    onChange: (checked) => setXLUTSetting(node, "apply_generated_lut", checked),
  });
  controls.appendChild(strength.element);
  controls.appendChild(size.element);
  controls.appendChild(styleStrength.element);
  controls.appendChild(applyToggle.element);
  root.appendChild(controls);

  const previewRoot = document.createElement("div");
  previewRoot.style.cssText = [
    "position:relative",
    "flex:1 1 auto",
    `min-height:${PREVIEW_MIN_H}px`,
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
    "background-image:linear-gradient(45deg, rgba(44,44,44,0.5) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.5) 75%, rgba(44,44,44,0.5)),linear-gradient(45deg, rgba(44,44,44,0.5) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.5) 75%, rgba(44,44,44,0.5))",
    "background-position:0 0, 8px 8px",
    "background-size:16px 16px",
  ].join(";");

  const imageB = document.createElement("img");
  imageB.alt = "LUT";
  imageB.draggable = false;
  imageB.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:cover",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const clip = document.createElement("div");
  clip.style.cssText = [
    "position:absolute",
    "inset:0",
    "overflow:hidden",
    "pointer-events:none",
  ].join(";");

  const imageA = document.createElement("img");
  imageA.alt = "Input";
  imageA.draggable = false;
  imageA.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:cover",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const line = document.createElement("div");
  line.style.cssText = [
    "position:absolute",
    "background:rgba(255,255,255,0.95)",
    "z-index:6",
    "pointer-events:none",
    "display:none",
  ].join(";");

  const handle = document.createElement("div");
  handle.style.cssText = [
    "position:absolute",
    "width:12px",
    "height:12px",
    "border-radius:999px",
    "border:2px solid rgba(12,16,22,0.55)",
    "background:var(--mkr-accent-lime, #D2FD51)",
    "box-shadow:0 0 0 1px rgba(9,13,20,0.22)",
    "box-sizing:border-box",
    "z-index:7",
    "pointer-events:none",
    "transform:translate(-50%, -50%)",
    "display:none",
  ].join(";");

  const badgeA = document.createElement("div");
  badgeA.textContent = "IN";
  badgeA.style.cssText = [
    "position:absolute",
    "top:8px",
    "left:8px",
    "padding:0 7px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
    "display:none",
  ].join(";");

  const badgeB = document.createElement("div");
  badgeB.textContent = "LUT";
  badgeB.style.cssText = [
    "position:absolute",
    "top:8px",
    "right:8px",
    "padding:0 7px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
    "display:none",
  ].join(";");

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
  status.textContent = "Select a LUT or connect an image";

  clip.appendChild(imageA);
  previewRoot.appendChild(checker);
  previewRoot.appendChild(imageB);
  previewRoot.appendChild(clip);
  previewRoot.appendChild(line);
  previewRoot.appendChild(handle);
  previewRoot.appendChild(badgeA);
  previewRoot.appendChild(badgeB);
  previewRoot.appendChild(status);
  root.appendChild(previewRoot);

  state.previewDom = { root: previewRoot, imageA, imageB, clip, line, handle, badgeA, badgeB, status };

  const splitFromEvent = (event) => {
    const rect = previewRoot.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const raw = (event.clientX - rect.left) / rect.width;
    const split = Math.max(0.02, Math.min(0.98, Number(raw) || 0.5));
    state.previewSplit = Number(split.toFixed(3));
    setSplitVisuals(state.previewDom, state.previewSplit);
    markDirty(node);
  };

  let dragging = false;
  previewRoot.addEventListener("pointerdown", (event) => {
    dragging = true;
    previewRoot.setPointerCapture?.(event.pointerId);
    splitFromEvent(event);
    event.preventDefault();
  });
  previewRoot.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    splitFromEvent(event);
    event.preventDefault();
  });
  const stopDrag = (event) => {
    dragging = false;
    previewRoot.releasePointerCapture?.(event.pointerId);
  };
  previewRoot.addEventListener("pointerup", stopDrag);
  previewRoot.addEventListener("pointercancel", stopDrag);
  previewRoot.addEventListener("pointerleave", () => {
    dragging = false;
  });

  setSplitVisuals(state.previewDom, state.previewSplit);

  select.addEventListener("change", () => {
    setXLUTSetting(node, "lut_name", select.value);
    updateXLUTControls(node, state);
    refreshBottomPreview(node, state, true);
  });

  browseButton.addEventListener("click", (event) => {
    openPopup(node, state, event);
  });

  const widget = node.addDOMWidget?.(CONTROLS_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => 176,
    getMaxHeight: () => 220,
  });
  if (widget) widget.serialize = false;

  state.controlsWidget = widget;
  state.controlsDom = {
    root,
    select,
    browseButton,
    strength,
    size,
    styleStrength,
    applyToggle,
  };
}

function updateXLUTControls(node, state) {
  ensureNodeShape(node);
  hideXLUTWidgets(node);
  removeGeneratedInputs(node, HIDDEN_WIDGET_NAMES);
  ensureControlsWidget(node, state);
  const dom = state.controlsDom;
  if (!dom) return;

  const settings = readXLUTSettings(node);
  const current = String(settings.lut_name ?? LUT_NONE);
  const choices = [LUT_NONE, ...state.entries.map((entry) => String(entry?.label || "")).filter(Boolean)];
  if (!choices.includes(current) && current && current !== LUT_NONE) {
    choices.push(current);
  }
  if (
    dom.select.options.length !== choices.length ||
    choices.some((choice, index) => dom.select.options[index]?.value !== String(choice))
  ) {
    dom.select.innerHTML = "";
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = String(choice);
      option.textContent = String(choice);
      dom.select.appendChild(option);
    }
  }
  dom.select.value = current;
  dom.strength.setValue(settings.strength ?? 1);
  dom.size.setValue(settings.generated_lut_size ?? 33);
  dom.styleStrength.setValue(settings.generated_style_strength ?? 1);
  dom.applyToggle.setValue(!!settings.apply_generated_lut);

  const isGenerated = current === LUT_NONE;
  const hasLutImage = inputIsConnected(node, "lut_image");
  dom.size.setVisible(isGenerated);
  dom.styleStrength.setVisible(isGenerated);
  dom.applyToggle.setVisible(isGenerated && hasLutImage);
  normalizePreviewWidgetStack(node, state);
}

function closePopup(state) {
  if (!state?.popupRoot) return;
  state.popupRoot.style.display = "none";
  if (activePopupState === state) activePopupState = null;
}

function clampPopupPosition(root, x, y) {
  const margin = 12;
  const vw = Math.max(200, window.innerWidth || 0);
  const vh = Math.max(200, window.innerHeight || 0);
  const rect = root.getBoundingClientRect();

  let left = Number(x) || margin;
  let top = Number(y) || margin;

  if (left + rect.width > vw - margin) {
    left = Math.max(margin, vw - rect.width - margin);
  }
  if (top + rect.height > vh - margin) {
    top = Math.max(margin, vh - rect.height - margin);
  }

  root.style.left = `${Math.round(left)}px`;
  root.style.top = `${Math.round(top)}px`;
}

function ensurePopup(node, state) {
  if (state.popupRoot) return;

  const root = document.createElement("div");
  root.style.position = "fixed";
  root.style.left = "40px";
  root.style.top = "40px";
  root.style.width = "min(92vw, 640px)";
  root.style.maxHeight = "82vh";
  root.style.display = "none";
  root.style.zIndex = "99999";
  root.style.padding = "8px";
  root.style.borderRadius = "12px";
  root.style.border = "1px solid #6f8897";
  root.style.background = "linear-gradient(180deg, #dce8f0 0%, #c5d8e4 100%)";
  root.style.boxShadow = "0 18px 42px rgba(9,24,35,0.34)";

  const header = document.createElement("div");
  header.style.display = "grid";
  header.style.gridTemplateColumns = "1fr auto auto";
  header.style.gap = "6px";
  header.style.alignItems = "center";

  const folderSelect = document.createElement("select");
  folderSelect.style.padding = "6px 8px";
  folderSelect.style.borderRadius = "7px";
  folderSelect.style.border = "1px solid #5d7788";
  folderSelect.style.background = "#f8fcff";
  folderSelect.style.font = "600 11px 'Avenir Next', 'Segoe UI', sans-serif";

  const refreshButton = document.createElement("button");
  refreshButton.type = "button";
  refreshButton.textContent = "Refresh";
  refreshButton.style.padding = "6px 10px";
  refreshButton.style.borderRadius = "7px";
  refreshButton.style.border = "1px solid #4b6778";
  refreshButton.style.background = "#204b63";
  refreshButton.style.color = "#f8fcff";
  refreshButton.style.cursor = "pointer";
  refreshButton.style.font = "600 11px 'Avenir Next', 'Segoe UI', sans-serif";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.textContent = "Close";
  closeButton.style.padding = "6px 10px";
  closeButton.style.borderRadius = "7px";
  closeButton.style.border = "1px solid #4b6778";
  closeButton.style.background = "#ffffff";
  closeButton.style.color = "#234355";
  closeButton.style.cursor = "pointer";
  closeButton.style.font = "600 11px 'Avenir Next', 'Segoe UI', sans-serif";

  header.appendChild(folderSelect);
  header.appendChild(refreshButton);
  header.appendChild(closeButton);
  root.appendChild(header);

  const statusEl = document.createElement("div");
  statusEl.style.font = "600 10px 'Avenir Next', 'Segoe UI', sans-serif";
  statusEl.style.color = "#294455";
  statusEl.style.padding = "4px 1px";
  statusEl.textContent = "Loading LUTs...";
  root.appendChild(statusEl);

  const list = document.createElement("div");
  list.style.display = "grid";
  list.style.gridTemplateColumns = "repeat(2, minmax(0, 1fr))";
  list.style.gap = "8px";
  list.style.maxHeight = "62vh";
  list.style.overflow = "auto";
  list.style.padding = "2px";
  root.appendChild(list);

  root.addEventListener("mousedown", (event) => {
    event.stopPropagation();
  });

  const onDocMouseDown = (event) => {
    if (!state.popupRoot || state.popupRoot.style.display === "none") return;
    if (state.popupRoot.contains(event.target)) return;
    closePopup(state);
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape" && activePopupState === state) {
      closePopup(state);
    }
  };

  document.addEventListener("mousedown", onDocMouseDown, true);
  document.addEventListener("keydown", onKeyDown, true);

  state.teardown.push(() => {
    document.removeEventListener("mousedown", onDocMouseDown, true);
    document.removeEventListener("keydown", onKeyDown, true);
  });

  folderSelect.onchange = () => {
    state.folder = String(folderSelect.value || "");
    loadCatalog(node, state, true);
  };

  refreshButton.onclick = () => {
    loadCatalog(node, state, true);
  };

  closeButton.onclick = () => closePopup(state);

  document.body.appendChild(root);
  state.popupRoot = root;
  state.folderSelect = folderSelect;
  state.statusEl = statusEl;
  state.listEl = list;
}

function renderCard(node, state, entry, selected) {
  const button = document.createElement("button");
  button.type = "button";
  button.style.display = "grid";
  button.style.gridTemplateColumns = "104px 1fr";
  button.style.gap = "8px";
  button.style.alignItems = "center";
  button.style.padding = "7px";
  button.style.borderRadius = "10px";
  button.style.border = selected ? "2px solid #de7a41" : "1px solid #587689";
  button.style.background = selected
    ? "linear-gradient(180deg, #fff2e7 0%, #ffe3cc 100%)"
    : "linear-gradient(180deg, #f7fbff 0%, #e6eff6 100%)";
  button.style.cursor = "pointer";
  button.style.textAlign = "left";

  const thumb = document.createElement("img");
  const srcRaw = String(entry.preview_url || "");
  thumb.src = srcRaw
    ? withQueryParam(apiUrl(srcRaw), "_mkrcatalog", String(state.catalogStamp || Date.now()))
    : "";
  thumb.loading = "eager";
  thumb.decoding = "async";
  thumb.style.width = "104px";
  thumb.style.height = "58px";
  thumb.style.objectFit = "cover";
  thumb.style.borderRadius = "7px";
  thumb.style.border = "1px solid rgba(49,80,98,0.32)";
  thumb.onload = () => {
    thumb.style.display = "block";
    placeholder.style.display = "none";
  };
  thumb.onerror = () => {
    thumb.style.display = "none";
    placeholder.style.display = "grid";
  };

  const placeholder = document.createElement("div");
  placeholder.style.display = "none";
  placeholder.style.width = "104px";
  placeholder.style.height = "58px";
  placeholder.style.placeItems = "center";
  placeholder.style.borderRadius = "7px";
  placeholder.style.border = "1px solid rgba(49,80,98,0.32)";
  placeholder.style.background = "linear-gradient(135deg, #8ba9ba 0%, #b4cad7 100%)";
  placeholder.style.color = "#294455";
  placeholder.style.font = "600 10px 'Avenir Next', 'Segoe UI', sans-serif";
  placeholder.textContent = "No Preview";
  if (!thumb.src) {
    thumb.style.display = "none";
    placeholder.style.display = "grid";
  }

  const right = document.createElement("div");
  right.style.display = "flex";
  right.style.flexDirection = "column";
  right.style.gap = "3px";

  const name = document.createElement("div");
  name.textContent = String(entry.name || entry.label || "");
  name.style.font = "700 11px 'Avenir Next', 'Segoe UI', sans-serif";
  name.style.color = "#1d3342";
  name.style.lineHeight = "1.2";
  name.style.wordBreak = "break-word";

  const folder = document.createElement("div");
  folder.textContent = String(entry.folder || "root");
  folder.style.font = "500 10px 'Avenir Next', 'Segoe UI', sans-serif";
  folder.style.color = "#496071";
  folder.style.lineHeight = "1.2";

  right.appendChild(name);
  right.appendChild(folder);

  const thumbWrap = document.createElement("div");
  thumbWrap.style.position = "relative";
  thumbWrap.appendChild(thumb);
  thumbWrap.appendChild(placeholder);

  button.appendChild(thumbWrap);
  button.appendChild(right);

  button.onclick = () => {
    const label = String(entry.label || LUT_NONE);
    setXLUTSetting(node, "lut_name", label);
    updateXLUTControls(node, state);
    refreshBottomPreview(node, state, true);
    closePopup(state);
  };

  return button;
}

function renderList(node, state) {
  const listEl = state.listEl;
  if (!listEl) return;

  const selected = selectedLutValue(node);
  listEl.innerHTML = "";

  const noneBtn = document.createElement("button");
  noneBtn.type = "button";
  noneBtn.textContent = "None (Bypass LUT)";
  noneBtn.style.padding = "9px 10px";
  noneBtn.style.borderRadius = "8px";
  noneBtn.style.border = selected === LUT_NONE ? "2px solid #de7a41" : "1px solid #587689";
  noneBtn.style.background = selected === LUT_NONE
    ? "linear-gradient(180deg, #fff2e7 0%, #ffe3cc 100%)"
    : "linear-gradient(180deg, #f7fbff 0%, #e6eff6 100%)";
  noneBtn.style.font = "700 11px 'Avenir Next', 'Segoe UI', sans-serif";
  noneBtn.style.color = "#1d3342";
  noneBtn.style.cursor = "pointer";
  noneBtn.style.gridColumn = "1 / -1";
  noneBtn.onclick = () => {
    setXLUTSetting(node, "lut_name", LUT_NONE);
    updateXLUTControls(node, state);
    refreshBottomPreview(node, state, true);
    closePopup(state);
  };
  listEl.appendChild(noneBtn);

  for (const entry of state.entries) {
    const label = String(entry.label || "");
    const card = renderCard(node, state, entry, selected === label);
    listEl.appendChild(card);
  }
}

async function loadCatalog(node, state, force = false) {
  const statusEl = state.statusEl;
  const folderSelect = state.folderSelect;
  if (statusEl) {
    statusEl.textContent = force ? "Refreshing LUTs..." : "Loading LUTs...";
  }

  const nonce = ++state.requestNonce;
  try {
    const payload = await fetchCatalog(state.folder);
    if (nonce !== state.requestNonce) return;

    state.folders = Array.isArray(payload?.folders) ? payload.folders.map((f) => String(f || "")) : [];
    state.entries = Array.isArray(payload?.entries) ? payload.entries : [];
    state.folder = String(payload?.selected_folder || "");
    state.catalogStamp = Date.now();
    state.loadedOnce = true;

    if (folderSelect) {
      const options = [""].concat(state.folders.filter((f) => f));
      folderSelect.innerHTML = "";
      for (const folder of options) {
        const option = document.createElement("option");
        option.value = folder;
        option.textContent = folder || "All folders";
        folderSelect.appendChild(option);
      }
      folderSelect.value = state.folder;
    }

    if (statusEl) {
      statusEl.textContent = `LUTs: ${state.entries.length} shown`;
    }

    renderList(node, state);
    updateXLUTControls(node, state);
    refreshBottomPreview(node, state, true);
    markDirty(node);
  } catch (error) {
    if (statusEl) {
      statusEl.textContent = "Failed to load LUT catalog";
    }
    console.warn("[mkrshift.xlut] LUT catalog fetch failed:", error);
  }
}

function openPopup(node, state, event) {
  ensurePopup(node, state);
  if (activePopupState && activePopupState !== state) {
    closePopup(activePopupState);
  }
  activePopupState = state;

  const root = state.popupRoot;
  if (!root) return;
  root.style.display = "block";

  const x = Number(event?.clientX ?? event?.x ?? 48);
  const y = Number(event?.clientY ?? event?.y ?? 48);
  clampPopupPosition(root, x + 6, y + 10);

  if (!state.loadedOnce) {
    loadCatalog(node, state, false);
  } else {
    renderList(node, state);
    if ((Date.now() - Number(state.catalogStamp || 0)) > 10000) {
      loadCatalog(node, state, false);
    }
  }
}

function setSplitVisuals(dom, split) {
  const s = Math.max(0.02, Math.min(0.98, Number(split) || 0.5));
  dom.clip.style.clipPath = `inset(0 ${100 - Math.round(s * 100)}% 0 0)`;
  dom.line.style.left = `${Math.round(s * 100)}%`;
  dom.line.style.top = "0";
  dom.line.style.width = "2px";
  dom.line.style.height = "100%";
  dom.handle.style.left = `${Math.round(s * 100)}%`;
  dom.handle.style.top = "50%";
}

function setImageElSrc(imageEl, src) {
  const next = String(src || "");
  if (!imageEl) return;
  if (String(imageEl.src || "") === next) return;
  imageEl.src = next;
}

function ensureBottomPreviewWidget(node, state) {
  if (state.previewDom && !state.previewWidget) return;
  const previewReady =
    !!state.previewDom &&
    !!state.previewWidget &&
    Array.isArray(node?.widgets) &&
    node.widgets.includes(state.previewWidget);
  if (previewReady) return;
  state.previewDom = null;
  state.previewWidget = null;

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
    "background-image:linear-gradient(45deg, rgba(44,44,44,0.5) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.5) 75%, rgba(44,44,44,0.5)),linear-gradient(45deg, rgba(44,44,44,0.5) 25%, transparent 25%, transparent 75%, rgba(44,44,44,0.5) 75%, rgba(44,44,44,0.5))",
    "background-position:0 0, 8px 8px",
    "background-size:16px 16px",
  ].join(";");

  const imageB = document.createElement("img");
  imageB.alt = "LUT";
  imageB.draggable = false;
  imageB.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:cover",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const clip = document.createElement("div");
  clip.style.cssText = [
    "position:absolute",
    "inset:0",
    "overflow:hidden",
    "pointer-events:none",
  ].join(";");

  const imageA = document.createElement("img");
  imageA.alt = "Input";
  imageA.draggable = false;
  imageA.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:cover",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const line = document.createElement("div");
  line.style.cssText = [
    "position:absolute",
    "background:rgba(255,255,255,0.95)",
    "z-index:6",
    "pointer-events:none",
    "display:none",
  ].join(";");

  const handle = document.createElement("div");
  handle.style.cssText = [
    "position:absolute",
    "width:12px",
    "height:12px",
    "border-radius:999px",
    "border:2px solid rgba(12,16,22,0.55)",
    "background:var(--mkr-accent-lime, #D2FD51)",
    "box-shadow:0 0 0 1px rgba(9,13,20,0.22)",
    "box-sizing:border-box",
    "z-index:7",
    "pointer-events:none",
    "transform:translate(-50%, -50%)",
    "display:none",
  ].join(";");

  const badgeA = document.createElement("div");
  badgeA.textContent = "IN";
  badgeA.style.cssText = [
    "position:absolute",
    "top:8px",
    "left:8px",
    "padding:0 7px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
    "display:none",
  ].join(";");

  const badgeB = document.createElement("div");
  badgeB.textContent = "LUT";
  badgeB.style.cssText = [
    "position:absolute",
    "top:8px",
    "right:8px",
    "padding:0 7px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
    "display:none",
  ].join(";");

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

  clip.appendChild(imageA);
  root.appendChild(checker);
  root.appendChild(imageB);
  root.appendChild(clip);
  root.appendChild(line);
  root.appendChild(handle);
  root.appendChild(badgeA);
  root.appendChild(badgeB);
  root.appendChild(status);

  const widget = node.addDOMWidget?.(PREVIEW_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => PREVIEW_MIN_H,
    getMaxHeight: () => Number.POSITIVE_INFINITY,
  });

  if (widget) {
    widget.serialize = false;
    state.previewWidget = widget;
  }

  state.previewDom = { root, imageA, imageB, clip, line, handle, badgeA, badgeB, status };
  const splitFromEvent = (event) => {
    const rect = root.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const raw = (event.clientX - rect.left) / rect.width;
    const split = Math.max(0.02, Math.min(0.98, Number(raw) || 0.5));
    state.previewSplit = Number(split.toFixed(3));
    setSplitVisuals(state.previewDom, state.previewSplit);
    markDirty(node);
  };

  let dragging = false;
  root.addEventListener("pointerdown", (event) => {
    dragging = true;
    root.setPointerCapture?.(event.pointerId);
    splitFromEvent(event);
    event.preventDefault();
  });
  root.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    splitFromEvent(event);
    event.preventDefault();
  });
  const stopDrag = (event) => {
    dragging = false;
    root.releasePointerCapture?.(event.pointerId);
  };
  root.addEventListener("pointerup", stopDrag);
  root.addEventListener("pointercancel", stopDrag);
  root.addEventListener("pointerleave", () => {
    dragging = false;
  });

  setSplitVisuals(state.previewDom, state.previewSplit);
}

function normalizePreviewWidgetStack(node, state) {
  if (!Array.isArray(node?.widgets)) return false;
  let changed = false;

  const controlWidgets = node.widgets.filter((w) => String(w?.name || "") === CONTROLS_WIDGET_NAME);
  if (controlWidgets.length > 1 && state?.controlsWidget) {
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== CONTROLS_WIDGET_NAME || w === state.controlsWidget);
    changed = true;
  }

  if (state?.previewWidget) {
    const domWidgets = node.widgets.filter((w) => String(w?.name || "") === PREVIEW_WIDGET_NAME);
    if (domWidgets.length > 1) {
      node.widgets = node.widgets.filter((w) => String(w?.name || "") !== PREVIEW_WIDGET_NAME || w === state.previewWidget);
      changed = true;
    }
  } else {
    const before = node.widgets.length;
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== PREVIEW_WIDGET_NAME);
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

  if (state?.previewWidget) {
    const previewIndex = node.widgets.indexOf(state.previewWidget);
    const targetIndex = state?.controlsWidget ? 1 : 0;
    if (previewIndex > -1 && previewIndex !== targetIndex) {
      const [previewWidget] = node.widgets.splice(previewIndex, 1);
      node.widgets.splice(targetIndex, 0, previewWidget);
      changed = true;
    }
  }

  if (state?.controlsWidget) {
    const innerWidth = Math.max(220, DEFAULT_NODE_WIDTH - 20);
    const nodeHeight = DEFAULT_NODE_HEIGHT;
    if (state?.previewWidget) {
      const controlsHeight = resolveXLUTControlsHeight(state);
      const previewY = LAYOUT_TOP + controlsHeight + LAYOUT_GAP;
      const previewHeight = Math.max(PREVIEW_MIN_H, nodeHeight - previewY - LAYOUT_BOTTOM);
      changed = applyWidgetBox(state.controlsWidget, innerWidth, controlsHeight, LAYOUT_TOP) || changed;
      changed = applyWidgetBox(state.previewWidget, innerWidth, previewHeight, previewY) || changed;
    } else {
      const panelHeight = Math.max(PREVIEW_MIN_H + 120, nodeHeight - LAYOUT_TOP - LAYOUT_BOTTOM);
      changed = applyWidgetBox(state.controlsWidget, innerWidth, panelHeight, LAYOUT_TOP) || changed;
    }
  }
  return changed;
}

function refreshBottomPreview(node, state, force = false) {
  ensureNodeShape(node);
  ensureControlsWidget(node, state);
  ensureBottomPreviewWidget(node, state);
  if (!state.previewDom) return;
  const stackChanged = normalizePreviewWidgetStack(node, state);

  const selected = selectedLutValue(node);
  const source = resolveLinkedImageSource(node, "image");
  const hasLut = selected && selected !== LUT_NONE;
  const lutSrc = hasLut
    ? apiUrl(`/mkrshift_lut/preview?label=${encodeURIComponent(selected)}&r=${Math.floor(Date.now() / 1200)}`)
    : "";
  let inputSrc = source.connected ? toLiveImageUrl(source.src, source.signature) : "";
  if (!inputSrc && source.drawable) {
    if (source.drawable instanceof HTMLImageElement) {
      inputSrc = source.drawable.currentSrc || source.drawable.src || "";
    } else if (typeof HTMLCanvasElement !== "undefined" && source.drawable instanceof HTMLCanvasElement) {
      try {
        inputSrc = source.drawable.toDataURL("image/png");
      } catch {
        inputSrc = "";
      }
    }
  }
  const liveBucket = inputSrc ? Math.floor(Date.now() / LIVE_IMAGE_BUCKET_MS) : 0;

  const sig = `${selected}|${source.signature}|${hasLut ? "lut" : "none"}|b=${liveBucket}`;
  if (!force && !stackChanged && sig === state.lastPreviewSig) return;
  state.lastPreviewSig = sig;

  const dom = state.previewDom;
  const haveInput = !!inputSrc;
  const haveLutPreview = !!lutSrc;

  if (haveInput && haveLutPreview) {
    setImageElSrc(dom.imageA, inputSrc);
    setImageElSrc(dom.imageB, lutSrc);
    dom.imageA.style.display = "block";
    dom.imageB.style.display = "block";
    dom.clip.style.display = "block";
    dom.line.style.display = "block";
    dom.handle.style.display = "block";
    dom.badgeA.style.display = "flex";
    dom.badgeB.style.display = "flex";
    dom.status.style.display = "none";
    dom.status.textContent = "";
    setSplitVisuals(dom, state.previewSplit);
    return;
  }

  if (haveInput) {
    setImageElSrc(dom.imageB, inputSrc);
    dom.imageB.style.display = "block";
    dom.imageA.style.display = "none";
    dom.clip.style.display = "none";
    dom.line.style.display = "none";
    dom.handle.style.display = "none";
    dom.badgeA.style.display = "none";
    dom.badgeB.style.display = "none";
    dom.status.style.display = "none";
    return;
  }

  if (haveLutPreview) {
    setImageElSrc(dom.imageB, lutSrc);
    dom.imageB.style.display = "block";
    dom.imageA.style.display = "none";
    dom.clip.style.display = "none";
    dom.line.style.display = "none";
    dom.handle.style.display = "none";
    dom.badgeA.style.display = "none";
    dom.badgeB.style.display = "none";
    dom.status.style.display = "none";
    return;
  }

  dom.imageA.removeAttribute("src");
  dom.imageB.removeAttribute("src");
  dom.imageA.style.display = "none";
  dom.imageB.style.display = "none";
  dom.clip.style.display = "none";
  dom.line.style.display = "none";
  dom.handle.style.display = "none";
  dom.badgeA.style.display = "none";
  dom.badgeB.style.display = "none";
  dom.status.style.display = "block";
  dom.status.textContent = "Select a LUT or connect an image";
}

function wrapWidgetCallbacks(node, state) {
  for (const widget of node.widgets || []) {
    const name = String(widget?.name || "");
    if (!name || name === PREVIEW_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) continue;
    if (widget.__mkrXLUTWrapped) continue;
    const original = widget.callback;
    widget.callback = function wrappedCallback() {
      if (typeof original === "function") {
        original.apply(this, arguments);
      }
      syncXLUTWidgetVisibility(node);
      updateXLUTControls(node, state);
      if (state.popupRoot && state.popupRoot.style.display !== "none") {
        renderList(node, state);
      }
      refreshBottomPreview(node, state, true);
      markDirty(node);
    };
    widget.__mkrXLUTWrapped = true;
  }
}

function attachXLUTChooser(node) {
  if (!node || node.__mkrXLUTChooserAttached) return;
  node.__mkrXLUTChooserAttached = true;

  const state = makeState(node);
  ensureNodeShape(node);
  syncXLUTWidgetVisibility(node);
  updateXLUTControls(node, state);
  ensureBottomPreviewWidget(node, state);
  wrapWidgetCallbacks(node, state);

  const originalDrawForeground = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground() {
    ensureNodeShape(this);
    return originalDrawForeground?.apply(this, arguments);
  };

  const isHiddenBackendWidget = (widget) => {
    const name = String(widget?.name || "");
    if (!name) return false;
    if (name === PREVIEW_WIDGET_NAME || name === CONTROLS_WIDGET_NAME) return false;
    return HIDDEN_WIDGET_NAMES.includes(name) || widget?.hidden === true || widget?.type === "hidden";
  };

  if (!node.__mkrXLUTWidgetHitPatched) {
    node.__mkrXLUTWidgetHitPatched = true;

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
  }

  const originalMouseDown = node.onMouseDown;
  node.onMouseDown = function onMouseDown(event, pos) {
    const hitOnPos = this.getWidgetOnPos?.apply(this, arguments);
    if (isHiddenBackendWidget(hitOnPos)) return true;
    const hitAtPos = this.getWidgetAtPos?.apply(this, arguments);
    if (isHiddenBackendWidget(hitAtPos)) return true;
    return originalMouseDown?.apply(this, arguments);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    const out = originalConnectionsChange?.apply(this, arguments);
    syncXLUTWidgetVisibility(this);
    updateXLUTControls(this, state);
    wrapWidgetCallbacks(this, state);
    refreshBottomPreview(this, state, true);
    return out;
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    const out = originalConfigure?.apply(this, arguments);
    ensureNodeShape(this);
    syncXLUTWidgetVisibility(this);
    updateXLUTControls(this, state);
    wrapWidgetCallbacks(this, state);
    refreshBottomPreview(this, state, true);
    return out;
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    const out = originalResize?.apply(this, arguments);
    ensureNodeShape(this);
    updateXLUTControls(this, state);
    refreshBottomPreview(this, state, true);
    return out;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted() {
    const out = originalExecuted?.apply(this, arguments);
    ensureNodeShape(this);
    updateXLUTControls(this, state);
    refreshBottomPreview(this, state, true);
    return out;
  };

  state.previewTimer = setInterval(() => {
    ensureNodeShape(node);
    refreshBottomPreview(node, state, false);
  }, PREVIEW_POLL_MS);

  const originalOnRemoved = node.onRemoved;
  node.onRemoved = function onRemoved() {
    closePopup(state);

    if (state.previewTimer) {
      clearInterval(state.previewTimer);
      state.previewTimer = null;
    }

    for (const dispose of state.teardown || []) {
      try {
        dispose();
      } catch {
        // ignore cleanup errors
      }
    }

    if (state.popupRoot?.parentNode) {
      state.popupRoot.parentNode.removeChild(state.popupRoot);
    }
    state.popupRoot = null;

    if (typeof originalOnRemoved === "function") {
      return originalOnRemoved.apply(this, arguments);
    }
    return undefined;
  };

  loadCatalog(node, state, false);
  updateXLUTControls(node, state);
  refreshBottomPreview(node, state, true);
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!isXLUTNodeDef(nodeData)) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = typeof originalOnNodeCreated === "function"
        ? originalOnNodeCreated.apply(this, arguments)
        : undefined;
      try {
        attachXLUTChooser(this);
      } catch (error) {
        console.warn("[mkrshift.xlut] failed to attach chooser:", error);
      }
      return result;
    };
  },
  async nodeCreated(node) {
    if (!isXLUTNode(node)) return;
    attachXLUTChooser(node);
  },
  loadedGraphNode(node) {
    if (!isXLUTNode(node)) return;
    attachXLUTChooser(node);
  },
});
