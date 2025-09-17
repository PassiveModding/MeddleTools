import bpy
import logging
from bpy.types import Operator
from collections import defaultdict
from . import helpers

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class SetCyclesDefaults(Operator):
    """Set default settings for Cycles render engine."""
    bl_idname = "meddle.set_cycles_defaults"
    bl_label = "Set Cycles Defaults"
    bl_description = "Set default settings for Cycles render engine"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.context.scene.render.engine = 'CYCLES'
        cycles = bpy.context.scene.cycles
        cycles.device = 'GPU'
        cycles.preview_samples = 128
        cycles.samples = 256
        cycles.adaptive_threshold = 0.03
        cycles.use_fast_gi = True
        bpy.context.scene.render.use_simplify = True
        cycles.denoising_use_gpu = True

        return {'FINISHED'}

class SetCameraCulling(Operator):
    """Set default settings for Camera Culling."""
    bl_idname = "meddle.set_camera_culling"
    bl_label = "Set Camera Culling"
    bl_description = "Set default settings for Camera Culling"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Cycles
        bpy.context.scene.cycles.use_camera_cull = True
        bpy.context.scene.cycles.camera_cull_margin = 0.1
        
        # get all objects and enable cycles.use_camera_cull
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                obj.cycles.use_camera_cull = True

        return {'FINISHED'}