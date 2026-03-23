import json
from typing import Tuple

from ..categories import ADDONS_NETWORK
from ..lib.host_bridge_shared import clean_text, parse_json_object
from ..lib.network_runtime_shared import (
    apply_endpoint_headers,
    build_url,
    json_text,
    request_json,
    resolve_payload,
    send_osc_message,
    send_tcp_payload,
    write_watch_payload,
)


def _summary(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKRAddonEndpointSubmit:
    SEARCH_ALIASES = ["endpoint submit", "addon endpoint submit", "host submit", "http job submit"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "endpoint_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("response_json", "job_id", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, endpoint_plan_json: str = "{}", payload_json: str = "{}") -> Tuple[str, str, str]:
        plan, plan_warnings = parse_json_object(endpoint_plan_json, "endpoint_plan_json")
        payload, payload_warnings = resolve_payload(plan, payload_json)
        url = build_url(clean_text(plan.get("base_url")), clean_text(plan.get("submit_path")) or "/mkrshift/submit")
        headers = apply_endpoint_headers(plan)
        response, status, response_warnings = request_json(url, "POST", headers, payload, int(plan.get("timeout_ms", 30000) or 30000))
        job_id = clean_text(response.get("job_id"))
        summary = {
            "url": url,
            "status": status,
            "job_id": job_id,
            "warning_count": len(plan_warnings) + len(payload_warnings) + len(response_warnings),
            "warnings": plan_warnings + payload_warnings + response_warnings,
        }
        return (json_text(response), job_id, _summary(summary))


class MKRAddonEndpointPoll:
    SEARCH_ALIASES = ["endpoint poll", "job poll", "addon endpoint poll", "host status poll"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "endpoint_plan_json": ("STRING", {"default": "{}", "multiline": True}),
                "job_id": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("status_json", "result_json", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, endpoint_plan_json: str = "{}", job_id: str = "") -> Tuple[str, str, str]:
        plan, plan_warnings = parse_json_object(endpoint_plan_json, "endpoint_plan_json")
        job = clean_text(job_id)
        headers = apply_endpoint_headers(plan)
        timeout_ms = int(plan.get("timeout_ms", 30000) or 30000)
        status_url = build_url(clean_text(plan.get("base_url")), clean_text(plan.get("status_path")) or "/mkrshift/status/{job_id}", job_id=job)
        status_response, status_code, status_warnings = request_json(status_url, "GET", headers, None, timeout_ms)
        result_response = {}
        result_code = 0
        result_warnings = []
        state = clean_text(status_response.get("state") or status_response.get("status")).lower()
        if job and clean_text(plan.get("result_path")) and state in {"done", "complete", "completed", "success", "succeeded"}:
            result_url = build_url(clean_text(plan.get("base_url")), clean_text(plan.get("result_path")), job_id=job)
            result_response, result_code, result_warnings = request_json(result_url, "GET", headers, None, timeout_ms)
        summary = {
            "job_id": job,
            "status_code": status_code,
            "result_code": result_code,
            "state": state,
            "warnings": plan_warnings + status_warnings + result_warnings,
        }
        return (json_text(status_response), json_text(result_response), _summary(summary))


class MKRHTTPWebhookSend:
    SEARCH_ALIASES = ["http send", "webhook send", "rest send", "http runtime"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "http_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("response_json", "status_code", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, http_plan_json: str = "{}", payload_json: str = "{}") -> Tuple[str, int, str]:
        plan, plan_warnings = parse_json_object(http_plan_json, "http_plan_json")
        payload, payload_warnings = resolve_payload(plan, payload_json)
        headers = {clean_text(key): clean_text(value) for key, value in (plan.get("headers") if isinstance(plan.get("headers"), dict) else {}).items() if clean_text(key)}
        response, status_code, response_warnings = request_json(
            clean_text(plan.get("url")) or "http://127.0.0.1:8188/mkrshift",
            clean_text(plan.get("method")) or "POST",
            headers,
            payload,
            30000,
        )
        summary = {
            "url": clean_text(plan.get("url")),
            "method": clean_text(plan.get("method")) or "POST",
            "status_code": status_code,
            "warnings": plan_warnings + payload_warnings + response_warnings,
        }
        return (json_text(response), int(status_code), _summary(summary))


class MKRTCPBridgeSend:
    SEARCH_ALIASES = ["tcp send", "socket send", "tcp runtime", "bridge send"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tcp_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("sent_payload_json", "bytes_sent", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, tcp_plan_json: str = "{}", payload_json: str = "{}") -> Tuple[str, int, str]:
        plan, plan_warnings = parse_json_object(tcp_plan_json, "tcp_plan_json")
        payload, payload_warnings = resolve_payload(plan, payload_json)
        host = clean_text(plan.get("host")) or "127.0.0.1"
        port = int(plan.get("port", 7001) or 7001)
        framing = clean_text(plan.get("framing")) or "json_line"
        bytes_sent, send_warnings = send_tcp_payload(host, port, framing, payload)
        summary = {
            "host": host,
            "port": port,
            "framing": framing,
            "bytes_sent": bytes_sent,
            "warnings": plan_warnings + payload_warnings + send_warnings,
        }
        return (json_text(payload), int(bytes_sent), _summary(summary))


class MKROSCSend:
    SEARCH_ALIASES = ["osc send", "osc runtime", "udp osc send", "osc output"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "osc_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("sent_payload_json", "bytes_sent", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, osc_plan_json: str = "{}", payload_json: str = "{}") -> Tuple[str, int, str]:
        plan, plan_warnings = parse_json_object(osc_plan_json, "osc_plan_json")
        payload, payload_warnings = resolve_payload(plan, payload_json)
        host = clean_text(plan.get("host")) or "127.0.0.1"
        port = int(plan.get("port", 7000) or 7000)
        address = clean_text(plan.get("address")) or "/mkrshift/frame"
        bytes_sent, send_warnings, type_tags = send_osc_message(host, port, address, payload)
        summary = {
            "host": host,
            "port": port,
            "address": address,
            "bytes_sent": bytes_sent,
            "type_tags": "".join(type_tags),
            "warnings": plan_warnings + payload_warnings + send_warnings,
        }
        return (json_text(payload), int(bytes_sent), _summary(summary))


class MKRWatchFolderWrite:
    SEARCH_ALIASES = ["watch folder write", "folder write", "watch runtime", "directory write"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "watch_folder_plan_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
                "filename_hint": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("written_path", "written_payload_json", "summary_json")
    FUNCTION = "run"
    CATEGORY = ADDONS_NETWORK

    def run(self, watch_folder_plan_json: str = "{}", payload_json: str = "{}", filename_hint: str = "") -> Tuple[str, str, str]:
        plan, plan_warnings = parse_json_object(watch_folder_plan_json, "watch_folder_plan_json")
        payload, payload_warnings = resolve_payload(plan, payload_json)
        path, write_warnings = write_watch_payload(clean_text(plan.get("watch_path")), clean_text(plan.get("pattern")) or "*.json", payload, filename_hint)
        summary = {
            "written_path": path,
            "pattern": clean_text(plan.get("pattern")) or "*.json",
            "warnings": plan_warnings + payload_warnings + write_warnings,
        }
        return (path, json_text(payload), _summary(summary))
