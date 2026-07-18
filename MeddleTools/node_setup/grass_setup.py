# Meddle exports .ggd grass blades as point-cloud meshes named
# 'GrassBlades_<zone grass dir>_<tier>' (one per h/m/l streaming tier), with
# instance data in custom attributes (_ROTATION/_SCALE/_INFO/_BEND/COLOR_0)
# and the zone's texture atlas in the object's 'GrassTextures' extra.
#
# This realizes those points into geometry via the
# 'meddle grass_blades_geometry' node group, with a per-zone copy of
# 'meddle grass_blades shader' carrying the atlas. Node group inputs are set
# only if the group actually exposes that socket, so older/customized groups
# still import fine.

import logging
from os import path

import bpy

from .. import blend_import, version

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

GEOMETRY_GROUP_RESOURCE = 'grass_blades_geometry'
SHADER_RESOURCE = 'grass_blades shader'
MODIFIER_NAME = 'MeddleGrassBlades'
TEMPLATE_COLLECTION = 'MeddleGrassTemplates'
RANGE_ORIGIN_NAME = 'GrassRangeOrigin'
GRASS_TEXTURE_NODE_LABEL = 'GrassTexture'

# matches the game client's per-tier streaming radii (yalms)
TIER_RINGS = {
    'h': (0.0, 64.0),
    'm': (64.0, 128.0),
    'l': (128.0, 384.0),
}


def is_grass_blade_object(obj: bpy.types.Object) -> bool:
    return obj is not None and obj.type == 'MESH' and obj.get('GrassBladeTier') is not None


def setup_grass_blades(obj: bpy.types.Object, cache_dir: str, context: bpy.types.Context):
    """Attach the grass geometry node modifier and per-zone material to one tier object."""
    group_name = blend_import.get_resource_name(GEOMETRY_GROUP_RESOURCE)
    group = bpy.data.node_groups.get(group_name)
    if group is None:
        logger.warning("Grass geometry node group %s not found, skipping %s", group_name, obj.name)
        return

    _link_template_objects(group, context)

    atlas_path = _resolve_atlas_path(obj, cache_dir)
    zone = _zone_key(obj, atlas_path)
    material = _get_zone_material(obj, zone, atlas_path)
    if material is not None and obj.material_slots:
        obj.material_slots[0].material = material

    sockets = {
        item.name: item.identifier
        for item in group.interface.items_tree
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT'
    }

    # no Material socket to override per-modifier, so swap it in a per-zone
    # copy of the group instead
    if material is not None and 'Material' not in sockets:
        group = _get_zone_group(group, material, zone)

    modifier = obj.modifiers.get(MODIFIER_NAME)
    if modifier is None:
        modifier = obj.modifiers.new(MODIFIER_NAME, 'NODES')
    modifier.node_group = group

    tier = str(obj.get('GrassBladeTier', 'h'))
    min_distance, max_distance = TIER_RINGS.get(tier, TIER_RINGS['h'])

    inputs = {
        'Range Origin': _get_range_origin(context),
        'Min Distance': min_distance,
        'Max Distance': max_distance,
        'Jitter Strength': 1.0,
        'Material': material,
    }
    for name, value in inputs.items():
        if value is None or name not in sockets:
            continue
        try:
            _set_modifier_input(modifier, sockets[name], value)
        except Exception as e:
            logger.warning("Could not set grass input '%s' on %s: %s", name, obj.name, e)

    logger.info("Set up grass blades for %s (tier %s, ring %s-%s)", obj.name, tier, min_distance, max_distance)


def _get_zone_group(base_group: bpy.types.GeometryNodeTree, material: bpy.types.Material, zone: str):
    """Per-zone copy of the geometry group with Set Material pointed at the
    zone material. Only needed when the group has no 'Material' input."""
    name = f'{base_group.name} {zone}'
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing

    group = base_group.copy()
    group.name = name
    swapped = False
    for node in group.nodes:
        if node.bl_idname != 'GeometryNodeSetMaterial':
            continue
        socket = node.inputs['Material']
        if not socket.is_linked:
            socket.default_value = material
            swapped = True
    if not swapped:
        logger.warning("Zone group %s has no Set Material node to swap; blades keep the template material", name)
    return group


