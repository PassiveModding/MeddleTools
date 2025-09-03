import bpy
import logging
from bpy.types import Operator
from . import helpers

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class JoinByMaterial(Operator):
    """Join meshes that share the same material as the active object's active material"""
    bl_idname = "meddle.join_by_material"
    bl_label = "Join by Selected Material"
    bl_description = "Join mesh objects that use the same material as the active object's active material"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Work with selected mesh objects and group them by material
        helpers.ensure_object_mode(context, 'OBJECT')

        selected_meshes = helpers.get_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        # Map material name -> set of objects that use it
        mat_to_objs = {}
        for obj in selected_meshes:
            try:
                for slot in getattr(obj, 'material_slots', []):
                    mat = getattr(slot, 'material', None)
                    if mat is None:
                        continue
                    key = mat.name
                    if key not in mat_to_objs:
                        mat_to_objs[key] = {
                            'material': mat,
                            'objects': set()
                        }
                    mat_to_objs[key]['objects'].add(obj)
            except Exception:
                logger.exception("Error while checking material slots for object '%s'", getattr(obj, 'name', '<unknown>'))

        # Only perform joins for material groups with 2 or more objects
        join_groups = [v for v in mat_to_objs.values() if len(v['objects']) >= 2]
        if not join_groups:
            self.report({'INFO'}, "No groups of selected meshes share the same material — nothing to join")
            return {'CANCELLED'}

        total_joined = 0
        original_active = context.view_layer.objects.active

        for group in join_groups:
            objs = list(group['objects'])
            # Deselect all then select group's objects
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except Exception:
                helpers._safe_deselect_all_objects(context)

            for o in objs:
                try:
                    o.select_set(True)
                except Exception:
                    logger.warning("Could not select object '%s' for join", getattr(o, 'name', '<unknown>'))

            # Prefer previous active if it's part of the group
            if original_active in objs:
                context.view_layer.objects.active = original_active
            else:
                context.view_layer.objects.active = objs[0]

            active_obj = context.view_layer.objects.active

            # stabilize children so they do not shift after join
            # Re-parent children of the soon-to-be removed objects (other than active)
            # to the active object while preserving world transforms.
            for src in objs:
                if src == active_obj:
                    continue
                try:
                    for child in list(src.children):
                        # Skip if child is also being joined (it will be merged away)
                        if child in objs:
                            continue
                        # Only handle standard object parenting
                        if getattr(child, "parent_type", "OBJECT") != "OBJECT":
                            continue
                        if child.parent == active_obj:
                            continue
                        try:
                            mw = child.matrix_world.copy()
                            child.parent = active_obj
                            # Recompute inverse so local = active_inv * world
                            child.matrix_parent_inverse = active_obj.matrix_world.inverted() @ mw
                            child.matrix_world = mw  # ensure world transform unchanged
                        except Exception:
                            logger.debug("Failed to reparent child '%s' before join", getattr(child, 'name', '<unknown>'))
                except Exception:
                    pass

            # Ensure object mode and attempt join
            helpers.ensure_object_mode(context, 'OBJECT')
            try:
                bpy.ops.object.join()
                joined_count = len(objs)
                total_joined += joined_count
                logger.info("Joined %d objects using material '%s'", joined_count, group['material'].name)
            except Exception as e:
                logger.exception("Failed to join objects for material '%s': %s", group['material'].name, str(e))
                continue

        # Restore a sensible selection: select the active object if still present
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            helpers._safe_deselect_all_objects(context)
        if context.view_layer.objects.active and context.view_layer.objects.active.name in bpy.data.objects:
            try:
                context.view_layer.objects.active.select_set(True)
            except Exception:
                pass

        if total_joined > 0:
            self.report({'INFO'}, f"Joined {total_joined} objects across {len(join_groups)} material group(s)")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No objects were joined")
            return {'CANCELLED'}