import { app } from "../../../scripts/app.js";

const EXT = "mkr.presave";
const DOM_WIDGET_NAME = "mkr_presave_ui";
const DEFAULT_W = 360;
const DEFAULT_H = 900;
const PREVIEW_MIN_H = 360;
const PREVIEW_MARGIN = 8;
const ACCENT_LIME = "#D2FD51";
const ACCENT_STYLE_ID = "mkrshift-accent-style";
const ACCENT_STYLE_CSS = `
:root {
  --mkr-accent-lime: #d2fd51;
  --mkr-dark-label: #1f1f1f;
  --mkr-dark-label-highlight: #2e2e2e;
}
`;
const SAVE_OPTION_WIDGET_NAMES = [
  "output_format",
  "animation_mode",
  "filename_prefix",
  "subfolder",
  "overwrite",
  "save_mask",
  "png_compress_level",
  "jpeg_quality",
  "webp_quality",
  "animation_fps",
  "animation_loop",
  "filename_labels",
];

let registered = false;

function getApp() {
  return window.comfyAPI?.app?.app || window.app || app || null;
}

function getApi() {
  return window.comfyAPI?.api || window.api || null;
}

function apiUrl(path) {
  const p = String(path || "");
  const api = getApi();
  if (api && typeof api.apiURL === "function") return api.apiURL(p);
  return p;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function numberValue(value, fallback = 0) {
  const n = Number.parseFloat(String(value));
  return Number.isFinite(n) ? n : fallback;
}

function boolValue(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const t = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(t)) return true;
    if (["false", "0", "no", "off"].includes(t)) return false;
  }
  return fallback;
}

function normalizeToken(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function hasPreSaveToken(value) {
  const token = normalizeToken(value);
  return token === "mkrpresave" || token === "mkrpresaveimage" || token === "presaveimage";
}

function getWidget(node, name) {
  return node.widgets?.find((w) => w?.name === name);
}

function hasWidget(node, name) {
  return !!getWidget(node, name);
}

function hasInput(node, name) {
  return !!node.inputs?.some((entry) => entry?.name === name);
}

function isPreSaveNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
    node?.constructor?.title,
  ].filter(Boolean);
  if (candidates.some((value) => hasPreSaveToken(value))) return true;

  return hasInput(node, "image") && hasWidget(node, "preview_only") && hasWidget(node, "output_format");
}

function isPreSaveNodeDef(nodeData) {
  const candidates = [nodeData?.name, nodeData?.display_name, nodeData?.type, nodeData?.category].filter(Boolean);
  return candidates.some((value) => hasPreSaveToken(value));
}

function ensureAccentStylesheet() {
  if (document.getElementById(ACCENT_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = ACCENT_STYLE_ID;
  style.textContent = ACCENT_STYLE_CSS;
  document.head.appendChild(style);
}

function queueRedraw(node) {
  const app = getApp();
  node.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
}

function suppressGenericPreviewBuffers(node) {
  if (!node) return;
  if (Array.isArray(node.imgs) && node.imgs.length) {
    node.imgs = [];
  }
  if (Array.isArray(node.images) && node.images.length) {
    node.images = [];
  }
  if (Array.isArray(node.animatedImages) && node.animatedImages.length) {
    node.animatedImages = [];
  }
  if (Number.isFinite(node.imageIndex)) {
    node.imageIndex = 0;
  }
  if (typeof node.preview === "object" && node.preview) {
    node.preview = null;
  }
}

function setWidgetValue(node, widget, value) {
  if (!widget) return;
  const app = getApp();
  const previous = widget.value;
  if (typeof value === "number") {
    const prevNum = Number.parseFloat(String(previous));
    if (Number.isFinite(prevNum) && Math.abs(prevNum - value) < 1e-6) return;
  } else if (String(previous) === String(value)) {
    return;
  }
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app?.graph, node, widget);
  }
}

function readWidgetOrProperty(node, name, fallback) {
  const widget = getWidget(node, name);
  if (widget && widget.value !== undefined) {
    return widget.value;
  }
  const prop = node?.properties?.[name];
  if (prop !== undefined) {
    return prop;
  }
  return fallback;
}

function setWidgetOrProperty(node, name, value) {
  const widget = getWidget(node, name);
  if (widget) {
    setWidgetValue(node, widget, value);
    return;
  }
  node.properties = node.properties || {};
  const prev = node.properties[name];
  if (typeof value === "number") {
    const prevNum = Number.parseFloat(String(prev));
    if (Number.isFinite(prevNum) && Math.abs(prevNum - value) < 1e-6) return;
  } else if (String(prev) === String(value)) {
    return;
  }
  node.properties[name] = value;
}

