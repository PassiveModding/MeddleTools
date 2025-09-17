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
        
        selected_parents = defaultdict(list)
        for obj in context.selected_objects:
            # Only consider empties with children
            if obj.type == 'EMPTY' and obj.children:
                selected_parents[obj].extend(obj.children)
        

        return {'FINISHED'}
