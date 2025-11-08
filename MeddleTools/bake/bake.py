from calendar import c
from . import bake_utils
import bpy
import logging
from bpy.types import Operator
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

def get_bake_label(context):
    """Get dynamic label for RunBake operator based on selection"""
    meshes = bake_utils.get_all_selected_meshes(context)
    distinct_materials = set()
    for mesh in meshes:
        for mat in mesh.data.materials:
            if mat:
                distinct_materials.add(mat.name)
                
    material_count = len(distinct_materials)
    if material_count == 0:
        return "Run Bake (No materials found)"
    elif material_count == 1:
        return f"Run Bake (1 material)"
    else:
        return f"Run Bake ({material_count} materials)"

class RunBake(Operator):
    """Run the baking process for selected objects"""
    bl_idname = "meddle.run_bake"
    bl_label = "Run Bake"
    bl_description = "Run the baking process for selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def update_progress(self, context, progress, message=None):
        """Update progress bar and force UI redraw"""
        wm = context.window_manager
        wm.progress_update(progress)
        if message:
            self.report({'INFO'}, message)
        # Force UI update
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    
    @classmethod
    def poll(cls, context):
        return bpy.data.is_saved and bake_utils.require_mesh_or_armature_selected(context)
    
    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        try:
            # Check if armature is selected
            armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
            mesh_objects = bake_utils.get_all_selected_meshes(context)

            # get all materials used by these mesh objects
            materials = set()
            for mesh in mesh_objects:
                materials.update(mat.name for mat in mesh.data.materials if mat)

            if not materials:
                self.report({'ERROR'}, "No materials found on the mesh objects.")
                return {'CANCELLED'}
            
            logger.info(f"Materials to bake: {materials}")
            
            # Create a collection for baked objects
            self.update_progress(context, 5, "Creating bake collection...")
            collection_name = f"BAKE_{armature.name if armature else 'Meshes'}"
            bake_collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(bake_collection)
            collection_name = bake_collection.name
            logger.info(f"Created collection: {collection_name}")
            
            self.update_progress(context, 10, f"Duplicating and processing {len(mesh_objects)} mesh(es)...")
            (armature_copy, mesh_copies, material_copies) = self.duplicate_armature_and_meshes(context, armature, mesh_objects, materials, bake_collection)
            
            total_materials = len(material_copies)
            current_material = 0
            
            self.update_progress(context, 20, f"Baking {total_materials} material(s)...")
            uv_layer_name = "UVMap"
            for original_name, material_copy in material_copies.items():
                current_material += 1
                # get mesh copies using this material
                meshes_using_material = [mesh for mesh in mesh_copies if material_copy.name in [mat.name for mat in mesh.data.materials if mat]]
                if not meshes_using_material:
                    continue
                if len(meshes_using_material) > 1:
                    raise Exception("Should not reach here, joining handled in duplicate_armature_and_meshes")

                progress = 20 + int((current_material / total_materials) * 50)
                
                # Determine UV layer name based on pack_uv_islands setting
                if context.scene.meddle_settings.pack_uv_islands:
                    self.pack_uv_islands(meshes_using_material[0], "UVMap", "MeddlePackedUVs")
                    uv_layer_name = "MeddlePackedUVs"
                
                self.update_progress(context, progress, f"  Baking material {current_material}/{total_materials}: {original_name}...")
                self.bake_material(context, material_copy, meshes_using_material[0], uv_layer_name)
            
            self.update_progress(context, 70, "Joining all meshes...")
            
            # Join all meshes into one
            for mesh in mesh_copies:
                self.set_active_uv_layer(mesh, uv_layer_name)

            joined_mesh = self.join_all_meshes(context, mesh_copies, armature_copy)
            self.update_progress(context, 95, f"Bake complete! Created collection: {collection_name}")
            self.report({'INFO'}, f"Bake complete! Created collection: {collection_name}")
            return {'FINISHED'}
        finally:
            wm.progress_end()
    
    def join_all_meshes(self, context, mesh_copies, armature_copy):
        """Join all mesh copies into a single mesh"""
        if not mesh_copies:
            logger.warning("No meshes to join")
            return None
        
        if len(mesh_copies) == 1:
            logger.info("Only one mesh, no joining needed")
            return mesh_copies[0]
        
        logger.info(f"Joining {len(mesh_copies)} meshes into one")
        self.report({'INFO'}, f"  Joining {len(mesh_copies)} mesh(es) into one...")
        
        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all mesh copies
        for mesh in mesh_copies:
            mesh.select_set(True)
        
        # Set the first mesh as active
        context.view_layer.objects.active = mesh_copies[0]
        
        # Join the meshes
        bpy.ops.object.join()
        
        joined_mesh = context.view_layer.objects.active
        logger.info(f"Meshes joined into: {joined_mesh.name}")
        
        return joined_mesh
    
    def copy_baked_textures(self, mesh_copies, textures_folder):
        """Copy all baked textures used by the meshes to the textures folder"""
        import shutil
        
        copied_images = set()
        
        for mesh in mesh_copies:
            for mat_slot in mesh.data.materials:
                if not mat_slot or not mat_slot.use_nodes:
                    continue
                
                material = mat_slot
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        image = node.image
                        
                        # Skip if already copied
                        if image.name in copied_images:
                            continue
                        
                        # Only copy images that start with "Bake_"
                        if not image.name.startswith("Bake_"):
                            continue
                        
                        # Get the source path
                        src_path = bpy.path.abspath(image.filepath)
                        
                        # Ensure the image is saved
                        if image.is_dirty or not os.path.exists(src_path):
                            image.filepath_raw = os.path.join(textures_folder, image.name)
                            image.file_format = 'PNG'
                            image.save()
                            logger.info(f"Saved baked texture: {image.name}")
                        else:
                            # Copy the file to textures folder
                            dst_path = os.path.join(textures_folder, os.path.basename(src_path))
                            try:
                                shutil.copy2(src_path, dst_path)
                                logger.info(f"Copied texture {os.path.basename(src_path)} to textures folder")
                            except Exception as e:
                                logger.warning(f"Failed to copy texture {src_path}: {e}")
                        
                        # Update image path to point to textures folder
                        new_path = os.path.join(textures_folder, os.path.basename(image.filepath))
                        image.filepath = new_path
                        
                        copied_images.add(image.name)
        
        logger.info(f"Copied {len(copied_images)} baked texture(s) to {textures_folder}")
        self.report({'INFO'}, f"  Copied {len(copied_images)} texture(s)")
    
    def duplicate_armature_and_meshes(self, context, armature, mesh_objects, materials, bake_collection):        
        # duplicate the armature and mesh objects
        self.report({'INFO'}, f"  Duplicating armature and meshes...")
        armature_copy = None
        if armature:
            armature_copy = armature.copy()
            armature_copy.data = armature.data.copy()
            bake_collection.objects.link(armature_copy)
        
        mesh_bucket = {}
        for mesh in mesh_objects:
            mesh_copy = mesh.copy()
            mesh_copy.data = mesh.data.copy()
            
            # assign to armature copy if it exists
            if armature_copy:
                for mod in mesh_copy.modifiers:
                    if mod.type == 'ARMATURE':
                        mod.object = armature_copy
                # parent to armature copy
                mesh_copy.parent = armature_copy
            
            bake_collection.objects.link(mesh_copy)
            
            # place in bucket with material as key
            mat_key = tuple(sorted(mat.name for mat in mesh_copy.data.materials if mat))
            if mat_key not in mesh_bucket:
                mesh_bucket[mat_key] = []
            mesh_bucket[mat_key].append(mesh_copy)

        # copy materials and rename
        self.report({'INFO'}, f"  Copying {len(materials)} material(s)...")
        material_copies = {}
        for material_name in materials:
            original_material = bpy.data.materials.get(material_name)
            if not original_material:
                continue
            baked_material = original_material.copy()
            baked_material.name = f"BAKE_{material_name}"
            logger.info(f"Created baked material: {baked_material.name}")
            material_copies[material_name] = baked_material
        
        # join meshes in each bucket
        self.report({'INFO'}, f"  Joining and processing meshes...")
        joined_meshes = []
        total_buckets = len(mesh_bucket)
        current_bucket = 0
        for mat_names, meshes in mesh_bucket.items():
            current_bucket += 1
            joined_mesh = None
            if len(meshes) > 1:
                self.report({'INFO'}, f"    Joining {len(meshes)} mesh(es) ({current_bucket}/{total_buckets})...")
                bpy.ops.object.select_all(action='DESELECT')
                # Set active object ONCE before selecting others
                context.view_layer.objects.active = meshes[0]
                for mesh in meshes:
                    mesh.select_set(True)
                bpy.ops.object.join()
                joined_mesh = context.view_layer.objects.active
                logger.info(f"Joined {len(meshes)} meshes into {joined_mesh.name} with materials {mat_names}")
            else:
                joined_mesh = meshes[0]
            
            self.report({'INFO'}, f"    Merging vertices by UV ({current_bucket}/{total_buckets})...")
            # Ensure UV layer exists before merging
            if not self.ensure_uv_layer(joined_mesh, "UVMap"):
                self.report({'ERROR'}, f"Failed to create UVs for {joined_mesh.name}")
                return (None, [], {})
            
            joined_meshes.append(joined_mesh)
                
        # assign bake materials to mesh copies
        for mesh_copy in joined_meshes:
            for i, mat in enumerate(mesh_copy.data.materials):
                if mat and mat.name in material_copies:
                    mesh_copy.data.materials[i] = material_copies[mat.name]

        # position armature/meshes to side of original for viewing
        if armature_copy:
            armature_copy.location.x += 1.0
        else:
            # If no armature, offset all joined meshes
            for mesh in joined_meshes:
                mesh.location.x += 1.0

        return (armature_copy, joined_meshes, material_copies)
    
    def set_active_uv_layer(self, mesh, uv_layer_name):
        """Set the active UV layer on the mesh"""
        if uv_layer_name in mesh.data.uv_layers:
            uv_layer = mesh.data.uv_layers[uv_layer_name];
            mesh.data.uv_layers.active = uv_layer
            uv_layer.active_render = True
            logger.info(f"Set active UV layer to {uv_layer_name} on mesh {mesh.name}")
            return True
        else:
            logger.warning(f"UV layer {uv_layer_name} not found on mesh {mesh.name}")
            return False
    
    def pack_uv_islands(self, mesh, uv_layer_name, new_uv_layer_name):
        """Pack UV islands into a new UV layer"""
        # Ensure the specified UV layer exists
        if uv_layer_name not in mesh.data.uv_layers:
            logger.warning(f"UV layer {uv_layer_name} not found on mesh {mesh.name}")
            return False
        
        # ensure only the mesh is selected
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        
        # Create a new UV layer for packed UVs
        if new_uv_layer_name in mesh.data.uv_layers:
            # remove existing packed UV layer
            mesh.data.uv_layers.remove(mesh.data.uv_layers[new_uv_layer_name])
        
        # Get the source UV layer
        source_uv_layer = mesh.data.uv_layers[uv_layer_name]
        
        # Create new UV layer and copy data from source
        packed_uv_layer = mesh.data.uv_layers.new(name=new_uv_layer_name)
        
        # Copy UV data from source layer to packed layer
        for loop_idx in range(len(mesh.data.loops)):
            packed_uv_layer.data[loop_idx].uv = source_uv_layer.data[loop_idx].uv.copy()
        
        # Set the new layer as active for packing
        mesh.data.uv_layers.active = packed_uv_layer
        # Pack UV islands
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM',
                                rotate=False,
                                scale=True,
                                merge_overlap=False,
                                margin_method='SCALED',
                                margin=0.001,
                                pin=False,
                                shape_method='CONCAVE')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        logger.info(f"Packed UV islands into layer {new_uv_layer_name} on mesh {mesh.name}")        
        return True

    def bake_material(self, context, material, joined_mesh, uv_layer_name):
        logger.info(f"Baking material: {material.name}")
        # check for principled BSDF node
        if not material.use_nodes:
            logger.warning(f"Material {material.name} does not use nodes. Skipping bake.")
            return
        
        principled_nodes = [node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED']
        if not principled_nodes:
            logger.warning(f"Material {material.name} has no Principled BSDF node. Skipping bake.")
            return
        
        
        material_output_node = next((node for node in material.node_tree.nodes if node.type == 'OUTPUT_MATERIAL'), None)
        if not material_output_node:
            logger.warning(f"Material {material.name} has no Material Output node. Skipping bake.")
            return
        
        original_nodes = list(material.node_tree.nodes)
        # remove material_output_node from list
        original_nodes.remove(material_output_node)
        
        def createBakeBsdfNode():
            # duplicate the principled node for baking
            bake_node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            bake_node.location = (material_output_node.location.x - 300, material_output_node.location.y)
            bake_node.label = f"Bake_{material.name}"
            # fix defaults            
            bake_node.inputs['IOR'].default_value = 1
            bake_node.inputs['Metallic'].default_value = 0.0
            bake_node.inputs['Roughness'].default_value = 0.5
            bake_node.inputs['Base Color'].default_value = (1.0, 1.0, 1.0, 1.0)

            return bake_node
        
        def determineLargestImage():
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
            return (max_width * 2, max_height * 2)
        
        max_image_size = determineLargestImage()
        
        # bake passes
        image_nodes = []
        diffuse_image = self.bake_pass(context, material, joined_mesh, 'diffuse', max_image_size, uv_layer_name)
        normal_image = self.bake_pass(context, material, joined_mesh, 'normal', max_image_size, uv_layer_name)
        roughness_image = self.bake_pass(context, material, joined_mesh, 'roughness', max_image_size, uv_layer_name)
        image_nodes.append(diffuse_image)
        image_nodes.append(normal_image)
        image_nodes.append(roughness_image)

        # trigger save of baked images
        for img_node in image_nodes:
            if img_node.image and img_node.image.has_data:
                img_node.image.save()

        duplicate_node = createBakeBsdfNode()
        
        # link image node to duplicate_node
        material.node_tree.links.new(diffuse_image.outputs['Color'], duplicate_node.inputs['Base Color'])
        material.node_tree.links.new(diffuse_image.outputs['Alpha'], duplicate_node.inputs['Alpha'])
        # material.node_tree.links.new(alpha_image.outputs['Alpha'], duplicate_node.inputs['Alpha'])
        material.node_tree.links.new(roughness_image.outputs['Color'], duplicate_node.inputs['Roughness'])
        
        # run normal through normal map node
        normal_map_node = material.node_tree.nodes.new('ShaderNodeNormalMap')
        normal_map_node.location = (duplicate_node.location.x - 300, duplicate_node.location.y - 200)
        material.node_tree.links.new(normal_image.outputs['Color'], normal_map_node.inputs['Color'])
        material.node_tree.links.new(normal_map_node.outputs['Normal'], duplicate_node.inputs['Normal'])

        # link duplicate_node output to material output
        material.node_tree.links.new(duplicate_node.outputs['BSDF'], material_output_node.inputs['Surface'])
        
        # set image node locations
        for i, img_node in enumerate(image_nodes):
            img_node.location = (duplicate_node.location.x - 600, duplicate_node.location.y - i * 200)
        
        for node in original_nodes:
            material.node_tree.nodes.remove(node)

    def bake_pass(self, context, material, mesh, bake_name, max_image_size, uv_layer_name):        
        logger.info(f"Baking pass: {bake_name} for material: {material.name}")
        
        # Get bake pass configuration from utility function
        pass_config = bake_utils.get_bake_pass_config(bake_name)
        if not pass_config:
            raise ValueError(f"Unsupported bake type: {bake_name}")
        
        bake_type = pass_config['bake_type']
        background_color = pass_config['background_color']
        bake_pass_filter = pass_config['pass_filter']
        required_inputs = pass_config['required_inputs']
        alpha_mode = pass_config['alpha_mode']
        colorspace = pass_config['colorspace']
        
        clear = True
        selected_to_active = False
        normal_space = "TANGENT"
        bake_margin = bake_utils.calculate_bake_margin(max_image_size)
        remap_target_socket_name = None
        logger.info(f"Bake margin set to: {bake_margin} pixels")

        def create_bake_image(bake_name, background_color, width, height, alpha_mode, colorspace):
            file_name = f"Bake_{bake_name}_{material.name}.png"
            image = bpy.data.images.new(name=file_name, 
                    width=width, height=height, alpha=True)
            image.filepath = bpy.path.abspath(f"//Bake/{file_name}")
            image.alpha_mode = alpha_mode
            image.scale(width, height)
            image.generated_color = background_color
            image.colorspace_settings.name = colorspace
            
            return image
        
        # create image texture node and link to bake_node
        image_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        image = None
        if bake_name == 'normal':
            # workaround for now
            # find g_SamplerNormal_PngCachePath and just use that image instead of baking
            normal_image = None
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and "g_SamplerNormal_PngCachePath" in node.label:
                    normal_image = node.image
                    break
            
            if normal_image and normal_image.has_data and uv_layer_name == "UVMap" and False: # Can only do workaround if using original UVs
                def img_channels_as_nparray(image):
                    pixel_buffer = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
                    image.pixels.foreach_get(pixel_buffer)
                    return pixel_buffer.reshape(4, -1, order='F')
                def nparray_channels_to_img(image, nparr):
                    assert(nparr.shape[0] == 4)
                    assert(nparr.shape[1] == image.size[0] * image.size[1])
                    image.pixels.foreach_set(np.ravel(nparr, order='F'))
                
                # copied_image.filepath = bpy.path.abspath(f"//Bake/{copied_image.name}.png")
                
                pixel_data = img_channels_as_nparray(normal_image)
                # zero out blue and alpha channels
                pixel_data[2, :] = 1.0  # Blue channel
                pixel_data[3, :] = 1.0  # Alpha channel
                
                copied_image = create_bake_image(bake_name, background_color, normal_image.size[0], normal_image.size[1], alpha_mode, colorspace)
                
                nparray_channels_to_img(copied_image, pixel_data)

                image_node.image = copied_image
                return image_node
            else:
                # Use standard baking for normal map
                image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1], alpha_mode, colorspace)
                image_node.image = image
        else:
            # Standard baking for other passes (diffuse, roughness, etc.)
            image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1], alpha_mode, colorspace)
            image_node.image = image
        
        
        # For non-color/normal channels, remap the input to Emission for more reliable baking
        # Emission is better for scalar values that can exceed 0-1 range or need precise preservation
        remapped_inputs = []
        
        if remap_target_socket_name:
            for node in material.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    for required_input_name in required_inputs:
                        input_socket = node.inputs.get(required_input_name)
                        if input_socket and input_socket.is_linked:
                            # Store the original connection
                            for link in input_socket.links:
                                from_node = link.from_node
                                from_socket = link.from_socket
                                
                                # Disconnect from original input
                                material.node_tree.links.remove(link)
                                
                                # Connect to Emission instead
                                target_socket = node.inputs.get(remap_target_socket_name)
                                if target_socket:
                                    material.node_tree.links.new(from_socket, target_socket)
                                    
                                    # Store for restoration
                                    remapped_inputs.append((input_socket, from_node, from_socket, target_socket))
                                    logger.info(f"Remapped {required_input_name} to {remap_target_socket_name} for {bake_name} bake")
        
        # for each bsdf node, disconnect all inputs except those needed for bake, then re-connect after bake
        # this is to prevent other inputs from affecting the bake result
        disconnect_inputs = []
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                for input_socket in node.inputs:
                    # For remapped bakes, keep the target socket connected; for normal bakes, keep required inputs
                    if remapped_inputs:
                        inputs_to_keep = [remap_target_socket_name] if remap_target_socket_name else []
                    else:
                        inputs_to_keep = required_inputs
                    
                    if input_socket.name not in inputs_to_keep:
                        # disconnect
                        for link in input_socket.links:
                            from_node = link.from_node
                            from_socket = link.from_socket
                            disconnect_inputs.append((input_socket, from_node, from_socket))
                            material.node_tree.links.remove(link)         
        
        # ensure image is active
        material.node_tree.nodes.active = image_node        
        
        # deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        # select the mesh to bake
        mesh.select_set(True)
        context.view_layer.objects.active = mesh
        
        # Setup bake settings using utility function
        bake_utils.setup_bake_settings(
            context,
            bake_type,
            bake_pass_filter,
            bake_margin,
            samples=context.scene.meddle_settings.bake_samples,
            use_clear=clear
        )
        # Note: We still need to set selected_to_active since it's not standard
        context.scene.render.bake.use_selected_to_active = selected_to_active               
        
        try:
            bpy.ops.object.bake(type=bake_type,
                                # pass_filter=bake_pass_filter,
                                use_clear=context.scene.render.bake.use_clear,
                                uv_layer=uv_layer_name,
                                use_selected_to_active=context.scene.render.bake.use_selected_to_active,
                                cage_extrusion=0,
                                normal_space=normal_space
                                )
        except Exception as e:
            logger.error(f"Bake failed for material {material.name}, pass {bake_name}: {e}")
            raise e
        
        # First, restore remapped inputs (disconnect from temporary target and reconnect to original socket)
        for original_socket, from_node, from_socket, temp_target_socket in remapped_inputs:
            # Remove the temporary connection (e.g., from Emission)
            for link in temp_target_socket.links:
                if link.from_socket == from_socket:
                    material.node_tree.links.remove(link)
                    break
            
            # Restore original connection
            material.node_tree.links.new(from_socket, original_socket)
            logger.info(f"Restored {original_socket.name} connection after {bake_name} bake")
        
        # Then, reconnect previously disconnected inputs using utility function
        bake_utils.reconnect_inputs(disconnect_inputs)
        
        return image_node

    def ensure_uv_layer(self, mesh_obj, uv_layer_name="UVMap"):
        """Ensure the mesh has a UV layer, create one if missing"""
        
        if uv_layer_name in mesh_obj.data.uv_layers:
            return True
        
        logger.info(f"UV layer '{uv_layer_name}' not found for {mesh_obj.name}, generating UVs...")
        self.report({'WARNING'}, f"  Mesh {mesh_obj.name} has no UVs, generating smart UV projection...")
        
        # Select only this mesh
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        
        # Switch to edit mode and select all
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Generate Smart UV Project
        try:
            bpy.ops.uv.smart_project(
                angle_limit=66.0,
                island_margin=0.02,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=False
            )
            logger.info(f"Successfully generated UVs for {mesh_obj.name}")
        except Exception as e:
            logger.error(f"Failed to generate UVs for {mesh_obj.name}: {e}")
            bpy.ops.object.mode_set(mode='OBJECT')
            return False
        
        # Return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Verify UV layer was created
        if uv_layer_name not in mesh_obj.data.uv_layers:
            # If default name doesn't exist, rename the first UV layer
            if len(mesh_obj.data.uv_layers) > 0:
                mesh_obj.data.uv_layers[0].name = uv_layer_name
                logger.info(f"Renamed UV layer to '{uv_layer_name}'")
            else:
                logger.error(f"Failed to create UV layer for {mesh_obj.name}")
                return False
        
        return True