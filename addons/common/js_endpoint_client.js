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

async function submitEndpointPayload(endpointPlan, payload) {
  const plan = endpointPlan && typeof endpointPlan === "object" ? endpointPlan : {};
  const response = await fetch(`${String(plan.base_url || "").replace(/\/$/, "")}${plan.submit_path || "/mkrshift/submit"}`, {
    method: "POST",
    headers: buildEndpointHeaders(plan),
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

module.exports = { parseJsonOrEmpty, buildEndpointHeaders, submitEndpointPayload };