function setWidgetOrPropertySilent(node, name, value) {
  const widget = getWidget(node, name);
  if (widget) {
    const previous = widget.value;
    if (typeof value === "number") {
      const prevNum = Number.parseFloat(String(previous));
      if (Number.isFinite(prevNum) && Math.abs(prevNum - value) < 1e-6) return;
    } else if (String(previous) === String(value)) {
      return;
    }
    widget.value = value;
    return;
  }
  node.properties = node.properties || {};
  const prev = node.properties[name];
  if (typeof value === "number") {
    const prevNum = Number.parseFloat(String(prev));
    if (Number.isFinite(prevNum) && Math.abs(prevNum - value) < 1e-6) return;
  } else if (String(prev) === String(value)) {
    return;
  }
  node.properties[name] = value;
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

function toUrlList(entries) {
  if (!Array.isArray(entries)) return [];
  return entries
    .map((entry, idx) => {
      const base = buildViewUrl(entry);
      if (!base) return "";
      const joiner = base.includes("?") ? "&" : "?";
      return `${base}${joiner}_mkrpresave=${Date.now()}_${idx}`;
    })
    .filter(Boolean);
}

function readOrientation(node, fallback = "horizontal") {
  const value = String(readWidgetOrProperty(node, "orientation", fallback)).trim().toLowerCase();
  return value === "horizontal" ? "horizontal" : "vertical";
}

function readFitMode(node, fallback = "contain") {
  const value = String(readWidgetOrProperty(node, "fit_mode", fallback)).trim().toLowerCase();
  if (value === "cover" || value === "stretch") return value;
  return "contain";
}

function readSplit(node, fallback = 0.5) {
  const value = numberValue(readWidgetOrProperty(node, "split_percent", fallback), fallback);
  return clamp(value, 0, 1);
}

function hideInternalPreviewControls(node) {
  if (!node) return false;
  let changed = false;
  node.properties = node.properties || {};

  const splitDefault = clamp(numberValue(readWidgetOrProperty(node, "split_percent", 0.5), 0.5), 0, 1);
  const fitDefault = readFitMode(node, "contain");
  if (node.properties.split_percent === undefined) {
    node.properties.split_percent = splitDefault;
    changed = true;
  }
  if (node.properties.fit_mode === undefined) {
    node.properties.fit_mode = fitDefault;
    changed = true;
  }

  const hidden = new Set(["split_percent", "fit_mode"]);
  for (const name of hidden) {
    const widget = getWidget(node, name);
    if (!widget) continue;
    changed = setWidgetHiddenState(widget, true) || changed;
  }

  return changed;
}

function fallbackWidgetTypeForName(name) {
  const key = String(name || "");
  if (["preview_only", "overwrite", "save_mask"].includes(key)) return "toggle";
  if (["output_format", "animation_mode", "orientation", "fit_mode"].includes(key)) return "combo";
  if (
    [
      "split_percent",
      "png_compress_level",
      "jpeg_quality",
      "webp_quality",
      "animation_fps",
      "animation_loop",
    ].includes(key)
  ) {
    return "number";
  }
  return "text";
}

function repairWidgetTypes(node) {
  if (!node) return false;
  let changed = false;
  const names = [
    "preview_only",
    "output_format",
    "animation_mode",
    "filename_prefix",
    "subfolder",
    "overwrite",
    "save_mask",
    "orientation",
    "split_percent",
    "fit_mode",
    "png_compress_level",
    "jpeg_quality",
    "webp_quality",
    "animation_fps",
    "animation_loop",
    "filename_labels",
  ];

  for (const name of names) {
    const widget = getWidget(node, name);
    if (!widget || widget.hidden) continue;
    const expected = fallbackWidgetTypeForName(name);
    if (widget.type === "hidden") {
      widget.type = expected;
      changed = true;
      continue;
    }
    if (!widget.type || widget.type === "undefined") {
      widget.type = expected;
      changed = true;
    }
  }
  return changed;
}

function setWidgetHiddenState(widget, hidden) {
  if (!widget) return false;
  const target = !!hidden;
  if (widget.hidden === target) return false;
  widget.hidden = target;
  return true;
}

function sanitizePreSaveWidgetValues(node) {
  if (!node) return false;
  let changed = false;

  const hasChanged = (raw, value) => {
    if (typeof value === "number") {
      const rawNum = Number.parseFloat(String(raw));
      return !Number.isFinite(rawNum) || Math.abs(rawNum - value) > 1e-6;
    }
    if (typeof value === "boolean") {
      return boolValue(raw, value) !== value;
    }
    return String(raw ?? "") !== String(value ?? "");
  };

  const enumOrDefault = (name, allowed, fallback) => {
    const rawVal = readWidgetOrProperty(node, name, fallback);
    const raw = String(rawVal || "").trim().toLowerCase();
    const value = allowed.includes(raw) ? raw : fallback;
    if (hasChanged(rawVal, value)) changed = true;
    setWidgetOrPropertySilent(node, name, value);
  };

  const intOrDefault = (name, fallback, min, max) => {
    const rawVal = readWidgetOrProperty(node, name, fallback);
    const n = Number.parseInt(String(rawVal), 10);
    const value = Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback;
    if (hasChanged(rawVal, value)) changed = true;
    setWidgetOrPropertySilent(node, name, value);
  };

  const floatOrDefault = (name, fallback, min, max) => {
    const rawVal = readWidgetOrProperty(node, name, fallback);
    const n = Number.parseFloat(String(rawVal));
    const value = Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback;
    if (hasChanged(rawVal, value)) changed = true;
    setWidgetOrPropertySilent(node, name, value);
  };

  const boolOrDefault = (name, fallback) => {
    const rawVal = readWidgetOrProperty(node, name, fallback);
    const value = boolValue(rawVal, fallback);
    if (hasChanged(rawVal, value)) changed = true;
    setWidgetOrPropertySilent(node, name, value);
  };

  enumOrDefault("output_format", ["png", "jpeg", "webp", "gif"], "png");
  enumOrDefault("animation_mode", ["auto", "single_animation", "per_frame"], "auto");
  enumOrDefault("orientation", ["horizontal", "vertical"], "horizontal");
  enumOrDefault("fit_mode", ["contain", "cover", "stretch"], "contain");
  floatOrDefault("split_percent", 0.5, 0, 1);
  intOrDefault("png_compress_level", 4, 0, 9);
  intOrDefault("jpeg_quality", 92, 1, 100);
  intOrDefault("webp_quality", 90, 1, 100);
  intOrDefault("animation_fps", 12, 1, 60);
  intOrDefault("animation_loop", 0, 0, 1000);
  boolOrDefault("preview_only", true);
  boolOrDefault("overwrite", false);
  boolOrDefault("save_mask", false);

  const filenamePrefix = String(readWidgetOrProperty(node, "filename_prefix", "MKR") || "MKR");
  const subfolder = String(readWidgetOrProperty(node, "subfolder", "") || "");
  const labels = String(readWidgetOrProperty(node, "filename_labels", "") || "");
  if (hasChanged(readWidgetOrProperty(node, "filename_prefix", "MKR"), filenamePrefix)) changed = true;
  if (hasChanged(readWidgetOrProperty(node, "subfolder", ""), subfolder)) changed = true;
  if (hasChanged(readWidgetOrProperty(node, "filename_labels", ""), labels)) changed = true;
  setWidgetOrPropertySilent(node, "filename_prefix", filenamePrefix);
  setWidgetOrPropertySilent(node, "subfolder", subfolder);
  setWidgetOrPropertySilent(node, "filename_labels", labels);

  return changed;
}

function updateSaveOptionVisibility(node) {
  const previewOnly = boolValue(readWidgetOrProperty(node, "preview_only", true), true);
  let changed = false;
  for (const name of SAVE_OPTION_WIDGET_NAMES) {
    const widget = getWidget(node, name);
    if (!widget) continue;
    changed = setWidgetHiddenState(widget, previewOnly) || changed;
  }
  return changed;
}

function compactFilenameLabelsWidget(node) {
  const widget = getWidget(node, "filename_labels");
  if (!widget) return false;
  let changed = false;

  widget.options = widget.options || {};
  if (widget.options.multiline !== false) {
    widget.options.multiline = false;
    changed = true;
  }
  if (widget.hidden) return changed;

  if (!widget.__mkrCompactComputeSize) {
    widget.__mkrCompactOrigComputeSize = widget.computeSize;
    widget.computeSize = function computeSize(width) {
      const base =
        typeof widget.__mkrCompactOrigComputeSize === "function"
          ? widget.__mkrCompactOrigComputeSize.call(this, width)
          : [200, 24];
      const w = Array.isArray(base) ? Number(base[0] || width || 200) : Number(width || 200);
      return [Math.max(120, w), 24];
    };
    widget.__mkrCompactComputeSize = true;
    changed = true;
  }

  if (widget.inputEl) {
    const tag = String(widget.inputEl.tagName || "").toLowerCase();
    if (tag === "textarea") {
      if (typeof widget.inputEl.rows === "number" && widget.inputEl.rows !== 1) {
        widget.inputEl.rows = 1;
        changed = true;
      }
      if (widget.inputEl.style) {
        if (widget.inputEl.style.minHeight !== "24px") {
          widget.inputEl.style.minHeight = "24px";
          changed = true;
        }
        if (widget.inputEl.style.height !== "24px") {
          widget.inputEl.style.height = "24px";
          changed = true;
        }
      }
    }
  }

  return changed;
}

function syncPreSaveWidgets(node, withSanitize = false) {
  let changed = false;
  if (withSanitize) {
    changed = sanitizePreSaveWidgetValues(node) || changed;
  }
  changed = hideInternalPreviewControls(node) || changed;
  changed = updateSaveOptionVisibility(node) || changed;
  changed = repairWidgetTypes(node) || changed;
  changed = compactFilenameLabelsWidget(node) || changed;
  return changed;
}

function resolvePreviewMinHeight() {
  return PREVIEW_MIN_H;
}

function resolvePreviewTop(node, nodeH) {
  const minPreviewH = resolvePreviewMinHeight();
  const fallback = Math.round(clamp(96, 70, Math.max(70, nodeH - minPreviewH - PREVIEW_MARGIN)));
  const controlBottom = Number(node?.__mkrPreSaveControlBottom);
  const byControls = Number.isFinite(controlBottom) ? Number(controlBottom) + 8 : fallback;
  const maxTop = Math.max(70, nodeH - minPreviewH - PREVIEW_MARGIN);
  return Math.round(clamp(byControls, 70, maxTop || fallback));
}

function readWidgetHeight(widget, width) {
  let height = Number.isFinite(widget?.computedHeight) ? Number(widget.computedHeight) : 24;
  try {
    if (typeof widget?.computeSize === "function") {
      const size = widget.computeSize(width);
      if (Array.isArray(size) && Number.isFinite(size[1])) {
        height = Number(size[1]);
      }
    }
  } catch (error) {
  }
  return clamp(height, 18, 84);
}

function reflowVisibleWidgets(node, state) {
  if (!node || !Array.isArray(node.widgets)) return false;
  let changed = false;
  const width = Number(node?.size?.[0]) || DEFAULT_W;
  let y = 44;
  let lastBottom = y;

  for (const widget of node.widgets) {
    if (!widget || widget === state?.domWidget) continue;
    if (String(widget?.name || "") === DOM_WIDGET_NAME) continue;
    if (widget.hidden) continue;

    changed = trySetWidgetY(widget, y) || changed;
    const height = readWidgetHeight(widget, width);
    y += height + 4;
    lastBottom = y;
  }

  if (!Number.isFinite(node.__mkrPreSaveControlBottom) || Math.abs(Number(node.__mkrPreSaveControlBottom) - lastBottom) > 0.5) {
    node.__mkrPreSaveControlBottom = lastBottom;
    changed = true;
  }
  return changed;
}

function normalizeWidgetStack(node, state) {
  if (!Array.isArray(node?.widgets) || !state?.domWidget) return false;
  let changed = false;

  const all = node.widgets.filter((w) => String(w?.name || "") === DOM_WIDGET_NAME);
  if (all.length > 1) {
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

function trySetWidgetY(widget, y) {
  let changed = false;
  const keys = ["y", "last_y", "_y"];
  for (const key of keys) {
    const current = Number(widget?.[key]);
    if (Number.isFinite(current) && Math.abs(current - y) <= 0.5) continue;
    try {
      widget[key] = y;
      changed = true;
    } catch (error) {
    }
  }
  return changed;
}

function layoutDomWidget(node, state) {
  if (!state?.domWidget) return;
  let changed = normalizeWidgetStack(node, state);
  changed = syncPreSaveWidgets(node, false) || changed;
  changed = reflowVisibleWidgets(node, state) || changed;
  const nodeH = Number.isFinite(node?.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;
  const targetY = resolvePreviewTop(node, nodeH);
  const minNodeH = Math.round(targetY + resolvePreviewMinHeight() + PREVIEW_MARGIN);
  if (Array.isArray(node.size) && minNodeH > Number(node.size[1] || 0)) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), minNodeH];
    changed = true;
  }
  if (Array.isArray(node.size) && Number(node.size[1] || 0) > minNodeH + 650) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), minNodeH];
    changed = true;
  }
  changed = trySetWidgetY(state.domWidget, targetY) || changed;

  const minPx = `${resolvePreviewMinHeight()}px`;
  if (state?.dom?.root?.style?.getPropertyValue("--comfy-widget-min-height") !== minPx) {
    state.dom.root.style.setProperty("--comfy-widget-min-height", minPx);
    changed = true;
  }
  if (changed) queueRedraw(node);
}

