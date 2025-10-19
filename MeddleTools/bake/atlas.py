import bpy
import logging
from bpy.types import Operator
import bmesh
from mathutils import Vector
import math
import numpy as np
import os

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
        
        # Calculate optimal atlas layout
        atlas_cols = math.ceil(math.sqrt(num_materials))
        atlas_rows = math.ceil(num_materials / atlas_cols)
        
        logger.info(f"Atlas layout: {atlas_cols}x{atlas_rows} for {num_materials} materials")
        self.report({'INFO'}, f"Atlas layout: {atlas_cols}x{atlas_rows} grid")
        
        # Determine atlas resolution (find max texture size from all materials)
        max_texture_size = 1024
        texture_types = ['diffuse', 'normal', 'roughness']
        
        for material in materials:
            if not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    max_texture_size = max(max_texture_size, node.image.size[0], node.image.size[1])
        
        # Atlas size per tile
        tile_size = max_texture_size
        atlas_width = tile_size * atlas_cols
        atlas_height = tile_size * atlas_rows
        
        logger.info(f"Atlas resolution: {atlas_width}x{atlas_height} (tile size: {tile_size})")
        
        # ndarray helpers are defined at module scope
        
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
            
            # Initialize with default colors
            rgba = np.zeros((atlas_height, atlas_width, 4), dtype=np.float32)
            if tex_type == 'diffuse':
                rgba[:, :, 3] = 1.0  # Alpha channel 1.0
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

            nparray_to_img(atlas_image, rgba)
            atlas_images[tex_type] = atlas_image
        
        # Build material-to-tile mapping and copy textures into atlas
        material_uv_mapping = {}  # material_index -> (u_offset, v_offset, u_scale, v_scale)

        for mat_idx, material in enumerate(materials):
            # Calculate tile position in atlas
            tile_col = mat_idx % atlas_cols
            tile_row = mat_idx // atlas_cols

            # UV offsets and scales for this tile
            u_offset = tile_col / atlas_cols
            v_offset = tile_row / atlas_rows
            u_scale = 1.0 / atlas_cols
            v_scale = 1.0 / atlas_rows

            material_uv_mapping[mat_idx] = (u_offset, v_offset, u_scale, v_scale)

            logger.info(f"Material {mat_idx} ({material.name}) -> tile ({tile_col}, {tile_row})")

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

                if not source_image or not source_image.has_data:
                    logger.debug(f"No {tex_type} texture found for material '{material.name}', leaving tile blank.")
                    continue

                try:
                    self.copy_texture_to_atlas(
                        source_image,
                        atlas_images[tex_type],
                        tile_col * tile_size,
                        tile_row * tile_size,
                        tile_size,
                        tile_size
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
        diffuse_tex.location = (-400, 200)
        diffuse_tex.label = "Atlas Diffuse"
        
        normal_tex = nodes.new('ShaderNodeTexImage')
        normal_tex.image = atlas_images['normal']
        normal_tex.location = (-400, -100)
        normal_tex.label = "Atlas Normal"
        
        roughness_tex = nodes.new('ShaderNodeTexImage')
        roughness_tex.image = atlas_images['roughness']
        roughness_tex.location = (-400, -400)
        roughness_tex.label = "Atlas Roughness"
        
        # Create normal map node
        normal_map = nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-100, -100)
        
        # Link nodes
        links.new(diffuse_tex.outputs['Color'], bsdf_node.inputs['Base Color'])
        links.new(diffuse_tex.outputs['Alpha'], bsdf_node.inputs['Alpha'])
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
    
    def copy_texture_to_atlas(self, source_image, atlas_image, dest_x, dest_y, width, height):
        """Copy a source texture into the atlas at the specified position"""
        # Read source and atlas pixels as (H, W, 4) arrays
        source_width = source_image.size[0]
        source_height = source_image.size[1]
        atlas_width = atlas_image.size[0]
        atlas_height = atlas_image.size[1]

        # Get pixel data in (height, width, 4) format
        source_pixels = img_as_nparray(source_image)
        atlas_pixels = img_as_nparray(atlas_image)
        
        # Resize source if needed using vectorized bilinear interpolation
        if source_width != width or source_height != height:
            logger.info(f"Resizing texture from {source_width}x{source_height} to {width}x{height}")
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
            
            u_offset, v_offset, u_scale, v_scale = material_uv_mapping[mat_idx]
            
            # Update UVs for all loops in this polygon
            for loop_idx in poly.loop_indices:
                uv = uv_layer.data[loop_idx].uv
                # Scale and offset UV to fit in the correct atlas tile
                uv.x = uv.x * u_scale + u_offset
                uv.y = uv.y * v_scale + v_offset
        
        mesh.update()
        logger.info(f"UVs updated for {len(mesh.polygons)} polygons")