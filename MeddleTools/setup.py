import bpy
from . import panel
from . import blend_import
from . import gltf_import
from . import version
from . import preferences

classes = [
    version.MeddleToolsInstallUpdate,
    panel.MeddleHeaderPanel,
    panel.MeddleImportPanel,
    panel.MeddleShaderImportPanel,
    panel.MeddleCreditPanel,
    panel.ModelImportHelpHover,
    blend_import.ImportShaders,
    blend_import.ReplaceShaders,
    gltf_import.ModelImport
]

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