function frameCount(state) {
  const fromImages = Array.isArray(state?.imageUrls) ? state.imageUrls.length : 0;
  return Math.max(1, fromImages);
}

function clampFrameIndex(state) {
  const total = frameCount(state);
  state.frameIndex = clamp(Number.isFinite(state.frameIndex) ? state.frameIndex : 0, 0, Math.max(0, total - 1));
}

function advanceFrame(node, state, step) {
  const total = frameCount(state);
  if (total <= 1) return;
  const next = (state.frameIndex + step + total) % total;
  state.frameIndex = next;
  updateDomVisuals(node, state);
  queueRedraw(node);
}

function currentImageUrl(state) {
  if (!Array.isArray(state?.imageUrls) || state.imageUrls.length === 0) return "";
  const idx = clamp(state.frameIndex, 0, state.imageUrls.length - 1);
  return String(state.imageUrls[idx] || "");
}

function currentMaskUrl(state) {
  if (!Array.isArray(state?.maskUrls) || state.maskUrls.length === 0) return "";
  const idx = clamp(state.frameIndex, 0, state.maskUrls.length - 1);
  return String(state.maskUrls[idx] || "");
}

function updateSplitFromPointer(node, state, event) {
  const stage = state?.dom?.stage;
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  const orientation = readOrientation(node, state.orientation);
  let split = 0.5;
  if (orientation === "horizontal") {
    split = clamp((event.clientX - rect.left) / rect.width, 0, 1);
  } else {
    split = clamp((event.clientY - rect.top) / rect.height, 0, 1);
  }
  state.split = Number(split.toFixed(3));
  setWidgetOrProperty(node, "split_percent", state.split);
  updateDomVisuals(node, state);
  queueRedraw(node);
}

