import { app } from "../../../scripts/app.js";
import { ComponentWidgetImpl, addWidget } from "../../../scripts/domWidget.js";
import { extractModelFileCandidate } from "./load3dModelFileUtils.js";

const EXT = "mkr.preview_material";
const NODE_NAME = "x1PreviewMaterial";
const PREVIEW_WIDGET_NAME = "__mkr_native_preview3d";
const DEFAULT_NODE_WIDTH = 420;
const DEFAULT_NODE_HEIGHT = 560;

let load3dComponentPromise = null;

function getWidget(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
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
  node.setSize?.([width, height]);
}

function syncHiddenWidgets(node) {
  let changed = false;
  changed = hardHideWidget(getWidget(node, "model_file")) || changed;
  if (changed) {
    node.setDirtyCanvas?.(true, true);
  }
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
  };
}

async function prepareNode(node) {
  if (!node || !isPreviewMaterialNode(node)) return;
  patchNodeExecution(node);
  syncHiddenWidgets(node);
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
