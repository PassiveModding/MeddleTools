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

class CleanBoneHierarchy(Operator):
    """Remove unused bones from armatures that don't affect any vertices"""
    bl_idname = "meddle.clean_bone_hierarchy"
    bl_label = "Clean Bone Hierarchy"
    bl_description = "Remove unused bones from selected armatures that don't affect any vertices"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        # Determine target armatures: prefer selected, fallback to active armature
        armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
        if not armatures and context.active_object and context.active_object.type == 'ARMATURE':
            armatures = [context.active_object]

        if not armatures:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}

        total_removed = 0

        for arm_obj in armatures:
            used_bones = set()

            # Cache bone name set for quick membership checks
            try:
                arm_bone_names = set(b.name for b in arm_obj.data.bones)
            except Exception:
                arm_bone_names = set()

            # Iterate only meshes that reference this armature via an armature modifier
            for obj in (o for o in bpy.data.objects if o.type == 'MESH'):
                try:
                    # Quick check for armature modifier referencing this armature
                    mods = getattr(obj, 'modifiers', None)
                    if not mods:
                        continue
                    is_skinned = False
                    for mod in mods:
                        # avoid attribute errors by guarded access
                        if getattr(mod, 'type', None) == 'ARMATURE' and getattr(mod, 'object', None) == arm_obj:
                            is_skinned = True
                            break
                    if not is_skinned:
                        continue

                    mesh = obj.data
                    if mesh is None:
                        continue

                    # Build index->bone-name mapping only for groups whose names exist on the armature
                    vg_index_to_name = {}
                    for vg in obj.vertex_groups:
                        try:
                            if vg.name in arm_bone_names:
                                vg_index_to_name[vg.index] = vg.name
                        except Exception:
                            # Defensive: skip problematic groups
                            pass

                    if not vg_index_to_name:
                        continue

                    # Scan vertices once and mark used bone names when weight > 0
                    # Early exit if we've found all possible names referenced by this mesh
                    needed = set(vg_index_to_name.values())
                    for v in mesh.vertices:
                        for g in v.groups:
                            if g.weight > 0.0:
                                name = vg_index_to_name.get(g.group)
                                if name:
                                    used_bones.add(name)
                                    # If we've collected all we can from this mesh, stop
                                    if used_bones >= needed:
                                        break
                        if used_bones >= needed:
                            break
                except Exception:
                    # Defensive: skip problematic meshes/modifiers rather than failing
                    continue

            # Prepare to remove unused edit bones. Switch to edit mode once per armature.
            prev_active = context.view_layer.objects.active
            try:
                context.view_layer.objects.active = arm_obj
                ensure_object_mode(context, 'OBJECT')
                bpy.ops.object.mode_set(mode='EDIT')
            except Exception:
                # If we can't enter edit mode, skip this armature
                logger.warning("Could not enter edit mode for armature '%s'", arm_obj.name)
                if prev_active:
                    context.view_layer.objects.active = prev_active
                continue

            removed_this_arm = 0
            ebones = arm_obj.data.edit_bones

            # Build a set of bone names to keep: any bone that is directly used
            # and all of its ancestors (parents) must be preserved.
            keep_names = set(used_bones)
            bones_ref = arm_obj.data.bones
            for name in list(used_bones):
                try:
                    b = bones_ref.get(name)
                    # Walk parent chain; use a tight loop and local variables
                    while b is not None and b.parent is not None:
                        b = b.parent
                        if b.name in keep_names:
                            break
                        keep_names.add(b.name)
                except Exception:
                    # Defensive: if parent traversal fails for any bone, ignore
                    pass

            # Collect bones to remove (those not in keep_names)
            to_remove = [b for b in list(ebones) if b.name not in keep_names]

            for eb in to_remove:
                try:
                    ebones.remove(eb)
                    removed_this_arm += 1
                except Exception:
                    # Some bones may not be removable in certain situations; ignore
                    pass

            # Return to object mode and restore previous active object
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

            if prev_active and prev_active.name in bpy.data.objects:
                context.view_layer.objects.active = prev_active

            total_removed += removed_this_arm
            if removed_this_arm > 0:
                logger.info("Armature '%s': removed %d unused bone(s)", arm_obj.name, removed_this_arm)

        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} unused bone(s) from armature(s)")
        else:
            self.report({'INFO'}, "No unused bones found on selected armature(s)")

        return {'FINISHED'}