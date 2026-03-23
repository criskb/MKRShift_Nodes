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
