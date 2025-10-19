import bpy
from .bake import RunBake
from .atlas import RunAtlas
from .export_fbx import ExportFBX

class MeddleBakePanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleBakePanel"
    bl_label = "Baking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        # warning to disable decal or other uv1 relayed layers to avoid baking issues
        row.label(text="Due to symmetry of faces, decals may bake incorrectly.", icon='ERROR')
        row = layout.row()
        row.label(text="Please disable decal or other UV1 relayed layers before baking", icon='ERROR')

        row = layout.row()
        row.prop(context.scene.meddle_settings, "bake_samples")
        
        row = layout.row()        
        row.operator(RunBake.bl_idname, text="Run Bake")
        
        # Separator for atlas section
        layout.separator()
        
        row = layout.row()
        row.label(text="Texture Atlas", icon='TEXTURE')
        
        row = layout.row()
        row.prop(context.scene.meddle_settings, "pack_alpha")
        
        row = layout.row()
        row.operator(RunAtlas.bl_idname, text="Create Atlas from Selection")
        
        # Separator for export section
        layout.separator()
        
        row = layout.row()
        row.label(text="Export", icon='EXPORT')
        
        row = layout.row()
        row.operator(ExportFBX.bl_idname, text="Export FBX with Textures")