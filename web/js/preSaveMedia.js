import { app } from "../../../scripts/app.js";

const EXT = "mkr.presave.media";
const DOM_WIDGET_NAME = "mkr_presave_media_ui";
const DEFAULT_W = 360;
const DEFAULT_H = 620;
const PREVIEW_MIN_H = 280;
const PREVIEW_MARGIN = 8;
const ACCENT_STYLE_ID = "mkrshift-accent-style";
const ACCENT_STYLE_CSS = `
:root {
  --mkr-accent-lime: #d2fd51;
  --mkr-dark-label: #1f1f1f;
  --mkr-dark-label-highlight: #2e2e2e;
}
`;

const SAVE_OPTION_WIDGETS = {
  video: [
    "output_format",
    "filename_prefix",
    "subfolder",
    "overwrite",
    "animation_fps",
    "webp_quality",
    "animation_loop",
    "filename_label",
  ],
  audio: ["output_format", "filename_prefix", "subfolder", "overwrite", "filename_label"],
};

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

function kindFromToken(value) {
  const token = normalizeToken(value);
  if (token === "mkrpresavevideo" || token === "presavevideo") return "video";
  if (token === "mkrpresaveaudio" || token === "presaveaudio") return "audio";
  return "";
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

function nodeKind(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
    node?.constructor?.title,
  ].filter(Boolean);

  for (const candidate of candidates) {
    const kind = kindFromToken(candidate);
    if (kind) return kind;
  }

  if (hasInput(node, "video") && hasWidget(node, "preview_only") && hasWidget(node, "output_format")) return "video";
  if (hasInput(node, "audio") && hasWidget(node, "preview_only") && hasWidget(node, "output_format")) return "audio";
  return "";
}

function nodeDefKind(nodeData) {
  const candidates = [nodeData?.name, nodeData?.display_name, nodeData?.type, nodeData?.category].filter(Boolean);
  for (const candidate of candidates) {
    const kind = kindFromToken(candidate);
    if (kind) return kind;
  }
  return "";
}

function isMediaPreSaveNode(node) {
  return !!nodeKind(node);
}

function isMediaPreSaveNodeDef(nodeData) {
  return !!nodeDefKind(nodeData);
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
  if (Array.isArray(node.imgs) && node.imgs.length) node.imgs = [];
  if (Array.isArray(node.images) && node.images.length) node.images = [];
  if (Array.isArray(node.animatedImages) && node.animatedImages.length) node.animatedImages = [];
  if (Number.isFinite(node.imageIndex)) node.imageIndex = 0;
  if (typeof node.preview === "object" && node.preview) node.preview = null;
}

function setWidgetHidden(widget, hidden) {
  if (!widget) return false;
  const value = !!hidden;
  if (widget.hidden === value) return false;
  widget.hidden = value;
  return true;
}

function readWidgetOrProperty(node, name, fallback) {
  const widget = getWidget(node, name);
  if (widget && widget.value !== undefined) return widget.value;
  const prop = node?.properties?.[name];
  if (prop !== undefined) return prop;
  return fallback;
}

function setWidgetOrPropertySilent(node, name, value) {
  const widget = getWidget(node, name);
  if (widget) {
    widget.value = value;
    return;
  }
  node.properties = node.properties || {};
  node.properties[name] = value;
}

