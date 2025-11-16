import bpy
from .bake import RunBake, get_bake_label
from .atlas import RunAtlas, get_atlas_label
from .export_fbx import ExportFBX
from .reproject_retile import ReprojectRetile, get_reproject_retile_label
from .reproject_rebake import ReprojectRebake
from .create_copy_for_baking import CreateCopyForBaking, get_create_copy_label
from .create_uv_bake_layers import CreateUVBakeLayers, get_create_uv_label
from .join_meshes import JoinMeshes, get_join_label
from . import bake_utils

class MEDDLE_UL_MaterialBakeList(bpy.types.UIList):
    """UI List for displaying materials with bake settings"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.material_name, icon='MATERIAL')
            row.prop(item, "image_width", text="W")
            row.prop(item, "image_height", text="H")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.material_name, icon='MATERIAL')

class MEDDLE_OT_InitMaterialSettings(bpy.types.Operator):
    """Initialize bake settings for materials without settings"""
    bl_idname = "meddle.init_material_settings"
    bl_label = "Initialize Settings"
    bl_description = "Create bake settings for materials that don't have them yet"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return bake_utils.require_mesh_or_armature_selected(context)
    
    def execute(self, context):
        settings = context.scene.meddle_settings
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        
        # Get all materials from selected meshes
        current_materials = {}
        for mesh in mesh_objects:
            for mat in mesh.data.materials:
                if mat:
                    current_materials[mat.name] = mat
        
        # Build set of existing material setting names
        existing_names = {s.material_name for s in settings.material_bake_settings}
        
        # Add settings for new materials
        added_count = 0
        for material_name, material in current_materials.items():
            if material_name not in existing_names:
                default_size = bake_utils.determine_largest_image_size(material)
                item = settings.material_bake_settings.add()
                item.material_name = material_name
                item.image_width = default_size[0]
                item.image_height = default_size[1]
                added_count += 1
        
        if added_count > 0:
            self.report({'INFO'}, f"Initialized settings for {added_count} material(s)")
        else:
            self.report({'INFO'}, "All materials already have settings")
        return {'FINISHED'}

class MEDDLE_OT_ClearMaterialSettings(bpy.types.Operator):
    """Clear bake settings for materials from selected objects"""
    bl_idname = "meddle.clear_material_settings"
    bl_label = "Clear Settings"
    bl_description = "Remove bake settings for materials from selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return bake_utils.require_mesh_or_armature_selected(context)
    
    def execute(self, context):
        settings = context.scene.meddle_settings
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        
        # Get all materials from selected meshes
        current_materials = set()
        for mesh in mesh_objects:
            for mat in mesh.data.materials:
                if mat:
                    current_materials.add(mat.name)
        
        # Remove settings for current materials
        removed_count = 0
        indices_to_remove = []
        for i, s in enumerate(settings.material_bake_settings):
            if s.material_name in current_materials:
                indices_to_remove.append(i)
        
        # Remove in reverse order to maintain indices
        for i in reversed(indices_to_remove):
            settings.material_bake_settings.remove(i)
            removed_count += 1
        
        if removed_count > 0:
            self.report({'INFO'}, f"Cleared settings for {removed_count} material(s)")
        else:
            self.report({'INFO'}, "No settings to clear")
        return {'FINISHED'}

class MeddleBakePanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleBakePanel"
    bl_label = "Baking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    
    def get_selected_materials(self, context):
        """Get all materials from selected mesh objects"""
        mesh_objects = bake_utils.get_all_selected_meshes(context)
        materials = {}
        for mesh in mesh_objects:
            for mat in mesh.data.materials:
                if mat:
                    materials[mat.name] = mat
        return materials
    
    def get_filtered_material_settings(self, context):
        """Get material settings that exist for currently selected materials"""
        settings = context.scene.meddle_settings
        current_materials = self.get_selected_materials(context)
        
        # Build set of current material names for quick lookup
        current_names = set(current_materials.keys())
        
        # Return only existing settings that match current materials, sorted by name
        return sorted(
            [s for s in settings.material_bake_settings if s.material_name in current_names],
            key=lambda s: s.material_name
        )
    
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
        
        # Material Bake Settings Section        
        box.separator()
        box.operator(CreateCopyForBaking.bl_idname, text=get_create_copy_label(context))
        box.operator(CreateUVBakeLayers.bl_idname, text=get_create_uv_label(context))
        
        mat_box = box.box()
        mat_box.label(text="Bake Settings", icon='MATERIAL')
        
        # Get materials and their settings
        current_materials = self.get_selected_materials(context)
        existing_settings = self.get_filtered_material_settings(context)
        existing_names = {s.material_name for s in existing_settings}
        
        # Show init/clear buttons
        if current_materials:
            row = mat_box.row(align=True)
            if len(existing_names) < len(current_materials):
                row.operator(MEDDLE_OT_InitMaterialSettings.bl_idname, icon='ADD')
            if existing_settings:
                row.operator(MEDDLE_OT_ClearMaterialSettings.bl_idname, icon='X')
        
        # Display existing settings
        if existing_settings:
            for mat_setting in existing_settings:
                row = mat_box.row(align=True)
                split = row.split(factor=0.6, align=True)
                split.label(text=mat_setting.material_name, icon='MATERIAL')
                props_row = split.row(align=True)
                props_row.prop(mat_setting, "image_width", text="W")
                props_row.prop(mat_setting, "image_height", text="H")
        elif current_materials:
            mat_box.label(text="Click 'Initialize Settings' above", icon='INFO')
        else:
            mat_box.label(text="No materials found.", icon='INFO')
            
        mat_box.prop(settings, "bake_samples")
        mat_box.operator(RunBake.bl_idname, text=get_bake_label(context))
        box.separator()
        box.operator(JoinMeshes.bl_idname, text=get_join_label(context))
        box.operator(RunAtlas.bl_idname, text=get_atlas_label(context))

        # Export Section
        box = layout.box()
        box.label(text="Export", icon='EXPORT')
        box.operator(ExportFBX.bl_idname, text="Export FBX with Textures")