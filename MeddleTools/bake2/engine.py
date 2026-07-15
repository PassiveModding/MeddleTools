import logging
import math
import os

import bpy

from .constants import (
    BAKE_IMAGE_PREFIX,
    BAKE_OUTPUT_DIR,
    BAKED_MATERIAL_SUFFIX,
    OUTPUT_NEW_MATERIAL,
    OUTPUT_REPLACE_MATERIAL,
)
from .passes import REBUILT_BSDF_DEFAULTS, Strategy

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class BakeError(RuntimeError):
    """A bake step could not be started or completed."""


_active_session = None


def active_session():
    return _active_session


def set_active_session(session):
    global _active_session
    _active_session = session


class RenderStateSnapshot:
    """Captures every scene setting the engine touches, for exact restore."""

    # render restores first so the cycles settings below apply correctly
    _TRACKED = (
        ('render', ('engine',)),
        ('render.bake', (
            'use_pass_direct', 'use_pass_indirect', 'use_pass_color',
            'target', 'margin', 'use_clear', 'use_selected_to_active',
            'normal_space',
        )),
        ('cycles', ('bake_type', 'use_denoising', 'samples', 'device')),
    )

    def __init__(self, scene):
        self._values = []
        for path, attrs in self._TRACKED:
            holder = self._resolve(scene, path)
            if holder is None:
                continue
            for attr in attrs:
                if hasattr(holder, attr):
                    self._values.append((holder, attr, getattr(holder, attr)))

    @staticmethod
    def _resolve(scene, path):
        obj = scene
        for part in path.split('.'):
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    def restore(self):
        for holder, attr, value in self._values:
            try:
                setattr(holder, attr, value)
            except Exception:
                logger.warning("Could not restore render setting %s", attr)


class PassRig:
    """Node edits needed while one pass bakes; ``revert()`` always restores."""

    def __init__(self, material):
        self.material = material
        self._created_nodes = []
        self._removed_links = []  # (from_socket, to_socket)

    def build(self, spec, principled, output_node):
        if spec.strategy is Strategy.EMIT_CHANNEL:
            self._build_emit_channel(spec, principled, output_node)

    def _build_emit_channel(self, spec, principled, output_node):
        """Route a BSDF input through an Emission shader so EMIT can bake it."""
        tree = self.material.node_tree

        emit = tree.nodes.new('ShaderNodeEmission')
        emit.label = f"MeddleBake {spec.label}"
        emit.location = (output_node.location.x - 200, output_node.location.y + 200)
        emit.inputs['Strength'].default_value = 1.0
        self._created_nodes.append(emit)

        source = principled.inputs.get(spec.source_socket)
        if source is not None and source.is_linked:
            tree.links.new(source.links[0].from_socket, emit.inputs['Color'])
        else:
            emit.inputs['Color'].default_value = self._as_rgba(source)

        surface = output_node.inputs['Surface']
        for link in list(surface.links):
            self._removed_links.append((link.from_socket, link.to_socket))
            tree.links.remove(link)
        tree.links.new(emit.outputs['Emission'], surface)

    @staticmethod
    def _as_rgba(socket):
        if socket is None:
            return (0.0, 0.0, 0.0, 1.0)
        value = socket.default_value
        if isinstance(value, (int, float)):
            return (value, value, value, 1.0)
        channels = list(value)[:3]
        channels += [0.0] * (3 - len(channels))
        return (*channels, 1.0)

    def revert(self):
        tree = self.material.node_tree
        for node in self._created_nodes:
            try:
                tree.nodes.remove(node)
            except (ReferenceError, RuntimeError):
                logger.warning("Temporary bake node already removed")
        self._created_nodes.clear()
        for from_socket, to_socket in self._removed_links:
            try:
                tree.links.new(from_socket, to_socket)
            except (ReferenceError, RuntimeError):
                logger.warning("Could not restore a material link after baking")
        self._removed_links.clear()


