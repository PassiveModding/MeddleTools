import bpy
import logging
from bpy.types import Operator
import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# Consolidated texture defaults: (default_color, content_threshold)
TEXTURE_DEFAULTS = {
    'diffuse': ((0.0, 0.0, 0.0, 1.0), 0.05),
    'normal': ((0.5, 0.5, 1.0, 1.0), 0.02),
    'roughness': ((0.5, 0.5, 0.5, 1.0), 0.02),
    'alpha': ((1.0, 1.0, 1.0, 1.0), 0.02)
}

# Non-color texture types that need specific colorspace handling
NON_COLOR_TYPES = {'normal', 'roughness', 'alpha'}


def uv_bounds_to_pixels(uv_bounds, size):
    """Convert UV bounds (0-1) into pixel-space start/end coordinates."""
    width, height = size
    min_u, min_v, max_u, max_v = uv_bounds

    x_start = max(0, min(int(min_u * width), width))
    x_end = max(0, min(int(max_u * width), width))
    y_start = max(0, min(int(min_v * height), height))
    y_end = max(0, min(int(max_v * height), height))

    return x_start, x_end, y_start, y_end


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
    """Find the appropriate texture image for a given texture type from material
    
    Args:
        material: Blender material to search
        tex_type: Type of texture to find ('diffuse', 'normal', 'roughness', 'alpha')
    
    Returns:
        Image or None if not found
    """
    if not material.use_nodes:
        return None
    
    # First try to find by name
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            node_name_lower = node.image.name.lower()
            if f"bake_{tex_type}" in node_name_lower or f"_{tex_type}" in node_name_lower:
                return node.image
    
    # Then try to find by socket connections
    links = material.node_tree.links
    socket_mapping = {
        'diffuse': 'Base Color',
        'roughness': 'Roughness',
        'alpha': 'Alpha'
    }
    
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


def find_content_bounds(image, tex_type, uv_bounds):
    """
    Find actual content bounds within a texture by detecting non-default pixels.
    Returns refined UV bounds (min_u, min_v, max_u, max_v) that tightly fit content.
    """
    if not image or not image.has_data:
        return uv_bounds
    
    tex_width, tex_height = image.size
    min_u, min_v, max_u, max_v = uv_bounds
    
    # Convert UV bounds to pixel coordinates
    crop_x_start, crop_x_end, crop_y_start, crop_y_end = uv_bounds_to_pixels(
        uv_bounds, (tex_width, tex_height)
    )
    
    if crop_x_end <= crop_x_start or crop_y_end <= crop_y_start:
        return uv_bounds
    
    # Extract UV-bounded region
    pixels = img_as_nparray(image)
    uv_region = pixels[crop_y_start:crop_y_end, crop_x_start:crop_x_end, :]
    
    # Define default colors and thresholds per texture type
    default_color_tuple, threshold = TEXTURE_DEFAULTS.get(tex_type, TEXTURE_DEFAULTS['diffuse'])
    default_color = np.array(default_color_tuple, dtype=np.float32)
    
    # Find content mask
    diff = np.abs(uv_region - default_color)
    has_content = np.any(diff > threshold, axis=2)
    
    # Find bounding box of content
    rows_with_content = np.any(has_content, axis=1)
    cols_with_content = np.any(has_content, axis=0)
    
    if not np.any(rows_with_content) or not np.any(cols_with_content):
        return uv_bounds
    
    row_indices = np.where(rows_with_content)[0]
    col_indices = np.where(cols_with_content)[0]
    
    # Convert content bounds back to UV coordinates
    abs_x_start = crop_x_start + col_indices[0]
    abs_x_end = crop_x_start + col_indices[-1] + 1
    abs_y_start = crop_y_start + row_indices[0]
    abs_y_end = crop_y_start + row_indices[-1] + 1
    
    return (
        abs_x_start / tex_width,
        abs_y_start / tex_height,
        abs_x_end / tex_width,
        abs_y_end / tex_height
    )


