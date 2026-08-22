import bpy

from . import export, operators, properties, ui

classes = [
    properties.MeddleBake2MaterialSettings,
    properties.MeddleBake2MeshInfo,
    properties.MeddleBake2Settings,
    operators.MEDDLE_OT_bake2_run,
    operators.MEDDLE_OT_bake2_cancel,
    operators.MEDDLE_OT_bake2_refresh,
    operators.MEDDLE_OT_bake2_prepare_uvs,
    operators.MEDDLE_OT_bake2_select_mesh,
    operators.MEDDLE_OT_bake2_join_meshes,
    operators.MEDDLE_OT_bake2_atlas,
    operators.MEDDLE_OT_bake2_clear_materials,
    export.MEDDLE_OT_bake2_export_fbx,
    ui.MEDDLE_PT_bake2,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.meddle_bake2 = bpy.props.PointerProperty(
        type=properties.MeddleBake2Settings)


def unregister():
    del bpy.types.Scene.meddle_bake2
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
