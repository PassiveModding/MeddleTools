import bpy
from . import panel
from . import blend_import
from . import gltf_import
from . import version
from . import preferences
from . import utils
from . import bake

classes = [] + gltf_import.classes + panel.classes + blend_import.classes + utils.classes + version.classes + bake.classes

def register():    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register property groups        
    preferences.register()
    version.runInit()
        

def unregister():
    # Unregister property groups
    
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    preferences.unregister()