import { app } from "../../../scripts/app.js";
import {
  getBoolean,
  getValue,
  hideWidgets,
  installBundledSettingsAdapter,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ToggleSwitchNode";
const SETTINGS_WIDGET_NAME = "settings_json";
const PANEL_WIDGET_NAME = "mkr_toggle_switch_panel";
const STYLE_ID = "mkr-toggle-switch-style-v7";
const HOST_CLASS = "mkr-toggle-shell-node";
const NODE_KEYS = new Set(["MKRToggleSwitch", "Toggle Switch"]);

const DEFAULTS = {
  enabled: true,
  theme: "lime",
};

const NODE_WIDTH = 136;
const NODE_HEIGHT = 248;
const PANEL_WIDTH = 136;
const PANEL_HEIGHT = 248;
const BODY_X = 12;
const BODY_Y = 28;
const BODY_WIDTH = 112;
const BODY_HEIGHT = 204;
const PORT_INPUT_X = 18;
const PORT_INPUT_Y = 58;
const PORT_OUTPUT_X = NODE_WIDTH - 18;
const PORT_OUTPUT_Y = NODE_HEIGHT - 22;
const TITLE_TEXT = "Toggle";

const THEMES = {
  lime: {
    accent: "#b8ef52",
    accentDark: "#84ab27",
    border: "#e2ff9a",
    glow: "rgba(191, 255, 97, 0.26)",
    badge: "#e7ff63",
    label: "#daff6b",
    ring: "#dfff78",
  },
  graphite: {
    accent: "#e6ecf3",
    accentDark: "#9ba5b1",
    border: "#fbfdff",
    glow: "rgba(236, 242, 247, 0.16)",
    badge: "#f4f7fb",
    label: "#eef3f8",
    ring: "#ffffff",
  },
  rose: {
    accent: "#ff87c6",
    accentDark: "#d65394",
    border: "#ffd2eb",
    glow: "rgba(255, 120, 192, 0.24)",
    badge: "#ffef59",
    label: "#ffd7ef",
    ring: "#ffd9f0",
  },
  amber: {
    accent: "#ffb451",
    accentDark: "#db7f12",
    border: "#ffe1af",
    glow: "rgba(255, 185, 95, 0.22)",
    badge: "#ffef59",
    label: "#ffe79d",
    ring: "#fff0b8",
  },
};

function getLiteGraphGlobal() {
  return globalThis.LiteGraph || globalThis.window?.LiteGraph || null;
}

function getSettingValue(id, fallback) {
  const value =
    app?.extensionManager?.setting?.get?.(id) ??
    app?.ui?.settings?.getSettingValue?.(id);
  return value ?? fallback;
}

function isVueNodesEnabled() {
  return Boolean(
    getSettingValue(
      "Comfy.VueNodes.Enabled",
      document?.documentElement?.classList?.contains("tl-vue-node-theme-active") ?? false,
    ),
  );
}

function shouldUseDomRenderer(node) {
  return Boolean(node?.addDOMWidget) && isVueNodesEnabled();
}

function normalizeTheme(value) {
  const key = String(value || DEFAULTS.theme).trim().toLowerCase();
  return THEMES[key] ? key : DEFAULTS.theme;
}

function isToggleNode(candidate) {
  return [candidate?.comfyClass, candidate?.type, candidate?.constructor?.type, candidate?.title]
    .some((value) => NODE_KEYS.has(String(value || "")));
}

function isToggleNodeDef(nodeData) {
  return [nodeData?.name, nodeData?.display_name, nodeData?.type]
    .some((value) => NODE_KEYS.has(String(value || "")));
}

function hasLinkedInput(node) {
  return !!node?.inputs?.[0]?.link;
}

function getThemeName(node) {
  return normalizeTheme(getValue(node, "theme", DEFAULTS.theme));
}

function getNodeState(node) {
  const runtime = node?.__mkrToggleRuntime;
  return {
    enabled: runtime?.enabled ?? getBoolean(node, "enabled", DEFAULTS.enabled),
    theme: normalizeTheme(runtime?.theme ?? getThemeName(node)),
    controlledByInput: hasLinkedInput(node),
  };
}

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    html .lg-node.${HOST_CLASS},
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} {
      width: ${NODE_WIDTH}px !important;
      min-width: ${NODE_WIDTH}px !important;
      max-width: ${NODE_WIDTH}px !important;
      height: ${NODE_HEIGHT}px !important;
      min-height: ${NODE_HEIGHT}px !important;
      max-height: ${NODE_HEIGHT}px !important;
      background: transparent !important;
      background-image: none !important;
      border: 0 !important;
      box-shadow: none !important;
      padding: 0 !important;
      overflow: visible !important;
    }

    html .lg-node.${HOST_CLASS}::before,
    html .lg-node.${HOST_CLASS}::after,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS}::before,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS}::after {
      display: none !important;
    }

    html .lg-node.${HOST_CLASS} .lg-node-header,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-node-header {
      display: none !important;
      height: 0 !important;
      min-height: 0 !important;
      padding: 0 !important;
      margin: 0 !important;
      overflow: hidden !important;
      opacity: 0 !important;
    }

    html .lg-node.${HOST_CLASS} > [data-testid^="node-body-"],
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} > [data-testid^="node-body-"] {
      width: ${NODE_WIDTH}px !important;
      min-width: ${NODE_WIDTH}px !important;
      max-width: ${NODE_WIDTH}px !important;
      height: ${NODE_HEIGHT}px !important;
      min-height: ${NODE_HEIGHT}px !important;
      max-height: ${NODE_HEIGHT}px !important;
      background: transparent !important;
      border: 0 !important;
      box-shadow: none !important;
      padding: 0 !important;
      margin: 0 !important;
      overflow: visible !important;
      display: block !important;
      position: relative !important;
    }

    html .lg-node.${HOST_CLASS} .lg-slot--input,
    html .lg-node.${HOST_CLASS} .lg-slot--output,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--input,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--output {
      position: absolute !important;
      width: 0 !important;
      min-width: 0 !important;
      max-width: 0 !important;
      margin: 0 !important;
      padding: 0 !important;
      font-size: 0 !important;
      line-height: 0 !important;
      color: transparent !important;
      text-shadow: none !important;
      overflow: visible !important;
      z-index: 5 !important;
    }

    html .lg-node.${HOST_CLASS} .lg-slot--input,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--input {
      left: ${PORT_INPUT_X}px !important;
      top: ${PORT_INPUT_Y}px !important;
      right: auto !important;
      bottom: auto !important;
      transform: none !important;
    }

    html .lg-node.${HOST_CLASS} .lg-slot--output,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--output {
      left: auto !important;
      top: auto !important;
      right: ${NODE_WIDTH - PORT_OUTPUT_X}px !important;
      bottom: ${NODE_HEIGHT - PORT_OUTPUT_Y}px !important;
      transform: none !important;
    }

    html .lg-node.${HOST_CLASS} .lg-slot--input *,
    html .lg-node.${HOST_CLASS} .lg-slot--output *,
    html .lg-node.${HOST_CLASS} [data-testid*="node-input"],
    html .lg-node.${HOST_CLASS} [data-testid*="node-output"],
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--input *,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--output *,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} [data-testid*="node-input"],
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} [data-testid*="node-output"] {
      font-size: 0 !important;
      line-height: 0 !important;
      color: transparent !important;
      text-shadow: none !important;
    }

    html .lg-node.${HOST_CLASS} .lg-slot--input > :not(.slot-dot),
    html .lg-node.${HOST_CLASS} .lg-slot--output > :not(.slot-dot),
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--input > :not(.slot-dot),
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .lg-slot--output > :not(.slot-dot) {
      display: none !important;
    }

    html .lg-node.${HOST_CLASS} .slot-dot,
    html.tl-vue-node-theme-active .lg-node.${HOST_CLASS} .slot-dot {
      width: 10px !important;
      height: 10px !important;
      min-width: 10px !important;
      min-height: 10px !important;
      margin: 0 !important;
      border-radius: 999px !important;
    }

    .mkr-toggle-panel {
      position: relative;
      width: ${PANEL_WIDTH}px;
      height: ${PANEL_HEIGHT}px;
      pointer-events: auto;
      user-select: none;
      -webkit-user-select: none;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: rgba(244, 247, 252, 0.96);
      overflow: visible;
    }

    .mkr-toggle-panel * {
      box-sizing: border-box;
    }

    .mkr-toggle-badge {
      position: absolute;
      top: 2px;
      right: 8px;
      min-width: 66px;
      height: 22px;
      padding: 0 10px;
      border: 0;
      border-radius: 10px;
      background: rgba(9, 12, 17, 0.96);
      color: var(--mkr-toggle-badge, #e7ff63);
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.02em;
      box-shadow: 0 8px 18px rgba(0, 0, 0, 0.26);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      z-index: 3;
    }

    .mkr-toggle-shell {
      position: absolute;
      left: ${BODY_X}px;
      top: ${BODY_Y}px;
      width: ${BODY_WIDTH}px;
      height: ${BODY_HEIGHT}px;
      border-radius: 30px;
      background:
        radial-gradient(120% 85% at 50% 0%, rgba(98, 127, 180, 0.14) 0%, transparent 50%),
        linear-gradient(180deg, rgba(25, 31, 42, 0.98) 0%, rgba(10, 14, 20, 0.995) 100%);
      border: 1px solid rgba(88, 118, 173, 0.34);
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.06),
        0 18px 30px rgba(0, 0, 0, 0.24);
      overflow: hidden;
    }

    .mkr-toggle-shell::before {
      content: "";
      position: absolute;
      inset: 1px;
      border-radius: 29px;
      border: 1px solid rgba(255, 255, 255, 0.03);
      pointer-events: none;
    }

    .mkr-toggle-top-dot {
      position: absolute;
      left: 18px;
      top: 18px;
      width: 11px;
      height: 11px;
      border-radius: 999px;
      background: rgba(72, 95, 132, 0.78);
      box-shadow: 0 0 0 2px rgba(34, 46, 68, 0.44);
      pointer-events: none;
    }

    .mkr-toggle-rivet {
      position: absolute;
      width: 25px;
      height: 25px;
      border-radius: 999px;
      background:
        radial-gradient(circle at 35% 35%, rgba(255,255,255,0.54) 0%, rgba(255,255,255,0.16) 18%, rgba(167,171,188,0.14) 26%, rgba(61,67,86,0.8) 62%, rgba(26,30,40,0.98) 100%);
      border: 1px solid rgba(181, 192, 219, 0.16);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.1),
        0 4px 10px rgba(0,0,0,0.18);
      pointer-events: none;
    }

    .mkr-toggle-rivet--top {
      left: 26px;
      top: 30px;
    }

    .mkr-toggle-rivet--bottom {
      right: 18px;
      bottom: 18px;
    }

    .mkr-toggle-title {
      position: absolute;
      left: 42px;
      right: 18px;
      top: 20px;
      text-align: center;
      font-size: 15px;
      line-height: 1;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: rgba(241, 245, 251, 0.96);
      pointer-events: none;
    }

    .mkr-toggle-indicator {
      position: absolute;
      left: 50%;
      top: 56px;
      transform: translateX(-50%);
      width: 12px;
      height: 12px;
      border-radius: 999px;
      border: 2px solid var(--mkr-toggle-ring, #dfff78);
      box-shadow: 0 0 10px var(--mkr-toggle-glow, rgba(191,255,97,0.26));
      pointer-events: none;
    }

    .mkr-toggle-switch {
      position: absolute;
      left: 50%;
      top: 74px;
      width: 64px;
      height: 98px;
      transform: translateX(-50%);
      border: 0;
      border-radius: 18px;
      padding: 0;
      background:
        radial-gradient(circle at 50% 0%, rgba(255,255,255,0.08), transparent 34%),
        linear-gradient(180deg, rgba(8, 12, 18, 0.88) 0%, rgba(8, 12, 18, 0.96) 100%);
      box-shadow:
        0 0 0 1px rgba(255,255,255,0.04),
        0 0 26px rgba(0,0,0,0.32);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: transform 120ms ease, filter 120ms ease;
    }

    .mkr-toggle-switch:hover {
      filter: brightness(1.03);
    }

    .mkr-toggle-switch:active {
      transform: translateX(-50%) translateY(1px);
    }

    .mkr-toggle-switch:disabled {
      cursor: not-allowed;
      filter: none;
    }

    .mkr-toggle-face {
      position: relative;
      width: 56px;
      height: 90px;
      border-radius: 15px;
      background: linear-gradient(180deg, var(--mkr-toggle-accent, #b8ef52) 0%, var(--mkr-toggle-accent, #b8ef52) 42%, var(--mkr-toggle-accent-dark, #84ab27) 42%, var(--mkr-toggle-accent-dark, #84ab27) 100%);
      box-shadow:
        0 0 0 2px var(--mkr-toggle-border, #e2ff9a),
        0 0 18px var(--mkr-toggle-glow, rgba(191,255,97,0.26)),
        inset 0 1px 0 rgba(255,255,255,0.26),
        inset 0 -8px 14px rgba(0,0,0,0.12);
    }

    .mkr-toggle-panel[data-enabled="false"] .mkr-toggle-face {
      background: linear-gradient(180deg, #dce3ea 0%, #dce3ea 42%, #98a2ad 42%, #98a2ad 100%);
      box-shadow:
        0 0 0 2px rgba(245, 248, 250, 0.92),
        inset 0 1px 0 rgba(255,255,255,0.28),
        inset 0 -8px 14px rgba(0,0,0,0.12);
    }

    .mkr-toggle-face::before {
      content: "";
      position: absolute;
      left: 50%;
      top: 22px;
      width: 25px;
      height: 25px;
      transform: translateX(-50%);
      border-radius: 999px;
      border: 5px solid rgba(255,255,255,0.96);
      box-sizing: border-box;
    }

    .mkr-toggle-face::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 47px;
      width: 6px;
      height: 30px;
      transform: translateX(-50%);
      border-radius: 999px;
      background: rgba(255,255,255,0.98);
    }

    .mkr-toggle-status {
      position: absolute;
      left: 50%;
      bottom: 44px;
      transform: translateX(-50%);
      font-size: 11px;
      line-height: 1;
      font-weight: 900;
      letter-spacing: 0.08em;
      color: var(--mkr-toggle-label, #daff6b);
      text-shadow: 0 0 12px var(--mkr-toggle-glow, rgba(191,255,97,0.26));
      pointer-events: none;
    }

    .mkr-toggle-panel[data-enabled="false"] .mkr-toggle-status {
      color: rgba(229, 234, 241, 0.94);
      text-shadow: none;
    }

    .mkr-toggle-panel[data-controlled="true"] .mkr-toggle-indicator {
      border-color: rgba(255, 193, 107, 0.96);
      box-shadow: 0 0 10px rgba(255, 193, 107, 0.26);
    }
  `;
  document.head.appendChild(style);
}

function applyConnectionMetadata(node) {
  if (!node) return;
  const input = node.inputs?.[0];
  if (input) {
    input.name = "";
    input.label = "";
    input.localized_name = "";
    input.pos = [PORT_INPUT_X, PORT_INPUT_Y];
  }

  const output = node.outputs?.[0];
  if (output) {
    output.name = "";
    output.label = "";
    output.localized_name = "";
    output.pos = [PORT_OUTPUT_X, PORT_OUTPUT_Y];
  }
}

function setPoint(out, x, y) {
  if (out && typeof out === "object") {
    out[0] = x;
    out[1] = y;
    return out;
  }
  return [x, y];
}

function installConnectionOverride(node) {
  if (!node || node.__mkrToggleConnectionOverrideInstalled) return;
  node.__mkrToggleConnectionOverrideInstalled = true;

  const originalGetConnectionPos = typeof node.getConnectionPos === "function" ? node.getConnectionPos : null;
  node.getConnectionPos = function getConnectionPos(isInput, slotNumber, out) {
    if (this.flags?.collapsed) {
      return originalGetConnectionPos?.call(this, isInput, slotNumber, out) ?? setPoint(out, this.pos[0], this.pos[1]);
    }
    return setPoint(
      out,
      this.pos[0] + (isInput ? PORT_INPUT_X : PORT_OUTPUT_X),
      this.pos[1] + (isInput ? PORT_INPUT_Y : PORT_OUTPUT_Y),
    );
  };

  const originalComputeSize = typeof node.computeSize === "function" ? node.computeSize : null;
  node.computeSize = function computeSize() {
    if (this.flags?.collapsed && originalComputeSize) {
      return originalComputeSize.apply(this, arguments);
    }
    return [NODE_WIDTH, NODE_HEIGHT];
  };
}

function applyNodeChrome(node) {
  if (!node) return;
  const litegraph = getLiteGraphGlobal();
  node.resizable = false;
  node.collapsable = false;
  node.flags = typeof node.flags === "object" && node.flags !== null ? node.flags : {};
  node.flags.resizable = false;
  node.color = "rgba(0, 0, 0, 0)";
  node.bgcolor = "rgba(0, 0, 0, 0)";
  node.boxcolor = "rgba(0, 0, 0, 0)";
  node.title = "";
  if (litegraph?.NO_TITLE !== undefined) {
    node.title_mode = litegraph.NO_TITLE;
  }
  if (Number(node.size?.[0] || 0) !== NODE_WIDTH || Number(node.size?.[1] || 0) !== NODE_HEIGHT) {
    node.size = [NODE_WIDTH, NODE_HEIGHT];
  }
  applyConnectionMetadata(node);
}

function setNodeEnabled(node, enabled) {
  setWidgetValue(node, "enabled", !!enabled);
  if (!hasLinkedInput(node)) {
    node.__mkrToggleRuntime = null;
  }
  syncPresentation(node);
}

function cycleTheme(node) {
  const keys = Object.keys(THEMES);
  const current = getThemeName(node);
  const index = Math.max(0, keys.indexOf(current));
  const next = keys[(index + 1) % keys.length];
  setWidgetValue(node, "theme", next);
  if (node.__mkrToggleRuntime) {
    node.__mkrToggleRuntime.theme = next;
  }
  syncPresentation(node);
}

function createPanel(node) {
  ensureStyles();

  const root = document.createElement("div");
  root.className = "mkr-toggle-panel";

  const badge = document.createElement("button");
  badge.type = "button";
  badge.className = "mkr-toggle-badge";
  badge.textContent = "MKRShift";
  badge.title = "Cycle switch theme";

  const shell = document.createElement("div");
  shell.className = "mkr-toggle-shell";

  const topDot = document.createElement("div");
  topDot.className = "mkr-toggle-top-dot";

  const rivetTop = document.createElement("div");
  rivetTop.className = "mkr-toggle-rivet mkr-toggle-rivet--top";

  const rivetBottom = document.createElement("div");
  rivetBottom.className = "mkr-toggle-rivet mkr-toggle-rivet--bottom";

  const title = document.createElement("div");
  title.className = "mkr-toggle-title";
  title.textContent = TITLE_TEXT;

  const indicator = document.createElement("div");
  indicator.className = "mkr-toggle-indicator";

  const switchButton = document.createElement("button");
  switchButton.type = "button";
  switchButton.className = "mkr-toggle-switch";
  switchButton.title = "Toggle switch";

  const face = document.createElement("div");
  face.className = "mkr-toggle-face";

  const status = document.createElement("div");
  status.className = "mkr-toggle-status";

  switchButton.appendChild(face);
  shell.appendChild(topDot);
  shell.appendChild(rivetTop);
  shell.appendChild(title);
  shell.appendChild(indicator);
  shell.appendChild(switchButton);
  shell.appendChild(status);
  shell.appendChild(rivetBottom);
  root.appendChild(badge);
  root.appendChild(shell);

  const halt = (event) => event.stopPropagation();
  badge.addEventListener("pointerdown", halt);
  switchButton.addEventListener("pointerdown", halt);

  badge.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    cycleTheme(node);
  });

  switchButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (hasLinkedInput(node)) return;
    const state = getNodeState(node);
    setNodeEnabled(node, !state.enabled);
  });

  switchButton.addEventListener("dblclick", (event) => {
    event.preventDefault();
    event.stopPropagation();
    cycleTheme(node);
  });

  node.__mkrTogglePanel = {
    root,
    badge,
    title,
    switchButton,
    status,
  };

  syncPanel(node);
  return root;
}

function ensurePanelWidget(node) {
  if (!shouldUseDomRenderer(node) || !node?.addDOMWidget) return null;
  if (node.__mkrTogglePanelWidget) return node.__mkrTogglePanelWidget;

  const root = createPanel(node);
  const widget = node.addDOMWidget(PANEL_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
  });

  widget.computeSize = () => [PANEL_WIDTH, PANEL_HEIGHT];
  widget.computeLayoutSize = () => ({
    minHeight: PANEL_HEIGHT,
    maxHeight: PANEL_HEIGHT,
    minWidth: PANEL_WIDTH,
    preferredWidth: PANEL_WIDTH,
  });
  widget.y = 0;
  widget.last_y = 0;

  node.__mkrTogglePanelWidget = widget;
  scheduleHostChromeSync(node);
  return widget;
}

function syncPanel(node) {
  const panel = node?.__mkrTogglePanel;
  if (!panel?.root) return;

  const state = getNodeState(node);
  const theme = THEMES[state.theme] || THEMES[DEFAULTS.theme];
  panel.root.dataset.enabled = state.enabled ? "true" : "false";
  panel.root.dataset.controlled = state.controlledByInput ? "true" : "false";
  panel.root.style.setProperty("--mkr-toggle-accent", theme.accent);
  panel.root.style.setProperty("--mkr-toggle-accent-dark", theme.accentDark);
  panel.root.style.setProperty("--mkr-toggle-border", theme.border);
  panel.root.style.setProperty("--mkr-toggle-glow", theme.glow);
  panel.root.style.setProperty("--mkr-toggle-badge", theme.badge);
  panel.root.style.setProperty("--mkr-toggle-label", state.enabled ? theme.label : "#e5eaf1");
  panel.root.style.setProperty("--mkr-toggle-ring", state.controlledByInput ? "#ffc16b" : theme.ring);
  panel.switchButton.disabled = state.controlledByInput;
  panel.switchButton.title = state.controlledByInput ? "Driven by state_in" : "Toggle switch";
  panel.status.textContent = state.enabled ? "ON" : "OFF";
  panel.title.textContent = TITLE_TEXT;
  scheduleHostChromeSync(node);
}

function syncHostChrome(node) {
  if (!shouldUseDomRenderer(node)) return false;
  const root = node?.__mkrTogglePanel?.root;
  if (!root?.isConnected) return false;

  const body = root.closest('[data-testid^="node-body-"]');
  const host = body?.closest(".lg-node") || root.closest(".lg-node");
  if (!host || !body) return false;

  host.classList.add(HOST_CLASS);
  root.style.display = "block";
  root.style.width = `${PANEL_WIDTH}px`;
  root.style.height = `${PANEL_HEIGHT}px`;

  host.style.setProperty("width", `${NODE_WIDTH}px`, "important");
  host.style.setProperty("min-width", `${NODE_WIDTH}px`, "important");
  host.style.setProperty("max-width", `${NODE_WIDTH}px`, "important");
  host.style.setProperty("height", `${NODE_HEIGHT}px`, "important");
  host.style.setProperty("min-height", `${NODE_HEIGHT}px`, "important");
  host.style.setProperty("max-height", `${NODE_HEIGHT}px`, "important");
  host.style.setProperty("background", "transparent", "important");
  host.style.setProperty("border", "0", "important");
  host.style.setProperty("box-shadow", "none", "important");
  host.style.setProperty("overflow", "visible", "important");

  body.style.setProperty("width", `${NODE_WIDTH}px`, "important");
  body.style.setProperty("min-width", `${NODE_WIDTH}px`, "important");
  body.style.setProperty("max-width", `${NODE_WIDTH}px`, "important");
  body.style.setProperty("height", `${NODE_HEIGHT}px`, "important");
  body.style.setProperty("min-height", `${NODE_HEIGHT}px`, "important");
  body.style.setProperty("max-height", `${NODE_HEIGHT}px`, "important");
  body.style.setProperty("padding", "0", "important");
  body.style.setProperty("margin", "0", "important");
  body.style.setProperty("background", "transparent", "important");
  body.style.setProperty("border", "0", "important");
  body.style.setProperty("box-shadow", "none", "important");
  body.style.setProperty("overflow", "visible", "important");

  const header = host.querySelector(".lg-node-header");
  if (header) {
    header.style.setProperty("display", "none", "important");
    header.style.setProperty("height", "0", "important");
    header.style.setProperty("padding", "0", "important");
    header.style.setProperty("margin", "0", "important");
    header.style.setProperty("opacity", "0", "important");
  }

  host.querySelectorAll(".lg-slot").forEach((slot) => {
    slot.style.setProperty("position", "absolute", "important");
    slot.style.setProperty("width", "0", "important");
    slot.style.setProperty("min-width", "0", "important");
    slot.style.setProperty("max-width", "0", "important");
    slot.style.setProperty("margin", "0", "important");
    slot.style.setProperty("padding", "0", "important");
    slot.style.setProperty("overflow", "visible", "important");
    slot.style.setProperty("font-size", "0", "important");
    slot.style.setProperty("line-height", "0", "important");
    slot.style.setProperty("color", "transparent", "important");
    slot.style.setProperty("text-shadow", "none", "important");

    if (slot.classList.contains("lg-slot--input")) {
      slot.style.setProperty("left", `${PORT_INPUT_X}px`, "important");
      slot.style.setProperty("top", `${PORT_INPUT_Y}px`, "important");
      slot.style.setProperty("right", "auto", "important");
      slot.style.setProperty("bottom", "auto", "important");
      slot.style.setProperty("transform", "none", "important");
    } else if (slot.classList.contains("lg-slot--output")) {
      slot.style.setProperty("left", "auto", "important");
      slot.style.setProperty("top", "auto", "important");
      slot.style.setProperty("right", `${NODE_WIDTH - PORT_OUTPUT_X}px`, "important");
      slot.style.setProperty("bottom", `${NODE_HEIGHT - PORT_OUTPUT_Y}px`, "important");
      slot.style.setProperty("transform", "none", "important");
    }

    slot.querySelectorAll(".text-node-component-slot-text").forEach((label) => {
      label.style.setProperty("display", "none", "important");
    });

    slot.querySelectorAll(":scope > div").forEach((child) => {
      if (!child.classList.contains("slot-dot") && !child.querySelector(".slot-dot")) {
        child.style.setProperty("display", "none", "important");
      }
    });
  });

  return true;
}

function scheduleHostChromeSync(node, attempts = 12) {
  if (!shouldUseDomRenderer(node)) return;
  if (!node || node.__mkrToggleChromeSyncQueued) return;
  node.__mkrToggleChromeSyncQueued = true;
  requestAnimationFrame(() => {
    node.__mkrToggleChromeSyncQueued = false;
    const synced = syncHostChrome(node);
    if (!synced && attempts > 0) {
      setTimeout(() => scheduleHostChromeSync(node, attempts - 1), 24);
    }
  });
}

function installHostChromeLoop(node) {
  if (!shouldUseDomRenderer(node) || node.__mkrToggleChromeLoopInstalled) return;
  node.__mkrToggleChromeLoopInstalled = true;
  node.__mkrToggleChromeLoopId = window.setInterval(() => {
    if (!node?.graph || !node.__mkrTogglePanel?.root) return;
    scheduleHostChromeSync(node, 2);
  }, 250);
}

function hasConnectedPanel(node) {
  return !!node?.__mkrTogglePanel?.root?.isConnected;
}

function pointInRect(point, rect) {
  if (!point || !rect) return false;
  return point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h;
}

function getLocalPoint(node, event, pos) {
  if (Array.isArray(pos) && pos.length >= 2) {
    return { x: pos[0], y: pos[1] };
  }
  if (typeof event?.canvasX === "number" && typeof event?.canvasY === "number") {
    return {
      x: event.canvasX - node.pos[0],
      y: event.canvasY - node.pos[1],
    };
  }
  return null;
}

function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.max(0, Math.min(r, w * 0.5, h * 0.5));
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function drawRivet(ctx, cx, cy, radius) {
  const gradient = ctx.createRadialGradient(cx - radius * 0.3, cy - radius * 0.35, radius * 0.18, cx, cy, radius);
  gradient.addColorStop(0, "rgba(255,255,255,0.54)");
  gradient.addColorStop(0.18, "rgba(255,255,255,0.16)");
  gradient.addColorStop(0.26, "rgba(167,171,188,0.14)");
  gradient.addColorStop(0.62, "rgba(61,67,86,0.8)");
  gradient.addColorStop(1, "rgba(26,30,40,0.98)");
  ctx.save();
  ctx.fillStyle = gradient;
  ctx.strokeStyle = "rgba(181, 192, 219, 0.16)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawPowerGlyph(ctx, x, y) {
  ctx.strokeStyle = "rgba(255,255,255,0.96)";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(x, y, 10, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "rgba(255,255,255,0.98)";
  roundRect(ctx, x - 3, y + 12, 6, 30, 3);
  ctx.fill();
}

function getCanvasLayout() {
  return {
    badge: { x: 66, y: 2, w: 62, h: 22, r: 10 },
    shell: { x: BODY_X, y: BODY_Y, w: BODY_WIDTH, h: BODY_HEIGHT, r: 30 },
    topDot: { x: 24, y: 46, r: 5.5 },
    rivetTop: { x: 39, y: 58, r: 12.5 },
    rivetBottom: { x: 105, y: 213, r: 12.5 },
    title: { x: 68, y: 51 },
    indicator: { x: 68, y: 91, r: 6 },
    switchRect: { x: 36, y: 102, w: 64, h: 98, r: 18 },
    faceRect: { x: 40, y: 106, w: 56, h: 90, r: 15 },
    status: { x: 68, y: 207 },
  };
}

function drawCanvasFallback(node, ctx) {
  const state = getNodeState(node);
  const theme = THEMES[state.theme] || THEMES[DEFAULTS.theme];
  const layout = getCanvasLayout();

  ctx.save();

  roundRect(ctx, layout.badge.x, layout.badge.y, layout.badge.w, layout.badge.h, layout.badge.r);
  ctx.fillStyle = "rgba(9, 12, 17, 0.96)";
  ctx.fill();
  ctx.fillStyle = theme.badge;
  ctx.font = "900 10px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("MKRShift", layout.badge.x + (layout.badge.w * 0.5), layout.badge.y + (layout.badge.h * 0.5));

  roundRect(ctx, layout.shell.x, layout.shell.y, layout.shell.w, layout.shell.h, layout.shell.r);
  const shellGradient = ctx.createLinearGradient(0, layout.shell.y, 0, layout.shell.y + layout.shell.h);
  shellGradient.addColorStop(0, "rgba(25, 31, 42, 0.98)");
  shellGradient.addColorStop(1, "rgba(10, 14, 20, 0.995)");
  ctx.fillStyle = shellGradient;
  ctx.fill();
  ctx.strokeStyle = "rgba(88, 118, 173, 0.34)";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = "rgba(72, 95, 132, 0.78)";
  ctx.beginPath();
  ctx.arc(layout.topDot.x, layout.topDot.y, layout.topDot.r, 0, Math.PI * 2);
  ctx.fill();

  drawRivet(ctx, layout.rivetTop.x, layout.rivetTop.y, layout.rivetTop.r);
  drawRivet(ctx, layout.rivetBottom.x, layout.rivetBottom.y, layout.rivetBottom.r);

  ctx.fillStyle = "rgba(241, 245, 251, 0.96)";
  ctx.font = "800 15px sans-serif";
  ctx.fillText(TITLE_TEXT, layout.title.x, layout.title.y);

  ctx.strokeStyle = state.controlledByInput ? "rgba(255,193,107,0.96)" : theme.ring;
  ctx.lineWidth = 2;
  ctx.shadowColor = state.controlledByInput ? "rgba(255,193,107,0.26)" : theme.glow;
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ctx.arc(layout.indicator.x, layout.indicator.y, layout.indicator.r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;

  roundRect(ctx, layout.switchRect.x, layout.switchRect.y, layout.switchRect.w, layout.switchRect.h, layout.switchRect.r);
  const switchGradient = ctx.createLinearGradient(0, layout.switchRect.y, 0, layout.switchRect.y + layout.switchRect.h);
  switchGradient.addColorStop(0, "rgba(8, 12, 18, 0.88)");
  switchGradient.addColorStop(1, "rgba(8, 12, 18, 0.96)");
  ctx.fillStyle = switchGradient;
  ctx.fill();

  roundRect(ctx, layout.faceRect.x, layout.faceRect.y, layout.faceRect.w, layout.faceRect.h, layout.faceRect.r);
  const faceGradient = ctx.createLinearGradient(0, layout.faceRect.y, 0, layout.faceRect.y + layout.faceRect.h);
  if (state.enabled) {
    faceGradient.addColorStop(0, theme.accent);
    faceGradient.addColorStop(0.42, theme.accent);
    faceGradient.addColorStop(0.42, theme.accentDark);
    faceGradient.addColorStop(1, theme.accentDark);
    ctx.shadowColor = theme.glow;
    ctx.shadowBlur = 18;
    ctx.strokeStyle = theme.border;
  } else {
    faceGradient.addColorStop(0, "#dce3ea");
    faceGradient.addColorStop(0.42, "#dce3ea");
    faceGradient.addColorStop(0.42, "#98a2ad");
    faceGradient.addColorStop(1, "#98a2ad");
    ctx.shadowColor = "rgba(255,255,255,0.06)";
    ctx.shadowBlur = 4;
    ctx.strokeStyle = "rgba(245,248,250,0.92)";
  }
  ctx.fillStyle = faceGradient;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.lineWidth = 2;
  ctx.stroke();
  drawPowerGlyph(ctx, layout.faceRect.x + (layout.faceRect.w * 0.5), layout.faceRect.y + 25);

  ctx.fillStyle = state.enabled ? theme.label : "rgba(229, 234, 241, 0.94)";
  ctx.font = "900 11px sans-serif";
  ctx.fillText(state.enabled ? "ON" : "OFF", layout.status.x, layout.status.y);

  ctx.restore();
}

function ensureCanvasHooks(node) {
  if (!node || node.__mkrToggleCanvasHooksInstalled) return;
  node.__mkrToggleCanvasHooksInstalled = true;

  const originalDrawForeground = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    applyNodeChrome(this);
    if (typeof originalDrawForeground === "function") {
      originalDrawForeground.apply(this, arguments);
    }
    if (this.flags?.collapsed || shouldUseDomRenderer(this)) return;
    drawCanvasFallback(this, ctx);
  };

  const originalMouseDown = node.onMouseDown;
  node.onMouseDown = function onMouseDown(event, pos) {
    const originalResult = originalMouseDown?.apply(this, arguments);
    if (originalResult || this.flags?.collapsed || shouldUseDomRenderer(this)) {
      return originalResult;
    }

    const point = getLocalPoint(this, event, pos);
    const layout = getCanvasLayout();

    if (pointInRect(point, layout.badge) || event?.altKey || event?.detail >= 2) {
      cycleTheme(this);
      return true;
    }

    if (!pointInRect(point, layout.switchRect)) {
      return false;
    }
    if (hasLinkedInput(this)) {
      return true;
    }
    const state = getNodeState(this);
    setNodeEnabled(this, !state.enabled);
    return true;
  };
}

function installMenu(node) {
  if (!node || node.__mkrToggleMenuInstalled) return;
  node.__mkrToggleMenuInstalled = true;

  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function getExtraMenuOptions(_, options) {
    const items = Array.isArray(options) ? options : [];
    items.unshift(
      {
        content: "Cycle Theme",
        callback: () => cycleTheme(this),
      },
      {
        content: getNodeState(this).enabled ? "Set Off" : "Set On",
        disabled: hasLinkedInput(this),
        callback: () => {
          if (hasLinkedInput(this)) return;
          const state = getNodeState(this);
          setNodeEnabled(this, !state.enabled);
        },
      },
    );
    return originalMenu?.apply(this, arguments);
  };
}

function syncPresentation(node) {
  syncPanel(node);
  scheduleHostChromeSync(node);
  node?.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
}

function attachToggleNode(node) {
  if (!node || node.__mkrToggleAttached) return;
  node.__mkrToggleAttached = true;

  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: DEFAULTS,
    booleanKeys: ["enabled"],
  });
  hideWidgets(node, [SETTINGS_WIDGET_NAME]);
  installConnectionOverride(node);
  ensureCanvasHooks(node);
  if (shouldUseDomRenderer(node)) {
    ensurePanelWidget(node);
    installHostChromeLoop(node);
  }
  installMenu(node);
  applyNodeChrome(node);
  syncPresentation(node);

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure() {
    const result = originalConfigure?.apply(this, arguments);
    installBundledSettingsAdapter(this, {
      widgetName: SETTINGS_WIDGET_NAME,
      defaults: DEFAULTS,
      booleanKeys: ["enabled"],
    });
    hideWidgets(this, [SETTINGS_WIDGET_NAME]);
    installConnectionOverride(this);
    if (shouldUseDomRenderer(this)) {
      ensurePanelWidget(this);
      installHostChromeLoop(this);
    }
    this.__mkrToggleRuntime = null;
    applyNodeChrome(this);
    syncPresentation(this);
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResize() {
    const result = originalResize?.apply(this, arguments);
    applyNodeChrome(this);
    syncPresentation(this);
    return result;
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    const result = originalConnectionsChange?.apply(this, arguments);
    if (!hasLinkedInput(this)) {
      this.__mkrToggleRuntime = null;
    }
    syncPresentation(this);
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    const result = originalExecuted?.apply(this, arguments);
    const toggleState = message?.ui?.toggle_state?.[0] ?? message?.toggle_state?.[0] ?? null;
    if (toggleState && typeof toggleState === "object") {
      this.__mkrToggleRuntime = {
        enabled: !!toggleState.enabled,
        theme: normalizeTheme(toggleState.theme),
      };
    } else {
      this.__mkrToggleRuntime = null;
    }
    syncPresentation(this);
    return result;
  };

  const originalRemoved = node.onRemoved;
  node.onRemoved = function onRemoved() {
    if (this.__mkrToggleChromeLoopId) {
      window.clearInterval(this.__mkrToggleChromeLoopId);
      this.__mkrToggleChromeLoopId = null;
    }
    return originalRemoved?.apply(this, arguments);
  };
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!isToggleNodeDef(nodeData)) return;
    const litegraph = getLiteGraphGlobal();
    if (litegraph?.NO_TITLE !== undefined) {
      nodeType.title_mode = litegraph.NO_TITLE;
    }
    nodeType.collapsable = false;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = originalOnNodeCreated?.apply(this, arguments);
      attachToggleNode(this);
      return result;
    };
  },
  async nodeCreated(node) {
    if (!isToggleNode(node)) return;
    attachToggleNode(node);
  },
});