function createDomState(node, state) {
  const root = document.createElement("div");
  root.style.cssText = [
    "position:relative",
    "width:100%",
    "height:100%",
    "min-height:0",
    "--comfy-widget-height:100%",
    `--comfy-widget-min-height:${resolvePreviewMinHeight()}px`,
    "overflow:hidden",
    "border-radius:10px",
    "border:1px solid var(--mkr-dark-label-highlight, #2e2e2e)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "box-sizing:border-box",
    "touch-action:none",
    "user-select:none",
  ].join(";");

  const toolbar = document.createElement("div");
  toolbar.style.cssText = [
    "position:absolute",
    "left:0",
    "right:0",
    "top:0",
    "height:32px",
    "display:flex",
    "align-items:center",
    "justify-content:space-between",
    "padding:5px 8px",
    "box-sizing:border-box",
    "gap:8px",
    "background:rgba(31,31,31,0.98)",
    "border-bottom:1px solid rgba(255,255,255,0.08)",
    "z-index:8",
  ].join(";");

  const leftControls = document.createElement("div");
  leftControls.style.cssText = "display:flex;align-items:center;gap:6px;";

  const prev = document.createElement("button");
  prev.type = "button";
  prev.textContent = "<";
  prev.style.cssText = [
    "width:24px",
    "height:20px",
    "border-radius:6px",
    "border:1px solid rgba(255,255,255,0.18)",
    "background:#262626",
    "color:#e7eef7",
    "font:700 11px sans-serif",
    "cursor:pointer",
    "padding:0",
  ].join(";");

  const indexLabel = document.createElement("div");
  indexLabel.textContent = "1/1";
  indexLabel.style.cssText = "min-width:44px;color:#e7eef7;font:600 11px sans-serif;text-align:center;";

  const next = document.createElement("button");
  next.type = "button";
  next.textContent = ">";
  next.style.cssText = prev.style.cssText;

  const modeBadge = document.createElement("div");
  modeBadge.textContent = "Preview mode";
  modeBadge.style.cssText = [
    "font:600 11px sans-serif",
    "letter-spacing:0.15px",
    "color:rgba(226,236,247,0.88)",
    "background:transparent",
    "padding:0",
  ].join(";");

  leftControls.appendChild(prev);
  leftControls.appendChild(indexLabel);
  leftControls.appendChild(next);
  toolbar.appendChild(leftControls);
  toolbar.appendChild(modeBadge);

  const stage = document.createElement("div");
  stage.style.cssText = [
    "position:absolute",
    "left:8px",
    "right:8px",
    "top:40px",
    "bottom:8px",
    "overflow:hidden",
    "border-radius:9px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:#161616",
    "touch-action:none",
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
  imageB.alt = "Mask Preview";
  imageB.draggable = false;
  imageB.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:contain",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const clip = document.createElement("div");
  clip.style.cssText = "position:absolute;inset:0;overflow:hidden;pointer-events:none;";

  const imageA = document.createElement("img");
  imageA.alt = "Image Preview";
  imageA.draggable = false;
  imageA.style.cssText = [
    "position:absolute",
    "inset:0",
    "width:100%",
    "height:100%",
    "object-fit:contain",
    "display:none",
    "pointer-events:none",
  ].join(";");

  clip.appendChild(imageA);

  const line = document.createElement("div");
  line.style.cssText = "position:absolute;background:rgba(255,255,255,0.94);z-index:5;pointer-events:none;";

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
    "z-index:6",
    "pointer-events:none",
    "transform:translate(-50%, -50%)",
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
    "background:rgba(31,31,31,0.92)",
    "border-radius:8px",
    "pointer-events:none",
    "max-width:90%",
    "white-space:normal",
  ].join(";");

  stage.appendChild(checker);
  stage.appendChild(imageB);
  stage.appendChild(clip);
  stage.appendChild(line);
  stage.appendChild(handle);
  stage.appendChild(status);

  root.appendChild(toolbar);
  root.appendChild(stage);

  let dragging = false;
  stage.addEventListener("pointerdown", (event) => {
    if (!state.hasMask) return;
    dragging = true;
    stage.setPointerCapture?.(event.pointerId);
    updateSplitFromPointer(node, state, event);
    event.preventDefault();
  });

  stage.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    updateSplitFromPointer(node, state, event);
    event.preventDefault();
  });

  const stopDrag = (event) => {
    dragging = false;
    stage.releasePointerCapture?.(event.pointerId);
  };
  stage.addEventListener("pointerup", stopDrag);
  stage.addEventListener("pointercancel", stopDrag);
  stage.addEventListener("pointerleave", () => {
    dragging = false;
  });

  root.addEventListener(
    "wheel",
    (event) => {
      if (Math.abs(event.deltaY) < 1) return;
      advanceFrame(node, state, event.deltaY > 0 ? 1 : -1);
      event.preventDefault();
    },
    { passive: false }
  );

  prev.addEventListener("click", () => advanceFrame(node, state, -1));
  next.addEventListener("click", () => advanceFrame(node, state, 1));

  const widget = node.addDOMWidget?.(DOM_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => resolvePreviewMinHeight(),
    getMaxHeight: () => Number.POSITIVE_INFINITY,
  });

  if (!widget) return false;
  widget.serialize = false;

  state.dom = {
    root,
    stage,
    imageA,
    imageB,
    clip,
    line,
    handle,
    status,
    indexLabel,
    modeBadge,
  };
  state.domWidget = widget;
  return true;
}

