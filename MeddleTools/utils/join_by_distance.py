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

class JoinByDistance(Operator):
    """Join meshes within selected objects by merging nearby vertices"""
    bl_idname = "meddle.join_by_distance"
    bl_label = "Join by Distance"
    bl_description = "Merge vertices within the specified distance for selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        merge_distance = context.scene.meddle_settings.merge_distance
        
        # Store the current mode and active object
        original_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
        original_active = bpy.context.view_layer.objects.active
        
        # Get selected mesh objects based on current mode
        if original_mode == 'EDIT':
            # In edit mode, work with the active object only
            if bpy.context.object and bpy.context.object.type == 'MESH':
                selected_objects = [bpy.context.object]
            else:
                self.report({'WARNING'}, "No mesh object in edit mode")
                return {'CANCELLED'}
        else:
            # In object mode, work with all selected mesh objects
            selected_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            
            if not selected_objects:
                self.report({'WARNING'}, "No mesh objects selected")
                return {'CANCELLED'}
        
        processed_count = 0
        
        for obj in selected_objects:
            # Set the object as active
            bpy.context.view_layer.objects.active = obj
            
            # Enter edit mode if not already in it
            if bpy.context.object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Select all vertices
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Merge by distance
            bpy.ops.mesh.remove_doubles(threshold=merge_distance)
            
            processed_count += 1
            logger.info("Processed object '%s' with merge distance %s", obj.name, merge_distance)
        
        # Restore original mode and active object
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=original_mode)
        
        if original_active:
            bpy.context.view_layer.objects.active = original_active
        
        self.report({'INFO'}, f"Processed {processed_count} objects with merge distance {merge_distance}")
        
        return {'FINISHED'}