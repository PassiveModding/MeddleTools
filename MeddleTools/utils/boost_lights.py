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

class BoostLights(Operator):
    """Boost all area, spot, and point lights by specified factor"""
    bl_idname = "meddle.boost_lights"
    bl_label = "Boost Lights"
    bl_description = "Boost the power of all area, spot, and point lights by the specified factor"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        boost_factor = context.scene.meddle_settings.light_boost_factor
        
        # Define the light types we want to boost
        target_light_types = {'AREA', 'SPOT', 'POINT'}
        
        # Counter for boosted lights
        boosted_count = 0
        
        # Iterate through all objects in the scene
        for obj in bpy.context.scene.objects:
            # Check if the object is a light and of the target types
            if obj.type == 'LIGHT' and obj.data.type in target_light_types:
                # Store the original power for reference
                original_power = obj.data.energy
                
                # Boost the light power by the specified factor
                obj.data.energy *= boost_factor
                
                # Log info about the boosted light
                logger.info("Boosted %s light '%s': %s -> %s", obj.data.type, obj.name, original_power, obj.data.energy)
                
                boosted_count += 1
        
        if boosted_count > 0:
            self.report({'INFO'}, f"Successfully boosted {boosted_count} lights by {boost_factor}x")
            logger.info("Successfully boosted %d lights by %sx", boosted_count, boost_factor)
        else:
            self.report({'WARNING'}, "No area, spot, or point lights found in the scene")
        
        return {'FINISHED'}