function sanitizeWidgetValues(node, kind) {
  if (!node || !kind) return false;
  let changed = false;

  const preview = boolValue(readWidgetOrProperty(node, "preview_only", true), true);
  if (boolValue(readWidgetOrProperty(node, "preview_only", true), true) !== preview) changed = true;
  setWidgetOrPropertySilent(node, "preview_only", preview);

  const outputAllowed = kind === "video" ? ["auto", "mp4", "mov", "webm", "gif", "webp"] : ["auto", "wav", "mp3", "flac", "ogg"];
  const rawOutput = String(readWidgetOrProperty(node, "output_format", "auto") || "auto").trim().toLowerCase();
  const output = outputAllowed.includes(rawOutput) ? rawOutput : "auto";
  if (rawOutput !== output) changed = true;
  setWidgetOrPropertySilent(node, "output_format", output);

  const sanitizeInt = (name, fallback, min, max) => {
    const raw = Number.parseInt(String(readWidgetOrProperty(node, name, fallback)), 10);
    const value = Number.isFinite(raw) ? clamp(raw, min, max) : fallback;
    if (Number(raw) !== Number(value)) changed = true;
    setWidgetOrPropertySilent(node, name, value);
  };

  if (kind === "video") {
    sanitizeInt("animation_fps", 24, 1, 120);
    sanitizeInt("webp_quality", 90, 1, 100);
    sanitizeInt("animation_loop", 0, 0, 1000);
  }

  const prefix = String(readWidgetOrProperty(node, "filename_prefix", kind === "video" ? "MKR_video" : "MKR_audio") || "");
  const subfolder = String(readWidgetOrProperty(node, "subfolder", "") || "");
  const label = String(readWidgetOrProperty(node, "filename_label", "") || "");

  setWidgetOrPropertySilent(node, "filename_prefix", prefix);
  setWidgetOrPropertySilent(node, "subfolder", subfolder);
  setWidgetOrPropertySilent(node, "filename_label", label);

  return changed;
}

function syncWidgetVisibility(node, kind) {
  if (!node || !kind) return false;
  let changed = false;
  const previewOnly = boolValue(readWidgetOrProperty(node, "preview_only", true), true);
  const targets = SAVE_OPTION_WIDGETS[kind] || [];
  for (const name of targets) {
    changed = setWidgetHidden(getWidget(node, name), previewOnly) || changed;
  }
  return changed;
}

