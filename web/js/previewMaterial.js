import { app } from "../../../scripts/app.js";
import { ComponentWidgetImpl, addWidget } from "../../../scripts/domWidget.js";
import { extractModelFileCandidate } from "./load3dModelFileUtils.js";
import { ensureMkrUIStyles } from "./uiSystem.js";
import { hardHideWidget } from "./colorStudioShared.js";

const EXT = "mkr.preview_material";
const NODE_NAME = "x1PreviewMaterial";
const CONTROLS_WIDGET_NAME = "__mkr_preview_material_controls";
const PREVIEW_WIDGET_NAME = "__mkr_native_preview3d";
const DEFAULT_NODE_WIDTH = 520;
const DEFAULT_NODE_HEIGHT = 620;
const HIDDEN_WIDGET_NAMES = [
  "preview_mesh",
  "uv_scale",
  "roughness_default",
  "metalness_default",
  "normal_strength",
  "normal_convention",
  "height_to_normal_strength",
  "emissive_strength",
  "alpha_mode",
  "asset_label",
  "advanced_settings_json",
  "model_file",
];

let load3dComponentPromise = null;

ensureMkrUIStyles();

function getWidget(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
}

function isPreviewMaterialNode(node) {
  const comfyClass = String(node?.comfyClass || node?.constructor?.comfyClass || "");
  const type = String(node?.type || "");
  return comfyClass === NODE_NAME || type === NODE_NAME;
}

async function fetchNative3DAssets() {
  const api = window.comfyAPI?.api || window.api || null;
  if (api?.fetchApi) {
    const response = await api.fetchApi("/mkrshift/native_3d_assets");
    if (!response.ok) {
      throw new Error(`native 3d asset lookup failed (${response.status})`);
    }
    return await response.json();
  }

  const response = await fetch("/mkrshift/native_3d_assets", { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`native 3d asset lookup failed (${response.status})`);
  }
  return await response.json();
}

async function loadNativeLoad3DComponent() {
  if (load3dComponentPromise) {
    return load3dComponentPromise;
  }

  load3dComponentPromise = (async () => {
    const payload = await fetchNative3DAssets();
    const assetPath = String(payload?.load3d_component_asset || "");
    if (!assetPath) {
      throw new Error(payload?.error || "Load3D asset path was empty");
    }

    const module = await import(/* @vite-ignore */ assetPath);
    return module?.default || module?.Load3D || module?.t || Object.values(module || {})[0] || null;
  })();

  return load3dComponentPromise;
}

function ensureNodeShape(node) {
  if (!node) return;
  const width = Math.max(DEFAULT_NODE_WIDTH, Math.round(Number(node.size?.[0] || 0)));
  const height = Math.max(DEFAULT_NODE_HEIGHT, Math.round(Number(node.size?.[1] || 0)));
  if (Number(node.size?.[0] || 0) === width && Number(node.size?.[1] || 0) === height) return;
  if (node.__mkrPreviewMaterialSizing) return;
  node.__mkrPreviewMaterialSizing = true;
  try {
    node.setSize?.([width, height]);
  } finally {
    node.__mkrPreviewMaterialSizing = false;
  }
}

function syncHiddenWidgets(node) {
  let changed = false;
  for (const name of HIDDEN_WIDGET_NAMES) {
    changed = hardHideWidget(getWidget(node, name)) || changed;
  }
  if (changed) {
    node.setDirtyCanvas?.(true, true);
  }
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

function setWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return;
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app?.graph, node, widget);
  }
  node.setDirtyCanvas?.(true, true);
}

function createLabel(text) {
  const label = document.createElement("div");
  label.style.cssText = "font:600 11px sans-serif;color:rgba(229,235,242,0.82);";
  label.textContent = text;
  return label;
}

