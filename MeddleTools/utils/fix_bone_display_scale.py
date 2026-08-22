import bpy
import statistics
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


def fix_oversized_bone_display(armatures, context, threshold_multiplier=3.0, target_multiplier=1.5):
    """Scale down bones whose length is disproportionately large compared to the
    rest of the armature.

    glTF has no concept of bone length, so Blender has to guess head/tail
    positions on import, sometimes which are overly large.

    Returns the total number of bones scaled down.
    """
    total_fixed = 0

    for arm_obj in armatures:
        if arm_obj is None or arm_obj.type != 'ARMATURE':
            continue

        prev_active = context.view_layer.objects.active
        try:
            context.view_layer.objects.active = arm_obj
            helpers.ensure_object_mode(context, 'OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
        except Exception:
            logger.warning("Could not enter edit mode for armature '%s'", arm_obj.name)
            if prev_active:
                context.view_layer.objects.active = prev_active
            continue

        ebones = arm_obj.data.edit_bones
        lengths = [b.length for b in ebones if b.length > 1e-6]

        fixed_this_arm = 0
        if len(lengths) >= 2:
            median_length = statistics.median(lengths)
            threshold = median_length * threshold_multiplier
            target_length = median_length * target_multiplier

            for b in ebones:
                if b.length <= threshold:
                    continue
                factor = target_length / b.length
                direction = b.tail - b.head
                b.tail = b.head + direction * factor
                fixed_this_arm += 1

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        if prev_active and prev_active.name in bpy.data.objects:
            context.view_layer.objects.active = prev_active

        total_fixed += fixed_this_arm
        if fixed_this_arm > 0:
            logger.info("Armature '%s': scaled down %d oversized bone(s)", arm_obj.name, fixed_this_arm)

    return total_fixed


class FixOversizedBones(Operator):
    """Scale down bones that render oversized"""

    bl_idname = "meddle.fix_oversized_bones"
    bl_label = "Fix Oversized Bone Display"
    bl_description = (
        "Scale down bones that are disproportionately long compared to the rest of the "
        "armature. Does not affect deformation"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
        if not armatures and context.active_object and context.active_object.type == 'ARMATURE':
            armatures = [context.active_object]

        if not armatures:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}

        props = context.scene.meddle_settings
        total_fixed = fix_oversized_bone_display(
            armatures,
            context,
            threshold_multiplier=props.bone_oversized_threshold,
            target_multiplier=props.bone_oversized_target,
        )

        if total_fixed > 0:
            self.report({'INFO'}, f"Scaled down {total_fixed} oversized bone(s)")
        else:
            self.report({'INFO'}, "No oversized bones found on selected armature(s)")

        return {'FINISHED'}