function normalizeLayout(node, state) {
  if (!node || !state?.domWidget || !Array.isArray(node.widgets)) return false;
  let changed = false;

  const duplicates = node.widgets.filter((w) => String(w?.name || "") === DOM_WIDGET_NAME);
  if (duplicates.length > 1) {
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

function readWidgetHeight(widget, width) {
  let height = Number.isFinite(widget?.computedHeight) ? Number(widget.computedHeight) : 24;
  try {
    if (typeof widget?.computeSize === "function") {
      const size = widget.computeSize(width);
      if (Array.isArray(size) && Number.isFinite(size[1])) {
        height = Number(size[1]);
      }
    }
  } catch (error) {}
  return clamp(height, 18, 84);
}

function setWidgetY(widget, y) {
  let changed = false;
  const keys = ["y", "last_y", "_y"];
  for (const key of keys) {
    const current = Number(widget?.[key]);
    if (Number.isFinite(current) && Math.abs(current - y) <= 0.5) continue;
    try {
      widget[key] = y;
      changed = true;
    } catch (error) {}
  }
  return changed;
}

function layoutDomWidget(node, state) {
  if (!state?.domWidget) return;
  let changed = normalizeLayout(node, state);

  const width = Number(node?.size?.[0]) || DEFAULT_W;
  let y = 44;

  for (const widget of node.widgets || []) {
    if (!widget || widget === state.domWidget) continue;
    if (String(widget?.name || "") === DOM_WIDGET_NAME) continue;
    if (widget.hidden) continue;

    changed = setWidgetY(widget, y) || changed;
    y += readWidgetHeight(widget, width) + 4;
  }

  const top = Math.round(Math.max(72, y + 6));
  changed = setWidgetY(state.domWidget, top) || changed;

  const minNodeH = Math.round(top + PREVIEW_MIN_H + PREVIEW_MARGIN);
  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [DEFAULT_W, Math.max(DEFAULT_H, minNodeH)];
    changed = true;
  } else if (Number(node.size[1] || 0) < minNodeH) {
    node.size = [Math.max(DEFAULT_W, Number(node.size[0]) || DEFAULT_W), minNodeH];
    changed = true;
  }

  if (state.dom?.root) {
    const minHeight = `${PREVIEW_MIN_H}px`;
    if (state.dom.root.style.getPropertyValue("--comfy-widget-min-height") !== minHeight) {
      state.dom.root.style.setProperty("--comfy-widget-min-height", minHeight);
      changed = true;
    }
  }

  if (changed) queueRedraw(node);
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

function toUrlList(entries) {
  if (!Array.isArray(entries)) return [];
  const stamp = Date.now();
  return entries
    .map((entry, idx) => {
      const base = buildViewUrl(entry);
      if (!base) return "";
      const joiner = base.includes("?") ? "&" : "?";
      return `${base}${joiner}_mkrpresavemedia=${stamp}_${idx}`;
    })
    .filter(Boolean);
}

function setSource(el, url) {
  if (!el) return;
  if (!url) {
    el.pause?.();
    el.removeAttribute("src");
    el.load?.();
    return;
  }
  if (el.src !== url) {
    el.src = url;
    el.load?.();
  }
}

function createAudioBars() {
  const bars = document.createElement("div");
  bars.style.cssText = [
    "position:absolute",
    "left:16px",
    "right:16px",
    "top:20px",
    "height:68px",
    "display:flex",
    "align-items:flex-end",
    "justify-content:space-between",
    "gap:6px",
  ].join(";");

  for (let i = 0; i < 14; i += 1) {
    const bar = document.createElement("div");
    const delay = (i * 0.08).toFixed(2);
    const duration = (0.95 + (i % 5) * 0.07).toFixed(2);
    bar.style.cssText = [
      "flex:1",
      "min-width:4px",
      "height:18px",
      "border-radius:5px 5px 2px 2px",
      "background:linear-gradient(180deg, var(--mkr-accent-lime, #D2FD51), rgba(210,253,81,0.28))",
      "transform-origin:bottom center",
      `animation:mkrAudioPulse ${duration}s ease-in-out ${delay}s infinite`,
      "animation-play-state:paused",
    ].join(";");
    bars.appendChild(bar);
  }

  return bars;
}

function ensureMediaAnimationStyles() {
  const id = "mkr-presave-media-anim";
  if (document.getElementById(id)) return;
  const style = document.createElement("style");
  style.id = id;
  style.textContent = `
@keyframes mkrAudioPulse {
  0% { transform: scaleY(0.3); opacity: 0.5; }
  50% { transform: scaleY(1.0); opacity: 1.0; }
  100% { transform: scaleY(0.35); opacity: 0.55; }
}
`;
  document.head.appendChild(style);
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

  const left = document.createElement("div");
  left.style.cssText = "display:flex;align-items:center;gap:8px;";

  const kindBadge = document.createElement("div");
  kindBadge.textContent = state.kind === "video" ? "VIDEO" : "AUDIO";
  kindBadge.style.cssText = [
    "padding:2px 7px",
    "border-radius:999px",
    "font:700 10px sans-serif",
    "letter-spacing:0.4px",
    "background:rgba(210,253,81,0.18)",
    "color:var(--mkr-accent-lime, #D2FD51)",
    "border:1px solid rgba(210,253,81,0.45)",
  ].join(";");

  const modeBadge = document.createElement("div");
  modeBadge.textContent = "Preview mode";
  modeBadge.style.cssText = "font:600 11px sans-serif;color:rgba(226,236,247,0.88);";

  left.appendChild(kindBadge);
  toolbar.appendChild(left);
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
    "background:#151515",
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
    "z-index:5",
  ].join(";");
  status.textContent = "Queue node to generate preview.";

  let mediaEl = null;
  let barsWrap = null;

  if (state.kind === "video") {
    const video = document.createElement("video");
    video.style.cssText = [
      "position:absolute",
      "inset:0",
      "width:100%",
      "height:100%",
      "object-fit:contain",
      "background:#090909",
    ].join(";");
    video.muted = true;
    video.loop = true;
    video.controls = true;
    video.playsInline = true;
    stage.appendChild(video);
    mediaEl = video;
  } else {
    ensureMediaAnimationStyles();

    const audioShell = document.createElement("div");
    audioShell.style.cssText = [
      "position:absolute",
      "inset:0",
      "display:flex",
      "flex-direction:column",
      "justify-content:flex-end",
      "padding:10px 10px 14px",
      "box-sizing:border-box",
      "background:radial-gradient(circle at 30% 20%, rgba(210,253,81,0.12), transparent 56%), linear-gradient(160deg, #121212, #171717)",
    ].join(";");

    barsWrap = createAudioBars();
    audioShell.appendChild(barsWrap);

    const label = document.createElement("div");
    label.textContent = "Audio stream ready";
    label.style.cssText = "position:absolute;left:16px;right:16px;top:95px;font:600 12px sans-serif;color:rgba(226,236,247,0.78);";
    audioShell.appendChild(label);

    const audioEl = document.createElement("audio");
    audioEl.controls = true;
    audioEl.preload = "metadata";
    audioEl.style.cssText = [
      "width:100%",
      "margin-top:auto",
      "filter:saturate(0.98)",
      "border-radius:8px",
    ].join(";");

    audioShell.appendChild(audioEl);
    stage.appendChild(audioShell);
    mediaEl = audioEl;
  }

  stage.appendChild(status);

  root.appendChild(toolbar);
  root.appendChild(stage);

  const widget = node.addDOMWidget?.(DOM_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => PREVIEW_MIN_H,
    getMaxHeight: () => Number.POSITIVE_INFINITY,
  });

  if (!widget) return false;
  widget.serialize = false;

  state.dom = {
    root,
    stage,
    status,
    modeBadge,
    mediaEl,
    barsWrap,
  };
  state.domWidget = widget;

  if (state.kind === "audio" && mediaEl) {
    const syncBars = () => {
      if (!state.dom?.barsWrap) return;
      const running = !mediaEl.paused && !mediaEl.ended && !!mediaEl.src;
      for (const child of Array.from(state.dom.barsWrap.children)) {
        child.style.animationPlayState = running ? "running" : "paused";
      }
    };
    mediaEl.addEventListener("play", syncBars);
    mediaEl.addEventListener("pause", syncBars);
    mediaEl.addEventListener("ended", syncBars);
  }

  return true;
}

