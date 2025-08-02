import bpy

class MeddleSettings(bpy.types.PropertyGroup):
    gltfImportMode: bpy.props.EnumProperty(
        items=[
            ('BLENDER', 'Blender', 'Blender (Bone tips are placed on their local +Y axis (In gLTF space))'),
            ('TEMPERANCE', 'Temperance', 'Temperance (A bone with one child has its tip placed on the axis closest to its child)'),
        ],
        name='Import Mode',
        default='TEMPERANCE',
    )
    
    displayImportHelp: bpy.props.BoolProperty(
        name="Display Import Help",
        default=False,
    )
    
    deduplicateMaterials: bpy.props.BoolProperty(
        name="Deduplicate Materials",
        default=True,
    )
    
def register():
    bpy.utils.register_class(MeddleSettings)
    bpy.types.Scene.model_import_settings = bpy.props.PointerProperty(type=MeddleSettings)
    
def unregister():
    bpy.utils.unregister_class(MeddleSettings)
    del bpy.types.Scene.model_import_settings