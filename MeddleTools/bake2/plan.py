import math
from dataclasses import dataclass, field

from . import preflight
from .constants import (
    DEFAULT_UV_LAYER,
    OUTPUT_NEW_MATERIAL,
    OUTPUT_REPLACE_MATERIAL,
    PACKED_UV_LAYER,
    UV_SIZE_SCALE_PROP,
)
from .packing import next_power_of_two
from .passes import enabled_passes

# must match the largest dropdown choice in properties.py
MAX_BAKE_SIZE = 8192


@dataclass
class MeshTarget:
    obj: object       # bpy.types.Object (MESH)
    uv_layer: str     # UV layer name to bake with on this mesh


@dataclass
class MaterialJob:
    material: object            # bpy.types.Material
    targets: list               # list[MeshTarget], every mesh using the material
    size: tuple                 # (width, height)
    bake_passes: list           # list[BakePassSpec]
    original_nodes: list = field(default_factory=list)
    images: dict = field(default_factory=dict)       # pass id -> bpy Image
    image_nodes: dict = field(default_factory=dict)  # pass id -> image texture node
    baked_material: object = None                    # set in New Material mode
    finalized: bool = False


@dataclass
class BakeStep:
    job: MaterialJob
    spec: object     # BakePassSpec
    target_index: int

    @property
    def target(self) -> MeshTarget:
        return self.job.targets[self.target_index]

    @property
    def use_clear(self) -> bool:
        # first mesh clears the image, the rest paint into it
        return self.target_index == 0

    @property
    def is_last_target(self) -> bool:
        return self.target_index == len(self.job.targets) - 1


@dataclass
class BakePlan:
    jobs: list       # list[MaterialJob]
    steps: list      # list[BakeStep], grouped by job, then pass, then target
    warnings: list   # human-readable strings surfaced to the user


def selected_meshes(context):
    """Selected mesh objects, plus meshes parented to selected armatures."""
    meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
    for armature in (obj for obj in context.selected_objects if obj.type == 'ARMATURE'):
        for child in armature.children:
            if child.type == 'MESH' and child not in meshes:
                meshes.append(child)
    return meshes


def selected_materials(context):
    """Ordered {name: material} for every material on the selected meshes."""
    materials = {}
    for obj in selected_meshes(context):
        for mat in obj.data.materials:
            if mat is not None:
                materials.setdefault(mat.name, mat)
    return materials


def has_bakeable_selection(context):
    """Cheap poll check; build_plan does the real validation."""
    return any(obj.type in {'MESH', 'ARMATURE'} for obj in context.selected_objects)


def choose_uv_layer(obj):
    """Pick the UV layer to bake with, or None if the mesh has no UVs."""
    uv_layers = obj.data.uv_layers
    if PACKED_UV_LAYER in uv_layers:
        return PACKED_UV_LAYER
    if DEFAULT_UV_LAYER in uv_layers:
        return DEFAULT_UV_LAYER
    if uv_layers.active is not None:
        return uv_layers.active.name
    return None


def material_is_bakeable(material):
    if not material.use_nodes:
        return False, "does not use nodes"
    nodes = material.node_tree.nodes
    if not any(node.type == 'BSDF_PRINCIPLED' for node in nodes):
        return False, "has no Principled BSDF node"
    if not any(node.type == 'OUTPUT_MATERIAL' for node in nodes):
        return False, "has no Material Output node"
    return True, ""


def largest_source_size(material):
    """Square size matching the largest source texture (legacy behavior)."""
    max_dim = 0
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and "_array" not in node.image.name:
                max_dim = max(max_dim, node.image.size[0], node.image.size[1])
    if max_dim == 0:
        max_dim = 1024
    return (max_dim, max_dim)


def resolve_size(settings, material, targets=()):
    """Bake size for a material: ``(size, capped)``. AUTO applies the
    multiplier; any other dropdown value is used as-is."""
    for row in settings.material_settings:
        if row.material_name == material.name and row.size != 'AUTO':
            size = int(row.size)
            return (size, size), False
    return apply_size_multiplier(
        largest_source_size(material), size_multiplier(targets))


