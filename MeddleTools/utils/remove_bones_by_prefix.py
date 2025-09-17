import bpy
import logging
from bpy.types import Operator

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

def remove_bones_by_prefix(armature_obj, prefix: str, context: bpy.types.Context = None) -> int:
    """Remove bones from the given armature whose names start with `prefix`.

    Returns the number of bones removed. This is a best-effort helper that
    safely switches modes and restores selection/active object when possible.
    It swallows exceptions and returns 0 on error.
    """

    ctx = context or bpy.context
    if armature_obj is None or getattr(armature_obj, 'type', None) != 'ARMATURE':
        return 0

    removed_count = 0

    # Save selection / active / mode state to restore later
    try:
        original_selected = list(ctx.selected_objects)
    except Exception:
        original_selected = []
    original_active = ctx.view_layer.objects.active if hasattr(ctx, 'view_layer') else None
    original_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'

    try:
        # Make the armature active and selected
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass
        try:
            armature_obj.select_set(True)
            ctx.view_layer.objects.active = armature_obj
        except Exception:
            # best-effort fallback: try to set active by name
            try:
                ctx.view_layer.objects.active = bpy.data.objects.get(armature_obj.name)
            except Exception:
                pass

        # Enter edit mode on the armature
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except Exception:
            pass

        arm_data = armature_obj.data
        if not hasattr(arm_data, 'edit_bones'):
            return 0

        # Collect bones to remove (copy list because we'll modify edit_bones)
        to_remove = [b for b in arm_data.edit_bones if b.name.startswith(prefix)]

        for bone in to_remove:
            try:
                arm_data.edit_bones.remove(bone)
                removed_count += 1
            except Exception:
                # If a bone can't be removed, continue with others
                continue

    except Exception:
        removed_count = 0
    finally:
        # Restore mode
        try:
            if original_mode and original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=original_mode)
            else:
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        # Restore selection and active
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for o in original_selected:
                try:
                    o.select_set(True)
                except Exception:
                    pass
            if original_active:
                try:
                    ctx.view_layer.objects.active = original_active
                except Exception:
                    pass
        except Exception:
            pass

    return removed_count


class RemoveBonesByPrefix(Operator):
    """Remove bones from an armature whose names start with a prefix"""
    bl_idname = "meddle.remove_bones_by_prefix"
    bl_label = "Remove Bones by Prefix"
    bl_description = "Remove bones whose names start with the given prefix from the active armature"
    bl_options = {'REGISTER', 'UNDO'}

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="Remove bones whose name starts with this prefix",
        default=""
    )

    armature_name: bpy.props.StringProperty(
        name="Armature (optional)",
        description="Name of armature to operate on (defaults to active object)",
        default=""
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "prefix")
        layout.prop_search(self, "armature_name", bpy.data, "objects", text="Armature")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def execute(self, context):
        arm = None
        if self.armature_name:
            arm = bpy.data.objects.get(self.armature_name)
        if not arm:
            arm = context.active_object
        if not arm or arm.type != 'ARMATURE':
            self.report({'WARNING'}, "No armature selected or active")
            return {'CANCELLED'}

        removed = remove_bones_by_prefix(arm, self.prefix, context)
        if removed > 0:
            self.report({'INFO'}, f"Removed {removed} bone(s) starting with '{self.prefix}'")
        else:
            self.report({'INFO'}, f"No bones found starting with '{self.prefix}'")
        return {'FINISHED'}