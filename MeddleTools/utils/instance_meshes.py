from hmac import digest
import bpy
import logging
from bpy.types import Operator
from collections import defaultdict
from . import helpers
import re
from hashlib import sha1


# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class InstanceMeshes(Operator):
    """Finds identical meshes in the scene and instances them."""
    bl_idname = "object.instance_meshes"
    bl_label = "Instance Meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Find all mesh objects in the scene
        mesh_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found.")
            return {'CANCELLED'}
        
        selected_objects = context.selected_objects
        mesh_objects = [obj for obj in mesh_objects if obj in selected_objects] if selected_objects else mesh_objects

        def modelDataHash(obj):
            if not obj.data:
                return None
            
            # TODO: Check if I need to instance more
            vertices = tuple((round(v.co.x, 3), round(v.co.y, 3), round(v.co.z, 3)) for v in obj.data.vertices)
            
            # create hash for vertex positions
            sha = sha1()
            sha.update(str(vertices).encode('utf-8'))
            digest = sha.hexdigest()
            logger.info(f"Hash for {obj.name}: {digest}")
            return digest

        # Based on mesh data, group
        mesh_groups = defaultdict(list)
        data_groups = defaultdict(list)
        for obj in mesh_objects:
            if not obj.data:
                continue
            if data_groups[obj.data]:
                continue
            data_hash = modelDataHash(obj)
            data_groups[obj.data].append(obj)
            if data_hash is not None:
                mesh_groups[data_hash].append(obj)
                
        def getNumericValueFromSuffix(name):
            match = re.search(r'\.(\d+)$', name)
            return int(match.group(1)) if match else 0

        # For each group with more than one object, instance them
        for instances in mesh_groups.values():
            # find lowest suffixed instance
            base_instance = instances[0]
            suffix = getNumericValueFromSuffix(base_instance.name)
            for obj in instances:
                obj_suffix = getNumericValueFromSuffix(obj.name)
                if obj_suffix < suffix:
                    base_instance = obj
                    suffix = obj_suffix

            # replace data on all objects with base_instance's data
            instanced = 0
            for obj in instances:
                if obj.data != base_instance.data:
                    obj.data = base_instance.data
                    instanced += 1
            if instanced > 0:
                logger.info(f"Instanced {instanced} objects to {base_instance.name}")

        return {'FINISHED'}