function updateDomVisuals(node, state) {
  const dom = state?.dom;
  if (!dom) return;

  clampFrameIndex(state);
  state.previewOnly = boolValue(readWidgetOrProperty(node, "preview_only", state.previewOnly), state.previewOnly);
  state.orientation = readOrientation(node, state.orientation);
  state.fitMode = readFitMode(node, state.fitMode);
  state.split = readSplit(node, state.split);

  const imageSrc = currentImageUrl(state);
  const maskSrc = currentMaskUrl(state);
  const hasImage = !!imageSrc;
  const hasMask = !!maskSrc && !!state.hasMask;

  dom.imageA.style.objectFit = state.fitMode;
  dom.imageB.style.objectFit = state.fitMode;

  if (hasImage) {
    if (dom.imageA.src !== imageSrc) dom.imageA.src = imageSrc;
    dom.imageA.style.display = "block";
  } else {
    dom.imageA.removeAttribute("src");
    dom.imageA.style.display = "none";
  }

  if (hasMask) {
    if (dom.imageB.src !== maskSrc) dom.imageB.src = maskSrc;
    dom.imageB.style.display = "block";
  } else {
    dom.imageB.removeAttribute("src");
    dom.imageB.style.display = "none";
  }

  const splitPercent = clamp(state.split, 0, 1) * 100;
  if (hasMask) {
    dom.line.style.display = "block";
    dom.handle.style.display = "block";
    if (state.orientation === "horizontal") {
      dom.clip.style.clipPath = `inset(0 ${100 - splitPercent}% 0 0)`;
      dom.line.style.left = `${splitPercent}%`;
      dom.line.style.top = "0";
      dom.line.style.bottom = "0";
      dom.line.style.width = "1px";
      dom.line.style.height = "100%";
      dom.line.style.transform = "translateX(-0.5px)";
      dom.handle.style.left = `${splitPercent}%`;
      dom.handle.style.top = "50%";
    } else {
      dom.clip.style.clipPath = `inset(0 0 ${100 - splitPercent}% 0)`;
      dom.line.style.top = `${splitPercent}%`;
      dom.line.style.left = "0";
      dom.line.style.right = "0";
      dom.line.style.height = "1px";
      dom.line.style.width = "100%";
      dom.line.style.transform = "translateY(-0.5px)";
      dom.handle.style.left = "50%";
      dom.handle.style.top = `${splitPercent}%`;
    }
  } else {
    dom.clip.style.clipPath = "inset(0 0 0 0)";
    dom.line.style.display = "none";
    dom.handle.style.display = "none";
  }

  if (!hasImage) {
    dom.status.style.display = "block";
    dom.status.textContent = "Queue node to generate preview.";
  } else if (state.hasMask && !hasMask) {
    dom.status.style.display = "block";
    dom.status.textContent = "Mask preview missing.";
  } else {
    dom.status.style.display = "none";
  }

  const total = frameCount(state);
  dom.indexLabel.textContent = `${state.frameIndex + 1}/${total}`;
  dom.modeBadge.textContent = state.previewOnly ? "Preview mode" : "Save mode";
  dom.modeBadge.style.color = state.previewOnly
    ? "rgba(226,236,247,0.88)"
    : "var(--mkr-accent-lime, #D2FD51)";

  layoutDomWidget(node, state);
}

