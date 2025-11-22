import bpy
from bpy.types import Operator
import logging
from . import bake_utils

# Module logger
logger = logging.getLogger(__name__)

def get_join_label(context):
    """Get dynamic label for JoinMeshes operator based on selection"""
    mesh_objects = bake_utils.get_all_selected_meshes(context)
    mesh_count = len(mesh_objects)
    
    if mesh_count == 0:
        return "Join Meshes (No meshes selected)"
    elif mesh_count == 1:
        return "Join Meshes (1 mesh)"
    else:
        return f"Join Meshes ({mesh_count} meshes)"

class JoinMeshes(Operator):
    """Join all selected mesh objects into a single mesh"""
    bl_idname = "meddle.join_meshes"
    bl_label = "Join Meshes"
    bl_description = "Join all selected mesh objects into a single mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Require at least 2 mesh objects selected
        mesh_or_armature_selected = bake_utils.require_mesh_or_armature_selected(context)
        selected_meshes = bake_utils.get_all_selected_meshes(context)
        return mesh_or_armature_selected and len(selected_meshes) >= 2
    
    def execute(self, context):
        armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
        selected_meshes = bake_utils.get_all_selected_meshes(context)
        
        logger.info(f"Joining {len(selected_meshes)} meshes into one")
        self.report({'INFO'}, f"Joining {len(selected_meshes)} mesh(es) into one...")
        
        # Store and rename active UV layers to a common name before joining
        common_uv_name = "MEDDLE_ACTIVE_UV"
        uv_renames = []  # Store (mesh, original_name, uv_layer) for restoration
        
        for mesh in selected_meshes:
            if mesh.data.uv_layers:
                active_uv = mesh.data.uv_layers.active
                if active_uv:
                    original_name = active_uv.name
                    uv_renames.append((mesh, original_name, active_uv))
                    active_uv.name = common_uv_name
                    logger.info(f"Renamed UV layer '{original_name}' to '{common_uv_name}' on mesh '{mesh.name}'")
        
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all mesh objects
        for mesh in selected_meshes:
            mesh.select_set(True)
        
        # Set the first mesh as active
        context.view_layer.objects.active = selected_meshes[0]
        
        # Join the meshes
        bpy.ops.object.join()
        
        joined_mesh = context.view_layer.objects.active
        

        bake_utils.set_active_uv_layer(joined_mesh, common_uv_name)
        
        # remove all other UV layers except the active one
        uv_layer_names = [uv.name for uv in joined_mesh.data.uv_layers]
        for uv_name in uv_layer_names:
            if uv_name != common_uv_name:
                joined_mesh.data.uv_layers.remove(joined_mesh.data.uv_layers[uv_name])
                logger.info(f"Removed UV layer '{uv_name}' from joined mesh '{joined_mesh.name}'")
        
        logger.info(f"Meshes joined into: {joined_mesh.name}")
        self.report({'INFO'}, f"Successfully joined into {joined_mesh.name}")
        
        # re-select armature if it exists
        if armature:
            armature.select_set(True)
            context.view_layer.objects.active = armature
        
        return {'FINISHED'}
