import { app } from "../../../scripts/app.js";
import { api as comfyApi } from "../../../scripts/api.js";
import {
  extractModelFileCandidate,
  normalizeModelFile,
  parseModelFileReference,
} from "./load3dModelFileUtils.js";

const EXT = "mkr.preview3d_model_file_bridge";
const PREVIEW3D_NODE_NAME = "Preview3D";
const LOAD3D_NODE_NAME = "Load3D";
const PREVIEW_MATERIAL_NODE_NAME = "x1PreviewMaterial";
const MODEL_FILE_NAME = "model_file";

let native3DAssetsPromise = null;
let useLoad3dModulePromise = null;

function isLoad3DNode(node) {
  const comfyClass = String(node?.comfyClass || node?.constructor?.comfyClass || "");
  const type = String(node?.type || "");
  return (
    comfyClass === PREVIEW3D_NODE_NAME ||
    type === PREVIEW3D_NODE_NAME ||
    comfyClass === LOAD3D_NODE_NAME ||
    type === LOAD3D_NODE_NAME
  );
}

function isPreview3DNode(node) {
  const comfyClass = String(node?.comfyClass || node?.constructor?.comfyClass || "");
  const type = String(node?.type || "");
  return comfyClass === PREVIEW3D_NODE_NAME || type === PREVIEW3D_NODE_NAME;
}

function getWidget(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
}

function getModelFileInput(node) {
  return node?.inputs?.find((input) => input?.name === MODEL_FILE_NAME) || null;
}

function isMaterialPreviewPath(value) {
  const reference = parseModelFileReference(value);
  if (!reference || reference.isRemote) {
    return false;
  }
  return normalizeModelFile(reference.cleanPath).startsWith("mkrshift/material_preview/");
}

function stripOutputAnnotation(value) {
  return normalizeModelFile(value).replace(/\s*\[output\]\s*$/i, "");
}

function sanitizePreview3DExecutionMessage(message) {
  if (!message || typeof message !== "object" || !Array.isArray(message.result) || message.result.length === 0) {
    return message;
  }

  const rawModelFile = message.result[0];
  if (typeof rawModelFile !== "string" || !/\[output\]\s*$/i.test(rawModelFile)) {
    return message;
  }

  return {
    ...message,
    result: [stripOutputAnnotation(rawModelFile), ...message.result.slice(1)],
  };
}

function getModelUrl(modelFile) {
  const reference = parseModelFileReference(modelFile);
  if (!reference) return null;
  if (reference.isRemote) {
    return reference.cleanPath;
  }
  const params = new URLSearchParams({
    filename: reference.filename,
    type: reference.type || "input",
    subfolder: reference.subfolder,
  });
  const randParam = app?.getRandParam?.();
  const query = randParam ? `${params.toString()}&${String(randParam).replace(/^\?/, "")}` : params.toString();
  return comfyApi.apiURL(`/view?${query}`);
}

function coerceOutputModelUrl(node, modelUrl, filePath) {
  const rawUrl = normalizeModelFile(modelUrl);
  if (!rawUrl) {
    return modelUrl;
  }

  const shouldForceOutput =
    isMaterialPreviewPath(filePath) ||
    isMaterialPreviewPath(node?.__mkrLastLinkedModelFile) ||
    isMaterialPreviewPath(resolveLinkedSourceModelFile(node)) ||
    isMaterialPreviewPath(getWidget(node, MODEL_FILE_NAME)?.value);

  if (!shouldForceOutput) {
    try {
      const parsed = new URL(rawUrl, window.location.origin);
      const subfolder = normalizeModelFile(parsed.searchParams.get("subfolder"));
      if (!subfolder.startsWith("mkrshift/material_preview")) {
        return modelUrl;
      }
      parsed.searchParams.set("type", "output");
      return parsed.toString();
    } catch {
      return modelUrl;
    }
  }

  try {
    const parsed = new URL(rawUrl, window.location.origin);
    parsed.searchParams.set("type", "output");
    return parsed.toString();
  } catch {
    return modelUrl;
  }
}

async function fetchNative3DAssets() {
  if (native3DAssetsPromise) {
    return native3DAssetsPromise;
  }

  native3DAssetsPromise = (async () => {
    const response = await comfyApi.fetchApi("/mkrshift/native_3d_assets");
    if (!response.ok) {
      throw new Error(`native 3d asset lookup failed (${response.status})`);
    }
    return await response.json();
  })();

  return native3DAssetsPromise;
}

async function loadUseLoad3dModule() {
  if (useLoad3dModulePromise) {
    return useLoad3dModulePromise;
  }

  useLoad3dModulePromise = (async () => {
    const payload = await fetchNative3DAssets();
    const assetPath = String(payload?.use_load3d_asset || "");
    if (!assetPath) {
      throw new Error(payload?.error || "useLoad3d asset path was empty");
    }
    return await import(/* @vite-ignore */ assetPath);
  })();

  return useLoad3dModulePromise;
}

