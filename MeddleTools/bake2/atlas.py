import logging
import os
from dataclasses import dataclass

import bpy
import numpy as np

from . import engine, plan as plan_mod, properties
from .constants import (
    ATLAS_PREFIX,
    ATLAS_UV_LAYER,
    BAKE_IMAGE_PREFIX,
    BAKE_OUTPUT_DIR,
    BAKED_MATERIAL_SUFFIX,
)
from .packing import pack_rects, resize_bilinear
from .passes import PASS_MAP, PASSES

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass
class AtlasEntry:
    material: object   # baked bpy Material as assigned on the meshes
    images: dict       # pass id -> bpy Image
    size: tuple        # (width, height) of this material's atlas tile


@dataclass
class AtlasGroup:
    group_id: int
    entries: list      # [AtlasEntry]
    meshes: list       # objects whose UVs/slots are rewritten, then joined


def pass_images(material):
    """pass id -> bpy Image, found by the ``Bake_<pass id>_...`` naming
    convention."""
    found = {}
    if material is None or not material.use_nodes:
        return found
    for node in material.node_tree.nodes:
        if node.type != 'TEX_IMAGE' or node.image is None:
            continue
        name = node.image.name
        if not name.startswith(BAKE_IMAGE_PREFIX):
            continue
        pass_id = name[len(BAKE_IMAGE_PREFIX):].split('_', 1)[0]
        if pass_id in PASS_MAP:
            found.setdefault(pass_id, node.image)
    return found


def _atlas_group_of(settings, material_name):
    """Atlas group for a material; '<name>.baked' inherits its source's row."""
    row = properties.find_material_settings(settings, material_name)
    if row is None and material_name.endswith(BAKED_MATERIAL_SUFFIX):
        row = properties.find_material_settings(
            settings, material_name[:-len(BAKED_MATERIAL_SUFFIX)])
    return row.atlas_group if row is not None else 1


def collect_groups(context, settings):
    """(groups, warnings) for the current selection.

    A group needs at least two baked materials to be worth atlasing. A mesh
    can't join two groups at once, so if its materials span more than one
    group, only the first is used and the rest get a warning.
    """
    warnings = []

    entries_by_group = {}
    seen = set()
    for obj in plan_mod.selected_meshes(context):
        for material in obj.data.materials:
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            images = pass_images(material)
            if not images:
                continue  # not a baked material
            group_id = _atlas_group_of(settings, material.name)
            if group_id <= 0:
                continue  # group 0 opts out
            width = max(image.size[0] for image in images.values())
            height = max(image.size[1] for image in images.values())
            if width == 0 or height == 0:
                warnings.append(
                    f"Skipped '{material.name}': its baked image has no data")
                continue
            entries_by_group.setdefault(group_id, []).append(AtlasEntry(
                material=material, images=images, size=(width, height)))

    groups = []
    claimed = {}  # mesh name -> group id
    for group_id in sorted(entries_by_group):
        entries = entries_by_group[group_id]
        if len(entries) < 2:
            continue  # a single material has nothing to combine with
        names = {entry.material.name for entry in entries}
        meshes = [
            obj for obj in plan_mod.selected_meshes(context)
            if any(mat is not None and mat.name in names
                   for mat in obj.data.materials)
        ]
        conflicts = [obj.name for obj in meshes if obj.name in claimed]
        if conflicts:
            warnings.append(
                f"Skipped atlas group {group_id}: {', '.join(conflicts)} also "
                f"use(s) group {claimed[conflicts[0]]} materials; a mesh can "
                "only join one atlas")
            continue
        for obj in meshes:
            claimed[obj.name] = group_id
        groups.append(AtlasGroup(group_id=group_id, entries=entries, meshes=meshes))

    return groups, warnings


def preview(context, settings):
    """[(group_id, material_count, sheet_width, sheet_height), ...] for
    what Atlas & Join would produce right now. Cheap enough for the UI to
    call on every redraw."""
    groups, _ = collect_groups(context, settings)
    summaries = []
    for group in groups:
        width, height, _offsets = pack_rects(
            [entry.size for entry in group.entries])
        summaries.append((group.group_id, len(group.entries), width, height))
    return summaries


def button_label(summaries):
    """Dynamic label for the Atlas & Join button, from :func:`preview` data."""
    if not summaries:
        return "Atlas & Join (nothing to combine)"
    materials = sum(count for _, count, _, _ in summaries)
    plural = "atlas" if len(summaries) == 1 else "atlases"
    return f"Atlas & Join ({materials} materials -> {len(summaries)} {plural})"


