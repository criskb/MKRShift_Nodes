import json
import sys
from pathlib import Path


_COMMON_DIR = Path(__file__).resolve().parents[1] / "common"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from python_endpoint_client import poll_status_from_file, submit_payload_from_file  # type: ignore


def _load_json(path_text):
    path = Path(str(path_text or "").strip())
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_texture_spec(texture_plan_path="", transport_plan_path="", endpoint_plan_path=""):
    return {
        "texture_plan": _load_json(texture_plan_path),
        "transport_plan": _load_json(transport_plan_path),
        "endpoint_plan": _load_json(endpoint_plan_path),
    }


def build_image_payload(image_path="", image_role="render"):
    return {
        "schema": "mkrshift_fusion360_image_v1",
        "name": "Fusion360Image",
        "path": str(image_path or "").strip(),
        "kind": "image",
        "role": str(image_role or "render").strip() or "render",
    }


def build_image_output_spec(image_plan_path="", transport_plan_path="", endpoint_plan_path=""):
    return {
        "image_output_plan": _load_json(image_plan_path),
        "transport_plan": _load_json(transport_plan_path),
        "endpoint_plan": _load_json(endpoint_plan_path),
    }


def build_playback_spec(image_plan_path="", start_frame=1, loop_mode="once", trigger_mode="manual"):
    return {
        "schema": "mkrshift_fusion360_playback_spec_v1",
        "image_output_plan": _load_json(image_plan_path),
        "start_frame": int(start_frame or 1),
        "loop_mode": str(loop_mode or "once").strip() or "once",
        "trigger_mode": str(trigger_mode or "manual").strip() or "manual",
    }


def submit_payload(endpoint_plan_path="", payload_path=""):
    return submit_payload_from_file(endpoint_plan_path, payload_path)


def poll_status(endpoint_plan_path="", job_id=""):
    return poll_status_from_file(endpoint_plan_path, job_id)


def run(context):
    return "MKRShift Fusion 360 Bridge"


def stop(context):
    return None
