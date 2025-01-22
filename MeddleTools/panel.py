import glob
import bpy
from . import blend_import
from . import shader_fix
from . import gltf_import
import requests
import addon_utils

repo_url = "https://github.com/PassiveModding/MeddleTools"
repo_release_download_url = "https://github.com/PassiveModding/MeddleTools/releases"
repo_release_url = "https://api.github.com/repos/PassiveModding/MeddleTools/releases/latest"
repo_issues_url = "https://github.com/PassiveModding/MeddleTools/issues"
sponsor_url = "https://github.com/sponsors/PassiveModding"
current_version = "Unknown"
latest_version = "Unknown"

  
def getLatestVersion():
    response = requests.get(repo_release_url)
    if response.status_code != 200:
        raise Exception(f"Failed to get latest version: {response.status_code}")
    data = response.json()
    return data["tag_name"] 

class MeddleMainPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddlePanel"
    bl_label = "Meddle Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"

    def draw(self, context):
        if context is None:
            return {'CANCELLED'}
        
        layout = self.layout
        
        row = layout.row()
        row.operator(gltf_import.ModelImport.bl_idname, text='Import GLTF/GLB')
        
        box = layout.box()
        col = box.column()
        row = col.row()
        row.label(text="Import and automatically apply shaders")
        row = col.row()
        row.label(text="Navigate to your Meddle export folder")
        row = col.row()
        row.label(text="and select the .gltf or .glb file")
        col.separator()
        row = col.row()
        row.label(text="Make sure you exported in 'raw' mode")
        row = col.row()
        row.label(text="from the Meddle ffxiv plugin")
        
        layout.separator()
        

class MeddleShaderImportPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleShaderImportPanel"
    bl_label = "Meddle Shaders"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        row = layout.row()
        section = layout.box()
        col = section.column()
        
        row = col.row()
        row.operator(shader_fix.ShaderFixSelected.bl_idname, text='Apply Shaders to Selected Objects')
        
        row = col.row()
        row.operator(shader_fix.ShaderFixActive.bl_idname, text='Apply Shaders to Current Material')
        
        row = col.row()
        row.label(text="Navigate to the 'cache' folder")
        row = col.row()
        row.label(text="in the same folder as your model")
        
        row = layout.row()
        row.operator(blend_import.ImportShaders.bl_idname, text='Import Shaders')
        
        box = layout.box()
        col = box.column()
        
        row = col.row()
        row.label(text="Imports the Meddle shader node groups")

class MeddleCreditPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleVersionPanel"
    bl_label = "Credits"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"
    
    def draw(self, context):
        layout = self.layout
                
        if latest_version != "Unknown" and current_version != "Unknown":
            if latest_version != current_version:
                box = layout.box()
                col = box.column()
                row = col.row()
                row.label(text=f"New version available: {latest_version}")
                row = col.row()
                row.operator("wm.url_open", text="Download").url = repo_release_download_url
        else:
            row = layout.row()
            row.label(text="Failed to check for updates")
        
        row = layout.row()
        row.label(text=f"Version: {current_version}")
        row = layout.row()
        row.label(text=f"Latest Github Release: {latest_version}")
        
        layout.separator()
        
        # credits
        box = layout.box()
        col = box.column()
        
        row = col.row()
        row.label(text="Developed by:")
        row = col.row()
        row.label(text="  - PassiveModding/Ramen")
        row = col.row()
        row.label(text="Special thanks to:")
        row = col.row()
        row.label(text="  - SkulblakaDrotningu for Lizzer Tools Meddle")
        
        layout.separator()

        row = layout.row()
        row.operator("wm.url_open", text="MeddleTools Github").url = repo_url
        row.operator("wm.url_open", text="Report Issues").url = repo_issues_url
        
        row = layout.row()
        row.operator("wm.url_open", text="Support Meddle").url = sponsor_url
    
classes = [
    blend_import.ImportShaders,
    blend_import.ShaderHelper,
    shader_fix.ShaderFixActive,
    shader_fix.ShaderFixSelected,
    gltf_import.ModelImport,
    MeddleMainPanel,
    MeddleShaderImportPanel,
    MeddleCreditPanel
]

def register():
    try:
        global latest_version
        latest_version = getLatestVersion()
        print(f"Latest version: {latest_version}")
    except Exception as e:
        print(f"Failed to get latest version: {e}")
        
    try:
        global current_version      
        version_set = False 
        for mod in addon_utils.modules():
            if mod.bl_info.get("name") == "Meddle Tools":
                print(f"Found MeddleTools: {mod.bl_info.get('version')}")
                current_version = ".".join([str(v) for v in mod.bl_info.get("version")])
                version_set = True
        if not version_set:
            current_version = "Unknown"
        print(f"Current version: {current_version}")
    except Exception as e:
        print(f"Failed to read current version: {e}")
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)