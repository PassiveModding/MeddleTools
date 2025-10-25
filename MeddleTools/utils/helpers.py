import bpy

def safe_deselect_all_objects(context: bpy.types.Context):
    try:
        for ob in context.view_layer.objects:
            try:
                ob.select_set(False)
            except Exception:
                pass
    except Exception:
        # Fallback: try currently selected objects
        for ob in list(getattr(context, 'selected_objects', [])):
            try:
                ob.select_set(False)
            except Exception:
                pass


def ensure_object_mode(context: bpy.types.Context, mode: str = 'OBJECT'):
    """Ensure the active object is in the specified mode (default: OBJECT).
    This wraps the common pattern of checking and calling the operator.
    """
    try:
        obj = context.object
        if obj and obj.mode != mode:
            bpy.ops.object.mode_set(mode=mode)
    except Exception:
        # Best-effort; if it fails, don't raise
        pass


def get_selected_meshes(context: bpy.types.Context, edit_mode_as_active: bool = False):
    """Return a list of selected mesh objects. If edit_mode_as_active is True and
    the active object is in EDIT mode, return only the active mesh (common UI case).
    """
    try:
        if edit_mode_as_active and context.object and context.object.mode == 'EDIT' and context.object.type == 'MESH':
            return [context.object]
    except Exception:
        pass
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def vertex_group_has_weights(mesh_obj, vertex_group):
    """Return True if the specified vertex_group has any vertex with weight > 0.
    Shared between multiple operators to avoid duplicated implementations.
    """
    mesh = mesh_obj.data
    group_index = vertex_group.index
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == group_index and g.weight > 0.0:
                return True
    return False


def cleanup_imported_objects(imported_objects):
    """Safely remove imported objects and their data-blocks. Non-fatal on errors."""
    for obj in imported_objects:
        try:
            if obj.type == 'MESH' and obj.data:
                bpy.data.meshes.remove(obj.data, do_unlink=True)
            elif obj.type == 'ARMATURE' and obj.data:
                bpy.data.armatures.remove(obj.data, do_unlink=True)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass