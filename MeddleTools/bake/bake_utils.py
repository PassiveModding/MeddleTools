import bpy
    
def require_mesh_or_armature_selected(context):
    """Check if operation can be executed"""
    # Require at least one mesh or armature selected
    return any(obj.type in {'MESH', 'ARMATURE'} for obj in context.selected_objects)

def get_selected_armatures(context):
    """Get selected armature objects"""
    return [obj for obj in context.selected_objects if obj.type == 'ARMATURE']

def get_selected_meshes(context):
    """Get selected mesh objects"""
    return [obj for obj in context.selected_objects if obj.type == 'MESH']

def get_all_selected_meshes(context):
    """Get all selected mesh objects, including those parented to selected armatures"""
    selected_armatures = get_selected_armatures(context)
    selected_meshes = get_selected_meshes(context)
    
    # Include meshes parented to selected armatures
    for armature in selected_armatures:
        for child in armature.children:
            if child.type == 'MESH' and child not in selected_meshes:
                selected_meshes.append(child)
    
    return selected_meshes

def get_uv_islands(mesh):
    visited = set()
    islands = []
    
    # Build adjacency map based on UV edges
    # Two loops are connected if they share an edge with matching UVs
    # def build_uv_adjacency():
    #     adjacency = {}
    #     for poly in mesh.polygons:
    #         loop_indices = list(poly.loop_indices)
    #         for i, li in enumerate(loop_indices):
    #             next_li = loop_indices[(i + 1) % len(loop_indices)]
    #             if li not in adjacency:
    #                 adjacency[li] = []
    #             if next_li not in adjacency:
    #                 adjacency[next_li] = []
    #             adjacency[li].append(next_li)
    #             adjacency[next_li].append(li)
    #     return adjacency
    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        return []
    
    def build_uv_adjacency():
        # Map UV coordinates to loop indices
        uv_to_loops = {}
        for loop_index, uv in enumerate(uv_layer.data):
            uv_coord = (round(uv.uv.x, 6), round(uv.uv.y, 6))  # Round to handle float precision
            if uv_coord not in uv_to_loops:
                uv_to_loops[uv_coord] = []
            uv_to_loops[uv_coord].append(loop_index)
        
        # Build adjacency based on shared UV coordinates
        adjacency = {}
        for loops in uv_to_loops.values():
            for li in loops:
                if li not in adjacency:
                    adjacency[li] = []
                # Connect all loops that share this UV coordinate
                adjacency[li].extend([other_li for other_li in loops if other_li != li])
        
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
                
    return islands