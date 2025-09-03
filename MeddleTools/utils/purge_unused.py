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

class PurgeUnused(Operator):
    """Remove all unused datablocks from the scene"""
    bl_idname = "meddle.purge_unused"
    bl_label = "Purge Unused Data"
    bl_description = "Remove all unused materials, textures, meshes, and other datablocks to optimize the file"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Store initial counts for reporting
        initial_counts = {}
        final_counts = {}
        
        # Get initial counts of different data types
        data_types = [
            ('materials', bpy.data.materials),
            ('textures', bpy.data.textures),
            ('images', bpy.data.images),
            ('meshes', bpy.data.meshes),
            ('curves', bpy.data.curves),
            ('fonts', bpy.data.fonts),
            ('node_groups', bpy.data.node_groups),
            ('actions', bpy.data.actions),
            ('armatures', bpy.data.armatures)
        ]
        
        for name, data_collection in data_types:
            initial_counts[name] = len(data_collection)
        
        # Perform multiple purge passes to catch interdependent unused data
        purge_passes = 3
        total_removed = 0
        
        for pass_num in range(purge_passes):
            removed_this_pass = 0
            
            # Purge each data type
            for name, data_collection in data_types:
                before_count = len(data_collection)
                
                # Remove unused datablocks
                for item in list(data_collection):
                    if item.users == 0:
                        try:
                            data_collection.remove(item)
                            removed_this_pass += 1
                        except:
                            # Some items might not be removable
                            pass
                
                after_count = len(data_collection)
                pass_removed = before_count - after_count
                
                if pass_removed > 0:
                    logger.info("Pass %d: Removed %d unused %s", pass_num + 1, pass_removed, name)
            
            total_removed += removed_this_pass
            
            # If nothing was removed this pass, we can stop early
            if removed_this_pass == 0:
                break
        
        # Get final counts
        for name, data_collection in data_types:
            final_counts[name] = len(data_collection)
        
        # Report summary
        if total_removed > 0:
            self.report({'INFO'}, f"Purged {total_removed} unused datablocks")
            logger.info("=== Purge Unused Data Summary ===")
            logger.info("Total datablocks removed: %d", total_removed)
            for name, _ in data_types:
                removed = initial_counts[name] - final_counts[name]
                if removed > 0:
                    logger.info("  %s: %d removed (%d → %d)", name.title(), removed, initial_counts[name], final_counts[name])
            logger.info("%s", "=" * 35)
        else:
            self.report({'INFO'}, "No unused datablocks found to remove")
        
        return {'FINISHED'}