def size_multiplier(targets):
    """Largest PRESERVE-method size multiplier (see uvprep) among targets
    baking the packed UV layer."""
    multiplier = 1.0
    for target in targets:
        if target.uv_layer != PACKED_UV_LAYER:
            continue
        multiplier = max(
            multiplier, float(target.obj.data.get(UV_SIZE_SCALE_PROP, 1.0)))
    return multiplier


def apply_size_multiplier(size, multiplier):
    """Grow ``size`` by ``multiplier``, rounded up to a power of two.
    ``capped`` is True when MAX_BAKE_SIZE cut it short.
    """
    if multiplier <= 1.0:
        return size, False
    width = next_power_of_two(math.ceil(size[0] * multiplier))
    height = next_power_of_two(math.ceil(size[1] * multiplier))
    capped = width > MAX_BAKE_SIZE or height > MAX_BAKE_SIZE
    return (min(width, MAX_BAKE_SIZE), min(height, MAX_BAKE_SIZE)), capped


def build_plan(context):
    """Build a BakePlan from the current selection.
    Returns ``(plan, None)`` or ``(None, error_message)``.
    """
    settings = context.scene.meddle_bake2

    passes = enabled_passes(settings)
    if not passes:
        return None, "Enable at least one bake channel"

    meshes = selected_meshes(context)
    if not meshes:
        return None, "Select at least one mesh (or an armature with child meshes)"

    warnings = []

    # material -> targets, preserving first-seen order
    targets_by_material = {}
    for obj in meshes:
        uv_layer = choose_uv_layer(obj)
        if uv_layer is None:
            warnings.append(f"Skipped '{obj.name}': no UV layers")
            continue
        for mat in obj.data.materials:
            if mat is None:
                continue
            targets = targets_by_material.setdefault(mat, [])
            if not any(target.obj is obj for target in targets):
                targets.append(MeshTarget(obj=obj, uv_layer=uv_layer))

    jobs = []
    for material, targets in targets_by_material.items():
        ok, reason = material_is_bakeable(material)
        if not ok:
            warnings.append(f"Skipped material '{material.name}': {reason}")
            continue
        size, capped = resolve_size(settings, material, targets)
        if capped:
            warnings.append(
                f"Material '{material.name}': layout-preserving UVs need more "
                f"than {MAX_BAKE_SIZE}px to keep full detail, baking at "
                f"{MAX_BAKE_SIZE} with reduced texel density")
        jobs.append(MaterialJob(
            material=material,
            targets=targets,
            size=size,
            bake_passes=list(passes),
        ))

    if not jobs:
        message = "No bakeable materials on the selected meshes"
        if warnings:
            message += f" ({warnings[0]})"
        return None, message

    # stacked islands aren't warned here (mirrored copies bake fine), only
    # noted in the panel's mesh rows
    analyzed = set()
    for job in jobs:
        for target in job.targets:
            if target.obj.name in analyzed:
                continue
            analyzed.add(target.obj.name)
            report = preflight.safe_analyze_object(target.obj, target.uv_layer)
            if report is not None and report.has_problems:
                _status, summary, _hint = preflight.summarize(report, target.obj)
                warnings.append(
                    f"'{target.obj.name}' UVs ({target.uv_layer}): {summary}")

    # Replace mode also affects meshes outside the selection that share it
    if getattr(settings, 'output_mode', OUTPUT_NEW_MATERIAL) == OUTPUT_REPLACE_MATERIAL:
        target_names = {t.obj.name for job in jobs for t in job.targets}
        for job in jobs:
            external = [
                obj.name for obj in context.scene.objects
                if obj.type == 'MESH' and obj.name not in target_names
                and any(mat is job.material for mat in obj.data.materials)
            ]
            if external:
                shown = ", ".join(external[:3]) + ("..." if len(external) > 3 else "")
                warnings.append(
                    f"Material '{job.material.name}' is also used by unselected "
                    f"mesh(es) {shown}; Replace mode will change them too "
                    "(use New Material mode to leave them untouched)")

    steps = [
        BakeStep(job=job, spec=spec, target_index=index)
        for job in jobs
        for spec in job.bake_passes
        for index in range(len(job.targets))
    ]

    return BakePlan(jobs=jobs, steps=steps, warnings=warnings), None
