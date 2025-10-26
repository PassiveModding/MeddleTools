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
    """Join meshes that share materials. Groups selected objects by material and joins each group"""
    bl_idname = "meddle.join_by_material"
    bl_label = "Join by Material"
    bl_description = "Join mesh objects that share materials. If multiple objects are selected, groups them by material and joins each group"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            # Ensure we're in object mode
            helpers.ensure_object_mode(context)
            
            # Get selected mesh objects
            selected_meshes = helpers.get_selected_meshes(context)
            if not selected_meshes:
                self.report({'ERROR'}, "No mesh objects selected")
                return {'CANCELLED'}
            
            # If only one object is selected, use the active material approach
            if len(selected_meshes) == 1:
                return self.join_by_active_material(context, selected_meshes[0])
            
            # Multiple objects selected - group by materials and join each group
            return self.join_multiple_by_materials(context, selected_meshes)
            
        except Exception as e:
            error_msg = f"Unexpected error in join by material: {str(e)}"
            self.report({'ERROR'}, error_msg)
            logger.error(error_msg)
            return {'CANCELLED'}
    
    def join_by_active_material(self, context, active_obj):
        """Join objects that share the active material of the given object"""
        # Get the active material
        if not active_obj.data.materials:
            self.report({'ERROR'}, "Active object has no materials")
            return {'CANCELLED'}
        
        # Get active material slot
        active_material_index = active_obj.active_material_index
        if active_material_index >= len(active_obj.data.materials):
            self.report({'ERROR'}, "Invalid active material index")
            return {'CANCELLED'}
        
        target_material = active_obj.data.materials[active_material_index]
        if not target_material:
            self.report({'ERROR'}, "Active material slot is empty")
            return {'CANCELLED'}
        
        # Find all mesh objects that use this material
        objects_to_join = []
        for obj in context.scene.objects:
            if (obj.type == 'MESH' and 
                obj != active_obj and 
                obj.data and 
                obj.data.materials):
                
                # Check if this object uses the target material
                if target_material in obj.data.materials:
                    objects_to_join.append(obj)
        
        if not objects_to_join:
            self.report({'INFO'}, f"No other objects found using material '{target_material.name}'")
            return {'FINISHED'}
        
        # Join the objects
        joined_count = self.perform_join(context, active_obj, objects_to_join)
        if joined_count >= 0:
            self.report({'INFO'}, f"Joined {joined_count} objects using material '{target_material.name}'")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}
    
    def join_multiple_by_materials(self, context, selected_meshes):
        """Group selected objects by materials and join each group"""
        # Build material groups from selected objects
        material_groups = {}
        
        for obj in selected_meshes:
            if not obj.data or not obj.data.materials:
                continue
                
            # Add object to groups for each material it uses
            for material in obj.data.materials:
                if material:  # Skip empty material slots
                    if material not in material_groups:
                        material_groups[material] = []
                    material_groups[material].append(obj)
        
        if not material_groups:
            self.report({'ERROR'}, "Selected objects have no materials")
            return {'CANCELLED'}
        
        # Filter groups to only include those with multiple objects
        joinable_groups = {mat: objs for mat, objs in material_groups.items() if len(objs) > 1}
        
        if not joinable_groups:
            self.report({'INFO'}, "No materials are shared between multiple selected objects")
            return {'FINISHED'}
        
        total_joined = 0
        groups_processed = 0
        
        # Process each material group
        for material, objects in joinable_groups.items():
            # Use the first object as the target (active object for this group)
            target_obj = objects[0]
            objects_to_join = objects[1:]
            
            joined_count = self.perform_join(context, target_obj, objects_to_join)
            if joined_count >= 0:
                total_joined += joined_count
                groups_processed += 1
                logger.info(f"Joined {joined_count} objects with material '{material.name}'")
        
        if groups_processed > 0:
            self.report({'INFO'}, f"Processed {groups_processed} material groups, joined {total_joined} objects total")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to join any material groups")
            return {'CANCELLED'}
    
    def perform_join(self, context, target_obj, objects_to_join):
        """Perform the actual join operation, returns number of objects joined or -1 on error"""
        try:
            # Store original transform of target object to preserve it
            original_location = target_obj.location.copy()
            original_rotation = target_obj.rotation_euler.copy()
            original_scale = target_obj.scale.copy()
            
            # Deselect all objects first
            helpers.safe_deselect_all_objects(context)
            
            # Apply transforms to objects being joined to prevent location issues
            for obj in objects_to_join:
                try:
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                    obj.select_set(False)
                except Exception as e:
                    logger.warning(f"Failed to apply transforms to {obj.name}: {e}")
                    # Continue anyway - join might still work
            
            # Select all objects for joining (target + objects to join)
            objects_to_select = [target_obj] + objects_to_join
            for obj in objects_to_select:
                try:
                    obj.select_set(True)
                except Exception:
                    continue
            
            # Set target object as active
            context.view_layer.objects.active = target_obj
            
            # Perform the join operation
            join_count = len(objects_to_join)
            bpy.ops.object.join()
            
            # Restore original transform of the target object
            target_obj.location = original_location
            target_obj.rotation_euler = original_rotation
            target_obj.scale = original_scale
            
            return join_count
            
        except Exception as e:
            error_msg = f"Failed to join objects: {str(e)}"
            self.report({'ERROR'}, error_msg)
            logger.error(error_msg)
            return -1