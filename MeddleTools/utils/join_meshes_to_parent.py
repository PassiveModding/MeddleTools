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

class JoinMeshesToParent(Operator):
    """Join selected mesh objects into their mesh parent to reduce object count.
    For mesh parents: children are joined into the parent (original behavior).
    For non-mesh parents: mesh children are joined together (parent left as-is).
    """
    bl_idname = "meddle.join_meshes_to_parent"
    bl_label = "Join Meshes to Parent"
    bl_description = "Join selected mesh children into their parent (if parent is a mesh) or merge siblings if parent is not a mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        helpers.ensure_object_mode(context, 'OBJECT')

        selected_meshes = helpers.get_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        # Build hierarchy tree from selected objects
        def get_object_depth(obj):
            """Calculate the depth of an object in the hierarchy."""
            depth = 0
            current = obj
            while current.parent:
                depth += 1
                current = current.parent
            return depth

        def get_all_selected_objects():
            """Get all selected objects, not just meshes."""
            return list(context.selected_objects)

        def is_object_valid(obj):
            """Check if object reference is still valid."""
            try:
                return hasattr(obj, 'name') and obj.name in bpy.data.objects
            except (ReferenceError, AttributeError):
                return False

        # Get all selected objects and group by parent with depth info
        all_selected = get_all_selected_objects()
        parent_groups = {}
        
        for obj in all_selected:
            if not is_object_valid(obj):
                continue
                
            parent = obj.parent
            if parent:
                if parent not in parent_groups:
                    parent_groups[parent] = {'meshes': [], 'non_meshes': [], 'depth': 0}
                
                depth = get_object_depth(obj)
                parent_groups[parent]['depth'] = max(parent_groups[parent]['depth'], depth)
                
                if obj.type == 'MESH':
                    parent_groups[parent]['meshes'].append(obj)
                else:
                    parent_groups[parent]['non_meshes'].append(obj)

        if not parent_groups:
            self.report({'INFO'}, "No selected objects have parents — nothing to join")
            return {'CANCELLED'}

        # Sort by depth (deepest first) to process bottom-up
        sorted_groups = sorted(parent_groups.items(), key=lambda x: x[1]['depth'], reverse=True)

        total_joined = 0
        original_active = context.view_layer.objects.active

        for parent, group_data in sorted_groups:
            try:
                # Validate parent is still valid
                if not is_object_valid(parent):
                    logger.debug("Parent object has been removed, skipping group")
                    continue

                meshes = [m for m in group_data['meshes'] if is_object_valid(m)]
                non_meshes = [nm for nm in group_data['non_meshes'] if is_object_valid(nm)]

                # Skip if we have non-mesh children at this level (they block joining)
                if non_meshes:
                    logger.info("Skipping join for parent '%s' due to %d non-mesh children", 
                              parent.name, len(non_meshes))
                    continue

                # For mesh parents: join if we have any mesh children (1 or more)
                # For non-mesh parents: need at least 2 mesh children to join together
                if parent.type == 'MESH':
                    min_required = 1
                else:
                    min_required = 2

                if len(meshes) < min_required:
                    logger.debug("Not enough mesh children for parent '%s' (need %d, have %d), skipping", 
                               parent.name, min_required, len(meshes))
                    continue

                # Determine if we should join to parent or among siblings
                objects_to_join = []
                target_object = None

                if parent.type == 'MESH' and is_object_valid(parent):
                    # Join children into mesh parent
                    objects_to_join = [parent] + meshes
                    target_object = parent
                    logger.info("Joining %d children into mesh parent '%s'", len(meshes), parent.name)
                else:
                    # Join mesh children together
                    objects_to_join = meshes
                    target_object = meshes[0]
                    logger.info("Joining %d mesh children together (non-mesh parent '%s')", 
                              len(meshes), parent.name)

                # Perform the join operation
                joined_count = self._perform_join(context, objects_to_join, target_object, parent)
                if joined_count > 0:
                    total_joined += joined_count
                    logger.info("JOIN COMPLETED: %d objects joined for parent '%s'", joined_count, self._safe_get_name(parent))

                    # Check if this resulted in only one child, and if so, join to parent
                    if (parent.type == 'MESH' and is_object_valid(parent) and 
                        is_object_valid(target_object) and target_object != parent):
                        
                        # Count remaining children
                        remaining_children = [child for child in parent.children 
                                            if is_object_valid(child) and child.type == 'MESH']
                        
                        if len(remaining_children) == 1:
                            logger.info("AUTO-JOIN: Only one child remains, joining to parent '%s'", parent.name)
                            final_join_count = self._perform_join(context, [parent, remaining_children[0]], parent, parent)
                            if final_join_count > 0:
                                total_joined += final_join_count
                                logger.info("AUTO-JOIN COMPLETED: %d objects joined to parent '%s'", final_join_count, self._safe_get_name(parent))

            except Exception as e:
                parent_name = self._safe_get_name(parent)
                logger.exception("Error processing parent '%s': %s", parent_name, str(e))
                self.report({'WARNING'}, f"Error processing parent '{parent_name}': {str(e)}")
                continue

        # Restore selection
        self._restore_selection(context)

        if total_joined > 0:
            self.report({'INFO'}, f"Joined {total_joined} objects")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No objects were joined")
            return {'CANCELLED'}

    def _safe_get_name(self, obj):
        """Safely get object name without raising ReferenceError."""
        try:
            if hasattr(obj, 'name') and obj.name in bpy.data.objects:
                return obj.name
        except (ReferenceError, AttributeError):
            pass
        return '<unknown>'

    def _perform_join(self, context, objects_to_join, target_object, parent):
        """Perform the actual join operation with proper error handling."""
        try:
            # Validate all objects before joining
            valid_objects = [obj for obj in objects_to_join 
                           if hasattr(obj, 'name') and obj.name in bpy.data.objects]
            
            if len(valid_objects) < 2:
                return 0

            # Handle child reparenting before join
            self._reparent_children(valid_objects, target_object)

            # Deselect all then select objects to join
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except Exception:
                helpers._safe_deselect_all_objects(context)

            for obj in valid_objects:
                try:
                    obj.select_set(True)
                except Exception:
                    logger.warning("Could not select object '%s' for join", self._safe_get_name(obj))

            # Set target as active object
            context.view_layer.objects.active = target_object

            # Ensure object mode and attempt join
            helpers.ensure_object_mode(context, 'OBJECT')
            
            # Log the join operation details
            object_names = [self._safe_get_name(obj) for obj in valid_objects]
            parent_name = self._safe_get_name(parent)
            logger.info("JOINING: %d objects [%s] for parent '%s'", 
                       len(valid_objects), ', '.join(object_names), parent_name)
            
            bpy.ops.object.join()
            
            joined_count = len(valid_objects)
            logger.info("JOIN SUCCESS: %d objects merged successfully", joined_count)
            return joined_count

        except Exception as e:
            parent_name = self._safe_get_name(parent)
            logger.exception("Failed to join objects for parent '%s': %s", parent_name, str(e))
            self.report({'WARNING'}, f"Failed to join objects for parent '{parent_name}': {str(e)}")
            return 0

    def _reparent_children(self, objects_to_join, target_object):
        """Reparent children of objects that will be removed during join."""
        children_to_reparent = []
        
        # Collect children that need reparenting
        for src in objects_to_join:
            if src == target_object:
                continue
            try:
                if not (hasattr(src, 'name') and src.name in bpy.data.objects):
                    continue
                    
                for child in list(src.children):
                    if not (hasattr(child, 'name') and child.name in bpy.data.objects):
                        continue
                    if child in objects_to_join:
                        continue
                    if getattr(child, "parent_type", "OBJECT") != "OBJECT":
                        continue
                    if child.parent == target_object:
                        continue
                    
                    children_to_reparent.append((child, child.matrix_world.copy()))
            except (ReferenceError, AttributeError):
                continue
            except Exception:
                logger.debug("Error collecting children for reparenting from object '%s'", 
                           self._safe_get_name(src))
        
        # Reparent collected children
        for child, original_matrix in children_to_reparent:
            try:
                if not (hasattr(child, 'name') and child.name in bpy.data.objects):
                    continue
                    
                child.parent = target_object
                child.matrix_parent_inverse = target_object.matrix_world.inverted() @ original_matrix
                child.matrix_world = original_matrix
            except (ReferenceError, AttributeError):
                continue
            except Exception:
                logger.debug("Failed to reparent child '%s'", self._safe_get_name(child))

    def _restore_selection(self, context):
        """Restore a sensible selection state."""
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            helpers._safe_deselect_all_objects(context)
        
        if (context.view_layer.objects.active and 
            hasattr(context.view_layer.objects.active, 'name') and
            context.view_layer.objects.active.name in bpy.data.objects):
            try:
                context.view_layer.objects.active.select_set(True)
            except Exception:
                pass
        
        