function updateDomVisuals(node, state) {
  const dom = state?.dom;
  if (!dom) return;

  const previewUrl = String(state.previewUrl || "");
  const hasPreview = !!previewUrl;

  if (state.kind === "video") {
    const video = dom.mediaEl;
    if (video) {
      setSource(video, previewUrl);
      if (hasPreview && video.paused) {
        video.play?.().catch(() => {});
      }
    }
  } else {
    const audio = dom.mediaEl;
    if (audio) {
      setSource(audio, previewUrl);
    }
  }

  dom.status.style.display = hasPreview ? "none" : "block";
  dom.status.textContent = hasPreview ? "" : "Queue node to generate preview.";

  dom.modeBadge.textContent = state.previewOnly ? "Preview mode" : "Save mode";
  dom.modeBadge.style.color = state.previewOnly ? "rgba(226,236,247,0.88)" : "var(--mkr-accent-lime, #D2FD51)";
  layoutDomWidget(node, state);
}

function applyOutputMessage(node, state, message) {
  suppressGenericPreviewBuffers(node);

  const mediaState = message?.presave_media_state?.[0] ?? message?.ui?.presave_media_state?.[0] ?? null;
  const saveSummary = message?.save_summary?.[0] ?? message?.ui?.save_summary?.[0] ?? null;

  let entries = [];
  if (state.kind === "video") {
    entries = message?.presave_video_preview ?? message?.ui?.presave_video_preview ?? [];
  } else {
    entries = message?.presave_audio_preview ?? message?.ui?.presave_audio_preview ?? [];
  }

  const urls = toUrlList(entries);
  state.previewUrl = urls[0] || "";

  if (mediaState && typeof mediaState === "object") {
    state.previewOnly = !!mediaState.preview_only;
  }

  if (saveSummary && typeof saveSummary === "object") {
    state.saveSummary = saveSummary;
  } else {
    state.saveSummary = {};
  }

  sanitizeWidgetValues(node, state.kind);
  syncWidgetVisibility(node, state.kind);
  updateDomVisuals(node, state);
  queueRedraw(node);
}

