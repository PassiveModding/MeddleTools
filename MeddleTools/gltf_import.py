import bpy
from os import path

from .node_setup import node_configs
from . import blend_import
from . import lighting
from . import preferences


def getRootObject(obj: bpy.types.Object) -> bpy.types.Object:
    if obj is None:
        return None

    # find the root object, which is the first parent that has no parent
    while obj.parent is not None:
        obj = obj.parent

    return obj


def unlinkFromSceneCollection(obj: bpy.types.Object, context: bpy.types.Context):
    if obj is None or context is None:
        return {'CANCELLED'}

    # if object is not in the scene collection, do nothing
    if obj.name not in context.scene.collection.objects:
        return {'CANCELLED'}

    # unlink the object from the scene collection
    context.scene.collection.objects.unlink(obj)

    return {'FINISHED'}


def addToGroup(obj: bpy.types.Object, group_name: str, context: bpy.types.Context):
    if obj is None or group_name is None or context is None:
        return {'CANCELLED'}

    # check if the group exists
    if group_name not in bpy.data.collections:
        # create the group
        new_collection = bpy.data.collections.new(group_name)
        context.scene.collection.children.link(new_collection)

    # check if the object is already in the group
    if obj.name in bpy.data.collections[group_name].objects:
        print(f"Object {obj.name} is already in the group {group_name}.")
        return {'CANCELLED'}

    # link the object to the group
    collection = bpy.data.collections[group_name]
    collection.objects.link(obj)

    # unlink from scene collection
    unlinkFromSceneCollection(obj, context)

    return {'FINISHED'}


def setCollection(obj: bpy.types.Object, context: bpy.types.Context):
    if obj is None or context is None:
        return {'CANCELLED'}

    # get the root object
    checkObj = getRootObject(obj)

    # based on name of the object, set the collection
    if checkObj.name.startswith("Decal_"):
        addToGroup(obj, "Decals", context)

    if checkObj.name.startswith("Light_") or checkObj.name.startswith("EnvLighting_"):
        addToGroup(obj, "Lights", context)

    if checkObj.name.startswith("SharedGroup_"):
        addToGroup(obj, "SharedGroups", context)

    if checkObj.name.startswith("Housing_"):
        addToGroup(obj, "Housing", context)

    if checkObj.name.startswith("BgPart_"):
        addToGroup(obj, "BgParts", context)

    if checkObj.name.startswith("Terrain_"):
        addToGroup(obj, "Terrain", context)

    return {'FINISHED'}