function applyOutputMessage(node, state, message) {
  suppressGenericPreviewBuffers(node);
  const images = message?.presave_images ?? message?.ui?.presave_images ?? [];
  const maskImages = message?.presave_mask_images ?? message?.ui?.presave_mask_images ?? [];
  const presaveState = message?.presave_state?.[0] ?? message?.ui?.presave_state?.[0] ?? null;
  const saveSummary = message?.save_summary?.[0] ?? message?.ui?.save_summary?.[0] ?? null;

  state.imageUrls = toUrlList(images);
  state.maskUrls = toUrlList(maskImages);
  state.hasMask = state.maskUrls.length > 0;

  if (presaveState && typeof presaveState === "object") {
    state.previewOnly = !!presaveState.preview_only;
    state.hasMask = !!presaveState.has_mask || state.hasMask;
    if (presaveState.orientation !== undefined) {
      setWidgetOrProperty(node, "orientation", String(presaveState.orientation));
    }
    if (presaveState.split_percent !== undefined) {
      setWidgetOrProperty(node, "split_percent", numberValue(presaveState.split_percent, state.split));
    }
    if (presaveState.fit_mode !== undefined) {
      setWidgetOrProperty(node, "fit_mode", String(presaveState.fit_mode));
    }
  }
  if (saveSummary && typeof saveSummary === "object") {
    state.saveSummary = saveSummary;
  } else {
    state.saveSummary = {};
  }

  syncPreSaveWidgets(node, true);
  clampFrameIndex(state);
  updateDomVisuals(node, state);
  queueRedraw(node);
}

