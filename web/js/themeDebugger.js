import { app } from "../../../scripts/app.js";

const EXT = "mkr.theme_debugger";

const TRACKED_KEYS = [
  "theme_name",
  "mkr_ink",
  "mkr_card",
  "mkr_card_alt",
  "mkr_accent_a",
  "mkr_accent_b",
  "mkr_accent_c",
  "mkr_muted",
  "mkr_line",
  "mkr_shadow_color",
  "panel_gradient_start",
  "panel_gradient_end",
  "font_family",
  "panel_radius",
  "section_radius",
  "input_radius",
  "panel_padding",
  "section_padding",
  "control_gap",
  "viewport_height",
  "shadow_blur",
  "animation_ms",
  "button_style",
  "density",
  "notes",
];

function isThemeDebugger(node) {
  return node?.comfyClass === "MKRThemeDebugger";
}

function getWidget(node, name) {
  return node.widgets?.find((w) => w.name === name);
}

function asInt(value, fallback) {
  const n = Number.parseInt(String(value), 10);
  return Number.isFinite(n) ? n : fallback;
}

function gatherValues(node) {
  const values = {};
  for (const key of TRACKED_KEYS) {
    values[key] = getWidget(node, key)?.value ?? "";
  }
  return values;
}

function buildPayload(node) {
  const values = gatherValues(node);

  const densityScale = {
    compact: 0.88,
    comfortable: 1.0,
    spacious: 1.12,
  }[String(values.density)] ?? 1.0;

  const shadowBlur = Math.max(0, asInt(values.shadow_blur, 30));
  const panelRadius = Math.max(0, asInt(values.panel_radius, 18));
  const sectionRadius = Math.max(0, asInt(values.section_radius, 13));
  const inputRadius = Math.max(0, asInt(values.input_radius, 9));
  const panelPadding = Math.max(2, asInt(values.panel_padding, 12));
  const sectionPadding = Math.max(2, asInt(values.section_padding, 10));
  const controlGap = Math.max(2, asInt(values.control_gap, 8));
  const viewportHeight = Math.max(80, asInt(values.viewport_height, 260));
  const animationMs = Math.max(0, asInt(values.animation_ms, 260));

  const cssVars = {
    "--mkr-ink": String(values.mkr_ink),
    "--mkr-card": String(values.mkr_card),
    "--mkr-card-alt": String(values.mkr_card_alt),
    "--mkr-accent-a": String(values.mkr_accent_a),
    "--mkr-accent-b": String(values.mkr_accent_b),
    "--mkr-accent-c": String(values.mkr_accent_c),
    "--mkr-muted": String(values.mkr_muted),
    "--mkr-line": String(values.mkr_line),
    "--mkr-panel-gradient-start": String(values.panel_gradient_start),
    "--mkr-panel-gradient-end": String(values.panel_gradient_end),
    "--mkr-font-family": String(values.font_family),
    "--mkr-panel-radius": `${panelRadius}px`,
    "--mkr-section-radius": `${sectionRadius}px`,
    "--mkr-input-radius": `${inputRadius}px`,
    "--mkr-panel-padding": `${panelPadding}px`,
    "--mkr-section-padding": `${sectionPadding}px`,
    "--mkr-control-gap": `${controlGap}px`,
    "--mkr-viewport-height": `${viewportHeight}px`,
    "--mkr-font-scale": densityScale.toFixed(3),
    "--mkr-animation-ms": `${animationMs}ms`,
    "--mkr-shadow": `0 ${Math.max(0, Math.round(shadowBlur * 0.45))}px ${shadowBlur}px ${values.mkr_shadow_color}`,
    "--mkr-button-style": String(values.button_style),
  };

  const payload = {
    schema: "mkr_theme_debug_v1",
    theme_name: String(values.theme_name || "mkr_theme_v1"),
    button_style: String(values.button_style || "soft"),
    density: String(values.density || "comfortable"),
    notes: String(values.notes || ""),
    tokens: cssVars,
  };

  const jsonText = JSON.stringify(payload, null, 2);
  const cssText = `:root {\n${Object.entries(cssVars)
    .map(([k, v]) => `  ${k}: ${v};`)
    .join("\n")}\n}`;

  return `${jsonText}\n\n/* CSS Variables */\n${cssText}`;
}

