from __future__ import annotations

import bpy


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
