import { app } from "../../../scripts/app.js";
import { createPanelShell } from "./uiSystem.js";
import {
  attachPanel,
  createGradeButton,
  createGradeMetric,
  createGradeReadout,
  createGradeSection,
  createGradeSlider,
  createGradeToggle,
  ensureCanvasResolution,
  ensureColorGradeStyles,
  formatNumber,
  formatSigned,
  getBoolean,
  getNumber,
  installBundledSettingsAdapter,
  matchesNode,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.ColorCurvesStudio";
const NODE_NAME = "x1Curves";
const PANEL_NAME = "mkr_color_curves_studio";
const SETTINGS_WIDGET_NAME = "settings_json";
const LEGACY_WIDGETS = [
  "master_shadows",
  "master_midtones",
  "master_highlights",
  "red_curve",
  "green_curve",
  "blue_curve",
  "contrast",
  "mix",
  "mask_feather",
  "invert_mask",
];
const HIDDEN_WIDGETS = [SETTINGS_WIDGET_NAME, ...LEGACY_WIDGETS];

const DEFAULT_SETTINGS = {
  master_shadows: 0.0,
  master_midtones: 0.0,
  master_highlights: 0.0,
  red_curve: 0.0,
  green_curve: 0.0,
  blue_curve: 0.0,
  contrast: 1.0,
  mix: 1.0,
  mask_feather: 12.0,
  invert_mask: false,
};

const NUMERIC_SPECS = {
  master_shadows: { min: -1.0, max: 1.0 },
  master_midtones: { min: -1.0, max: 1.0 },
  master_highlights: { min: -1.0, max: 1.0 },
  red_curve: { min: -1.0, max: 1.0 },
  green_curve: { min: -1.0, max: 1.0 },
  blue_curve: { min: -1.0, max: 1.0 },
  contrast: { min: 0.3, max: 2.5 },
  mix: { min: 0.0, max: 1.0 },
  mask_feather: { min: 0.0, max: 256.0 },
};

const BOOLEAN_KEYS = ["invert_mask"];

const MASTER_KEYS = [
  { key: "master_shadows", x: 0.18, color: "#f0f4f7", label: "Shadows" },
  { key: "master_midtones", x: 0.50, color: "#f0f4f7", label: "Midtones" },
  { key: "master_highlights", x: 0.82, color: "#f0f4f7", label: "Highlights" },
];

const CHANNEL_KEYS = [
  { key: "red_curve", x: 0.22, color: "#ff5b52", label: "Red" },
  { key: "green_curve", x: 0.50, color: "#39c66d", label: "Green" },
  { key: "blue_curve", x: 0.78, color: "#4c8dff", label: "Blue" },
];

const PRESETS = {
  neutral: {
    master_shadows: 0.0,
    master_midtones: 0.0,
    master_highlights: 0.0,
    red_curve: 0.0,
    green_curve: 0.0,
    blue_curve: 0.0,
    contrast: 1.0,
    mix: 1.0,
  },
  filmic: {
    master_shadows: 0.18,
    master_midtones: 0.02,
    master_highlights: -0.08,
    red_curve: 0.08,
    green_curve: 0.0,
    blue_curve: -0.07,
    contrast: 1.08,
    mix: 1.0,
  },
  snap: {
    master_shadows: -0.10,
    master_midtones: 0.14,
    master_highlights: 0.18,
    red_curve: 0.04,
    green_curve: 0.02,
    blue_curve: -0.03,
    contrast: 1.22,
    mix: 1.0,
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function valueToY(value, top, height) {
  const t = (clamp(value, -1, 1) + 1) * 0.5;
  return top + ((1 - t) * height);
}

function yToValue(y, top, height) {
  const t = 1 - ((y - top) / Math.max(1, height));
  return clamp((t * 2) - 1, -1, 1);
}

function curveBasis(x) {
  return {
    shadows: Math.pow(1 - x, 2),
    mids: 4 * x * (1 - x),
    highs: Math.pow(x, 2),
  };
}

function applyCurveTriplet(x, shadows, mids, highs, amount = 0.5) {
  const basis = curveBasis(x);
  return clamp(x + (amount * ((shadows * basis.shadows) + (mids * basis.mids) + (highs * basis.highs))), 0, 1);
}

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values)) {
    setWidgetValue(node, key, value);
  }
}

