import bpy
import mathutils
import logging

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass


def safe_deselect_all_objects(context: bpy.types.Context):
    try:
        for ob in context.view_layer.objects:
            try:
                ob.select_set(False)
            except Exception:
                pass
    except Exception:
        # Fallback: try currently selected objects
        for ob in list(getattr(context, 'selected_objects', [])):
            try:
                ob.select_set(False)
            except Exception:
                pass


def ensure_object_mode(context: bpy.types.Context, mode: str = 'OBJECT'):
    """Ensure the active object is in the specified mode (default: OBJECT).
    This wraps the common pattern of checking and calling the operator.
    """
    try:
        obj = context.object
        if obj and obj.mode != mode:
            bpy.ops.object.mode_set(mode=mode)
    except Exception:
        # Best-effort; if it fails, don't raise
        pass


def get_selected_meshes(context: bpy.types.Context, edit_mode_as_active: bool = False):
    """Return a list of selected mesh objects. If edit_mode_as_active is True and
    the active object is in EDIT mode, return only the active mesh (common UI case).
    """
    try:
        if edit_mode_as_active and context.object and context.object.mode == 'EDIT' and context.object.type == 'MESH':
            return [context.object]
    except Exception:
        pass
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def vertex_group_has_weights(mesh_obj, vertex_group):
    """Return True if the specified vertex_group has any vertex with weight > 0.
    Shared between multiple operators to avoid duplicated implementations.
    """
    mesh = mesh_obj.data
    group_index = vertex_group.index
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == group_index and g.weight > 0.0:
                return True
    return False


def cleanup_imported_objects(imported_objects):
    """Safely remove imported objects and their data-blocks. Non-fatal on errors."""
    for obj in imported_objects:
        try:
            if obj.type == 'MESH' and obj.data:
                bpy.data.meshes.remove(obj.data, do_unlink=True)
            elif obj.type == 'ARMATURE' and obj.data:
                bpy.data.armatures.remove(obj.data, do_unlink=True)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass


def toBlenderColor(
    color_values: list[float], include_alpha: bool = True
) -> tuple[float, float, float, float] | tuple[float, float, float]:
    """Converts a color in linear rec.709 to the format expected by Blender, in the working color space.

    Args:
        color_values (list[float]): List of values making up the rec.709 color. Four values -> RGBA. Will get padded or trimmed if it's too short/long.
        include_alpha (bool, optional): Whether or not the output tuple should include the fourth value Alpha. Useful when assigning the color to things like lights. Defaults to True.

    Returns:
        tuple[float, float, float, float]: A tuple consisting of R, G, B and A, converted to scene linear colors. Ready to feed to a Color Ramp or similar. A can be disabled with include_alpha=False.
    """
    # It's possible we don't get a list, but an IDPropertyArray or something which does not have .pop(), but it can be converted to a list easily.
    if not hasattr(color_values, 'pop') and hasattr(color_values, 'to_list'):
        color_values = color_values.to_list()
    else:
        try:
            list(color_values)
        except Exception:
            logger.error(
                f"The function toBlenderColor got some object that it either isn't a list or it can't convert to a list: {color_values}. Returning a bright pink so it hopefully gets spotted and reported."
            )
            if include_alpha:
                return (1.0, 0.0, 1.0, 1.0)
            else:
                return (1.0, 0.0, 1.0)

    num_values = len(color_values)
    alpha = 1.0

    if num_values > 4:
        logger.warning(
            f"The function toBlenderColor was given a list of values longer than 4. Anything past that point will be trimmed away. Given list: {color_values}"
        )
        color_values = color_values[:4]

    if num_values == 4:
        # There's an alpha value which needs to be separated before colorspace conversion
        alpha = color_values.pop()

    while (
        len(color_values) < 3
    ):  # Unsure in which cases this would be needed, but just to be safe, make sure there are three color values
        color_values.append(1.0)

    rec709_colors = mathutils.Color(color_values)
    working_space_colors = rec709_colors.from_rec709_linear_to_scene_linear()

    if include_alpha:
        return (working_space_colors.r, working_space_colors.g, working_space_colors.b, alpha)
    else:
        return (working_space_colors.r, working_space_colors.g, working_space_colors.b)
