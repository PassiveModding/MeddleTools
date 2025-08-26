import bpy
from . import blend_import
from . import gltf_import
from . import version
from . import utils

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
    bl_category = "Meddle Tools"
    
    blender_import: bpy.props.BoolProperty(name="Blender Import", default=True)
    

    def draw(self, context):
        if context is None:
            return {'CANCELLED'}
        
        layout = self.layout
             
        # layout.prop(context.scene.meddle_settings, 'gltf_bone_dir', text='Import Mode', expand=True)    
        row = layout.row()
        row.operator(gltf_import.ModelImport.bl_idname, text='Import .gltf/.glb', icon='IMPORT')
        row.operator(ModelImportHelpHover.bl_idname, text='', icon='QUESTION')
        
        if context.scene.meddle_settings.display_import_help:
            self.drawModelImportHelp(layout)

    def drawModelImportHelp(self, layout):
        box = layout.box()
        col = box.column()
        col.label(text="Import and automatically apply shaders")
        col.label(text="Navigate to your Meddle export folder")
        col.label(text="and select the .gltf or .glb file(s)")
            
class ModelImportHelpHover(bpy.types.Operator):
    bl_idname = "meddle.model_import_help_hover"
    bl_label = "Import Help"
    bl_description = "Import and automatically apply shaders. Navigate to your Meddle export folder and select the .gltf or .glb file."
    
    def execute(self, context):
        # toggle the display of the import help
        context.scene.meddle_settings.display_import_help = not context.scene.meddle_settings.display_import_help
        return {'FINISHED'}    

class MeddleShaderImportPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleShaderImportPanel"
    bl_label = "Meddle Shaders"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
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
        row.label(text="Navigate to the 'cache' folder")
        row = col.row()
        row.label(text="in the same folder as your model")
        
        row = layout.row()
        row.operator(gltf_import.ApplyToSelected.bl_idname, text='Apply Shaders to Selected', icon='SHADERFX')
        
        row = layout.row()
        row.operator(blend_import.ImportShaders.bl_idname, text='Import Shaders')
        
        row = layout.row()
        row.operator(blend_import.ReplaceShaders.bl_idname, text='Replace Shaders')

class MeddleUtilsPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleUtilsPanel"
    bl_label = "Meddle Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.meddle_settings
        
        # Find Properties section
        # box = layout.box()
        # col = box.column()
        # col.label(text="Find Properties", icon='VIEWZOOM')
        # row = col.row()
        # row.prop(props, 'search_property', text='Property')
        # row = col.row()
        # row.operator(utils.FindProperties.bl_idname, text='Search Materials')
        
        # Light Boost section
        box = layout.box()
        col = box.column()
        col.label(text="Light Boost", icon='LIGHT')
        row = col.row()
        row.prop(props, 'light_boost_factor', text='Boost Factor')
        row = col.row()
        row.operator(utils.BoostLights.bl_idname, text='Boost All Lights')
        
        # Mesh Operations section
        box = layout.box()
        col = box.column()
        col.label(text="Mesh Operations", icon='MESH_DATA')
        row = col.row()
        row.operator(utils.JoinByMaterial.bl_idname, text='Join Meshes by Material', icon='MESH_CUBE')
        row = col.row()
        row.operator(utils.JoinMeshesToParent.bl_idname, text='Join Meshes to Parent', icon='GROUP')
        row = col.row()
        row.prop(props, 'merge_distance', text='Merge Distance')
        row = col.row()
        row.operator(utils.JoinByDistance.bl_idname, text='Join Vertices by Distance', icon='PARTICLE_DATA')
        
        # Material Operations section
        box = layout.box()
        col = box.column()
        col.label(text="Material Operations", icon='MATERIAL')
        row = col.row()
        row.operator(utils.AddVoronoiTexture.bl_idname, text='Apply Voronoi to Selected', icon='TEXTURE')

        # Animation & Rigging section
        box = layout.box()
        col = box.column()
        col.label(text="Animation & Rigging", icon='ARMATURE_DATA')
        row = col.row()
        row.operator(utils.ImportAnimationGLTF.bl_idname, text='Import Animation GLTF', icon='IMPORT')
        
        # Scene Cleanup section
        box = layout.box()
        col = box.column()
        col.label(text="Scene Cleanup", icon='TRASH')
        row = col.row()
        row.operator(utils.CleanBoneHierarchy.bl_idname, text='Clean Bone Hierarchy', icon='ARMATURE_DATA')
        row = col.row()
        row.operator(utils.RemoveBonesByPrefix.bl_idname, text='Remove Bones by Prefix', icon='ARMATURE_DATA')
        row = col.row()
        row.operator(utils.DeleteEmptyVertexGroups.bl_idname, text='Delete Empty Vertex Groups', icon='GROUP_VERTEX')
        row = col.row()
        row.operator(utils.DeleteUnusedUvMaps.bl_idname, text='Delete Unused UV Maps', icon='MESH_UVSPHERE')
        row = col.row()
        row.operator(utils.PurgeUnused.bl_idname, text='Purge Unused Data')    

class MeddleCreditPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleVersionPanel"
    bl_label = "Credits & Version"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
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
            if version.latest_version != version.current_version:
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
                
                
classes = [
    MeddleHeaderPanel,
    MeddleImportPanel,
    MeddleUtilsPanel,
    MeddleShaderImportPanel,
    MeddleCreditPanel,
    ModelImportHelpHover
]