function ensurePreSaveUI(node) {
  if (!node) return;
  if (node.__mkrPreSaveUIAttached) {
    syncPreSaveWidgets(node, true);
    suppressGenericPreviewBuffers(node);
    const state = node.__mkrPreSaveState;
    if (state) {
      updateDomVisuals(node, state);
    }
    queueRedraw(node);
    return;
  }

  node.__mkrPreSaveUIAttached = true;
  syncPreSaveWidgets(node, true);
  node.resizable = true;
  if (!Array.isArray(node.size) || node.size.length < 2) node.size = [DEFAULT_W, DEFAULT_H];
  const currentH = Number.isFinite(node.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;
  const topForMin = resolvePreviewTop(node, Math.max(currentH, DEFAULT_H));
  const minNodeH = Math.round(topForMin + resolvePreviewMinHeight() + PREVIEW_MARGIN);
  if (currentH < minNodeH) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), minNodeH];
  }

  const state = {
    imageUrls: [],
    maskUrls: [],
    frameIndex: 0,
    split: readSplit(node, 0.5),
    orientation: readOrientation(node, "horizontal"),
    fitMode: readFitMode(node, "contain"),
    hasMask: false,
    previewOnly: true,
    saveSummary: {},
    dom: null,
    domWidget: null,
  };
  node.__mkrPreSaveState = state;
  suppressGenericPreviewBuffers(node);
  syncPreSaveWidgets(node, false);

  if (typeof node.addDOMWidget === "function") {
    createDomState(node, state);
  }

  const previewOnlyWidget = getWidget(node, "preview_only");
  if (previewOnlyWidget && !previewOnlyWidget.__mkrPreviewOnlyHooked) {
    const originalPreviewOnlyCb = previewOnlyWidget.callback;
    previewOnlyWidget.callback = function previewOnlyCallback(value) {
      if (typeof originalPreviewOnlyCb === "function") {
        originalPreviewOnlyCb.apply(this, arguments);
      }
      syncPreSaveWidgets(node, false);
      updateDomVisuals(node, state);
      queueRedraw(node);
    };
    previewOnlyWidget.__mkrPreviewOnlyHooked = true;
  }

  const originalDrawBackground = node.onDrawBackground;
  node.onDrawBackground = function onDrawBackground() {
    suppressGenericPreviewBuffers(this);
    if (typeof originalDrawBackground === "function") {
      originalDrawBackground.apply(this, arguments);
    }
  };

  const originalDraw = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    suppressGenericPreviewBuffers(this);
    if (typeof originalDraw === "function") {
      originalDraw.apply(this, arguments);
    }
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    if (typeof originalExecuted === "function") originalExecuted.apply(this, arguments);
    applyOutputMessage(this, state, message || {});
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    if (typeof originalResize === "function") originalResize.apply(this, arguments);
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    if (typeof originalConfigure === "function") originalConfigure.apply(this, arguments);
    syncPreSaveWidgets(this, true);
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    if (typeof originalConnectionsChange === "function") originalConnectionsChange.apply(this, arguments);
    suppressGenericPreviewBuffers(this);
    syncPreSaveWidgets(this, true);
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  updateDomVisuals(node, state);
  queueRedraw(node);
}