function installRefreshHooks(node, key, refresh) {
  if (!node || node[key]) return;
  node[key] = true;

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigureRefreshPanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeRefreshPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedRefreshPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawChannelCurve(ctx, graph, color, channelAmount) {
  ctx.beginPath();
  for (let step = 0; step <= 96; step += 1) {
    const t = step / 96;
    const y = applyCurveTriplet(t, channelAmount, channelAmount * 0.25, -channelAmount, 0.30);
    const px = graph.x + (t * graph.w);
    const py = graph.y + ((1 - y) * graph.h);
    if (step === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();
}

function buildCurvePanel(node) {
  ensureColorGradeStyles();

  const { panel } = createPanelShell({
    kicker: "MKR SHIFT COLOR",
    title: "Curves Studio",
    subtitle: "Shape the master curve first, then trim RGB response with lighter inline controls.",
    showHeader: false,
  });

  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", "#4c8dff");

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metrics = document.createElement("div");
  metrics.className = "mkr-grade-metrics";
  const contrastMetric = createGradeMetric("Contrast", "1.00");
  const biasMetric = createGradeMetric("Curve Bias", "0.00");
  const mixMetric = createGradeMetric("Mix", "1.00");
  metrics.appendChild(contrastMetric.element);
  metrics.appendChild(biasMetric.element);
  metrics.appendChild(mixMetric.element);

  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  actions.appendChild(createGradeButton("Neutral", () => { applyValues(node, PRESETS.neutral); refresh(); }));
  actions.appendChild(createGradeButton("Filmic", () => { applyValues(node, PRESETS.filmic); refresh(); }, "accent"));
  actions.appendChild(createGradeButton("Snap", () => { applyValues(node, PRESETS.snap); refresh(); }));
  topbar.appendChild(metrics);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const curveSection = createGradeSection("Curve Surface", "drag handles");
  const canvas = document.createElement("canvas");
  canvas.className = "mkr-grade-canvas";
  canvas.style.height = "294px";
  curveSection.body.appendChild(canvas);

  const readouts = document.createElement("div");
  readouts.className = "mkr-grade-inline";
  const shadowReadout = createGradeReadout("Sh", "0.00");
  const midReadout = createGradeReadout("Mid", "0.00");
  const highReadout = createGradeReadout("Hi", "0.00");
  readouts.appendChild(shadowReadout.element);
  readouts.appendChild(midReadout.element);
  readouts.appendChild(highReadout.element);
  curveSection.body.appendChild(readouts);

  const note = document.createElement("div");
  note.className = "mkr-grade-note";
  note.textContent = "White handles shape the master response. Colored handles in the lower strip trim red, green, and blue without turning the node into a giant inspector.";
  curveSection.body.appendChild(note);
  panel.appendChild(curveSection.section);

  let activeHandle = null;

  const updateSummary = () => {
    const ms = getNumber(node, "master_shadows", 0);
    const mm = getNumber(node, "master_midtones", 0);
    const mh = getNumber(node, "master_highlights", 0);
    contrastMetric.setValue(formatNumber(getNumber(node, "contrast", 1)));
    biasMetric.setValue(formatSigned((ms + mm + mh) / 3));
    mixMetric.setValue(formatNumber(getNumber(node, "mix", 1)));
    shadowReadout.setValue(formatSigned(ms));
    midReadout.setValue(formatSigned(mm));
    highReadout.setValue(formatSigned(mh));
  };

  const draw = () => {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    ctx.clearRect(0, 0, width, height);

    const graph = { x: 20, y: 16, w: width - 40, h: Math.max(140, height - 82) };
    const band = { x: graph.x, y: graph.y + graph.h + 12, w: graph.w, h: 36 };

    const bg = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y + graph.h);
    bg.addColorStop(0, "rgba(18, 28, 40, 0.94)");
    bg.addColorStop(1, "rgba(35, 48, 63, 0.94)");
    ctx.fillStyle = bg;
    ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

    ctx.fillStyle = "rgba(245, 249, 252, 0.08)";
    ctx.fillRect(band.x, band.y, band.w, band.h);

    ctx.strokeStyle = "rgba(194, 207, 220, 0.12)";
    ctx.lineWidth = 1;
    for (let index = 0; index <= 10; index += 1) {
      const gx = graph.x + (graph.w * index / 10);
      const gy = graph.y + (graph.h * index / 10);
      ctx.beginPath();
      ctx.moveTo(gx, graph.y);
      ctx.lineTo(gx, graph.y + graph.h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(graph.x, gy);
      ctx.lineTo(graph.x + graph.w, gy);
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.moveTo(graph.x, graph.y + graph.h);
    ctx.lineTo(graph.x + graph.w, graph.y);
    ctx.strokeStyle = "rgba(228, 236, 244, 0.42)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    const ms = getNumber(node, "master_shadows", 0);
    const mm = getNumber(node, "master_midtones", 0);
    const mh = getNumber(node, "master_highlights", 0);
    const rc = getNumber(node, "red_curve", 0);
    const gc = getNumber(node, "green_curve", 0);
    const bc = getNumber(node, "blue_curve", 0);

    drawChannelCurve(ctx, graph, "rgba(255, 91, 82, 0.92)", rc);
    drawChannelCurve(ctx, graph, "rgba(57, 198, 109, 0.92)", gc);
    drawChannelCurve(ctx, graph, "rgba(76, 141, 255, 0.92)", bc);

    ctx.beginPath();
    for (let step = 0; step <= 120; step += 1) {
      const t = step / 120;
      const y = applyCurveTriplet(t, ms, mm, mh, 0.45);
      const px = graph.x + (t * graph.w);
      const py = graph.y + ((1 - y) * graph.h);
      if (step === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = "rgba(245, 249, 252, 0.98)";
    ctx.lineWidth = 2.2;
    ctx.stroke();

    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (const item of MASTER_KEYS) {
      const x = graph.x + (graph.w * item.x);
      const y = valueToY(getNumber(node, item.key, 0), graph.y, graph.h);
      ctx.fillStyle = item.color;
      ctx.beginPath();
      ctx.arc(x, y, 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(17, 21, 28, 0.92)";
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.fillStyle = "rgba(232, 239, 245, 0.78)";
      ctx.fillText(item.label, x, graph.y + graph.h + 14);
    }

    for (const item of CHANNEL_KEYS) {
      const x = band.x + (band.w * item.x);
      const y = valueToY(getNumber(node, item.key, 0), band.y, band.h);
      ctx.fillStyle = item.color;
      ctx.beginPath();
      ctx.arc(x, y, 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(17, 21, 28, 0.88)";
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.fillStyle = item.color;
      ctx.fillText(item.label, x, band.y - 10);
    }
  };

  const resolveHandle = (event) => {
    const rect = canvas.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const graph = { x: 20, y: 16, w: rect.width - 40, h: Math.max(140, rect.height - 82) };
    const band = { x: graph.x, y: graph.y + graph.h + 12, w: graph.w, h: 36 };

    for (const item of MASTER_KEYS) {
      const x = graph.x + (graph.w * item.x);
      const y = valueToY(getNumber(node, item.key, 0), graph.y, graph.h);
      if (Math.hypot(pointerX - x, pointerY - y) <= 12) {
        return { key: item.key, area: graph };
      }
    }

    for (const item of CHANNEL_KEYS) {
      const x = band.x + (band.w * item.x);
      const y = valueToY(getNumber(node, item.key, 0), band.y, band.h);
      if (Math.hypot(pointerX - x, pointerY - y) <= 12) {
        return { key: item.key, area: band };
      }
    }
    return null;
  };

  const updateHandle = (event) => {
    if (!activeHandle) return;
    const rect = canvas.getBoundingClientRect();
    const pointerY = event.clientY - rect.top;
    const value = Number(yToValue(pointerY, activeHandle.area.y, activeHandle.area.h).toFixed(4));
    setWidgetValue(node, activeHandle.key, value);
    updateSummary();
    draw();
  };

  canvas.addEventListener("pointerdown", (event) => {
    activeHandle = resolveHandle(event);
    if (!activeHandle) return;
    canvas.setPointerCapture?.(event.pointerId);
    updateHandle(event);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!activeHandle) return;
    updateHandle(event);
  });
  const stopDrag = (event) => {
    if (!activeHandle) return;
    activeHandle = null;
    canvas.releasePointerCapture?.(event.pointerId);
  };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
  }

  const responseSection = createGradeSection("Response", "primary");
  const responseControls = document.createElement("div");
  responseControls.className = "mkr-grade-controls";
  const contrastControl = createGradeSlider({
    label: "Contrast",
    min: 0.3,
    max: 2.5,
    step: 0.01,
    value: getNumber(node, "contrast", 1),
    decimals: 2,
    onChange: (value) => {
      setWidgetValue(node, "contrast", value);
      updateSummary();
    },
  });
  const mixControl = createGradeSlider({
    label: "Mix",
    min: 0,
    max: 1,
    step: 0.01,
    value: getNumber(node, "mix", 1),
    decimals: 2,
    onChange: (value) => {
      setWidgetValue(node, "mix", value);
      updateSummary();
    },
  });
  const featherControl = createGradeSlider({
    label: "Mask Feather",
    min: 0,
    max: 256,
    step: 0.5,
    value: getNumber(node, "mask_feather", 12),
    decimals: 1,
    onChange: (value) => {
      setWidgetValue(node, "mask_feather", value);
    },
  });
  const invertControl = createGradeToggle({
    label: "Invert Mask",
    checked: getBoolean(node, "invert_mask", false),
    description: "Flip the external mask before applying the curve.",
    onChange: (value) => {
      setWidgetValue(node, "invert_mask", value);
    },
  });
  responseControls.appendChild(contrastControl.element);
  responseControls.appendChild(mixControl.element);
  responseControls.appendChild(featherControl.element);
  responseControls.appendChild(invertControl.element);
  responseSection.body.appendChild(responseControls);
  panel.appendChild(responseSection.section);

  const refresh = () => {
    updateSummary();
    draw();
    contrastControl.setValue(getNumber(node, "contrast", 1));
    mixControl.setValue(getNumber(node, "mix", 1));
    featherControl.setValue(getNumber(node, "mask_feather", 12));
    invertControl.setValue(getBoolean(node, "invert_mask", false));
  };

  updateSummary();
  draw();
  return { panel, refresh };
}

function installCurveStudio(node) {
  if (!matchesNode(node, NODE_NAME)) return;
  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: DEFAULT_SETTINGS,
    numericSpecs: NUMERIC_SPECS,
    booleanKeys: BOOLEAN_KEYS,
    legacyNames: LEGACY_WIDGETS,
  });
  if (node.__mkrColorCurvesStudioInstalled) {
    node.__mkrColorCurvesRefresh?.();
    normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);
    return;
  }
  node.__mkrColorCurvesStudioInstalled = true;
  const { panel, refresh } = buildCurvePanel(node);
  node.__mkrColorCurvesRefresh = refresh;
  attachPanel(node, PANEL_NAME, panel, 760, 780);
  normalizePanelNode(node, HIDDEN_WIDGETS, PANEL_NAME);
  installRefreshHooks(node, "__mkrColorCurvesRefreshHooksInstalled", refresh);
  requestAnimationFrame(() => refresh());
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_NAME) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = originalOnNodeCreated?.apply(this, arguments);
      installCurveStudio(this);
      return result;
    };
  },
  async nodeCreated(node) {
    installCurveStudio(node);
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      installCurveStudio(node);
    }
  },
});
