import json
from pathlib import Path
from urllib import request


def load_json_file(path_text):
    path = Path(str(path_text or "").strip())
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_headers(endpoint_plan):
    plan = endpoint_plan if isinstance(endpoint_plan, dict) else {}
    headers = {"Content-Type": "application/json"}
    for key, value in (plan.get("default_headers") or {}).items():
        headers[str(key)] = str(value)
    auth_mode = str(plan.get("auth_mode") or "").strip()
    auth_key = str(plan.get("auth_key") or "Authorization").strip() or "Authorization"
    auth_value = str(plan.get("auth_value") or "").strip()
    if auth_mode == "bearer" and auth_value:
        headers[auth_key] = f"Bearer {auth_value}"
    elif auth_mode == "header" and auth_value:
        headers[auth_key] = auth_value
    return headers


def submit_payload(endpoint_plan, payload):
    plan = endpoint_plan if isinstance(endpoint_plan, dict) else {}
    base_url = str(plan.get("base_url") or "").rstrip("/")
    submit_path = str(plan.get("submit_path") or "/mkrshift/submit")
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(
        url=f"{base_url}{submit_path}",
        data=body,
        headers=build_headers(plan),
        method="POST",
    )
    with request.urlopen(req, timeout=float(plan.get("timeout_ms", 30000)) / 1000.0) as response:
        return json.loads(response.read().decode("utf-8"))


def submit_payload_from_file(endpoint_plan_path, payload_path):
    endpoint_plan = load_json_file(endpoint_plan_path)
    payload = load_json_file(payload_path)
    return submit_payload(endpoint_plan, payload)


def poll_status(endpoint_plan, job_id=""):
    plan = endpoint_plan if isinstance(endpoint_plan, dict) else {}
    base_url = str(plan.get("base_url") or "").rstrip("/")
    poll_path = str(plan.get("poll_path") or "/mkrshift/status").rstrip("/")
    url = f"{base_url}{poll_path}"
    job = str(job_id or "").strip()
    if job:
        url = f"{url}/{job}"
    req = request.Request(
        url=url,
        headers=build_headers(plan),
        method="GET",
    )
    with request.urlopen(req, timeout=float(plan.get("timeout_ms", 30000)) / 1000.0) as response:
        return json.loads(response.read().decode("utf-8"))


def poll_status_from_file(endpoint_plan_path, job_id=""):
    endpoint_plan = load_json_file(endpoint_plan_path)
    return poll_status(endpoint_plan, job_id)
