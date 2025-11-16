import bpy
import logging
from bpy.types import Operator
from . import bake_utils

# Module logger
logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

def get_create_copy_label(context):
    """Get dynamic label for CreateCopyForBaking operator based on selection"""
    mesh_objects = bake_utils.get_all_selected_meshes(context)
    mesh_count = len(mesh_objects)
    
    if mesh_count == 0:
        return "Create Copy for Baking (No meshes selected)"
    elif mesh_count == 1:
        return "Create Copy for Baking (1 mesh)"
    else:
        return f"Create Copy for Baking ({mesh_count} meshes)"


class CreateCopyForBaking(Operator):
    """Create a duplicate of selected armature and meshes prepared for baking"""
    bl_idname = "meddle.create_copy_for_baking"
    bl_label = "Create Copy for Baking"
    bl_description = "Duplicate selected armature and meshes, joining meshes with same materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Ensure we have a mesh or armature selected
        mesh_or_armature_selected = bake_utils.require_mesh_or_armature_selected(context)
        # Check if selected items already exist in a bake collection
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        in_bake_collection = any(bake_utils.is_in_bake_collection(obj) for obj in mesh_objects)
        armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
        if armature:
            in_bake_collection = in_bake_collection or bake_utils.is_in_bake_collection(armature)
        return mesh_or_armature_selected and not in_bake_collection
        
    
    def execute(self, context):
        try:
            # Check if armature is selected
            armature = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
            mesh_objects = bake_utils.get_all_selected_meshes(context)

            # Get all materials used by these mesh objects
            materials = set()
            for mesh in mesh_objects:
                materials.update(mat.name for mat in mesh.data.materials if mat)

            if not materials:
                self.report({'ERROR'}, "No materials found on the mesh objects.")
                return {'CANCELLED'}
            
            logger.info(f"Materials found: {materials}")
            
            # Create a collection for copied objects
            collection_name = f"BAKE_{armature.name if armature else 'Meshes'}"
            bake_collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(bake_collection)
            collection_name = bake_collection.name
            logger.info(f"Created collection: {collection_name}")
            
            self.report({'INFO'}, f"Duplicating and processing {len(mesh_objects)} mesh(es)...")
            (armature_copy, mesh_copies, material_copies) = self.duplicate_armature_and_meshes(
                context, armature, mesh_objects, materials, bake_collection
            )
            
            self.report({'INFO'}, f"Copy complete! Created collection: {collection_name} with {len(mesh_copies)} mesh(es)")
            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"Failed to create copy for baking: {e}")
            self.report({'ERROR'}, f"Failed to create copy: {str(e)}")
            return {'CANCELLED'}
    
    def duplicate_armature_and_meshes(self, context, armature, mesh_objects, materials, bake_collection):
        """Duplicate armature and meshes, joining meshes with same materials"""
        
        # Duplicate the armature
        self.report({'INFO'}, "  Duplicating armature and meshes...")
        armature_copy = None
        if armature:
            armature_copy = armature.copy()
            armature_copy.data = armature.data.copy()
            bake_collection.objects.link(armature_copy)
        
        # Duplicate meshes and organize by material
        mesh_bucket = {}
        for mesh in mesh_objects:
            mesh_copy = mesh.copy()
            mesh_copy.data = mesh.data.copy()
            
            # Assign to armature copy if it exists
            if armature_copy:
                for mod in mesh_copy.modifiers:
                    if mod.type == 'ARMATURE':
                        mod.object = armature_copy
                # Parent to armature copy
                mesh_copy.parent = armature_copy
            
            bake_collection.objects.link(mesh_copy)
            
            # Place in bucket with material as key
            mat_key = tuple(sorted(mat.name for mat in mesh_copy.data.materials if mat))
            if mat_key not in mesh_bucket:
                mesh_bucket[mat_key] = []
            mesh_bucket[mat_key].append(mesh_copy)

        # Copy materials and rename
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
        
        # Join meshes in each bucket
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
            
            self.report({'INFO'}, f"    Ensuring UV layer ({current_bucket}/{total_buckets})...")
            # Ensure UV layer exists
            if not self.ensure_uv_layer(joined_mesh, "UVMap"):
                self.report({'ERROR'}, f"Failed to create UVs for {joined_mesh.name}")
                return (None, [], {})
            
            joined_meshes.append(joined_mesh)
                
        # Assign bake materials to mesh copies
        for mesh_copy in joined_meshes:
            for i, mat in enumerate(mesh_copy.data.materials):
                if mat and mat.name in material_copies:
                    mesh_copy.data.materials[i] = material_copies[mat.name]

        # Position armature/meshes to side of original for viewing
        if armature_copy:
            armature_copy.location.x += 1.0
        else:
            # If no armature, offset all joined meshes
            for mesh in joined_meshes:
                mesh.location.x += 1.0

        return (armature_copy, joined_meshes, material_copies)
    
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


def register():
    bpy.utils.register_class(CreateCopyForBaking)


def unregister():
    bpy.utils.unregister_class(CreateCopyForBaking)
