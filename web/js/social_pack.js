import { app } from "../../../scripts/app.js";

const EXT = "mkrshift.socialpack";
const DOM_WIDGET_NAME = "mkr_social_pack_summary";
const STYLE_ID = "mkrshift-social-pack-compact-style";
const DEFAULT_W = 380;
const DEFAULT_H = 760;
const MIN_SUMMARY_H = 232;
const POLL_MS = 350;

const PLATFORM_DEFAULT_RATIOS = {
  Instagram: "4:5",
  TikTok: "9:16",
  "YouTube Shorts": "9:16",
  LinkedIn: "1:1",
  X: "1:1",
  Mixed: "4:5",
};

const ROLE_SEQUENCES = {
  Carousel: ["hook", "detail", "benefit", "context", "proof", "cta"],
  Story: ["hook", "detail", "motion", "reaction", "cta"],
  Mixed: ["hero", "detail", "context", "offer", "proof", "cta"],
};

const STYLE_CSS = `
:root {
  --mkr-social-bg: #0d1411;
  --mkr-social-panel: #121b17;
  --mkr-social-panel-soft: #18221d;
  --mkr-social-border: #27362f;
  --mkr-social-border-strong: #355044;
  --mkr-social-text: #eef7ef;
  --mkr-social-muted: #90a596;
  --mkr-social-accent: #d2fd51;
  --mkr-social-accent-soft: #dffb86;
  --mkr-social-accent-green: #d2fd51;
  --mkr-social-warn: #f1b44a;
}

.mkr-social-compact {
  box-sizing: border-box;
  width: 100%;
  min-height: ${MIN_SUMMARY_H}px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  color: var(--mkr-social-text);
  font: 500 12px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
  background: var(--mkr-social-panel);
  border: 1px solid var(--mkr-social-border);
  border-radius: 14px;
}

.mkr-social-compact__head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
}

.mkr-social-compact__eyebrow {
  color: var(--mkr-social-accent-soft);
  font: 700 10px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.mkr-social-compact__title {
  margin: 2px 0 0;
  font: 700 16px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
}

.mkr-social-compact__subtitle {
  margin-top: 3px;
  color: var(--mkr-social-muted);
  font-size: 11px;
  line-height: 1.4;
}

.mkr-social-compact__actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.mkr-social-compact__button {
  appearance: none;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 9px;
  border: 1px solid var(--mkr-social-border-strong);
  background: var(--mkr-social-panel-soft);
  color: var(--mkr-social-text);
  font: 700 10px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
  letter-spacing: 0.04em;
  cursor: pointer;
}

.mkr-social-compact__button:hover {
  border-color: var(--mkr-social-accent);
  color: var(--mkr-social-accent-soft);
}

.mkr-social-compact__button.is-primary {
  color: #0b1108;
  border-color: rgba(210,253,81,0.55);
  background: var(--mkr-social-accent);
}

.mkr-social-compact__content {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.mkr-social-compact__thumb {
  position: relative;
  width: 112px;
  height: 112px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--mkr-social-border-strong);
  background: var(--mkr-social-bg);
}

.mkr-social-compact__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.mkr-social-compact__thumb-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 10px;
  color: var(--mkr-social-muted);
  font-size: 11px;
  line-height: 1.35;
}

.mkr-social-compact__badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid var(--mkr-social-border-strong);
  background: var(--mkr-social-panel-soft);
  color: var(--mkr-social-accent-soft);
  font: 700 10px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
  letter-spacing: 0.04em;
}

.mkr-social-compact__pack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mkr-social-compact__pack-name {
  margin: 0;
  font: 700 13px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
}

.mkr-social-compact__meta,
.mkr-social-compact__note {
  color: var(--mkr-social-muted);
  font-size: 11px;
  line-height: 1.45;
}

.mkr-social-compact__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mkr-social-compact__chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--mkr-social-bg);
  border: 1px solid var(--mkr-social-border);
  color: var(--mkr-social-text);
  font: 700 10px "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
}

.mkr-social-compact__warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mkr-social-compact__warning {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 9px;
  border-radius: 10px;
  border: 1px solid var(--mkr-social-border);
  background: var(--mkr-social-bg);
}

.mkr-social-compact__warning-dot {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  margin-top: 4px;
  border-radius: 999px;
  background: var(--mkr-social-warn);
  box-shadow: 0 0 12px currentColor;
}

.mkr-social-compact__warning.is-ok .mkr-social-compact__warning-dot {
  background: var(--mkr-social-accent-green);
}

.mkr-social-compact__warning-text {
  color: var(--mkr-social-text);
  font-size: 11px;
  line-height: 1.45;
}
`;

