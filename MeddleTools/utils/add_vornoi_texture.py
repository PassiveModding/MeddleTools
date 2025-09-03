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

class AddVoronoiTexture(Operator):
    """Add voronoi texture setup for background objects"""
    bl_idname = "meddle.add_voronoi_texture"
    bl_label = "Apply Terrain Voronoi"
    bl_description = "Add voronoi texture setup for selected terrain objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        processed_count = 0
        
        # Apply voronoi to all selected objects
        for obj in context.selected_objects:
            if obj is None or obj.type != 'MESH':
                continue
            
            # Get the material slots
            for slot in obj.material_slots:
                if slot.material is not None:
                    result = self.add_voronoi_texture(slot.material)
                    if result == {'FINISHED'}:
                        processed_count += 1
        
        if processed_count > 0:
            self.report({'INFO'}, f"Applied Voronoi texture to {processed_count} materials")
        else:
            self.report({'WARNING'}, "No materials processed (no selected mesh objects or materials already have Voronoi)")
                    
        return {'FINISHED'}
    
    def add_voronoi_texture(self, mat):
        """Add voronoi texture setup to a material"""
        if mat is None or not mat.use_nodes:
            return {'CANCELLED'}
        
        # If already has voronoi texture, do nothing
        if any(node.type == 'TEX_VORONOI' for node in mat.node_tree.nodes):
            logger.info("Material %s already has a voronoi texture.", mat.name)
            return {'CANCELLED'}
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Create nodes
        uvMapNode = nodes.new('ShaderNodeUVMap')
        uvMapNode.uv_map = 'UVMap'
        uvMapNode.location = (-500, 0)
        
        voronoiTexture = nodes.new('ShaderNodeTexVoronoi')
        voronoiTexture.location = (-300, 0)
        
        vectorMapping = nodes.new('ShaderNodeMapping')
        vectorMapping.location = (0, 0)
        
        # Link the nodes
        links.new(uvMapNode.outputs['UV'], vectorMapping.inputs['Vector'])
        links.new(uvMapNode.outputs['UV'], voronoiTexture.inputs['Vector'])
        links.new(voronoiTexture.outputs['Color'], vectorMapping.inputs['Rotation'])
        
        # Get texture nodes for the material
        textureNodes = [node for node in nodes if node.type == 'TEX_IMAGE']
        
        # Link the voronoi texture to the texture nodes
        for texNode in textureNodes:
            if texNode is None:
                continue
            
            # Check if the texture node has an input for vector
            if 'Vector' in texNode.inputs:
                links.new(vectorMapping.outputs['Vector'], texNode.inputs['Vector'])
            else:
                logger.warning("Texture node %s does not have a Vector input.", texNode.name)
        
        return {'FINISHED'}