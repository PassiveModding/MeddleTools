import bpy

from . import atlas, engine, plan as plan_mod, properties
from .export import MEDDLE_OT_bake2_export_fbx
from .operators import (
    MEDDLE_OT_bake2_atlas,
    MEDDLE_OT_bake2_cancel,
    MEDDLE_OT_bake2_clear_materials,
    MEDDLE_OT_bake2_join_meshes,
    MEDDLE_OT_bake2_prepare_uvs,
    MEDDLE_OT_bake2_refresh,
    MEDDLE_OT_bake2_run,
    MEDDLE_OT_bake2_select_mesh,
)
from .passes import PASSES

_STATUS_ICONS = {
    'OK': 'CHECKMARK',
    'WARNING': 'ERROR',       # triangle warning icon
    'PROBLEM': 'CANCEL',
}


def _run_button_label(context):
    count = len(plan_mod.selected_materials(context))
    if count == 0:
        return "Bake (no materials)"
    if count == 1:
        return "Bake 1 Material"
    return f"Bake {count} Materials"


def _draw_mesh_row(box, info, obj):
    """One nested mesh row: status, name, bake UV layer + findings, buttons."""
    row = box.row(align=True)
    row.separator(factor=2.0)
    split = row.split(factor=0.42, align=True)
    if info is None:
        split.label(text=obj.name, icon='QUESTION')
        uv_layer = plan_mod.choose_uv_layer(obj)
        if uv_layer:
            split.label(text=f"{uv_layer} · refresh to analyze")
        else:
            split.label(text="No UV layers")
    else:
        row.alert = info.status == 'PROBLEM'
        split.label(
            text=obj.name,
            icon=_STATUS_ICONS.get(info.status, 'QUESTION'),
        )
        if info.status == 'OK':
            split.label(text=f"{info.uv_layer} · {info.islands} islands")
        elif info.uv_layer:
            split.label(text=f"{info.uv_layer} · {info.summary}")
        else:
            split.label(text=info.summary)

    # extra_warning means recreating the UV layer fixes it; highlight the row
    extra_warning = info.extra_warning if info is not None else ""
    buttons = row.row(align=True)
    buttons.alert = bool(extra_warning)
    op = buttons.operator(
        MEDDLE_OT_bake2_select_mesh.bl_idname, text="",
        icon='RESTRICT_SELECT_OFF', emboss=False)
    op.mesh_name = obj.name
    op = buttons.operator(
        MEDDLE_OT_bake2_prepare_uvs.bl_idname, text="", icon='UV', emboss=False)
    op.mesh_name = obj.name

    if extra_warning:
        warning = box.row(align=True)
        warning.alert = True
        warning.separator(factor=4.0)
        warning.label(text=extra_warning, icon='ERROR')
        # Same as the row's UV icon, just labeled so the fix is obvious.
        fix = warning.row(align=True)
        fix.alert = False
        op = fix.operator(
            MEDDLE_OT_bake2_prepare_uvs.bl_idname, text="Repack", icon='UV')
        op.mesh_name = obj.name
        op = fix.operator(
            MEDDLE_OT_bake2_prepare_uvs.bl_idname, text="Keep Layout",
            icon='MOD_UVPROJECT')
        op.mesh_name = obj.name
        op.method = 'PRESERVE'