let packsRequest = null;

function getApp() {
  return globalThis?.comfyAPI?.app?.app || globalThis?.app || app || null;
}

function getApi() {
  return globalThis?.api || globalThis?.comfyAPI?.api || null;
}

function apiUrl(path) {
  const apiObj = getApi();
  const text = String(path || "");
  if (apiObj && typeof apiObj.apiURL === "function") {
    return apiObj.apiURL(text);
  }
  return text;
}

function fetchApiCompat(path, init = undefined) {
  const apiObj = getApi();
  if (apiObj && typeof apiObj.fetchApi === "function") {
    return apiObj.fetchApi(path, init);
  }
  return fetch(path, init);
}

function ensureStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE_CSS;
  document.head.appendChild(style);
}

function matchesSocialPackName(name) {
  const token = String(name ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!token) return false;
  if (token === "mkrshiftsocialpackbuilder") return true;
  return token.includes("socialpackbuilder");
}

function isSocialPackNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
  ].filter(Boolean);
  return candidates.some(matchesSocialPackName);
}

function isSocialPackNodeDef(nodeData) {
  const candidates = [nodeData?.name, nodeData?.display_name, nodeData?.type].filter(Boolean);
  return candidates.some(matchesSocialPackName);
}

function getWidget(node, name) {
  return node.widgets?.find((widget) => String(widget?.name || "") === name);
}

function getWidgetChoices(widget) {
  if (!widget) return [];
  if (Array.isArray(widget.options?.values)) return widget.options.values;
  if (Array.isArray(widget.values)) return widget.values;
  if (Array.isArray(widget.options)) return widget.options;
  return [];
}

function widgetString(node, name, fallback = "") {
  const widget = getWidget(node, name);
  if (widget && widget.value !== undefined) return String(widget.value);
  const prop = node?.properties?.[name];
  if (prop !== undefined) return String(prop);
  return String(fallback);
}

function widgetInt(node, name, fallback = 0) {
  const raw = Number.parseInt(widgetString(node, name, fallback), 10);
  return Number.isFinite(raw) ? raw : fallback;
}

function setWidgetValue(node, widget, value) {
  if (!widget) return;
  widget.value = value;
  node.properties = node.properties || {};
  if (widget.name) {
    node.properties[widget.name] = value;
  }
  if (typeof widget.callback === "function") {
    widget.callback(value, getApp()?.graph, node, widget);
  }
  refreshCompactUI(node);
  markDirty(node);
}

function markDirty(node) {
  node?.setDirtyCanvas?.(true, true);
  getApp()?.graph?.setDirtyCanvas?.(true, true);
}

function dedupeKeepOrder(values) {
  const out = [];
  const seen = new Set();
  for (const value of values) {
    const clean = String(value || "").trim();
    if (!clean) continue;
    const token = clean.toLowerCase();
    if (seen.has(token)) continue;
    seen.add(token);
    out.push(clean);
  }
  return out;
}

function extractPackId(value) {
  const text = String(value ?? "").trim();
  if (text.includes("(") && text.endsWith(")")) {
    return text.split("(").pop().slice(0, -1).trim();
  }
  return text;
}

function selectedPackIdFromNode(node) {
  const fromProperty = String(node?.properties?.selected_pack_id || "").trim();
  if (fromProperty) return fromProperty;
  return extractPackId(widgetString(node, "pack", ""));
}

