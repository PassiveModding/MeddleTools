import bpy
import logging
from bpy.types import Operator
import numpy as np
from . import bake_utils

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

def get_atlas_label(context):
    """Generate label for atlas operation based on selected meshes"""
    meshes = bake_utils.get_all_selected_meshes(context)
    distinct_materials = set()
    for mesh in meshes:
        for mat in mesh.data.materials:
            if mat:
                distinct_materials.add(mat.name)
    num_materials = len(distinct_materials)
    num_meshes = len(meshes)
    settings = context.scene.meddle_settings
    
    if num_materials == 0:
        return "Atlas & Join (No materials found)"
    elif num_materials == 1:
        return "Atlas & Join (No atlasing needed)"
    else:
        # Count unique groups assigned
        groups = set()
        for mat_name in distinct_materials:
            mat_setting = next((s for s in settings.material_bake_settings if s.material_name == mat_name), None)
            if mat_setting:
                groups.add(mat_setting.atlas_group if mat_setting.atlas_group > 0 else 0)
        
        num_groups = len(groups)
        if 0 in groups and num_groups > 1:
            return f"Atlas & Join ({num_materials} materials -> {num_groups-1}+ groups)"
        elif num_groups == 1 and 0 in groups:
            return f"Atlas & Join ({num_materials} materials -> individual atlases)"
        else:
            return f"Atlas & Join ({num_materials} materials -> {num_groups} groups)"

def is_valid_bake_material(mat):
    """Check if material is valid for atlasing (i.e. only contains compatible nodes)"""
    if not mat.use_nodes:
        return False
    
    ALLOWED_NODES = {'BSDF_PRINCIPLED', 'TEX_IMAGE', 'NORMAL_MAP', 'OUTPUT_MATERIAL', "MATH" }
    for node in mat.node_tree.nodes:
        if node.type not in ALLOWED_NODES:
            return False
        
    return True

