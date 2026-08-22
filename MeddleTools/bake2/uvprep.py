import logging

import bpy

from . import preflight
from .constants import DEFAULT_UV_LAYER, PACKED_UV_LAYER, UV_SIZE_SCALE_PROP

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_PACK_MARGIN = 0.003

# Blender's hard limit on UV layers per mesh.
_MAX_UV_LAYERS = 8


def pick_source_layer(mesh):
    """The layer to build the bake layer from, or None if the mesh has none."""
    layers = mesh.uv_layers
    if DEFAULT_UV_LAYER in layers:
        return layers[DEFAULT_UV_LAYER]
    for layer in layers:
        if layer.name != PACKED_UV_LAYER and layer.active_render:
            return layer
    for layer in layers:
        if layer.name != PACKED_UV_LAYER:
            return layer
    # Only the packed layer exists; rebuild it from itself.
    return layers.get(PACKED_UV_LAYER)


def create_bake_uv_layer(context, obj, method='PACK'):
    """(Re)create the packed bake UV layer on ``obj``.

    method='PACK' normalizes islands into tile 0 and repacks them (changes
    the arrangement, keeps resolution). method='PRESERVE' fits the whole
    layout into 0-1 with one transform (keeps the arrangement, loses
    resolution - the loss is stored on the mesh so planning can bake a
    bigger image to compensate). Returns (ok, message).
    """
    mesh = obj.data
    source = pick_source_layer(mesh)
    if source is None:
        return False, f"'{obj.name}': no UV layers to build from"

    if (PACKED_UV_LAYER not in mesh.uv_layers
            and len(mesh.uv_layers) >= _MAX_UV_LAYERS):
        return False, f"'{obj.name}': UV layer limit reached ({_MAX_UV_LAYERS})"

    # read before touching layers, source may be the packed layer itself
    arrays = preflight.extract_mesh_arrays(mesh, source.name)
    if arrays is None:
        return False, f"'{obj.name}': could not read UV layer '{source.name}'"
    loop_starts, loop_totals, vertex_indices, uvs = arrays
    source_name = source.name

    multiplier = 1.0
    if method == 'PRESERVE':
        normalized, multiplier = preflight.fit_layout_into_tile(uvs)
    else:
        normalized = preflight.normalize_into_tile(
            loop_starts, loop_totals, vertex_indices, uvs, margin=_PACK_MARGIN)

    existing = mesh.uv_layers.get(PACKED_UV_LAYER)
    if existing is not None and existing.name != source_name:
        mesh.uv_layers.remove(existing)
    if PACKED_UV_LAYER not in mesh.uv_layers:
        mesh.uv_layers.new(name=PACKED_UV_LAYER, do_init=False)

    packed_layer = mesh.uv_layers[PACKED_UV_LAYER]
    packed_layer.data.foreach_set('uv', normalized)

    mesh.uv_layers.active = packed_layer
    # Keep the source as the render layer so material sampling is unaffected.
    source_layer = mesh.uv_layers.get(source_name)
    if source_layer is not None and source_layer.name != PACKED_UV_LAYER:
        source_layer.active_render = True

    # clear a stale multiplier from an earlier run
    if multiplier > 1.0:
        mesh[UV_SIZE_SCALE_PROP] = multiplier
    elif UV_SIZE_SCALE_PROP in mesh:
        del mesh[UV_SIZE_SCALE_PROP]

    if method != 'PRESERVE':
        error = _pack_active_layer(context, obj)
        if error:
            return False, f"'{obj.name}': {error}"

    report = preflight.safe_analyze_object(obj, PACKED_UV_LAYER)
    if report is None:
        return True, f"'{obj.name}': created '{PACKED_UV_LAYER}' (unverified)"
    status, summary, _hint = preflight.summarize(report)
    detail = f"{len(report.islands)} islands"
    if multiplier > 1.0:
        detail += f", layout kept, bake size x{multiplier:.1f}"
    if status == 'OK':
        return True, f"'{obj.name}': created '{PACKED_UV_LAYER}' ({detail})"
    if status == 'WARNING' and method == 'PRESERVE':
        # Stacked islands stay stacked by design when preserving the layout.
        return True, (
            f"'{obj.name}': created '{PACKED_UV_LAYER}' ({detail}; {summary})")
    return False, (
        f"'{obj.name}': created '{PACKED_UV_LAYER}' but issues remain: {summary}")


def _pack_active_layer(context, obj):
    """Run uv.pack_islands on the object's active UV layer. None on success."""
    view_layer = context.view_layer
    previous_selection = list(context.selected_objects)
    previous_active = view_layer.objects.active

    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    view_layer.objects.active = obj

    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        # Islands were already normalized into tile 0, so CLOSEST_UDIM
        # always targets the 0-1 tile.
        bpy.ops.uv.pack_islands(
            udim_source='CLOSEST_UDIM',
            rotate=False,
            scale=True,
            merge_overlap=False,
            margin_method='SCALED',
            margin=_PACK_MARGIN,
            pin=False,
            shape_method='CONCAVE',
        )
        return None
    except Exception as exc:
        logger.exception("pack_islands failed for %s", obj.name)
        return f"packing failed: {exc}"
    finally:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for prev in previous_selection:
            try:
                prev.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        try:
            view_layer.objects.active = previous_active
        except (ReferenceError, RuntimeError):
            pass