function connectedInput(node, name) {
  return !!node?.inputs?.find((entry) => entry?.name === name)?.link;
}

function effectiveRatioPlan(node, selectedPack) {
  const count = Math.max(1, widgetInt(node, "count", selectedPack?.default_count ?? 12));
  const outputMode = widgetString(node, "output_mode", "Carousel");
  const aspect = widgetString(node, "aspect", "Auto").trim();
  const platform = widgetString(node, "platform", "Mixed");

  if (aspect && aspect !== "Auto") {
    return Array.from({ length: count }, () => aspect);
  }

  const packRatios = Array.isArray(selectedPack?.ratios)
    ? dedupeKeepOrder(selectedPack.ratios.map((value) => String(value)))
    : [];

  if (outputMode === "Story") {
    return Array.from({ length: count }, () => "9:16");
  }

  if (outputMode === "Mixed") {
    const cycle = packRatios.length
      ? packRatios
      : dedupeKeepOrder([PLATFORM_DEFAULT_RATIOS[platform] || "4:5", "1:1", "9:16"]);
    return Array.from({ length: count }, (_, index) => cycle[index % cycle.length]);
  }

  const chosen = packRatios[0] || PLATFORM_DEFAULT_RATIOS[platform] || "4:5";
  return Array.from({ length: count }, () => chosen);
}

function effectiveRolePlan(node, count) {
  const outputMode = widgetString(node, "output_mode", "Carousel");
  const sequence = ROLE_SEQUENCES[outputMode] || ROLE_SEQUENCES.Mixed;
  if (count <= 1) return [sequence[0]];

  const middle = sequence.slice(1, -1).length ? sequence.slice(1, -1) : [sequence[0]];
  return Array.from({ length: count }, (_, index) => {
    if (index === 0) return sequence[0];
    if (index === count - 1) return sequence[sequence.length - 1];
    return middle[(index - 1) % middle.length];
  });
}

function summarizeSequence(values, maxVisible = 4) {
  if (!Array.isArray(values) || !values.length) return "Auto";
  const shown = values.slice(0, maxVisible);
  const joined = shown.join(" -> ");
  return values.length > maxVisible ? `${joined} -> ...` : joined;
}

function inferWidgetType(widget) {
  if (getWidgetChoices(widget).length) return "combo";
  if (typeof widget?.value === "boolean") return "toggle";
  if (typeof widget?.value === "number") return "number";
  return "string";
}

function restoreVisibleWidgets(node) {
  if (!Array.isArray(node?.widgets)) return;
  for (const widget of node.widgets) {
    const name = String(widget?.name || "");
    if (!name || name === DOM_WIDGET_NAME) continue;
    if (String(widget?.type || "") !== "hidden") continue;
    widget.type = inferWidgetType(widget);
    widget.hidden = false;
    delete widget.computeSize;
  }
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

async function fetchPacksFromBackend(force = false) {
  if (force) {
    packsRequest = null;
  }
  if (!packsRequest) {
    packsRequest = (async () => {
      try {
        const response = await fetchApiCompat("/mkrshift_social/packs");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        return Array.isArray(data) ? data : [];
      } catch (error) {
        console.warn("[mkrshift.socialpack] Failed to fetch packs:", error);
        packsRequest = null;
        return null;
      }
    })();
  }
  return packsRequest;
}

function fallbackPacksFromWidget(node) {
  const values = getWidgetChoices(getWidget(node, "pack"));
  return values.map((entry) => {
    const raw = String(entry);
    const id = extractPackId(raw);
    const name = raw.replace(/\s*\([^)]+\)\s*$/, "").trim() || id;
    return {
      id,
      name,
      tags: [],
      description: "",
      preview: "",
      default_count: 12,
      ratios: [],
      shot_count: 0,
      export: {},
    };
  });
}

