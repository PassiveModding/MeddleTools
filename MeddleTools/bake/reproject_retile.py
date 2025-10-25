import bpy
import logging
from bpy.types import Operator
import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ReprojectRetile(Operator):
    """Fixes uvs which sit outside the 0-1 range by updating uvs AND textures to fit within 0-1"""
    bl_idname = "meddle.reproject_retile"
    bl_label = "Reproject and Retile"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        
        meshes = []
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            meshes.append(obj)
            
            
        for obj in meshes:
            self.handle_uv_islands(obj)          
            
            mesh = obj.data
            mesh.update()
            
            
        self.report({'INFO'}, "Reproject and Retile completed")
        return {'FINISHED'}
    
    def handle_uv_islands(self, obj):
        mesh = obj.data
        if not mesh.uv_layers:
            return
        uv_layer = mesh.uv_layers.active.data
        
        visited = set()
        islands = []
        
        # Build adjacency map based on UV edges
        # Two loops are connected if they share an edge with matching UVs
        def build_uv_adjacency():
            adjacency = {}
            for poly in mesh.polygons:
                loop_indices = list(poly.loop_indices)
                for i, li in enumerate(loop_indices):
                    next_li = loop_indices[(i + 1) % len(loop_indices)]
                    if li not in adjacency:
                        adjacency[li] = []
                    if next_li not in adjacency:
                        adjacency[next_li] = []
                    adjacency[li].append(next_li)
                    adjacency[next_li].append(li)
            return adjacency
        
        adjacency = build_uv_adjacency()
        
        def get_connected_loops(start_loop_index):
            to_visit = [start_loop_index]
            island_loops = set()
            while to_visit:
                loop_index = to_visit.pop()
                if loop_index in visited:
                    continue
                visited.add(loop_index)
                island_loops.add(loop_index)
                
                # Add adjacent loops (within same polygon)
                if loop_index in adjacency:
                    for adjacent_li in adjacency[loop_index]:
                        if adjacent_li not in visited:
                            to_visit.append(adjacent_li)
            return island_loops
        
        # Find all islands
        for poly in mesh.polygons:
            for loop_index in poly.loop_indices:
                if loop_index not in visited:
                    island_loops = get_connected_loops(loop_index)
                    islands.append(island_loops)
        
        # Process each island
        for island in islands:
            uv_coords = np.array([uv_layer[li].uv for li in island])
            uv_min = uv_coords.min(axis=0)
            uv_max = uv_coords.max(axis=0)
            
            # Check if the island is fully outside 0-1 range
            if (uv_max[0] < 0.0 or uv_min[0] > 1.0 or uv_max[1] < 0.0 or uv_min[1] > 1.0):
                # Calculate tile offset to bring island back into 0-1 range
                # Use floor to get the tile index, then translate the entire island
                offset_x = np.floor(uv_min[0]) if uv_max[0] < 0.0 else np.floor(uv_min[0])
                offset_y = np.floor(uv_min[1]) if uv_max[1] < 0.0 else np.floor(uv_min[1])
                
                # Apply offset to entire island (maintains relative positions)
                for li in island:
                    uv = uv_layer[li].uv
                    uv_layer[li].uv = (uv[0] - offset_x, uv[1] - offset_y)
            