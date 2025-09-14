from hmac import digest
import time
import bpy
import logging
from bpy.types import Operator
from collections import defaultdict
from . import helpers
import re
from hashlib import sha1
import asyncio


# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

# class InstanceMeshes(Operator):
#     """Finds identical meshes in the scene and instances them."""
#     bl_idname = "object.instance_meshes"
#     bl_label = "Instance Meshes"
#     bl_options = {'REGISTER', 'UNDO'}

#     def execute(self, context):
#         # Find all mesh objects in the scene
#         mesh_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
#         if not mesh_objects:
#             self.report({'WARNING'}, "No mesh objects found.")
#             return {'CANCELLED'}
        
#         selected_objects = context.selected_objects
#         mesh_objects = [obj for obj in mesh_objects if obj in selected_objects] if selected_objects else mesh_objects

#         def modelDataHash(obj):
#             if not obj.data:
#                 return None
            
#             # TODO: Check if I need to instance more
#             vertices = tuple((round(v.co.x, 3), round(v.co.y, 3), round(v.co.z, 3)) for v in obj.data.vertices)
            
#             # create hash for vertex positions
#             sha = sha1()
#             sha.update(str(vertices).encode('utf-8'))
#             digest = sha.hexdigest()
#             logger.info(f"Hash for {obj.name}: {digest}")
#             return digest

#         # Based on mesh data, group
#         mesh_groups = defaultdict(list)
#         data_groups = defaultdict(list)
#         for obj in mesh_objects:
#             if not obj.data:
#                 continue
#             if data_groups[obj.data]:
#                 continue
#             data_hash = modelDataHash(obj)
#             data_groups[obj.data].append(obj)
#             if data_hash is not None:
#                 mesh_groups[data_hash].append(obj)
                
#         def getNumericValueFromSuffix(name):
#             match = re.search(r'\.(\d+)$', name)
#             return int(match.group(1)) if match else 0

#         # For each group with more than one object, instance them
#         for instances in mesh_groups.values():
#             # find lowest suffixed instance
#             base_instance = instances[0]
#             suffix = getNumericValueFromSuffix(base_instance.name)
#             for obj in instances:
#                 obj_suffix = getNumericValueFromSuffix(obj.name)
#                 if obj_suffix < suffix:
#                     base_instance = obj
#                     suffix = obj_suffix

#             # replace data on all objects with base_instance's data
#             instanced = 0
#             for obj in instances:
#                 if obj.data != base_instance.data:
#                     obj.data = base_instance.data
#                     instanced += 1
#             if instanced > 0:
#                 logger.info(f"Instanced {instanced} objects to {base_instance.name}")

#         return {'FINISHED'}

class InstanceMeshes(Operator):
    """Finds objects with identical children and instances them."""
    bl_idname = "object.instance_meshes_2"
    bl_label = "Instance Meshes 2"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Problem:
        # Scene -> Empty -> [Obj1, Obj2, Obj3]
        # Scene -> Empty2 -> [Obj4, Obj5, Obj6]
        # Obj1 -> Mesh1
        # Obj2 -> Mesh2
        # Obj3 -> Mesh3
        # Obj4 -> Mesh1
        # Obj5 -> Mesh2
        # Obj6 -> Mesh3
        # Result:
        # Join Obj1, Obj2, Obj3, store as RefObj
        # Discard Obj1, Obj2, Obj3, Obj4, Obj5, Obj6
        # Instance RefObj under Empty and Empty2
        # Scene -> Empty -> Obj1
        # Scene -> Empty2 -> Obj1
        
        selected_parents = []
        for obj in context.selected_objects:
            # skip if has a parent
            if obj.parent:
                continue

            # Only consider empties with children
            if obj.type == 'EMPTY' and obj.children:
                selected_parents.append(obj)
                
        # Group parents by their children's mesh data
        # collection should be identified as [mesh1, mesh2, mesh3] -> [parent1, parent2]
        parent_groups = defaultdict(list)
        for parent in selected_parents:
            child_meshes = tuple(sorted(child.data.name for child in parent.children if child.type == 'MESH' and child.data))
            # skip if any non-mesh children
            if not all(child.type == 'MESH' for child in parent.children):
                continue
            if child_meshes: 
                parent_groups[child_meshes].append(parent)
                
        for mesh_group, parents in parent_groups.items():
            if len(parents) < 2:
                continue  # No need to instance if only one parent
            
            logger.info(f"Found {len(parents)} parents with identical children meshes: {mesh_group}")
            # Join children of the first parent as the reference object
            ref_parent = parents[0]
            bpy.ops.object.select_all(action='DESELECT')
            for child in ref_parent.children:
                if child.type == 'MESH':
                    child.select_set(True)
            context.view_layer.objects.active = ref_parent.children[0] if ref_parent.children else None
            
            bpy.ops.object.join()
            ref_obj = context.active_object
            if not ref_obj:
                continue
            
            # profile this to find what to opti
            # Instance the reference object under all parents
            for parent in parents:
                if parent == ref_parent:
                    continue
                
                time_delete_start = time.time()
                # for child in parent.children:
                #     bpy.data.objects.remove(child)
                bpy.data.batch_remove(parent.children)
                time_delete_end = time.time()
                logger.info(f"Deleted children in {time_delete_end - time_delete_start:.4f} seconds")
                
                # duplicate linked
                time_copy_start = time.time()
                new_instance = ref_obj.copy()
                new_instance.data = ref_obj.data
                time_copy_end = time.time()
                logger.info(f"Copied instance in {time_copy_end - time_copy_start:.4f} seconds")
                
                time_link_start = time.time()
                context.collection.objects.link(new_instance)
                time_link_end = time.time()
                logger.info(f"Linked instance in {time_link_end - time_link_start:.4f} seconds")
                new_instance.parent = parent
                logger.info(f"Instanced {new_instance.name} under {parent.name}")
                    
            logger.info(f"Instanced {ref_obj.name} under {len(parents)} parents.")

        return {'FINISHED'}