function ensureState(node) {
  if (node.__mkrshiftSocialState) return node.__mkrshiftSocialState;
  node.__mkrshiftSocialState = {
    packs: [],
    selectedPackId: "",
    previewUrl: "",
    loadingPacks: false,
    backendReadiness: null,
    dom: null,
    domWidget: null,
    pollTimer: null,
    lastSig: "",
    lastRenderKey: "",
  };
  return node.__mkrshiftSocialState;
}

function clearStateTimer(state) {
  if (!state?.pollTimer) return;
  clearInterval(state.pollTimer);
  state.pollTimer = null;
}

function normalizeDomWidgetStack(node, state) {
  if (!Array.isArray(node?.widgets) || !state?.domWidget) return;
  const domWidgets = node.widgets.filter((widget) => String(widget?.name || "") === DOM_WIDGET_NAME);
  if (domWidgets.length > 1) {
    node.widgets = node.widgets.filter((widget) => String(widget?.name || "") !== DOM_WIDGET_NAME || widget === state.domWidget);
  }
  const index = node.widgets.indexOf(state.domWidget);
  if (index > -1 && index !== node.widgets.length - 1) {
    node.widgets.splice(index, 1);
    node.widgets.push(state.domWidget);
  }
}

function getSelectedPack(state) {
  if (!Array.isArray(state?.packs) || !state.packs.length) return null;
  return state.packs.find((pack) => pack.id === state.selectedPackId) || state.packs[0] || null;
}

function syncPackSelection(node, state, packId) {
  const clean = String(packId || "").trim();
  if (!clean) return;
  state.selectedPackId = clean;
  node.properties = node.properties || {};
  node.properties.selected_pack_id = clean;

  const packWidget = getWidget(node, "pack");
  if (packWidget) {
    const match = getWidgetChoices(packWidget).find((choice) => extractPackId(choice) === clean);
    if (match && String(packWidget.value) !== String(match)) {
      setWidgetValue(node, packWidget, match);
      return;
    }
  }

  refreshCompactUI(node);
}

function applyPackDefaults(node, state) {
  const selectedPack = getSelectedPack(state);
  if (!selectedPack) return;

  const countWidget = getWidget(node, "count");
  if (countWidget) {
    const min = Number(countWidget.options?.min ?? 1);
    const max = Number(countWidget.options?.max ?? 999);
    const fallback = Number(countWidget.value ?? min);
    const raw = Number(selectedPack.default_count ?? fallback);
    const next = Number.isFinite(raw) ? Math.max(min, Math.min(max, raw)) : fallback;
    setWidgetValue(node, countWidget, next);
  }

  const aspectWidget = getWidget(node, "aspect");
  if (aspectWidget) {
    const choices = getWidgetChoices(aspectWidget).map((value) => String(value));
    if (choices.includes("Auto")) {
      setWidgetValue(node, aspectWidget, "Auto");
    } else if (choices.includes("9:16") && widgetString(node, "output_mode", "Carousel") === "Story") {
      setWidgetValue(node, aspectWidget, "9:16");
    } else if (Array.isArray(selectedPack.ratios) && selectedPack.ratios.length) {
      const preferred = selectedPack.ratios.find((ratio) => choices.includes(String(ratio)));
      if (preferred) {
        setWidgetValue(node, aspectWidget, String(preferred));
      }
    }
  }

  refreshCompactUI(node);
}

function compactWarnings(node, state) {
  const lines = [];

  if (!connectedInput(node, "image")) {
    lines.push({ level: "warn", text: "IMAGE input is not connected." });
  }

  if (widgetString(node, "branding", "Off") !== "Off" && !connectedInput(node, "brand_logo")) {
    lines.push({ level: "warn", text: "Branding is enabled but the logo input is missing." });
  }

  const outputMode = widgetString(node, "output_mode", "Carousel");
  const aspect = widgetString(node, "aspect", "Auto").trim();
  if (outputMode === "Mixed" && aspect && aspect !== "Auto") {
    lines.push({ level: "warn", text: `Mixed mode is locked to ${aspect}. Use Auto if you want the pack ratio cycle.` });
  } else if (outputMode === "Story" && aspect && !["Auto", "9:16"].includes(aspect)) {
    lines.push({ level: "warn", text: `Story mode is currently using ${aspect} instead of a vertical frame.` });
  }

  const backendWarnings = Array.isArray(state?.backendReadiness?.warnings) ? state.backendReadiness.warnings : [];
  for (const warning of backendWarnings) {
    const text = String(warning || "").trim();
    if (!text) continue;
    if (lines.some((entry) => entry.text.toLowerCase() === text.toLowerCase())) continue;
    lines.push({ level: "warn", text });
  }

  if (!lines.length) {
    lines.push({ level: "ok", text: "Ready to queue and generate." });
  }

  return lines.slice(0, 3);
}