def create_bake_image(name, size, spec):
    """New image for a pass spec; replaces any existing same-name image."""
    existing = bpy.data.images.get(name)
    if existing is not None:
        bpy.data.images.remove(existing)

    image = bpy.data.images.new(
        name=name, width=size[0], height=size[1], alpha=True)
    image.filepath = bpy.path.abspath(f"//{BAKE_OUTPUT_DIR}/{name}")
    image.file_format = 'PNG'
    image.alpha_mode = spec.alpha_mode
    image.generated_color = spec.background_color
    image.colorspace_settings.name = spec.colorspace
    return image


# hasattr-guarded since these differ between Blender versions
# (shadow_method was removed in 4.2)
_DISPLAY_ATTRS = (
    'blend_method', 'shadow_method', 'alpha_threshold',
    'surface_render_method', 'use_transparent_shadow',
    'use_backface_culling',
)


def copy_display_settings(source, dest):
    """Copy how alpha/shadows render in the viewport between materials."""
    for attr in _DISPLAY_ATTRS:
        if hasattr(source, attr) and hasattr(dest, attr):
            try:
                setattr(dest, attr, getattr(source, attr))
            except Exception:
                pass


def wire_baked_nodes(tree, output_node, image_nodes, bake_passes):
    """Create the baked BSDF (+ normal map) and wire the images into it.

    ``image_nodes`` maps pass id -> image texture node already in ``tree``.
    Returns the new Principled BSDF node.
    """
    bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (output_node.location.x - 320, output_node.location.y)
    for socket_name, value in REBUILT_BSDF_DEFAULTS.items():
        if socket_name in bsdf.inputs:
            bsdf.inputs[socket_name].default_value = value

    normal_map = None
    if any(spec.needs_normal_map and spec.id in image_nodes
           for spec in bake_passes):
        normal_map = tree.nodes.new('ShaderNodeNormalMap')
        normal_map.location = (bsdf.location.x - 300, bsdf.location.y - 640)

    for index, spec in enumerate(bake_passes):
        image_node = image_nodes.get(spec.id)
        if image_node is None:
            continue
        image_node.location = (bsdf.location.x - 660, bsdf.location.y - index * 320)

        if spec.needs_normal_map and normal_map is not None:
            tree.links.new(image_node.outputs['Color'], normal_map.inputs['Color'])
            tree.links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
            continue
        if spec.rebuild_socket and spec.rebuild_socket in bsdf.inputs:
            tree.links.new(
                image_node.outputs['Color'], bsdf.inputs[spec.rebuild_socket])
        if spec.rebuild_alpha_socket and spec.rebuild_alpha_socket in bsdf.inputs:
            tree.links.new(
                image_node.outputs['Alpha'], bsdf.inputs[spec.rebuild_alpha_socket])

    tree.links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
    return bsdf


def _bake_margin(size):
    """Margin in pixels scaled to the image (~16px at 2048), minimum 4."""
    return max(4, math.ceil(0.0078125 * max(size)))


