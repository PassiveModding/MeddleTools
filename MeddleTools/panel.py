import bpy
from . import blend_import
from . import shader_fix
from . import gltf_import
from . import version

repo_url = "https://github.com/PassiveModding/MeddleTools"
repo_issues_url = "https://github.com/PassiveModding/MeddleTools/issues"
sponsor_url = "https://github.com/sponsors/PassiveModding"
carrd_url = "https://meddle.carrd.co/"
discord_url = "https://discord.gg/2jnZMNVM4p"
kofi_url = "https://ko-fi.com/ramen_au"


class MeddleImportPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddlePanel"
    bl_label = "Meddle Import"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"
    
    blender_import: bpy.props.BoolProperty(name="Blender Import", default=True)
    

    def draw(self, context):
        if context is None:
            return {'CANCELLED'}
        
        layout = self.layout
             
        layout.prop(context.scene.model_import_settings, 'gltfImportMode', text='Import Mode', expand=True)    
        layout.prop(context.scene.model_import_settings, 'deduplicateMaterials', text='Deduplicate Materials') 
        row = layout.row()
        row.operator(gltf_import.ModelImport.bl_idname, text='Import .gltf/.glb', icon='IMPORT')
        row.operator(ModelImportHelpHover.bl_idname, text='', icon='QUESTION')
        
        if context.scene.model_import_settings.displayImportHelp:
            self.drawModelImportHelp(layout)

    def drawModelImportHelp(self, layout):
        box = layout.box()
        col = box.column()
        col.label(text="Import and automatically apply shaders")
        col.label(text="Navigate to your Meddle export folder")
        col.label(text="and select the .gltf or .glb file")
            
class ModelImportHelpHover(bpy.types.Operator):
    bl_idname = "meddle.model_import_help_hover"
    bl_label = "Import Help"
    bl_description = "Import and automatically apply shaders. Navigate to your Meddle export folder and select the .gltf or .glb file."
    
    def execute(self, context):
        # toggle the display of the import help
        context.scene.model_import_settings.displayImportHelp = not context.scene.model_import_settings.displayImportHelp
        return {'FINISHED'}    

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
        
        # note that this section is mostly for testing
        row = layout.row()
        section = layout.box()
        col = section.column()
        row = col.row()
        row.label(text="This section is mostly for testing purposes")
        row = col.row()
        row.label(text="in most cases you can just use")
        row = col.row()
        row.label(text="the Import .gltf/.glb operator")

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
        
        row = layout.row()
        row.operator(blend_import.ReplaceShaders.bl_idname, text='Replace Shaders')
        
        box = layout.box()
        col = box.column()
        
        row = col.row()
        row.label(text="Imports the Meddle shader node groups")
        
        row = layout.row()
        row.operator(shader_fix.LightingBoost.bl_idname, text='Reparse Lights')
        
        row = layout.row()
        row.operator(shader_fix.MeddleClear.bl_idname, text='Clear Applied Status')
        
        row = layout.row()
        row.operator(shader_fix.AddVoronoiTexture.bl_idname, text='Apply Voronoi to selected terrains')

class MeddleCreditPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleVersionPanel"
    bl_label = "Credits & Version"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools"
    
    def draw(self, context):
        layout = self.layout
        
        section = layout.box()
        col = section.column()
        row = col.row()
        row.label(text=f"Version: {version.current_version}")
        row = col.row()
        row.label(text=f"Latest Release ({version.latest_version})")
        row = col.row()
        if version.latest_version_name is not None:
            row.label(text=f"{version.latest_version_name}")
        else:
            row.label(text="Unknown")
        
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
    
class MeddleHeaderPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleHeaderPanel"
    bl_label = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "Meddle Tools" 
    
    def draw_header(self, context):
        self.layout.label(text=f"Meddle Tools {version.current_version}", icon='INFO')

    def draw(self, context):
        layout = self.layout
        
        layout.operator("wm.url_open", text="Carrd", icon="HELP").url = carrd_url
        layout.operator("wm.url_open", text="Discord", icon="COMMUNITY").url = discord_url
        layout.operator("wm.url_open", text="Sponsor via Ko-Fi", icon="HEART").url = kofi_url
        
        row = layout.row()
        row.operator("wm.url_open", text="Github", icon="HELP").url = repo_url
        row.operator("wm.url_open", text="Issues", icon="BOOKMARKS").url = repo_issues_url
        
        if version.latest_version != "Unknown" and version.current_version != "Unknown":
            if True or version.latest_version != version.current_version:
                box = layout.box()
                col = box.column()
                row = col.row()
                row.label(text=f"Current version: {version.current_version}")
                row = col.row()
                row.label(text=f"New version available: {version.latest_version}")
                row = col.row()
                row.operator("wm.url_open", text="Download").url = version.GITHUB_RELEASE_PAGE_URL
                row = col.row()
                row.operator(version.MeddleToolsInstallUpdate.bl_idname, text="Install Automatically", icon='FILE_TICK')
                row = col.row()
                row.label(text=f"{version.latest_version_name}")