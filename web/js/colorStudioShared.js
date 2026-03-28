import { app } from "../../../scripts/app.js";
import { ensureMkrUIStyles } from "./uiSystem.js";

const STYLE_ID = "mkr-color-studio-v1";

export const DEFAULT_PANEL_WIDTH = 560;
export const DEFAULT_PANEL_HEIGHT = 760;

export function matchesNode(node, name) {
  const comfyClass = String(node?.comfyClass || node?.constructor?.comfyClass || "");
  const type = String(node?.type || "");
  return comfyClass === name || type === name;
}

export function getWidget(node, name) {
  const mapped = node?.__mkrColorWidgetByName?.get?.(String(name || ""));
  if (mapped) return mapped;
  return Array.isArray(node?.widgets) ? node.widgets.find((widget) => String(widget?.name || "") === name) : null;
}

function parseBundledBoolean(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const token = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(token)) return true;
    if (["false", "0", "no", "off"].includes(token)) return false;
  }
  return fallback;
}

function getSettingsAdapter(node) {
  return node?.__mkrColorSettingsAdapter || null;
}

function normalizeBundledSettings(adapter, payload) {
  const source = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const defaults = adapter?.defaults || {};
  const numericSpecs = adapter?.numericSpecs || {};
  const booleanKeys = new Set(adapter?.booleanKeys || []);
  const next = { ...defaults };

  for (const key of Object.keys(defaults)) {
    if (Object.prototype.hasOwnProperty.call(numericSpecs, key)) {
      const spec = numericSpecs[key] || {};
      const parsed = Number.parseFloat(String(source[key]));
      const fallback = Number(spec.fallback ?? defaults[key] ?? 0);
      const base = Number.isFinite(parsed) ? parsed : fallback;
      const min = Number.isFinite(Number(spec.min)) ? Number(spec.min) : base;
      const max = Number.isFinite(Number(spec.max)) ? Number(spec.max) : base;
      const clamped = Math.max(min, Math.min(max, base));
      next[key] = spec.integer ? Math.round(clamped) : clamped;
      continue;
    }
    if (booleanKeys.has(key)) {
      next[key] = parseBundledBoolean(source[key], Boolean(defaults[key]));
      continue;
    }
    if (source[key] !== undefined) {
      next[key] = source[key];
    }
  }
  return next;
}

function parseBundledSettingsValue(rawValue) {
  const text = String(rawValue ?? "").trim();
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
  }
  return {};
}

function serializeBundledSettings(adapter, settings) {
  return JSON.stringify(normalizeBundledSettings(adapter, settings));
}

function buildLegacyBundledSettings(node, adapter) {
  const legacyNames = Array.isArray(adapter?.legacyNames) ? adapter.legacyNames : [];
  const payload = {};
  let found = false;

  if (Array.isArray(node?.widgets_values) && node.widgets_values.length >= legacyNames.length) {
    legacyNames.forEach((name, index) => {
      if (node.widgets_values[index] !== undefined) {
        payload[name] = node.widgets_values[index];
        found = true;
      }
    });
  }

  if (!found && node?.properties && typeof node.properties === "object") {
    for (const name of legacyNames) {
      if (node.properties[name] !== undefined) {
        payload[name] = node.properties[name];
        found = true;
      }
    }
  }

  return found ? normalizeBundledSettings(adapter, payload) : null;
}

function ensureBundledSettingsSynchronized(node, adapter, settings) {
  const serialized = serializeBundledSettings(adapter, settings);
  const settingsWidget = getWidget(node, adapter.widgetName);
  if (settingsWidget && settingsWidget.value !== serialized) {
    settingsWidget.value = serialized;
  }
  if (node) {
    node.properties = typeof node.properties === "object" && node.properties !== null ? node.properties : {};
    node.properties[adapter.widgetName] = serialized;
    node.widgets_values = [serialized];
    node.__mkrColorSettingsCache = { raw: serialized, settings };
  }
  return serialized;
}

