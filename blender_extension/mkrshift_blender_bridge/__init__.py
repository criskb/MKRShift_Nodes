bl_info = {
    "name": "MKRShift Blender Bridge",
    "author": "MKRShift",
    "version": (0, 1, 3),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > MKRShift",
    "description": "Exports Blender camera and pose payloads for MKRShift ComfyUI bridge nodes",
    "category": "Import-Export",
}

from . import operators as _operators
from . import ui as _ui


CLASSES = (
    _operators.MKRSHIFT_OT_copy_camera_payload,
    _operators.MKRSHIFT_OT_copy_pose_payload,
    _operators.MKRSHIFT_OT_copy_image_payload,
    _operators.MKRSHIFT_OT_copy_material_payload,
    _operators.MKRSHIFT_OT_copy_scene_packet,
    _operators.MKRSHIFT_OT_save_scene_packet,
    _operators.MKRSHIFT_OT_apply_image_output_plan,
    _operators.MKRSHIFT_OT_apply_material_return_plan,
    _operators.MKRSHIFT_OT_submit_live_payload,
    _operators.MKRSHIFT_OT_poll_endpoint_job,
    _ui.MKRSHIFT_PT_bridge_panel,
    _ui.MKRSHIFT_PT_shader_bridge_panel,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mkrshift_endpoint_plan_path = bpy.props.StringProperty(
        name="Endpoint Plan",
        subtype="FILE_PATH",
        default="",
    )
    bpy.types.Scene.mkrshift_endpoint_job_id = bpy.props.StringProperty(
        name="Endpoint Job ID",
        default="",
    )
    bpy.types.Scene.mkrshift_endpoint_last_response = bpy.props.StringProperty(
        name="Endpoint Response",
        default="",
    )


def unregister():
    import bpy

    for prop_name in ("mkrshift_endpoint_last_response", "mkrshift_endpoint_job_id", "mkrshift_endpoint_plan_path"):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
