import { app } from "../../../scripts/app.js";

const EXT = "mkr.axb_compare";
const DEFAULT_W = 320;
const DEFAULT_H = 420;
const DOM_PREVIEW_MIN_H = 300;
const PREVIEW_MARGIN = 8;
const ENABLE_DOM_WIDGET = true;
const ACCENT_LIME = "#D2FD51";
const INTERNAL_SPLIT_PROP = "mkr_axb_split";
const MKR_BADGE_BG = "#1F1F1F";
const MKR_BADGE_FG = ACCENT_LIME;
const LEGACY_CANVAS_SUFFIX = " [Canvas]";
const AXB_RUNTIME_VERSION = "node2-2026-03-10b";
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
const MKR_BADGE_RETRY_MS = 90;
const MKR_BADGE_MAX_RETRIES = 25;

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
  if (api && typeof api.apiURL === "function") {
    return api.apiURL(p);
  }
  return p;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function ensureAccentStylesheet() {
  if (document.getElementById(ACCENT_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = ACCENT_STYLE_ID;
  style.textContent = ACCENT_STYLE_CSS;
  document.head.appendChild(style);
}

function normalizeToken(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function hasAxBToken(value) {
  const token = normalizeToken(value);
  return token.includes("axbcompare") || (token.includes("axb") && token.includes("compare"));
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

function getPrimaryOrientationWidget(node) {
  const widgets = Array.isArray(node?.widgets) ? node.widgets : [];
  const matches = widgets.filter((w) => String(w?.name || "") === "orientation" && !w?.hidden);
  if (!matches.length) return null;
  matches.sort((a, b) => {
    const ay = Number.isFinite(a?.y) ? Number(a.y) : Number(a?.last_y);
    const by = Number.isFinite(b?.y) ? Number(b.y) : Number(b?.last_y);
    if (!Number.isFinite(ay) && !Number.isFinite(by)) return 0;
    if (!Number.isFinite(ay)) return 1;
    if (!Number.isFinite(by)) return -1;
    return ay - by;
  });
  return matches[0] || null;
}

function resolvePreviewTop(node, nodeH) {
  const minPreviewH = resolvePreviewMinHeight(node);
  const fallbackTop = Math.round(clamp(86, 70, Math.max(70, nodeH - minPreviewH - PREVIEW_MARGIN)));
  const orientationWidget = getPrimaryOrientationWidget(node);
  if (!orientationWidget || orientationWidget.hidden) return fallbackTop;

  const oy = Number.isFinite(orientationWidget?.y) ? Number(orientationWidget.y) : Number(orientationWidget?.last_y);
  const ohRaw = Number.isFinite(orientationWidget?.computedHeight) ? Number(orientationWidget.computedHeight) : 24;
  const oh = clamp(ohRaw, 18, 40);
  if (!Number.isFinite(oy)) return fallbackTop;

  const candidate = oy + oh + 8;
  const maxTop = Math.max(70, nodeH - minPreviewH - PREVIEW_MARGIN);
  const maxReasonableTop = Math.min(maxTop, 160);
  if (candidate < 64 || candidate > maxReasonableTop) {
    return fallbackTop;
  }
  return Math.round(clamp(candidate, 70, maxReasonableTop));
}

function resolvePreviewMinHeight(node) {
  return DOM_PREVIEW_MIN_H;
}

function isAxBNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
    node?.constructor?.title,
  ].filter(Boolean);

  if (candidates.some((value) => hasAxBToken(value))) {
    return true;
  }

  return hasInput(node, "image_a") && hasInput(node, "image_b");
}

function looksLikeMkrNode(node) {
  const sourceBadge = String(node?.constructor?.nodeData?.nodeSource?.badgeText || "");
  const sourceType = String(node?.constructor?.nodeData?.nodeSource?.type || "");
  const pyModule = String(node?.constructor?.nodeData?.python_module || node?.python_module || "");
  const comfyClass = String(node?.constructor?.comfyClass || node?.comfyClass || "");
  const title = String(node?.title || "");
  const haystack = [sourceBadge, sourceType, pyModule, comfyClass, title].filter(Boolean).join(" ");
  return normalizeToken(haystack).includes("mkrshift");
}

function styleBadgeInstance(badge) {
  if (!badge || typeof badge !== "object") return badge;
  const text = normalizeToken(badge.text || "");
  if (!text.includes("mkrshift")) return badge;
  badge.bgColor = MKR_BADGE_BG;
  badge.fgColor = MKR_BADGE_FG;
  return badge;
}

function styleMkrNodeSourceBadge(node) {
  const source = node?.constructor?.nodeData?.nodeSource;
  if (!source || typeof source !== "object") return false;

  let changed = false;
  const bgFields = ["badgeColor", "badgeBgColor", "badgeBackgroundColor"];
  for (const key of bgFields) {
    if (source[key] !== MKR_BADGE_BG) {
      source[key] = MKR_BADGE_BG;
      changed = true;
    }
  }

  const fgFields = ["textColor", "badgeTextColor"];
  for (const key of fgFields) {
    if (source[key] !== MKR_BADGE_FG) {
      source[key] = MKR_BADGE_FG;
      changed = true;
    }
  }

  return changed;
}

function applyMkrBadgeOverride(node) {
  if (!node) return false;
  if (!looksLikeMkrNode(node)) return false;
  let changed = false;
  if (styleMkrNodeSourceBadge(node)) {
    changed = true;
  }

  if (Array.isArray(node.badges) && node.badges.length > 0) {
    node.badges = node.badges.map((entry) => {
      if (typeof entry === "function") {
        if (entry.__mkrBadgeWrapper) return entry;
        const wrapped = function wrappedBadgeFactory() {
          const badge = entry.apply(this, arguments);
          return styleBadgeInstance(badge);
        };
        wrapped.__mkrBadgeWrapper = true;
        changed = true;
        return wrapped;
      }
      const beforeBg = entry?.bgColor;
      const beforeFg = entry?.fgColor;
      const styled = styleBadgeInstance(entry);
      if (styled?.bgColor !== beforeBg || styled?.fgColor !== beforeFg) {
        changed = true;
      }
      return styled;
    });
  }

  if (changed) {
    queueRedraw(node);
  }
  return changed;
}

function stopMkrBadgeRefresh(node) {
  const timer = node?.__mkrBadgeRefreshTimer;
  if (!timer) return;
  clearInterval(timer);
  node.__mkrBadgeRefreshTimer = null;
}

function scheduleMkrBadgeRefresh(node) {
  if (!node) return;
  if (!looksLikeMkrNode(node)) return;
  stopMkrBadgeRefresh(node);

  let tries = 0;
  const tick = () => {
    tries += 1;
    applyMkrBadgeOverride(node);
    const hasBadges = Array.isArray(node.badges) && node.badges.length > 0;
    if (hasBadges || tries >= MKR_BADGE_MAX_RETRIES) {
      stopMkrBadgeRefresh(node);
    }
  };

  tick();
  if (!Array.isArray(node.badges) || node.badges.length === 0) {
    node.__mkrBadgeRefreshTimer = setInterval(tick, MKR_BADGE_RETRY_MS);
  }
}

function sanitizeAxBNodeTitle(node) {
  if (!node || typeof node.title !== "string") return;
  if (!node.title.includes(LEGACY_CANVAS_SUFFIX)) return;
  node.title = node.title.split(LEGACY_CANVAS_SUFFIX).join("");
}

function needsAxBRuntimeUpgrade(node) {
  return node?.__mkrAxBRuntimeVersion !== AXB_RUNTIME_VERSION;
}

function resetAxBNodeHooks(node) {
  if (!node) return;
  const proto = Object.getPrototypeOf(node) || {};
  const hookNames = [
    "onDrawForeground",
    "onMouseDown",
    "onMouseMove",
    "onMouseUp",
    "onMouseLeave",
    "onResize",
    "onExecuted",
    "onConnectionsChange",
    "onConfigure",
  ];
  for (const name of hookNames) {
    if (typeof proto[name] === "function") {
      node[name] = proto[name];
    } else {
      delete node[name];
    }
  }
}

function removeAllAxBDomWidgets(node) {
  if (!Array.isArray(node?.widgets)) return false;
  let changed = false;
  const kept = [];
  for (const widget of node.widgets) {
    const name = String(widget?.name || "");
    const type = String(widget?.type || "");
    if (name === "mkr_axb_compare_ui" || type === "AXB_COMPARE") {
      try {
        widget?.onRemove?.();
      } catch (error) {
      }
      changed = true;
      continue;
    }
    kept.push(widget);
  }
  if (changed) {
    node.widgets = kept;
  }
  return changed;
}

function migrateAxBNodeRuntime(node) {
  if (!node) return;
  if (!needsAxBRuntimeUpgrade(node)) return;
  sanitizeAxBNodeTitle(node);
  removeAllAxBDomWidgets(node);
  resetAxBNodeHooks(node);
  delete node.__mkrAxBState;
  delete node.__mkrAxBUIAttached;
  delete node.__mkrAxBCanvasAttached;
}

function looksLikeAxBCompareNode(node) {
  if (isAxBNode(node)) return true;

  const hasImageInputs = hasInput(node, "image_a") && hasInput(node, "image_b");
  if (!hasImageInputs) return false;

  // Node 2.0 may not expose the same widget array; image inputs are enough.
  const hasCoreWidgets =
    hasWidget(node, "orientation") &&
    hasWidget(node, "swap_inputs");

  return hasCoreWidgets || hasImageInputs;
}

function isAxBNodeDef(nodeData) {
  const candidates = [
    nodeData?.name,
    nodeData?.display_name,
    nodeData?.type,
    nodeData?.category,
  ].filter(Boolean);
  return candidates.some((value) => hasAxBToken(value));
}

function sanitizeAxBNodeDataInputs(nodeData) {
  if (!nodeData || typeof nodeData !== "object") return;
  const input = nodeData.input || (nodeData.input = {});
  const required = input.required || (input.required = {});
  const optional = input.optional || (input.optional = {});
  const inputOrder = nodeData.input_order || (nodeData.input_order = { required: [], optional: [] });
  inputOrder.required = Array.isArray(inputOrder.required) ? inputOrder.required : [];
  inputOrder.optional = Array.isArray(inputOrder.optional) ? inputOrder.optional : [];

  const stripInput = (name) => {
    delete required[name];
    delete optional[name];
    inputOrder.required = inputOrder.required.filter((entry) => entry !== name);
    inputOrder.optional = inputOrder.optional.filter((entry) => entry !== name);
  };

  stripInput("split_percent");
  stripInput("fit_mode");
  stripInput("swap_inputs");
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

function numberValue(value, fallback = 0.5) {
  const n = Number.parseFloat(String(value));
  return Number.isFinite(n) ? n : fallback;
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

function readSplitValue(node, state) {
  if (state && Number.isFinite(state.split)) {
    return clamp(Number(state.split), 0, 1);
  }

  const splitWidget = getWidget(node, "split_percent");
  if (splitWidget && splitWidget.value !== undefined) {
    return clamp(numberValue(splitWidget.value, 0.5), 0, 1);
  }

  const internal = node?.properties?.[INTERNAL_SPLIT_PROP];
  if (internal !== undefined) {
    return clamp(numberValue(internal, 0.5), 0, 1);
  }

  const legacy = node?.properties?.split_percent;
  if (legacy !== undefined) {
    return clamp(numberValue(legacy, 0.5), 0, 1);
  }

  return 0.5;
}

function setSplitValue(node, state, split) {
  const next = clamp(numberValue(split, 0.5), 0, 1);
  const rounded = Number(next.toFixed(3));
  if (state) state.split = next;
  node.properties = node.properties || {};
  node.properties[INTERNAL_SPLIT_PROP] = rounded;
  node.properties.split_percent = rounded;
  queueRedraw(node);
}

function hardHideWidget(widget) {
  if (!widget) return false;
  let changed = false;
  if (widget.hidden !== true) {
    widget.hidden = true;
    changed = true;
  }
  if (widget.type !== "hidden") {
    widget.__mkrOrigType ??= widget.type;
    widget.type = "hidden";
    changed = true;
  }
  if (!widget.__mkrOrigComputeSize) {
    widget.__mkrOrigComputeSize = widget.computeSize;
  }
  if (!widget.__mkrOrigComputeLayoutSize) {
    widget.__mkrOrigComputeLayoutSize = widget.computeLayoutSize;
  }
  widget.computeSize = () => [0, -4];
  widget.computeLayoutSize = () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 });
  return changed;
}

function removeLegacyAxBInputs(node) {
  if (!Array.isArray(node?.inputs) || node.inputs.length === 0) return false;
  const legacyNames = new Set(["split_percent", "fit_mode", "swap_inputs"]);
  let changed = false;

  for (let i = node.inputs.length - 1; i >= 0; i -= 1) {
    const input = node.inputs[i];
    const inputName = String(input?.name || "");
    const widgetName = String(input?.widget?.name || "");
    if (!legacyNames.has(inputName) && !legacyNames.has(widgetName)) continue;
    try {
      if (typeof node.disconnectInput === "function") {
        node.disconnectInput(i);
      }
    } catch (error) {
    }
    try {
      if (typeof node.removeInput === "function") {
        node.removeInput(i);
      } else {
        node.inputs.splice(i, 1);
      }
    } catch (error) {
      try {
        node.inputs.splice(i, 1);
      } catch (error2) {
      }
    }
    changed = true;
  }
  if (Array.isArray(node.inputs)) {
    const before = node.inputs.length;
    node.inputs = node.inputs.filter((input) => {
      const inputName = String(input?.name || "");
      const widgetName = String(input?.widget?.name || "");
      return !legacyNames.has(inputName) && !legacyNames.has(widgetName);
    });
    if (node.inputs.length !== before) {
      changed = true;
    }
  }
  return changed;
}

function hideLegacyAxBControls(node) {
  if (!node) return false;
  let changed = false;

  node.properties = node.properties || {};
  if (node.properties[INTERNAL_SPLIT_PROP] === undefined) {
    node.properties[INTERNAL_SPLIT_PROP] = clamp(numberValue(node.properties.split_percent, 0.5), 0, 1);
    changed = true;
  }

  if (node.properties.split_percent === undefined) {
    node.properties.split_percent = node.properties[INTERNAL_SPLIT_PROP];
    changed = true;
  }
  if (node.properties.fit_mode === undefined) {
    node.properties.fit_mode = "contain";
    changed = true;
  }
  if (node.properties.display_mode === undefined) {
    node.properties.display_mode = "actual_definition";
    changed = true;
  }
  if (node.properties.swap_inputs === undefined) {
    node.properties.swap_inputs = false;
    changed = true;
  }

  node.properties.split_percent = clamp(numberValue(node.properties.split_percent, 0.5), 0, 1);
  node.properties.fit_mode = "contain";
  node.properties.display_mode = "actual_definition";
  node.properties.swap_inputs = boolValue(node.properties.swap_inputs, false);

  if (Array.isArray(node.widgets) && node.widgets.length) {
    const filtered = [];
    for (const widget of node.widgets) {
      const name = String(widget?.name || "");
      if (name === "split_percent" || name === "fit_mode" || name === "swap_inputs") {
        try {
          widget?.onRemove?.();
        } catch (error) {
        }
        changed = true;
        continue;
      }
      filtered.push(widget);
    }
    if (filtered.length !== node.widgets.length) {
      node.widgets = filtered;
      changed = true;
    }
  }

  if (removeLegacyAxBInputs(node)) {
    changed = true;
  }

  if (node.properties[INTERNAL_SPLIT_PROP] !== node.properties.split_percent) {
    node.properties[INTERNAL_SPLIT_PROP] = node.properties.split_percent;
    changed = true;
  }

  return changed;
}

function readViewState(node, state) {
  const orientationRaw = String(readWidgetOrProperty(node, "orientation", "horizontal")).toLowerCase();
  const displayModeRaw = String(node?.properties?.display_mode || "actual_definition").toLowerCase();
  const fitModeRaw = String(node?.properties?.fit_mode || "contain").toLowerCase();
  const fitMode = ["contain", "cover", "stretch"].includes(fitModeRaw) ? fitModeRaw : "contain";

  return {
    orientation: orientationRaw === "horizontal" ? "horizontal" : "vertical",
    split: readSplitValue(node, state),
    fitMode,
    displayMode: displayModeRaw === "fit_view" ? "fit_view" : "actual_definition",
    swap: boolValue(node?.properties?.swap_inputs, false),
  };
}

function queueRedraw(node) {
  const app = getApp();
  node.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
}

function setWidgetValue(node, name, value) {
  const app = getApp();
  const widget = getWidget(node, name);

  if (widget) {
    let same = false;
    if (typeof value === "number") {
      const prev = Number.parseFloat(String(widget.value));
      same = Number.isFinite(prev) ? Math.abs(prev - value) < 1e-6 : false;
    } else {
      same = String(widget.value) === String(value);
    }
    if (same) return;

    widget.value = value;
    if (typeof widget.callback === "function") {
      widget.callback(value, app?.graph, node, widget);
    }
  } else {
    node.properties = node.properties || {};
    node.properties[name] = value;
  }

  queueRedraw(node);
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

function loadPreviewIntoState(node, state, slot, info) {
  const url = buildViewUrl(info);
  if (!url) return;

  const src = `${url}&_ts=${Date.now()}`;
  state.previewSrc[slot] = src;
  state.previewInfo = state.previewInfo || { a: null, b: null };
  state.previewInfo[slot] = info && typeof info === "object" ? { ...info } : null;

  const image = new Image();
  image.onload = () => {
    state.images[slot] = image;
    updateDomVisuals(node, state);
    queueRedraw(node);
  };
  image.onerror = () => {
    state.images[slot] = null;
    state.previewInfo[slot] = null;
    updateDomVisuals(node, state);
    queueRedraw(node);
  };
  image.src = src;
}

function isDrawableImage(image) {
  return !!(image && image.complete && image.naturalWidth > 0 && image.naturalHeight > 0);
}

function getImageDimensions(image) {
  if (!isDrawableImage(image)) return null;
  return {
    w: image.naturalWidth || image.width || 0,
    h: image.naturalHeight || image.height || 0,
  };
}

function getPreferredDimensions(image, previewInfo) {
  const sourceWidth = Number(previewInfo?.source_width);
  const sourceHeight = Number(previewInfo?.source_height);
  if (Number.isFinite(sourceWidth) && Number.isFinite(sourceHeight) && sourceWidth > 0 && sourceHeight > 0) {
    return { w: sourceWidth, h: sourceHeight };
  }
  return getImageDimensions(image);
}

function computePlacedRect(containerRect, sourceSize, scale, anchorX = 0.5, anchorY = 0.5) {
  if (!sourceSize || !sourceSize.w || !sourceSize.h || !Number.isFinite(scale) || scale <= 0) {
    return null;
  }

  const width = Math.max(1, Math.round(sourceSize.w * scale));
  const height = Math.max(1, Math.round(sourceSize.h * scale));
  const x = containerRect.x + Math.round((containerRect.w - width) * anchorX);
  const y = containerRect.y + Math.round((containerRect.h - height) * anchorY);
  return { x, y, w: width, h: height };
}

function resolveCompareLayout(containerRect, imageA, imageB, previewInfoA, previewInfoB, compareState, displayMode, fitMode) {
  const dimsA = getPreferredDimensions(imageA, previewInfoA);
  const dimsB = getPreferredDimensions(imageB, previewInfoB);
  const allDims = [dimsA, dimsB].filter(Boolean);
  if (!allDims.length) {
    return { frame: containerRect, a: null, b: null };
  }

  const metaCanvas = Array.isArray(compareState?.compare_canvas_size) ? compareState.compare_canvas_size : null;
  const compareCanvas = {
    w:
      metaCanvas && Number.isFinite(Number(metaCanvas[0])) && Number(metaCanvas[0]) > 0
        ? Number(metaCanvas[0])
        : Math.max(...allDims.map((dims) => dims.w)),
    h:
      metaCanvas && Number.isFinite(Number(metaCanvas[1])) && Number(metaCanvas[1]) > 0
        ? Number(metaCanvas[1])
        : Math.max(...allDims.map((dims) => dims.h)),
  };
  const mode = String(displayMode || "actual_definition").toLowerCase();
  if (mode === "fit_view") {
    return {
      frame: containerRect,
      a: dimsA ? { x: containerRect.x, y: containerRect.y, w: containerRect.w, h: containerRect.h, fitMode } : null,
      b: dimsB ? { x: containerRect.x, y: containerRect.y, w: containerRect.w, h: containerRect.h, fitMode } : null,
    };
  }

  const scale = Math.min(1, containerRect.w / compareCanvas.w, containerRect.h / compareCanvas.h);
  const frame = computePlacedRect(containerRect, compareCanvas, scale, 0.5, 0.5) || containerRect;
  return {
    frame,
    a: dimsA ? { x: frame.x, y: frame.y, w: frame.w, h: frame.h, fitMode } : null,
    b: dimsB ? { x: frame.x, y: frame.y, w: frame.w, h: frame.h, fitMode } : null,
  };
}

function drawImagePlaced(ctx, image, placement, fitMode) {
  if (!placement) return;
  if (placement.fitMode) {
    drawImageFitted(ctx, image, placement, fitMode);
    return;
  }
  ctx.drawImage(image, placement.x, placement.y, placement.w, placement.h);
}

function resolveLinkedNodeImageSrc(node, inputName) {
  const index = node.inputs?.findIndex((entry) => entry.name === inputName) ?? -1;
  if (index < 0) return "";

  const sourceNode = node.getInputNode?.(index);
  if (!sourceNode) return "";

  const images = sourceNode.imgs;
  if (!Array.isArray(images) || images.length < 1) return "";

  const sample = images[0];
  if (!sample) return "";

  if (sample instanceof HTMLImageElement) {
    return sample.src || "";
  }

  if (typeof sample === "object" && typeof sample.src === "string") {
    return sample.src;
  }

  if (typeof sample === "string") {
    return sample;
  }

  return "";
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

function drawImageFitted(ctx, image, rect, fitMode) {
  if (!isDrawableImage(image)) return;

  const iw = image.naturalWidth || image.width;
  const ih = image.naturalHeight || image.height;
  if (!iw || !ih) return;

  if (fitMode === "stretch") {
    ctx.drawImage(image, rect.x, rect.y, rect.w, rect.h);
    return;
  }

  if (fitMode === "contain") {
    const scale = Math.min(rect.w / iw, rect.h / ih);
    const dw = iw * scale;
    const dh = ih * scale;
    const dx = rect.x + (rect.w - dw) * 0.5;
    const dy = rect.y + (rect.h - dh) * 0.5;
    ctx.drawImage(image, dx, dy, dw, dh);
    return;
  }

  const scale = Math.max(rect.w / iw, rect.h / ih);
  const sw = rect.w / scale;
  const sh = rect.h / scale;
  const sx = (iw - sw) * 0.5;
  const sy = (ih - sh) * 0.5;
  ctx.drawImage(image, sx, sy, sw, sh, rect.x, rect.y, rect.w, rect.h);
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
  return point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h;
}

function getDomLocalPoint(root, event) {
  if (!root || !event) return null;
  const rect = root.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;

  const localWidth = Math.max(1, root.clientWidth || rect.width);
  const localHeight = Math.max(1, root.clientHeight || rect.height);
  const scaleX = localWidth / rect.width;
  const scaleY = localHeight / rect.height;
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
    rect,
  };
}

function updateSplitFromPos(node, state, point) {
  const rect = state.compareRect;
  if (!rect) return;

  const viewState = readViewState(node, state);
  let split = 0.5;
  if (viewState.orientation === "horizontal") {
    split = clamp((point.x - rect.x) / rect.w, 0, 1);
  } else {
    split = clamp((point.y - rect.y) / rect.h, 0, 1);
  }

  setSplitValue(node, state, Number(split.toFixed(3)));
  updateDomVisuals(node, state);
}

function previewRectForNode(node) {
  const margin = PREVIEW_MARGIN;
  const nodeW = Number.isFinite(node?.size?.[0]) ? Number(node.size[0]) : DEFAULT_W;
  const nodeH = Number.isFinite(node?.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;

  const x = margin;
  const w = Math.max(1, nodeW - margin * 2);
  const y = resolvePreviewTop(node, nodeH);

  const h = Math.max(1, nodeH - y - margin);
  return { x, y, w, h };
}

function drawCompareCanvas(node, ctx, state) {
  const rect = previewRectForNode(node);

  drawRoundedFill(ctx, rect.x, rect.y, rect.w, rect.h, 10, "rgba(31,31,31,0.98)");
  drawRoundedStroke(ctx, rect.x, rect.y, rect.w, rect.h, 10, "rgba(88,88,88,0.45)", 1);

  const linkedA = resolveLinkedNodeImageSrc(node, "image_a");
  if (linkedA && (!state.images.a || linkedA !== state.images.a.src)) {
    const img = new Image();
    img.src = linkedA;
    state.images.a = img;
  }

  const linkedB = resolveLinkedNodeImageSrc(node, "image_b");
  if (linkedB && (!state.images.b || linkedB !== state.images.b.src)) {
    const img = new Image();
    img.src = linkedB;
    state.images.b = img;
  }

  const viewState = readViewState(node, state);
  const sourceA = viewState.swap ? state.images.b : state.images.a;
  const sourceB = viewState.swap ? state.images.a : state.images.b;
  const infoA = viewState.swap ? state.previewInfo?.b : state.previewInfo?.a;
  const infoB = viewState.swap ? state.previewInfo?.a : state.previewInfo?.b;

  const hasA = isDrawableImage(sourceA);
  const hasB = isDrawableImage(sourceB);
  const layout = resolveCompareLayout(
    rect,
    sourceA,
    sourceB,
    infoA,
    infoB,
    state.compareState,
    viewState.displayMode,
    viewState.fitMode,
  );
  const frame = layout.frame || rect;
  state.compareRect = frame;

  ctx.save();
  roundRectPath(ctx, frame.x, frame.y, frame.w, frame.h, 10);
  ctx.clip();

  drawChecker(ctx, frame);

  if (hasB && layout.b) {
    drawImagePlaced(ctx, sourceB, layout.b, viewState.fitMode);
  }

  if (hasA && layout.a) {
    const split = clamp(viewState.split, 0, 1);
    ctx.save();
    if (viewState.orientation === "horizontal") {
      ctx.beginPath();
      ctx.rect(frame.x, frame.y, frame.w * split, frame.h);
      ctx.clip();
    } else {
      ctx.beginPath();
      ctx.rect(frame.x, frame.y, frame.w, frame.h * split);
      ctx.clip();
    }
    drawImagePlaced(ctx, sourceA, layout.a, viewState.fitMode);
    ctx.restore();
  }

  ctx.restore();

  const split = clamp(viewState.split, 0, 1);
  if (viewState.orientation === "horizontal") {
    const x = frame.x + frame.w * split;
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(x, frame.y);
    ctx.lineTo(x, frame.y + frame.h);
    ctx.stroke();

    ctx.fillStyle = ACCENT_LIME;
    ctx.beginPath();
    ctx.arc(x, frame.y + frame.h * 0.5, 6, 0, Math.PI * 2);
    ctx.fill();
  } else {
    const y = frame.y + frame.h * split;
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(frame.x, y);
    ctx.lineTo(frame.x + frame.w, y);
    ctx.stroke();

    ctx.fillStyle = ACCENT_LIME;
    ctx.beginPath();
    ctx.arc(frame.x + frame.w * 0.5, y, 6, 0, Math.PI * 2);
    ctx.fill();
  }

  if (!hasA || !hasB) {
    const msg = !hasA && !hasB
      ? "Connect both images and queue upstream nodes"
      : !hasA
        ? "Image A preview missing"
        : "Image B preview missing";

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 12px sans-serif";
    ctx.fillStyle = "rgba(224,236,245,0.92)";
    ctx.fillText(msg, rect.x + rect.w * 0.5, rect.y + rect.h * 0.5);
  }
}

function createDomState(node, state) {
  const initialMinPreviewH = resolvePreviewMinHeight(node);
  const root = document.createElement("div");
  root.style.cssText = [
    "position:relative",
    "width:100%",
    "height:100%",
    "min-height:0",
    "--comfy-widget-height:100%",
    `--comfy-widget-min-height:${initialMinPreviewH}px`,
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
  imageB.alt = "B";
  imageB.draggable = false;
  imageB.style.cssText = [
    "position:absolute",
    "left:0",
    "top:0",
    "width:1px",
    "height:1px",
    "object-fit:fill",
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
  imageA.alt = "A";
  imageA.draggable = false;
  imageA.style.cssText = [
    "position:absolute",
    "left:0",
    "top:0",
    "width:1px",
    "height:1px",
    "object-fit:fill",
    "display:none",
    "pointer-events:none",
  ].join(";");

  const line = document.createElement("div");
  line.style.cssText = [
    "position:absolute",
    "background:rgba(255,255,255,0.95)",
    "z-index:6",
    "pointer-events:none",
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
  ].join(";");

  const badgeA = document.createElement("div");
  badgeA.textContent = "A";
  badgeA.style.cssText = [
    "position:absolute",
    "top:8px",
    "left:8px",
    "width:22px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
  ].join(";");

  const badgeB = document.createElement("div");
  badgeB.textContent = "B";
  badgeB.style.cssText = [
    "position:absolute",
    "top:8px",
    "right:8px",
    "width:22px",
    "height:16px",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "border-radius:8px",
    "font:700 10px sans-serif",
    "color:rgba(244,248,252,0.92)",
    "background:var(--mkr-dark-label, #1f1f1f)",
    "pointer-events:none",
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

  state.dom = {
    root,
    imageA,
    imageB,
    clip,
    line,
    handle,
    badgeA,
    badgeB,
    status,
  };

  const requestLayoutRefresh = () => {
    updateDomVisuals(node, state);
    queueRedraw(node);
  };
  imageA.addEventListener("load", requestLayoutRefresh);
  imageB.addEventListener("load", requestLayoutRefresh);

  const splitFromEvent = (event) => {
    const point = getDomLocalPoint(root, event);
    if (!point) return;
    const frame = state.compareRect || { x: 0, y: 0, w: Math.max(1, root.clientWidth), h: Math.max(1, root.clientHeight) };
    const viewState = readViewState(node, state);

    let split = 0.5;
    if (viewState.orientation === "horizontal") {
      split = clamp((point.x - frame.x) / Math.max(1, frame.w), 0, 1);
    } else {
      split = clamp((point.y - frame.y) / Math.max(1, frame.h), 0, 1);
    }

    setSplitValue(node, state, Number(split.toFixed(3)));
    updateDomVisuals(node, state);
  };

  let dragging = false;
  root.addEventListener("pointerdown", (event) => {
    const point = getDomLocalPoint(root, event);
    const frame = state.compareRect || { x: 0, y: 0, w: Math.max(1, root.clientWidth), h: Math.max(1, root.clientHeight) };
    if (!point || !pointInRect(point, frame)) {
      return;
    }
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

  const widget = node.addDOMWidget?.("mkr_axb_compare_ui", "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => resolvePreviewMinHeight(node),
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

function chooseDisplayedSources(node, state) {
  const viewState = readViewState(node, state);
  const linkedA = resolveLinkedNodeImageSrc(node, "image_a");
  const linkedB = resolveLinkedNodeImageSrc(node, "image_b");

  const srcA = state.previewSrc.a || linkedA || "";
  const srcB = state.previewSrc.b || linkedB || "";

  if (viewState.swap) {
    return {
      viewState,
      srcA: srcB,
      srcB: srcA,
      hasA: !!srcB,
      hasB: !!srcA,
    };
  }

  return {
    viewState,
    srcA,
    srcB,
    hasA: !!srcA,
    hasB: !!srcB,
  };
}

function normalizeAxBWidgetStack(node, state) {
  if (!node || !Array.isArray(node.widgets) || !state?.domWidget) return false;
  let changed = false;

  const domWidgets = node.widgets.filter((w) => w && String(w.name || "") === "mkr_axb_compare_ui");
  if (domWidgets.length > 1) {
    node.widgets = node.widgets.filter((w) => String(w?.name || "") !== "mkr_axb_compare_ui" || w === state.domWidget);
    changed = true;
  }

  if (state.domWidget && Array.isArray(node.widgets)) {
    const idx = node.widgets.indexOf(state.domWidget);
    if (idx > -1 && idx !== node.widgets.length - 1) {
      node.widgets.splice(idx, 1);
      node.widgets.push(state.domWidget);
      changed = true;
    }
  }

  return changed;
}

function trySetWidgetNumber(widget, key, value) {
  if (!widget) return false;
  const current = Number(widget[key]);
  if (Number.isFinite(current) && Math.abs(current - value) <= 0.5) {
    return false;
  }
  try {
    widget[key] = value;
    return true;
  } catch (error) {
    return false;
  }
}

function trySetWidgetY(widget, value) {
  if (!widget) return false;
  let changed = false;
  changed = trySetWidgetNumber(widget, "y", value) || changed;
  changed = trySetWidgetNumber(widget, "last_y", value) || changed;
  changed = trySetWidgetNumber(widget, "_y", value) || changed;
  return changed;
}

function tightenPreviewWidgetLayout(node, state) {
  const domWidget = state?.domWidget;
  if (!domWidget || !Array.isArray(node?.widgets)) return;

  let changed = normalizeAxBWidgetStack(node, state);
  const nodeH = Number.isFinite(node?.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;
  const targetY = resolvePreviewTop(node, nodeH);

  changed = trySetWidgetY(domWidget, targetY) || changed;
  if (state?.dom?.root) {
    const minPx = `${resolvePreviewMinHeight(node)}px`;
    if (state.dom.root.style.getPropertyValue("--comfy-widget-min-height") !== minPx) {
      state.dom.root.style.setProperty("--comfy-widget-min-height", minPx);
      changed = true;
    }
  }

  if (changed) {
    queueRedraw(node);
  }
}

function updateDomVisuals(node, state) {
  const dom = state.dom;
  if (!dom) return;

  const { viewState, srcA, srcB, hasA, hasB } = chooseDisplayedSources(node, state);
  const infoA = viewState.swap ? state.previewInfo?.b : state.previewInfo?.a;
  const infoB = viewState.swap ? state.previewInfo?.a : state.previewInfo?.b;

  if (srcA) {
    if (dom.imageA.src !== srcA) dom.imageA.src = srcA;
    dom.imageA.style.display = "block";
  } else {
    dom.imageA.removeAttribute("src");
    dom.imageA.style.display = "none";
  }
  if (srcB) {
    if (dom.imageB.src !== srcB) dom.imageB.src = srcB;
    dom.imageB.style.display = "block";
  } else {
    dom.imageB.removeAttribute("src");
    dom.imageB.style.display = "none";
  }

  const rootWidth = Math.max(1, Math.round(dom.root.clientWidth || 0));
  const rootHeight = Math.max(1, Math.round(dom.root.clientHeight || 0));
  const layout = resolveCompareLayout(
    { x: 0, y: 0, w: rootWidth, h: rootHeight },
    dom.imageA,
    dom.imageB,
    infoA,
    infoB,
    state.compareState,
    viewState.displayMode,
    viewState.fitMode,
  );
  const frame = layout.frame || { x: 0, y: 0, w: rootWidth, h: rootHeight };

  const applyPlacement = (element, placement) => {
    if (!element) return;
    if (!placement) {
      element.style.left = "0px";
      element.style.top = "0px";
      element.style.width = "1px";
      element.style.height = "1px";
      element.style.objectFit = "fill";
      return;
    }
    element.style.left = `${placement.x}px`;
    element.style.top = `${placement.y}px`;
    element.style.width = `${placement.w}px`;
    element.style.height = `${placement.h}px`;
    element.style.objectFit = placement.fitMode === "cover" ? "cover" : placement.fitMode === "stretch" ? "fill" : "contain";
  };

  applyPlacement(dom.imageB, layout.b);
  dom.clip.style.left = `${frame.x}px`;
  dom.clip.style.top = `${frame.y}px`;
  dom.clip.style.right = "auto";
  dom.clip.style.bottom = "auto";
  dom.clip.style.width = `${frame.w}px`;
  dom.clip.style.height = `${frame.h}px`;
  applyPlacement(dom.imageA, layout.a ? {
    x: layout.a.x - frame.x,
    y: layout.a.y - frame.y,
    w: layout.a.w,
    h: layout.a.h,
    fitMode: layout.a.fitMode,
  } : null);

  state.compareRect = frame;
  const split = clamp(viewState.split, 0, 1);
  const splitPercent = split * 100;
  const hasBadges = !!dom.badgeA && !!dom.badgeB;
  if (viewState.orientation === "horizontal") {
    dom.clip.style.clipPath = `inset(0 ${Math.max(0, frame.w - frame.w * split)}px 0 0)`;
    dom.line.style.left = `${frame.x + frame.w * split}px`;
    dom.line.style.top = `${frame.y}px`;
    dom.line.style.bottom = "auto";
    dom.line.style.right = "auto";
    dom.line.style.width = "0.5px";
    dom.line.style.height = `${frame.h}px`;
    dom.line.style.transform = "translateX(-0.25px)";
    dom.handle.style.left = `${frame.x + frame.w * split}px`;
    dom.handle.style.top = `${frame.y + frame.h * 0.5}px`;
    dom.handle.style.background = ACCENT_LIME;
    if (hasBadges) {
      dom.badgeA.style.top = `${frame.y + 8}px`;
      dom.badgeA.style.bottom = "auto";
      dom.badgeA.style.left = `${frame.x + 8}px`;
      dom.badgeA.style.right = "auto";
      dom.badgeB.style.top = `${frame.y + 8}px`;
      dom.badgeB.style.bottom = "auto";
      dom.badgeB.style.right = `${Math.max(8, rootWidth - frame.x - frame.w + 8)}px`;
      dom.badgeB.style.left = "auto";
    }
  } else {
    dom.clip.style.clipPath = `inset(0 0 ${Math.max(0, frame.h - frame.h * split)}px 0)`;
    dom.line.style.top = `${frame.y + frame.h * split}px`;
    dom.line.style.left = `${frame.x}px`;
    dom.line.style.right = "auto";
    dom.line.style.bottom = "auto";
    dom.line.style.height = "0.5px";
    dom.line.style.width = `${frame.w}px`;
    dom.line.style.transform = "translateY(-0.25px)";
    dom.handle.style.left = `${frame.x + frame.w * 0.5}px`;
    dom.handle.style.top = `${frame.y + frame.h * split}px`;
    dom.handle.style.background = ACCENT_LIME;
    if (hasBadges) {
      dom.badgeA.style.top = `${frame.y + 8}px`;
      dom.badgeA.style.bottom = "auto";
      dom.badgeA.style.left = `${frame.x + 8}px`;
      dom.badgeA.style.right = "auto";
      dom.badgeB.style.top = "auto";
      dom.badgeB.style.bottom = `${Math.max(8, rootHeight - frame.y - frame.h + 8)}px`;
      dom.badgeB.style.right = `${Math.max(8, rootWidth - frame.x - frame.w + 8)}px`;
      dom.badgeB.style.left = "auto";
    }
  }

  if (!hasA || !hasB) {
    dom.status.style.display = "block";
    dom.status.textContent = !hasA && !hasB
      ? "Connect both images and queue upstream nodes"
      : !hasA
        ? "Image A preview missing"
        : "Image B preview missing";
  } else {
    dom.status.style.display = "none";
  }

  tightenPreviewWidgetLayout(node, state);
}

function applyOutputMessage(node, state, message) {
  const previewA = message?.a_preview?.[0] ?? message?.ui?.a_preview?.[0] ?? null;
  const previewB = message?.b_preview?.[0] ?? message?.ui?.b_preview?.[0] ?? null;

  if (previewA) loadPreviewIntoState(node, state, "a", previewA);
  if (previewB) loadPreviewIntoState(node, state, "b", previewB);

  const compareState = message?.compare_state?.[0] ?? message?.ui?.compare_state?.[0] ?? null;
  if (compareState && typeof compareState === "object") {
    state.compareState = { ...(state.compareState || {}), ...compareState };
    node.properties = node.properties || {};
    if (compareState.orientation !== undefined && node.properties.orientation === undefined && !getWidget(node, "orientation")) {
      node.properties.orientation = String(compareState.orientation);
    }
    if (compareState.split_percent !== undefined && node.properties[INTERNAL_SPLIT_PROP] === undefined) {
      setSplitValue(node, state, numberValue(compareState.split_percent, readSplitValue(node, state)));
    }
    if (compareState.fit_mode !== undefined && node.properties.fit_mode === undefined) {
      node.properties.fit_mode = String(compareState.fit_mode || "contain").toLowerCase();
    }
    if (compareState.swap_inputs !== undefined && node.properties.swap_inputs === undefined) {
      node.properties.swap_inputs = boolValue(compareState.swap_inputs, false);
    }
    if (compareState.display_mode !== undefined && node.properties.display_mode === undefined) {
      node.properties.display_mode = String(compareState.display_mode || "actual_definition");
    }
  }

  updateDomVisuals(node, state);
  queueRedraw(node);
}

function ensureCanvasHooks(node, state) {
  if (node.__mkrAxBCanvasAttached) return;
  node.__mkrAxBCanvasAttached = true;

  const originalDraw = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    if (typeof originalDraw === "function") {
      originalDraw.apply(this, arguments);
    }
    if (this.flags?.collapsed) return;
    // DOM widget is primary in Node 2.0; draw canvas fallback when DOM isn't mounted/visible.
    const domMounted = !!(
      state.dom &&
      state.domWidget &&
      state.dom.root &&
      state.dom.root.isConnected &&
      state.dom.root.getClientRects &&
      state.dom.root.getClientRects().length
    );
    if (domMounted) return;
    try {
      this.__mkrAxBError = "";
      drawCompareCanvas(this, ctx, state);
    } catch (error) {
      this.__mkrAxBError = String(error?.message || error || "unknown draw error");
      const msg = `AxB draw error: ${this.__mkrAxBError}`;
      ctx.save();
      ctx.fillStyle = "rgba(190, 46, 46, 0.95)";
      ctx.font = "700 11px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(msg, 10, Math.max(10, (this.size?.[1] || 200) - 24));
      ctx.restore();
    }
  };

  const originalMouseDown = node.onMouseDown;
  node.onMouseDown = function onMouseDown(event, pos) {
    const point = getLocalPos(this, event, pos);
    if (point && pointInRect(point, state.compareRect)) {
      state.dragging = true;
      updateSplitFromPos(this, state, point);
      queueRedraw(this);
      return true;
    }

    if (typeof originalMouseDown === "function") {
      return originalMouseDown.apply(this, arguments);
    }
    return false;
  };

  const originalMouseMove = node.onMouseMove;
  node.onMouseMove = function onMouseMove(event, pos) {
    if (state.dragging) {
      const point = getLocalPos(this, event, pos);
      if (point) {
        updateSplitFromPos(this, state, point);
        queueRedraw(this);
        return true;
      }
    }

    if (typeof originalMouseMove === "function") {
      return originalMouseMove.apply(this, arguments);
    }
    return false;
  };

  const originalMouseUp = node.onMouseUp;
  node.onMouseUp = function onMouseUp() {
    state.dragging = false;
    if (typeof originalMouseUp === "function") {
      return originalMouseUp.apply(this, arguments);
    }
    return false;
  };

  const originalMouseLeave = node.onMouseLeave;
  node.onMouseLeave = function onMouseLeave() {
    state.dragging = false;
    if (typeof originalMouseLeave === "function") {
      return originalMouseLeave.apply(this, arguments);
    }
    return false;
  };
}

function ensureCompareUI(node) {
  if (!node) return;
  migrateAxBNodeRuntime(node);
  if (node.__mkrAxBUIAttached && !needsAxBRuntimeUpgrade(node)) return;
  sanitizeAxBNodeTitle(node);
  let hiddenLegacyControls = hideLegacyAxBControls(node);
  if (removeLegacyAxBInputs(node)) {
    hiddenLegacyControls = true;
  }
  node.__mkrAxBUIAttached = true;
  node.__mkrAxBRuntimeVersion = AXB_RUNTIME_VERSION;
  node.resizable = true;

  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [DEFAULT_W, DEFAULT_H];
  }
  if (Number.isFinite(node.size?.[1]) && Number(node.size[1]) > 1200) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), DEFAULT_H];
  }
  const minPreviewH = resolvePreviewMinHeight(node);
  const currentH = Number.isFinite(node.size?.[1]) ? Number(node.size[1]) : DEFAULT_H;
  const topForMin = resolvePreviewTop(node, Math.max(currentH, DEFAULT_H));
  const minNodeH = Math.round(topForMin + minPreviewH + PREVIEW_MARGIN);
  if (currentH < minNodeH) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), minNodeH];
  }

  const state = {
    images: {
      a: null,
      b: null,
    },
    compareState: null,
    previewInfo: {
      a: null,
      b: null,
    },
    previewSrc: {
      a: "",
      b: "",
    },
    compareRect: null,
    dragging: false,
    split: readSplitValue(node, null),
    layoutSig: "",
    dom: null,
    domWidget: null,
  };
  node.__mkrAxBState = state;

  if (ENABLE_DOM_WIDGET && typeof node.addDOMWidget === "function") {
    createDomState(node, state);
  }

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
    if (removeLegacyAxBInputs(this)) {
      queueRedraw(this);
    }

    const hasA = this.inputs?.some((entry) => entry.name === "image_a" && entry.link);
    const hasB = this.inputs?.some((entry) => entry.name === "image_b" && entry.link);
    if (!hasA) {
      state.images.a = null;
      state.previewInfo.a = null;
      state.previewSrc.a = "";
    }
    if (!hasB) {
      state.images.b = null;
      state.previewInfo.b = null;
      state.previewSrc.b = "";
    }
    if (!hasA || !hasB) {
      state.compareState = null;
    }

    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    if (typeof originalConfigure === "function") {
      originalConfigure.apply(this, arguments);
    }
    if (removeLegacyAxBInputs(this)) {
      queueRedraw(this);
    }
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    if (typeof originalResize === "function") {
      originalResize.apply(this, arguments);
    }
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  updateDomVisuals(node, state);
  if (hiddenLegacyControls) {
    queueRedraw(node);
  }
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
    if (String(node.id) === raw || String(node.id) === String(tail)) {
      return node;
    }
  }

  return null;
}

function attachAllKnownNodes() {
  const app = getApp();
  const nodes = app?.graph?._nodes || [];
  for (const node of nodes) {
    sanitizeAxBNodeTitle(node);
    scheduleMkrBadgeRefresh(node);
    if (looksLikeAxBCompareNode(node) || isAxBNode(node)) {
      removeLegacyAxBInputs(node);
      if (!node.__mkrAxBUIAttached || needsAxBRuntimeUpgrade(node)) {
        ensureCompareUI(node);
      }
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
      if (!isAxBNodeDef(nodeData)) return;
      sanitizeAxBNodeDataInputs(nodeData);

      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function onNodeCreated() {
        if (typeof originalOnNodeCreated === "function") {
          originalOnNodeCreated.apply(this, arguments);
        }
        ensureCompareUI(this);
      };
    },

    async nodeCreated(node) {
      scheduleMkrBadgeRefresh(node);

      if (isAxBNode(node) || looksLikeAxBCompareNode(node)) {
        ensureCompareUI(node);
        return;
      }

      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (isAxBNode(node) || looksLikeAxBCompareNode(node)) {
          ensureCompareUI(node);
          clearInterval(timer);
          return;
        }
        if (tries >= 30) {
          clearInterval(timer);
        }
      }, 100);
    },

    loadedGraphNode(node) {
      scheduleMkrBadgeRefresh(node);
      if (isAxBNode(node) || looksLikeAxBCompareNode(node)) {
        ensureCompareUI(node);
      }
    },

    onNodeOutputsUpdated(nodeOutputs) {
      if (!nodeOutputs || typeof nodeOutputs !== "object") return;

      for (const [locatorId, output] of Object.entries(nodeOutputs)) {
        if (!output || typeof output !== "object") continue;
        if (!("a_preview" in output || "b_preview" in output || "compare_state" in output)) continue;

        const node = findNodeByLocator(locatorId);
        if (!node || !node.__mkrAxBState) continue;
        if (!(isAxBNode(node) || looksLikeAxBCompareNode(node))) continue;

        applyOutputMessage(node, node.__mkrAxBState, output);
      }
    },
  };
}

function registerWhenReady(tries = 0) {
  if (registered) return;

  ensureAccentStylesheet();

  const app = getApp();
  if (!app?.registerExtension) {
    if (tries < 400) {
      setTimeout(() => registerWhenReady(tries + 1), 100);
    }
    return;
  }

  app.registerExtension(buildExtension());
  registered = true;
}

registerWhenReady();