function updatePanel(node, state) {
  const text = buildPayload(node);
  if (text === state.lastText) return;
  state.lastText = text;
  state.textarea.value = text;
  node.properties = node.properties || {};
  node.properties.theme_debug_text = text;
  node.setDirtyCanvas?.(true, true);
}

function wrapWidgetCallbacks(node, state) {
  for (const widget of node.widgets || []) {
    if (widget.__mkrThemeWrapped) continue;
    const original = widget.callback;
    widget.callback = function wrappedCallback() {
      if (typeof original === "function") {
        original.apply(this, arguments);
      }
      updatePanel(node, state);
    };
    widget.__mkrThemeWrapped = true;
  }
}

function attachLivePanel(node) {
  if (node.__mkrThemeDebuggerState) return;

  const wrap = document.createElement("div");
  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";
  wrap.style.gap = "8px";
  wrap.style.padding = "8px";
  wrap.style.width = "100%";
  wrap.style.maxWidth = "560px";

  const title = document.createElement("div");
  title.textContent = "Theme Payload (Live)";
  title.style.fontWeight = "700";
  title.style.fontSize = "12px";
  title.style.opacity = "0.92";
  wrap.appendChild(title);

  const hint = document.createElement("div");
  hint.textContent = "Adjust widgets and copy this payload for styling requests.";
  hint.style.fontSize = "11px";
  hint.style.opacity = "0.72";
  wrap.appendChild(hint);

  const textarea = document.createElement("textarea");
  textarea.readOnly = true;
  textarea.spellcheck = false;
  textarea.style.width = "100%";
  textarea.style.minHeight = "260px";
  textarea.style.resize = "vertical";
  textarea.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, monospace";
  textarea.style.fontSize = "11px";
  textarea.style.lineHeight = "1.35";
  textarea.style.padding = "8px";
  wrap.appendChild(textarea);

  const buttons = document.createElement("div");
  buttons.style.display = "flex";
  buttons.style.gap = "6px";

  const copyButton = document.createElement("button");
  copyButton.textContent = "Copy Payload";
  copyButton.onclick = async () => {
    try {
      await navigator.clipboard.writeText(textarea.value || "");
      copyButton.textContent = "Copied";
      setTimeout(() => {
        copyButton.textContent = "Copy Payload";
      }, 900);
    } catch {
      copyButton.textContent = "Copy Failed";
      setTimeout(() => {
        copyButton.textContent = "Copy Payload";
      }, 900);
    }
  };
  buttons.appendChild(copyButton);

  const selectButton = document.createElement("button");
  selectButton.textContent = "Select All";
  selectButton.onclick = () => {
    textarea.focus();
    textarea.select();
  };
  buttons.appendChild(selectButton);

  wrap.appendChild(buttons);

  if (node.addDOMWidget) {
    node.addDOMWidget("mkr_theme_debug_panel", "DOM", wrap);
  } else {
    node.addCustomWidget({
      name: "mkr_theme_debug_panel",
      type: "dom",
      draw: function () {},
      getHeight: function () {
        return 360;
      },
      getWidth: function () {
        return 580;
      },
      element: wrap,
    });
  }

  const state = {
    textarea,
    lastText: "",
    intervalId: null,
  };
  node.__mkrThemeDebuggerState = state;

  wrapWidgetCallbacks(node, state);
  updatePanel(node, state);

  state.intervalId = setInterval(() => {
    updatePanel(node, state);
  }, 220);

  const originalRemoved = node.onRemoved;
  node.onRemoved = function onRemoved() {
    if (state.intervalId) {
      clearInterval(state.intervalId);
      state.intervalId = null;
    }
    if (typeof originalRemoved === "function") {
      return originalRemoved.apply(this, arguments);
    }
    return undefined;
  };

  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: EXT,
  async nodeCreated(node) {
    if (!isThemeDebugger(node)) return;
    attachLivePanel(node);
  },
});
