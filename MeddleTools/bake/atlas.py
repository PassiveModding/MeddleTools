import bpy
import logging
from bpy.types import Operator
import math
import numpy as np

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

# Helper functions to efficiently move pixels between Blender images and numpy
def img_as_nparray(image):
    """Convert Blender image to numpy array (H, W, 4) in row-major order"""
    pixel_buffer = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
    image.pixels.foreach_get(pixel_buffer)
    # Blender stores pixels in row-major order: RGBARGBARGBA...
    # Reshape to (height, width, 4) using C order
    return pixel_buffer.reshape(image.size[1], image.size[0], 4)

def nparray_to_img(image, nparr):
    """Write numpy array (H, W, 4) back to Blender image"""
    assert nparr.shape[0] == image.size[1]  # height
    assert nparr.shape[1] == image.size[0]  # width
    assert nparr.shape[2] == 4  # RGBA
    image.pixels.foreach_set(nparr.ravel())

class RunAtlas(Operator):
    """Create texture atlas from selected mesh materials"""
    bl_idname = "meddle.run_atlas"
    bl_label = "Create Texture Atlas"
    bl_description = "Create a texture atlas from the materials of the selected mesh(es)"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Require at least one mesh to be selected
        return any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        # Get selected mesh objects
        mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected.")
            return {'CANCELLED'}
        
        # If multiple meshes selected, join them first
        if len(mesh_objects) > 1:
            self.report({'INFO'}, f"Joining {len(mesh_objects)} meshes...")
            logger.info(f"Joining {len(mesh_objects)} meshes for atlas")
            
            # Deselect all
            bpy.ops.object.select_all(action='DESELECT')
            
            # Select mesh objects
            for obj in mesh_objects:
                obj.select_set(True)
            
            # Set active
            context.view_layer.objects.active = mesh_objects[0]
            
            # Join
            bpy.ops.object.join()
            
            # Get the joined mesh
            joined_mesh = context.view_layer.objects.active
        else:
            joined_mesh = mesh_objects[0]
        
        # Create atlas name based on mesh name
        atlas_name = f"Atlas_{joined_mesh.name}"
        
        # Create texture atlas
        atlas_material = self.create_texture_atlas(context, joined_mesh, atlas_name)
        
        if atlas_material:
            self.report({'INFO'}, f"Texture atlas created successfully: {atlas_material.name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to create texture atlas")
            return {'CANCELLED'}
    
    def analyze_material_sizes(self, materials, texture_types, mesh):
        """Analyze all materials to determine their texture sizes and UV bounds"""
        material_info = []
        
        # First, determine which materials are actually used and calculate UV bounds
        material_uv_bounds = {}  # mat_idx -> (min_u, min_v, max_u, max_v)
        
        # Get UV layer
        uv_layer = mesh.uv_layers.get("UVMap")
        if not uv_layer:
            logger.warning("No UVMap found on mesh, cannot calculate UV bounds")
            # Fall back to full UV range for all materials
            for mat_idx in range(len(materials)):
                material_uv_bounds[mat_idx] = (0.0, 0.0, 1.0, 1.0)
        else:
            # Initialize bounds for each material
            for mat_idx in range(len(materials)):
                material_uv_bounds[mat_idx] = None
            
            # Scan all polygons to find UV bounds per material
            for poly in mesh.polygons:
                mat_idx = poly.material_index
                
                # Get UV coordinates for this polygon
                for loop_idx in poly.loop_indices:
                    uv = uv_layer.data[loop_idx].uv
                    
                    if material_uv_bounds[mat_idx] is None:
                        # First UV for this material
                        material_uv_bounds[mat_idx] = (uv.x, uv.y, uv.x, uv.y)
                    else:
                        # Expand bounds
                        min_u, min_v, max_u, max_v = material_uv_bounds[mat_idx]
                        material_uv_bounds[mat_idx] = (
                            min(min_u, uv.x),
                            min(min_v, uv.y),
                            max(max_u, uv.x),
                            max(max_v, uv.y)
                        )
        
        logger.info(f"Calculated UV bounds for {len(materials)} materials")
        
        for mat_idx, material in enumerate(materials):
            # Skip materials not used by any polygon (no UV bounds)
            if material_uv_bounds[mat_idx] is None:
                logger.info(f"Skipping material {mat_idx} ({material.name}): not used by any polygon")
                continue
            
            # Get UV bounds
            min_u, min_v, max_u, max_v = material_uv_bounds[mat_idx]
            uv_width = max_u - min_u
            uv_height = max_v - min_v
            
            # Clamp to reasonable values (avoid degenerate cases)
            uv_width = max(uv_width, 0.01)
            uv_height = max(uv_height, 0.01)
            
            # Find the representative texture size for this material
            # Use the ACTUAL texture size from the images, not theoretical max
            actual_tex_width = None
            actual_tex_height = None
            has_texture = False
            
            if material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.has_data:
                        has_texture = True
                        img_width = node.image.size[0]
                        img_height = node.image.size[1]
                        # Use the actual texture size (could be smaller than 1024 if baked at lower res)
                        if actual_tex_width is None or (img_width * img_height > actual_tex_width * actual_tex_height):
                            actual_tex_width = img_width
                            actual_tex_height = img_height
            
            # If no texture found, use defaults
            if actual_tex_width is None:
                actual_tex_width = 1024
                actual_tex_height = 1024
            
            # Calculate actual cropped pixel region size from the ACTUAL texture dimensions
            crop_x_start = int(min_u * actual_tex_width)
            crop_x_end = int(max_u * actual_tex_width)
            crop_y_start = int(min_v * actual_tex_height)
            crop_y_end = int(max_v * actual_tex_height)
            
            # Actual cropped dimensions in pixels
            crop_width = crop_x_end - crop_x_start
            crop_height = crop_y_end - crop_y_start
            
            # Ensure minimum size
            crop_width = max(crop_width, 16)
            crop_height = max(crop_height, 16)
            
            material_info.append({
                'index': mat_idx,
                'material': material,
                'width': crop_width,
                'height': crop_height,
                'has_texture': has_texture,
                'uv_bounds': material_uv_bounds[mat_idx],
                'texture_size': (actual_tex_width, actual_tex_height)
            })
            
            logger.info(f"Material {mat_idx} ({material.name}): {crop_width}x{crop_height} pixels (actual texture: {actual_tex_width}x{actual_tex_height}, UV coverage: {uv_width:.2f}x{uv_height:.2f})")
        
        return material_info
    
    def calculate_atlas_layout(self, material_info):
        """
        Calculate an efficient atlas layout that packs materials by their actual cropped sizes.
        
        This uses a skyline packing algorithm that:
        - Packs textures at their actual pixel dimensions (no forced resizing)
        - Places larger textures first for better space utilization
        - Allows smaller textures to fill gaps in shelves
        - Handles mixed aspect ratios efficiently
        """
        # Sort materials by area (largest first) for better packing efficiency
        sorted_materials = sorted(material_info, key=lambda x: x['width'] * x['height'], reverse=True)
        
        logger.info(f"Packing {len(sorted_materials)} materials at their actual sizes")
        
        # Use a simple but effective skyline/shelf packing algorithm
        # This handles mixed aspect ratios much better than simple grouping
        placements = {}
        
        # Track shelves (horizontal strips)
        # Each shelf: {'y': int, 'height': int, 'segments': [(x_start, x_end)]}
        shelves = []
        atlas_width = 0
        atlas_height = 0
        
        for info in sorted_materials:
            # Use the actual cropped texture dimensions
            width = info['width']
            height = info['height']
            mat_idx = info['index']
            
            # Try to find a spot in existing shelves
            placed = False
            best_shelf = None
            best_x = None
            best_waste = float('inf')
            
            # Look for best fit in existing shelves
            for shelf in shelves:
                shelf_y = shelf['y']
                shelf_height = shelf['height']
                
                # Can only place if height fits
                if height <= shelf_height:
                    # Find a gap in this shelf that fits our width
                    segments = shelf['segments']
                    
                    for i, (seg_start, seg_end) in enumerate(segments):
                        seg_width = seg_end - seg_start
                        
                        if seg_width >= width:
                            # This segment can fit our material
                            # Calculate waste (height difference in shelf)
                            waste = shelf_height - height
                            
                            if waste < best_waste:
                                best_waste = waste
                                best_shelf = shelf
                                best_x = seg_start
                                placed = True
                            break  # Only use first fitting segment per shelf
            
            # If we found a good spot, place it
            if placed and best_shelf is not None:
                # Place in the best shelf
                shelf_y = best_shelf['y']
                
                # Update segments to mark this space as used
                new_segments = []
                for seg_start, seg_end in best_shelf['segments']:
                    if seg_start == best_x:
                        # Split this segment
                        if seg_start + width < seg_end:
                            # There's remaining space after our material
                            new_segments.append((seg_start + width, seg_end))
                    else:
                        # Keep segment as-is
                        new_segments.append((seg_start, seg_end))
                
                best_shelf['segments'] = new_segments
                
                placements[mat_idx] = {
                    'x': best_x,
                    'y': shelf_y,
                    'width': width,
                    'height': height
                }
                
                atlas_width = max(atlas_width, best_x + width)
                
            else:
                # Create a new shelf at the bottom
                new_shelf_y = atlas_height
                
                placements[mat_idx] = {
                    'x': 0,
                    'y': new_shelf_y,
                    'width': width,
                    'height': height
                }
                
                # Create new shelf
                shelves.append({
                    'y': new_shelf_y,
                    'height': height,
                    'segments': [(width, atlas_width)] if width < atlas_width else []
                })
                
                atlas_width = max(atlas_width, width)
                atlas_height = new_shelf_y + height
            
            logger.debug(f"Placed material {mat_idx} ({width}x{height}) at ({placements[mat_idx]['x']}, {placements[mat_idx]['y']})")
        
        # Ensure minimum size
        atlas_width = max(atlas_width, 64)
        atlas_height = max(atlas_height, 64)
        
        # Calculate packing efficiency
        total_material_area = sum(info['width'] * info['height'] for info in material_info)
        atlas_area = atlas_width * atlas_height
        efficiency = (total_material_area / atlas_area * 100) if atlas_area > 0 else 0
        
        logger.info(f"Calculated atlas size: {atlas_width}x{atlas_height}")
        logger.info(f"Packing efficiency: {efficiency:.1f}% ({total_material_area}/{atlas_area})")
        
        return {
            'width': atlas_width,
            'height': atlas_height,
            'placements': placements
        }
    
    def create_texture_atlas(self, context, joined_mesh, atlas_name):
        """Create a texture atlas from all materials on the mesh and update UVs"""
        logger.info(f"Creating texture atlas for mesh: {joined_mesh.name}")
        
        # Get all materials from the joined mesh
        materials = [mat for mat in joined_mesh.data.materials if mat]
        if not materials:
            logger.warning("No materials found on mesh")
            self.report({'ERROR'}, "No materials found on the selected mesh")
            return None
        
        num_materials = len(materials)
        self.report({'INFO'}, f"Creating atlas from {num_materials} material(s)...")
        
        texture_types = ['diffuse', 'normal', 'roughness', 'alpha']
        
        # Analyze materials to determine texture sizes
        material_info = self.analyze_material_sizes(materials, texture_types, joined_mesh.data)
        
        # Calculate optimal atlas layout with size-based packing
        atlas_layout = self.calculate_atlas_layout(material_info)
        atlas_width = atlas_layout['width']
        atlas_height = atlas_layout['height']
        
        logger.info(f"Atlas resolution: {atlas_width}x{atlas_height}")
        self.report({'INFO'}, f"Atlas resolution: {atlas_width}x{atlas_height}")
        
        # Create atlas images for each texture type
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
            
            if tex_type == 'normal':
                atlas_image.colorspace_settings.name = 'Non-Color'
            elif tex_type == 'roughness':
                atlas_image.colorspace_settings.name = 'Non-Color'
            elif tex_type == 'alpha':
                atlas_image.colorspace_settings.name = 'Non-Color'
            
            # Initialize with default colors
            rgba = np.zeros((atlas_height, atlas_width, 4), dtype=np.float32)
            if tex_type == 'diffuse':
                # Diffuse always has opaque alpha
                rgba[:, :, 3] = 1.0
            elif tex_type == 'normal':
                rgba[:, :, 0] = 0.5  # R
                rgba[:, :, 1] = 0.5  # G
                rgba[:, :, 2] = 1.0  # B (up)
                rgba[:, :, 3] = 1.0  # Alpha
            elif tex_type == 'roughness':
                rgba[:, :, 0] = 0.5  # Default roughness in RGB
                rgba[:, :, 1] = 0.5
                rgba[:, :, 2] = 0.5
                rgba[:, :, 3] = 1.0
            elif tex_type == 'alpha':
                # Default alpha is fully opaque (white)
                rgba[:, :, :] = 1.0

            nparray_to_img(atlas_image, rgba)
            atlas_images[tex_type] = atlas_image
        
        # Build material-to-tile mapping and copy textures into atlas using the layout
        material_uv_mapping = {}  # material_index -> (u_offset, v_offset, u_scale, v_scale, original_uv_bounds)
        
        # Create a lookup for material_info by index
        material_info_by_idx = {info['index']: info for info in material_info}

        for mat_idx, material in enumerate(materials):
            # Get the layout position for this material
            if mat_idx not in atlas_layout['placements']:
                logger.warning(f"Material {mat_idx} has no placement in atlas layout")
                continue
            
            # Get material info (contains UV bounds)
            if mat_idx not in material_info_by_idx:
                logger.warning(f"Material {mat_idx} has no material info")
                continue
            
            mat_info = material_info_by_idx[mat_idx]
            uv_bounds = mat_info['uv_bounds']  # (min_u, min_v, max_u, max_v)
            
            placement = atlas_layout['placements'][mat_idx]
            tile_x = placement['x']
            tile_y = placement['y']
            tile_w = placement['width']
            tile_h = placement['height']

            # UV offsets and scales for this tile
            # Need to account for original UV bounds
            u_offset = tile_x / atlas_width
            v_offset = tile_y / atlas_height
            u_scale = tile_w / atlas_width
            v_scale = tile_h / atlas_height

            material_uv_mapping[mat_idx] = (u_offset, v_offset, u_scale, v_scale, uv_bounds)

            logger.info(f"Material {mat_idx} ({material.name}) -> pos ({tile_x}, {tile_y}) size ({tile_w}x{tile_h})")

            # For each texture type, try to locate a matching source image in the material and copy it into the atlas
            for tex_type in texture_types:
                source_image = None

                if material.use_nodes:
                    # Find a candidate image node by name or connection
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            node_name_lower = node.image.name.lower()
                            # Prefer explicit baked names or type suffixes
                            if f"bake_{tex_type}" in node_name_lower or f"_{tex_type}" in node_name_lower:
                                source_image = node.image
                                break
                    # Fallback: infer by connections
                    if not source_image:
                        links = material.node_tree.links
                        for node in material.node_tree.nodes:
                            if node.type != 'TEX_IMAGE' or not node.image:
                                continue
                            if tex_type == 'diffuse':
                                if any(l.to_socket.name == 'Base Color' and l.from_node == node for l in links):
                                    source_image = node.image
                                    break
                            elif tex_type == 'normal':
                                if any(l.to_node.type == 'NORMAL_MAP' and l.from_node == node for l in links):
                                    source_image = node.image
                                    break
                            elif tex_type == 'roughness':
                                if any(l.to_socket.name == 'Roughness' and l.from_node == node for l in links):
                                    source_image = node.image
                                    break
                            elif tex_type == 'alpha':
                                if any(l.to_socket.name == 'Alpha' and l.from_node == node for l in links):
                                    source_image = node.image
                                    break

                if not source_image or not source_image.has_data:
                    logger.debug(f"No {tex_type} texture found for material '{material.name}', leaving tile blank.")
                    continue

                try:
                    self.copy_texture_to_atlas(
                        source_image,
                        atlas_images[tex_type],
                        tile_x,
                        tile_y,
                        tile_w,
                        tile_h,
                        tex_type,
                        uv_bounds
                    )
                except Exception as e:
                    logger.exception(f"Failed copying {tex_type} for material '{material.name}': {e}")
        
        # Update UVs on the mesh to map to correct atlas tiles
        self.update_uvs_for_atlas(joined_mesh, material_uv_mapping)
        
        # Create new atlas material
        atlas_material = bpy.data.materials.new(name=atlas_name)
        atlas_material.use_nodes = True
        nodes = atlas_material.node_tree.nodes
        links = atlas_material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create material output
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        # Create principled BSDF
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 0)
        bsdf_node.inputs['IOR'].default_value = 1.0
        bsdf_node.inputs['Metallic'].default_value = 0.0
        
        # Create image texture nodes
        diffuse_tex = nodes.new('ShaderNodeTexImage')
        diffuse_tex.image = atlas_images['diffuse']
        diffuse_tex.location = (-400, 300)
        diffuse_tex.label = "Atlas Diffuse"
        
        alpha_tex = nodes.new('ShaderNodeTexImage')
        alpha_tex.image = atlas_images['alpha']
        alpha_tex.location = (-400, 100)
        alpha_tex.label = "Atlas Alpha"
        
        normal_tex = nodes.new('ShaderNodeTexImage')
        normal_tex.image = atlas_images['normal']
        normal_tex.location = (-400, -100)
        normal_tex.label = "Atlas Normal"
        
        roughness_tex = nodes.new('ShaderNodeTexImage')
        roughness_tex.image = atlas_images['roughness']
        roughness_tex.location = (-400, -300)
        roughness_tex.label = "Atlas Roughness"
        
        # Create normal map node
        normal_map = nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-100, -100)
        
        # Link nodes
        links.new(diffuse_tex.outputs['Color'], bsdf_node.inputs['Base Color'])
        links.new(alpha_tex.outputs['Color'], bsdf_node.inputs['Alpha'])  # Use alpha texture for transparency
        links.new(roughness_tex.outputs['Color'], bsdf_node.inputs['Roughness'])
        links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf_node.inputs['Normal'])
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # Replace all materials on mesh with the atlas material
        joined_mesh.data.materials.clear()
        joined_mesh.data.materials.append(atlas_material)
        
        # Save atlas images
        for tex_type, atlas_image in atlas_images.items():
            atlas_image.save()
            logger.info(f"Saved atlas texture: {atlas_image.name}")
        
        logger.info("Texture atlas creation complete")
        self.report({'INFO'}, f"Created {atlas_width}x{atlas_height} atlas with {num_materials} materials")
        
        return atlas_material
    
    def copy_texture_to_atlas(self, source_image, atlas_image, dest_x, dest_y, width, height, tex_type, uv_bounds):
        """Copy a source texture into the atlas at the specified position, cropping to UV bounds"""
        # Read source and atlas pixels as (H, W, 4) arrays
        source_width = source_image.size[0]
        source_height = source_image.size[1]
        atlas_width = atlas_image.size[0]
        atlas_height = atlas_image.size[1]

        # Get pixel data in (height, width, 4) format
        source_pixels = img_as_nparray(source_image)
        atlas_pixels = img_as_nparray(atlas_image)
        
        # Crop to UV bounds
        # UV bounds are in UV space (0-1), convert to pixel coordinates
        min_u, min_v, max_u, max_v = uv_bounds
        
        # Calculate pixel coordinates for cropping (remember V is flipped in image space)
        crop_x_start = int(min_u * source_width)
        crop_x_end = int(max_u * source_width)
        crop_y_start = int(min_v * source_height)
        crop_y_end = int(max_v * source_height)
        
        # Clamp to image bounds
        crop_x_start = max(0, min(crop_x_start, source_width))
        crop_x_end = max(0, min(crop_x_end, source_width))
        crop_y_start = max(0, min(crop_y_start, source_height))
        crop_y_end = max(0, min(crop_y_end, source_height))
        
        # Extract the cropped region
        cropped_pixels = source_pixels[crop_y_start:crop_y_end, crop_x_start:crop_x_end, :]
        cropped_height, cropped_width = cropped_pixels.shape[:2]
        
        if cropped_width == 0 or cropped_height == 0:
            logger.warning(f"Cropped texture has zero size, skipping")
            return
        
        source_pixels = cropped_pixels
        source_width = cropped_width
        source_height = cropped_height
        
        logger.debug(f"Cropped texture from UV bounds ({min_u:.2f}, {min_v:.2f}) to ({max_u:.2f}, {max_v:.2f}): {source_width}x{source_height}")
        
        # For alpha texture type, extract alpha channel to RGB
        if tex_type == 'alpha':
            # Copy alpha channel to RGB channels
            alpha_channel = source_pixels[:, :, 3:4]  # Keep dims (H, W, 1)
            source_pixels = np.concatenate([alpha_channel, alpha_channel, alpha_channel, np.ones_like(alpha_channel)], axis=2)
        
        # For diffuse texture type, force alpha to 1.0
        if tex_type == 'diffuse':
            source_pixels[:, :, 3] = 1.0
        
        # Only resize if the cropped texture doesn't match the allocated atlas space
        # This preserves original quality when possible
        if source_width != width or source_height != height:
            logger.info(f"Resizing texture from {source_width}x{source_height} to {width}x{height}")
            
            # Only resize if we need to fit into a smaller space or if sizes differ significantly
            # Otherwise, we might be wasting space - log a warning
            if source_width > width or source_height > height:
                logger.debug(f"Downscaling texture to fit allocated space")
            else:
                logger.warning(f"Upscaling texture from {source_width}x{source_height} to {width}x{height} - may indicate packing inefficiency")
            
            # Compute source sampling coordinates
            x_ratio = source_width / width
            y_ratio = source_height / height
            xs = np.arange(width, dtype=np.float32) * x_ratio
            ys = np.arange(height, dtype=np.float32) * y_ratio

            x0 = np.floor(xs).astype(np.int32)
            y0 = np.floor(ys).astype(np.int32)
            x1 = np.clip(x0 + 1, 0, source_width - 1)
            y1 = np.clip(y0 + 1, 0, source_height - 1)

            # Expand with a trailing channel axis for broadcasting with (H,W,4)
            wx = (xs - x0)[None, :, None]  # shape (1, W, 1)
            wy = (ys - y0)[:, None, None]  # shape (H, 1, 1)

            # Gather corners using broadcasting
            TL = source_pixels[y0[:, None], x0[None, :], :]  # (H,W,4)
            TR = source_pixels[y0[:, None], x1[None, :], :]  # (H,W,4)
            BL = source_pixels[y1[:, None], x0[None, :], :]  # (H,W,4)
            BR = source_pixels[y1[:, None], x1[None, :], :]  # (H,W,4)

            top = TL * (1.0 - wx) + TR * wx
            bottom = BL * (1.0 - wx) + BR * wx
            source_pixels = top * (1.0 - wy) + bottom * wy
            source_height = height
            source_width = width
        
        # Paste into atlas with y-flip using vectorized slice assignment
        # Clamp region to atlas bounds
        x0 = max(dest_x, 0)
        y0 = max(dest_y, 0)
        x1 = min(dest_x + width, atlas_width)
        y1 = min(dest_y + height, atlas_height)
        if x1 <= x0 or y1 <= y0:
            return

        # Corresponding source region
        sx0 = x0 - dest_x
        sy0 = y0 - dest_y
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)

        # Calculate atlas destination position (no y-flip needed)
        ay_start = dest_y + sy0
        ay_end = dest_y + sy1

        # Assign directly without flipping
        atlas_pixels[ay_start:ay_end, x0:x1, :] = source_pixels[sy0:sy1, sx0:sx1, :]
        
        # Write back to atlas
        nparray_to_img(atlas_image, atlas_pixels)
    
    def update_uvs_for_atlas(self, mesh_obj, material_uv_mapping):
        """Update UV coordinates to map to the correct atlas tiles"""
        logger.info(f"Updating UVs for atlas on mesh: {mesh_obj.name}")
        
        mesh = mesh_obj.data
        uv_layer = mesh.uv_layers.get("UVMap")
        if not uv_layer:
            logger.warning("No UVMap found on mesh")
            return
        
        # Iterate through all polygons and update UVs based on material index
        for poly in mesh.polygons:
            mat_idx = poly.material_index
            if mat_idx not in material_uv_mapping:
                continue
            
            u_offset, v_offset, u_scale, v_scale, uv_bounds = material_uv_mapping[mat_idx]
            min_u, min_v, max_u, max_v = uv_bounds
            uv_range_u = max_u - min_u
            uv_range_v = max_v - min_v
            
            # Avoid division by zero
            if uv_range_u == 0:
                uv_range_u = 1.0
            if uv_range_v == 0:
                uv_range_v = 1.0
            
            # Update UVs for all loops in this polygon
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                
                # First, normalize UV to 0-1 range based on the original UV bounds
                normalized_u = (uv.x - min_u) / uv_range_u
                normalized_v = (uv.y - min_v) / uv_range_v
                
                # Then, scale and offset to fit in the correct atlas tile
                uv.x = normalized_u * u_scale + u_offset
                uv.y = normalized_v * v_scale + v_offset
        
        mesh.update()
        logger.info(f"UVs updated for {len(mesh.polygons)} polygons")