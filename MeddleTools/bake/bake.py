from calendar import c
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
        # require .blend file to be saved
        is_saved = bpy.data.is_saved
        # require either armature OR mesh to be selected
        has_valid_selection = any(obj.type in {'ARMATURE', 'MESH'} for obj in context.selected_objects)
        return is_saved and has_valid_selection
        
    
    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        try:
            # Check if armature is selected
            armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
            
            if armature:
                # Armature workflow: bake all meshes under the armature
                logger.info(f"Starting bake process for armature: {armature.name}")
                mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH' and armature.name in [mod.object.name for mod in obj.modifiers if mod.type == 'ARMATURE']]
                
                if not mesh_objects:
                    self.report({'ERROR'}, "No mesh objects found under the selected armature.")
                    return {'CANCELLED'}
            else:
                # Mesh workflow: bake selected meshes
                mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
                
                if not mesh_objects:
                    self.report({'ERROR'}, "No armature or mesh selected.")
                    return {'CANCELLED'}
                
                logger.info(f"Starting bake process for {len(mesh_objects)} selected mesh(es)")

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
            (armature_copy, mesh_copies, material_copies) = self.duplicateArmatureAndMeshes(context, armature, mesh_objects, materials, bake_collection)
            
            total_materials = len(material_copies)
            current_material = 0
            
            self.update_progress(context, 20, f"Baking {total_materials} material(s)...")
            for original_name, material_copy in material_copies.items():
                current_material += 1
                # get mesh copies using this material
                meshes_using_material = [mesh for mesh in mesh_copies if material_copy.name in [mat.name for mat in mesh.data.materials if mat]]
                if not meshes_using_material:
                    continue
                if len(meshes_using_material) > 1:
                    logger.info(f"Multiple meshes use material {original_name}, joining for baking.")
                    raise Exception("Should not reach here, joining handled in duplicateArmatureAndMeshes")

                progress = 20 + int((current_material / total_materials) * 50)
                self.update_progress(context, progress, f"  Baking material {current_material}/{total_materials}: {original_name}...")
                self.bakeMaterial(context, material_copy, meshes_using_material[0])
            
            self.update_progress(context, 70, "Joining all meshes...")
            # Join all meshes into one
            joined_mesh = self.join_all_meshes(context, mesh_copies, armature_copy)
            mesh_copies = [joined_mesh]  # Update mesh_copies to contain only the joined mesh
            
            self.update_progress(context, 85, "Exporting FBX...")
            # Export the baked collection to FBX
            fbx_path = self.export_to_fbx(context, bake_collection, collection_name, armature_copy, mesh_copies)
            
            self.update_progress(context, 95, f"Bake complete! Created collection: {collection_name}")
            self.report({'INFO'}, f"Exported to: {fbx_path}")

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
    
    def export_to_fbx(self, context, bake_collection, collection_name, armature_copy, mesh_copies):
        """Export the baked collection to FBX format with textures in a dedicated folder"""
        # Create export directory relative to the blend file
        blend_filepath = bpy.data.filepath
        blend_dir = os.path.dirname(blend_filepath)
        
        # Create a dedicated folder for this export (FBX + textures)
        # If folder exists, find next available incremental number
        export_folder = os.path.join(blend_dir, "Bake", collection_name)
        
        if os.path.exists(export_folder):
            # Find next available incremental folder
            counter = 1
            while True:
                incremental_name = f"{collection_name}_{counter:03d}"
                export_folder = os.path.join(blend_dir, "Bake", incremental_name)
                if not os.path.exists(export_folder):
                    collection_name = incremental_name
                    logger.info(f"Export folder already exists, using incremental name: {collection_name}")
                    self.report({'INFO'}, f"  Using incremental folder: {collection_name}")
                    break
                counter += 1
                if counter > 999:
                    self.report({'ERROR'}, "Too many export folders (>999), please clean up Bake directory")
                    return None
        
        os.makedirs(export_folder, exist_ok=True)
        
        # Create textures subfolder
        textures_folder = os.path.join(export_folder, "textures")
        os.makedirs(textures_folder, exist_ok=True)
        
        # Create FBX filename
        fbx_filename = f"{collection_name}.fbx"
        fbx_path = os.path.join(export_folder, fbx_filename)
        
        logger.info(f"Exporting to FBX: {fbx_path}")
        logger.info(f"Textures will be saved to: {textures_folder}")
        
        # Copy all baked textures to the textures folder and update image paths
        self.copy_baked_textures(mesh_copies, textures_folder)
        
        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all objects in the bake collection
        objects_to_export = []
        if armature_copy:
            armature_copy.select_set(True)
            objects_to_export.append(armature_copy)
        
        for mesh in mesh_copies:
            mesh.select_set(True)
            objects_to_export.append(mesh)
        
        # Set active object
        if armature_copy:
            context.view_layer.objects.active = armature_copy
        elif mesh_copies:
            context.view_layer.objects.active = mesh_copies[0]
        
        # Export FBX with appropriate settings
        try:
            bpy.ops.export_scene.fbx(
                filepath=fbx_path,
                use_selection=True,
                global_scale=1.0,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_NONE',
                bake_space_transform=False,
                object_types={'ARMATURE', 'MESH'},
                use_mesh_modifiers=True,
                use_mesh_modifiers_render=True,
                mesh_smooth_type='FACE',
                use_tspace=True,
                use_custom_props=False,
                add_leaf_bones=False,
                primary_bone_axis='Y',
                secondary_bone_axis='X',
                armature_nodetype='NULL',
                bake_anim=False,
                path_mode='RELATIVE',
                embed_textures=True,
                batch_mode='OFF'
            )
            logger.info(f"Successfully exported FBX to: {fbx_path}")
            self.report({'INFO'}, f"  Exported to: {export_folder}")
        except Exception as e:
            logger.error(f"Failed to export FBX: {e}")
            self.report({'WARNING'}, f"  Failed to export FBX: {e}")
            return None
        
        return fbx_path
    
    def duplicateArmatureAndMeshes(self, context, armature, mesh_objects, materials, bake_collection):        
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
            
            # Merge vertices with duplicate UV coordinates
            self.fix_uvs(context, joined_mesh, "UVMap")
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

    def fix_uvs(self, context, mesh, map_name):
        # 1. Find all uv islands
        uv_islands = {}
        bm = bmesh.new()
        bm.from_mesh(mesh.data)
        uv_layer = bm.loops.layers.uv.get(map_name)
        
        if not uv_layer:
            logger.warning(f"No UV layer named {map_name} found on mesh {mesh.name}")
            bm.free()
            return
        
        for face in bm.faces:
            vertex_set = frozenset(loop.vert.index for loop in face.loops)
            if vertex_set not in uv_islands:
                uv_islands[vertex_set] = set()
            for loop in face.loops:
                uv_islands[vertex_set].add(loop.vert)
                
        # 2. Get island bounding box
        for key, verts in uv_islands.items():
            if len(verts) < 2:
                continue
            
            min_uv = Vector((float('inf'), float('inf')))
            max_uv = Vector((-float('inf'), -float('inf')))
            for vert in verts:
                for loop in vert.link_loops:
                    uv = loop[uv_layer].uv
                    min_uv.x = min(min_uv.x, uv.x)
                    min_uv.y = min(min_uv.y, uv.y)
                    max_uv.x = max(max_uv.x, uv.x)
                    max_uv.y = max(max_uv.y, uv.y)
            
            # check if island exceeds 0-1 range
            if min_uv.x >= 0.0 and min_uv.y >= 0.0 and max_uv.x <= 1.0 and max_uv.y <= 1.0:
                continue  # already within 0-1 range
            
            def fix_boundary_tile(verts, uv_layer, min_uv, max_uv):
                # shift the max uv to be within the tile of min uv
                for vert in verts:
                    for loop in vert.link_loops:
                        uv = loop[uv_layer].uv
                        # only adjust uvs that are outside the tile
                        # ex. if uv.x = 2.1 and tile_offset_x = 2, adjust to 2.0
                        if uv.x > math.floor(min_uv.x) + 1.0: # if 1.1 > 0 + 1
                            uv.x = math.floor(uv.x)
                        if uv.y > math.floor(min_uv.y) + 1.0:
                            uv.y = math.floor(uv.y)
                                        
            # Check if island crosses tile boundaries (e.g., min_uv.x = 1.9, max_uv.x = 2.1)
            x_tile_diff = math.floor(max_uv.x) - math.floor(min_uv.x)
            y_tile_diff = math.floor(max_uv.y) - math.floor(min_uv.y)
            island_exceeds_tile = (x_tile_diff > 1) or (y_tile_diff > 1)
            if island_exceeds_tile:
                logger.error(f"UV island on mesh {mesh.name} exceeds multiple tile boundaries, cannot fix automatically.")
                continue
            
            island_crosses_boundary = (x_tile_diff > 0) or (y_tile_diff > 0)
            if island_crosses_boundary:
                fix_boundary_tile(verts, uv_layer, min_uv, max_uv)
                continue
            
            # Now normalize to 0-1 range if needed
            island_exists_outside_0_1 = (min_uv.x < 0.0 or min_uv.y < 0.0 or max_uv.x > 1.0 or max_uv.y > 1.0)
            if island_exists_outside_0_1:
                # Calculate tile offset to move to 0-1 range
                tile_offset_x = math.floor(min_uv.x)
                tile_offset_y = math.floor(min_uv.y)
                
                # Shift uvs to 0-1 range
                for vert in verts:
                    for loop in vert.link_loops:
                        uv = loop[uv_layer].uv
                        uv.x = uv.x - tile_offset_x
                        uv.y = uv.y - tile_offset_y
            
        bm.to_mesh(mesh.data)
        bm.free()

    def bakeMaterial(self, context, material, joined_mesh):
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
            # fix default
            
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
            return (max_width, max_height)
        
        max_image_size = determineLargestImage()
        
        # bake passes
        image_nodes = []
        diffuse_image = self.bake_pass(context, material, joined_mesh, 'diffuse', max_image_size)
        # alpha_image = self.bake_pass(context, material, joined_mesh, 'alpha', max_image_size)
        normal_image = self.bake_pass(context, material, joined_mesh, 'normal', max_image_size)
        roughness_image = self.bake_pass(context, material, joined_mesh, 'roughness', max_image_size)
        image_nodes.append(diffuse_image)
        # image_nodes.append(alpha_image) # this is basically redundant since alpha is in diffuse
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

    def bake_pass(self, context, material, mesh, bake_name, max_image_size):        
        logger.info(f"Baking pass: {bake_name} for material: {material.name}")
        bake_pass_filter = {}
        bake_type = None
        background_color = (0, 0, 0, 1.0)        
        clear = True
        selected_to_active = False
        normal_space = "TANGENT"
        bake_margin = int(math.ceil(0.0078125 * max(max_image_size)))
        required_inputs = []
        remap_target_socket_name = None
        logger.info(f"Bake margin set to: {bake_margin} pixels")

        def create_bake_image(bake_name, background_color, width, height):
            file_name = f"Bake_{bake_name}_{material.name}.png"
            image = bpy.data.images.new(name=file_name, 
                    width=width, height=height, alpha=True)
            image.filepath = bpy.path.abspath(f"//Bake/{file_name}")
            image.alpha_mode = "STRAIGHT"
            image.scale(width, height)
            image.generated_color = background_color
            
            return image
        
        # create image texture node and link to bake_node
        image_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        image = None
        if bake_name == 'diffuse':
            bake_type = 'DIFFUSE'
            bake_pass_filter = {'COLOR'}            
            image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
            image.alpha_mode = "CHANNEL_PACKED"
            image_node.image = image
            required_inputs = ['Base Color', 'Alpha']
        elif bake_name == 'normal':
            # workaround for now
            # find g_SamplerNormal_PngCachePath and just use that image instead of baking
            normal_image = None
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and "g_SamplerNormal_PngCachePath" in node.label:
                    normal_image = node.image
                    break
            
            if normal_image and normal_image.has_data:
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
                
                copied_image = create_bake_image(bake_name, background_color, normal_image.size[0], normal_image.size[1])
                copied_image.alpha_mode = normal_image.alpha_mode
                copied_image.colorspace_settings.name = 'Non-Color'
                
                nparray_channels_to_img(copied_image, pixel_data)

                image_node.image = copied_image
                return image_node
            else:
                bake_type = 'NORMAL'
                bake_pass_filter = set()
                image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
                image.alpha_mode = "CHANNEL_PACKED"
                image_node.image = image
                image.colorspace_settings.name = 'Non-Color'
                required_inputs = ['Normal']              
        elif bake_name == 'roughness':
            bake_type = 'ROUGHNESS'
            bake_pass_filter = set()
            image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
            image.alpha_mode = "CHANNEL_PACKED"
            image_node.image = image
            image.colorspace_settings.name = 'Non-Color'
            required_inputs = ['Roughness', 'Metallic']
        else:
            raise ValueError(f"Unsupported bake type: {bake_name}")
        
        
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
        
        # ensure we are using cycles
        context.scene.render.engine = 'CYCLES'
        
        # Set up bake settings
        context.scene.cycles.bake_type = bake_type
        context.scene.cycles.use_denoising = False
        context.scene.render.bake.use_pass_direct = "DIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_indirect = "INDIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_color = "COLOR" in bake_pass_filter
        context.scene.render.bake.use_pass_diffuse = "DIFFUSE" in bake_pass_filter
        context.scene.render.bake.use_pass_emit = "EMIT" in bake_pass_filter
        context.scene.render.bake.target = "IMAGE_TEXTURES"
        context.scene.cycles.samples = context.scene.meddle_settings.bake_samples
        context.scene.render.bake.margin = bake_margin
        context.scene.render.image_settings.color_mode = 'RGB'
        context.scene.render.bake.use_clear = clear
        context.scene.render.bake.use_selected_to_active = selected_to_active
        context.scene.render.bake.normal_space = normal_space               
        
        try:
            bpy.ops.object.bake(type=bake_type,
                                # pass_filter=bake_pass_filter,
                                use_clear=context.scene.render.bake.use_clear,
                                uv_layer="UVMap",
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
        
        # Then, reconnect previously disconnected inputs
        for input_socket, from_node, from_socket in disconnect_inputs:
            material.node_tree.links.new(from_socket, input_socket)
        
        return image_node

    def ensure_uv_layer(self, mesh_obj, uv_layer_name="UVMap"):
        """Ensure the mesh has a UV layer, create one if missing"""
        
        if uv_layer_name in mesh_obj.data.uv_layers:
            logger.info(f"UV layer '{uv_layer_name}' already exists for {mesh_obj.name}")
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