function readBundledSettings(node) {
  const adapter = getSettingsAdapter(node);
  if (!adapter) return null;

  const settingsWidget = getWidget(node, adapter.widgetName);
  const raw = String(settingsWidget?.value ?? node?.properties?.[adapter.widgetName] ?? "");
  const cache = node?.__mkrColorSettingsCache;
  if (cache?.raw === raw && cache?.settings) {
    return cache.settings;
  }

  let payload = parseBundledSettingsValue(raw);
  if ((!payload || Object.keys(payload).length === 0) && !node?.__mkrColorBundledLegacyMigrated) {
    const legacy = buildLegacyBundledSettings(node, adapter);
    if (legacy) {
      payload = legacy;
    }
    node.__mkrColorBundledLegacyMigrated = true;
  }

  const settings = normalizeBundledSettings(adapter, payload);
  ensureBundledSettingsSynchronized(node, adapter, settings);
  return settings;
}

function writeBundledSettings(node, patch, options = {}) {
  const adapter = getSettingsAdapter(node);
  if (!adapter) return null;
  const current = options.replace ? { ...adapter.defaults } : (readBundledSettings(node) || { ...adapter.defaults });
  const next = normalizeBundledSettings(
    adapter,
    options.replace ? (typeof patch === "string" ? parseBundledSettingsValue(patch) : patch) : { ...current, ...(patch || {}) }
  );
  const serialized = ensureBundledSettingsSynchronized(node, adapter, next);
  const settingsWidget = getWidget(node, adapter.widgetName);
  if (!options.silent && typeof settingsWidget?.callback === "function") {
    settingsWidget.callback(serialized, app?.graph, node, settingsWidget);
  }
  node?.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
  return next;
}

export function installBundledSettingsAdapter(node, config) {
  if (!node || !config || !config.defaults) return;
  node.__mkrColorSettingsAdapter = {
    widgetName: config.widgetName || "settings_json",
    defaults: { ...(config.defaults || {}) },
    numericSpecs: { ...(config.numericSpecs || {}) },
    booleanKeys: Array.isArray(config.booleanKeys) ? [...config.booleanKeys] : [],
    legacyNames: Array.isArray(config.legacyNames) ? [...config.legacyNames] : [],
  };
  readBundledSettings(node);
}

export function getValue(node, name, fallback = undefined) {
  const key = String(name || "");
  const adapter = getSettingsAdapter(node);
  if (adapter && (key === adapter.widgetName || Object.prototype.hasOwnProperty.call(adapter.defaults, key))) {
    const settings = readBundledSettings(node) || adapter.defaults;
    return key === adapter.widgetName ? serializeBundledSettings(adapter, settings) : (settings[key] ?? fallback);
  }
  const widget = getWidget(node, key);
  if (widget && widget.value !== undefined) return widget.value;
  const prop = node?.properties?.[key];
  if (prop !== undefined) return prop;
  return fallback;
}

export function getNumber(node, name, fallback = 0) {
  const value = Number(getValue(node, name, fallback));
  return Number.isFinite(value) ? value : fallback;
}

export function getBoolean(node, name, fallback = false) {
  return parseBundledBoolean(getValue(node, name, fallback), fallback);
}

export function setWidgetValue(node, name, value) {
  const key = String(name || "");
  const adapter = getSettingsAdapter(node);
  if (adapter && (key === adapter.widgetName || Object.prototype.hasOwnProperty.call(adapter.defaults, key))) {
    writeBundledSettings(
      node,
      key === adapter.widgetName ? value : { [key]: value },
      { replace: key === adapter.widgetName }
    );
    return true;
  }
  const widget = getWidget(node, key);
  if (!widget) return false;
  if (widget.value === value) return false;
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app?.graph, node, widget);
  }
  node.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
  return true;
}

export function hardHideWidget(widget) {
  return hardHideWidgetInternal(widget, new Set());
}

function hardHideWidgetInternal(widget, seen) {
  if (!widget || seen.has(widget)) return false;
  seen.add(widget);
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
  widget.visible = false;
  widget.options = {
    ...(widget.options || {}),
    visible: false,
    serialize: true,
    hidden: true,
  };
  widget.computeSize = () => [0, -4];
  widget.computeLayoutSize = () => ({ minHeight: 0, maxHeight: 0, minWidth: 0, preferredWidth: 0 });
  widget.draw = () => {};
  widget.disabled = true;
  widget.last_y = 0;
  widget.y = 0;
  for (const key of ["element", "inputEl", "textarea", "controlEl"]) {
    const el = widget?.[key];
    if (el?.style) {
      el.style.display = "none";
      el.style.visibility = "hidden";
      el.style.height = "0px";
      el.style.minHeight = "0px";
      el.style.maxHeight = "0px";
      el.style.overflow = "hidden";
      el.style.margin = "0";
      el.style.padding = "0";
    }
  }
  const linked = Array.isArray(widget.linkedWidgets)
    ? widget.linkedWidgets
    : Array.isArray(widget.linked_widgets)
      ? widget.linked_widgets
      : [];
  for (const linkedWidget of linked) {
    changed = hardHideWidgetInternal(linkedWidget, seen) || changed;
  }
  return changed;
}