function ensureMediaUI(node) {
  if (!node) return;
  const kind = nodeKind(node);
  if (!kind) return;

  if (node.__mkrPreSaveMediaUIAttached) {
    sanitizeWidgetValues(node, kind);
    syncWidgetVisibility(node, kind);
    suppressGenericPreviewBuffers(node);
    const state = node.__mkrPreSaveMediaState;
    if (state) updateDomVisuals(node, state);
    queueRedraw(node);
    return;
  }

  node.__mkrPreSaveMediaUIAttached = true;
  node.resizable = true;
  if (!Array.isArray(node.size) || node.size.length < 2) node.size = [DEFAULT_W, DEFAULT_H];

  const state = {
    kind,
    previewOnly: boolValue(readWidgetOrProperty(node, "preview_only", true), true),
    previewUrl: "",
    saveSummary: {},
    dom: null,
    domWidget: null,
  };
  node.__mkrPreSaveMediaState = state;

  sanitizeWidgetValues(node, kind);
  syncWidgetVisibility(node, kind);

  if (typeof node.addDOMWidget === "function") {
    createDomState(node, state);
  }

  const previewOnlyWidget = getWidget(node, "preview_only");
  if (previewOnlyWidget && !previewOnlyWidget.__mkrMediaHooked) {
    const original = previewOnlyWidget.callback;
    previewOnlyWidget.callback = function previewOnlyCallback(value) {
      if (typeof original === "function") {
        original.apply(this, arguments);
      }
      state.previewOnly = boolValue(value, state.previewOnly);
      syncWidgetVisibility(node, kind);
      updateDomVisuals(node, state);
      queueRedraw(node);
    };
    previewOnlyWidget.__mkrMediaHooked = true;
  }

  const originalDrawBg = node.onDrawBackground;
  node.onDrawBackground = function onDrawBackground() {
    suppressGenericPreviewBuffers(this);
    if (typeof originalDrawBg === "function") originalDrawBg.apply(this, arguments);
  };

  const originalDrawFg = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground() {
    suppressGenericPreviewBuffers(this);
    if (typeof originalDrawFg === "function") originalDrawFg.apply(this, arguments);
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
    sanitizeWidgetValues(this, kind);
    syncWidgetVisibility(this, kind);
    updateDomVisuals(this, state);
    queueRedraw(this);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    if (typeof originalConnectionsChange === "function") originalConnectionsChange.apply(this, arguments);
    sanitizeWidgetValues(this, kind);
    syncWidgetVisibility(this, kind);
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
    if (isMediaPreSaveNode(node)) {
      ensureMediaUI(node);
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
      if (!isMediaPreSaveNodeDef(nodeData)) return;
      const original = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function onNodeCreated() {
        if (typeof original === "function") original.apply(this, arguments);
        ensureMediaUI(this);
      };
    },

    async nodeCreated(node) {
      if (isMediaPreSaveNode(node)) {
        ensureMediaUI(node);
        return;
      }

      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (isMediaPreSaveNode(node)) {
          ensureMediaUI(node);
          clearInterval(timer);
          return;
        }
        if (tries >= 30) clearInterval(timer);
      }, 100);
    },

    loadedGraphNode(node) {
      if (isMediaPreSaveNode(node)) ensureMediaUI(node);
    },

    onNodeOutputsUpdated(nodeOutputs) {
      if (!nodeOutputs || typeof nodeOutputs !== "object") return;

      for (const [locatorId, output] of Object.entries(nodeOutputs)) {
        if (!output || typeof output !== "object") continue;
        if (!("presave_media_state" in output || "presave_video_preview" in output || "presave_audio_preview" in output)) {
          continue;
        }

        const node = findNodeByLocator(locatorId);
        if (!node || !node.__mkrPreSaveMediaState) continue;
        if (!isMediaPreSaveNode(node)) continue;
        applyOutputMessage(node, node.__mkrPreSaveMediaState, output);
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
