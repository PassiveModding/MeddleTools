import bpy
from . import blend_import
from . import shader_fix
# get the latest version from the github release page
import requests
import toml
import os

repo_url = "https://github.com/PassiveModding/MeddleTools"
repo_api_url = "https://raw.githubusercontent.com/PassiveModding/MeddleTools/main/MeddleTools/blender_manifest.toml"
current_version = "Unknown"
latest_version = "Unknown"

  
def getLatestVersion():
    response = requests.get(repo_api_url)
    if response.status_code != 200:
        raise Exception(f"Failed to get latest version: {response.status_code}")
    data = toml.loads(response.text)
    return data["version"] 

class MeddlePanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddlePanel"
    bl_label = "Meddle Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"

    def draw(self, context):
        if context is None:
            return {'CANCELLED'}
        
        obj = context.object

        layout = self.layout

        row = layout.row()
        row.operator(blend_import.ImportShaders.bl_idname, text='Import Shaders')
        
        row = layout.row()
        row.operator(shader_fix.ShaderFixSelected.bl_idname, text='Apply Shaders to Selected Objects')
        
        row = layout.row()
        row.operator(shader_fix.ShaderFixActive.bl_idname, text='Apply Shaders to Current Material')
        
        row = layout.row()
        row = layout.row()
        row.label(text=f"Version: {current_version}")
        
        row = layout.row()
        row.label(text=f"Latest Github Release: {latest_version}")
        
        if latest_version != "Unknown" and current_version != "Unknown":
            if latest_version != current_version:
                row = layout.row()
                row.label(text="New version available!")
                row = layout.row()
                row.operator("wm.url_open", text="Download").url = repo_url
        else:
            row = layout.row()
            row.label(text="Failed to check for updates")
        
        row = layout.row()
        row.operator("wm.url_open", text="Meddle Github").url = repo_url


classes = [
    blend_import.ImportShaders,
    shader_fix.ShaderFixActive,
    shader_fix.ShaderFixSelected,
    MeddlePanel,
]

def register():
    try:
        global latest_version
        latest_version = getLatestVersion()
    except Exception as e:
        print(f"Failed to get latest version: {e}")
        
    try:
        # read from addon.json Version property
        with open(os.path.join(os.path.dirname(__file__), 'blender_manifest.toml')) as f:
            data = toml.load(f)
            global current_version
            current_version = data["version"]
    except Exception as e:
        print(f"Failed to read current version: {e}")
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)