import bpy
import logging
from bpy.types import Operator
from collections import defaultdict
from . import helpers

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class ReparentToEmpty(Operator):
    """For each selected object, if it is the only child of an empty, remove the empty and replace it with the object
    i.e. scene -> empty -> object  becomes  scene -> object
    """
    bl_idname = "meddle.reparent_to_empty"
    bl_label = "Reparent to Empty"
    bl_description = "Reparent selected objects to their empty parent (if applicable)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        empty_parents = defaultdict(list)

        # Find all empty parents of selected objects
        for obj in selected_objects:
            if obj.parent and obj.parent.type == 'EMPTY':
                empty_parents[obj.parent].append(obj)

        # Reparent objects and remove empty parents
        children = []
        for empty, children in empty_parents.items():
            if len(children) == 1:
                child = children[0]
                child.parent = empty.parent
                parent_name = empty.parent.name if empty.parent else "None"
                logger.info(f"Reparented {child.name} from {empty.name} to {parent_name}")
                # set child location to empty location
                child.location = empty.location
                child.rotation_euler = empty.rotation_euler
                child.scale = empty.scale
                bpy.data.objects.remove(empty)
                children.append(child.name)
            else:
                logger.info(f"Skipped {empty.name} with multiple children")

        # select newly reparented children
        for child_name in children:
            child = bpy.data.objects.get(child_name)
            if child:
                child.select_set(True)

        return {'FINISHED'}