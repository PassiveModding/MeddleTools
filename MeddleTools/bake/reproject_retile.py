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
            
        # since we edit materials, quicker to do it in one pass than per object
        unique_materials = set()
        for obj in meshes:
            for mat_slot in obj.material_slots:
                if mat_slot.material:
                    unique_materials.add(mat_slot.material)

        material_to_object_map = {}
        for obj in meshes:
            for mat_slot in obj.material_slots:
                if mat_slot.material in unique_materials:
                    if mat_slot.material not in material_to_object_map:
                        material_to_object_map[mat_slot.material] = set()
                    material_to_object_map[mat_slot.material].add(obj)

        # if any object assigned to a material has uvs spanning an edge, we need to update all objects using that material that were selected
        objects_needing_material_update = set()
        materials_needing_update = set()
        for material, objs in material_to_object_map.items():
            needs_update = False
            for obj in objs:
                mesh = obj.data
                if not mesh.uv_layers:
                    continue
                # self.handle_uv_islands(obj)
                # mesh.update()
                uv_islands = self.get_uv_islands(mesh)
                for island in uv_islands:
                    uv_layer = mesh.uv_layers.active.data
                    uv_coords = np.array([uv_layer[li].uv for li in island])
                    uv_min_x = uv_coords.min(axis=0)[0]
                    uv_max_x = uv_coords.max(axis=0)[0]
                    uv_min_y = uv_coords.min(axis=0)[1]
                    uv_max_y = uv_coords.max(axis=0)[1]
                    # if floor of min != floor of max, it spans an edge
                    if np.floor(uv_min_x) != np.floor(uv_max_x) or np.floor(uv_min_y) != np.floor(uv_max_y):
                        needs_update = True
                        break
                if needs_update:
                    break
            if needs_update:
                for obj in objs:
                    objects_needing_material_update.add(obj)
                    for mat_slot in obj.material_slots:
                        materials_needing_update.add(mat_slot.material)
                        
        meshes_needing_uv_update = set()
        for obj in objects_needing_material_update:
            meshes_needing_uv_update.add(obj.data)

        for mesh in meshes_needing_uv_update:
            self.handle_uv_edges(mesh)
            mesh.update()

        # Process each unique material
        new_materials = {}
        for material in materials_needing_update:
            new_material = self.process_material(material)
            new_materials[material] = new_material
            
        # Apply new materials to objects
        for obj in meshes:
            for mat_slot in obj.material_slots:
                if mat_slot.material in new_materials:
                    mat_slot.material = new_materials[mat_slot.material]
                     
        self.report({'INFO'}, "Reproject and Retile completed")
        return {'FINISHED'}
    
    def handle_uv_islands(self, obj):
        mesh = obj.data
        if not mesh.uv_layers:
            return
        uv_layer = mesh.uv_layers.active.data
        islands = self.get_uv_islands(mesh)
        
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
          
    def get_uv_islands(self, mesh):
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
                    
        return islands

    def handle_uv_edges(self, mesh):       
        """Handle UV edges by tiling textures and adjusting UVs to fit within 0-1 range"""
        if not mesh.uv_layers:
            return

        logger.info(f"Handling UV edges for object: {mesh.name}")

        uv_layer = mesh.uv_layers.active.data
        islands = self.get_uv_islands(mesh)
        
        # Normalize UV islands to 0-2 range
        for island in islands:
            uv_coords = np.array([uv_layer[li].uv for li in island])
            uv_min = uv_coords.min(axis=0)
            uv_max = uv_coords.max(axis=0)
            
            # Calculate offset to bring island into 0-2 range
            offset_x = np.floor(uv_min[0])
            offset_y = np.floor(uv_min[1])
            
            # Apply offset to entire island
            if offset_x != 0 or offset_y != 0:
                for li in island:
                    uv = uv_layer[li].uv
                    uv_layer[li].uv = (uv[0] - offset_x, uv[1] - offset_y)
        
        # Check if any UVs are still outside 0-2 range after normalization
        all_uvs = np.array([uv_layer[li].uv for li in range(len(uv_layer))])
        if np.any(all_uvs < 0) or np.any(all_uvs > 2):
            logger.warning(f"Mesh {mesh.name}: Some UVs are outside 0-2 range after normalization. Min: {all_uvs.min(axis=0)}, Max: {all_uvs.max(axis=0)}")
        
        # Scale down all UVs to fit within 0-1 range
        for li in range(len(uv_layer)):
            uv = uv_layer[li].uv
            uv_layer[li].uv = (uv[0] / 2.0, uv[1] / 2.0)
    
    def process_material(self, source_material):
         # Create a copy of the material if not already a RETILE version
        material = source_material
        if not source_material.name.startswith("RETILE_"):
            new_material = source_material.copy()
            new_material.name = f"RETILE_{source_material.name}"
            material = new_material
        else:
            return material
        
        # Process all texture nodes in the material
        node_tree = material.node_tree
        texture_nodes = [node for node in node_tree.nodes if node.type == 'TEX_IMAGE']
        
        for tex_node in texture_nodes:
            if not tex_node.image:
                continue
            
            original_image = tex_node.image
            # if name contains _array skip
            if "_array" in original_image.name:
                continue
            # if image mode is not REPEAT skip
            if tex_node.extension == "REPEAT":            
                tiled_image_name = f"RETILE_2x2_{original_image.name}"
                
                # Check if tiled version already exists
                if tiled_image_name in bpy.data.images:
                    tex_node.image = bpy.data.images[tiled_image_name]
                    continue
                
                # Create 2x2 tiled version of the texture
                tiled_image = self.create_tiled_texture(original_image, tiled_image_name)
                if tiled_image:
                    tex_node.image = tiled_image
                    logger.info(f"Created tiled texture: {tiled_image_name}")
            else:
                logger.info(f"Skipping texture {original_image.name} with extension {tex_node.extension}")
                
        return material
    
    def create_tiled_texture(self, original_image, new_name):
        """Create a 2x2 tiled version of the input image"""
        if not original_image or not original_image.size[0] or not original_image.size[1]:
            logger.warning(f"Invalid image for tiling: {original_image.name if original_image else 'None'}")
            return None
        
        width = original_image.size[0]
        height = original_image.size[1]
        new_width = width * 2
        new_height = height * 2
        
        # Create new image
        new_image = bpy.data.images.new(new_name, width=new_width, height=new_height)
        
        # Reshape original pixels into (height, width, 4) array
        original_pixels = np.array(original_image.pixels[:], dtype=np.float32)
        original_pixels = original_pixels.reshape((height, width, 4))
        
        # Use np.tile to create 2x2 tiled version efficiently
        # tile((2, 2, 1)) means: repeat 2 times in height, 2 times in width, 1 time in channels
        new_pixels = np.tile(original_pixels, (2, 2, 1))
        
        # Assign pixels directly using foreach_set (much faster than list conversion)
        new_image.pixels.foreach_set(new_pixels.ravel())
        new_image.pack()
        
        # copy color space settings and alpha mode
        new_image.colorspace_settings.name = original_image.colorspace_settings.name
        new_image.alpha_mode = original_image.alpha_mode
        
        return new_image
        