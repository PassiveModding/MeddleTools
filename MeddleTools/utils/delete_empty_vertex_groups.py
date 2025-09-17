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

class DeleteEmptyVertexGroups(Operator):
    """Delete vertex groups that have no vertex weights from selected mesh objects"""
    bl_idname = "meddle.delete_empty_vertex_groups"
    bl_label = "Delete Empty Vertex Groups"
    bl_description = "Remove vertex groups from selected mesh objects that have no vertices assigned (weight == 0)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Enable only when at least one Mesh is selected.

        This greys out the button in the UI unless any selected object
        is a Mesh. Using selected_objects (not only active_object) makes
        it work when multiple meshes are selected.
        """
        try:
            selected = getattr(context, 'selected_objects', []) or []
            return any(obj and getattr(obj, 'type', None) == 'MESH' for obj in selected)
        except Exception:
            return False

    def execute(self, context):
        # Ensure object mode
        helpers.ensure_object_mode(context, 'OBJECT')

        selected_meshes = helpers.get_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        total_removed = 0
        for obj in selected_meshes:
            removed_this_obj = 0

            # Fast-path: if there are no vertex groups, skip
            vg_count = len(obj.vertex_groups)
            if vg_count == 0:
                continue

            # Build a boolean list marking which vertex groups have any weight > 0
            # This iterates vertices only once (O(#vertices + #groups)) instead of
            # checking every group against all vertices (O(#groups * #vertices)).
            has_weight = [False] * vg_count
            try:
                mesh = obj.data
                for v in mesh.vertices:
                    for g in v.groups:
                        gi = g.group
                        if 0 <= gi < vg_count and g.weight > 0.0:
                            has_weight[gi] = True
                # Collect groups to remove (use list to avoid mutating while iterating)
                to_remove = [vg for vg in obj.vertex_groups if vg.index < vg_count and not has_weight[vg.index]]

                for vg in to_remove:
                    try:
                        obj.vertex_groups.remove(vg)
                        removed_this_obj += 1
                    except Exception:
                        # Ignore failures to remove a specific group
                        pass
            except Exception:
                # If anything goes wrong accessing mesh data, skip this object defensively
                removed_this_obj = 0

            if removed_this_obj > 0:
                logger.info("Removed %d empty vertex group(s) from '%s'", removed_this_obj, obj.name)
            total_removed += removed_this_obj

        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} empty vertex group(s) from selected meshes")
        else:
            self.report({'INFO'}, "No empty vertex groups found on selected meshes")
        return {'FINISHED'}