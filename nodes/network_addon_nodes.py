import json
from typing import Any, Dict, Tuple

from ..categories import ADDONS_NETWORK
from ..lib.host_bridge_shared import clean_text, parse_json_object, slugify


def _json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


class MKROSCMessagePlan:
    SEARCH_ALIASES = ["osc plan", "osc output", "osc bridge", "udp osc"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "address": ("STRING", {"default": "/mkrshift/frame"}),
                "host": ("STRING", {"default": "127.0.0.1"}),
                "port": ("INT", {"default": 7000, "min": 1, "max": 65535}),
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("osc_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, address: str = "/mkrshift/frame", host: str = "127.0.0.1", port: int = 7000, payload_json: str = "{}") -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(payload_json, "payload_json")
        plan = {
            "schema": "mkrshift_osc_plan_v1",
            "protocol": "osc",
            "address": clean_text(address) or "/mkrshift/frame",
            "host": clean_text(host) or "127.0.0.1",
            "port": int(port),
            "payload": payload,
        }
        return (_json(plan), ",".join([plan["host"], str(plan["port"]), plan["address"]]), _json({"host": plan["host"], "port": plan["port"], "address": plan["address"], "warnings": warnings}))


class MKRNDIStreamPlan:
    SEARCH_ALIASES = ["ndi plan", "ndi output", "ndi stream", "ndi bridge"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "stream_name": ("STRING", {"default": "MKRShift NDI"}),
                "asset_path": ("STRING", {"default": ""}),
                "source_kind": (["image", "image_sequence", "video", "texture"], {"default": "video"}),
                "alpha_mode": (["ignore", "premultiplied", "straight"], {"default": "ignore"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("ndi_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, stream_name: str = "MKRShift NDI", asset_path: str = "", source_kind: str = "video", alpha_mode: str = "ignore") -> Tuple[str, str, str]:
        plan = {
            "schema": "mkrshift_ndi_plan_v1",
            "protocol": "ndi",
            "stream_name": clean_text(stream_name) or "MKRShift NDI",
            "stream_slug": slugify(stream_name, "mkrshift-ndi"),
            "asset_path": clean_text(asset_path),
            "source_kind": source_kind,
            "alpha_mode": alpha_mode,
        }
        return (_json(plan), ",".join([plan["stream_name"], source_kind, alpha_mode, plan["asset_path"]]), _json({"stream_name": plan["stream_name"], "has_path": bool(plan["asset_path"])}))


class MKRSpoutSenderPlan:
    SEARCH_ALIASES = ["spout plan", "spout sender", "spout output", "spout bridge"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sender_name": ("STRING", {"default": "MKRShift Spout"}),
                "asset_path": ("STRING", {"default": ""}),
                "source_kind": (["image", "image_sequence", "video", "texture"], {"default": "texture"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("spout_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, sender_name: str = "MKRShift Spout", asset_path: str = "", source_kind: str = "texture") -> Tuple[str, str, str]:
        plan = {
            "schema": "mkrshift_spout_plan_v1",
            "protocol": "spout",
            "sender_name": clean_text(sender_name) or "MKRShift Spout",
            "sender_slug": slugify(sender_name, "mkrshift-spout"),
            "asset_path": clean_text(asset_path),
            "source_kind": source_kind,
        }
        return (_json(plan), ",".join([plan["sender_name"], source_kind, plan["asset_path"]]), _json({"sender_name": plan["sender_name"], "has_path": bool(plan["asset_path"])}))


class MKRWebSocketBridgePlan:
    SEARCH_ALIASES = ["websocket plan", "ws plan", "websocket bridge", "network bridge"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": ("STRING", {"default": "ws://127.0.0.1:8188/mkrshift"}),
                "channel": ("STRING", {"default": "frame"}),
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("websocket_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, url: str = "ws://127.0.0.1:8188/mkrshift", channel: str = "frame", payload_json: str = "{}") -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(payload_json, "payload_json")
        plan = {
            "schema": "mkrshift_websocket_plan_v1",
            "protocol": "websocket",
            "url": clean_text(url) or "ws://127.0.0.1:8188/mkrshift",
            "channel": clean_text(channel) or "frame",
            "payload": payload,
        }
        return (_json(plan), ",".join([plan["url"], plan["channel"]]), _json({"url": plan["url"], "channel": plan["channel"], "warnings": warnings}))


class MKRTCPBridgePlan:
    SEARCH_ALIASES = ["tcp plan", "tcp output", "socket bridge", "tcp sender"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "host": ("STRING", {"default": "127.0.0.1"}),
                "port": ("INT", {"default": 7001, "min": 1, "max": 65535}),
                "framing": (["json_line", "raw_json", "length_prefixed"], {"default": "json_line"}),
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("tcp_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, host: str = "127.0.0.1", port: int = 7001, framing: str = "json_line", payload_json: str = "{}") -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(payload_json, "payload_json")
        plan = {
            "schema": "mkrshift_tcp_plan_v1",
            "protocol": "tcp",
            "host": clean_text(host) or "127.0.0.1",
            "port": int(port),
            "framing": framing,
            "payload": payload,
        }
        return (_json(plan), ",".join([plan["host"], str(plan["port"]), plan["framing"]]), _json({"host": plan["host"], "port": plan["port"], "framing": framing, "warnings": warnings}))


class MKRHTTPWebhookPlan:
    SEARCH_ALIASES = ["http webhook", "http plan", "rest output", "webhook bridge"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": ("STRING", {"default": "http://127.0.0.1:8188/mkrshift"}),
                "method": (["POST", "PUT", "PATCH"], {"default": "POST"}),
                "payload_json": ("STRING", {"default": "{}", "multiline": True}),
            },
            "optional": {
                "headers_json": ("STRING", {"default": "{}", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("http_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, url: str = "http://127.0.0.1:8188/mkrshift", method: str = "POST", payload_json: str = "{}", headers_json: str = "{}") -> Tuple[str, str, str]:
        payload, warnings = parse_json_object(payload_json, "payload_json")
        headers, header_warnings = parse_json_object(headers_json, "headers_json")
        warnings.extend(header_warnings)
        plan = {
            "schema": "mkrshift_http_plan_v1",
            "protocol": "http",
            "url": clean_text(url) or "http://127.0.0.1:8188/mkrshift",
            "method": method,
            "headers": headers,
            "payload": payload,
        }
        return (_json(plan), ",".join([plan["method"], plan["url"]]), _json({"url": plan["url"], "method": method, "header_count": len(headers), "warnings": warnings}))


class MKRSyphonSenderPlan:
    SEARCH_ALIASES = ["syphon plan", "syphon sender", "syphon output", "mac sender"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_name": ("STRING", {"default": "MKRShift Syphon"}),
                "asset_path": ("STRING", {"default": ""}),
                "source_kind": (["image", "image_sequence", "video", "texture"], {"default": "texture"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("syphon_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, server_name: str = "MKRShift Syphon", asset_path: str = "", source_kind: str = "texture") -> Tuple[str, str, str]:
        plan = {
            "schema": "mkrshift_syphon_plan_v1",
            "protocol": "syphon",
            "server_name": clean_text(server_name) or "MKRShift Syphon",
            "server_slug": slugify(server_name, "mkrshift-syphon"),
            "asset_path": clean_text(asset_path),
            "source_kind": source_kind,
        }
        return (_json(plan), ",".join([plan["server_name"], source_kind, plan["asset_path"]]), _json({"server_name": plan["server_name"], "has_path": bool(plan["asset_path"])}))


class MKRWatchFolderPlan:
    SEARCH_ALIASES = ["watch folder", "folder sync", "file watch", "directory bridge"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "watch_path": ("STRING", {"default": ""}),
                "pattern": ("STRING", {"default": "*.png"}),
                "ingest_mode": (["latest", "sequence", "all_changed"], {"default": "latest"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("watch_folder_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(self, watch_path: str = "", pattern: str = "*.png", ingest_mode: str = "latest") -> Tuple[str, str, str]:
        plan = {
            "schema": "mkrshift_watch_folder_plan_v1",
            "protocol": "watch_folder",
            "watch_path": clean_text(watch_path),
            "pattern": clean_text(pattern) or "*.png",
            "ingest_mode": ingest_mode,
        }
        return (_json(plan), ",".join([plan["watch_path"], plan["pattern"], plan["ingest_mode"]]), _json({"watch_path": plan["watch_path"], "pattern": plan["pattern"], "has_path": bool(plan["watch_path"])}))


class MKRAddonEndpointPlan:
    SEARCH_ALIASES = ["endpoint plan", "host endpoint", "addon endpoint", "http bridge config"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "http://127.0.0.1:8188"}),
                "submit_path": ("STRING", {"default": "/mkrshift/submit"}),
                "status_path": ("STRING", {"default": "/mkrshift/status/{job_id}"}),
                "result_path": ("STRING", {"default": "/mkrshift/result/{job_id}"}),
                "auth_mode": (["none", "bearer", "header"], {"default": "none"}),
                "auth_key": ("STRING", {"default": "Authorization"}),
                "auth_value": ("STRING", {"default": ""}),
                "timeout_ms": ("INT", {"default": 30000, "min": 1000, "max": 600000}),
            },
            "optional": {
                "default_headers_json": ("STRING", {"default": "{}", "multiline": True}),
                "workflow_hint": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("endpoint_plan_json", "manifest_line", "summary_json")
    FUNCTION = "build"
    CATEGORY = ADDONS_NETWORK

    def build(
        self,
        base_url: str = "http://127.0.0.1:8188",
        submit_path: str = "/mkrshift/submit",
        status_path: str = "/mkrshift/status/{job_id}",
        result_path: str = "/mkrshift/result/{job_id}",
        auth_mode: str = "none",
        auth_key: str = "Authorization",
        auth_value: str = "",
        timeout_ms: int = 30000,
        default_headers_json: str = "{}",
        workflow_hint: str = "",
    ) -> Tuple[str, str, str]:
        headers, warnings = parse_json_object(default_headers_json, "default_headers_json")
        plan = {
            "schema": "mkrshift_addon_endpoint_plan_v1",
            "protocol": "http_endpoint",
            "base_url": clean_text(base_url).rstrip("/") or "http://127.0.0.1:8188",
            "submit_path": clean_text(submit_path) or "/mkrshift/submit",
            "status_path": clean_text(status_path) or "/mkrshift/status/{job_id}",
            "result_path": clean_text(result_path) or "/mkrshift/result/{job_id}",
            "auth_mode": auth_mode,
            "auth_key": clean_text(auth_key) or "Authorization",
            "auth_value": clean_text(auth_value),
            "default_headers": headers,
            "timeout_ms": int(timeout_ms),
            "workflow_hint": clean_text(workflow_hint),
        }
        return (
            _json(plan),
            ",".join([plan["base_url"], plan["submit_path"], plan["auth_mode"], plan["workflow_hint"]]),
            _json(
                {
                    "base_url": plan["base_url"],
                    "submit_path": plan["submit_path"],
                    "auth_mode": plan["auth_mode"],
                    "has_auth_value": bool(plan["auth_value"]),
                    "workflow_hint": plan["workflow_hint"],
                    "warnings": warnings,
                }
            ),
        )