class BakeSession:
    """State machine that executes a BakePlan step by step.

    Call begin(), then start_step()/complete_step() per step, then end().
    On cancel or failure, call abort() before end().
    """

    def __init__(self, plan, samples, output_mode=OUTPUT_NEW_MATERIAL,
                 device='GPU'):
        self.plan = plan
        self.samples = samples
        self.output_mode = output_mode
        self.device = device
        self.cancel_requested = False
        self._index = 0
        self._rig = None
        self._snapshot = None

    @property
    def total_steps(self):
        return len(self.plan.steps)

    @property
    def done(self):
        return self._index >= self.total_steps

    @property
    def current_step(self):
        return None if self.done else self.plan.steps[self._index]

    @property
    def progress(self):
        return self._index / max(1, self.total_steps)

    @property
    def finalized_count(self):
        return sum(1 for job in self.plan.jobs if job.finalized)

    @property
    def status_text(self):
        step = self.current_step
        if step is None:
            return "Finishing..."
        text = f"{step.job.material.name}: {step.spec.label}"
        if len(step.job.targets) > 1:
            text += f" on {step.target.obj.name}"
        return f"{text}  ({self._index + 1}/{self.total_steps})"

    def begin(self, context):
        self._snapshot = RenderStateSnapshot(context.scene)

        # grabbed now, removed once the whole material finalizes
        for job in self.plan.jobs:
            tree = job.material.node_tree
            job.original_nodes = [
                node for node in tree.nodes if node.type != 'OUTPUT_MATERIAL'
            ]

        # image.save() fails on a missing directory, so create it up front.
        os.makedirs(bpy.path.abspath(f"//{BAKE_OUTPUT_DIR}"), exist_ok=True)

    def start_step(self, context, invoke):
        """Prepare and launch the bake for the current step.

        With ``invoke=True`` it runs as a background job; wait for the
        ``object_bake_complete`` handler before calling ``complete_step``.
        Returns True if it already finished synchronously.
        """
        step = self.current_step
        if step is None:
            raise BakeError("No bake step to start")

        job, spec, target = step.job, step.spec, step.target
        tree = job.material.node_tree

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        principled = next(
            (node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        output_node = next(
            (node for node in tree.nodes if node.type == 'OUTPUT_MATERIAL'), None)
        if principled is None or output_node is None:
            raise BakeError(
                f"Material '{job.material.name}' lost its BSDF or output node mid-bake")

        # one image+node per (material, pass); later targets bake into the
        # same image, node stays in the tree for finalize to reuse
        if spec.id not in job.images:
            job.images[spec.id] = self._create_image(job, spec)
            image_node = tree.nodes.new('ShaderNodeTexImage')
            image_node.image = job.images[spec.id]
            image_node.label = f"Bake {spec.label}"
            job.image_nodes[spec.id] = image_node
        tree.nodes.active = job.image_nodes[spec.id]

        self._rig = PassRig(job.material)
        self._rig.build(spec, principled, output_node)

        bpy.ops.object.select_all(action='DESELECT')
        target.obj.select_set(True)
        context.view_layer.objects.active = target.obj

        self._apply_bake_settings(context, spec, job)

        kwargs = {
            'type': spec.bake_type,
            'use_clear': step.use_clear,
            'uv_layer': target.uv_layer,
            'use_selected_to_active': False,
            'cage_extrusion': 0.0,
            'normal_space': 'TANGENT',
        }
        logger.info(
            "Baking %s / %s on %s (%dx%d, uv=%s)",
            job.material.name, spec.id, target.obj.name,
            job.size[0], job.size[1], target.uv_layer)

        if invoke:
            result = bpy.ops.object.bake('INVOKE_DEFAULT', **kwargs)
        else:
            result = bpy.ops.object.bake(**kwargs)

        if not result & {'RUNNING_MODAL', 'FINISHED'}:
            raise BakeError(
                f"Bake did not start for '{job.material.name}' ({spec.label}): {result}")
        return 'FINISHED' in result

    def complete_step(self, context):
        """Revert the step rig, persist results, finalize finished materials."""
        step = self.current_step
        if step is None:
            return
        self._revert_rig()

        if step.is_last_target:
            image = step.job.images.get(step.spec.id)
            if image is not None and image.has_data:
                try:
                    image.save()
                except Exception:
                    logger.warning("Could not save baked image %s", image.name)

        self._index += 1
        next_step = self.current_step
        if next_step is None or next_step.job is not step.job:
            self._finalize_job(step.job)

    def abort(self, context):
        """Cancel path: revert edits, drop partial results of unfinished jobs."""
        self._revert_rig()
        for job in self.plan.jobs:
            if job.finalized:
                continue  # finished materials keep their baked result
            tree = job.material.node_tree if job.material else None
            for node in job.image_nodes.values():
                try:
                    tree.nodes.remove(node)
                except (AttributeError, ReferenceError, RuntimeError):
                    pass
            for image in job.images.values():
                try:
                    bpy.data.images.remove(image)
                except (ReferenceError, RuntimeError):
                    pass
            job.image_nodes.clear()
            job.images.clear()

    def end(self, context):
        """Restore the user's render settings."""
        if self._snapshot is not None:
            self._snapshot.restore()
            self._snapshot = None

    def _revert_rig(self):
        if self._rig is not None:
            self._rig.revert()
            self._rig = None

    def _create_image(self, job, spec):
        name = f"{BAKE_IMAGE_PREFIX}{spec.id}_{job.material.name}.png"
        return create_bake_image(name, job.size, spec)

    def _apply_bake_settings(self, context, spec, job):
        scene = context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.bake_type = spec.bake_type
        scene.cycles.use_denoising = False
        scene.cycles.samples = self.samples
        scene.cycles.device = self.device

        bake = scene.render.bake
        bake.target = 'IMAGE_TEXTURES'
        bake.margin = _bake_margin(job.size)
        bake.use_pass_direct = 'DIRECT' in spec.pass_filter
        bake.use_pass_indirect = 'INDIRECT' in spec.pass_filter
        bake.use_pass_color = 'COLOR' in spec.pass_filter
        bake.use_selected_to_active = False
        bake.normal_space = 'TANGENT'

    def _finalize_job(self, job):
        """Produce the baked material according to the session's output mode."""
        if self.output_mode == OUTPUT_REPLACE_MATERIAL:
            self._finalize_replace(job)
        else:
            self._finalize_new_material(job)

        # make the bake UV layer the render layer, so previews/exports use it
        for target in job.targets:
            uv_layers = target.obj.data.uv_layers
            layer = uv_layers.get(target.uv_layer)
            if layer is not None:
                uv_layers.active = layer
                layer.active_render = True

        job.finalized = True
        logger.info("Finalized bake of %s (%s mode)", job.material.name, self.output_mode)

    def _finalize_replace(self, job):
        """Rewrite the source material in place with the baked result.

        Affects every user of the material, including meshes outside the bake.
        """
        material = job.material
        tree = material.node_tree
        output_node = next(
            (node for node in tree.nodes if node.type == 'OUTPUT_MATERIAL'), None)
        if output_node is None:
            logger.warning("Material %s has no output node; skipping rebuild", material.name)
            return

        bsdf = wire_baked_nodes(tree, output_node, job.image_nodes, job.bake_passes)
        bsdf.label = f"Baked {material.name}"

        for node in job.original_nodes:
            try:
                tree.nodes.remove(node)
            except (ReferenceError, RuntimeError):
                pass
        job.original_nodes = []

    def _finalize_new_material(self, job):
        """Build a separate baked material and assign it to the baked meshes
        only, leaving the source material untouched."""
        source = job.material
        baked_name = f"{source.name}{BAKED_MATERIAL_SUFFIX}"
        baked = bpy.data.materials.get(baked_name)
        if baked is None:
            baked = bpy.data.materials.new(baked_name)  # reused on re-bakes
        baked.use_nodes = True
        tree = baked.node_tree
        tree.nodes.clear()

        output_node = tree.nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (320, 0)

        image_nodes = {}
        for spec in job.bake_passes:
            image = job.images.get(spec.id)
            if image is None:
                continue
            node = tree.nodes.new('ShaderNodeTexImage')
            node.image = image
            node.label = f"Bake {spec.label}"
            image_nodes[spec.id] = node

        bsdf = wire_baked_nodes(tree, output_node, image_nodes, job.bake_passes)
        bsdf.label = f"Baked {source.name}"

        copy_display_settings(source, baked)

        # drop the temp image nodes start_step added to the source material
        source_tree = source.node_tree
        for node in job.image_nodes.values():
            try:
                source_tree.nodes.remove(node)
            except (ReferenceError, RuntimeError):
                pass
        job.image_nodes = image_nodes

        # Swap slots on the baked meshes only; other users keep the original.
        for target in job.targets:
            mesh = target.obj.data
            for index, mat in enumerate(mesh.materials):
                if mat is source:
                    mesh.materials[index] = baked
        job.baked_material = baked