async function getLoad3dForNode(node) {
  try {
    const module = await loadUseLoad3dModule();
    const nodeToLoad3dMap = module?.nodeToLoad3dMap || module?.t || null;
    const existing = nodeToLoad3dMap?.get?.(node) || null;
    if (existing) {
      return patchLoad3dInstance(node, existing);
    }

    const useLoad3d = module?.useLoad3d || module?.e || null;
    if (typeof useLoad3d === "function") {
      return await new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          resolve(value || null);
        };

        const timeoutId = window.setTimeout(() => {
          finish(null);
        }, 2000);

        try {
          useLoad3d(node)?.waitForLoad3d?.((load3d) => {
            window.clearTimeout(timeoutId);
            finish(patchLoad3dInstance(node, load3d));
          });
        } catch {
          window.clearTimeout(timeoutId);
          finish(null);
        }
      });
    }

    return null;
  } catch (error) {
    console.error("[MKRShift] Failed to resolve useLoad3d module", error);
    return null;
  }
}

function patchLoad3dInstance(node, load3d) {
  if (!load3d || load3d.__mkrPreview3DLoadPatched) {
    return load3d;
  }

  const originalLoadModel = typeof load3d.loadModel === "function" ? load3d.loadModel.bind(load3d) : null;
  if (!originalLoadModel) {
    return load3d;
  }

  load3d.loadModel = async (modelUrl, filePath) => {
    const coercedUrl = coerceOutputModelUrl(node, modelUrl, filePath);
    return await originalLoadModel(coercedUrl, filePath);
  };
  load3d.__mkrPreview3DLoadPatched = true;
  return load3d;
}

function rememberSourceModelFile(node, modelFile) {
  if (!node) return;
  node.__mkrLastModelFile = modelFile;
  const comfyClass = String(node?.comfyClass || node?.constructor?.comfyClass || node?.type || "");
  if (comfyClass === PREVIEW_MATERIAL_NODE_NAME) {
    node.__mkrModelFileFolderType = "output";
  }
}

function getGraphLink(graph, linkId) {
  return graph?.links?.[linkId] || null;
}

function getLinkedSourceNode(previewNode) {
  const graph = previewNode?.graph || app.graph;
  const linkId = getModelFileInput(previewNode)?.link;
  if (linkId == null) {
    return null;
  }

  const link = getGraphLink(graph, linkId);
  if (link?.origin_id == null) {
    return null;
  }
  return graph?.getNodeById?.(link.origin_id) || app.graph?.getNodeById?.(link.origin_id) || null;
}

function resolveLinkedSourceModelFile(previewNode) {
  const sourceNode = getLinkedSourceNode(previewNode);
  const rememberedValue = normalizeModelFile(sourceNode?.__mkrLastModelFile);
  if (rememberedValue) {
    return rememberedValue;
  }
  const widgetValue = normalizeModelFile(getWidget(sourceNode, MODEL_FILE_NAME)?.value);
  if (widgetValue) {
    return widgetValue;
  }
  return "";
}

function getSourceModelFileFallbackType(sourceNode, modelFile) {
  const explicitType = normalizeModelFile(sourceNode?.__mkrModelFileFolderType).toLowerCase();
  if (explicitType === "output" || explicitType === "input" || explicitType === "temp") {
    return explicitType;
  }

  const comfyClass = String(sourceNode?.comfyClass || sourceNode?.constructor?.comfyClass || sourceNode?.type || "");
  if (comfyClass === PREVIEW_MATERIAL_NODE_NAME) {
    return "output";
  }

  if (normalizeModelFile(modelFile).startsWith("mkrshift/material_preview/")) {
    return "output";
  }

  return "input";
}

function setWidgetValueSilently(widget, value) {
  if (!widget || widget.value === value) {
    return;
  }

  const options = widget.options;
  if (Array.isArray(options?.values) && !options.values.includes(value)) {
    options.values.push(value);
  }

  const originalCallback = widget.callback;
  try {
    // Load3D patches model_file with an input-folder loader. Suppress that callback
    // so linked output paths can be reloaded with the correct folder type below.
    widget.callback = null;
    widget.value = value;
  } finally {
    if (originalCallback === undefined) {
      delete widget.callback;
    } else {
      widget.callback = originalCallback;
    }
  }
}

function sanitizePreview3DStoredModelFile(node) {
  if (!isPreview3DNode(node)) {
    return;
  }

  node.properties ??= {};
  const lastTimeModelFile = normalizeModelFile(node.properties["Last Time Model File"]);
  if (lastTimeModelFile) {
    node.properties["Last Time Model File"] = stripOutputAnnotation(lastTimeModelFile);
  }

  const widget = getWidget(node, MODEL_FILE_NAME);
  if (!widget) {
    return;
  }

  const sanitizedWidgetValue = stripOutputAnnotation(widget.value);
  if (sanitizedWidgetValue) {
    setWidgetValueSilently(widget, sanitizedWidgetValue);
  }
}