export function hideWidgets(node, names) {
  let changed = false;
  for (const name of names) {
    changed = hardHideWidget(getWidget(node, name)) || changed;
  }
  if (changed) {
    node.setDirtyCanvas?.(true, true);
  }
  return changed;
}

export function formatSigned(value, decimals = 2) {
  const number = Number(value) || 0;
  const fixed = number.toFixed(decimals);
  return number > 0 ? `+${fixed}` : fixed;
}

export function formatNumber(value, decimals = 2) {
  return (Number(value) || 0).toFixed(decimals);
}

export function ensureCanvasResolution(canvas) {
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(1, Math.round(rect.width));
  const cssHeight = Math.max(1, Math.round(rect.height));
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const targetWidth = Math.max(1, Math.round(cssWidth * dpr));
  const targetHeight = Math.max(1, Math.round(cssHeight * dpr));
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: cssWidth, height: cssHeight };
}

export function createMetricPill(label, value, tone = "neutral") {
  const pill = document.createElement("div");
  pill.className = "mkr-color-pill";
  pill.dataset.tone = tone;

  const labelNode = document.createElement("div");
  labelNode.className = "mkr-color-pill-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("div");
  valueNode.className = "mkr-color-pill-value";
  valueNode.textContent = value;

  pill.appendChild(labelNode);
  pill.appendChild(valueNode);

  return {
    element: pill,
    setValue(next) {
      valueNode.textContent = next;
    },
    setLabel(next) {
      labelNode.textContent = next;
    },
  };
}

