import bpy
import logging
from bpy.types import Operator
from collections import defaultdict

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class JoinMeshesToParent(Operator):
    """Join selected mesh objects into their mesh parent to reduce object count.
    For mesh parents: children are joined into the parent (original behavior).
    For non-mesh parents: mesh children are joined together (parent left as-is).
    """
    bl_idname = "meddle.join_meshes_to_parent"
    bl_label = "Join Meshes to Parent"
    bl_description = "Join selected mesh children into their parent (if parent is a mesh) or merge siblings if parent is not a mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context, 'OBJECT')

        sel = context.selected_objects
        if not sel:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        # Collect selected mesh children that have any parent (mesh or non-mesh)
        mesh_children = [
            o for o in sel
            if o.type == 'MESH'
            and getattr(o, 'parent', None)
            and o.parent.name in bpy.data.objects
            and o.parent != o
        ]

        if not mesh_children:
            self.report({'INFO'}, "No selected mesh children with a parent")
            return {'CANCELLED'}

        # Group children by parent
        groups = defaultdict(list)
        for child in mesh_children:
            groups[child.parent].append(child)

        # Filter out parents with no valid children (defensive)
        parents = [p for p, kids in groups.items() if kids]
        if not parents:
            self.report({'INFO'}, "Nothing to join (no valid parent groups)")
            return {'CANCELLED'}

        # Depth ordering (deepest first) to stabilize hierarchy when multiple levels exist
        def _mesh_depth(obj):
            d = 0
            cur = getattr(obj, 'parent', None)
            while cur and getattr(cur, 'type', None) == 'MESH':
                d += 1
                cur = getattr(cur, 'parent', None)
            return d
        parents.sort(key=_mesh_depth, reverse=True)

        total_children_joined = 0
        non_mesh_merge_groups = 0

        # Preserve original selection & active
        try:
            orig_selected = list(sel)
        except Exception:
            orig_selected = []
        orig_active = context.view_layer.objects.active

        result_child_objects = []  # For non-mesh parent groups (resulting merged meshes)

        deselect_helper = _safe_deselect_all_objects
        view_layer = context.view_layer

        for parent in parents:
            children = [c for c in groups[parent] if c.name in bpy.data.objects]
            if len(children) < 2 and (parent.type != 'MESH'):
                # Not enough to merge among themselves
                continue
            if parent.type == 'MESH':
                # Original behavior: join children into mesh parent
                try:
                    # Deselect all
                    for o in context.selected_objects:
                        o.select_set(False)
                except Exception:
                    deselect_helper(context)

                # Select parent + children
                try:
                    parent.select_set(True)
                except Exception:
                    logger.warning("Could not select parent '%s'", getattr(parent, 'name', '<unknown>'))
                    continue
                for c in children:
                    try:
                        c.select_set(True)
                    except Exception:
                        logger.warning("Could not select child '%s'", getattr(c, 'name', '<unknown>'))
                # Active = parent
                if parent.name in bpy.data.objects:
                    try:
                        view_layer.objects.active = parent
                    except Exception:
                        pass

                ensure_object_mode(context, 'OBJECT')
                try:
                    bpy.ops.object.join()
                    joined_count = len(children)
                    total_children_joined += joined_count
                    logger.info("Joined %d child(ren) into mesh parent '%s'", joined_count, parent.name)
                except Exception as e:
                    logger.exception("Failed joining into parent '%s': %s", getattr(parent, 'name', '<unknown>'), str(e))
                    continue
            else:
                # Non-mesh parent: join children among themselves, keep parent relation
                if len(children) < 2:
                    continue  # Nothing to merge
                non_mesh_merge_groups += 1

                # Deselect all
                try:
                    for o in context.selected_objects:
                        o.select_set(False)
                except Exception:
                    deselect_helper(context)

                # Choose a base child (first) to become the merged object
                base = children[0]
                # Select only the children
                for c in children:
                    try:
                        c.select_set(True)
                    except Exception:
                        logger.warning("Could not select child '%s' for non-mesh merge", getattr(c, 'name', '<unknown>'))

                # Set base active
                if base.name in bpy.data.objects:
                    try:
                        view_layer.objects.active = base
                    except Exception:
                        pass

                ensure_object_mode(context, 'OBJECT')

                # Ensure base retains the original parent (others will vanish after join)
                original_parent = getattr(base, 'parent', None)
                try:
                    bpy.ops.object.join()
                    # After join, base remains; ensure it is still parented
                    if original_parent and base.parent != original_parent:
                        try:
                            mw = base.matrix_world.copy()
                            base.parent = original_parent
                            base.matrix_parent_inverse = original_parent.matrix_world.inverted() @ mw
                            base.matrix_world = mw
                        except Exception:
                            pass
                    result_child_objects.append(base)
                    joined_count = len(children) - 1
                    total_children_joined += joined_count
                    logger.info("Merged %d sibling mesh(es) under non-mesh parent '%s'", joined_count, getattr(parent, 'name', '<unknown>'))
                except Exception as e:
                    logger.exception("Failed merging children under non-mesh parent '%s': %s", getattr(parent, 'name', '<unknown>'), str(e))
                    continue

        # Restore a clean selection:
        try:
            deselect_helper(context)
            # Select parents (consistent with previous behavior)
            for p in parents:
                if p.name in bpy.data.objects:
                    p.select_set(True)
            # Also select resulting merged child meshes from non-mesh groups for convenience
            for r in result_child_objects:
                if r.name in bpy.data.objects:
                    r.select_set(True)
            # Restore or set active
            if orig_active and orig_active.name in bpy.data.objects:
                view_layer.objects.active = orig_active
            else:
                # Prefer a merged mesh result, else any parent
                for r in result_child_objects:
                    if r.name in bpy.data.objects:
                        view_layer.objects.active = r
                        break
                else:
                    for p in parents:
                        if p.name in bpy.data.objects:
                            view_layer.objects.active = p
                            break
        except Exception:
            pass

        if total_children_joined > 0:
            extra = ""
            if non_mesh_merge_groups > 0:
                extra = f" ({non_mesh_merge_groups} non-mesh parent group(s) merged)"
            self.report({'INFO'}, f"Joined {total_children_joined} child object(s) across {len(parents)} parent group(s){extra}")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No meshes were joined to parents")
            return {'CANCELLED'}