function patchPreview3DExecution(node) {
  if (!isPreview3DNode(node) || node.__mkrPreview3DExecutionPatched) return;
  node.__mkrPreview3DExecutionPatched = true;

  const wrapOnExecuted = (handler) => {
    if (typeof handler !== "function") {
      return handler;
    }

    return function wrappedOnExecuted(message, ...rest) {
      return handler.call(this, sanitizePreview3DExecutionMessage(message), ...rest);
    };
  };

  let currentOnExecuted = wrapOnExecuted(node.onExecuted);
  Object.defineProperty(node, "onExecuted", {
    configurable: true,
    enumerable: true,
    get() {
      return currentOnExecuted;
    },
    set(value) {
      currentOnExecuted = wrapOnExecuted(value);
    },
  });
}

async function applyModelFileToPreviewNode(previewNode, modelFile, fallbackType = "input") {
  const reference = parseModelFileReference(modelFile, fallbackType);
  if (!isLoad3DNode(previewNode) || !reference) return;

  const widget = getWidget(previewNode, MODEL_FILE_NAME);
  if (widget) {
    setWidgetValueSilently(widget, reference.widgetValue);
  }
  previewNode.__mkrLastLinkedModelFile = reference.raw;
  previewNode.__mkrModelFileFolderType = reference.type || fallbackType;
  previewNode.properties ??= {};
  if (String(previewNode?.constructor?.comfyClass || previewNode?.comfyClass || previewNode?.type || "") === PREVIEW3D_NODE_NAME) {
    previewNode.properties["Last Time Model File"] = reference.widgetValue;
  }
  previewNode.setDirtyCanvas?.(true, true);

  const modelUrl = getModelUrl(reference.raw);
  if (!modelUrl) return;

  const load3d = await getLoad3dForNode(previewNode);
  if (!load3d) {
    return;
  }

  try {
    await load3d.loadModel(modelUrl, reference.cleanPath);
    load3d.refreshViewport?.();
  } catch (error) {
    console.error("[MKRShift] Failed to reload Preview3D from linked model_file", error);
  }
}

function getConnectedPreviewNodes(sourceNode) {
  const graph = sourceNode?.graph || app.graph;
  const outputs = Array.isArray(sourceNode?.outputs) ? sourceNode.outputs : [];
  const previewNodes = [];
  const seen = new Set();

  outputs.forEach((output) => {
    const outputName = String(output?.name || output?.label || "");
    if (outputName && outputName !== MODEL_FILE_NAME) {
      return;
    }

    for (const linkId of output?.links || []) {
      const link = getGraphLink(graph, linkId);
      if (!link) continue;

      const targetNode = graph?.getNodeById?.(link.target_id) || app.graph?.getNodeById?.(link.target_id) || null;
      if (!targetNode || !isLoad3DNode(targetNode)) continue;

      const targetInputName = String(targetNode?.inputs?.[link.target_slot]?.name || "");
      if (targetInputName !== MODEL_FILE_NAME) continue;
      if (seen.has(targetNode.id)) continue;

      seen.add(targetNode.id);
      previewNodes.push(targetNode);
    }
  });

  return previewNodes;
}

async function syncPreviewNodeFromLinkedSource(previewNode) {
  const sourceNode = getLinkedSourceNode(previewNode);
  const modelFile = resolveLinkedSourceModelFile(previewNode);
  if (modelFile) {
    await applyModelFileToPreviewNode(previewNode, modelFile, getSourceModelFileFallbackType(sourceNode, modelFile));
  }
}

function patchPreviewNode(node) {
  if (!isLoad3DNode(node) || node.__mkrPreview3DBridgePatched) return;
  node.__mkrPreview3DBridgePatched = true;
  patchPreview3DExecution(node);
  sanitizePreview3DStoredModelFile(node);

  const originalOnConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange(...args) {
    const result = originalOnConnectionsChange?.apply(this, args);
    queueMicrotask(() => {
      void syncPreviewNodeFromLinkedSource(this);
    });
    return result;
  };
}

function getEventPayload(event) {
  return event?.detail && typeof event.detail === "object" ? event.detail : event;
}

async function handleExecuted(event) {
  const payload = getEventPayload(event);
  const candidate = extractModelFileCandidate(payload);
  if (!candidate) return;

  const sourceId = payload?.display_node ?? payload?.node;
  const sourceNode = sourceId != null ? app.graph?.getNodeById?.(sourceId) || null : null;
  if (!sourceNode) return;

  rememberSourceModelFile(sourceNode, candidate);

  const previewNodes = getConnectedPreviewNodes(sourceNode);
  for (const previewNode of previewNodes) {
    await applyModelFileToPreviewNode(previewNode, candidate, getSourceModelFileFallbackType(sourceNode, candidate));
  }
}

function preparePreviewNode(node) {
  if (!isLoad3DNode(node)) return;
  patchPreviewNode(node);
  queueMicrotask(() => {
    void syncPreviewNodeFromLinkedSource(node);
  });
}

app.registerExtension({
  name: EXT,
  setup() {
    comfyApi.addEventListener("executed", handleExecuted);
  },
  nodeCreated(node) {
    preparePreviewNode(node);
  },
  async afterConfigureGraph() {
    const nodes = app.graph?._nodes || [];
    for (const node of nodes) {
      preparePreviewNode(node);
    }
  },
});
