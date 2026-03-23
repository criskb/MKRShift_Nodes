from __future__ import annotations

import bpy
from . import operators as _operators


def _draw_workflow_interface(layout, context):
    workflow_box = layout.box()
    workflow_box.label(text="Workflow Interface")
    workflow_box.prop(context.scene, "mkrshift_workflow_interface_path", text="Interface JSON")
    action_row = workflow_box.row(align=True)
    action_row.operator("mkrshift_bridge.load_workflow_interface", text="Load", icon="FILE_REFRESH")
    action_row.operator("mkrshift_bridge.copy_workflow_inputs", text="Copy Inputs", icon="COPYDOWN")

    payload = _operators._load_workflow_interface_data(context)
    if not payload:
        workflow_box.label(text="No workflow interface loaded", icon="INFO")
        return

    _operators._ensure_workflow_props(context, payload)
    fields = _operators._workflow_fields(payload)
    groups = {}
    for field in fields:
        group = str(field.get("group") or "Workflow").strip() or "Workflow"
        groups.setdefault(group, []).append(field)

    if payload.get("interface_name"):
        workflow_box.label(text=str(payload.get("interface_name")))
    for group_name, group_fields in groups.items():
        group_box = workflow_box.box()
        group_box.label(text=group_name)
        for field in group_fields:
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            prop_name = f'mkrshift_wf_{key}'
            label = str(field.get("label") or key)
            field_type = str(field.get("type") or "text")
            help_text = str(field.get("help") or "").strip()
            if field_type == "choice":
                group_box.label(text=f"{label}: {context.scene.get(prop_name, field.get('default', ''))}")
                choice_row = group_box.row(align=True)
                for choice in field.get("choices") or []:
                    op = choice_row.operator("mkrshift_bridge.set_workflow_choice", text=str(choice))
                    op.field_key = key
                    op.choice_value = str(choice)
            else:
                group_box.prop(context.scene, f'["{prop_name}"]', text=label)
            if help_text:
                group_box.label(text=help_text, icon="QUESTION")


class MKRSHIFT_PT_bridge_panel(bpy.types.Panel):
    bl_label = "MKRShift Bridge"
    bl_idname = "MKRSHIFT_PT_bridge_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MKRShift"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Export payloads for MKRShift nodes")
        bridge_box = layout.box()
        bridge_box.label(text="Endpoint Bridge")
        bridge_box.prop(context.scene, "mkrshift_endpoint_plan_path", text="Endpoint Plan")
        bridge_box.prop(context.scene, "mkrshift_endpoint_job_id", text="Job ID")
        live_col = bridge_box.column(align=True)
        live_row = live_col.row(align=True)
        live_row.operator("mkrshift_bridge.submit_live_payload", text="Submit Scene", icon="URL").payload_kind = "scene"
        live_row.operator("mkrshift_bridge.poll_endpoint_job", text="Poll", icon="FILE_REFRESH")
        live_row = live_col.row(align=True)
        live_row.operator("mkrshift_bridge.submit_live_payload", text="Camera").payload_kind = "camera"
        live_row.operator("mkrshift_bridge.submit_live_payload", text="Pose").payload_kind = "pose"
        live_row = live_col.row(align=True)
        live_row.operator("mkrshift_bridge.submit_live_payload", text="Material").payload_kind = "material"
        live_row.operator("mkrshift_bridge.submit_live_payload", text="Image").payload_kind = "image"
        col = layout.column(align=True)
        col.operator("mkrshift_bridge.copy_camera_payload", icon="CAMERA_DATA")
        col.operator("mkrshift_bridge.copy_pose_payload", icon="ARMATURE_DATA")
        col.operator("mkrshift_bridge.copy_image_payload", icon="IMAGE_DATA")
        col.operator("mkrshift_bridge.copy_material_payload", icon="MATERIAL")
        col.operator("mkrshift_bridge.copy_scene_packet", icon="OUTLINER_OB_CAMERA")
        col.separator()
        col.operator("mkrshift_bridge.save_scene_packet", icon="FILE_TICK")
        col.operator("mkrshift_bridge.apply_image_output_plan", icon="IMAGE_DATA")
        col.operator("mkrshift_bridge.apply_material_return_plan", icon="SHADING_TEXTURE")
        _draw_workflow_interface(layout, context)


class MKRSHIFT_PT_shader_bridge_panel(bpy.types.Panel):
    bl_label = "MKRShift Material Bridge"
    bl_idname = "MKRSHIFT_PT_shader_bridge_panel"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "MKRShift"

    @classmethod
    def poll(cls, context):
        return getattr(getattr(context, "space_data", None), "tree_type", "") == "ShaderNodeTree"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Shader editor material bridge")
        bridge_box = layout.box()
        bridge_box.prop(context.scene, "mkrshift_endpoint_plan_path", text="Endpoint Plan")
        bridge_box.prop(context.scene, "mkrshift_endpoint_job_id", text="Job ID")
        live_col = bridge_box.column(align=True)
        live_col.operator("mkrshift_bridge.submit_live_payload", text="Submit Material", icon="URL").payload_kind = "material"
        live_col.operator("mkrshift_bridge.submit_live_payload", text="Submit Image", icon="IMAGE_DATA").payload_kind = "image"
        live_col.operator("mkrshift_bridge.poll_endpoint_job", text="Poll Endpoint", icon="FILE_REFRESH")
        col = layout.column(align=True)
        col.operator("mkrshift_bridge.copy_image_payload", icon="IMAGE_DATA")
        col.operator("mkrshift_bridge.copy_material_payload", icon="MATERIAL")
        col.operator("mkrshift_bridge.apply_image_output_plan", icon="IMAGE_DATA")
        col.operator("mkrshift_bridge.apply_material_return_plan", icon="SHADING_TEXTURE")
        _draw_workflow_interface(layout, context)
