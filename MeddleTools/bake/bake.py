import bpy
import logging
from bpy.types import Operator

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
    
    @classmethod
    def poll(cls, context):
        # require .blend file to be saved
        is_saved = bpy.data.is_saved
        # require armature to be selected
        armature_selected = any(obj.type == 'ARMATURE' for obj in context.selected_objects)
        return is_saved and armature_selected
        
    
    def execute(self, context):
        # get selected armature
        armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
        if not armature:
            self.report({'ERROR'}, "No armature or mesh selected.")
            return {'CANCELLED'}
        
        logger.info(f"Starting bake process for armature: {armature.name}")
        # get all mesh objects under the armature
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH' and armature.name in [mod.object.name for mod in obj.modifiers if mod.type == 'ARMATURE']]
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects found under the selected armature.")
            return {'CANCELLED'}

        # get all materials used by these mesh objects
        materials = set()
        for mesh in mesh_objects:
            materials.update(mat.name for mat in mesh.data.materials if mat)

        if not materials:
            self.report({'ERROR'}, "No materials found on the mesh objects.")
            return {'CANCELLED'}
        
        logger.info(f"Materials to bake: {materials}")
        (armature_copy, mesh_copies, material_copies) = self.duplicateArmatureAndMeshes(context, armature, mesh_objects, materials)
        
        # position armature to side of original for viewing
        armature_copy.location.x += 1.0

        for original_name, material_copy in material_copies.items():
            # get mesh copies using this material
            meshes_using_material = [mesh for mesh in mesh_copies if material_copy.name in [mat.name for mat in mesh.data.materials if mat]]
            if not meshes_using_material:
                continue
            if len(meshes_using_material) > 1:
                logger.info(f"Multiple meshes use material {original_name}, joining for baking.")
                raise Exception("Should not reach here, joining handled in duplicateArmatureAndMeshes")

            self.bakeMaterial(context, material_copy, meshes_using_material[0])

        return {'FINISHED'}
    
    def duplicateArmatureAndMeshes(self, context, armature, mesh_objects, materials):        
        # duplicate the armature and mesh objects
        armature_copy = armature.copy()
        armature_copy.data = armature.data.copy()
        context.collection.objects.link(armature_copy)
        mesh_bucket = {}
        for mesh in mesh_objects:
            mesh_copy = mesh.copy()
            mesh_copy.data = mesh.data.copy()
            # assign to armature copy
            for mod in mesh_copy.modifiers:
                if mod.type == 'ARMATURE':
                    mod.object = armature_copy
            context.collection.objects.link(mesh_copy)
            # parent to armature copy
            mesh_copy.parent = armature_copy
            # place in bucket with material as key
            mat_key = tuple(sorted(mat.name for mat in mesh_copy.data.materials if mat))
            if mat_key not in mesh_bucket:
                mesh_bucket[mat_key] = []
            mesh_bucket[mat_key].append(mesh_copy)

        # copy materials and rename
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
        joined_meshes = []
        for mat_names, meshes in mesh_bucket.items():
            joined_mesh = None
            if len(meshes) > 1:
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
            
                
            # Merge vertices with duplicate UV coordinates
            self.merge_vertices_by_uv(joined_mesh, "UVMap")
            joined_meshes.append(joined_mesh)
                
        # assign bake materials to mesh copies
        for mesh_copy in joined_meshes:
            for i, mat in enumerate(mesh_copy.data.materials):
                if mat and mat.name in material_copies:
                    mesh_copy.data.materials[i] = material_copies[mat.name]

        return (armature_copy, joined_meshes, material_copies)

    def merge_vertices_by_uv(self, mesh_obj, uv_layer_name):
        """Merge vertices that share the same UV coordinates and normalize UVs to 0-1 range"""
        import bmesh
        from mathutils import Vector
        import math
        
        logger.info(f"Processing UV coordinates for {mesh_obj.name}")
        
        if uv_layer_name not in mesh_obj.data.uv_layers:
            logger.warning(f"UV layer {uv_layer_name} not found in mesh {mesh_obj.name}")
            return
        
        # Use BMesh for better mesh manipulation
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        uv_layer = bm.loops.layers.uv.get(uv_layer_name)
        if not uv_layer:
            logger.warning(f"UV layer {uv_layer_name} not found in bmesh")
            bm.free()
            return
        
        # First, normalize wrapped UVs and split faces that span boundaries
        needs_normalization = False
        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                if uv.x < 0 or uv.x > 1 or uv.y < 0 or uv.y > 1:
                    needs_normalization = True
                    break
            if needs_normalization:
                break
        
        if needs_normalization:
            logger.info(f"Normalizing wrapped UVs for {mesh_obj.name}")
            
            # Identify faces that span UV boundaries
            faces_to_process = []
            for face in bm.faces:
                uvs = [loop[uv_layer].uv.copy() for loop in face.loops]
                
                # Check for boundary spanning
                min_u = min(uv.x for uv in uvs)
                max_u = max(uv.x for uv in uvs)
                min_v = min(uv.y for uv in uvs)
                max_v = max(uv.y for uv in uvs)
                
                u_span = max_u - min_u
                v_span = max_v - min_v
                
                # If span > 0.5, face likely wraps around boundary
                if u_span > 0.5 or v_span > 0.5:
                    faces_to_process.append((face, uvs, u_span > 0.5, v_span > 0.5))
            
            if faces_to_process:
                logger.info(f"Found {len(faces_to_process)} faces spanning UV boundaries, splitting...")
                
                # Process each spanning face
                for face, orig_uvs, spans_u, spans_v in faces_to_process:
                    # Determine which UV tile each vertex should be in
                    tile_assignments = []
                    for uv in orig_uvs:
                        tile_u = math.floor(uv.x)
                        tile_v = math.floor(uv.y)
                        tile_assignments.append((tile_u, tile_v))
                    
                    # Get unique tiles this face spans
                    unique_tiles = list(set(tile_assignments))
                    
                    if len(unique_tiles) <= 1:
                        # Face is in a single tile, just normalize
                        for loop in face.loops:
                            loop[uv_layer].uv.x = loop[uv_layer].uv.x % 1.0
                            loop[uv_layer].uv.y = loop[uv_layer].uv.y % 1.0
                        continue
                    
                    # Face spans multiple tiles - need to duplicate it for each tile
                    face_verts = [loop.vert for loop in face.loops]
                    face_material = face.material_index
                    face_smooth = face.smooth
                    
                    # Create a copy of the face for each tile it spans
                    for tile_u, tile_v in unique_tiles:
                        # Create new vertices at the same positions
                        new_verts = []
                        for v in face_verts:
                            new_v = bm.verts.new(v.co)
                            new_verts.append(new_v)
                        
                        # Create new face
                        try:
                            new_face = bm.faces.new(new_verts)
                            new_face.material_index = face_material
                            new_face.smooth = face_smooth
                            
                            # Set UVs for this tile copy
                            for i, loop in enumerate(new_face.loops):
                                orig_uv = orig_uvs[i]
                                # Normalize UV to 0-1 range relative to this tile
                                normalized_u = (orig_uv.x - tile_u) % 1.0
                                normalized_v = (orig_uv.y - tile_v) % 1.0
                                loop[uv_layer].uv = Vector((normalized_u, normalized_v))
                        except ValueError:
                            # Face already exists or invalid geometry
                            logger.warning(f"Could not create duplicate face for tile ({tile_u}, {tile_v})")
                            continue
                    
                    # Remove the original face
                    bm.faces.remove(face)
            
            # Normalize all remaining UVs
            for face in bm.faces:
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    loop[uv_layer].uv = Vector((uv.x % 1.0, uv.y % 1.0))
            
            # Update indices after modifications
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            logger.info(f"UV normalization complete")
                        
        # write back to mesh
        bm.to_mesh(mesh_obj.data)
        bm.free()
        mesh_obj.data.update()

        logger.info(f"UV processing complete for {mesh_obj.name}")

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
        
        # fix to 4k
        # max_image_size = (4096, 4096)
        max_image_size = determineLargestImage()
        duplicate_node = createBakeBsdfNode()
        
        # bake passes
        image_nodes = []
        diffuse_image = self.bake_pass(context, material, joined_mesh, 'diffuse', max_image_size)
        # alpha_image = self.bake_pass(context, material, joined_mesh, 'alpha', max_image_size)
        normal_image = self.bake_pass(context, material, joined_mesh, 'normal', max_image_size)
        # roughness_image = self.bake_pass(context, material, joined_mesh, 'roughness', max_image_size)
        image_nodes.append(diffuse_image)
        # image_nodes.append(alpha_image)
        image_nodes.append(normal_image)
        # image_nodes.append(roughness_image)
        
        # trigger save of baked images
        for img_node in image_nodes:
            if img_node.image and img_node.image.has_data:
                img_node.image.save()

        # link image node to duplicate_node
        material.node_tree.links.new(diffuse_image.outputs['Color'], duplicate_node.inputs['Base Color'])
        material.node_tree.links.new(diffuse_image.outputs['Alpha'], duplicate_node.inputs['Alpha'])
        # material.node_tree.links.new(alpha_image.outputs['Alpha'], duplicate_node.inputs['Alpha'])
        
        # run normal through normal map node
        normal_map_node = material.node_tree.nodes.new('ShaderNodeNormalMap')
        normal_map_node.location = (duplicate_node.location.x - 300, duplicate_node.location.y - 200)
        material.node_tree.links.new(normal_image.outputs['Color'], normal_map_node.inputs['Color'])
        material.node_tree.links.new(normal_map_node.outputs['Normal'], duplicate_node.inputs['Normal'])
        # material.node_tree.links.new(roughness_image.outputs['Color'], duplicate_node.inputs['Roughness'])

        # link duplicate_node output to material output
        material.node_tree.links.new(duplicate_node.outputs['BSDF'], material_output_node.inputs['Surface'])
        
        # set image node locations
        for i, img_node in enumerate(image_nodes):
            img_node.location = (duplicate_node.location.x - 600, duplicate_node.location.y - i * 200)
        
        for node in original_nodes:
            material.node_tree.nodes.remove(node)

    def bake_pass(self, context, material, mesh, bake_name, max_image_size):
        import math
        
        logger.info(f"Baking pass: {bake_name} for material: {material.name}")
        bake_pass_filter = {}
        bake_type = None
        background_color = (0, 0, 0, 1.0)        
        clear = True
        selected_to_active = False
        normal_space = "TANGENT"
        bake_margin = int(math.ceil(0.0078125 * max(max_image_size)))
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
        # elif bake_name == 'alpha':
        #     bake_type = 'DIFFUSE'
        #     bake_pass_filter = {'COLOR'}            
        #     image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
        #     image.alpha_mode = "CHANNEL_PACKED"
        #     image_node.image = image
        elif bake_name == 'normal':
            # workaround for now
            # find g_SamplerNormal_PngCachePath and just use that image instead of baking
            normal_image = None
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and "g_SamplerNormal_PngCachePath" in node.label:
                    normal_image = node.image
                    break
            
            if normal_image and normal_image.has_data:
                import numpy as np
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
        # elif bake_name == 'roughness':
        #     bake_type = 'ROUGHNESS'
        #     bake_pass_filter = set()
        #     image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
        #     image.alpha_mode = "CHANNEL_PACKED"
        #     image.colorspace_settings.name = 'Non-Color'
        else:
            raise ValueError(f"Unsupported bake type: {bake_type}")
        
        
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
        context.scene.cycles.use_denoising = False # https://developer.blender.org/T94573
        context.scene.render.bake.use_pass_direct = "DIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_indirect = "INDIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_color = "COLOR" in bake_pass_filter
        context.scene.render.bake.use_pass_diffuse = "DIFFUSE" in bake_pass_filter
        context.scene.render.bake.use_pass_emit = "EMIT" in bake_pass_filter
        context.scene.render.bake.target = "IMAGE_TEXTURES"
        context.scene.cycles.samples = 4
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
        
        return image_node