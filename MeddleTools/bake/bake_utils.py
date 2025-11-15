import bpy
import math
import os

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

def get_uv_islands(mesh, full_island_detection=False):
    visited = set()
    islands = []
    

    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        return []
    
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
    
    def build_uv_adjacency_full():
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
    
    adjacency = build_uv_adjacency_full() if full_island_detection else build_uv_adjacency()
    
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

def calculate_bake_margin(image_size):
    """Calculate bake margin based on image size (0.78125% of max dimension)"""
    return int(math.ceil(0.0078125 * max(image_size)))

def create_bake_image(name, width, height, background_color=(0.0, 0.0, 0.0, 1.0), alpha_mode='STRAIGHT', colorspace='sRGB'):
    """Create a new image for baking with proper settings
    
    Args:
        name: Name of the image
        width: Width in pixels
        height: Height in pixels
        background_color: RGBA tuple for background color
        alpha_mode: 'STRAIGHT', 'CHANNEL_PACKED', or 'NONE'
        colorspace: 'sRGB' or 'Non-Color'
    
    Returns:
        The created image
    """
    # Remove existing image with same name
    if name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[name])
    
    image = bpy.data.images.new(
        name=name,
        width=width,
        height=height,
        alpha=True
    )
    image.generated_color = background_color
    image.alpha_mode = alpha_mode
    image.colorspace_settings.name = colorspace
    
    # Set filepath relative to blend file
    blend_filepath = bpy.data.filepath
    blend_dir = os.path.dirname(blend_filepath)
    image.filepath = os.path.join(blend_dir, "Bake", f"{name}.png")
    
    return image

def disconnect_bsdf_inputs(material, required_inputs):
    """Disconnect all BSDF inputs except those in required_inputs list
    
    Args:
        material: The material to process
        required_inputs: List of input socket names to keep connected
    
    Returns:
        List of tuples (input_socket, from_node, from_socket) for reconnecting later
    """
    disconnect_inputs = []
    
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            for input_socket in node.inputs:
                if input_socket.name not in required_inputs:
                    # Disconnect
                    for link in input_socket.links:
                        from_node = link.from_node
                        from_socket = link.from_socket
                        disconnect_inputs.append((input_socket, from_node, from_socket))
                        material.node_tree.links.remove(link)
    
    return disconnect_inputs

def reconnect_inputs(disconnect_inputs):
    """Reconnect previously disconnected inputs
    
    Args:
        disconnect_inputs: List of tuples (input_socket, from_node, from_socket)
    """
    for input_socket, from_node, from_socket in disconnect_inputs:
        input_socket.id_data.links.new(from_socket, input_socket)

def setup_bake_settings(context, bake_type, pass_filter, bake_margin, samples=32, use_clear=True):
    """Setup Cycles bake settings
    
    Args:
        context: Blender context
        bake_type: Bake type string ('DIFFUSE', 'NORMAL', 'ROUGHNESS', etc.)
        pass_filter: Set of pass filters ('COLOR', 'DIRECT', 'INDIRECT', etc.)
        bake_margin: Margin in pixels
        samples: Number of samples for baking
        use_clear: Whether to clear the image before baking
    """
    context.scene.render.engine = 'CYCLES'
    context.scene.cycles.bake_type = bake_type
    context.scene.cycles.use_denoising = False
    context.scene.render.bake.use_pass_direct = "DIRECT" in pass_filter
    context.scene.render.bake.use_pass_indirect = "INDIRECT" in pass_filter
    context.scene.render.bake.use_pass_color = "COLOR" in pass_filter
    context.scene.render.bake.use_pass_diffuse = "DIFFUSE" in pass_filter
    context.scene.render.bake.use_pass_emit = "EMIT" in pass_filter
    context.scene.render.bake.target = "IMAGE_TEXTURES"
    context.scene.cycles.samples = samples
    context.scene.render.bake.margin = bake_margin
    context.scene.render.image_settings.color_mode = 'RGB'
    context.scene.render.bake.use_clear = use_clear
    context.scene.render.bake.use_selected_to_active = False
    context.scene.render.bake.normal_space = 'TANGENT'

def get_bake_pass_config(pass_name):
    """Get baking configuration for a specific pass
    
    Args:
        pass_name: Name of the pass ('diffuse', 'normal', 'roughness')
    
    Returns:
        Dictionary with bake_type, background_color, pass_filter, required_inputs, alpha_mode, colorspace
    """
    configs = {
        'diffuse': {
            'bake_type': 'DIFFUSE',
            'background_color': (0.0, 0.0, 0.0, 1.0),
            'pass_filter': {'COLOR'},
            'required_inputs': ['Base Color', 'Alpha'],
            'alpha_mode': 'CHANNEL_PACKED',
            'colorspace': 'sRGB'
        },
        'normal': {
            'bake_type': 'NORMAL',
            'background_color': (0.5, 0.5, 1.0, 1.0),
            'pass_filter': set(),
            'required_inputs': ['Normal'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'Non-Color'
        },
        'roughness': {
            'bake_type': 'ROUGHNESS',
            'background_color': (0.5, 0.5, 0.5, 1.0),
            'pass_filter': set(),
            'required_inputs': ['Roughness', 'Metallic'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'Non-Color'
        },
        'ior': {
            'bake_type': 'EMIT',
            'background_color': (0.0, 0.0, 0.0, 1.0),  # Represents IOR of 1.0 after remapping
            'pass_filter': {'EMIT'},
            'required_inputs': ['IOR'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'Non-Color',
            'remap_to_emission': True  # Flag to remap IOR to Emission for baking
        }
    }
    
    return configs.get(pass_name.lower(), None)

def set_active_uv_layer(mesh, uv_layer_name):
    """Set the active UV layer on the mesh
    
    Args:
        mesh: The mesh object to set the UV layer on
        uv_layer_name: The name of the UV layer to set as active
        
    Returns:
        bool: True if successful, False otherwise
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if uv_layer_name in mesh.data.uv_layers:
        uv_layer = mesh.data.uv_layers[uv_layer_name]
        mesh.data.uv_layers.active = uv_layer
        uv_layer.active_render = True
        logger.info(f"Set active UV layer to {uv_layer_name} on mesh {mesh.name}")
        return True
    else:
        logger.warning(f"UV layer {uv_layer_name} not found on mesh {mesh.name}")
        return False