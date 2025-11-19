import bpy

class MaterialBakeSettings(bpy.types.PropertyGroup):
    """Settings for individual material baking"""
    material_name: bpy.props.StringProperty(
        name="Material Name",
        description="Name of the material",
        default=""
    )
    
    image_width: bpy.props.IntProperty(
        name="Width",
        description="Width of the baked texture",
        default=2048,
        min=64,
        max=8192
    )
    
    image_height: bpy.props.IntProperty(
        name="Height",
        description="Height of the baked texture",
        default=2048,
        min=64,
        max=8192
    )
    
    atlas_group: bpy.props.IntProperty(
        name="Atlas Group",
        description="Which atlas group this material belongs to (0 = auto-assign)",
        default=0,
        min=0,
        max=32
    )

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
    
    bake_samples: bpy.props.IntProperty(
        name="Bake Samples",
        description="Number of samples to use when baking",
        default=4,
        min=1,
        max=4096
    )
    
    # Bake channel toggles
    bake_diffuse: bpy.props.BoolProperty(
        name="Diffuse",
        description="Bake diffuse/base color channel",
        default=True
    )
    
    bake_normal: bpy.props.BoolProperty(
        name="Normal",
        description="Bake normal map channel",
        default=True
    )
    
    bake_roughness: bpy.props.BoolProperty(
        name="Roughness",
        description="Bake roughness channel",
        default=True
    )
    
    bake_metalness: bpy.props.BoolProperty(
        name="Metalness",
        description="Bake metalness channel",
        default=True
    )
    
    bake_ior: bpy.props.BoolProperty(
        name="IOR",
        description="Bake IOR (Index of Refraction) channel",
        default=True
    )
    
    bake_emission: bpy.props.BoolProperty(
        name="Emission",
        description="Bake emission channel",
        default=True
    )
    
    material_bake_settings: bpy.props.CollectionProperty(
        type=MaterialBakeSettings,
        name="Material Bake Settings",
        description="Per-material bake settings"
    )
    
    active_material_index: bpy.props.IntProperty(
        name="Active Material Index",
        description="Currently selected material in the list",
        default=0
    )
    
def register():
    bpy.utils.register_class(MaterialBakeSettings)
    bpy.utils.register_class(MeddleSettings)
    bpy.types.Scene.meddle_settings = bpy.props.PointerProperty(type=MeddleSettings)
    
def unregister():
    bpy.utils.unregister_class(MeddleSettings)
    bpy.utils.unregister_class(MaterialBakeSettings)
    del bpy.types.Scene.meddle_settings