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

class FindProperties(Operator):
    """Find materials with specific custom properties"""
    bl_idname = "meddle.find_properties"
    bl_label = "Find Properties"
    bl_description = "Search for materials containing the specified property"
    
    def execute(self, context):
        search_value = context.scene.meddle_settings.search_property
        
        if not search_value:
            self.report({'WARNING'}, "Please enter a property to search for")
            return {'CANCELLED'}
        
        matching_materials = []
        
        # Iterate through all materials in the blend file
        for material in bpy.data.materials:
            # Check if the search value exists as a custom property
            if search_value in material:
                matching_materials.append({
                    'material': material.name,
                    'property': search_value,
                    'value': material[search_value]
                })
        
        if matching_materials:
            self.report({'INFO'}, f"Found {len(matching_materials)} material(s) with '{search_value}'")
            logger.info("Searching for materials containing '%s' in custom properties...", search_value)
            for match in matching_materials:
                logger.info("Material: '%s' - %s = %r", match['material'], match['property'], match['value'])
        else:
            self.report({'INFO'}, f"No materials found containing '{search_value}' in their custom properties")
        
        return {'FINISHED'}