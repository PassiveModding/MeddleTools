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

class ReprojectRebake(Operator):
    bl_idname = "object.reproject_rebake"
    bl_label = "Reproject and Rebake Atlassed Textures"
    bl_description = "Reproject UVs and rebake atlassed materials to new 4K textures. Only works on materials created with 'Create Atlas from Selection'"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if not bpy.data.is_saved or not bake_utils.require_mesh_or_armature_selected(context):
            return False
        
        # Check if any selected mesh has atlassed materials
        selected_meshes = bake_utils.get_all_selected_meshes(context)
        for mesh_obj in selected_meshes:
            if cls.has_atlassed_materials(mesh_obj):
                return True
        
        return False
    
    @staticmethod
    def has_atlassed_materials(mesh_obj):
        """Check if mesh has materials created by the atlas operator"""
        for mat_slot in mesh_obj.material_slots:
            if mat_slot.material and mat_slot.material.name.startswith("Atlas_"):
                return True
        return False
    
    def execute(self, context):
        selected_meshes = bake_utils.get_all_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected.")
            return {'CANCELLED'}
        
        # Filter meshes to only those with atlassed materials
        atlassed_meshes = [mesh for mesh in selected_meshes if self.has_atlassed_materials(mesh)]
        
        if not atlassed_meshes:
            self.report({'WARNING'}, "No meshes with atlassed materials selected. Materials must be created with 'Create Atlas from Selection' first.")
            return {'CANCELLED'}
        
        logger.info(f"Starting Reproject and Rebake for {len(atlassed_meshes)} mesh(es) with atlassed materials")
        
        # Process each mesh
        for mesh_obj in atlassed_meshes:
            self.report({'INFO'}, f"Processing mesh: {mesh_obj.name}")
            
            # Step 1: Create new UV map and reproject
            if not self.reproject_uvs(context, mesh_obj):
                self.report({'WARNING'}, f"Failed to reproject UVs for {mesh_obj.name}")
                continue
            
            # Step 2: Bake materials to new 4K textures
            if not self.rebake_materials(context, mesh_obj):
                self.report({'WARNING'}, f"Failed to rebake materials for {mesh_obj.name}")
                continue
            
            self.report({'INFO'}, f"Successfully processed {mesh_obj.name}")
        
        # set new UV map as active for all processed meshes
        for mesh_obj in atlassed_meshes:
            mesh = mesh_obj.data
            if "ReprojectedUVs" in mesh.uv_layers:
                mesh.uv_layers.active = mesh.uv_layers["ReprojectedUVs"]
                logger.info(f"Set ReprojectedUVs as active UV map for {mesh_obj.name}")
        
        self.report({'INFO'}, "Reproject and Rebake completed")
        return {'FINISHED'}
    
    def reproject_uvs(self, context, mesh_obj):
        """Create a new UV map named 'ReprojectedUVs' and reproject using Smart UV Project"""
        logger.info(f"Reprojecting UVs for {mesh_obj.name}")
        
        mesh = mesh_obj.data
        
        # Create or get the ReprojectedUVs layer
        uv_layer_name = "ReprojectedUVs"
        if uv_layer_name in mesh.uv_layers:
            logger.info(f"UV layer '{uv_layer_name}' already exists, removing it")
            uv_layer = mesh.uv_layers[uv_layer_name]
            mesh.uv_layers.remove(uv_layer)
        
        # Create new UV layer
        new_uv_layer = mesh.uv_layers.new(name=uv_layer_name)
        mesh.uv_layers.active = new_uv_layer
        logger.info(f"Created new UV layer: {uv_layer_name}")
        
        # Select only this mesh
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        context.view_layer.objects.active = mesh_obj
        
        # Switch to edit mode and select all
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Generate Smart UV Project
        try:
            # bpy.ops.uv.smart_project(
            #     angle_limit=66.0,
            #     island_margin=0.00,
            #     area_weight=0.0,
            #     correct_aspect=True,
            #     scale_to_bounds=True,
            #     margin_method="SCALED",
            #     rotate_method="AXIS_ALIGNED"
            # )
            # logger.info(f"Smart UV projection completed for {mesh_obj.name}")
            # use unwrap angle based
            bpy.ops.uv.unwrap(
                method='ANGLE_BASED',
                margin=0.001,
                no_flip=True,
                correct_aspect=True,
                fill_holes=True
            )
        except Exception as e:
            logger.error(f"Failed to generate Smart UV projection: {e}")
            bpy.ops.object.mode_set(mode='OBJECT')
            return False
        
        # Return to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return True
    
    def rebake_materials(self, context, mesh_obj):
        """Bake all atlassed materials to new 4K textures using the ReprojectedUVs"""
        logger.info(f"Rebaking materials for {mesh_obj.name}")
        
        mesh = mesh_obj.data
        
        # Verify ReprojectedUVs exists
        if "ReprojectedUVs" not in mesh.uv_layers:
            logger.error(f"ReprojectedUVs not found for {mesh_obj.name}")
            return False
        
        # Set ReprojectedUVs as active
        mesh.uv_layers.active = mesh.uv_layers["ReprojectedUVs"]
        
        # Process each atlassed material slot
        processed_any = False
        for mat_slot in mesh_obj.material_slots:
            if not mat_slot.material:
                continue
            
            material = mat_slot.material
            
            # Only process atlassed materials
            if not material.name.startswith("Atlas_"):
                logger.info(f"Skipping non-atlassed material: {material.name}")
                continue
            
            logger.info(f"Processing atlassed material: {material.name}")
            
            # Validate material structure (should only have textures, normal map, BSDF, and material output)
            if not self.validate_material_structure(material):
                self.report({'WARNING'}, f"Material {material.name} does not meet preconditions (should only contain textures, normal map, BSDF, and material output)")
                continue
            
            # Bake the material
            if not self.bake_material_to_4k(context, material, mesh_obj):
                logger.error(f"Failed to bake material: {material.name}")
                continue
            
            processed_any = True
        
        if not processed_any:
            logger.warning(f"No atlassed materials found to process on {mesh_obj.name}")
            return False
        
        return True
    
    def validate_material_structure(self, material):
        """Validate that material only contains textures, normal mapping node, BSDF, and material output"""
        if not material.use_nodes:
            return False
        
        allowed_node_types = {
            'TEX_IMAGE',           # Texture nodes
            'NORMAL_MAP',          # Normal mapping node
            'BSDF_PRINCIPLED',     # Principled BSDF
            'OUTPUT_MATERIAL',     # Material output
            'REROUTE'              # Allow reroute nodes for organization
        }
        
        for node in material.node_tree.nodes:
            if node.type not in allowed_node_types:
                logger.warning(f"Material {material.name} contains unsupported node type: {node.type}")
                return False
        
        return True
    
    def bake_material_to_4k(self, context, material, mesh_obj):
        """Bake material to new 4K textures"""
        logger.info(f"Baking material {material.name} to 4K textures")
        
        # Check for Principled BSDF
        principled_node = None
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled_node = node
                break
        
        if not principled_node:
            logger.warning(f"No Principled BSDF found in material {material.name}")
            return False
        
        # Target resolution: 4K
        target_size = (4096, 4096)
        bake_margin = bake_utils.calculate_bake_margin(target_size)
        
        # Bake passes
        passes_to_bake = ['diffuse', 'normal', 'roughness']
        baked_images = {}
        
        for pass_name in passes_to_bake:
            logger.info(f"Baking {pass_name} pass for {material.name}")
            
            # Get pass configuration
            config = bake_utils.get_bake_pass_config(pass_name)
            if not config:
                logger.error(f"Unknown bake pass: {pass_name}")
                continue
            
            # Create new 4K image with proper settings
            image_name = f"REBAKE_{pass_name.capitalize()}_{material.name}"
            image = bake_utils.create_bake_image(
                name=image_name,
                width=target_size[0],
                height=target_size[1],
                background_color=config['background_color'],
                alpha_mode=config['alpha_mode'],
                colorspace=config['colorspace']
            )
            
            # Create image texture node for baking
            image_node = material.node_tree.nodes.new('ShaderNodeTexImage')
            image_node.image = image
            image_node.label = f"REBAKE_{pass_name.capitalize()}"
            material.node_tree.nodes.active = image_node
            
            # Disconnect inputs that aren't needed for this bake pass
            disconnect_inputs = bake_utils.disconnect_bsdf_inputs(material, config['required_inputs'])
            
            # Select the mesh
            bpy.ops.object.select_all(action='DESELECT')
            mesh_obj.select_set(True)
            context.view_layer.objects.active = mesh_obj
            
            # Setup bake settings
            samples = context.scene.meddle_settings.bake_samples if hasattr(context.scene, 'meddle_settings') else 32
            bake_utils.setup_bake_settings(
                context,
                config['bake_type'],
                config['pass_filter'],
                bake_margin,
                samples=samples,
                use_clear=True
            )
            
            # Perform bake
            try:
                bpy.ops.object.bake(
                    type=config['bake_type'],
                    use_clear=True,
                    uv_layer="ReprojectedUVs",
                    use_selected_to_active=False,
                    cage_extrusion=0,
                    normal_space='TANGENT'
                )
                logger.info(f"Successfully baked {pass_name} pass")
                
                # Save the image
                os.makedirs(os.path.dirname(image.filepath), exist_ok=True)
                image.save()
                logger.info(f"Saved baked image to: {image.filepath}")
                
                baked_images[pass_name.capitalize()] = image_node
            except Exception as e:
                logger.error(f"Failed to bake {pass_name} pass: {e}")
                material.node_tree.nodes.remove(image_node)
                # Reconnect disconnected inputs before continuing
                bake_utils.reconnect_inputs(disconnect_inputs)
                continue
            
            # Reconnect previously disconnected inputs
            bake_utils.reconnect_inputs(disconnect_inputs)
        
        # Clean up and reconnect nodes with baked textures
        if baked_images:
            self.reconnect_baked_textures(material, baked_images, principled_node)
        
        # Set ReprojectedUVs as the active UV map after baking
        mesh = mesh_obj.data
        if "ReprojectedUVs" in mesh.uv_layers:
            mesh.uv_layers.active = mesh.uv_layers["ReprojectedUVs"]
            logger.info(f"Set ReprojectedUVs as active UV map for {mesh_obj.name}")
        
        return True
    
    def reconnect_baked_textures(self, material, baked_images, principled_node):
        """Reconnect the material using only the baked textures"""
        logger.info(f"Reconnecting baked textures for material {material.name}")
        
        # Find material output
        material_output = None
        for node in material.node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                material_output = node
                break
        
        if not material_output:
            logger.error("No material output found")
            return
        
        # Remove all nodes except the baked image nodes and material output
        nodes_to_keep = set([material_output] + list(baked_images.values()))
        nodes_to_remove = [node for node in material.node_tree.nodes if node not in nodes_to_keep]
        
        for node in nodes_to_remove:
            material.node_tree.nodes.remove(node)
        
        # Create new Principled BSDF
        new_bsdf = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        new_bsdf.location = (material_output.location.x - 300, material_output.location.y)
        new_bsdf.inputs['IOR'].default_value = 1.0
        new_bsdf.inputs['Metallic'].default_value = 0.0
        
        # Connect baked textures
        if 'Diffuse' in baked_images:
            diffuse_node = baked_images['Diffuse']
            diffuse_node.location = (new_bsdf.location.x - 600, new_bsdf.location.y)
            material.node_tree.links.new(diffuse_node.outputs['Color'], new_bsdf.inputs['Base Color'])
            material.node_tree.links.new(diffuse_node.outputs['Alpha'], new_bsdf.inputs['Alpha'])
        
        if 'Roughness' in baked_images:
            roughness_node = baked_images['Roughness']
            roughness_node.location = (new_bsdf.location.x - 600, new_bsdf.location.y - 200)
            material.node_tree.links.new(roughness_node.outputs['Color'], new_bsdf.inputs['Roughness'])
        
        if 'Normal' in baked_images:
            normal_node = baked_images['Normal']
            normal_node.location = (new_bsdf.location.x - 600, new_bsdf.location.y - 400)
            
            # Create normal map node
            normal_map = material.node_tree.nodes.new('ShaderNodeNormalMap')
            normal_map.location = (new_bsdf.location.x - 300, new_bsdf.location.y - 300)
            material.node_tree.links.new(normal_node.outputs['Color'], normal_map.inputs['Color'])
            material.node_tree.links.new(normal_map.outputs['Normal'], new_bsdf.inputs['Normal'])
        
        # Connect BSDF to material output
        material.node_tree.links.new(new_bsdf.outputs['BSDF'], material_output.inputs['Surface'])
        
        logger.info(f"Successfully reconnected baked textures for {material.name}")