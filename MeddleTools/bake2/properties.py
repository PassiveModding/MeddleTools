import bpy

from . import plan
from .constants import OUTPUT_NEW_MATERIAL, OUTPUT_REPLACE_MATERIAL
from .passes import PASSES

_SIZE_CHOICES = (256, 512, 1024, 2048, 4096, 8192)


def nearest_size_choice(size):
    """Smallest size dropdown choice that holds ``size`` pixels."""
    for choice in _SIZE_CHOICES:
        if choice >= size:
            return str(choice)
    return str(_SIZE_CHOICES[-1])

# Blender requires Python to keep the strings returned by an enum items
# callback referenced, or the UI reads freed memory; this holds the last
# result per material row.
_size_items_refs = {}


def _size_items(self, context):
    """Size choices for one material row, with the material's actual auto
    size shown in the Auto label (e.g. "Auto (2048)")."""
    auto_label = "Auto"
    material = bpy.data.materials.get(self.material_name)
    if material is not None:
        auto_size, _height = plan.largest_source_size(material)
        auto_label = f"Auto ({auto_size})"
    # Indices are fixed so values saved in existing .blend files keep meaning.
    items = [('AUTO', auto_label,
              "Match the largest source texture in the material", 0)]
    items += [
        (str(size), f"{size}", f"Bake to {size} x {size} pixels", index + 1)
        for index, size in enumerate(_SIZE_CHOICES)
    ]
    _size_items_refs[self.material_name] = items
    return items


class MeddleBake2MaterialSettings(bpy.types.PropertyGroup):
    """Per-material overrides, keyed by material name."""

    material_name: bpy.props.StringProperty(
        name="Material",
        description="Name of the material this row configures",
        default="",
    )

    # No default=: dynamic enums take the first item ('AUTO') as default.
    size: bpy.props.EnumProperty(
        name="Size",
        description="Resolution of the baked textures for this material",
        items=_size_items,
    )

    atlas_group: bpy.props.IntProperty(
        name="Atlas Group",
        description=(
            "Materials with the same group number are combined by Atlas & "
            "Join after baking; 0 keeps this material out of any atlas"
        ),
        default=1,
        min=0,
        soft_max=9,
    )


class MeddleBake2MeshInfo(bpy.types.PropertyGroup):
    """Read-only preflight result row for one mesh (rebuilt on Refresh)."""

    mesh_name: bpy.props.StringProperty(name="Mesh", default="")

    uv_layer: bpy.props.StringProperty(
        name="Bake UV Layer",
        description="UV layer the bake will rasterize into on this mesh",
        default="",
    )

    polygons: bpy.props.IntProperty(name="Polygons", default=0)

    islands: bpy.props.IntProperty(name="UV Islands", default=0)

    status: bpy.props.EnumProperty(
        name="Status",
        items=[
            ('OK', "OK", "UVs will bake correctly"),
            ('WARNING', "Warning", "May bake with reduced quality"),
            ('PROBLEM', "Problem", "Will bake incorrectly or be excluded"),
        ],
        default='OK',
    )

    summary: bpy.props.StringProperty(
        name="Summary",
        description="Preflight findings for this mesh",
        default="",
    )

    extra_warning: bpy.props.StringProperty(
        name="Extra Warning",
        description="Additional advisory shown as its own alert row under "
                    "the mesh, with the row's UV buttons highlighted",
        default="",
    )


class MeddleBake2Settings(bpy.types.PropertyGroup):
    # A bake_<pass id> BoolProperty per registered pass is injected below.

    samples: bpy.props.IntProperty(
        name="Samples",
        description="Cycles samples per bake pass (color-only passes need very few)",
        default=4,
        min=1,
        max=1024,
    )

    device: bpy.props.EnumProperty(
        name="Device",
        description="Compute device Cycles bakes with",
        items=[
            ('GPU', "GPU Compute",
             "Bake on the GPU. Falls back to the CPU if no compute device is "
             "configured in Blender's Cycles preferences"),
            ('CPU', "CPU",
             "Bake on the CPU. Slower, but works everywhere"),
        ],
        default='GPU',
    )

    output_mode: bpy.props.EnumProperty(
        name="Material Output",
        description="What happens to a material when its bake finishes",
        items=[
            (OUTPUT_NEW_MATERIAL, "New Material",
             "Create '<name>.baked' and assign it to the baked meshes only. "
             "The original material is untouched, so it's safe when unselected "
             "meshes share it, and re-bakes always read the pristine source"),
            (OUTPUT_REPLACE_MATERIAL, "Replace",
             "Rewrite the material in place with the baked result. Every mesh "
             "using it is affected, including meshes outside the bake selection"),
        ],
        default=OUTPUT_NEW_MATERIAL,
    )

    material_settings: bpy.props.CollectionProperty(
        type=MeddleBake2MaterialSettings,
        name="Material Settings",
        description="Per-material bake overrides",
    )

    mesh_info: bpy.props.CollectionProperty(
        type=MeddleBake2MeshInfo,
        name="Mesh Preflight",
        description="Per-mesh UV preflight results (rebuilt on Refresh)",
    )


# Channel toggles are derived from the pass registry so a new pass in
# passes.py automatically gets a setting (and UI toggle) with no edits here.
for _spec in PASSES:
    MeddleBake2Settings.__annotations__[_spec.toggle_attr] = bpy.props.BoolProperty(
        name=_spec.label,
        description=_spec.description,
        default=_spec.default_enabled,
    )


def get_settings(context) -> MeddleBake2Settings:
    return context.scene.meddle_bake2


def find_material_settings(settings, material_name):
    """Return the per-material row for ``material_name``, or None."""
    for row in settings.material_settings:
        if row.material_name == material_name:
            return row
    return None
