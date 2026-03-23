import json
import sys
from pathlib import Path


_COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from python_endpoint_client import poll_status_from_file, submit_payload_from_file  # type: ignore


def load_json_file(path_text):
    path = Path(str(path_text or "").strip())
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_packet(path_text):
    return load_json_file(path_text)


def load_transport_plan(path_text):
    return load_json_file(path_text)


def load_endpoint_plan(path_text):
    return load_json_file(path_text)


def build_read_node_spec(packet_path="", transport_plan_path="", endpoint_plan_path=""):
    packet = load_packet(packet_path)
    transport = load_transport_plan(transport_plan_path)
    endpoint = load_endpoint_plan(endpoint_plan_path)
    return {
        "script_name": packet.get("script_name", "untitled.nk"),
        "reads": packet.get("reads", []),
        "transport_plan": transport,
        "endpoint_plan": endpoint,
    }


def build_image_payload(packet_path="", preferred_slot="", read_name=""):
    packet = load_packet(packet_path)
    reads = packet.get("reads") if isinstance(packet.get("reads"), list) else []
    chosen = {}
    preferred = str(preferred_slot or "").strip().lower()
    read_match = str(read_name or "").strip().lower()
    for item in reads:
        if not isinstance(item, dict):
            continue
        if read_match and str(item.get("name") or "").strip().lower() == read_match:
            chosen = item
            break
        if preferred and preferred in str(item.get("slot") or item.get("name") or "").strip().lower():
            chosen = item
            break
    if not chosen and reads:
        chosen = reads[0]
    return {
        "schema": "mkrshift_nuke_image_payload_v1",
        "host": "nuke",
        "script_name": packet.get("script_name", "untitled.nk"),
        "images": [
            {
                "slot": chosen.get("slot") or chosen.get("name") or "read",
                "path": chosen.get("path", ""),
                "colorspace": chosen.get("colorspace", "default"),
                "read_name": chosen.get("name", "Read1"),
            }
        ] if chosen else [],
    }


def build_image_output_spec(image_output_plan_path="", transport_plan_path="", endpoint_plan_path=""):
    image_plan = load_json_file(image_output_plan_path)
    transport = load_transport_plan(transport_plan_path)
    endpoint = load_endpoint_plan(endpoint_plan_path)
    return {
        "schema": "mkrshift_nuke_image_output_spec_v1",
        "image_output_plan": image_plan,
        "transport_plan": transport,
        "endpoint_plan": endpoint,
    }


def build_live_bridge_spec(packet_path="", read_plan_path="", transport_plan_path="", endpoint_plan_path="", image_output_plan_path=""):
    return {
        "packet": load_packet(packet_path),
        "read_plan": load_json_file(read_plan_path),
        "transport_plan": load_transport_plan(transport_plan_path),
        "endpoint_plan": load_endpoint_plan(endpoint_plan_path),
        "image_output_plan": load_json_file(image_output_plan_path),
    }


def build_playback_spec(read_plan_path="", start_frame=1, loop_mode="once", trigger_mode="manual"):
    return {
        "schema": "mkrshift_nuke_playback_spec_v1",
        "read_plan": load_json_file(read_plan_path),
        "start_frame": int(start_frame or 1),
        "loop_mode": str(loop_mode or "once").strip() or "once",
        "trigger_mode": str(trigger_mode or "manual").strip() or "manual",
    }


def submit_payload(endpoint_plan_path="", payload_path=""):
    return submit_payload_from_file(endpoint_plan_path, payload_path)


def poll_status(endpoint_plan_path="", job_id=""):
    return poll_status_from_file(endpoint_plan_path, job_id)


def show_mkrshift_bridge_panel():
    return "MKRShift Nuke Bridge Panel"