def _set_modifier_input(modifier: bpy.types.NodesModifier, identifier: str, value):
    """Set a geometry nodes modifier input across Blender versions: 5.x uses
    typed wrappers on modifier.properties.inputs, 4.x uses ID properties
    directly on the modifier."""
    properties = getattr(modifier, 'properties', None)
    inputs = getattr(properties, 'inputs', None) if properties is not None else None
    if inputs is not None:
        socket = getattr(inputs, identifier, None)
        if socket is not None:
            socket.value = value
            return
    modifier[identifier] = value


def _link_template_objects(group: bpy.types.GeometryNodeTree, context: bpy.types.Context):
    """Link the blade template objects referenced by the group into the view
    layer. Object Info nodes only evaluate linked objects, but the templates
    arrive from shaders.blend unlinked."""
    templates = []
    for node in group.nodes:
        if node.bl_idname != 'GeometryNodeObjectInfo':
            continue
        target = node.inputs['Object'].default_value
        if target is not None and not target.users_collection:
            templates.append(target)
    if not templates:
        return

    collection = bpy.data.collections.get(TEMPLATE_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(TEMPLATE_COLLECTION)
        collection.hide_render = True
    if collection.name not in context.scene.collection.children:
        context.scene.collection.children.link(collection)

    for template in templates:
        collection.objects.link(template)
        template.hide_render = True

    layer_collection = _find_layer_collection(context.view_layer.layer_collection, collection.name)
    if layer_collection is not None:
        layer_collection.hide_viewport = True


def _find_layer_collection(layer_collection, name):
    if layer_collection.name == name:
        return layer_collection
    for child in layer_collection.children:
        found = _find_layer_collection(child, name)
        if found is not None:
            return found
    return None


def _get_range_origin(context: bpy.types.Context) -> bpy.types.Object:
    """Get or create the empty the grass streams around; shared by all tiers/zones."""
    origin = bpy.data.objects.get(RANGE_ORIGIN_NAME)
    if origin is None:
        origin = bpy.data.objects.new(RANGE_ORIGIN_NAME, None)
        origin.empty_display_type = 'PLAIN_AXES'
        origin.empty_display_size = 5.0
    if not origin.users_collection:
        context.scene.collection.objects.link(origin)
    return origin


def _get_zone_material(obj: bpy.types.Object, zone: str, atlas_path):
    """Copy the grass shader for this zone and load its texture atlas into
    it. One copy is shared by the zone's h/m/l tier objects."""
    template_name = blend_import.get_resource_name(SHADER_RESOURCE)
    template = bpy.data.materials.get(template_name)
    if template is None:
        logger.warning("Grass shader material %s not found for %s", template_name, obj.name)
        return None

    material_name = f'Meddle {version.current_version} grass_blades {zone}'
    existing = bpy.data.materials.get(material_name)
    if existing is not None:
        return existing

    material = template.copy()
    material.name = material_name

    if atlas_path is None:
        logger.warning("No cached grass atlas found for %s; material left without texture", obj.name)
        return material

    try:
        image = bpy.data.images.load(atlas_path, check_existing=True)
    except Exception as e:
        logger.warning("Could not load grass atlas %s: %s", atlas_path, e)
        return material

    texture_nodes = [n for n in material.node_tree.nodes if n.type == 'TEX_IMAGE'] if material.use_nodes else []
    labeled = [n for n in texture_nodes if n.label == GRASS_TEXTURE_NODE_LABEL]
    for node in labeled or texture_nodes[:1]:
        node.image = image
    if not texture_nodes:
        logger.warning("Grass shader %s has no image texture node to receive the atlas", template_name)

    return material


def _resolve_atlas_path(obj: bpy.types.Object, cache_dir: str):
    """First existing cached texture from the object's 'GrassTextures' extra."""
    textures = obj.get('GrassTextures')
    if textures is None:
        return None
    for entry in textures:
        try:
            cache_path = entry.get('CachePath')
        except AttributeError:
            continue
        if not cache_path:
            continue
        full_path = path.join(cache_dir, bpy.path.native_pathsep(cache_path))
        if path.exists(full_path):
            return full_path
    return None


def _zone_key(obj: bpy.types.Object, atlas_path):
    # cache paths look like bg/ex3/01_nvt_n4/fld/n4f4/grass/_grass1.tex.png; the
    # folder above 'grass' is the zone id
    if atlas_path is not None:
        parts = path.normpath(atlas_path).split(path.sep)
        if len(parts) >= 3:
            return parts[-3]
    name = obj.name
    if name.startswith('GrassBlades_'):
        name = name[len('GrassBlades_'):]
    return name