function summaryImageInfo(node, state, selectedPack) {
  if (state.previewUrl) {
    return {
      src: state.previewUrl,
      badge: "Source",
      placeholder: "",
      note: "",
    };
  }

  if (selectedPack?.preview) {
    return {
      src: apiUrl(selectedPack.preview),
      badge: "Pack",
      placeholder: "",
      note: connectedInput(node, "image") ? "Queue once to swap the pack preview with your live source image." : "",
    };
  }

  return {
    src: "",
    badge: "",
    placeholder: connectedInput(node, "image")
      ? "Queue once to capture a source preview."
      : "Connect IMAGE to get a preview.",
    note: "",
  };
}

function renderKey(node, state) {
  const selectedPack = getSelectedPack(state);
  const warnings = compactWarnings(node, state).map((entry) => `${entry.level}:${entry.text}`).join("|");
  const ratios = summarizeSequence(effectiveRatioPlan(node, selectedPack), 3);
  const roles = summarizeSequence(effectiveRolePlan(node, Math.max(1, widgetInt(node, "count", selectedPack?.default_count ?? 12))), 4);
  return [
    state.loadingPacks ? "loading" : "idle",
    state.selectedPackId,
    selectedPack?.name || "",
    selectedPack?.preview || "",
    selectedPack?.description || "",
    selectedPack?.default_count || 0,
    Array.isArray(selectedPack?.ratios) ? selectedPack.ratios.join(",") : "",
    widgetString(node, "pack", ""),
    widgetString(node, "output_mode", ""),
    widgetString(node, "aspect", ""),
    widgetString(node, "platform", ""),
    widgetString(node, "branding", ""),
    widgetString(node, "count", ""),
    state.previewUrl,
    JSON.stringify(state.backendReadiness || null),
    ratios,
    roles,
    warnings,
    connectedInput(node, "image") ? "image" : "noimage",
    connectedInput(node, "brand_logo") ? "logo" : "nologo",
  ].join("::");
}

