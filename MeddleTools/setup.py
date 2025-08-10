import bpy
from . import panel
from . import blend_import
from . import shader_fix
from . import gltf_import
from . import version
from . import preferences
from . import utils

classes = [
    version.MeddleToolsInstallUpdate,
    panel.MeddleHeaderPanel,
    panel.MeddleImportPanel,
    panel.MeddleShaderImportPanel,
    panel.MeddleUtilsPanel,
    panel.MeddleCreditPanel,
    panel.ModelImportHelpHover,
    blend_import.ImportShaders,
    blend_import.ReplaceShaders,
    blend_import.ShaderHelper,
    shader_fix.ShaderFixActive,
    shader_fix.ShaderFixSelected,
    shader_fix.LightingBoost,
    shader_fix.MeddleClear,
    gltf_import.ModelImport
] + utils.utility_classes

def register():    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register property groups
    bpy.types.Scene.meddle_utils_props = bpy.props.PointerProperty(type=utils.MeddleUtilsProperties)
        
    preferences.register()
    version.runInit()
        

def unregister():
    # Unregister property groups
    del bpy.types.Scene.meddle_utils_props
    
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    preferences.unregister()