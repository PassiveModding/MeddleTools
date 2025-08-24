import bpy

class MeddleSettings(bpy.types.PropertyGroup):
    # gltf_bone_dir: bpy.props.EnumProperty(
    #     items=[
    #         ('BLENDER', 'Blender', 'Blender (Bone tips are placed on their local +Y axis (In gLTF space))'),
    #         ('TEMPERANCE', 'Temperance', 'Temperance (A bone with one child has its tip placed on the axis closest to its child)'),
    #     ],
    #     name='Import Mode',
    #     default='TEMPERANCE',
    # )
    
    display_import_help: bpy.props.BoolProperty(
        name="Display Import Help",
        default=False,
    )
    
    search_property: bpy.props.StringProperty(
        name="Property Search",
        description="Search for materials containing this property",
        default=""
    )
    
    light_boost_factor: bpy.props.FloatProperty(
        name="Light Boost Factor",
        description="Factor to multiply light power by",
        default=10.0,
        min=0.1,
        max=100.0
    )
    
    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description="Distance threshold for merging vertices",
        default=0.001,
        min=0.0001,
        max=1.0
    )
    
    animation_gltf_path: bpy.props.StringProperty(
        name="Animation GLTF Path",
        description="Path to the animation GLTF file to import",
        default="",
        subtype='FILE_PATH'
    )
    
def register():
    bpy.utils.register_class(MeddleSettings)
    bpy.types.Scene.meddle_settings = bpy.props.PointerProperty(type=MeddleSettings)
    
def unregister():
    bpy.utils.unregister_class(MeddleSettings)
    del bpy.types.Scene.meddle_settings