def build_atlas(context, group):
    """Atlas one group's images, remap UVs, swap materials, and join the
    meshes. Returns the joined object."""
    sheet_width, sheet_height, offsets = pack_rects(
        [entry.size for entry in group.entries])
    base_name = group.meshes[0].name

    os.makedirs(bpy.path.abspath(f"//{BAKE_OUTPUT_DIR}"), exist_ok=True)
    atlas_images = _build_atlas_images(
        group, sheet_width, sheet_height, offsets, base_name)

    # Affine UV transform per source material: uv' = uv * scale + offset.
    transforms = {}
    for entry, (x, y) in zip(group.entries, offsets):
        transforms[entry.material.name] = (
            entry.size[0] / sheet_width, entry.size[1] / sheet_height,
            x / sheet_width, y / sheet_height,
        )

    material = _build_atlas_material(
        f"{ATLAS_PREFIX}{base_name}", atlas_images, group.entries[0].material)

    for obj in group.meshes:
        _remap_uvs(obj, transforms)
        mesh = obj.data
        for index, slot_material in enumerate(mesh.materials):
            if slot_material is not None and slot_material.name in transforms:
                mesh.materials[index] = material
        if len(group.meshes) > 1:
            _unify_bake_layer_name(obj)

    joined = _join_meshes(context, group.meshes)

    for image in atlas_images.values():
        image.save()
    logger.info(
        "Atlased %d materials into '%s' (%dx%d) on '%s'",
        len(group.entries), material.name, sheet_width, sheet_height,
        joined.name)
    return joined


def _read_pixels(image):
    """Image pixels as an (H, W, 4) float32 array (rows bottom-up)."""
    width, height = image.size
    buffer = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(buffer)
    return buffer.reshape(height, width, 4)


def _build_atlas_images(group, sheet_width, sheet_height, offsets, base_name):
    """One atlas image per pass; materials missing a pass get its background
    color instead of a tile."""
    atlas_images = {}
    for spec in PASSES:
        if not any(spec.id in entry.images for entry in group.entries):
            continue
        image = engine.create_bake_image(
            f"{ATLAS_PREFIX}{spec.id}_{base_name}.png",
            (sheet_width, sheet_height), spec)
        sheet = np.empty((sheet_height, sheet_width, 4), dtype=np.float32)
        sheet[:, :] = spec.background_color
        for entry, (x, y) in zip(group.entries, offsets):
            source = entry.images.get(spec.id)
            if source is None or not source.has_data:
                continue
            width, height = entry.size
            tile = resize_bilinear(_read_pixels(source), width, height)
            sheet[y:y + height, x:x + width] = tile
        image.pixels.foreach_set(sheet.reshape(-1))
        image.update()
        atlas_images[spec.id] = image
    return atlas_images


def _build_atlas_material(name, atlas_images, template):
    """Single Principled material wired to the atlas images."""
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)  # reused on re-runs
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output_node = tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (320, 0)

    image_nodes = {}
    for pass_id, image in atlas_images.items():
        node = tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.label = f"Atlas {PASS_MAP[pass_id].label}"
        image_nodes[pass_id] = node

    specs = [PASS_MAP[pass_id] for pass_id in atlas_images]
    bsdf = engine.wire_baked_nodes(tree, output_node, image_nodes, specs)
    bsdf.label = name
    engine.copy_display_settings(template, material)
    return material


def _bake_uv_layer(mesh):
    # engine.py sets the baked layer render-active
    for layer in mesh.uv_layers:
        if layer.active_render:
            return layer
    return mesh.uv_layers.active


def _unify_bake_layer_name(obj):
    """Rename the bake layer to the shared atlas name before joining, since
    Blender's join merges UV layers by name."""
    mesh = obj.data
    layer = _bake_uv_layer(mesh)
    if layer is None or layer.name == ATLAS_UV_LAYER:
        return
    stale = mesh.uv_layers.get(ATLAS_UV_LAYER)
    if stale is not None:
        # old layer from a previous run, replace it
        mesh.uv_layers.remove(stale)
        layer = _bake_uv_layer(mesh)
        if layer is None:
            return
    layer.name = ATLAS_UV_LAYER
    mesh.uv_layers.active = layer
    layer.active_render = True


def _remap_uvs(obj, transforms):
    """Scale/offset the bake UVs of polygons using an atlased material."""
    mesh = obj.data
    layer = _bake_uv_layer(mesh)
    if layer is None or not mesh.materials:
        return

    slot_count = len(mesh.materials)
    scale = np.ones((slot_count, 2), dtype=np.float32)
    offset = np.zeros((slot_count, 2), dtype=np.float32)
    any_slot_mapped = False
    for index, material in enumerate(mesh.materials):
        transform = transforms.get(material.name) if material else None
        if transform is not None:
            scale[index] = transform[:2]
            offset[index] = transform[2:]
            any_slot_mapped = True
    if not any_slot_mapped:
        return

    poly_count = len(mesh.polygons)
    material_indices = np.empty(poly_count, dtype=np.int32)
    loop_totals = np.empty(poly_count, dtype=np.int32)
    mesh.polygons.foreach_get('material_index', material_indices)
    mesh.polygons.foreach_get('loop_total', loop_totals)
    np.clip(material_indices, 0, slot_count - 1, out=material_indices)
    # Loops are stored per polygon in order, so per-loop slot = repeat.
    loop_slots = np.repeat(material_indices, loop_totals)

    uvs = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    layer.data.foreach_get('uv', uvs)
    uvs = uvs.reshape(-1, 2) * scale[loop_slots] + offset[loop_slots]
    layer.data.foreach_set('uv', uvs.reshape(-1))
    mesh.update()


def _join_meshes(context, meshes):
    """Join into the first mesh."""
    target = meshes[0]
    if len(meshes) == 1:
        return target
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in meshes:
        obj.select_set(True)
    context.view_layer.objects.active = target
    if 'FINISHED' not in bpy.ops.object.join():
        raise RuntimeError(f"Blender's Join failed for '{target.name}'")
    return target