export function attachPanel(node, panelName, panel, width = DEFAULT_PANEL_WIDTH, height = DEFAULT_PANEL_HEIGHT) {
  if (!node || node[`__${panelName}`]) {
    return node?.[`__${panelName}`] || null;
  }

  panel.style.width = "100%";
  panel.style.maxWidth = "none";
  panel.style.maxHeight = "none";
  panel.style.boxSizing = "border-box";

  let domWidget = null;
  const innerWidth = Math.max(width - 14, 280);
  const innerHeight = Math.max(height - 12, 120);
  if (typeof node.addDOMWidget === "function") {
    domWidget = node.addDOMWidget(panelName, "DOM", panel, {
      serialize: false,
      hideOnZoom: false,
    });
  } else if (typeof node.addCustomWidget === "function") {
    domWidget = node.addCustomWidget({
      name: panelName,
      type: "dom",
      draw() {},
      getHeight() {
        return height;
      },
      getWidth() {
        return width;
      },
      element: panel,
    });
  }

  if (domWidget) {
    domWidget.computeSize = () => [innerWidth, innerHeight];
    domWidget.computeLayoutSize = () => ({
      minHeight: innerHeight,
      maxHeight: innerHeight,
      minWidth: innerWidth,
      preferredWidth: innerWidth,
    });
    if (domWidget.element?.style) {
      domWidget.element.style.width = `${innerWidth}px`;
      domWidget.element.style.height = `${innerHeight}px`;
      domWidget.element.style.minHeight = `${innerHeight}px`;
      domWidget.element.style.maxHeight = `${innerHeight}px`;
      domWidget.element.style.maxWidth = "100%";
      domWidget.element.style.overflow = "hidden";
      domWidget.element.style.boxSizing = "border-box";
    }
  }

  const originalOnResize = node.onResize;
  if (!node.__mkrColorStudioResizePatched) {
    node.__mkrColorStudioResizePatched = true;
    node.onResize = function onResize(size) {
      const result = originalOnResize?.apply(this, arguments);
      const lockedSize = Array.isArray(this.__mkrColorLockedSize) ? this.__mkrColorLockedSize : [width, height];
      const nextWidth = lockedSize[0];
      const nextHeight = lockedSize[1];
      const nextInnerWidth = Math.max(nextWidth - 14, 280);
      const nextInnerHeight = Math.max(nextHeight - 12, 120);
      if (domWidget?.element?.style) {
        domWidget.element.style.width = `${nextInnerWidth}px`;
        domWidget.element.style.height = `${nextInnerHeight}px`;
        domWidget.element.style.minHeight = `${nextInnerHeight}px`;
        domWidget.element.style.maxHeight = `${nextInnerHeight}px`;
      }
      domWidget.computeSize = () => [nextInnerWidth, nextInnerHeight];
      domWidget.computeLayoutSize = () => ({
        minHeight: nextInnerHeight,
        maxHeight: nextInnerHeight,
        minWidth: nextInnerWidth,
        preferredWidth: nextInnerWidth,
      });
      trySetWidgetY(domWidget, 6);
      this.size = [nextWidth, nextHeight];
      this.setDirtyCanvas?.(true, true);
      return result;
    };
  }

  const lockedSize = [width, height];
  node.__mkrColorLockedSize = lockedSize;
  node.resizable = false;
  node.flags = typeof node.flags === "object" && node.flags !== null ? node.flags : {};
  node.flags.resizable = false;
  node.size = [lockedSize[0], lockedSize[1]];
  node.setSize?.([lockedSize[0], lockedSize[1]]);
  trySetWidgetY(domWidget, 6);

  const originalExecuted = node.onExecuted;
  if (!node.__mkrColorExecutedPatched) {
    node.__mkrColorExecutedPatched = true;
    node.onExecuted = function onExecutedColorPanel(message) {
      const result = originalExecuted?.apply(this, arguments);
      if (Array.isArray(this.__mkrColorLockedSize)) {
        this.size = [this.__mkrColorLockedSize[0], this.__mkrColorLockedSize[1]];
      }
      return result;
    };
  }

  node[`__${panelName}`] = domWidget || { element: panel };
  return node[`__${panelName}`];
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

function removePanelGeneratedInputs(node, hiddenWidgetNames) {
  if (!node || !Array.isArray(node.inputs) || node.inputs.length === 0) return false;
  const hiddenNames = new Set(hiddenWidgetNames.filter(Boolean).map((name) => String(name)));
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

  if (changed) {
    node.inputs = keep;
  }
  return changed;
}

function installSilentWidgetGuards(node, hiddenWidgetNames, domWidgetName) {
  if (!node || node.__mkrColorSilentWidgetGuardsInstalled) return;
  node.__mkrColorSilentWidgetGuardsInstalled = true;

  const hiddenNameSet = new Set((hiddenWidgetNames || []).filter(Boolean).map((name) => String(name)));
  const isSilentWidget = (widget) => {
    const name = String(widget?.name || "");
    if (!name || name === domWidgetName) return false;
    return hiddenNameSet.has(name) || widget?.hidden === true || widget?.type === "hidden";
  };

  const originalGetWidgetOnPos = typeof node.getWidgetOnPos === "function" ? node.getWidgetOnPos : null;
  if (originalGetWidgetOnPos) {
    node.getWidgetOnPos = function getWidgetOnPosSilentGuard() {
      const widget = originalGetWidgetOnPos.apply(this, arguments);
      return isSilentWidget(widget) ? null : widget;
    };
  }

  const originalGetWidgetAtPos = typeof node.getWidgetAtPos === "function" ? node.getWidgetAtPos : null;
  if (originalGetWidgetAtPos) {
    node.getWidgetAtPos = function getWidgetAtPosSilentGuard() {
      const widget = originalGetWidgetAtPos.apply(this, arguments);
      return isSilentWidget(widget) ? null : widget;
    };
  }

  const originalMouseDown = typeof node.onMouseDown === "function" ? node.onMouseDown : null;
  node.onMouseDown = function onMouseDownSilentGuard() {
    const hitOnPos = originalGetWidgetOnPos?.apply(this, arguments);
    if (isSilentWidget(hitOnPos)) {
      return true;
    }
    const hitAtPos = originalGetWidgetAtPos?.apply(this, arguments);
    if (isSilentWidget(hitAtPos)) {
      return true;
    }
    return originalMouseDown?.apply(this, arguments) ?? false;
  };
}

export function normalizePanelNode(node, hiddenWidgetNames, domWidgetName) {
  if (!node) return;
  const applyNormalization = (target) => {
    const hiddenWidgets = hiddenWidgetNames
      .map((name) => getWidget(target, name))
      .filter(Boolean);

    hiddenWidgets.forEach((widget) => hardHideWidget(widget));
    target.__mkrColorWidgetByName = new Map(
      (target.widgets || [])
        .filter(Boolean)
        .map((widget) => [String(widget.name || ""), widget])
        .filter(([name]) => !!name)
    );
    removePanelGeneratedInputs(target, hiddenWidgetNames);
    installSilentWidgetGuards(target, hiddenWidgetNames, domWidgetName);
    const domWidget = getWidget(target, domWidgetName);
    trySetWidgetY(domWidget, 6);
  };

  applyNormalization(node);

  if (!node.__mkrColorNormalizeHookInstalled) {
    node.__mkrColorNormalizeHookInstalled = true;

    const originalConfigure = node.onConfigure;
    node.onConfigure = function onConfigureColorPanel() {
      const result = originalConfigure?.apply(this, arguments);
      applyNormalization(this);
      return result;
    };

    const originalResize = node.onResize;
    node.onResize = function onResizeColorPanel() {
      const result = originalResize?.apply(this, arguments);
      applyNormalization(this);
      return result;
    };
  }

  node.setDirtyCanvas?.(true, true);
}

export function ensureColorStudioStyles() {
  ensureMkrUIStyles();
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-color-studio {
      width: 100%;
      max-width: none;
      max-height: none;
      overflow: hidden;
      padding: 10px 12px 12px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.55);
      background:
        radial-gradient(120% 130% at 8% 0%, rgba(255, 163, 74, 0.10) 0%, rgba(255, 163, 74, 0.0) 38%),
        radial-gradient(150% 140% at 100% 0%, rgba(68, 151, 255, 0.10) 0%, rgba(68, 151, 255, 0.0) 48%),
        linear-gradient(180deg, rgba(255, 252, 248, 0.98) 0%, rgba(246, 249, 252, 0.98) 100%);
      box-shadow: 0 12px 24px rgba(24, 38, 53, 0.08);
    }

    .mkr-color-studio .mkr-header {
      margin-bottom: 6px;
      padding: 6px 8px 8px;
      border: 0;
      border-bottom: 1px solid rgba(17, 49, 68, 0.08);
      border-radius: 0;
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--mkr-accent-a, #f39f4d) 8%, #ffffff) 0%, rgba(255,255,255,0.46) 100%);
    }

    .mkr-color-studio .mkr-kicker {
      font-size: 10px;
      letter-spacing: 0.12em;
      margin-bottom: 3px;
    }

    .mkr-color-studio .mkr-title {
      font-size: 18px;
      line-height: 1.05;
      letter-spacing: -0.02em;
    }

    .mkr-color-studio .mkr-subtitle {
      font-size: 11px;
      line-height: 1.35;
      color: #5f7282;
    }

    .mkr-color-studio .mkr-section {
      margin-top: 0;
      padding: 9px 0 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      box-shadow: none;
    }

    .mkr-color-studio .mkr-section + .mkr-section {
      margin-top: 10px;
      border-top: 1px solid rgba(17, 49, 68, 0.08);
      padding-top: 10px;
    }

    .mkr-color-studio .mkr-section-head {
      margin-bottom: 6px;
    }

    .mkr-color-studio .mkr-stack {
      gap: 6px;
    }

    .mkr-color-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .mkr-color-pill {
      padding: 8px 9px;
      border-radius: 10px;
      border: 1px solid rgba(16, 35, 45, 0.08);
      background: rgba(255, 255, 255, 0.56);
      box-shadow: none;
    }

    .mkr-color-pill[data-tone="warm"] {
      background: linear-gradient(180deg, rgba(255, 239, 220, 0.92), rgba(255, 251, 246, 0.92));
    }

    .mkr-color-pill[data-tone="cool"] {
      background: linear-gradient(180deg, rgba(226, 241, 255, 0.92), rgba(248, 252, 255, 0.92));
    }

    .mkr-color-pill[data-tone="accent"] {
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--mkr-accent-a, #2d9c8f) 14%, white), rgba(255, 255, 255, 0.92));
      border-color: color-mix(in srgb, var(--mkr-accent-a, #2d9c8f) 28%, transparent);
    }

    .mkr-color-pill-label {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #5d7080;
      margin-bottom: 4px;
    }

    .mkr-color-pill-value {
      font-size: 16px;
      font-weight: 700;
      color: #10293b;
      font-variant-numeric: tabular-nums;
    }

    .mkr-color-grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .mkr-color-wheel-card,
    .mkr-color-canvas-card {
      padding: 2px 0 0;
      border-radius: 0;
      border: 0;
      background: transparent;
      box-sizing: border-box;
    }

    .mkr-color-card-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
    }

    .mkr-color-card-title {
      font-size: 13px;
      font-weight: 700;
      color: #12344a;
    }

    .mkr-color-card-note {
      font-size: 11px;
      color: #607280;
    }

    .mkr-color-wheel-canvas,
    .mkr-color-graph-canvas,
    .mkr-color-warp-canvas {
      display: block;
      width: 100%;
      box-sizing: border-box;
      border-radius: 10px;
      cursor: crosshair;
      background:
        radial-gradient(120% 120% at 50% 0%, rgba(255,255,255,0.78) 0%, rgba(255,255,255,0.12) 55%, rgba(11,16,22,0.06) 100%);
      border: 1px solid rgba(17, 49, 68, 0.10);
    }

    .mkr-color-wheel-canvas {
      aspect-ratio: 1 / 1;
    }

    .mkr-color-graph-canvas,
    .mkr-color-warp-canvas {
      height: 278px;
    }

    .mkr-color-badge-row {
      margin-top: 6px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .mkr-color-badge {
      padding: 3px 7px;
      border-radius: 999px;
      background: rgba(15, 38, 55, 0.04);
      border: 1px solid rgba(15, 38, 55, 0.06);
      color: #27465a;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.03em;
    }

    .mkr-color-note {
      margin-top: 6px;
      font-size: 11px;
      line-height: 1.45;
      color: #5f7282;
    }

    .mkr-color-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .mkr-color-toolbar .mkr-btn-row {
      flex: 1 1 auto;
    }

    .mkr-color-point-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .mkr-color-point-chip {
      border: 1px solid rgba(16, 35, 45, 0.08);
      background: rgba(255, 255, 255, 0.62);
      color: #163347;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
    }

    .mkr-color-point-chip[data-active="true"] {
      background: color-mix(in srgb, var(--mkr-accent-a, #d9573b) 12%, white);
      border-color: color-mix(in srgb, var(--mkr-accent-a, #d9573b) 35%, transparent);
    }

    .mkr-color-point-empty {
      font-size: 12px;
      color: #627583;
    }

    .mkr-color-studio .mkr-control {
      padding: 4px 0;
      border-bottom: 1px solid rgba(19, 33, 47, 0.05);
    }

    .mkr-color-studio .mkr-control:last-child {
      border-bottom: 0;
    }

    .mkr-color-studio .mkr-btn {
      border-radius: 9px;
      background: rgba(255, 255, 255, 0.62);
      box-shadow: none;
    }

    .mkr-color-studio .mkr-btn[data-tone="accent"] {
      background: color-mix(in srgb, var(--mkr-accent-a, #2d9c8f) 10%, rgba(255, 255, 255, 0.78));
    }

    @media (max-width: 720px) {
      .mkr-color-summary,
      .mkr-color-grid-2 {
        grid-template-columns: 1fr;
      }

      .mkr-color-graph-canvas,
      .mkr-color-warp-canvas {
        height: 240px;
      }
    }
  `;

  document.head.appendChild(style);
}

const GRADE_STYLE_ID = "mkr-color-grade-v1";

export function ensureColorGradeStyles() {
  if (document.getElementById(GRADE_STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = GRADE_STYLE_ID;
  style.textContent = `
    .mkr-grade-panel {
      width: 100%;
      max-width: none;
      max-height: none;
      overflow: hidden;
      padding: 4px 4px 14px;
      border-radius: 0;
      border: 0;
      background: transparent;
      color: #eef1f4;
      box-shadow: none;
      box-sizing: border-box;
      font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", sans-serif;
    }

    .mkr-grade-panel .mkr-kicker {
      color: rgba(245,248,252,0.44);
      font-size: 9px;
      letter-spacing: 0.12em;
      margin-bottom: 3px;
    }

    .mkr-grade-panel .mkr-title {
      color: #f5f7fa;
      font-size: 16px;
      line-height: 1.05;
      letter-spacing: -0.02em;
      margin: 0;
    }

    .mkr-grade-panel .mkr-subtitle {
      margin-top: 4px;
      color: rgba(226,231,237,0.58);
      font-size: 11px;
      line-height: 1.3;
    }

    .mkr-grade-topbar {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }

    .mkr-grade-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      flex: 1 1 auto;
    }

    .mkr-grade-metric {
      min-width: 0;
      padding: 5px 7px;
      border-radius: 8px;
      background: rgba(255,255,255,0.035);
      border: 1px solid rgba(255,255,255,0.05);
    }

    .mkr-grade-metric-label {
      color: rgba(225,232,238,0.42);
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 2px;
    }

    .mkr-grade-metric-value {
      color: #f4f7fb;
      font-size: 14px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    .mkr-grade-actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .mkr-grade-button {
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      color: rgba(241,245,248,0.88);
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
    }

    .mkr-grade-button:hover {
      background: rgba(255,255,255,0.07);
    }

    .mkr-grade-button[data-tone="accent"] {
      border-color: rgba(255,255,255,0.12);
      background: color-mix(in srgb, var(--mkr-grade-accent, #ff7b31) 16%, rgba(255,255,255,0.02));
    }

    .mkr-grade-section {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid rgba(255,255,255,0.08);
    }

    .mkr-grade-section-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 7px;
    }

    .mkr-grade-section-title {
      font-size: 11px;
      font-weight: 700;
      color: rgba(245,248,252,0.96);
    }

    .mkr-grade-section-note {
      font-size: 9px;
      color: rgba(221,228,234,0.42);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .mkr-grade-canvas {
      display: block;
      width: 100%;
      border-radius: 10px;
      background:
        radial-gradient(circle at 50% 45%, rgba(255,255,255,0.04), rgba(255,255,255,0.00) 55%),
        linear-gradient(180deg, rgba(17,18,21,0.98), rgba(26,28,31,0.98));
      border: 1px solid rgba(255,255,255,0.08);
      box-sizing: border-box;
    }

    .mkr-grade-inline {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      margin-top: 7px;
    }

    .mkr-grade-readout {
      padding: 4px 5px;
      border-radius: 6px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.04);
      text-align: center;
    }

    .mkr-grade-readout-label {
      color: rgba(221,228,234,0.38);
      font-size: 8px;
      margin-bottom: 2px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .mkr-grade-readout-value {
      color: #f0f4f8;
      font-size: 10px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    .mkr-grade-note {
      margin-top: 6px;
      color: rgba(237,242,247,0.62);
      font-size: 10px;
      line-height: 1.35;
    }

    .mkr-grade-controls {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }

    .mkr-grade-control {
      min-width: 0;
    }

    .mkr-grade-control-label {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
      color: rgba(237,242,247,0.84);
      font-size: 10px;
      font-weight: 600;
    }

    .mkr-grade-control-value {
      color: rgba(237,242,247,0.50);
      font-variant-numeric: tabular-nums;
    }

    .mkr-grade-range {
      width: 100%;
      accent-color: var(--mkr-grade-accent, #ff7b31);
      margin: 0;
    }

    .mkr-grade-number {
      width: 100%;
      margin-top: 4px;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.20);
      color: #eef2f6;
      padding: 4px 6px;
      font-size: 10px;
      box-sizing: border-box;
      font-variant-numeric: tabular-nums;
    }

    .mkr-grade-toggle-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 58px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
      box-sizing: border-box;
    }

    .mkr-grade-toggle-wrap input {
      accent-color: var(--mkr-grade-accent, #ff7b31);
    }

    .mkr-grade-toggle-text {
      color: rgba(237,242,247,0.72);
      font-size: 10px;
      line-height: 1.25;
    }

    .mkr-grade-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .mkr-grade-chip {
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      color: rgba(241,245,248,0.88);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
    }

    .mkr-grade-chip[data-active="true"] {
      background: color-mix(in srgb, var(--mkr-grade-accent, #ff7b31) 16%, rgba(255,255,255,0.02));
      border-color: rgba(255,255,255,0.12);
    }

    @media (max-width: 860px) {
      .mkr-grade-topbar {
        flex-direction: column;
        align-items: stretch;
      }

      .mkr-grade-controls {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `;

  document.head.appendChild(style);
}

export function createGradeMetric(label, value) {
  const root = document.createElement("div");
  root.className = "mkr-grade-metric";
  const labelNode = document.createElement("div");
  labelNode.className = "mkr-grade-metric-label";
  labelNode.textContent = label;
  const valueNode = document.createElement("div");
  valueNode.className = "mkr-grade-metric-value";
  valueNode.textContent = value;
  root.appendChild(labelNode);
  root.appendChild(valueNode);
  return {
    element: root,
    setValue(next) {
      valueNode.textContent = next;
    },
  };
}

export function createGradeSection(title, note = "") {
  const section = document.createElement("section");
  section.className = "mkr-grade-section";
  const head = document.createElement("div");
  head.className = "mkr-grade-section-head";
  const titleNode = document.createElement("div");
  titleNode.className = "mkr-grade-section-title";
  titleNode.textContent = title;
  const noteNode = document.createElement("div");
  noteNode.className = "mkr-grade-section-note";
  noteNode.textContent = note;
  head.appendChild(titleNode);
  if (note) head.appendChild(noteNode);
  const body = document.createElement("div");
  section.appendChild(head);
  section.appendChild(body);
  return { section, body, head };
}

export function createGradeButton(label, onClick, tone = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "mkr-grade-button";
  if (tone) button.dataset.tone = tone;
  button.textContent = label;
  button.addEventListener("click", () => onClick?.());
  return button;
}

export function createGradeReadout(label, value) {
  const root = document.createElement("div");
  root.className = "mkr-grade-readout";
  const labelNode = document.createElement("div");
  labelNode.className = "mkr-grade-readout-label";
  labelNode.textContent = label;
  const valueNode = document.createElement("div");
  valueNode.className = "mkr-grade-readout-value";
  valueNode.textContent = value;
  root.appendChild(labelNode);
  root.appendChild(valueNode);
  return {
    element: root,
    setValue(next) {
      valueNode.textContent = next;
    },
  };
}

export function createGradeSlider({ label, min, max, step, value, decimals = 2, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("span");
  valueNode.className = "mkr-grade-control-value";
  head.appendChild(labelNode);
  head.appendChild(valueNode);

  const range = document.createElement("input");
  range.type = "range";
  range.className = "mkr-grade-range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);

  const number = document.createElement("input");
  number.type = "number";
  number.className = "mkr-grade-number";
  number.min = String(min);
  number.max = String(max);
  number.step = String(step);

  const setDisplay = (next) => {
    const normalized = Number.isFinite(next) ? Number(next.toFixed(decimals)) : Number(value);
    range.value = String(normalized);
    number.value = String(normalized);
    valueNode.textContent = normalized.toFixed(decimals);
  };

  const commit = (raw) => {
    const parsed = Number.parseFloat(String(raw));
    const next = Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : Number(value);
    setDisplay(next);
    onChange?.(next);
  };

  setDisplay(Number(value));
  range.addEventListener("input", () => commit(range.value));
  number.addEventListener("change", () => commit(number.value));

  root.appendChild(head);
  root.appendChild(range);
  root.appendChild(number);

  return {
    element: root,
    setValue(next) {
      setDisplay(Number(next));
    },
  };
}

export function createGradeToggle({ label, checked, description = "", onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${checked ? "On" : "Off"}</span>`;
  const wrap = document.createElement("label");
  wrap.className = "mkr-grade-toggle-wrap";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = checked;
  const text = document.createElement("div");
  text.className = "mkr-grade-toggle-text";
  text.textContent = description;
  wrap.appendChild(input);
  wrap.appendChild(text);
  input.addEventListener("change", () => {
    head.lastChild.textContent = input.checked ? "On" : "Off";
    onChange?.(input.checked);
  });
  root.appendChild(head);
  root.appendChild(wrap);
  return {
    element: root,
    setValue(next) {
      input.checked = !!next;
      head.lastChild.textContent = input.checked ? "On" : "Off";
    },
  };
}
