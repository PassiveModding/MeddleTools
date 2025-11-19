import bpy
import math
import os
import numpy as np

def is_in_bake_collection(obj):
    """Check if the object is in a bake collection (name starts with 'BAKE_')"""
    for collection in obj.users_collection:
        if collection.name.startswith("BAKE_"):
            return True
    return False

def get_mat_settings_by_name(settings, material_name):
    """Get material bake settings by material name"""
    for mat_setting in settings.material_bake_settings:
        if mat_setting.material_name == material_name:
            return mat_setting
    return None

def determine_largest_image_size(material):
    """Determine the largest image size used in a material's texture nodes"""
    if not material or not material.use_nodes:
        return (2048, 2048)
    
    max_width = 0
    max_height = 0
    for node in material.node_tree.nodes:
        # skip _array images
        if node.type == 'TEX_IMAGE' and node.image and "_array" not in node.image.name:
            max_width = max(max_width, node.image.size[0])
            max_height = max(max_height, node.image.size[1])
    
    if max_width == 0 or max_height == 0:
        max_width = 1024
        max_height = 1024
        
    max_dimension = max(max_width, max_height)
    
    return (max_dimension, max_dimension) # want to keep square sizes for baking

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

def calculate_bake_margin(image_size):
    """Calculate bake margin based on image size (0.78125% of max dimension)"""
    # min size of 4 pixels
    return max(4, int(math.ceil(0.0078125 * max(image_size))))