class ModelImport(bpy.types.Operator):
    bl_idname = "meddle.import_gltf"
    bl_label = "Import Model"
    bl_description = "Import GLTF/GLB files exported from Meddle, automatically applying shaders"
    bl_options = {'PRESET', 'UNDO'}
    files: bpy.props.CollectionProperty(name="File Path Collection", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})

    # The glTF import options (import_shading, bone_heuristic, ...) are defined
    # once in preferences.gltf_import_option_defs() and injected below the
    # class body, so the operator and the add-on preferences stay in sync.

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, 'import_shading')
        layout.prop(self, 'export_import_convert_lighting_mode')

        header, body = layout.panel("MEDDLE_import_mesh", default_closed=False)
        header.label(text="Mesh")
        if body:
            body.prop(self, 'merge_vertices')
            body.prop(self, 'import_merge_material_slots')

        header, body = layout.panel("MEDDLE_import_bone", default_closed=False)
        header.label(text="Bones & Skin")
        if body:
            body.prop(self, 'bone_heuristic')
            if self.bone_heuristic == 'BLENDER':
                body.prop(self, 'guess_original_bind_pose')
                body.prop(self, 'disable_bone_shape')
                body.prop(self, 'bone_shape_scale_factor')

        header, body = layout.panel("MEDDLE_import_texture", default_closed=False)
        header.label(text="Texture")
        if body:
            body.prop(self, 'import_pack_images')

        header, body = layout.panel("MEDDLE_import_ux", default_closed=False)
        header.label(text="Pipeline")
        if body:
            body.prop(self, 'import_select_created_objects')

    def get_gltf_import_kwargs(self):
        return {key: getattr(self, key) for key in preferences.GLTF_IMPORT_OPTION_KEYS}

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}

        # Seed options from the add-on preferences. Options the user already
        # changed this session (remembered by Blender as last-used operator
        # properties) win over the preference defaults.
        prefs = preferences.get_addon_preferences(context)
        if prefs is not None:
            for key in preferences.GLTF_IMPORT_OPTION_KEYS:
                if not self.properties.is_property_set(key):
                    setattr(self, key, getattr(prefs, key))

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if context is None:
            return {'CANCELLED'}

        # Prepare the import queue
        import_queue = []
        for file in self.files:
            filepath = path.join(self.directory, file.name)
            import_queue.append(filepath)

        if not import_queue:
            return {'CANCELLED'}

        gltf_import_kwargs = self.get_gltf_import_kwargs()

        # Import shaders once at the beginning
        try:
            blend_import.import_shaders()
        except Exception as e:
            print(f"Error importing shaders: {e}")
            return {'CANCELLED'}

        # Start the import process
        print(f"Starting import of {len(import_queue)} files...")

        # Set cursor to show progress/wait state
        context.window.cursor_modal_set('WAIT')

        # Progress calculation: each file gets 2 chunks (import + material application)
        # Total chunks = len(import_queue) * 2
        progress_started = False
        total_chunks = len(import_queue) * 2

        try:
            context.window_manager.progress_begin(0, total_chunks)
            progress_started = True
        except Exception:
            pass

        # Report to the user in the info area
        try:
            self.report({'INFO'}, f"Starting import of {len(import_queue)} files...")
        except Exception:
            pass

        # Process each file
        for index, filepath in enumerate(import_queue):
            try:
                # Calculate progress range for this file
                chunk_start = index * 2
                chunk_mid = chunk_start + 1
                chunk_end = chunk_start + 2

                # Set progress to start of this file's import
                if progress_started:
                    try:
                        context.window_manager.progress_update(chunk_start)
                    except Exception:
                        pass

                # Import file and apply materials with granular progress
                mesh_count = self.import_single_file(
                    filepath,
                    context,
                    chunk_mid,
                    chunk_end,
                    progress_started,
                    context.window_manager if progress_started else None,
                    gltf_import_kwargs,
                )

                print(f"Imported file {index + 1}/{len(import_queue)}: {path.basename(filepath)} ({mesh_count} meshes)")

                # Restore cursor state after import (GLTF import may have changed it)
                try:
                    context.window.cursor_modal_set('WAIT')
                except Exception:
                    pass

                try:
                    self.report({'INFO'}, f"Imported {path.basename(filepath)} ({index + 1}/{len(import_queue)})")
                except Exception:
                    pass
            except Exception as e:
                print(f"Error importing {filepath}: {e}")
                try:
                    self.report({'WARNING'}, f"Failed to import {path.basename(filepath)}: {e}")
                except Exception:
                    pass
                # Restore cursor state even after error
                try:
                    context.window.cursor_modal_set('WAIT')
                except Exception:
                    pass

        # Cleanup
        try:
            if progress_started:
                context.window_manager.progress_end()
        except Exception:
            pass

        # Restore cursor to normal
        context.window.cursor_modal_restore()

        print("Import completed!")
        try:
            self.report({'INFO'}, "Import completed")
        except Exception:
            pass

        return {'FINISHED'}

    def import_single_file(self, filepath, context, chunk_mid, chunk_end, progress_started, wm, gltf_import_kwargs):
        """Import a single GLTF file and process it

        Args:
            filepath: Path to the GLTF file
            context: Blender context
            chunk_mid: Progress value after import (before materials)
            chunk_end: Progress value after all materials applied
            progress_started: Whether progress tracking is active
            wm: Window manager for progress updates
            gltf_import_kwargs: Options forwarded to bpy.ops.import_scene.gltf

        Returns:
            Number of meshes processed
        """
        print(f"GLTF Path: {filepath}")

        cache_dir = path.join(path.dirname(filepath), "cache")

        # Store existing objects before import (selection isn't reliable here since
        # 'import_select_created_objects' may be disabled, leaving nothing selected)
        original_objects = set(bpy.data.objects)

        # Import the GLTF file
        bpy.ops.import_scene.gltf(filepath=filepath, **gltf_import_kwargs)

        # Update progress to chunk_mid (import complete)
        if progress_started and wm:
            try:
                wm.progress_update(chunk_mid)
            except Exception:
                pass

        # Get newly imported objects
        newly_imported = [obj for obj in bpy.data.objects if obj not in original_objects]

        # Process imported meshes
        imported_meshes = [obj for obj in newly_imported if obj.type == 'MESH']

        # Calculate granular progress increment for each mesh
        # Progress goes from chunk_mid to chunk_end over all meshes

        material_slot_map = {}
        for mesh in imported_meshes:
            if mesh is None:
                continue

            for slot in mesh.material_slots:
                if slot.material is not None:
                    if slot.material not in material_slot_map:
                        material_slot_map[slot.material] = []
                    material_slot_map[slot.material].append(slot)

        material_count = len(material_slot_map)

        for material, slots in material_slot_map.items():
            try:
                node_configs.map_mesh(material, slots, cache_dir)

                # Update progress granularly between chunk_mid and chunk_end
                if progress_started and wm and material_count > 0:
                    progress_fraction = (list(material_slot_map.keys()).index(material) + 1) / material_count
                    current_progress = chunk_mid + (chunk_end - chunk_mid) * progress_fraction
                    try:
                        wm.progress_update(current_progress)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error mapping material {material.name}: {e}")

        # Process imported lights
        imported_lights = [obj for obj in newly_imported if obj.name.startswith("Light")]
        for light in imported_lights:
            if light is None:
                continue

            try:
                lighting.setupLight(light)
            except Exception as e:
                print(f"Error setting up light {light.name}: {e}")

        # Set collections for all imported objects
        for obj in newly_imported:
            try:
                setCollection(obj, context)
            except Exception as e:
                print(f"Error setting collection for {obj.name}: {e}")

        return len(imported_meshes)


# Inject the shared glTF import option properties (single definition in
# preferences.py) so register_class picks them up on this operator too.
for _name, _prop in preferences.gltf_import_option_defs().items():
    ModelImport.__annotations__[_name] = _prop


class ApplyToSelected(bpy.types.Operator):
    bl_idname = "meddle.apply_to_selected"
    bl_label = "Apply Shaders to Selected"
    bl_description = "Apply shaders to the selected objects based on their shader package"
    directory: bpy.props.StringProperty(subtype='DIR_PATH')

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if context is None:
            return {'CANCELLED'}

        selected_objects = context.selected_objects

        material_slot_map = {}
        for obj in selected_objects:
            if obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material is not None:
                        if slot.material not in material_slot_map:
                            material_slot_map[slot.material] = []
                        material_slot_map[slot.material].append(slot)

        for material, slots in material_slot_map.items():
            try:
                if material.name.startswith("Meddle "):
                    material.name = material.name[len("Meddle ") :]
                node_configs.map_mesh(material, slots, self.directory)
            except Exception as e:
                print(f"Error mapping material {material.name}: {e}")

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ModelImport.bl_idname, text="Meddle Model (.gltf/.glb)", icon='IMPORT')


classes = [ModelImport, ApplyToSelected]
