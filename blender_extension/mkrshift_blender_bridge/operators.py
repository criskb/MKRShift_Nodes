from __future__ import annotations

import json
from pathlib import Path
from urllib import request

import bpy

from .payloads import build_camera_payload, build_image_payload, build_material_payload, build_pose_payload, build_scene_packet


def _copy_payload(context, payload) -> set[str]:
    context.window_manager.clipboard = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"FINISHED"}


def _save_payload(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _load_json_file(path_text: str):
    path = Path(str(path_text or "").strip())
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_endpoint_headers(endpoint_plan):
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


def _submit_to_endpoint(endpoint_plan, payload):
    base_url = str(endpoint_plan.get("base_url") or "").rstrip("/")
    submit_path = str(endpoint_plan.get("submit_path") or "/mkrshift/submit")
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{base_url}{submit_path}",
        data=body,
        headers=_build_endpoint_headers(endpoint_plan),
        method="POST",
    )
    with request.urlopen(req, timeout=float(endpoint_plan.get("timeout_ms", 30000)) / 1000.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _poll_endpoint(endpoint_plan, job_id: str):
    base_url = str(endpoint_plan.get("base_url") or "").rstrip("/")
    poll_path = str(endpoint_plan.get("poll_path") or "/mkrshift/status").rstrip("/")
    url = f"{base_url}{poll_path}"
    job = str(job_id or "").strip()
    if job:
        url = f"{url}/{job}"
    req = request.Request(url=url, headers=_build_endpoint_headers(endpoint_plan), method="GET")
    with request.urlopen(req, timeout=float(endpoint_plan.get("timeout_ms", 30000)) / 1000.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _store_endpoint_response(context, payload):
    context.scene.mkrshift_endpoint_last_response = json.dumps(payload or {}, ensure_ascii=False, indent=2)
    context.window_manager.clipboard = context.scene.mkrshift_endpoint_last_response
    job_id = str((payload or {}).get("job_id") or (payload or {}).get("id") or "").strip()
    if job_id:
        context.scene.mkrshift_endpoint_job_id = job_id


def _endpoint_plan_from_scene(context):
    plan_path = getattr(context.scene, "mkrshift_endpoint_plan_path", "")
    plan = _load_json_file(plan_path)
    if not plan:
        raise FileNotFoundError("No valid endpoint plan JSON found")
    return plan


def _payload_for_kind(context, payload_kind: str):
    payload_kind = str(payload_kind or "scene").strip()
    if payload_kind == "camera":
        camera_object = getattr(context.scene, "camera", None)
        if not camera_object:
            raise ValueError("No active scene camera found")
        return build_camera_payload(camera_object, context.scene)
    if payload_kind == "pose":
        active_object = getattr(context, "active_object", None)
        if not active_object or getattr(active_object, "type", "") != "ARMATURE":
            raise ValueError("Select an armature object first")
        return build_pose_payload(active_object)
    if payload_kind == "material":
        payload = build_material_payload(context)
        if not payload.get("name"):
            raise ValueError("No active material found on the active object")
        return payload
    if payload_kind == "image":
        payload = build_image_payload(context)
        if not payload.get("path"):
            raise ValueError("No active image or texture found")
        return payload
    return build_scene_packet(context)


def _load_workflow_interface_data(context):
    path_text = getattr(context.scene, "mkrshift_workflow_interface_path", "")
    if path_text:
        payload = _load_json_file(path_text)
        if isinstance(payload, dict) and payload.get("schema") == "mkrshift_addon_workflow_interface_v1":
            context.scene.mkrshift_workflow_interface_cached_json = json.dumps(payload, ensure_ascii=False, indent=2)
            return payload
    cached = str(getattr(context.scene, "mkrshift_workflow_interface_cached_json", "") or "").strip()
    if not cached:
        return {}
    try:
        payload = json.loads(cached)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _workflow_fields(interface_payload):
    fields = interface_payload.get("fields") if isinstance(interface_payload, dict) else []
    return fields if isinstance(fields, list) else []


def _ensure_workflow_props(context, interface_payload):
    scene = context.scene
    for field in _workflow_fields(interface_payload):
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        prop_name = f"mkrshift_wf_{key}"
        if prop_name in scene:
            continue
        default = field.get("default")
        field_type = str(field.get("type") or "text").strip()
        if field_type == "bool":
            scene[prop_name] = bool(default)
        elif field_type == "int":
            try:
                scene[prop_name] = int(default)
            except Exception:
                scene[prop_name] = 0
        elif field_type == "float":
            try:
                scene[prop_name] = float(default)
            except Exception:
                scene[prop_name] = 0.0
        else:
            scene[prop_name] = "" if default is None else str(default)


def _collect_workflow_inputs(context, interface_payload=None):
    interface = interface_payload or _load_workflow_interface_data(context)
    _ensure_workflow_props(context, interface)
    values = {}
    for field in _workflow_fields(interface):
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        prop_name = f"mkrshift_wf_{key}"
        values[key] = context.scene.get(prop_name, field.get("default"))
    return values


class MKRSHIFT_OT_copy_camera_payload(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_camera_payload"
    bl_label = "Copy Camera Payload"
    bl_description = "Copy the active Blender camera payload to the clipboard"

    def execute(self, context):
        camera_object = getattr(context.scene, "camera", None)
        if not camera_object:
            self.report({"ERROR"}, "No active scene camera found")
            return {"CANCELLED"}
        return _copy_payload(context, build_camera_payload(camera_object, context.scene))


class MKRSHIFT_OT_copy_pose_payload(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_pose_payload"
    bl_label = "Copy Pose Payload"
    bl_description = "Copy the selected armature pose payload to the clipboard"

    def execute(self, context):
        active_object = getattr(context, "active_object", None)
        if not active_object or getattr(active_object, "type", "") != "ARMATURE":
            self.report({"ERROR"}, "Select an armature object first")
            return {"CANCELLED"}
        return _copy_payload(context, build_pose_payload(active_object))


class MKRSHIFT_OT_copy_scene_packet(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_scene_packet"
    bl_label = "Copy Scene Packet"
    bl_description = "Copy a combined camera + pose scene packet to the clipboard"

    def execute(self, context):
        return _copy_payload(context, build_scene_packet(context))


class MKRSHIFT_OT_copy_material_payload(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_material_payload"
    bl_label = "Copy Material Payload"
    bl_description = "Copy the active object's active material payload to the clipboard"

    def execute(self, context):
        payload = build_material_payload(context)
        if not payload.get("name"):
            self.report({"ERROR"}, "No active material found on the active object")
            return {"CANCELLED"}
        return _copy_payload(context, payload)


class MKRSHIFT_OT_copy_image_payload(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_image_payload"
    bl_label = "Copy Image Payload"
    bl_description = "Copy the active image or texture payload to the clipboard"

    def execute(self, context):
        payload = build_image_payload(context)
        if not payload.get("path"):
            self.report({"ERROR"}, "No active image or texture found")
            return {"CANCELLED"}
        return _copy_payload(context, payload)


class MKRSHIFT_OT_save_scene_packet(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.save_scene_packet"
    bl_label = "Save Scene Packet"
    bl_description = "Save the scene packet JSON to disk"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "Choose a destination file")
            return {"CANCELLED"}
        _save_payload(self.filepath, build_scene_packet(context))
        self.report({"INFO"}, f"Saved scene packet to {self.filepath}")
        return {"FINISHED"}

    def invoke(self, context, event):
        self.filepath = "//mkrshift_scene_packet.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MKRSHIFT_OT_apply_material_return_plan(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.apply_material_return_plan"
    bl_label = "Apply Material Return Plan"
    bl_description = "Apply a material return-plan JSON from disk to the target object/material slot"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "Choose a return-plan JSON file")
            return {"CANCELLED"}
        try:
            payload = json.loads(Path(self.filepath).read_text(encoding="utf-8"))
        except Exception as error:
            self.report({"ERROR"}, f"Failed to read return plan: {error}")
            return {"CANCELLED"}
        if not isinstance(payload, dict):
            self.report({"ERROR"}, "Return plan must be a JSON object")
            return {"CANCELLED"}

        material_name = str(payload.get("material_name") or "MKRShift Material").strip() or "MKRShift Material"
        target_object_name = str(payload.get("target_object_name") or "").strip()
        target_slot_name = str(payload.get("target_material_slot") or "").strip()
        textures = payload.get("textures") if isinstance(payload.get("textures"), dict) else {}

        target_object = bpy.data.objects.get(target_object_name) if target_object_name else context.active_object
        if target_object is None:
            self.report({"ERROR"}, "Target object not found")
            return {"CANCELLED"}

        material = None
        if target_slot_name:
            for slot in getattr(target_object, "material_slots", []):
                if getattr(getattr(slot, "material", None), "name", "") == target_slot_name:
                    material = slot.material
                    break
        if material is None:
            material = getattr(target_object, "active_material", None)
        if material is None:
            material = bpy.data.materials.new(name=material_name)
            if hasattr(target_object.data, "materials"):
                target_object.data.materials.append(material)

        material.use_nodes = True
        node_tree = material.node_tree
        principled = next((node for node in node_tree.nodes if getattr(node, "type", "") == "BSDF_PRINCIPLED"), None)
        if principled is None:
            principled = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in node_tree.nodes if getattr(node, "type", "") == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = node_tree.nodes.new("ShaderNodeOutputMaterial")
        if not any(link.from_node == principled and link.to_node == output for link in node_tree.links):
            node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        slot_mapping = {
            "base_color": ("Base Color", "sRGB"),
            "roughness": ("Roughness", "Non-Color"),
            "metallic": ("Metallic", "Non-Color"),
            "emission": ("Emission Color", "sRGB"),
            "alpha": ("Alpha", "Non-Color"),
        }
        normal_path = str(textures.get("normal") or "").strip()
        if normal_path:
            image = bpy.data.images.load(normal_path, check_existing=True)
            image.colorspace_settings.name = "Non-Color"
            tex_node = node_tree.nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            normal_node = node_tree.nodes.new("ShaderNodeNormalMap")
            node_tree.links.new(tex_node.outputs["Color"], normal_node.inputs["Color"])
            node_tree.links.new(normal_node.outputs["Normal"], principled.inputs["Normal"])

        for key, (socket_name, colorspace) in slot_mapping.items():
            path = str(textures.get(key) or "").strip()
            if not path:
                continue
            image = bpy.data.images.load(path, check_existing=True)
            image.colorspace_settings.name = colorspace
            tex_node = node_tree.nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            if socket_name in principled.inputs:
                node_tree.links.new(tex_node.outputs["Color"], principled.inputs[socket_name])

        self.report({"INFO"}, f"Applied material return plan to {target_object.name}")
        return {"FINISHED"}

    def invoke(self, context, event):
        self.filepath = "//mkrshift_material_return_plan.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MKRSHIFT_OT_apply_image_output_plan(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.apply_image_output_plan"
    bl_label = "Apply Image Output Plan"
    bl_description = "Apply an image output-plan JSON from disk to the target object/material/image context"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "Choose an image output-plan JSON file")
            return {"CANCELLED"}
        try:
            payload = json.loads(Path(self.filepath).read_text(encoding="utf-8"))
        except Exception as error:
            self.report({"ERROR"}, f"Failed to read image output plan: {error}")
            return {"CANCELLED"}
        if not isinstance(payload, dict):
            self.report({"ERROR"}, "Image output plan must be a JSON object")
            return {"CANCELLED"}

        asset_path = str(payload.get("asset_path") or "").strip()
        apply_mode = str(payload.get("apply_mode") or "texture_image").strip()
        target_name = str(payload.get("target_name") or "MKRShift Result").strip() or "MKRShift Result"
        target_material_name = str(payload.get("target_material_name") or "").strip()
        target_object_name = str(payload.get("target_object_name") or "").strip()
        if not asset_path:
            self.report({"ERROR"}, "Image output plan did not include an asset path")
            return {"CANCELLED"}

        image = bpy.data.images.load(asset_path, check_existing=True)
        target_object = bpy.data.objects.get(target_object_name) if target_object_name else context.active_object

        if apply_mode == "image_plane":
            bpy.ops.object.empty_add(type="IMAGE")
            obj = context.active_object
            obj.name = target_name
            obj.data = image
        elif apply_mode == "camera_background":
            camera_object = getattr(context.scene, "camera", None)
            if not camera_object:
                self.report({"ERROR"}, "No active camera found for camera_background mode")
                return {"CANCELLED"}
            camera_object.data.show_background_images = True
            bg = camera_object.data.background_images.new()
            bg.image = image
        elif apply_mode == "compositor_image":
            node_tree = getattr(context.scene, "node_tree", None)
            if node_tree is None:
                context.scene.use_nodes = True
                node_tree = context.scene.node_tree
            image_node = node_tree.nodes.new("CompositorNodeImage")
            image_node.name = target_name
            image_node.image = image
        else:
            if target_object is None:
                self.report({"ERROR"}, "Target object not found for texture_image mode")
                return {"CANCELLED"}
            material = bpy.data.materials.get(target_material_name) if target_material_name else getattr(target_object, "active_material", None)
            if material is None:
                material = bpy.data.materials.new(name=target_material_name or f"{target_name}_MAT")
                if hasattr(target_object.data, "materials"):
                    target_object.data.materials.append(material)
            material.use_nodes = True
            tex_node = material.node_tree.nodes.new("ShaderNodeTexImage")
            tex_node.name = target_name
            tex_node.image = image

        self.report({"INFO"}, f"Applied image output plan from {asset_path}")
        return {"FINISHED"}

    def invoke(self, context, event):
        self.filepath = "//mkrshift_image_output_plan.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MKRSHIFT_OT_submit_live_payload(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.submit_live_payload"
    bl_label = "Submit Live Payload"
    bl_description = "Submit the current Blender bridge payload directly to the configured endpoint plan"

    payload_kind: bpy.props.EnumProperty(
        name="Payload Kind",
        items=(
            ("scene", "Scene", ""),
            ("camera", "Camera", ""),
            ("pose", "Pose", ""),
            ("material", "Material", ""),
            ("image", "Image", ""),
        ),
        default="scene",
    )

    def execute(self, context):
        try:
            endpoint_plan = _endpoint_plan_from_scene(context)
            payload = _payload_for_kind(context, self.payload_kind)
            workflow_interface = _load_workflow_interface_data(context)
            workflow_values = _collect_workflow_inputs(context, workflow_interface) if workflow_interface else {}
            if workflow_interface:
                payload = {
                    "host_payload": payload,
                    "payload_kind": self.payload_kind,
                    "workflow_interface_name": str(workflow_interface.get("interface_name") or ""),
                    "workflow_id": str(workflow_interface.get("workflow_id") or ""),
                    "workflow_inputs": workflow_values,
                }
            response = _submit_to_endpoint(endpoint_plan, payload)
            _store_endpoint_response(context, response)
        except Exception as error:
            self.report({"ERROR"}, f"Submit failed: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Submitted {self.payload_kind} payload")
        return {"FINISHED"}


class MKRSHIFT_OT_poll_endpoint_job(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.poll_endpoint_job"
    bl_label = "Poll Endpoint Job"
    bl_description = "Poll the configured endpoint plan for the current job status"

    def execute(self, context):
        job_id = str(getattr(context.scene, "mkrshift_endpoint_job_id", "") or "").strip()
        if not job_id:
            self.report({"ERROR"}, "No endpoint job id set")
            return {"CANCELLED"}
        try:
            endpoint_plan = _endpoint_plan_from_scene(context)
            response = _poll_endpoint(endpoint_plan, job_id)
            _store_endpoint_response(context, response)
        except Exception as error:
            self.report({"ERROR"}, f"Poll failed: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Polled job {job_id}")
        return {"FINISHED"}


class MKRSHIFT_OT_load_workflow_interface(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.load_workflow_interface"
    bl_label = "Load Workflow Interface"
    bl_description = "Load a workflow interface JSON and seed dynamic MKRShift controls"

    def execute(self, context):
        payload = _load_workflow_interface_data(context)
        if not payload:
            self.report({"ERROR"}, "No valid workflow interface JSON found")
            return {"CANCELLED"}
        _ensure_workflow_props(context, payload)
        self.report({"INFO"}, f"Loaded workflow interface: {payload.get('interface_name', 'Workflow')}")
        return {"FINISHED"}


class MKRSHIFT_OT_copy_workflow_inputs(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.copy_workflow_inputs"
    bl_label = "Copy Workflow Inputs"
    bl_description = "Copy the current dynamic workflow input values to the clipboard"

    def execute(self, context):
        payload = _load_workflow_interface_data(context)
        if not payload:
            self.report({"ERROR"}, "No workflow interface loaded")
            return {"CANCELLED"}
        values = _collect_workflow_inputs(context, payload)
        context.window_manager.clipboard = json.dumps(
            {
                "workflow_interface_name": payload.get("interface_name", ""),
                "workflow_id": payload.get("workflow_id", ""),
                "workflow_inputs": values,
            },
            ensure_ascii=False,
            indent=2,
        )
        self.report({"INFO"}, "Copied workflow inputs")
        return {"FINISHED"}


class MKRSHIFT_OT_set_workflow_choice(bpy.types.Operator):
    bl_idname = "mkrshift_bridge.set_workflow_choice"
    bl_label = "Set Workflow Choice"
    bl_description = "Set a dynamic choice field value"

    field_key: bpy.props.StringProperty(default="")
    choice_value: bpy.props.StringProperty(default="")

    def execute(self, context):
        key = str(self.field_key or "").strip()
        if not key:
            self.report({"ERROR"}, "Missing workflow field key")
            return {"CANCELLED"}
        context.scene[f"mkrshift_wf_{key}"] = self.choice_value
        return {"FINISHED"}