class RunAtlas(Operator):
    """Combine meshes and create texture atlas to reach target material count"""
    bl_idname = "meddle.run_atlas"
    bl_label = "Atlas & Join Meshes"
    bl_description = "Join meshes and create texture atlases to reduce material count (1 material per mesh), assign using the G input in material settings"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        mesh_or_armature_selected = bake_utils.require_mesh_or_armature_selected(context)
        # Check if all materials are a bake material OR at least can function as one (i.e. only containing image, principled shader, etc.)
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        valid_materials = True
        material_count = 0
        for mesh in mesh_objects:
            for mat in mesh.data.materials:
                if mat and not is_valid_bake_material(mat):
                    valid_materials = False
                    break
                if mat:
                    material_count += 1
            if not valid_materials:
                break
            
        return mesh_or_armature_selected and valid_materials and material_count > 1
    
    def execute(self, context):
        meshes = bake_utils.get_all_selected_meshes(context)        
        if not meshes:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}
        
        settings = context.scene.meddle_settings
        
        # Get all materials from selected meshes
        all_materials = []
        mesh_by_material = {}  # Map material -> list of meshes using it
        
        for mesh in meshes:
            for mat in mesh.data.materials:
                if mat:
                    if mat not in mesh_by_material:
                        mesh_by_material[mat] = []
                        all_materials.append(mat)
                    if mesh not in mesh_by_material[mat]:
                        mesh_by_material[mat].append(mesh)
        
        num_materials = len(all_materials)
        logger.info(f"Found {num_materials} unique materials across {len(meshes)} meshes")
        
        if num_materials == 0:
            self.report({'ERROR'}, "No materials found on selected meshes")
            return {'CANCELLED'}
        
        # Group materials by their assigned atlas_group
        material_groups = self.group_materials_manually(all_materials, settings)
        logger.info(f"Manual grouping created {len(material_groups)} groups")
        
        # Check if atlasing is actually needed
        if len(material_groups) >= num_materials:
            self.report({'INFO'}, "All materials in separate groups, no atlasing needed")
            return {'CANCELLED'}
        
        # Process each group: collect meshes, join them, create atlas
        atlas_meshes = []
        for group_idx, material_group in enumerate(material_groups):
            logger.info(f"Processing group {group_idx + 1}/{len(material_groups)} with {len(material_group)} materials")
            
            # Collect all meshes that use materials in this group
            group_meshes = set()
            for mat in material_group:
                group_meshes.update(mesh_by_material[mat])
            
            group_meshes = list(group_meshes)
            logger.info(f"Group {group_idx} contains {len(group_meshes)} meshes")
            
            # Join meshes in this group
            if len(group_meshes) > 1:
                # Store and rename active UV layers to a common name before joining
                common_uv_name = "MEDDLE_ATLAS_UV"
                for mesh in group_meshes:
                    if mesh.data.uv_layers:
                        active_uv = mesh.data.uv_layers.active
                        if active_uv:
                            active_uv.name = common_uv_name
                            logger.info(f"Renamed UV layer to '{common_uv_name}' on mesh '{mesh.name}'")
                
                bpy.ops.object.select_all(action='DESELECT')
                for obj in group_meshes:
                    obj.select_set(True)
                
                context.view_layer.objects.active = group_meshes[0]
                bpy.ops.object.join()
                joined_mesh = context.view_layer.objects.active
                
                # Set the common UV layer as active on the joined mesh
                bake_utils.set_active_uv_layer(joined_mesh, common_uv_name)
            else:
                joined_mesh = group_meshes[0]
            
            if len(material_group) == 1:
                logger.info(f"Group {group_idx} has only one material, skipping atlasing")
                atlas_meshes.append(joined_mesh)
                continue
            
            # Create atlas for this group
            atlas_name = f"Atlas_{joined_mesh.name}_{group_idx}" if len(material_groups) > 1 else f"Atlas_{joined_mesh.name}"
            atlas_material = self.create_texture_atlas(context, joined_mesh, atlas_name)
            
            if atlas_material:
                atlas_meshes.append(joined_mesh)
                logger.info(f"Successfully created atlas for group {group_idx}")
            else:
                self.report({'ERROR'}, f"Failed to create atlas for group {group_idx}")
                return {'CANCELLED'}
        
        self.report({'INFO'}, f"Created {len(atlas_meshes)} atlas mesh(es) successfully")
        return {'FINISHED'}
    
    def analyze_material_sizes(self, materials, texture_types, mesh):
        """Analyze materials to determine texture sizes"""
        material_info = []
        
        for mat_idx, material in enumerate(materials):
            actual_tex_width = actual_tex_height = None
            has_texture = False
            
            if material.use_nodes:
                # Find all textures and determine size
                texture_types_found = {t: bake_utils.find_texture_in_material(material, t) for t in texture_types}
                
                for image in texture_types_found.values():
                    if image and image.has_data:
                        has_texture = True
                        img_width, img_height = image.size
                        if actual_tex_width is None or (img_width * img_height > actual_tex_width * actual_tex_height):
                            actual_tex_width, actual_tex_height = img_width, img_height
            
            actual_tex_width = actual_tex_width or 1024
            actual_tex_height = actual_tex_height or 1024
            
            material_info.append({
                'index': mat_idx, 'material': material, 'width': actual_tex_width, 'height': actual_tex_height,
                'has_texture': has_texture, 'texture_size': (actual_tex_width, actual_tex_height)
            })
            logger.info(f"Material {mat_idx} ({material.name}): {actual_tex_width}x{actual_tex_height} px")
        
        return material_info
    
    def calculate_atlas_layout(self, material_info):
        """Calculate atlas layout using skyline packing algorithm"""
        sorted_materials = sorted(material_info, key=lambda x: max(x['width'], x['height']), reverse=True)
        logger.info(f"Packing {len(sorted_materials)} materials")
        
        # Calculate total area and estimate square dimensions
        total_area = sum(info['width'] * info['height'] for info in sorted_materials)
        estimated_side = int(total_area ** 0.5)
        
        # Round up to nearest power of 2 for initial width estimate
        def next_power_of_2(n):
            """Round up to the nearest power of 2"""
            if n <= 0:
                return 1
            power = 1
            while power < n:
                power *= 2
            return power
        
        # Start with a width that aims for a square, but at least as wide as the widest item
        max_item_width = max((info['width'] for info in sorted_materials), default=64)
        width_limit = max(next_power_of_2(estimated_side), max_item_width)
        
        logger.info(f"Target square size: ~{estimated_side}px, initial width limit: {width_limit}px")
        
        # Skyline algorithm: maintain list of segments with (x, y, width)
        # representing the "skyline" - the top edge of placed rectangles
        skyline = [{'x': 0, 'y': 0, 'width': width_limit}]
        placements = {}
        max_height = 0

        for info in sorted_materials:
            rect_width, rect_height, mat_idx = info['width'], info['height'], info['index']
            
            # Find best position along skyline
            best_pos = None
            best_y = float('inf')
            best_idx = -1
            best_waste = float('inf')
            
            for i, segment in enumerate(skyline):
                # Check if rectangle fits starting at this segment
                can_fit, y_pos = self.can_fit_at_segment(skyline, i, rect_width, rect_height, width_limit)
                
                if can_fit:
                    # Calculate waste (how much vertical space this creates)
                    waste = y_pos - segment['y']
                    
                    # Prefer lower positions, then less waste
                    if y_pos < best_y or (y_pos == best_y and waste < best_waste):
                        best_pos = segment['x']
                        best_y = y_pos
                        best_idx = i
                        best_waste = waste
            
            if best_pos is None:
                logger.error(f"Could not fit material {mat_idx} ({rect_width}x{rect_height})")
                continue
            
            # Place the rectangle
            placement = {'x': best_pos, 'y': best_y, 'width': rect_width, 'height': rect_height}
            placements[mat_idx] = placement
            max_height = max(max_height, best_y + rect_height)
            
            # Update skyline
            self.update_skyline(skyline, best_pos, best_y, rect_width, rect_height)
            
            logger.debug(f"Placed material {mat_idx}: ({best_pos}, {best_y}) size {rect_width}x{rect_height}")
        
        atlas_width = next_power_of_2(max(width_limit, 64))
        atlas_height = next_power_of_2(max(max_height, 64))
        
        # Calculate efficiency
        used_area = sum(info['width'] * info['height'] for info in material_info)
        efficiency = (used_area / (atlas_width * atlas_height)) * 100
        
        logger.info(f"Atlas: {atlas_width}x{atlas_height}, Efficiency: {efficiency:.1f}%")
        return {
            'width': atlas_width,
            'height': atlas_height,
            'placements': placements,
        }
    
    def can_fit_at_segment(self, skyline, start_idx, width, height, width_limit):
        """Check if a rectangle can fit at the given skyline segment
        
        Returns (can_fit, y_position) where y_position is the lowest Y where the rectangle top would be
        """
        segment = skyline[start_idx]
        x = segment['x']
        
        # Check if rectangle would exceed width limit
        if x + width > width_limit:
            return False, 0
        
        # Find the maximum Y value across all segments this rectangle would span
        max_y = segment['y']
        current_x = x
        
        for i in range(start_idx, len(skyline)):
            seg = skyline[i]
            if current_x >= x + width:
                break
            
            if seg['x'] < x + width:
                max_y = max(max_y, seg['y'])
                current_x = seg['x'] + seg['width']
        
        # Check if we have enough continuous width
        if current_x < x + width:
            return False, 0
        
        return True, max_y
    
    def update_skyline(self, skyline, x, y, width, height):
        """Update the skyline after placing a rectangle
        
        This removes/modifies segments covered by the new rectangle and adds a new segment on top
        """
        new_y = y + height
        rect_right = x + width
        
        # Find segments that overlap with the placed rectangle
        new_skyline = []
        i = 0
        
        while i < len(skyline):
            seg = skyline[i]
            seg_right = seg['x'] + seg['width']
            
            # Segment is completely before the rectangle
            if seg_right <= x:
                new_skyline.append(seg)
                i += 1
                continue
            
            # Segment is completely after the rectangle
            if seg['x'] >= rect_right:
                new_skyline.append(seg)
                i += 1
                continue
            
            # Segment overlaps with rectangle
            # Add left part if exists
            if seg['x'] < x:
                new_skyline.append({
                    'x': seg['x'],
                    'y': seg['y'],
                    'width': x - seg['x']
                })
            
            # Add right part if exists
            if seg_right > rect_right:
                new_skyline.append({
                    'x': rect_right,
                    'y': seg['y'],
                    'width': seg_right - rect_right
                })
            
            i += 1
        
        # Add the new segment on top of the placed rectangle
        new_skyline.append({
            'x': x,
            'y': new_y,
            'width': width
        })
        
        # Sort by x position and merge adjacent segments with same height
        new_skyline.sort(key=lambda s: s['x'])
        
        merged = []
        for seg in new_skyline:
            if merged and merged[-1]['y'] == seg['y'] and merged[-1]['x'] + merged[-1]['width'] == seg['x']:
                # Merge with previous segment
                merged[-1]['width'] += seg['width']
            else:
                merged.append(seg)
        
        skyline.clear()
        skyline.extend(merged)
    
    def group_materials_manually(self, materials, settings):
        """Group materials based on their manually assigned atlas_group values
        
        Returns a list of material groups, where each group is a list of materials.
        Materials with atlas_group=0 are put into separate individual groups.
        """
        groups_dict = {}  # group_id -> list of materials
        ungrouped = []  # Materials with group=0
        
        for mat in materials:
            mat_setting = next((s for s in settings.material_bake_settings if s.material_name == mat.name), None)
            
            if mat_setting and mat_setting.atlas_group > 0:
                group_id = mat_setting.atlas_group
                if group_id not in groups_dict:
                    groups_dict[group_id] = []
                groups_dict[group_id].append(mat)
                logger.info(f"Material '{mat.name}' assigned to group {group_id}")
            else:
                # Materials with no setting or group=0 go into individual groups
                ungrouped.append(mat)
                logger.info(f"Material '{mat.name}' not assigned to a group (will be in separate atlas)")
        
        # Build final list of groups
        material_groups = []
        
        # Add assigned groups (sorted by group ID for consistency)
        for group_id in sorted(groups_dict.keys()):
            material_groups.append(groups_dict[group_id])
        
        # Add ungrouped materials as individual groups
        for mat in ungrouped:
            material_groups.append([mat])
        
        return material_groups
    
    def create_texture_atlas(self, context, joined_mesh, atlas_name):
        """Create texture atlas from all materials on mesh and update UVs"""
        logger.info(f"Creating texture atlas for mesh: {joined_mesh.name}")
        
        materials = [mat for mat in joined_mesh.data.materials if mat]
        if not materials:
            logger.warning("No materials found on mesh")
            self.report({'ERROR'}, "No materials found on the selected mesh")
            return None
        
        num_materials = len(materials)
        self.report({'INFO'}, f"Creating atlas from {num_materials} material(s)...")
        
        # Get atlas configuration
        atlas_config = bake_utils.get_atlas_config(context)
        texture_types = atlas_config['texture_types']
        logger.info(f"Atlas texture types: {texture_types}")
        
        # trim down texture types to only those that are actually used in the materials
        used_texture_types = set()
        for material in materials:
            for tex_type in texture_types:
                if bake_utils.find_texture_in_material(material, tex_type):
                    used_texture_types.add(tex_type)

        material_info = self.analyze_material_sizes(materials, used_texture_types, joined_mesh.data)
        atlas_layout = self.calculate_atlas_layout(material_info)
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        
        logger.info(f"Atlas resolution: {atlas_width}x{atlas_height}")
        self.report({'INFO'}, f"Atlas resolution: {atlas_width}x{atlas_height}")
        
        atlas_images = self.create_atlas_images(atlas_name, atlas_width, atlas_height, used_texture_types)
        material_uv_mapping = self.copy_textures_to_atlas(materials, material_info, atlas_layout, atlas_images, used_texture_types)

        self.update_uvs_for_atlas(joined_mesh, material_uv_mapping)
        atlas_material = self.create_atlas_material(context, atlas_name, atlas_images)
        
        joined_mesh.data.materials.clear()
        joined_mesh.data.materials.append(atlas_material)
        
        for tex_type, atlas_image in atlas_images.items():
            atlas_image.save()
            logger.info(f"Saved atlas texture: {atlas_image.name}")
        
        logger.info("Texture atlas creation complete")
        self.report({'INFO'}, f"Created {atlas_width}x{atlas_height} atlas with {num_materials} materials")
        
        return atlas_material
    
    def create_atlas_images(self, atlas_name, atlas_width, atlas_height, texture_types):
        """Create and initialize atlas images for each texture type"""
        atlas_images = {}
        
        for tex_type in texture_types:
            atlas_image_name = f"{atlas_name}_{tex_type}"
            atlas_image = bpy.data.images.new(
                name=atlas_image_name,
                width=atlas_width,
                height=atlas_height,
                alpha=True
            )
            atlas_image.filepath = bpy.path.abspath(f"//Bake/{atlas_image_name}.png")
            atlas_image.file_format = 'PNG'
            
            # Get configuration from bake_utils
            config = bake_utils.get_bake_pass_config(tex_type)
            if config:
                atlas_image.colorspace_settings.name = config['colorspace']
                default_color = config['background_color']
            else:
                # Fallback for unknown texture types
                atlas_image.colorspace_settings.name = 'sRGB'
                default_color = (0.0, 0.0, 0.0, 1.0)
            
            # Initialize with default color for this texture type
            rgba = np.zeros((atlas_height, atlas_width, 4), dtype=np.float32)
            rgba[:, :] = default_color
            
            bake_utils.nparray_to_img(atlas_image, rgba)
            atlas_images[tex_type] = atlas_image
        
        return atlas_images
    
    def copy_textures_to_atlas(self, materials, material_info, atlas_layout, atlas_images, texture_types):
        """Copy material textures into atlas and build UV mapping"""
        material_uv_mapping = {}
        material_info_by_idx = {info['index']: info for info in material_info}
        placements = atlas_layout['placements']
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        atlas_buffers = {tex_type: bake_utils.img_as_nparray(image) for tex_type, image in atlas_images.items()}

        for mat_idx, material in enumerate(materials):
            placement = placements.get(mat_idx)
            if placement is None:
                logger.warning(f"Material {mat_idx} has no placement in atlas layout")
                continue
            
            if mat_idx not in material_info_by_idx:
                logger.warning(f"Material {mat_idx} has no material info")
                continue
            
            mat_info = material_info_by_idx[mat_idx]
            
            tile_x = placement['x']
            tile_y = placement['y']
            tile_w = placement['width']
            tile_h = placement['height']

            u_offset = tile_x / atlas_width
            v_offset = tile_y / atlas_height
            u_scale = tile_w / atlas_width
            v_scale = tile_h / atlas_height

            material_uv_mapping[mat_idx] = (u_offset, v_offset, u_scale, v_scale)

            logger.info(f"Material {mat_idx} ({material.name}) -> pos ({tile_x}, {tile_y}) size ({tile_w}x{tile_h})")
            alpha_source = bake_utils.find_texture_in_material(material, 'alpha')

            for tex_type in texture_types:
                source_image = bake_utils.find_texture_in_material(material, tex_type)
                
                if not source_image or not source_image.has_data:
                    logger.debug(f"No {tex_type} texture found for material '{material.name}'")
                    continue

                try:
                    # Pass alpha source if we're packing alpha into diffuse
                    alpha_img = alpha_source
                    
                    self.copy_texture_to_atlas(
                        source_image,
                        atlas_buffers[tex_type],
                        tile_x,
                        tile_y,
                        tile_w,
                        tile_h,
                        tex_type,
                        alpha_img
                    )
                except Exception as e:
                    logger.exception(f"Failed copying {tex_type} for material '{material.name}': {e}")
        
        for tex_type, pixels in atlas_buffers.items():
            bake_utils.nparray_to_img(atlas_images[tex_type], pixels)

        return material_uv_mapping
    
    def create_atlas_material(self, context, atlas_name, atlas_images):
        """Create material with atlas textures"""
        atlas_material = bpy.data.materials.new(name=atlas_name)
        atlas_material.use_nodes = True
        nodes = atlas_material.node_tree.nodes
        links = atlas_material.node_tree.links
        
        nodes.clear()
        
        # Get atlas configuration
        atlas_config = bake_utils.get_atlas_config(context)
        texture_configs = atlas_config['texture_node_configs']
        special_nodes_config = atlas_config['special_nodes']
        connections = atlas_config['node_connections']
        
        # Create texture nodes only for available textures
        texture_nodes = {}
        for tex_type, location, label in texture_configs:
            if tex_type in atlas_images:
                tex_node = nodes.new('ShaderNodeTexImage')
                tex_node.image = atlas_images[tex_type]
                tex_node.location = location
                tex_node.label = label
                texture_nodes[tex_type] = tex_node
        
        # Create special nodes (normal_map, ior_math, bsdf, output)
        # Only create nodes that are needed based on available textures
        special_nodes = {}
        texture_types = atlas_config['texture_types']
        
        for node_key, factory_func, location, requires_texture in special_nodes_config:
            # Check if this node requires a specific texture type to be available
            if requires_texture and requires_texture not in texture_types:
                continue
            
            node = factory_func(atlas_material, location)
            special_nodes[node_key] = node
        
        # Combine all nodes for connection lookups
        all_nodes = {**texture_nodes, **special_nodes}
        
        # Create connections based on config, skipping missing nodes
        for from_key, from_output, to_key, to_input in connections:
            if from_key not in all_nodes or to_key not in all_nodes:
                continue
            from_node = all_nodes[from_key]
            to_node = all_nodes[to_key]
            links.new(from_node.outputs[from_output], to_node.inputs[to_input])
        
        return atlas_material
    
    def copy_texture_to_atlas(self, source_image, atlas_pixels, dest_x, dest_y, width, height, tex_type, alpha_image=None):
        """Copy source texture into atlas at specified position"""
        source_width, source_height = source_image.size
        atlas_height, atlas_width = atlas_pixels.shape[:2]

        # Get full source texture
        source_pixels = bake_utils.img_as_nparray(source_image)
        
        # Handle special texture type processing
        if tex_type == 'alpha':
            alpha_channel = source_pixels[:, :, 3:4]
            source_pixels = np.concatenate([alpha_channel] * 3 + [np.ones_like(alpha_channel)], axis=2)
        elif tex_type == 'diffuse' and alpha_image:
            logger.info(f"Packing alpha channel into diffuse texture")
            alpha_pixels = bake_utils.img_as_nparray(alpha_image)
            
            if alpha_pixels.shape[:2] != source_pixels.shape[:2]:
                alpha_pixels = self.bilinear_resize(alpha_pixels, source_width, source_height, alpha_image.size[0], alpha_image.size[1])
            
            source_pixels[:, :, 3] = alpha_pixels[:, :, 3]
        elif tex_type == 'diffuse':
            source_pixels[:, :, 3] = 1.0
        
        # Resize if needed
        if source_width != width or source_height != height:
            resize_type = "Downscaling" if (source_width > width or source_height > height) else "Upscaling"
            logger.info(f"{resize_type} texture from {source_width}x{source_height} to {width}x{height}")
            if resize_type == "Upscaling":
                logger.warning(f"Upscaling texture - may indicate packing inefficiency")
            source_pixels = self.bilinear_resize(source_pixels, width, height, source_width, source_height)
        
        # Calculate clipped bounds and copy
        x0, y0 = max(dest_x, 0), max(dest_y, 0)
        x1, y1 = min(dest_x + width, atlas_width), min(dest_y + height, atlas_height)
        
        if x1 > x0 and y1 > y0:
            sx0, sy0 = x0 - dest_x, y0 - dest_y
            atlas_pixels[dest_y + sy0:dest_y + sy0 + (y1 - y0), x0:x1, :] = source_pixels[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0), :]
    
    def bilinear_resize(self, source_pixels, width, height, source_width, source_height):
        """Resize image using bilinear interpolation"""
        x_ratio, y_ratio = source_width / width, source_height / height
        xs, ys = np.arange(width, dtype=np.float32) * x_ratio, np.arange(height, dtype=np.float32) * y_ratio
        x0, y0 = np.floor(xs).astype(np.int32), np.floor(ys).astype(np.int32)
        x1, y1 = np.clip(x0 + 1, 0, source_width - 1), np.clip(y0 + 1, 0, source_height - 1)
        wx, wy = (xs - x0)[None, :, None], (ys - y0)[:, None, None]

        TL, TR = source_pixels[y0[:, None], x0[None, :], :], source_pixels[y0[:, None], x1[None, :], :]
        BL, BR = source_pixels[y1[:, None], x0[None, :], :], source_pixels[y1[:, None], x1[None, :], :]
        return (TL * (1.0 - wx) + TR * wx) * (1.0 - wy) + (BL * (1.0 - wx) + BR * wx) * wy
    
    def update_uvs_for_atlas(self, mesh_obj, material_uv_mapping):
        """Update UV coordinates to map to atlas tiles"""
        logger.info(f"Updating UVs for atlas on mesh: {mesh_obj.name}")
        
        mesh = mesh_obj.data
        # uv_layer = mesh.uv_layers.get("UVMap")
        # if not uv_layer:
        #     logger.warning("No UVMap found on mesh")
        #     return
        # get the active UV layer
        uv_layer = mesh.uv_layers.active
        if not uv_layer:
            logger.warning("No active UV layer found on mesh")
            return
        if not uv_layer.active_render:
            logger.warning("Active UV layer is not set for rendering")
            return
        
        for poly in mesh.polygons:
            mat_idx = poly.material_index
            if mat_idx not in material_uv_mapping:
                continue
            
            u_offset, v_offset, u_scale, v_scale = material_uv_mapping[mat_idx]
            
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                
                uv.x = uv.x * u_scale + u_offset
                uv.y = uv.y * v_scale + v_offset
        
        mesh.update()
        logger.info(f"UVs updated for {len(mesh.polygons)} polygons")