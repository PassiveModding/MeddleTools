import logging
import os

import bpy
from bpy.types import Operator

from . import engine, plan as plan_mod

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

TEXTURE_SUBFOLDER = "textures"


def _export_objects(context):
    """Meshes to export (incl. armature children) plus selected armatures."""
    objects = list(plan_mod.selected_meshes(context))
    objects += [
        obj for obj in context.selected_objects
        if obj.type == 'ARMATURE' and obj not in objects
    ]
    return objects


def _fbx_filename(objects):
    """'<armature or first object>.fbx', sanitized for the filesystem."""
    armature = next((obj for obj in objects if obj.type == 'ARMATURE'), None)
    base = (armature or objects[0]).name
    base = "".join(c for c in base if c.isalnum() or c in " _-").strip()
    return f"{base or 'export'}.fbx"


def _save_texture_copies(mesh_objects, folder):
    """Save every image used by the meshes' materials as PNG into ``folder``,
    without changing what the .blend points at."""
    os.makedirs(folder, exist_ok=True)
    seen = set()
    saved = failed = 0
    for obj in mesh_objects:
        for material in obj.data.materials:
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type != 'TEX_IMAGE' or node.image is None:
                    continue
                image = node.image
                if image.name in seen:
                    continue
                seen.add(image.name)
                try:
                    _save_png(image, folder)
                    saved += 1
                except Exception:
                    logger.exception("Could not save texture %s", image.name)
                    failed += 1
    return saved, failed


def _save_png(image, folder):
    base = os.path.basename(image.filepath) or f"{image.name}.png"
    path = os.path.join(folder, os.path.splitext(base)[0] + ".png")

    original_path = image.filepath_raw
    original_format = image.file_format
    try:
        image.filepath_raw = path
        image.file_format = 'PNG'
        image.save()
    finally:
        image.filepath_raw = original_path
        image.file_format = original_format


def _export_fbx(context, objects, fbx_path):
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    armature = next((obj for obj in objects if obj.type == 'ARMATURE'), None)
    context.view_layer.objects.active = armature or objects[0]

    # Only non-default settings are spelled out.
    bpy.ops.export_scene.fbx(
        filepath=fbx_path,
        use_selection=True,
        object_types={'ARMATURE', 'MESH'},
        mesh_smooth_type='FACE',
        use_tspace=True,          # export tangents for the baked normal maps
        add_leaf_bones=False,
        bake_anim=False,
        path_mode='COPY',
        embed_textures=True,
    )


class MEDDLE_OT_bake2_export_fbx(Operator):
    """Export the selection to FBX with textures"""

    bl_idname = "meddle.bake2_export_fbx"
    bl_label = "Export FBX"
    bl_description = (
        "Export the selected meshes (and armatures) to an FBX with embedded "
        "textures, plus PNG copies in a 'textures' subfolder"
    )
    bl_options = {'REGISTER'}

    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Folder the FBX and its textures subfolder are written to",
        subtype='DIR_PATH',
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        return (
            engine.active_session() is None
            and plan_mod.has_bakeable_selection(context)
        )

    def invoke(self, context, event):
        self.directory = (
            os.path.dirname(bpy.data.filepath)
            if bpy.data.filepath else os.path.expanduser("~")
        )
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "No export directory selected")
            return {'CANCELLED'}

        objects = _export_objects(context)
        meshes = [obj for obj in objects if obj.type == 'MESH']
        if not meshes:
            self.report({'ERROR'}, "No meshes to export")
            return {'CANCELLED'}

        try:
            saved, failed = _save_texture_copies(
                meshes, os.path.join(self.directory, TEXTURE_SUBFOLDER))
            fbx_path = os.path.join(self.directory, _fbx_filename(objects))
            _export_fbx(context, objects, fbx_path)
        except Exception as exc:
            logger.exception("FBX export failed")
            self.report({'ERROR'}, f"Export failed: {exc}")
            return {'CANCELLED'}

        if failed:
            self.report(
                {'WARNING'},
                f"Exported {os.path.basename(fbx_path)}; {failed} texture(s) "
                "failed to save (see console)",
            )
        else:
            self.report(
                {'INFO'},
                f"Exported {os.path.basename(fbx_path)} with {saved} texture(s)",
            )
        return {'FINISHED'}
