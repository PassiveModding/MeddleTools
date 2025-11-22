import bpy
import logging
from bpy.types import Operator
from . import bake_utils

# Module logger
logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

def get_create_uv_label(context):
    """Get dynamic label for CreateUVBakeLayers operator based on selection"""
    mesh_objects = bake_utils.get_all_selected_meshes(context)
    mesh_count = len(mesh_objects)
    
    if mesh_count == 0:
        return "Create UV Bake Layers (No meshes selected)"
    elif mesh_count == 1:
        return "Create UV Bake Layers (1 mesh)"
    else:
        return f"Create UV Bake Layers ({mesh_count} meshes)"


class CreateUVBakeLayers(Operator):
    """Create packed UV layers for baking on selected meshes"""
    bl_idname = "meddle.create_uv_bake_layers"
    bl_label = "Create UV Bake Layers"
    bl_description = "Create new UV layers with packed islands for baking"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Ensure we have a mesh or armature selected
        mesh_or_armature_selected = bake_utils.require_mesh_or_armature_selected(context)
        # Check if at least one selected mesh lacks the packed UV layer
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        lacks_packed_uv = any("MeddlePackedUVs" not in mesh.data.uv_layers for mesh in mesh_objects)
        return mesh_or_armature_selected and lacks_packed_uv
    
    def execute(self, context):
        try:
            mesh_objects = bake_utils.get_all_selected_meshes(context)
            
            if not mesh_objects:
                self.report({'ERROR'}, "No mesh objects selected.")
                return {'CANCELLED'}
            
            total_meshes = len(mesh_objects)
            success_count = 0
            
            for i, mesh in enumerate(mesh_objects):
                self.report({'INFO'}, f"Processing mesh {i+1}/{total_meshes}: {mesh.name}")
                
                # Ensure UV layer exists
                if "UVMap" not in mesh.data.uv_layers:
                    self.report({'WARNING'}, f"  Mesh {mesh.name} has no UVMap, skipping...")
                    continue
                
                if "MeddlePackedUVs" in mesh.data.uv_layers:
                    self.report({'INFO'}, f"  Mesh {mesh.name} already has MeddlePackedUVs, skipping...")
                    success_count += 1
                    continue
                
                # Pack UV islands into new layer
                if self.pack_uv_islands(mesh, "UVMap", "MeddlePackedUVs"):
                    success_count += 1
                    logger.info(f"Created packed UV layer for {mesh.name}")
                else:
                    self.report({'ERROR'}, f"  Failed to create packed UV layer for {mesh.name}")
            
            if success_count > 0:
                self.report({'INFO'}, f"Created packed UV layers for {success_count}/{total_meshes} mesh(es)")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to create packed UV layers for any meshes")
                return {'CANCELLED'}
                
        except Exception as e:
            logger.error(f"Failed to create UV bake layers: {e}")
            self.report({'ERROR'}, f"Failed to create UV bake layers: {str(e)}")
            return {'CANCELLED'}
    
    def pack_uv_islands(self, mesh, uv_layer_name, new_uv_layer_name):
        """Pack UV islands into a new UV layer"""
        # Ensure the specified UV layer exists
        if uv_layer_name not in mesh.data.uv_layers:
            logger.warning(f"UV layer {uv_layer_name} not found on mesh {mesh.name}")
            return False
        
        # Store current selection state
        original_selection = bpy.context.selected_objects[:]
        original_active = bpy.context.view_layer.objects.active
        
        # Ensure only the mesh is selected
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        
        # Create a new UV layer for packed UVs
        if new_uv_layer_name in mesh.data.uv_layers:
            # Remove existing packed UV layer
            mesh.data.uv_layers.remove(mesh.data.uv_layers[new_uv_layer_name])
        
        # Get the source UV layer
        source_uv_layer = mesh.data.uv_layers[uv_layer_name]
        
        # Create new UV layer and copy data from source
        packed_uv_layer = mesh.data.uv_layers.new(name=new_uv_layer_name)
        
        # Copy UV data from source layer to packed layer
        for loop_idx in range(len(mesh.data.loops)):
            packed_uv_layer.data[loop_idx].uv = source_uv_layer.data[loop_idx].uv.copy()
        
        # Set the new layer as active for packing
        mesh.data.uv_layers.active = packed_uv_layer
        
        # Pack UV islands
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.uv.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(
                udim_source='CLOSEST_UDIM',
                rotate=False,
                scale=True,
                merge_overlap=False,
                margin_method='SCALED',
                margin=0.001,
                pin=False,
                shape_method='CONCAVE'
            )
            bpy.ops.object.mode_set(mode='OBJECT')
            
            logger.info(f"Packed UV islands into layer {new_uv_layer_name} on mesh {mesh.name}")
            
            # Restore original selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = original_active
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to pack UV islands for {mesh.name}: {e}")
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Restore original selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = original_active
            
            return False


def register():
    bpy.utils.register_class(CreateUVBakeLayers)


def unregister():
    bpy.utils.unregister_class(CreateUVBakeLayers)