function createSelectControl({ label, options, value, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:92px 1fr;gap:8px;align-items:center;";
  row.appendChild(createLabel(label));
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
  for (const optionValue of options) {
    const option = document.createElement("option");
    option.value = String(optionValue);
    option.textContent = String(optionValue);
    select.appendChild(option);
  }
  select.value = String(value);
  select.addEventListener("change", () => onChange?.(select.value));
  row.appendChild(select);
  return {
    element: row,
    setValue(next) {
      select.value = String(next);
    },
  };
}

function createRangeControl({ label, min, max, step, value, decimals = 2, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:92px 1fr 64px;gap:8px;align-items:center;";
  row.appendChild(createLabel(label));
  const range = document.createElement("input");
  range.type = "range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);
  range.value = String(value);
  range.style.cssText = "width:100%;accent-color:#6bc4ff;";
  const number = document.createElement("input");
  number.type = "number";
  number.min = String(min);
  number.max = String(max);
  number.step = String(step);
  number.value = Number(value).toFixed(decimals);
  number.style.cssText = [
    "width:64px",
    "border-radius:8px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:rgba(9,10,13,0.48)",
    "color:rgba(245,248,252,0.92)",
    "padding:5px 6px",
    "font:600 11px sans-serif",
    "box-sizing:border-box",
  ].join(";");
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
  };
}

function createTextControl({ label, value, multiline = false, onChange }) {
  const row = document.createElement("div");
  row.style.cssText = "display:grid;grid-template-columns:92px 1fr;gap:8px;align-items:start;";
  row.appendChild(createLabel(label));
  const input = multiline ? document.createElement("textarea") : document.createElement("input");
  if (!multiline) input.type = "text";
  input.value = String(value ?? "");
  input.style.cssText = [
    "width:100%",
    "border-radius:9px",
    "border:1px solid rgba(255,255,255,0.08)",
    "background:rgba(9,10,13,0.48)",
    "color:rgba(245,248,252,0.92)",
    "padding:7px 8px",
    "font:600 11px sans-serif",
    "box-sizing:border-box",
    multiline ? "min-height:54px;resize:vertical;" : "",
  ].join("");
  input.addEventListener(multiline ? "change" : "input", () => onChange?.(input.value));
  row.appendChild(input);
  return {
    element: row,
    setValue(next) {
      input.value = String(next ?? "");
    },
  };
}

function ensureControlsWidget(node) {
  if (getWidget(node, CONTROLS_WIDGET_NAME)) return node.__mkrPreviewControls || null;

  const root = document.createElement("div");
  root.className = "mkr-seamless-panel";

  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;gap:8px;";
  root.appendChild(grid);

  const controls = {
    previewMesh: createSelectControl({
      label: "Mesh",
      options: ["shader_ball", "plane", "cube"],
      value: getWidget(node, "preview_mesh")?.value ?? "shader_ball",
      onChange: (value) => setWidgetValue(node, "preview_mesh", value),
    }),
    uvScale: createRangeControl({
      label: "UV Scale",
      min: 0.01, max: 32, step: 0.01, value: getWidget(node, "uv_scale")?.value ?? 1,
      onChange: (value) => setWidgetValue(node, "uv_scale", value),
    }),
    roughness: createRangeControl({
      label: "Roughness",
      min: 0, max: 1, step: 0.01, value: getWidget(node, "roughness_default")?.value ?? 0.55,
      onChange: (value) => setWidgetValue(node, "roughness_default", value),
    }),
    metalness: createRangeControl({
      label: "Metalness",
      min: 0, max: 1, step: 0.01, value: getWidget(node, "metalness_default")?.value ?? 0,
      onChange: (value) => setWidgetValue(node, "metalness_default", value),
    }),
    normalStrength: createRangeControl({
      label: "Normal",
      min: 0, max: 8, step: 0.01, value: getWidget(node, "normal_strength")?.value ?? 1,
      onChange: (value) => setWidgetValue(node, "normal_strength", value),
    }),
    normalConvention: createSelectControl({
      label: "Normal Map",
      options: ["directx", "opengl"],
      value: getWidget(node, "normal_convention")?.value ?? "directx",
      onChange: (value) => setWidgetValue(node, "normal_convention", value),
    }),
    heightToNormal: createRangeControl({
      label: "Height->N",
      min: 0, max: 64, step: 0.1, value: getWidget(node, "height_to_normal_strength")?.value ?? 6,
      decimals: 1,
      onChange: (value) => setWidgetValue(node, "height_to_normal_strength", value),
    }),
    emissive: createRangeControl({
      label: "Emissive",
      min: 0, max: 8, step: 0.01, value: getWidget(node, "emissive_strength")?.value ?? 1,
      onChange: (value) => setWidgetValue(node, "emissive_strength", value),
    }),
    alphaMode: createSelectControl({
      label: "Alpha",
      options: ["auto", "blend", "mask"],
      value: getWidget(node, "alpha_mode")?.value ?? "auto",
      onChange: (value) => setWidgetValue(node, "alpha_mode", value),
    }),
    assetLabel: createTextControl({
      label: "Label",
      value: getWidget(node, "asset_label")?.value ?? "material_preview",
      onChange: (value) => setWidgetValue(node, "asset_label", value),
    }),
    advanced: createTextControl({
      label: "Advanced",
      value: getWidget(node, "advanced_settings_json")?.value ?? "",
      multiline: true,
      onChange: (value) => setWidgetValue(node, "advanced_settings_json", value),
    }),
  };

  for (const control of Object.values(controls)) {
    grid.appendChild(control.element);
  }

  const widget = node.addDOMWidget?.(CONTROLS_WIDGET_NAME, "DOM", root, {
    serialize: false,
    hideOnZoom: false,
    margin: 0,
    getMinHeight: () => 330,
    getMaxHeight: () => 420,
  });
  if (widget) widget.serialize = false;

  node.__mkrPreviewControls = controls;
  return controls;
}

function syncControls(node) {
  const controls = node.__mkrPreviewControls;
  if (!controls) return;
  controls.previewMesh.setValue(getWidget(node, "preview_mesh")?.value ?? "shader_ball");
  controls.uvScale.setValue(getWidget(node, "uv_scale")?.value ?? 1);
  controls.roughness.setValue(getWidget(node, "roughness_default")?.value ?? 0.55);
  controls.metalness.setValue(getWidget(node, "metalness_default")?.value ?? 0);
  controls.normalStrength.setValue(getWidget(node, "normal_strength")?.value ?? 1);
  controls.normalConvention.setValue(getWidget(node, "normal_convention")?.value ?? "directx");
  controls.heightToNormal.setValue(getWidget(node, "height_to_normal_strength")?.value ?? 6);
  controls.emissive.setValue(getWidget(node, "emissive_strength")?.value ?? 1);
  controls.alphaMode.setValue(getWidget(node, "alpha_mode")?.value ?? "auto");
  controls.assetLabel.setValue(getWidget(node, "asset_label")?.value ?? "material_preview");
  controls.advanced.setValue(getWidget(node, "advanced_settings_json")?.value ?? "");
}

function syncModelFileFromExecution(node, message) {
  if (!node || !message || typeof message !== "object") return;
  const candidate = extractModelFileCandidate(message);
  if (typeof candidate !== "string" || !candidate.trim()) return;
  const widget = getWidget(node, "model_file");
  if (widget && widget.value !== candidate) {
    widget.value = candidate;
    node.setDirtyCanvas?.(true, true);
  }
  node.__mkrLastModelFile = candidate;
  node.__mkrModelFileFolderType = "output";
}

async function attachNativeViewer(node) {
  if (!node || !isPreviewMaterialNode(node)) return;
  if (getWidget(node, PREVIEW_WIDGET_NAME)) return;

  ensureNodeShape(node);
  syncHiddenWidgets(node);

  const component = await loadNativeLoad3DComponent();
  if (!component) {
    throw new Error("Load3D component export was not found");
  }

  const widget = new ComponentWidgetImpl({
    node,
    name: PREVIEW_WIDGET_NAME,
    component,
    inputSpec: {
      name: PREVIEW_WIDGET_NAME,
      type: "Preview3D",
      isPreview: true,
    },
    options: {},
  });
  widget.type = "load3D";
  addWidget(node, widget);
  node.setDirtyCanvas?.(true, true);
}

function patchNodeExecution(node) {
  if (!node || node.__mkrPreviewMaterialPatched) return;
  node.__mkrPreviewMaterialPatched = true;

  const originalOnExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    originalOnExecuted?.call(this, message);
    syncModelFileFromExecution(this, message);
    removeGeneratedInputs(this, HIDDEN_WIDGET_NAMES);
    syncControls(this);
  };

  const originalOnConfigure = node.onConfigure;
  node.onConfigure = function onConfigurePreviewMaterial() {
    const result = originalOnConfigure?.apply(this, arguments);
    ensureNodeShape(this);
    syncHiddenWidgets(this);
    removeGeneratedInputs(this, HIDDEN_WIDGET_NAMES);
    syncControls(this);
    return result;
  };

  const originalOnResize = node.onResize;
  node.onResize = function onResizePreviewMaterial() {
    const result = originalOnResize?.apply(this, arguments);
    syncHiddenWidgets(this);
    removeGeneratedInputs(this, HIDDEN_WIDGET_NAMES);
    syncControls(this);
    return result;
  };
}

async function prepareNode(node) {
  if (!node || !isPreviewMaterialNode(node)) return;
  patchNodeExecution(node);
  syncHiddenWidgets(node);
  removeGeneratedInputs(node, HIDDEN_WIDGET_NAMES);
  ensureControlsWidget(node);
  syncControls(node);
  try {
    await attachNativeViewer(node);
  } catch (error) {
    console.error("[MKRShift] Failed to attach native 3D preview", error);
  }
}

app.registerExtension({
  name: EXT,
  async nodeCreated(node) {
    await prepareNode(node);
  },
  async afterConfigureGraph() {
    const graph = app.graph;
    const nodes = graph?._nodes || [];
    for (const node of nodes) {
      if (isPreviewMaterialNode(node)) {
        await prepareNode(node);
      }
    }
  },
});