def create_bake_image(name, width, height, background_color=(0.0, 0.0, 0.0, 1.0), alpha_mode='STRAIGHT', colorspace='sRGB'):
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
        pass_name: Name of the pass ('diffuse', 'normal', 'roughness', 'metalness')
    
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
        'metalness': {
            'bake_type': 'EMIT',
            'background_color': (0.0, 0.0, 0.0, 1.0),
            'pass_filter': set(),
            'required_inputs': ['Metallic'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'Non-Color',
            'custom_mapping': 'EmissionStrength'
        },
        'ior': {
            'bake_type': 'EMIT',
            'background_color': (1.0, 1.0, 1.0, 1.0),
            'pass_filter': set(),
            'required_inputs': ['IOR'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'Non-Color',
            'custom_mapping': 'IORToEmissionStrength'
        },
        'emission': {
            'bake_type': 'EMIT',
            'background_color': (0.0, 0.0, 0.0, 1.0),
            'pass_filter': set(),
            'required_inputs': ['Emission Color', 'Emission Strength'],
            'alpha_mode': 'STRAIGHT',
            'colorspace': 'sRGB'
        }
    }
    
    return configs.get(pass_name.lower(), None)

def get_bake_material_config(context=None) -> dict:
    """Get configuration for baking materials
    
    Args:
        context: Blender context (optional) - if provided, filters passes based on user settings
    
    Returns:
        Dictionary with bake passes and material setup configuration
    """
    # All available bake passes
    all_passes = ['diffuse', 'normal', 'roughness', 'metalness', 'ior', 'emission']
    
    # Filter passes based on user settings if context is provided
    if context:
        settings = context.scene.meddle_settings
        enabled_passes = []
        if settings.bake_diffuse:
            enabled_passes.append('diffuse')
        if settings.bake_normal:
            enabled_passes.append('normal')
        if settings.bake_roughness:
            enabled_passes.append('roughness')
        if settings.bake_metalness:
            enabled_passes.append('metalness')
        if settings.bake_ior:
            enabled_passes.append('ior')
        if settings.bake_emission:
            enabled_passes.append('emission')
        bake_passes = enabled_passes
    else:
        bake_passes = all_passes
    
    return {
        # Bake passes to execute in order
        'bake_passes': bake_passes,
        
        # Material node connections after baking
        # Format: (from_node_key, from_output, to_node_key, to_input)
        'node_connections': [
            ('diffuse', 'Color', 'bsdf', 'Base Color'),
            ('diffuse', 'Alpha', 'bsdf', 'Alpha'),
            ('roughness', 'Color', 'bsdf', 'Roughness'),
            ('metalness', 'Color', 'bsdf', 'Metallic'),
            ('normal', 'Color', 'normal_map', 'Color'),
            ('normal_map', 'Normal', 'bsdf', 'Normal'),
            ('bsdf', 'BSDF', 'output', 'Surface'),
            ('ior', 'Color', 'ior_math', 'Value'),
            ('ior_math', 'Value', 'bsdf', 'IOR'),
            ('emission', 'Color', 'bsdf', 'Emission Color'),
            ('emission', 'Alpha', 'bsdf', 'Emission Strength'),
        ],
        
        # Special nodes needed for baked material
        'special_nodes': {
            'normal_map': {
                'type': 'ShaderNodeNormalMap',
                'location_offset': (-300, -200),  # Relative to bsdf node
                'requires_pass': 'normal'  # Only create if this pass is enabled
            },
            'ior_math': {
                'type': 'ShaderNodeMath',
                'location_offset': (-300, -700),  # Relative to bsdf node
                'operation': 'ADD',
                'inputs': {1: 1.0},  # Add 1.0 to remap 0-1 back to 1-2
                'requires_pass': 'ior'  # Only create if this pass is enabled
            }
        },

        # BSDF node default inputs
        'bsdf_defaults': {
            'IOR': 1.2,
            'Metallic': 0.0,
            'Roughness': 0.5,
            'Base Color': (1.0, 1.0, 1.0, 1.0),
            'Emission Color': (1.0, 1.0, 1.0, 1.0),
            'Emission Strength': 0.0
        }
    }

def get_atlas_config(context=None) -> dict:
    """Get configuration for atlas creation
    
    Args:
        context: Blender context (optional) - if provided, filters texture types based on user settings
    
    Returns:
        Dictionary with texture_types, socket_mapping, material setup and other atlas settings
    """
    # All available texture types
    all_texture_types = ['diffuse', 'normal', 'roughness', 'metalness', 'ior', 'emission']
    
    # Filter texture types based on user settings if context is provided
    if context:
        settings = context.scene.meddle_settings
        enabled_types = []
        if settings.bake_diffuse:
            enabled_types.append('diffuse')
        if settings.bake_normal:
            enabled_types.append('normal')
        if settings.bake_roughness:
            enabled_types.append('roughness')
        if settings.bake_metalness:
            enabled_types.append('metalness')
        if settings.bake_ior:
            enabled_types.append('ior')
        if settings.bake_emission:
            enabled_types.append('emission')
        texture_types = enabled_types
    else:
        texture_types = all_texture_types
    
    return {
        'texture_types': texture_types,

        # Socket mapping for finding textures by connection
        'socket_mapping': {
            'diffuse': 'Base Color',
            'roughness': 'Roughness',
            'metalness': 'Metallic',
            'alpha': 'Alpha',
            'ior': 'IOR',
            'emission': 'Emission Color'
        },
        
        # Texture node configurations for atlas material setup
        'texture_node_configs': [
            ('diffuse', (-400, 300), 'Atlas Diffuse'),
            ('normal', (-400, 0), 'Atlas Normal'),
            ('roughness', (-400, -300), 'Atlas Roughness'),
            ('metalness', (-400, -600), 'Atlas Metalness'),
            ('ior', (-400, -900), 'Atlas IOR'),
            ('emission', (-400, -1200), 'Atlas Emission')
        ],
        
        # Node connections for atlas material
        # Format: (from_node_key, from_output, to_node_key, to_input)
        'node_connections': [
            ('diffuse', 'Color', 'bsdf', 'Base Color'),
            ('diffuse', 'Alpha', 'bsdf', 'Alpha'),
            ('roughness', 'Color', 'bsdf', 'Roughness'),
            ('metalness', 'Color', 'bsdf', 'Metallic'),
            ('normal', 'Color', 'normal_map', 'Color'),
            ('normal_map', 'Normal', 'bsdf', 'Normal'),
            ('bsdf', 'BSDF', 'output', 'Surface'),
            ('ior', 'Color', 'ior_math', 'Value'),
            ('ior_math', 'Value', 'bsdf', 'IOR'),
            ('emission', 'Color', 'bsdf', 'Emission Color'),
            ('emission', 'Alpha', 'bsdf', 'Emission Strength')
        ],
        
        # Special node setup
        'special_nodes': {
            'normal_map': {
                'type': 'ShaderNodeNormalMap',
                'location': (-100, -100),
                'requires_texture': 'normal'  # Only create if this texture type is available
            },
            'ior_math': {
                'type': 'ShaderNodeMath',
                'location': (-100, -700),
                'operation': 'ADD',
                'inputs': {1: 1.0},  # Add 1.0 to remap 0-1 back to 1-2
                'requires_texture': 'ior'  # Only create if this texture type is available
            },
            'bsdf': {
                'type': 'ShaderNodeBsdfPrincipled',
                'location': (0, 0),
                'inputs': {
                    'IOR': 1.2,
                    'Metallic': 0.0
                }
            },
            'output': {
                'type': 'ShaderNodeOutputMaterial',
                'location': (400, 0)
            }
        }
    }

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
    
    
def img_as_nparray(image):
    """Convert Blender image to numpy array (H, W, 4)"""
    pixel_buffer = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
    image.pixels.foreach_get(pixel_buffer)
    return pixel_buffer.reshape(image.size[1], image.size[0], 4)


def nparray_to_img(image, nparr):
    """Write numpy array (H, W, 4) to Blender image"""
    assert nparr.shape == (image.size[1], image.size[0], 4)
    image.pixels.foreach_set(nparr.ravel())


def find_texture_in_material(material, tex_type):
    if not material.use_nodes:
        return None
    
    # First try to find by name
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            node_name_lower = node.image.name.lower()
            if f"bake_{tex_type}" in node_name_lower or f"_{tex_type}" in node_name_lower:
                return node.image
    
    # Then try to find by socket connections using config
    atlas_config = get_atlas_config()
    socket_mapping = atlas_config['socket_mapping']
    links = material.node_tree.links
    
    if tex_type in socket_mapping:
        for node in material.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            if any(l.to_socket.name == socket_mapping[tex_type] and l.from_node == node for l in links):
                return node.image
    elif tex_type == 'normal':
        for node in material.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            if any(l.to_node.type == 'NORMAL_MAP' and l.from_node == node for l in links):
                return node.image
    
    return None