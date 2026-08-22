import logging

import bpy
from bpy.types import Operator

from . import atlas, engine, plan as plan_mod, preflight, properties, uvprep
from .constants import PACKED_UV_LAYER, UV_SIZE_SCALE_PROP

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _redraw_view3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class MEDDLE_OT_bake2_run(Operator):
    """Bake the enabled channels for all materials on the selected objects"""

    bl_idname = "meddle.bake2_run"
    bl_label = "Bake"
    bl_description = (
        "Bake the enabled channels for every material on the selected objects. "
        "Runs in the background, cancel from the panel or the status bar"
    )
    bl_options = {'REGISTER', 'UNDO'}

    _TIMER_INTERVAL = 0.2

    @classmethod
    def poll(cls, context):
        return (
            engine.active_session() is None
            and bpy.data.is_saved
            and plan_mod.has_bakeable_selection(context)
        )

    def _begin_session(self, context):
        bake_plan, error = plan_mod.build_plan(context)
        if error:
            self.report({'ERROR'}, error)
            return None
        for warning in bake_plan.warnings:
            self.report({'WARNING'}, warning)

        settings = properties.get_settings(context)
        session = engine.BakeSession(
            bake_plan, settings.samples, settings.output_mode,
            device=settings.device)
        session.begin(context)
        engine.set_active_session(session)
        return session

    def invoke(self, context, event):
        session = self._begin_session(context)
        if session is None:
            return {'CANCELLED'}

        self._session = session
        self._cleaned_up = False
        self._baking = False
        self._job_done = False
        self._job_cancelled = False
        self._install_handlers()

        wm = context.window_manager
        self._timer = wm.event_timer_add(self._TIMER_INTERVAL, window=context.window)
        wm.modal_handler_add(self)
        _redraw_view3d(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            # Let every other event through so the user can keep working.
            return {'PASS_THROUGH'}

        session = self._session
        try:
            if self._baking:
                if self._job_cancelled:
                    # user cancelled the Cycles job in the status bar
                    return self._finish(context, cancelled=True)
                if not self._job_done:
                    return {'PASS_THROUGH'}  # still baking, check next tick
                self._baking = False
                session.complete_step(context)
                _redraw_view3d(context)

            if session.cancel_requested:
                return self._finish(context, cancelled=True)
            if session.done:
                return self._finish(context, cancelled=False)

            self._job_done = False
            self._job_cancelled = False
            finished_synchronously = session.start_step(context, invoke=True)
            self._baking = True
            if finished_synchronously:
                self._job_done = True
            _redraw_view3d(context)
            return {'PASS_THROUGH'}

        except Exception as exc:
            logger.exception("Bake failed")
            self.report({'ERROR'}, f"Bake failed: {exc}")
            return self._finish(context, cancelled=True, quiet=True)

    def cancel(self, context):
        # Blender tore the modal down externally (window closed, file loaded).
        self._finish(context, cancelled=True, quiet=True)

    def _finish(self, context, cancelled, quiet=False):
        if self._cleaned_up:
            return {'CANCELLED'} if cancelled else {'FINISHED'}
        self._cleaned_up = True

        session = self._session
        try:
            if cancelled:
                session.abort(context)
                if not quiet:
                    self.report(
                        {'WARNING'},
                        f"Bake cancelled, {session.finalized_count}/"
                        f"{len(session.plan.jobs)} material(s) had finished",
                    )
            else:
                self.report(
                    {'INFO'},
                    f"Bake complete: {len(session.plan.jobs)} material(s), "
                    f"{session.total_steps} passes",
                )
        finally:
            session.end(context)
            engine.set_active_session(None)
            self._remove_handlers()
            if getattr(self, '_timer', None) is not None:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            _redraw_view3d(context)

        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def _install_handlers(self):
        def on_complete(*_args):
            self._job_done = True

        def on_cancel(*_args):
            self._job_cancelled = True

        self._on_complete = on_complete
        self._on_cancel = on_cancel
        bpy.app.handlers.object_bake_complete.append(on_complete)
        bpy.app.handlers.object_bake_cancel.append(on_cancel)

    def _remove_handlers(self):
        for handler_list, func in (
            (bpy.app.handlers.object_bake_complete, getattr(self, '_on_complete', None)),
            (bpy.app.handlers.object_bake_cancel, getattr(self, '_on_cancel', None)),
        ):
            if func is not None and func in handler_list:
                handler_list.remove(func)
        self._on_complete = None
        self._on_cancel = None

    def execute(self, context):
        session = self._begin_session(context)
        if session is None:
            return {'CANCELLED'}
        try:
            while not session.done:
                session.start_step(context, invoke=False)
                session.complete_step(context)
        except Exception as exc:
            logger.exception("Bake failed")
            session.abort(context)
            self.report({'ERROR'}, f"Bake failed: {exc}")
            return {'CANCELLED'}
        finally:
            session.end(context)
            engine.set_active_session(None)

        self.report(
            {'INFO'},
            f"Bake complete: {len(session.plan.jobs)} material(s), "
            f"{session.total_steps} passes",
        )
        return {'FINISHED'}


class MEDDLE_OT_bake2_cancel(Operator):
    """Stop the running bake after the current pass finishes"""

    bl_idname = "meddle.bake2_cancel"
    bl_label = "Cancel Bake"
    bl_description = "Stop the bake after the current pass finishes"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return engine.active_session() is not None

    def execute(self, context):
        session = engine.active_session()
        if session is not None:
            session.cancel_requested = True
            self.report({'INFO'}, "Cancelling after the current pass...")
        return {'FINISHED'}


class MEDDLE_OT_bake2_refresh(Operator):
    """Refresh the material settings and mesh preflight lists"""

    bl_idname = "meddle.bake2_refresh"
    bl_label = "Refresh Lists"
    bl_description = (
        "Rebuild the material settings and mesh lists from the current "
        "selection, and analyze each mesh's UVs for bake problems"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return plan_mod.has_bakeable_selection(context)

    def execute(self, context):
        settings = properties.get_settings(context)
        added, removed = self._sync_materials(context, settings)
        problems = self._rebuild_mesh_info(context, settings)

        message = f"Materials: +{added}/-{removed}"
        if problems:
            message += f" - {problems} mesh(es) with UV problems"
            self.report({'WARNING'}, message)
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}

    @staticmethod
    def _sync_materials(context, settings):
        existing = {row.material_name for row in settings.material_settings}
        added = 0
        for name in plan_mod.selected_materials(context):
            if name not in existing:
                row = settings.material_settings.add()
                row.material_name = name
                added += 1

        removed = 0
        for index in reversed(range(len(settings.material_settings))):
            name = settings.material_settings[index].material_name
            if name not in bpy.data.materials:
                settings.material_settings.remove(index)
                removed += 1

        return added, removed

    @staticmethod
    def _rebuild_mesh_info(context, settings):
        settings.mesh_info.clear()
        problems = 0

        for obj in plan_mod.selected_meshes(context):
            row = settings.mesh_info.add()
            row.mesh_name = obj.name
            row.polygons = len(obj.data.polygons)

            if not any(mat is not None for mat in obj.data.materials):
                row.status = 'PROBLEM'
                row.summary = "No materials, nothing to bake"
                problems += 1
                continue

            uv_layer = plan_mod.choose_uv_layer(obj)
            if uv_layer is None:
                row.status = 'PROBLEM'
                row.summary = "No UV layers, excluded from bake"
                problems += 1
                continue
            row.uv_layer = uv_layer

            report = preflight.safe_analyze_object(obj, uv_layer)
            if report is None:
                row.status = 'WARNING'
                row.summary = "UV analysis failed (see console)"
                continue

            row.islands = len(report.islands)
            row.status, row.summary, row.extra_warning = preflight.summarize(
                report, obj)
            if row.status == 'PROBLEM':
                problems += 1

        return problems


class MEDDLE_OT_bake2_prepare_uvs(Operator):
    """Create the packed bake UV layer for one mesh or the whole selection"""

    bl_idname = "meddle.bake2_prepare_uvs"
    bl_label = "Create Bake UV Layer"
    bl_description = (
        f"(Re)create the '{PACKED_UV_LAYER}' layer so every island fits 0-1. "
        "Repack rearranges islands without overlaps; Keep Layout preserves "
        "the authored arrangement and compensates by baking to a larger "
        "image. From a list row this targets that mesh; from the header, "
        "every selected mesh missing the layer"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mesh_name: bpy.props.StringProperty(
        name="Mesh",
        description="Mesh to prepare; empty prepares every selected mesh "
                    "missing the packed layer",
        default="",
        options={'SKIP_SAVE'},
    )

    method: bpy.props.EnumProperty(
        name="Method",
        description="How islands outside 0-1 are brought into the bake tile",
        items=[
            ('PACK', "Repack Islands",
             "Normalize islands into 0-1 and repack them without overlaps "
             "(arrangement changes; resolution kept)"),
            ('PRESERVE', "Keep Layout",
             "Scale the whole layout uniformly into 0-1, keeping the "
             "authored arrangement; the bake image is enlarged to match "
             "(rounded up to a power of two) so texel density is kept"),
        ],
        default='PACK',
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        return engine.active_session() is None and plan_mod.has_bakeable_selection(context)

    def execute(self, context):
        targets = self._resolve_targets(context)
        if isinstance(targets, str):
            self.report({'ERROR'}, targets)
            return {'CANCELLED'}

        succeeded = 0
        failed = 0
        prepared = []
        for obj in targets:
            ok, message = uvprep.create_bake_uv_layer(
                context, obj, method=self.method)
            if ok:
                succeeded += 1
                prepared.append(obj)
                logger.info(message)
            else:
                failed += 1
                self.report({'WARNING'}, message)

        settings = properties.get_settings(context)
        if self.method == 'PRESERVE':
            for change in self._sync_material_sizes(settings, prepared):
                self.report({'INFO'}, change)

        # Keep the panel's preflight rows in sync with the new layers.
        MEDDLE_OT_bake2_refresh._rebuild_mesh_info(context, settings)

        if failed:
            self.report({'WARNING'},
                        f"Created bake UVs for {succeeded} mesh(es), {failed} with issues")
            return {'FINISHED'} if succeeded else {'CANCELLED'}
        self.report({'INFO'}, f"Created bake UVs for {succeeded} mesh(es)")
        return {'FINISHED'}

    @staticmethod
    def _sync_material_sizes(settings, prepared):
        """Write the layout-preserve bake size into each prepared material's
        size dropdown."""
        multipliers = {}  # material -> largest multiplier across the run
        for obj in prepared:
            multiplier = float(obj.data.get(UV_SIZE_SCALE_PROP, 1.0))
            if multiplier <= 1.0:
                continue
            for mat in obj.data.materials:
                if mat is not None:
                    multipliers[mat] = max(multipliers.get(mat, 1.0), multiplier)

        changes = []
        for mat, multiplier in multipliers.items():
            (width, _height), capped = plan_mod.apply_size_multiplier(
                plan_mod.largest_source_size(mat), multiplier)
            choice = properties.nearest_size_choice(width)
            row = properties.find_material_settings(settings, mat.name)
            if row is None:
                row = settings.material_settings.add()
                row.material_name = mat.name
            if row.size != choice:
                row.size = choice
                note = ", capped, reduced texel density" if capped else ""
                changes.append(
                    f"'{mat.name}': bake size set to {choice} "
                    f"(layout kept at x{multiplier:.1f}{note})")
        return changes

    def _resolve_targets(self, context):
        """List of mesh objects to prepare, or an error string."""
        if self.mesh_name:
            obj = context.scene.objects.get(self.mesh_name)
            if obj is None or obj.type != 'MESH':
                return f"Mesh '{self.mesh_name}' not found in the scene"
            return [obj]

        targets = [
            obj for obj in plan_mod.selected_meshes(context)
            if PACKED_UV_LAYER not in obj.data.uv_layers and obj.data.uv_layers
        ]
        if not targets:
            return f"All selected meshes already have '{PACKED_UV_LAYER}'"
        return targets


class MEDDLE_OT_bake2_select_mesh(Operator):
    """Select a mesh from the material list in the viewport"""

    bl_idname = "meddle.bake2_select_mesh"
    bl_label = "Select Mesh"
    bl_description = "Select this mesh in the viewport and make it active"
    bl_options = {'REGISTER', 'UNDO'}

    mesh_name: bpy.props.StringProperty(
        name="Mesh",
        description="Mesh to select",
        default="",
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        obj = context.scene.objects.get(self.mesh_name)
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, f"Mesh '{self.mesh_name}' not found in the scene")
            return {'CANCELLED'}
        try:
            for other in context.selected_objects:
                other.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except RuntimeError as exc:
            # Hidden/unselectable object, leave the selection alone.
            self.report({'WARNING'}, f"Could not select '{obj.name}': {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


class MEDDLE_OT_bake2_join_meshes(Operator):
    """Join the selected meshes that use a material into one object"""

    bl_idname = "meddle.bake2_join_meshes"
    bl_label = "Join Meshes"
    bl_description = (
        "Join the listed meshes into a single object (Blender's Join, undoable). "
        "One mesh per material lets the packed bake UV layer lay the whole "
        "material out together"
    )
    bl_options = {'REGISTER', 'UNDO'}

    material_name: bpy.props.StringProperty(
        name="Material",
        description="Material whose meshes are joined",
        default="",
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        return (
            engine.active_session() is None
            and context.mode == 'OBJECT'
            and plan_mod.has_bakeable_selection(context)
        )

    def execute(self, context):
        material = bpy.data.materials.get(self.material_name)
        if material is None:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}

        meshes = [
            obj for obj in plan_mod.selected_meshes(context)
            if any(mat is material for mat in obj.data.materials)
        ]
        if len(meshes) < 2:
            self.report({'ERROR'}, "Fewer than two selected meshes use this material")
            return {'CANCELLED'}

        target = meshes[0]
        absorbed = {obj.name for obj in meshes[1:]}
        previous_selection = [
            obj.name for obj in context.selected_objects
            if obj.name not in absorbed
        ]
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in meshes:
                obj.select_set(True)
            context.view_layer.objects.active = target
        except RuntimeError as exc:
            self.report({'ERROR'}, f"Could not select the meshes to join: {exc}")
            return {'CANCELLED'}

        if 'FINISHED' not in bpy.ops.object.join():
            self.report({'ERROR'}, "Blender's Join operator failed")
            return {'CANCELLED'}

        # Join collapsed the selection to the target; restore the rest.
        for name in previous_selection:
            obj = context.scene.objects.get(name)
            if obj is not None:
                try:
                    obj.select_set(True)
                except RuntimeError:
                    pass

        MEDDLE_OT_bake2_refresh._rebuild_mesh_info(
            context, properties.get_settings(context))
        self.report(
            {'INFO'},
            f"Joined {len(meshes)} meshes into '{target.name}' "
            f"for material '{material.name}'",
        )
        return {'FINISHED'}


class MEDDLE_OT_bake2_atlas(Operator):
    """Combine baked materials into texture atlases and join their meshes"""

    bl_idname = "meddle.bake2_atlas"
    bl_label = "Atlas & Join"
    bl_description = (
        "Pack the baked images of materials sharing an atlas group into one "
        "texture per channel, remap UVs, and join each group's meshes into a "
        "single object with a single material. Bake first, only baked "
        "materials are combined; group 0 opts a material out"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            engine.active_session() is None
            and context.mode == 'OBJECT'
            and bpy.data.is_saved
            and plan_mod.has_bakeable_selection(context)
        )

    def execute(self, context):
        settings = properties.get_settings(context)
        groups, warnings = atlas.collect_groups(context, settings)
        for warning in warnings:
            self.report({'WARNING'}, warning)
        if not groups:
            self.report(
                {'ERROR'},
                "Nothing to combine, bake the materials first, then atlas",
            )
            return {'CANCELLED'}

        joined = []
        try:
            for group in groups:
                joined.append(atlas.build_atlas(context, group))
        except Exception as exc:
            logger.exception("Atlas failed")
            self.report({'ERROR'}, f"Atlas failed: {exc} (undo to revert)")
            return {'CANCELLED'}

        MEDDLE_OT_bake2_refresh._rebuild_mesh_info(context, settings)
        names = ", ".join(obj.name for obj in joined)
        self.report({'INFO'}, f"Created {len(joined)} atlas object(s): {names}")
        return {'FINISHED'}


class MEDDLE_OT_bake2_clear_materials(Operator):
    """Remove all per-material settings rows"""

    bl_idname = "meddle.bake2_clear_materials"
    bl_label = "Clear Materials"
    bl_description = "Remove all per-material bake settings"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(properties.get_settings(context).material_settings) > 0

    def execute(self, context):
        settings = properties.get_settings(context)
        count = len(settings.material_settings)
        settings.material_settings.clear()
        self.report({'INFO'}, f"Removed {count} material row(s)")
        return {'FINISHED'}