function createElement(tag, className = "", text = "") {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

function buildCompactSummary(node, state) {
  const root = state?.dom?.root;
  if (!root || typeof document === "undefined") return;

  const nextKey = renderKey(node, state);
  if (nextKey === state.lastRenderKey) return;
  state.lastRenderKey = nextKey;

  const selectedPack = getSelectedPack(state);
  const ratioPlan = effectiveRatioPlan(node, selectedPack);
  const rolePlan = effectiveRolePlan(node, ratioPlan.length);
  const warnings = compactWarnings(node, state);
  const summaryImage = summaryImageInfo(node, state, selectedPack);
  const shell = createElement("div", "mkr-social-compact");

  const head = createElement("div", "mkr-social-compact__head");
  const intro = createElement("div");
  intro.appendChild(createElement("div", "mkr-social-compact__eyebrow", "Social Builder"));
  intro.appendChild(createElement("div", "mkr-social-compact__title", "Compact Summary"));
  const subtitle = state.loadingPacks
    ? "Refreshing pack metadata..."
    : selectedPack
      ? `${selectedPack.name} selected. Native widgets are the main controls.`
      : "Use the normal widgets above and keep the summary panel for feedback.";
  intro.appendChild(createElement("div", "mkr-social-compact__subtitle", subtitle));

  const actions = createElement("div", "mkr-social-compact__actions");
  const defaultsButton = createElement("button", "mkr-social-compact__button is-primary", "Defaults");
  defaultsButton.type = "button";
  defaultsButton.addEventListener("click", () => applyPackDefaults(node, state));
  actions.appendChild(defaultsButton);

  const reloadButton = createElement("button", "mkr-social-compact__button", "Reload");
  reloadButton.type = "button";
  reloadButton.addEventListener("click", async () => {
    await loadPacks(node, state, true);
  });
  actions.appendChild(reloadButton);
  head.append(intro, actions);
  shell.appendChild(head);

  const content = createElement("div", "mkr-social-compact__content");
  const thumb = createElement("div", "mkr-social-compact__thumb");
  if (summaryImage.src) {
    const img = document.createElement("img");
    img.src = summaryImage.src;
    img.alt = selectedPack?.name || "Social pack preview";
    thumb.appendChild(img);
  } else {
    thumb.appendChild(createElement("div", "mkr-social-compact__thumb-empty", summaryImage.placeholder));
  }
  content.appendChild(thumb);

  const packCol = createElement("div", "mkr-social-compact__pack");
  if (summaryImage.badge) {
    packCol.appendChild(createElement("div", "mkr-social-compact__badge", `${summaryImage.badge} Preview`));
  }
  packCol.appendChild(createElement("div", "mkr-social-compact__pack-name", selectedPack?.name || "No pack selected"));

  const ratioText = Array.isArray(selectedPack?.ratios) && selectedPack.ratios.length
    ? selectedPack.ratios.join(" / ")
    : "Auto";
  const exportType = String(selectedPack?.export?.type || "mixed");
  const metaText = selectedPack
    ? `${selectedPack.default_count ?? 12} assets • ${ratioText} • ${exportType}`
    : "Pack metadata will show here after selection.";
  packCol.appendChild(createElement("div", "mkr-social-compact__meta", metaText));

  const chips = createElement("div", "mkr-social-compact__chips");
  for (const label of [
    `Mode ${widgetString(node, "output_mode", "Carousel")}`,
    `Count ${widgetInt(node, "count", selectedPack?.default_count ?? 12)}`,
    `Ratios ${summarizeSequence(ratioPlan, 3)}`,
    `Pacing ${summarizeSequence(rolePlan, 4)}`,
  ]) {
    chips.appendChild(createElement("span", "mkr-social-compact__chip", label));
  }
  packCol.appendChild(chips);

  const description = selectedPack?.description
    || "Choose a pack and the summary will describe the preset and current plan behavior.";
  packCol.appendChild(createElement("div", "mkr-social-compact__meta", description));
  if (summaryImage.note) {
    packCol.appendChild(createElement("div", "mkr-social-compact__note", summaryImage.note));
  }
  content.appendChild(packCol);
  shell.appendChild(content);

  const warningsBox = createElement("div", "mkr-social-compact__warnings");
  for (const line of warnings) {
    const row = createElement("div", `mkr-social-compact__warning${line.level === "ok" ? " is-ok" : ""}`);
    row.appendChild(createElement("span", "mkr-social-compact__warning-dot"));
    row.appendChild(createElement("div", "mkr-social-compact__warning-text", line.text));
    warningsBox.appendChild(row);
  }
  shell.appendChild(warningsBox);

  root.replaceChildren(shell);
}

function createDomWidget(node, state) {
  if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return false;
  if (state.domWidget) return true;

  ensureStyle();
  const root = document.createElement("div");
  root.style.cssText = "width:100%;box-sizing:border-box;";
  const widget = node.addDOMWidget(DOM_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => MIN_SUMMARY_H,
    getMaxHeight: () => MIN_SUMMARY_H,
  });
  if (!widget) return false;

  widget.serialize = false;
  state.dom = { root };
  state.domWidget = widget;
  normalizeDomWidgetStack(node, state);
  buildCompactSummary(node, state);
  return true;
}

