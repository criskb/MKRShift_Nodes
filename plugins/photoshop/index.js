function parseJsonOrEmpty(raw) {
  try {
    const parsed = JSON.parse(String(raw || "").trim() || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    return {};
  }
}

function buildEndpointHeaders(endpointPlan) {
  const plan = endpointPlan && typeof endpointPlan === "object" ? endpointPlan : {};
  const headers = { "Content-Type": "application/json", ...(plan.default_headers || {}) };
  if (plan.auth_mode === "bearer" && plan.auth_value) {
    headers[plan.auth_key || "Authorization"] = `Bearer ${plan.auth_value}`;
  } else if (plan.auth_mode === "header" && plan.auth_value) {
    headers[plan.auth_key || "Authorization"] = plan.auth_value;
  }
  return headers;
}

function buildPhotoshopBridgeSpec(documentPayload, exportPlan, transportPlan, endpointPlan) {
  return {
    document: parseJsonOrEmpty(documentPayload),
    exportPlan: parseJsonOrEmpty(exportPlan),
    transportPlan: parseJsonOrEmpty(transportPlan),
    endpointPlan: parseJsonOrEmpty(endpointPlan),
  };
}

function buildPhotoshopImagePayload(documentPayload, preferredSlot = "") {
  const document = parseJsonOrEmpty(documentPayload);
  const layers = Array.isArray(document.layers) ? document.layers : [];
  const preferred = String(preferredSlot || "").toLowerCase();
  let chosen = layers.find((layer) =>
    preferred && String(layer.slot || layer.name || "").toLowerCase().includes(preferred),
  );
  if (!chosen) chosen = layers[0] || {};
  return {
    schema: "mkrshift_photoshop_image_payload_v1",
    host: "photoshop",
    document_name: document.document_name || "Untitled.psd",
    images: chosen.path
      ? [
          {
            slot: chosen.slot || chosen.name || "layer",
            path: chosen.path,
            layer_name: chosen.name || "Layer 1",
            blend_mode: chosen.blend_mode || "normal",
          },
        ]
      : [],
  };
}

function buildPhotoshopImageOutputSpec(imageOutputPlan, transportPlan, endpointPlan) {
  return {
    schema: "mkrshift_photoshop_image_output_spec_v1",
    imageOutputPlan: parseJsonOrEmpty(imageOutputPlan),
    transportPlan: parseJsonOrEmpty(transportPlan),
    endpointPlan: parseJsonOrEmpty(endpointPlan),
  };
}

async function submitPhotoshopPayload(endpointPlan, payload) {
  const plan = endpointPlan && typeof endpointPlan === "object" ? endpointPlan : {};
  const response = await fetch(`${String(plan.base_url || "").replace(/\/$/, "")}${plan.submit_path || "/mkrshift/submit"}`, {
    method: "POST",
    headers: buildEndpointHeaders(plan),
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

async function pollPhotoshopJob(endpointPlan, jobId = "") {
  const plan = endpointPlan && typeof endpointPlan === "object" ? endpointPlan : {};
  const base = `${String(plan.base_url || "").replace(/\/$/, "")}${plan.poll_path || "/mkrshift/status"}`.replace(/\/$/, "");
  const url = jobId ? `${base}/${encodeURIComponent(String(jobId))}` : base;
  const response = await fetch(url, {
    method: "GET",
    headers: buildEndpointHeaders(plan),
  });
  return response.json();
}

console.log("MKRShift Photoshop Plugin loaded");
