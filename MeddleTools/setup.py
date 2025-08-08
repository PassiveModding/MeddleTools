import bpy
from . import panel
from . import blend_import
from . import shader_fix
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
    blend_import.ShaderHelper,
    shader_fix.ShaderFixActive,
    shader_fix.ShaderFixSelected,
    shader_fix.LightingBoost,
    shader_fix.MeddleClear,
    shader_fix.AddVoronoiTexture,
    gltf_import.ModelImport
]

def register():    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    preferences.register()
    version.runInit()
        

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    preferences.unregister()