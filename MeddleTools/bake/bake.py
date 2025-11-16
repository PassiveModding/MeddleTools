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
            mesh_objects = bake_utils.get_all_selected_meshes(context)

            # Get all materials used by these mesh objects
            materials = {}
            for mesh in mesh_objects:
                for mat in mesh.data.materials:
                    if mat:
                        materials[mat.name] = mat

            if not materials:
                self.report({'ERROR'}, "No materials found on the mesh objects.")
                return {'CANCELLED'}
            
            logger.info(f"Materials to bake: {list(materials.keys())}")
            
            # Bake each material
            total_materials = len(materials)
            current_material = 0
            
            self.update_progress(context, 20, f"Baking {total_materials} material(s)...")
            for material_name, material in materials.items():
                current_material += 1
                # Get mesh using this material
                meshes_using_material = [mesh for mesh in mesh_objects if material.name in [mat.name for mat in mesh.data.materials if mat]]
                if not meshes_using_material:
                    continue
                if len(meshes_using_material) > 1:
                    logger.warning(f"Multiple meshes found with material {material.name}, using first one")

                # Determine UV layer name for this specific mesh
                mesh_to_bake = meshes_using_material[0]
                uv_layer_name = "UVMap"
                if "MeddlePackedUVs" in mesh_to_bake.data.uv_layers:
                    uv_layer_name = "MeddlePackedUVs"
                    logger.info(f"Using MeddlePackedUVs layer for baking material {material.name} on mesh {mesh_to_bake.name}")
                else:
                    logger.info(f"Using UVMap layer for baking material {material.name} on mesh {mesh_to_bake.name}")

                progress = 20 + int((current_material / total_materials) * 70)                
                self.update_progress(context, progress, f"  Baking material {current_material}/{total_materials}: {material_name}...")
                self.bake_material(context, material, mesh_to_bake, uv_layer_name)
                bake_utils.set_active_uv_layer(mesh_to_bake, uv_layer_name)
            
            self.update_progress(context, 95, "Bake complete!")
            self.report({'INFO'}, "Bake complete!")
            return {'FINISHED'}
        finally:
            wm.progress_end()
    
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
        
        # Get bake material configuration
        bake_config = bake_utils.get_bake_material_config()
        
        def createBakeBsdfNode():
            # duplicate the principled node for baking
            bake_node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            bake_node.location = (material_output_node.location.x - 300, material_output_node.location.y)
            bake_node.label = f"Bake_{material.name}"
            
            # Apply default values from config
            for input_name, value in bake_config['bsdf_defaults'].items():
                if input_name in bake_node.inputs:
                    bake_node.inputs[input_name].default_value = value

            return bake_node
        
        # Get image size from material settings
        settings = bake_utils.get_mat_settings_by_name(context.scene.meddle_settings, material.name)
        max_image_size = (settings.image_width, settings.image_height) if settings else bake_utils.determine_largest_image_size(material)

        # Bake passes from config
        baked_images = {}
        for pass_name in bake_config['bake_passes']:
            image_node = self.bake_pass(context, material, joined_mesh, pass_name, max_image_size, uv_layer_name)
            baked_images[pass_name] = image_node
            
            # Trigger save of baked image
            if image_node.image and image_node.image.has_data:
                image_node.image.save()

        # Create baked BSDF node
        duplicate_node = createBakeBsdfNode()
        
        # Create special nodes (like normal map)
        special_nodes = {'bsdf': duplicate_node, 'output': material_output_node}
        for node_key, node_config in bake_config['special_nodes'].items():
            node = material.node_tree.nodes.new(node_config['type'])
            location_offset = node_config['location_offset']
            node.location = (duplicate_node.location.x + location_offset[0], 
                           duplicate_node.location.y + location_offset[1])
            
            # Set node operation if specified (for math nodes)
            if 'operation' in node_config:
                node.operation = node_config['operation']
            
            # Set node inputs if specified
            if 'inputs' in node_config:
                for input_index, value in node_config['inputs'].items():
                    node.inputs[input_index].default_value = value
            
            special_nodes[node_key] = node
        
        # Connect nodes according to config
        for from_key, from_output, to_key, to_input in bake_config['node_connections']:
            if from_key in baked_images:
                from_node = baked_images[from_key]
            elif from_key in special_nodes:
                from_node = special_nodes[from_key]
            else:
                continue
                
            if to_key in special_nodes:
                to_node = special_nodes[to_key]
            else:
                continue
                
            material.node_tree.links.new(from_node.outputs[from_output], to_node.inputs[to_input])
        
        # Set image node locations
        for i, (pass_name, img_node) in enumerate(baked_images.items()):
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
        
        # validate to clear linting errors
        # Ensure required_inputs is str[]
        assert isinstance(required_inputs, list)
        
        clear = True
        selected_to_active = False
        normal_space = "TANGENT"
        bake_margin = bake_utils.calculate_bake_margin(max_image_size)        
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
        image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1], alpha_mode, colorspace)
        image_node.image = image
        
        # Track all original connections for all BSDF nodes
        original_connections = []
        temp_nodes = []
        
        # Store all connections for BSDF nodes before any modifications
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            original_connections.append({
                                'input_socket': input_socket,
                                'from_node': link.from_node,
                                'from_socket': link.from_socket,
                                'input_name': input_socket.name
                            })
        
        # Check if this pass requires remapping to Emission
        remap_target_socket_name = None
        ior_to_emission = False
        if pass_config.get('custom_mapping') == 'EmissionStrength':
            remap_target_socket_name = 'Emission Strength'
        elif pass_config.get('custom_mapping') == 'IORToEmissionStrength':
            remap_target_socket_name = 'Emission Strength'
            ior_to_emission = True
        
        # Now disconnect everything and reconnect only what's needed for baking
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                # Disconnect all inputs
                for input_socket in node.inputs:
                    for link in list(input_socket.links):
                        material.node_tree.links.remove(link)
                
                # Reconnect only the required inputs for this bake pass
                for conn in original_connections:
                    if conn['input_name'] in required_inputs:
                        if remap_target_socket_name:
                            # Remap to emission for special passes
                            target_socket = node.inputs.get(remap_target_socket_name)
                            if target_socket:
                                if ior_to_emission:
                                    # Create a Math node to remap IOR to Emission Strength
                                    math_node = material.node_tree.nodes.new('ShaderNodeMath')
                                    math_node.operation = 'SUBTRACT'
                                    math_node.inputs[1].default_value = 1.0
                                    math_node.location = (conn['from_node'].location.x + 200, conn['from_node'].location.y)
                                    
                                    material.node_tree.links.new(conn['from_socket'], math_node.inputs[0])
                                    material.node_tree.links.new(math_node.outputs[0], target_socket)
                                    temp_nodes.append(math_node)
                                    logger.info(f"Remapped {conn['input_name']} to {remap_target_socket_name} via Math node for {bake_name} bake")
                                else:
                                    material.node_tree.links.new(conn['from_socket'], target_socket)
                                    logger.info(f"Remapped {conn['input_name']} to {remap_target_socket_name} for {bake_name} bake")
                        else:
                            # Normal connection for standard bake passes
                            material.node_tree.links.new(conn['from_socket'], conn['input_socket'])         
        
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

        # Clean up temporary nodes
        for temp_node in temp_nodes:
            material.node_tree.nodes.remove(temp_node)

        # Restore all original connections
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                # Disconnect all current connections
                for input_socket in node.inputs:
                    for link in list(input_socket.links):
                        material.node_tree.links.remove(link)
        
        # Reconnect all original connections
        for conn in original_connections:
            material.node_tree.links.new(conn['from_socket'], conn['input_socket'])
        
        logger.info(f"Restored {len(original_connections)} original connection(s) after {bake_name} bake")
        
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