class RunAtlas(Operator):
    """Create texture atlas from selected mesh materials"""
    bl_idname = "meddle.run_atlas"
    bl_label = "Create Texture Atlas"
    bl_description = "Create a texture atlas from the materials of the selected mesh(es)"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}
        
        if len(mesh_objects) > 1:
            self.report({'INFO'}, f"Joining {len(mesh_objects)} meshes...")
            logger.info(f"Joining {len(mesh_objects)} meshes for atlas")
            
            bpy.ops.object.select_all(action='DESELECT')
            for obj in mesh_objects:
                obj.select_set(True)
            
            context.view_layer.objects.active = mesh_objects[0]
            bpy.ops.object.join()
            joined_mesh = context.view_layer.objects.active
        else:
            joined_mesh = mesh_objects[0]
        
        atlas_name = f"Atlas_{joined_mesh.name}"
        atlas_material = self.create_texture_atlas(context, joined_mesh, atlas_name)
        
        if atlas_material:
            self.report({'INFO'}, f"Texture atlas created successfully: {atlas_material.name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to create texture atlas")
            return {'CANCELLED'}
    
    def analyze_material_sizes(self, materials, texture_types, mesh):
        """Analyze materials to determine texture sizes and UV bounds"""
        material_info = []
        uv_layer = mesh.uv_layers.get("UVMap")
        
        # Calculate UV bounds per material
        material_uv_bounds = {i: (0.0, 0.0, 1.0, 1.0) for i in range(len(materials))} if not uv_layer else {}
        
        if uv_layer:
            material_uv_bounds = {i: None for i in range(len(materials))}
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    uv = uv_layer.data[loop_idx].uv
                    mat_idx = poly.material_index
                    if material_uv_bounds[mat_idx] is None:
                        material_uv_bounds[mat_idx] = (uv.x, uv.y, uv.x, uv.y)
                    else:
                        min_u, min_v, max_u, max_v = material_uv_bounds[mat_idx]
                        material_uv_bounds[mat_idx] = (min(min_u, uv.x), min(min_v, uv.y), max(max_u, uv.x), max(max_v, uv.y))
        
        logger.info(f"Calculated UV bounds for {len(materials)} materials")
        
        for mat_idx, material in enumerate(materials):
            if material_uv_bounds.get(mat_idx) is None:
                logger.info(f"Skipping material {mat_idx} ({material.name}): not used")
                continue
            
            initial_uv_bounds = material_uv_bounds[mat_idx]
            refined_bounds = initial_uv_bounds
            actual_tex_width = actual_tex_height = None
            has_texture = False
            
            if material.use_nodes:
                # Find all textures and determine size
                texture_types_found = {t: find_texture_in_material(material, t) for t in texture_types}
                
                for image in texture_types_found.values():
                    if image and image.has_data:
                        has_texture = True
                        img_width, img_height = image.size
                        if actual_tex_width is None or (img_width * img_height > actual_tex_width * actual_tex_height):
                            actual_tex_width, actual_tex_height = img_width, img_height
                
                # Find tight content bounds
                content_bounds_found = []
                for tex_type, img in texture_types_found.items():
                    if img is not None:
                        cb = find_content_bounds(img, tex_type, initial_uv_bounds)
                        if cb != initial_uv_bounds:
                            content_bounds_found.append(cb)
                
                if content_bounds_found:
                    refined_bounds = (min(b[0] for b in content_bounds_found), min(b[1] for b in content_bounds_found),
                                    max(b[2] for b in content_bounds_found), max(b[3] for b in content_bounds_found))
                    
                    orig_area = (initial_uv_bounds[2] - initial_uv_bounds[0]) * (initial_uv_bounds[3] - initial_uv_bounds[1])
                    refined_area = (refined_bounds[2] - refined_bounds[0]) * (refined_bounds[3] - refined_bounds[1])
                    if (savings := (1.0 - refined_area / orig_area) * 100 if orig_area > 0 else 0) > 5:
                        logger.info(f"Material {mat_idx} ({material.name}): content trim saving {savings:.1f}%")
            
            actual_tex_width = actual_tex_width or 1024
            actual_tex_height = actual_tex_height or 1024
            
            min_u, min_v, max_u, max_v = refined_bounds
            crop_width = max(int((max_u - min_u) * actual_tex_width), 16)
            crop_height = max(int((max_v - min_v) * actual_tex_height), 16)
            
            material_info.append({
                'index': mat_idx, 'material': material, 'width': crop_width, 'height': crop_height,
                'has_texture': has_texture, 'uv_bounds': refined_bounds, 'texture_size': (actual_tex_width, actual_tex_height)
            })
            logger.info(f"Material {mat_idx} ({material.name}): {crop_width}x{crop_height} px")
        
        return material_info
    
    def calculate_atlas_layout(self, material_info):
        """Calculate efficient atlas layout using skyline packing algorithm with square optimization"""
        sorted_materials = sorted(material_info, key=lambda x: x['width'] * x['height'], reverse=True)
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
        
        placements, shelves, atlas_height, max_used_width = {}, [], 0, 0

        for info in sorted_materials:
            width, height, mat_idx = info['width'], info['height'], info['index']
            placement = None

            # Try to fit on existing shelf - find best fit shelf
            best_shelf = None
            best_waste = float('inf')
            
            for shelf in shelves:
                if height <= shelf['height'] and shelf['next_x'] + width <= width_limit:
                    # Calculate wasted space (height difference)
                    waste = shelf['height'] - height
                    if waste < best_waste:
                        best_waste = waste
                        best_shelf = shelf
            
            if best_shelf is not None:
                placement = {'x': best_shelf['next_x'], 'y': best_shelf['y'], 'width': width, 'height': height}
                best_shelf['next_x'] += width
                best_shelf['used_width'] = max(best_shelf['used_width'], best_shelf['next_x'])
                max_used_width = max(max_used_width, best_shelf['next_x'])
            else:
                # Create new shelf if needed
                placement = {'x': 0, 'y': atlas_height, 'width': width, 'height': height}
                shelves.append({'y': atlas_height, 'height': height, 'next_x': width, 'used_width': width})
                atlas_height += height
                max_used_width = max(max_used_width, width)

            placements[mat_idx] = placement
        
        atlas_width = next_power_of_2(max(max_used_width, 64))
        atlas_height = next_power_of_2(max(atlas_height, 64))
        efficiency = (total_area / (atlas_width * atlas_height) * 100) if atlas_width * atlas_height > 0 else 0
        aspect_ratio = atlas_width / atlas_height if atlas_height > 0 else 1.0
        logger.info(f"Atlas: {atlas_width}x{atlas_height} (aspect: {aspect_ratio:.2f}:1), efficiency: {efficiency:.1f}%")
        
        return {'width': atlas_width, 'height': atlas_height, 'placements': placements}
    
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
        
        # Check if alpha should be packed into diffuse
        pack_alpha = context.scene.meddle_settings.pack_alpha
        
        # Determine texture types based on pack_alpha setting
        if pack_alpha:
            texture_types = ['diffuse', 'normal', 'roughness']
            logger.info("Pack alpha enabled - alpha will be packed into diffuse texture")
        else:
            texture_types = ['diffuse', 'normal', 'roughness', 'alpha']
            logger.info("Pack alpha disabled - separate alpha texture will be created")
        
        material_info = self.analyze_material_sizes(materials, texture_types, joined_mesh.data)
        atlas_layout = self.calculate_atlas_layout(material_info)
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        
        logger.info(f"Atlas resolution: {atlas_width}x{atlas_height}")
        self.report({'INFO'}, f"Atlas resolution: {atlas_width}x{atlas_height}")
        
        atlas_images = self.create_atlas_images(atlas_name, atlas_width, atlas_height, texture_types)
        material_uv_mapping = self.copy_textures_to_atlas(materials, material_info, atlas_layout, atlas_images, texture_types, pack_alpha)
        
        self.update_uvs_for_atlas(joined_mesh, material_uv_mapping)
        atlas_material = self.create_atlas_material(atlas_name, atlas_images, pack_alpha)
        
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
            
            if tex_type in NON_COLOR_TYPES:
                atlas_image.colorspace_settings.name = 'Non-Color'
            
            # Initialize with default color for this texture type
            default_color, _ = TEXTURE_DEFAULTS.get(tex_type, TEXTURE_DEFAULTS['diffuse'])
            rgba = np.zeros((atlas_height, atlas_width, 4), dtype=np.float32)
            rgba[:, :] = default_color
            
            nparray_to_img(atlas_image, rgba)
            atlas_images[tex_type] = atlas_image
        
        return atlas_images
    
    def copy_textures_to_atlas(self, materials, material_info, atlas_layout, atlas_images, texture_types, pack_alpha):
        """Copy material textures into atlas and build UV mapping"""
        material_uv_mapping = {}
        material_info_by_idx = {info['index']: info for info in material_info}
        placements = atlas_layout['placements']
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        atlas_buffers = {tex_type: img_as_nparray(image) for tex_type, image in atlas_images.items()}

        for mat_idx, material in enumerate(materials):
            placement = placements.get(mat_idx)
            if placement is None:
                logger.warning(f"Material {mat_idx} has no placement in atlas layout")
                continue
            
            if mat_idx not in material_info_by_idx:
                logger.warning(f"Material {mat_idx} has no material info")
                continue
            
            mat_info = material_info_by_idx[mat_idx]
            uv_bounds = mat_info['uv_bounds']
            
            tile_x = placement['x']
            tile_y = placement['y']
            tile_w = placement['width']
            tile_h = placement['height']

            u_offset = tile_x / atlas_width
            v_offset = tile_y / atlas_height
            u_scale = tile_w / atlas_width
            v_scale = tile_h / atlas_height

            material_uv_mapping[mat_idx] = (u_offset, v_offset, u_scale, v_scale, uv_bounds)

            logger.info(f"Material {mat_idx} ({material.name}) -> pos ({tile_x}, {tile_y}) size ({tile_w}x{tile_h})")

            # Handle alpha texture separately if pack_alpha is enabled
            alpha_source = None
            if pack_alpha:
                alpha_source = find_texture_in_material(material, 'alpha')

            for tex_type in texture_types:
                source_image = find_texture_in_material(material, tex_type)
                
                if not source_image or not source_image.has_data:
                    logger.debug(f"No {tex_type} texture found for material '{material.name}'")
                    continue

                try:
                    # Pass alpha source if we're packing alpha into diffuse
                    alpha_img = alpha_source if (pack_alpha and tex_type == 'diffuse') else None
                    
                    self.copy_texture_to_atlas(
                        source_image,
                        atlas_buffers[tex_type],
                        tile_x,
                        tile_y,
                        tile_w,
                        tile_h,
                        tex_type,
                        uv_bounds,
                        alpha_img
                    )
                except Exception as e:
                    logger.exception(f"Failed copying {tex_type} for material '{material.name}': {e}")
        
        for tex_type, pixels in atlas_buffers.items():
            nparray_to_img(atlas_images[tex_type], pixels)

        return material_uv_mapping
    
    def create_atlas_material(self, atlas_name, atlas_images, pack_alpha):
        """Create material with atlas textures"""
        atlas_material = bpy.data.materials.new(name=atlas_name)
        atlas_material.use_nodes = True
        nodes = atlas_material.node_tree.nodes
        links = atlas_material.node_tree.links
        
        nodes.clear()
        
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 0)
        bsdf_node.inputs['IOR'].default_value = 1.0
        bsdf_node.inputs['Metallic'].default_value = 0.0
        
        # Configure texture nodes based on pack_alpha setting
        if pack_alpha:
            texture_configs = [
                ('diffuse', (-400, 300), 'Atlas Diffuse'),
                ('normal', (-400, 0), 'Atlas Normal'),
                ('roughness', (-400, -300), 'Atlas Roughness')
            ]
        else:
            texture_configs = [
                ('diffuse', (-400, 300), 'Atlas Diffuse'),
                ('alpha', (-400, 100), 'Atlas Alpha'),
                ('normal', (-400, -100), 'Atlas Normal'),
                ('roughness', (-400, -300), 'Atlas Roughness')
            ]
        
        texture_nodes = {}
        for tex_type, location, label in texture_configs:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = atlas_images[tex_type]
            tex_node.location = location
            tex_node.label = label
            texture_nodes[tex_type] = tex_node
        
        normal_map = nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-100, -100)
        
        # Connect nodes
        links.new(texture_nodes['diffuse'].outputs['Color'], bsdf_node.inputs['Base Color'])
        
        if pack_alpha:
            # When packing, use diffuse's alpha channel
            links.new(texture_nodes['diffuse'].outputs['Alpha'], bsdf_node.inputs['Alpha'])
        else:
            # When not packing, use separate alpha texture
            links.new(texture_nodes['alpha'].outputs['Color'], bsdf_node.inputs['Alpha'])
        
        links.new(texture_nodes['roughness'].outputs['Color'], bsdf_node.inputs['Roughness'])
        links.new(texture_nodes['normal'].outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf_node.inputs['Normal'])
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        return atlas_material
    
    def copy_texture_to_atlas(self, source_image, atlas_pixels, dest_x, dest_y, width, height, tex_type, uv_bounds, alpha_image=None):
        """Copy source texture into atlas at specified position, cropping to UV bounds"""
        source_width, source_height = source_image.size
        min_u, min_v, max_u, max_v = uv_bounds
        atlas_height, atlas_width = atlas_pixels.shape[:2]

        # Crop to UV bounds
        crop_x_start, crop_x_end, crop_y_start, crop_y_end = uv_bounds_to_pixels(uv_bounds, (source_width, source_height))
        source_pixels = img_as_nparray(source_image)[crop_y_start:crop_y_end, crop_x_start:crop_x_end, :]
        cropped_height, cropped_width = source_pixels.shape[:2]
        
        if cropped_width == 0 or cropped_height == 0:
            logger.warning(f"Cropped texture has zero size, skipping")
            return
        
        logger.debug(f"Cropped texture from UV ({min_u:.2f}, {min_v:.2f}) to ({max_u:.2f}, {max_v:.2f}): {cropped_width}x{cropped_height}")
        
        # Handle special texture type processing
        if tex_type == 'alpha':
            alpha_channel = source_pixels[:, :, 3:4]
            source_pixels = np.concatenate([alpha_channel] * 3 + [np.ones_like(alpha_channel)], axis=2)
        elif tex_type == 'diffuse' and alpha_image:
            logger.info(f"Packing alpha channel into diffuse texture")
            alpha_crop = uv_bounds_to_pixels(uv_bounds, (alpha_image.size[0], alpha_image.size[1]))
            alpha_cropped = img_as_nparray(alpha_image)[alpha_crop[2]:alpha_crop[3], alpha_crop[0]:alpha_crop[1], :]
            
            if alpha_cropped.shape[:2] != source_pixels.shape[:2]:
                alpha_cropped = self.bilinear_resize(alpha_cropped, cropped_width, cropped_height, alpha_cropped.shape[1], alpha_cropped.shape[0])
            
            source_pixels[:, :, 3] = alpha_cropped[:, :, 3]
        elif tex_type == 'diffuse':
            source_pixels[:, :, 3] = 1.0
        
        # Resize if needed
        if cropped_width != width or cropped_height != height:
            resize_type = "Downscaling" if (cropped_width > width or cropped_height > height) else "Upscaling"
            logger.info(f"{resize_type} texture from {cropped_width}x{cropped_height} to {width}x{height}")
            if resize_type == "Upscaling":
                logger.warning(f"Upscaling texture - may indicate packing inefficiency")
            source_pixels = self.bilinear_resize(source_pixels, width, height, cropped_width, cropped_height)
        
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
        uv_layer = mesh.uv_layers.get("UVMap")
        if not uv_layer:
            logger.warning("No UVMap found on mesh")
            return
        
        for poly in mesh.polygons:
            mat_idx = poly.material_index
            if mat_idx not in material_uv_mapping:
                continue
            
            u_offset, v_offset, u_scale, v_scale, uv_bounds = material_uv_mapping[mat_idx]
            min_u, min_v, max_u, max_v = uv_bounds
            uv_range_u = max(max_u - min_u, 1e-6)
            uv_range_v = max(max_v - min_v, 1e-6)
            
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                
                normalized_u = (uv.x - min_u) / uv_range_u
                normalized_v = (uv.y - min_v) / uv_range_v
                
                uv.x = normalized_u * u_scale + u_offset
                uv.y = normalized_v * v_scale + v_offset
        
        mesh.update()
        logger.info(f"UVs updated for {len(mesh.polygons)} polygons")