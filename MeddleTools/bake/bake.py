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
        single_mesh_selected = sum(1 for obj in context.selected_objects if obj.type == 'MESH') >= 1
        return is_saved and (armature_selected or single_mesh_selected)
        
    
    def execute(self, context):
        # get selected armature
        armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
        mesh = next((obj for obj in context.selected_objects if obj.type == 'MESH'), None)
        if not armature and not mesh:
            self.report({'ERROR'}, "No armature or mesh selected.")
            return {'CANCELLED'}
        
        if armature:            
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
        elif mesh:
            logger.info(f"Starting bake process for single mesh: {mesh.name}")
            # get all materials used by this mesh
            materials = set(mat.name for mat in mesh.data.materials if mat)
            if not materials:
                self.report({'ERROR'}, "No materials found on the selected mesh.")
                return {'CANCELLED'}
            
            logger.info(f"Materials to bake: {materials}")
            
            for material in materials:
                material_obj = bpy.data.materials.get(material)
                if not material_obj:
                    logger.warning(f"Material {material} not found, skipping.")
                    continue
                self.bakeMaterial(context, material_obj, mesh)

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
            if len(meshes) > 1:
                bpy.ops.object.select_all(action='DESELECT')
                # Set active object ONCE before selecting others
                context.view_layer.objects.active = meshes[0]
                for mesh in meshes:
                    mesh.select_set(True)
                bpy.ops.object.join()
                joined_mesh = context.view_layer.objects.active
                joined_meshes.append(joined_mesh)
                logger.info(f"Joined {len(meshes)} meshes into {joined_mesh.name} with materials {mat_names}")
            else:
                joined_meshes.append(meshes[0])
                
        # assign bake materials to mesh copies
        for mesh_copy in joined_meshes:
            for i, mat in enumerate(mesh_copy.data.materials):
                if mat and mat.name in material_copies:
                    mesh_copy.data.materials[i] = material_copies[mat.name]

        return (armature_copy, joined_meshes, material_copies)

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
        
        def normalizeWrappedUVs(mesh, uv_layer_name):
            """Normalize UVs that extend beyond 0-1 range while preserving face integrity"""
            import math
            
            if uv_layer_name not in mesh.data.uv_layers:
                logger.warning(f"UV layer {uv_layer_name} not found in mesh {mesh.name}")
                return
            
            uv_layer = mesh.data.uv_layers[uv_layer_name]
            
            # Check if normalization is needed
            needs_normalization = False
            for loop in mesh.data.loops:
                uv = uv_layer.data[loop.index].uv
                if uv.x < 0 or uv.x > 1 or uv.y < 0 or uv.y > 1:
                    needs_normalization = True
                    break
            
            if not needs_normalization:
                logger.info(f"UVs already in 0-1 range for {mesh.name}")
                return
            
            logger.info(f"Normalizing wrapped UVs for {mesh.name}")
            
            # Group loops by face to detect spanning issues
            for poly in mesh.data.polygons:
                face_uvs = [uv_layer.data[loop_idx].uv.copy() for loop_idx in poly.loop_indices]
                
                # Find the "tile" each UV coordinate belongs to
                for axis in [0, 1]:  # x, y
                    coords = [uv[axis] for uv in face_uvs]
                    min_coord = min(coords)
                    max_coord = max(coords)
                    
                    # If face spans more than 0.5 units, it's likely wrapping
                    if max_coord - min_coord > 0.5:
                        # Shift UVs to same tile (normalize to floor of minimum)
                        tile_offset = math.floor(min_coord)
                        for i, loop_idx in enumerate(poly.loop_indices):
                            current_uv = uv_layer.data[loop_idx].uv
                            current_uv[axis] -= tile_offset
                    else:
                        # Just normalize to 0-1 range without tile detection
                        tile_offset = math.floor(min_coord)
                        for i, loop_idx in enumerate(poly.loop_indices):
                            current_uv = uv_layer.data[loop_idx].uv
                            current_uv[axis] -= tile_offset
            
            # Final pass: clamp any remaining out-of-range values
            for loop in mesh.data.loops:
                uv = uv_layer.data[loop.index].uv
                uv.x = max(0.0, min(1.0, uv.x))
                uv.y = max(0.0, min(1.0, uv.y))
            
            mesh.data.update()
            logger.info(f"UV normalization complete for {mesh.name}")
        
        # fix to 4k
        # max_image_size = (4096, 4096)
        max_image_size = determineLargestImage()
        duplicate_node = createBakeBsdfNode()
        
        uv_map_name = "UVMap"
        normalizeWrappedUVs(joined_mesh, uv_map_name)
        
        # bake passes
        image_nodes = []
        diffuse_image = self.bake_pass(context, material, joined_mesh, 'diffuse', max_image_size)
        alpha_image = self.bake_pass(context, material, joined_mesh, 'alpha', max_image_size)
        normal_image = self.bake_pass(context, material, joined_mesh, 'normal', max_image_size)
        # roughness_image = self.bake_pass(context, material, joined_mesh, 'roughness', max_image_size)
        image_nodes.append(diffuse_image)
        image_nodes.append(alpha_image)
        image_nodes.append(normal_image)
        # image_nodes.append(roughness_image)

        # link image node to duplicate_node
        material.node_tree.links.new(diffuse_image.outputs['Color'], duplicate_node.inputs['Base Color'])
        material.node_tree.links.new(alpha_image.outputs['Alpha'], duplicate_node.inputs['Alpha'])
        
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
        logger.info(f"Baking pass: {bake_name} for material: {material.name}")
        bake_pass_filter = {}
        bake_type = None
        background_color = (0, 0, 0, 1.0)        
        clear = True
        selected_to_active = False
        normal_space = "TANGENT"


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

        image = create_bake_image(bake_name, background_color, max_image_size[0], max_image_size[1])
        image.alpha_mode = "CHANNEL_PACKED"
        image_node.image = image
        # ensure image is active
        material.node_tree.nodes.active = image_node
        
        if bake_name == 'diffuse':
            bake_type = 'DIFFUSE'
            bake_pass_filter = {'COLOR'}
        elif bake_name == 'alpha':
            bake_type = 'DIFFUSE'
            bake_pass_filter = {'COLOR'}
        elif bake_name == 'normal':
            bake_type = 'NORMAL'
            bake_pass_filter = set()
            image.colorspace_settings.name = 'Non-Color'
        elif bake_name == 'roughness':
            bake_type = 'ROUGHNESS'
            bake_pass_filter = set()
            image.colorspace_settings.name = 'Non-Color'
        else:
            raise ValueError(f"Unsupported bake type: {bake_type}")
        
        # Set up bake settings
        context.scene.cycles.bake_type = bake_type
        context.scene.cycles.use_denoising = False # https://developer.blender.org/T94573
        context.scene.render.bake.use_pass_direct = "DIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_indirect = "INDIRECT" in bake_pass_filter
        context.scene.render.bake.use_pass_color = "COLOR" in bake_pass_filter
        context.scene.render.bake.use_pass_diffuse = "DIFFUSE" in bake_pass_filter
        context.scene.render.bake.use_pass_emit = "EMIT" in bake_pass_filter
        context.scene.render.bake.target = "IMAGE_TEXTURES"
        context.scene.cycles.samples = 1
        context.scene.render.image_settings.color_mode = 'RGB'
        context.scene.render.bake.use_clear = True
        context.scene.render.bake.use_selected_to_active = selected_to_active
        context.scene.render.bake.normal_space = normal_space                       
        
        # deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        # select the mesh to bake
        mesh.select_set(True)
        context.view_layer.objects.active = mesh
        
        try:
            bpy.ops.object.bake(type=bake_type,
                                # pass_filter=bake_pass_filter,
                                use_clear=clear and bake_type == 'NORMAL',
                                # uv_layer="SCRIPT",
                                use_selected_to_active=selected_to_active,
                                cage_extrusion=0,
                                normal_space=normal_space
                                )
        except Exception as e:
            logger.error(f"Bake failed for material {material.name}, pass {bake_name}: {e}")
            raise e
        
        return image_node