import bpy
from .bake import RunBake, get_bake_label
from .atlas import RunAtlas, get_atlas_label
from .export_fbx import ExportFBX
from .reproject_retile import ReprojectRetile, get_reproject_retile_label
from .reproject_rebake import ReprojectRebake
from .create_copy_for_baking import CreateCopyForBaking
from .create_uv_bake_layers import CreateUVBakeLayers
from .join_meshes import JoinMeshes, get_join_label

class MeddleBakePanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleBakePanel"
    bl_label = "Baking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.meddle_settings
        
        # UV Reproject and Retile Section
        # box = layout.box()
        # box.label(text="UV Operations", icon='UV')
        # box.operator(ReprojectRetile.bl_idname, text=get_reproject_retile_label(context))
        
        # Baking Section
        box = layout.box()
        box.label(text="Baking", icon='RENDER_STILL')
        
        # Project save warning
        if not bpy.data.is_saved:
            col = box.column(align=True)
            col.alert = True
            col.label(text="Save project before baking!", icon='ERROR')
            box.separator(factor=0.5)
        
        box.prop(settings, "pack_uv_islands")
        box.prop(settings, "bake_samples")
        box.operator(CreateCopyForBaking.bl_idname, text="Create Copy for Baking")
        box.operator(CreateUVBakeLayers.bl_idname, text="Create UV Bake Layers")
        box.operator(RunBake.bl_idname, text=get_bake_label(context))
        box.operator(JoinMeshes.bl_idname, text=get_join_label(context))
        
        # Texture Atlas Section
        box = layout.box()
        box.label(text="Texture Atlas", icon='TEXTURE')
        box.prop(settings, "pack_alpha")
        box.operator(RunAtlas.bl_idname, text=get_atlas_label(context))
        # box.operator(ReprojectRebake.bl_idname, text="Reproject and Rebake Atlas")
        
        # Export Section
        box = layout.box()
        box.label(text="Export", icon='EXPORT')
        box.operator(ExportFBX.bl_idname, text="Export FBX with Textures")