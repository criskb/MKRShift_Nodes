import json
from pathlib import Path
from urllib import request


class MKRShiftBridgeExt:
    """
    Minimal TouchDesigner component extension scaffold for MKRShift bridge packets.
    Drop this into a bridge COMP and point your DAT/TOP network at it.
    """

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.lastPacket = {}

    def _par_text(self, name, default=""):
        try:
            return str(getattr(self.ownerComp.par, name).eval() or "").strip()
        except Exception:
            return default

    def loadPacketFromText(self, raw_text):
        text = str(raw_text or "").strip()
        if not text:
            self.lastPacket = {}
            return {}
        self.lastPacket = json.loads(text)
        return self.lastPacket

    def loadPacketFromFile(self, path_text):
        path = Path(str(path_text or "").strip())
        if not path.is_file():
            self.lastPacket = {}
            return {}
        self.lastPacket = json.loads(path.read_text(encoding="utf-8"))
        return self.lastPacket

    def loadTransportPlanFromFile(self, path_text):
        path = Path(str(path_text or "").strip())
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def loadEndpointPlanFromFile(self, path_text):
        path = Path(str(path_text or "").strip())
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _build_endpoint_headers(self, endpoint_plan):
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

    def buildOutgoingPayload(self):
        return {
            "schema": "mkrshift_touchdesigner_bridge_v1",
            "source": "touchdesigner",
            "project_name": self.ownerComp.project.name if hasattr(self.ownerComp, "project") else "TouchDesigner",
            "tox_name": getattr(self.ownerComp, "name", "MKRShiftBridge"),
            "operator_path": getattr(self.ownerComp, "path", "/project1/mkrshift_bridge1"),
            "transport": self._par_text("Transport", "file"),
            "top_name": self._par_text("Topname", "mkrshiftTOP"),
            "width": int(float(self._par_text("Width", "1920"))),
            "height": int(float(self._par_text("Height", "1080"))),
            "fps": float(self._par_text("Fps", "60")),
            "controls": {},
            "textures": [],
            "notes": self._par_text("Notes", ""),
        }

    def buildImagePayload(self, image_path="", slot_name="beauty", top_name=""):
        return {
            "schema": "mkrshift_touchdesigner_image_payload_v1",
            "host": "touchdesigner",
            "project_name": self.ownerComp.project.name if hasattr(self.ownerComp, "project") else "TouchDesigner",
            "tox_name": getattr(self.ownerComp, "name", "MKRShiftBridge"),
            "operator_path": getattr(self.ownerComp, "path", "/project1/mkrshift_bridge1"),
            "images": [
                {
                    "slot": str(slot_name or "beauty").strip() or "beauty",
                    "path": str(image_path or "").strip(),
                    "top_name": str(top_name or self._par_text("Topname", "mkrshiftTOP")).strip() or "mkrshiftTOP",
                }
            ] if str(image_path or "").strip() else [],
        }

    def buildImageOutputSpec(self, image_output_plan_path="", transport_plan_path="", endpoint_plan_path=""):
        image_output_plan = {}
        image_path = Path(str(image_output_plan_path or "").strip())
        if image_path.is_file():
            image_output_plan = json.loads(image_path.read_text(encoding="utf-8"))
        transport_plan = self.loadTransportPlanFromFile(transport_plan_path)
        endpoint_plan = self.loadEndpointPlanFromFile(endpoint_plan_path)
        return {
            "schema": "mkrshift_touchdesigner_image_output_spec_v1",
            "packet": self.lastPacket,
            "image_output_plan": image_output_plan,
            "transport_plan": transport_plan,
            "endpoint_plan": endpoint_plan,
        }

    def buildPlaybackSpec(self, frame_plan_path="", start_frame=1, loop_mode="once", trigger_mode="manual"):
        frame_plan = {}
        frame_path = Path(str(frame_plan_path or "").strip())
        if frame_path.is_file():
            frame_plan = json.loads(frame_path.read_text(encoding="utf-8"))
        return {
            "schema": "mkrshift_touchdesigner_playback_spec_v1",
            "frame_plan": frame_plan,
            "start_frame": int(start_frame or 1),
            "loop_mode": str(loop_mode or "once").strip() or "once",
            "trigger_mode": str(trigger_mode or "manual").strip() or "manual",
        }

    def submitPayload(self, endpoint_plan_path="", payload=None):
        endpoint_plan = self.loadEndpointPlanFromFile(endpoint_plan_path)
        base_url = str(endpoint_plan.get("base_url") or "").rstrip("/")
        submit_path = str(endpoint_plan.get("submit_path") or "/mkrshift/submit")
        body = json.dumps(payload if isinstance(payload, dict) else self.buildOutgoingPayload()).encode("utf-8")
        req = request.Request(
            url=f"{base_url}{submit_path}",
            data=body,
            headers=self._build_endpoint_headers(endpoint_plan),
            method="POST",
        )
        with request.urlopen(req, timeout=float(endpoint_plan.get("timeout_ms", 30000)) / 1000.0) as response:
            return json.loads(response.read().decode("utf-8"))

    def pollStatus(self, endpoint_plan_path="", job_id=""):
        endpoint_plan = self.loadEndpointPlanFromFile(endpoint_plan_path)
        base_url = str(endpoint_plan.get("base_url") or "").rstrip("/")
        poll_path = str(endpoint_plan.get("poll_path") or "/mkrshift/status").rstrip("/")
        job = str(job_id or "").strip()
        url = f"{base_url}{poll_path}"
        if job:
            url = f"{url}/{job}"
        req = request.Request(url=url, headers=self._build_endpoint_headers(endpoint_plan), method="GET")
        with request.urlopen(req, timeout=float(endpoint_plan.get("timeout_ms", 30000)) / 1000.0) as response:
            return json.loads(response.read().decode("utf-8"))

    def buildFrameSpec(self, frame_plan_path="", transport_plan_path="", endpoint_plan_path=""):
        frame_plan = {}
        transport_plan = {}
        endpoint_plan = {}
        frame_path = Path(str(frame_plan_path or "").strip())
        if frame_path.is_file():
            frame_plan = json.loads(frame_path.read_text(encoding="utf-8"))
        transport_plan = self.loadTransportPlanFromFile(transport_plan_path)
        endpoint_plan = self.loadEndpointPlanFromFile(endpoint_plan_path)
        return {
            "packet": self.lastPacket,
            "frame_plan": frame_plan,
            "transport_plan": transport_plan,
            "endpoint_plan": endpoint_plan,
        }

    def exportPayloadToDat(self, dat_op):
        payload = self.buildOutgoingPayload()
        dat_op.text = json.dumps(payload, ensure_ascii=False, indent=2)
        return payload
