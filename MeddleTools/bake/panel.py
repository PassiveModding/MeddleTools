import bpy
from . import RunBake

class MeddleBakePanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MeddleBakePanel"
    bl_label = "Baking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator(RunBake.bl_idname, text="Run Bake")