class MEDDLE_PT_bake2(bpy.types.Panel):
    bl_idname = "MEDDLE_PT_bake2"
    bl_label = "Bake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meddle Tools"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        session = engine.active_session()
        if session is not None:
            self._draw_running(layout, session)
            return

        settings = properties.get_settings(context)

        if not bpy.data.is_saved:
            row = layout.row()
            row.alert = True
            row.label(text="Save the .blend file before baking", icon='ERROR')

        # Channels
        column = layout.column(align=True)
        column.label(text="Channels", icon='NODE_TEXTURE')
        grid = column.grid_flow(row_major=True, columns=3, align=True)
        for spec in PASSES:
            grid.prop(settings, spec.toggle_attr, toggle=True)

        layout.prop(settings, "samples")
        row = layout.row(align=True)
        row.prop(settings, "device", expand=True)

        # Material output mode
        column = layout.column(align=True)
        column.label(text="Material Output", icon='MATERIAL_DATA')
        row = column.row(align=True)
        row.prop(settings, "output_mode", expand=True)

        # Materials, each with the meshes that use it
        column = layout.column(align=True)
        header = column.row(align=True)
        header.label(text="Materials", icon='MATERIAL')
        header.operator(MEDDLE_OT_bake2_prepare_uvs.bl_idname, text="", icon='UV')
        header.operator(MEDDLE_OT_bake2_refresh.bl_idname, text="", icon='FILE_REFRESH')
        header.operator(MEDDLE_OT_bake2_clear_materials.bl_idname, text="", icon='X')

        if settings.material_settings:
            self._draw_materials(context, column, settings)
        else:
            column.label(text="Refresh to list the selection's materials", icon='INFO')

        problem_count = sum(
            1 for row in settings.mesh_info if row.status == 'PROBLEM')
        if problem_count:
            warning = column.row()
            warning.alert = True
            warning.label(
                text=f"{problem_count} mesh(es) will not bake correctly",
                icon='ERROR',
            )

        run_row = layout.row()
        run_row.scale_y = 1.4
        run_row.operator(
            MEDDLE_OT_bake2_run.bl_idname,
            text=_run_button_label(context),
            icon='RENDER_STILL',
        )

        atlas_preview = atlas.preview(context, settings)
        layout.operator(
            MEDDLE_OT_bake2_atlas.bl_idname,
            text=atlas.button_label(atlas_preview),
            icon='TEXTURE',
        )
        if atlas_preview:
            column = layout.column(align=True)
            for group_id, count, width, height in atlas_preview:
                column.label(
                    text=f"Group {group_id}: {count} materials -> {width} x {height}",
                    icon='TEXTURE',
                )
        layout.operator(
            MEDDLE_OT_bake2_export_fbx.bl_idname,
            text="Export FBX with Textures",
            icon='EXPORT',
        )

    def _draw_materials(self, context, column, settings):
        """One box per material: name + size, nested rows for its meshes."""
        info_by_mesh = {row.mesh_name: row for row in settings.mesh_info}
        meshes = plan_mod.selected_meshes(context)

        rows = sorted(
            settings.material_settings,
            key=lambda row: row.material_name.lower(),
        )
        for item in rows:
            material = bpy.data.materials.get(item.material_name)
            box = column.box()
            header = box.row(align=True)
            header.label(text=item.material_name, icon='MATERIAL')
            header.prop(item, "size", text="")
            group = header.row(align=True)
            group.scale_x = 0.55
            group.prop(item, "atlas_group", text="G")

            if material is None:
                row = box.row()
                row.alert = True
                row.label(text="Material no longer exists, refresh", icon='ERROR')
                continue

            users = [
                obj for obj in meshes
                if any(mat is material for mat in obj.data.materials)
            ]
            if not users:
                box.label(text="Not used by any selected mesh", icon='INFO')
                continue

            for obj in users:
                _draw_mesh_row(box, info_by_mesh.get(obj.name), obj)

            if len(users) > 1:
                row = box.row()
                op = row.operator(
                    MEDDLE_OT_bake2_join_meshes.bl_idname,
                    text=f"Join {len(users)} Meshes",
                    icon='AUTOMERGE_ON',
                )
                op.material_name = item.material_name

    def _draw_running(self, layout, session):
        column = layout.column(align=True)
        column.progress(
            factor=session.progress,
            type='BAR',
            text=session.status_text,
        )
        column.separator(factor=0.5)
        column.operator(MEDDLE_OT_bake2_cancel.bl_idname, icon='CANCEL')
