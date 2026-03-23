import json
import socket
import struct
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .host_bridge_shared import clean_text, parse_json_object, slugify


def json_text(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def resolve_payload(plan: Dict[str, Any], payload_override_json: Any, field_name: str = "payload_json") -> Tuple[Dict[str, Any], List[str]]:
    payload_override, warnings = parse_json_object(payload_override_json, field_name)
    if payload_override:
        return (payload_override, warnings)
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    return (payload, warnings)


def apply_endpoint_headers(plan: Dict[str, Any], base_headers: Dict[str, str] | None = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, value in (base_headers or {}).items():
        text_key = clean_text(key)
        if text_key:
            headers[text_key] = clean_text(value)
    for key, value in (plan.get("default_headers") if isinstance(plan.get("default_headers"), dict) else {}).items():
        text_key = clean_text(key)
        if text_key:
            headers[text_key] = clean_text(value)
    auth_mode = clean_text(plan.get("auth_mode")).lower()
    auth_key = clean_text(plan.get("auth_key")) or "Authorization"
    auth_value = clean_text(plan.get("auth_value"))
    if auth_value:
        if auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_mode == "header":
            headers[auth_key] = auth_value
    return headers


def build_url(base_url: str, path: str, **values: Any) -> str:
    root = clean_text(base_url).rstrip("/")
    raw_path = clean_text(path) or "/"
    rendered = raw_path.format(**{key: clean_text(value) for key, value in values.items()})
    if rendered.startswith("http://") or rendered.startswith("https://"):
        return rendered
    return f"{root}/{rendered.lstrip('/')}"


def request_json(url: str, method: str = "GET", headers: Dict[str, str] | None = None, payload: Dict[str, Any] | None = None, timeout_ms: int = 30000) -> Tuple[Dict[str, Any], int, List[str]]:
    warnings: List[str] = []
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url=url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, float(timeout_ms) / 1000.0)) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        status = int(exc.code)
        warnings.append(f"http error {status}")
    except Exception as exc:  # pragma: no cover - exercised broadly in tests through success path
        return ({"ok": False, "error": str(exc), "url": url}, 0, [str(exc)])

    if not body:
        return ({"ok": 200 <= status < 300, "url": url, "status": status}, status, warnings)
    try:
        payload_json = json.loads(body)
    except Exception:
        return ({"ok": 200 <= status < 300, "url": url, "status": status, "text": body}, status, warnings + ["response was not valid JSON"])
    if isinstance(payload_json, dict):
        payload_json.setdefault("ok", 200 <= status < 300)
        payload_json.setdefault("status", status)
        payload_json.setdefault("url", url)
        return (payload_json, status, warnings)
    return ({"ok": 200 <= status < 300, "status": status, "url": url, "data": payload_json}, status, warnings)


def send_tcp_payload(host: str, port: int, framing: str, payload: Dict[str, Any], timeout_ms: int = 10000) -> Tuple[int, List[str]]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "json_line":
        message = raw + b"\n"
    elif framing == "length_prefixed":
        message = struct.pack(">I", len(raw)) + raw
    else:
        message = raw
    warnings: List[str] = []
    with socket.create_connection((host, int(port)), timeout=max(1.0, float(timeout_ms) / 1000.0)) as client:
        client.sendall(message)
    if not payload:
        warnings.append("payload was empty")
    return (len(message), warnings)


def _osc_pad(raw: bytes) -> bytes:
    remainder = len(raw) % 4
    if remainder == 0:
        return raw
    return raw + (b"\x00" * (4 - remainder))


def _osc_string(value: str) -> bytes:
    return _osc_pad(clean_text(value).encode("utf-8") + b"\x00")


def _osc_arg(value: Any) -> Tuple[str, bytes]:
    if isinstance(value, bool):
        return ("T" if value else "F", b"")
    if isinstance(value, int) and not isinstance(value, bool):
        return ("i", struct.pack(">i", int(value)))
    if isinstance(value, float):
        return ("f", struct.pack(">f", float(value)))
    if isinstance(value, (dict, list, tuple)):
        return ("s", _osc_string(json.dumps(value, ensure_ascii=False)))
    return ("s", _osc_string(clean_text(value)))


def build_osc_packet(address: str, payload: Dict[str, Any]) -> Tuple[bytes, List[str], List[str]]:
    warnings: List[str] = []
    args_source = payload.get("args") if isinstance(payload.get("args"), list) else None
    if args_source is None:
        args_source = [payload[key] for key in sorted(payload.keys())]
        if payload and "args" not in payload:
            warnings.append("payload args inferred from sorted payload keys")
    tags = ","
    encoded_args: List[bytes] = []
    encoded_preview: List[str] = []
    for value in args_source:
        tag, encoded = _osc_arg(value)
        tags += tag
        encoded_args.append(encoded)
        encoded_preview.append(tag)
    packet = _osc_string(address) + _osc_string(tags) + b"".join(encoded_args)
    return (packet, warnings, encoded_preview)


def send_osc_message(host: str, port: int, address: str, payload: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    packet, warnings, preview = build_osc_packet(address, payload)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sent = sock.sendto(packet, (host, int(port)))
    if not payload:
        warnings.append("payload was empty")
    return (sent, warnings, preview)


def write_watch_payload(watch_path: str, pattern: str, payload: Dict[str, Any], filename_hint: str = "") -> Tuple[str, List[str]]:
    folder = Path(clean_text(watch_path)).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    hint = clean_text(filename_hint)
    if hint:
        filename = hint
    else:
        pattern_text = clean_text(pattern) or "*.json"
        suffix = Path(pattern_text.replace("*", "payload")).suffix or ".json"
        filename = f"{slugify(payload.get('job_id') or payload.get('name') or 'payload', 'payload')}{suffix}"
    path = folder / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    warnings: List[str] = []
    if path.suffix.lower() != ".json":
        warnings.append("watch-folder write stores JSON payload text regardless of filename suffix")
    return (str(path), warnings)
