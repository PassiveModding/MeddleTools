import bpy


def gltf_import_option_defs():
    """Property definitions for the glTF import options (copied from the
    built-in glTF 2.0 importer).

    Shared by the import operator and the add-on preferences, which hold the
    user's preferred defaults. Returns a fresh dict each call because property
    definitions are consumed when a class is registered.
    """
    return {
        'import_shading': bpy.props.EnumProperty(
            name="Shading",
            items=(
                ("NORMALS", "Use Normal Data", ""),
                ("FLAT", "Flat Shading", ""),
                ("SMOOTH", "Smooth Shading", ""),
            ),
            description="How normals are computed during import",
            default="NORMALS",
        ),
        'export_import_convert_lighting_mode': bpy.props.EnumProperty(
            name='Lighting Mode',
            items=(
                ('SPEC', 'Standard', 'Physically-based glTF lighting units (cd, lx, nt)'),
                (
                    'COMPAT',
                    'Unitless',
                    'Non-physical, unitless lighting. Useful when exposure controls are not available',
                ),
                ('RAW', 'Raw (Deprecated)', 'Blender lighting strengths with no conversion'),
            ),
            description='Optional backwards compatibility for non-standard render engines. Applies to lights',
            default='SPEC',
        ),
        'merge_vertices': bpy.props.BoolProperty(
            name='Merge Vertices',
            description=(
                'The glTF format requires discontinuous normals, UVs, and '
                'other vertex attributes to be stored as separate vertices, '
                'as required for rendering on typical graphics hardware. '
                'This option attempts to combine co-located vertices where possible. '
                'Currently cannot combine verts with different normals'
            ),
            default=True,
        ),
        'import_merge_material_slots': bpy.props.BoolProperty(
            name='Merge Material Slot when possible',
            description='Merge material slots when possible',
            default=True,
        ),
        'bone_heuristic': bpy.props.EnumProperty(
            name="Bone Dir",
            items=(
                (
                    "BLENDER",
                    "Blender (best for import/export round trip)",
                    "Good for re-importing glTFs exported from Blender, "
                    "and re-exporting glTFs to glTFs after Blender editing. "
                    "Bone tips are placed on their local +Y axis (in glTF space)",
                ),
                (
                    "TEMPERANCE",
                    "Temperance (average)",
                    "Decent all-around strategy. "
                    "A bone with one child has its tip placed on the local axis "
                    "closest to its child",
                ),
                (
                    "FORTUNE",
                    "Fortune (may look better, less accurate)",
                    "Might look better than Temperance, but also might have errors. "
                    "A bone with one child has its tip placed at its child's root. "
                    "Non-uniform scalings may get messed up though, so beware",
                ),
            ),
            description="Heuristic for placing bones. Tries to make bones pretty",
            default="TEMPERANCE",
        ),
        'guess_original_bind_pose': bpy.props.BoolProperty(
            name='Guess Original Bind Pose',
            description=(
                'Try to guess the original bind pose for skinned meshes from '
                'the inverse bind matrices. '
                'When off, use default/rest pose as bind pose'
            ),
            default=True,
        ),
        'disable_bone_shape': bpy.props.BoolProperty(
            name='Disable Bone Shape', description='Do not create bone shapes', default=False
        ),
        'bone_shape_scale_factor': bpy.props.FloatProperty(
            name='Bone Shape Scale', description='Scale factor for bone shapes', default=1.0
        ),
        'import_pack_images': bpy.props.BoolProperty(
            name='Pack Images', description='Pack all images into .blend file', default=True
        ),
        'import_select_created_objects': bpy.props.BoolProperty(
            name='Select Imported Objects',
            description='Select created objects at the end of the import',
            default=True,
        ),
    }


GLTF_IMPORT_OPTION_KEYS = tuple(gltf_import_option_defs().keys())


def meddle_import_option_defs():
    """Property definitions for Meddle-specific post-import options.

    Unlike gltf_import_option_defs(), these are not forwarded as kwargs to
    bpy.ops.import_scene.gltf - they control extra processing steps the
    import operator runs after the glTF itself has been imported.
    """
    return {
        'auto_remove_empty_vertex_groups': bpy.props.BoolProperty(
            name='Remove Empty Vertex Groups',
            description='Automatically delete vertex groups with no weighted vertices from imported meshes',
            default=False,
        ),
        'auto_clean_bone_hierarchy': bpy.props.BoolProperty(
            name='Clean Bone Hierarchy',
            description='Automatically remove bones from imported armatures that do not affect any vertices',
            default=False,
        ),
    }


MEDDLE_IMPORT_OPTION_KEYS = tuple(meddle_import_option_defs().keys())


class MeddleAddonPreferences(bpy.types.AddonPreferences):
    """Add-on level preferences: persisted across sessions and .blend files."""

    bl_idname = __package__

    enable_update_check: bpy.props.BoolProperty(
        name="Check for Updates on Startup",
        description=(
            "Fetch the latest MeddleTools version number from GitHub after startup "
            "to show update notifications. Disable to prevent any network access"
        ),
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'enable_update_check')

        box = layout.box()
        box.label(text="Default glTF Import Options", icon='IMPORT')
        box.label(
            text="Initial values for the Import Model dialog. Options changed in the dialog last for the session."
        )
        for key in GLTF_IMPORT_OPTION_KEYS:
            box.prop(self, key)
        for key in MEDDLE_IMPORT_OPTION_KEYS:
            box.prop(self, key)


# The import option properties are defined once in gltf_import_option_defs()
# and meddle_import_option_defs(); inject them as annotations so
# register_class picks them up.
for _name, _prop in gltf_import_option_defs().items():
    MeddleAddonPreferences.__annotations__[_name] = _prop
for _name, _prop in meddle_import_option_defs().items():
    MeddleAddonPreferences.__annotations__[_name] = _prop


def get_addon_preferences(context=None):
    """Return the MeddleAddonPreferences instance, or None if unavailable."""
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


class MeddleSettings(bpy.types.PropertyGroup):
    display_import_help: bpy.props.BoolProperty(
        name="Display Import Help",
        default=False,
    )

    search_property: bpy.props.StringProperty(
        name="Property Search", description="Search for materials containing this property", default=""
    )

    light_boost_factor: bpy.props.FloatProperty(
        name="Light Boost Factor", description="Factor to multiply light power by", default=10.0, min=0.1, max=100.0
    )

    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance", description="Distance threshold for merging vertices", default=0.001, min=0.0001, max=1.0
    )

    animation_gltf_path: bpy.props.StringProperty(
        name="Animation GLTF Path",
        description="Path to the animation GLTF file to import",
        default="",
        subtype='FILE_PATH',
    )


def register():
    bpy.utils.register_class(MeddleAddonPreferences)
    bpy.utils.register_class(MeddleSettings)
    bpy.types.Scene.meddle_settings = bpy.props.PointerProperty(type=MeddleSettings)


def unregister():
    bpy.utils.unregister_class(MeddleSettings)
    bpy.utils.unregister_class(MeddleAddonPreferences)
    del bpy.types.Scene.meddle_settings