function compactUiSignature(node, state) {
  return [
    widgetString(node, "pack", ""),
    widgetString(node, "output_mode", ""),
    widgetString(node, "count", ""),
    widgetString(node, "aspect", ""),
    widgetString(node, "platform", ""),
    widgetString(node, "branding", ""),
    widgetString(node, "caption_tone", ""),
    widgetString(node, "objective", ""),
    widgetString(node, "hook_style", ""),
    widgetString(node, "cta_mode", ""),
    widgetString(node, "hashtag_mode", ""),
    connectedInput(node, "image") ? "image" : "noimage",
    connectedInput(node, "brand_logo") ? "logo" : "nologo",
    state.previewUrl,
    JSON.stringify(state.backendReadiness || null),
  ].join("|");
}

function refreshCompactUI(node) {
  const state = ensureState(node);
  const selected = selectedPackIdFromNode(node);
  if (selected && selected !== state.selectedPackId) {
    state.selectedPackId = selected;
  }
  normalizeDomWidgetStack(node, state);
  buildCompactSummary(node, state);
}

async function loadPacks(node, state, force = false) {
  state.loadingPacks = true;
  refreshCompactUI(node);
  markDirty(node);

  const remotePacks = await fetchPacksFromBackend(force);
  state.packs = Array.isArray(remotePacks) && remotePacks.length ? remotePacks : fallbackPacksFromWidget(node);

  const selected = selectedPackIdFromNode(node) || state.packs[0]?.id || "";
  if (selected) {
    state.selectedPackId = selected;
  }

  state.loadingPacks = false;
  refreshCompactUI(node);
  markDirty(node);
}

function attachHandlers(node, state) {
  if (node.__mkrshiftSocialCompactAttached) return;
  node.__mkrshiftSocialCompactAttached = true;

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    originalExecuted?.apply(this, arguments);
    const readinessInfo = message?.readiness?.[0] ?? message?.ui?.readiness?.[0] ?? null;
    if (readinessInfo) {
      state.backendReadiness = readinessInfo;
    }
    const previewInfo = message?.input_preview?.[0] ?? message?.ui?.input_preview?.[0] ?? null;
    if (previewInfo?.filename) {
      state.previewUrl = `${buildViewUrl(previewInfo)}&_ts=${Date.now()}`;
    }
    refreshCompactUI(this);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    originalConfigure?.apply(this, arguments);
    restoreVisibleWidgets(this);
    createDomWidget(this, state);
    refreshCompactUI(this);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    const out = originalConnectionsChange?.apply(this, arguments);
    refreshCompactUI(this);
    return out;
  };

  const originalRemoved = node.onRemoved;
  node.onRemoved = function onRemoved() {
    clearStateTimer(state);
    return originalRemoved?.apply(this, arguments);
  };
}

function startPolling(node, state) {
  clearStateTimer(state);
  state.lastSig = compactUiSignature(node, state);
  state.pollTimer = setInterval(() => {
    const nextSig = compactUiSignature(node, state);
    if (nextSig === state.lastSig) return;
    state.lastSig = nextSig;
    refreshCompactUI(node);
  }, POLL_MS);
}

async function initializeSocialPackNode(node) {
  ensureStyle();
  const state = ensureState(node);
  restoreVisibleWidgets(node);
  node.resizable = true;
  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [DEFAULT_W, DEFAULT_H];
  }
  node.size[0] = Math.max(DEFAULT_W, Number(node.size[0] || DEFAULT_W));
  node.size[1] = Math.max(DEFAULT_H, Number(node.size[1] || DEFAULT_H));

  createDomWidget(node, state);
  attachHandlers(node, state);
  startPolling(node, state);
  refreshCompactUI(node);
  await loadPacks(node, state, false);
}

app.registerExtension({
  name: EXT,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!isSocialPackNodeDef(nodeData)) return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      originalOnNodeCreated?.apply(this, arguments);
      initializeSocialPackNode(this).catch((error) => {
        console.error("[mkrshift.socialpack] init failed in onNodeCreated:", error);
      });
    };
  },
  async nodeCreated(node) {
    if (!isSocialPackNode(node)) return;
    await initializeSocialPackNode(node);
  },
});
