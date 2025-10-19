import bpy
import logging
from bpy.types import Operator
import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


CONTENT_DEFAULTS = {
    'normal': (np.array([0.5, 0.5, 1.0, 1.0], dtype=np.float32), 0.02),
    'roughness': (np.array([0.5, 0.5, 0.5, 1.0], dtype=np.float32), 0.02),
    'alpha': (np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32), 0.02),
    'diffuse': (np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32), 0.05)
}


def _uv_bounds_to_pixels(uv_bounds, size):
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
    crop_x_start, crop_x_end, crop_y_start, crop_y_end = _uv_bounds_to_pixels(
        uv_bounds, (tex_width, tex_height)
    )
    
    if crop_x_end <= crop_x_start or crop_y_end <= crop_y_start:
        return uv_bounds
    
    # Extract UV-bounded region
    pixels = img_as_nparray(image)
    uv_region = pixels[crop_y_start:crop_y_end, crop_x_start:crop_x_end, :]
    
    # Define default colors and thresholds per texture type
    default_color, threshold = CONTENT_DEFAULTS.get(tex_type, CONTENT_DEFAULTS['diffuse'])
    
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
        material_uv_bounds = {}
        
        uv_layer = mesh.uv_layers.get("UVMap")
        if not uv_layer:
            logger.warning("No UVMap found, using full UV range")
            for mat_idx in range(len(materials)):
                material_uv_bounds[mat_idx] = (0.0, 0.0, 1.0, 1.0)
        else:
            for mat_idx in range(len(materials)):
                material_uv_bounds[mat_idx] = None
            
            for poly in mesh.polygons:
                mat_idx = poly.material_index
                
                for loop_idx in poly.loop_indices:
                    uv = uv_layer.data[loop_idx].uv
                    
                    if material_uv_bounds[mat_idx] is None:
                        material_uv_bounds[mat_idx] = (uv.x, uv.y, uv.x, uv.y)
                    else:
                        min_u, min_v, max_u, max_v = material_uv_bounds[mat_idx]
                        material_uv_bounds[mat_idx] = (
                            min(min_u, uv.x),
                            min(min_v, uv.y),
                            max(max_u, uv.x),
                            max(max_v, uv.y)
                        )
        
        logger.info(f"Calculated UV bounds for {len(materials)} materials")
        
        for mat_idx, material in enumerate(materials):
            if material_uv_bounds[mat_idx] is None:
                logger.info(f"Skipping material {mat_idx} ({material.name}): not used")
                continue
            
            initial_uv_bounds = material_uv_bounds[mat_idx]
            actual_tex_width = None
            actual_tex_height = None
            has_texture = False
            refined_bounds = initial_uv_bounds
            texture_types_found = {t: None for t in texture_types}
            
            if material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.has_data:
                        has_texture = True
                        node_name_lower = node.image.name.lower()
                        
                        for tex_type in texture_types:
                            if f'bake_{tex_type}' in node_name_lower or f'_{tex_type}' in node_name_lower:
                                texture_types_found[tex_type] = node.image
                                break
                        
                        img_width, img_height = node.image.size
                        if actual_tex_width is None or (img_width * img_height > actual_tex_width * actual_tex_height):
                            actual_tex_width = img_width
                            actual_tex_height = img_height
                
                content_bounds_found = []
                for tex_type, image in texture_types_found.items():
                    if image is not None:
                        content_bound = find_content_bounds(image, tex_type, initial_uv_bounds)
                        if content_bound != initial_uv_bounds:
                            content_bounds_found.append(content_bound)
                            logger.debug(f"  {tex_type}: content bounds {content_bound}")
                
                if content_bounds_found:
                    all_min_u = min(b[0] for b in content_bounds_found)
                    all_min_v = min(b[1] for b in content_bounds_found)
                    all_max_u = max(b[2] for b in content_bounds_found)
                    all_max_v = max(b[3] for b in content_bounds_found)
                    refined_bounds = (all_min_u, all_min_v, all_max_u, all_max_v)
                    
                    orig_area = (initial_uv_bounds[2] - initial_uv_bounds[0]) * (initial_uv_bounds[3] - initial_uv_bounds[1])
                    refined_area = (all_max_u - all_min_u) * (all_max_v - all_min_v)
                    savings = (1.0 - refined_area / orig_area) * 100 if orig_area > 0 else 0
                    if savings > 5:
                        logger.info(f"Material {mat_idx} ({material.name}): content trim saving {savings:.1f}%")
            
            if actual_tex_width is None:
                actual_tex_width = 1024
                actual_tex_height = 1024
            
            min_u, min_v, max_u, max_v = refined_bounds
            crop_width = max(int((max_u - min_u) * actual_tex_width), 16)
            crop_height = max(int((max_v - min_v) * actual_tex_height), 16)
            
            material_info.append({
                'index': mat_idx,
                'material': material,
                'width': crop_width,
                'height': crop_height,
                'has_texture': has_texture,
                'uv_bounds': refined_bounds,
                'texture_size': (actual_tex_width, actual_tex_height)
            })
            
            logger.info(f"Material {mat_idx} ({material.name}): {crop_width}x{crop_height} px")
        
        return material_info
    
    def calculate_atlas_layout(self, material_info):
        """
        Calculate efficient atlas layout using skyline packing algorithm.
        Packs textures at actual pixel dimensions, placing larger textures first.
        """
        sorted_materials = sorted(material_info, key=lambda x: x['width'] * x['height'], reverse=True)
        
        logger.info(f"Packing {len(sorted_materials)} materials")
        
        placements = {}
        shelves = []
        atlas_height = 0
        max_used_width = 0

        width_limit = max((info['width'] for info in sorted_materials), default=0)
        width_limit = max(width_limit, 64)

        for info in sorted_materials:
            width = info['width']
            height = info['height']
            mat_idx = info['index']

            placement = None

            if width > width_limit:
                width_limit = width

            for shelf in shelves:
                if height <= shelf['height'] and shelf['next_x'] + width <= width_limit:
                    x_pos = shelf['next_x']
                    shelf['next_x'] += width
                    shelf['used_width'] = max(shelf['used_width'], shelf['next_x'])
                    placement = {
                        'x': x_pos,
                        'y': shelf['y'],
                        'width': width,
                        'height': height
                    }
                    max_used_width = max(max_used_width, shelf['used_width'])
                    break

            if placement is None:
                shelf_y = atlas_height
                placement = {
                    'x': 0,
                    'y': shelf_y,
                    'width': width,
                    'height': height
                }

                shelves.append({
                    'y': shelf_y,
                    'height': height,
                    'next_x': width,
                    'used_width': width
                })

                atlas_height = shelf_y + height
                max_used_width = max(max_used_width, width)

            placements[mat_idx] = placement
            logger.debug(
                f"Placed material {mat_idx} ({width}x{height}) at ({placement['x']}, {placement['y']})"
            )
        
        atlas_width = max(max_used_width, 64)
        atlas_height = max(atlas_height, 64)
        
        total_material_area = sum(info['width'] * info['height'] for info in material_info)
        atlas_area = atlas_width * atlas_height
        efficiency = (total_material_area / atlas_area * 100) if atlas_area > 0 else 0
        
        logger.info(f"Atlas: {atlas_width}x{atlas_height}, efficiency: {efficiency:.1f}%")
        
        return {
            'width': atlas_width,
            'height': atlas_height,
            'placements': placements
        }
    
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
        
        texture_types = ['diffuse', 'normal', 'roughness', 'alpha']
        
        material_info = self.analyze_material_sizes(materials, texture_types, joined_mesh.data)
        atlas_layout = self.calculate_atlas_layout(material_info)
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        
        logger.info(f"Atlas resolution: {atlas_width}x{atlas_height}")
        self.report({'INFO'}, f"Atlas resolution: {atlas_width}x{atlas_height}")
        
        atlas_images = self._create_atlas_images(atlas_name, atlas_width, atlas_height, texture_types)
        material_uv_mapping = self._copy_textures_to_atlas(materials, material_info, atlas_layout, atlas_images, texture_types)
        
        self.update_uvs_for_atlas(joined_mesh, material_uv_mapping)
        atlas_material = self._create_atlas_material(atlas_name, atlas_images)
        
        joined_mesh.data.materials.clear()
        joined_mesh.data.materials.append(atlas_material)
        
        for tex_type, atlas_image in atlas_images.items():
            atlas_image.save()
            logger.info(f"Saved atlas texture: {atlas_image.name}")
        
        logger.info("Texture atlas creation complete")
        self.report({'INFO'}, f"Created {atlas_width}x{atlas_height} atlas with {num_materials} materials")
        
        return atlas_material
    
    def _create_atlas_images(self, atlas_name, atlas_width, atlas_height, texture_types):
        """Create and initialize atlas images for each texture type"""
        atlas_images = {}
        
        default_colors = {
            'diffuse': (0, 0, 0, 1),
            'normal': (0.5, 0.5, 1.0, 1.0),
            'roughness': (0.5, 0.5, 0.5, 1.0),
            'alpha': (1.0, 1.0, 1.0, 1.0)
        }
        
        non_color_types = {'normal', 'roughness', 'alpha'}
        
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
            
            if tex_type in non_color_types:
                atlas_image.colorspace_settings.name = 'Non-Color'
            
            rgba = np.zeros((atlas_height, atlas_width, 4), dtype=np.float32)
            r, g, b, a = default_colors[tex_type]
            rgba[:, :] = [r, g, b, a]
            
            nparray_to_img(atlas_image, rgba)
            atlas_images[tex_type] = atlas_image
        
        return atlas_images
    
    def _copy_textures_to_atlas(self, materials, material_info, atlas_layout, atlas_images, texture_types):
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

            for tex_type in texture_types:
                source_image = self._find_texture_for_type(material, tex_type)
                
                if not source_image or not source_image.has_data:
                    logger.debug(f"No {tex_type} texture found for material '{material.name}'")
                    continue

                try:
                    self.copy_texture_to_atlas(
                        source_image,
                        atlas_buffers[tex_type],
                        tile_x,
                        tile_y,
                        tile_w,
                        tile_h,
                        tex_type,
                        uv_bounds
                    )
                except Exception as e:
                    logger.exception(f"Failed copying {tex_type} for material '{material.name}': {e}")
        
        for tex_type, pixels in atlas_buffers.items():
            nparray_to_img(atlas_images[tex_type], pixels)

        return material_uv_mapping
    
    def _find_texture_for_type(self, material, tex_type):
        """Find the appropriate texture image for a given texture type from material"""
        if not material.use_nodes:
            return None
        
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                node_name_lower = node.image.name.lower()
                if f"bake_{tex_type}" in node_name_lower or f"_{tex_type}" in node_name_lower:
                    return node.image
        
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
    
    def _create_atlas_material(self, atlas_name, atlas_images):
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
        
        links.new(texture_nodes['diffuse'].outputs['Color'], bsdf_node.inputs['Base Color'])
        links.new(texture_nodes['alpha'].outputs['Color'], bsdf_node.inputs['Alpha'])
        links.new(texture_nodes['roughness'].outputs['Color'], bsdf_node.inputs['Roughness'])
        links.new(texture_nodes['normal'].outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf_node.inputs['Normal'])
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        return atlas_material
    
    def copy_texture_to_atlas(self, source_image, atlas_pixels, dest_x, dest_y, width, height, tex_type, uv_bounds):
        """Copy source texture into atlas at specified position, cropping to UV bounds"""
        source_width, source_height = source_image.size
        min_u, min_v, max_u, max_v = uv_bounds
        atlas_height, atlas_width = atlas_pixels.shape[:2]

        source_pixels = img_as_nparray(source_image)

        crop_x_start, crop_x_end, crop_y_start, crop_y_end = _uv_bounds_to_pixels(
            uv_bounds, (source_width, source_height)
        )
        
        cropped_pixels = source_pixels[crop_y_start:crop_y_end, crop_x_start:crop_x_end, :]
        cropped_height, cropped_width = cropped_pixels.shape[:2]
        
        if cropped_width == 0 or cropped_height == 0:
            logger.warning(f"Cropped texture has zero size, skipping")
            return
        
        source_pixels = cropped_pixels
        source_width = cropped_width
        source_height = cropped_height
        
        logger.debug(f"Cropped texture from UV ({min_u:.2f}, {min_v:.2f}) to ({max_u:.2f}, {max_v:.2f}): {source_width}x{source_height}")
        
        if tex_type == 'alpha':
            alpha_channel = source_pixels[:, :, 3:4]
            source_pixels = np.concatenate([alpha_channel, alpha_channel, alpha_channel, np.ones_like(alpha_channel)], axis=2)
        elif tex_type == 'diffuse':
            source_pixels[:, :, 3] = 1.0
        
        if source_width != width or source_height != height:
            logger.info(f"Resizing texture from {source_width}x{source_height} to {width}x{height}")
            
            if source_width > width or source_height > height:
                logger.debug(f"Downscaling texture to fit allocated space")
            else:
                logger.warning(f"Upscaling texture - may indicate packing inefficiency")
            
            source_pixels = self._bilinear_resize(source_pixels, width, height, source_width, source_height)
            source_height = height
            source_width = width
        
        x0 = max(dest_x, 0)
        y0 = max(dest_y, 0)
        x1 = min(dest_x + width, atlas_width)
        y1 = min(dest_y + height, atlas_height)
        if x1 <= x0 or y1 <= y0:
            return

        sx0 = x0 - dest_x
        sy0 = y0 - dest_y
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)

        ay_start = dest_y + sy0
        ay_end = dest_y + sy1

        atlas_pixels[ay_start:ay_end, x0:x1, :] = source_pixels[sy0:sy1, sx0:sx1, :]
    
    def _bilinear_resize(self, source_pixels, width, height, source_width, source_height):
        """Resize image using bilinear interpolation"""
        x_ratio = source_width / width
        y_ratio = source_height / height
        xs = np.arange(width, dtype=np.float32) * x_ratio
        ys = np.arange(height, dtype=np.float32) * y_ratio

        x0 = np.floor(xs).astype(np.int32)
        y0 = np.floor(ys).astype(np.int32)
        x1 = np.clip(x0 + 1, 0, source_width - 1)
        y1 = np.clip(y0 + 1, 0, source_height - 1)

        wx = (xs - x0)[None, :, None]
        wy = (ys - y0)[:, None, None]

        TL = source_pixels[y0[:, None], x0[None, :], :]
        TR = source_pixels[y0[:, None], x1[None, :], :]
        BL = source_pixels[y1[:, None], x0[None, :], :]
        BR = source_pixels[y1[:, None], x1[None, :], :]

        top = TL * (1.0 - wx) + TR * wx
        bottom = BL * (1.0 - wx) + BR * wx
        return top * (1.0 - wy) + bottom * wy
    
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