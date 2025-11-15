import bpy
from bpy.types import Operator
import logging
from . import bake_utils

# Module logger
logger = logging.getLogger(__name__)

def get_join_label(context):
    """Get dynamic label for JoinMeshes operator based on selection"""
    selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
    mesh_count = len(selected_meshes)
    
    if mesh_count == 0:
        return "Join Meshes (No meshes selected)"
    elif mesh_count == 1:
        return "Join Meshes (1 mesh - nothing to join)"
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
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        return len(selected_meshes) >= 2
    
    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if len(selected_meshes) < 2:
            self.report({'ERROR'}, "Select at least 2 mesh objects to join")
            return {'CANCELLED'}
        
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
        
        # Restore the common UV layer name as active on the joined mesh
        bake_utils.set_active_uv_layer(joined_mesh, common_uv_name)
        
        logger.info(f"Meshes joined into: {joined_mesh.name}")
        self.report({'INFO'}, f"Successfully joined into {joined_mesh.name}")
        
        return {'FINISHED'}