function findNodeByLocator(locatorId) {
  const app = getApp();
  const graph = app?.graph;
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
    if (String(node.id) === raw || String(node.id) === String(tail)) return node;
  }
  return null;
}

function attachAllKnownNodes() {
  const app = getApp();
  const nodes = app?.graph?._nodes || [];
  for (const node of nodes) {
    if (isPreSaveNode(node)) {
      suppressGenericPreviewBuffers(node);
      syncPreSaveWidgets(node, true);
      ensurePreSaveUI(node);
    }
  }
}

function buildExtension() {
  return {
    name: EXT,

    async setup() {
      attachAllKnownNodes();
      setTimeout(attachAllKnownNodes, 1200);
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
      if (!isPreSaveNodeDef(nodeData)) return;
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function onNodeCreated() {
        if (typeof originalOnNodeCreated === "function") {
          originalOnNodeCreated.apply(this, arguments);
        }
        ensurePreSaveUI(this);
      };
    },

    async nodeCreated(node) {
      if (isPreSaveNode(node)) {
        ensurePreSaveUI(node);
        return;
      }

      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (isPreSaveNode(node)) {
          ensurePreSaveUI(node);
          clearInterval(timer);
          return;
        }
        if (tries >= 30) clearInterval(timer);
      }, 100);
    },

    loadedGraphNode(node) {
      if (isPreSaveNode(node)) ensurePreSaveUI(node);
    },

    onNodeOutputsUpdated(nodeOutputs) {
      if (!nodeOutputs || typeof nodeOutputs !== "object") return;
      for (const [locatorId, output] of Object.entries(nodeOutputs)) {
        if (!output || typeof output !== "object") continue;
        if (
          !(
            "presave_images" in output ||
            "presave_mask_images" in output ||
            "presave_state" in output
          )
        ) {
          continue;
        }
        const node = findNodeByLocator(locatorId);
        if (!node || !node.__mkrPreSaveState) continue;
        if (!isPreSaveNode(node)) continue;
        applyOutputMessage(node, node.__mkrPreSaveState, output);
      }
    },
  };
}

function registerWhenReady(tries = 0) {
  if (registered) return;
  ensureAccentStylesheet();

  const app = getApp();
  if (!app?.registerExtension) {
    if (tries < 400) setTimeout(() => registerWhenReady(tries + 1), 100);
    return;
  }
  app.registerExtension(buildExtension());
  registered = true;
}

registerWhenReady();
