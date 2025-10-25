import bpy
from os import path

from . import node_configs
from . import blend_import
from . import lighting


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
    #filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    files: bpy.props.CollectionProperty(name="File Path Collection", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})
    
    # Class variables for async import state
    _import_queue = []
    _current_import_index = 0
    _timer = None
    _context = None
    _progress_started = False

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):    
        if context is None:
            return {'CANCELLED'}
        
        # Prepare the import queue
        self._import_queue = []
        for file in self.files:
            filepath = path.join(self.directory, file.name)
            self._import_queue.append(filepath)
        
        self._current_import_index = 0
        self._context = context
        
        if not self._import_queue:
            return {'CANCELLED'}
        
        # Import shaders once at the beginning
        try:
            blend_import.import_shaders()
        except Exception as e:
            print(f"Error importing shaders: {e}")
            return {'CANCELLED'}
        
        # Start the async import process
        print(f"Starting import of {len(self._import_queue)} files...")
        # Begin a progress indicator in the UI so the user can see activity
        try:
            context.window_manager.progress_begin(len(self._import_queue))
            self._progress_started = True
        except Exception:
            # Some Blender contexts may not support progress APIs in all areas; fall back to prints
            self._progress_started = False

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        # Report to the user in the info area
        try:
            self.report({'INFO'}, f"Starting import of {len(self._import_queue)} files...")
        except Exception:
            pass

        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            # Process one file from the queue
            if self._current_import_index < len(self._import_queue):
                filepath = self._import_queue[self._current_import_index]
                
                try:
                    self.import_single_file(filepath, context)
                    print(f"Imported file {self._current_import_index + 1}/{len(self._import_queue)}: {path.basename(filepath)}")
                    # update the UI progress and operator report
                    try:
                        if self._progress_started:
                            context.window_manager.progress_update(self._current_import_index + 1)
                            # Force UI redraw so progress shows between imports
                            try:
                                for area in context.window.screen.areas:
                                    area.tag_redraw()
                            except Exception:
                                # Fallback to redraw operator if available
                                try:
                                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        self.report({'INFO'}, f"Imported {path.basename(filepath)} ({self._current_import_index + 1}/{len(self._import_queue)})")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Error importing {filepath}: {e}")
                
                self._current_import_index += 1
                
                # Continue processing
                return {'PASS_THROUGH'}
            else:
                # All files processed, cleanup and finish
                self._cleanup(context)
                print("Import completed!")
                try:
                    self.report({'INFO'}, "Import completed")
                except Exception:
                    pass
                return {'FINISHED'}
        
        return {'PASS_THROUGH'}
    
    def cancel(self, context):
        self._cleanup(context)
        print("Async import cancelled!")
        try:
            self.report({'WARNING'}, "Async import cancelled")
        except Exception:
            pass
        return {'CANCELLED'}
    
    def _cleanup(self, context):
        """Clean up timer and reset state"""
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        # End progress indicator if started
        try:
            if self._progress_started:
                context.window_manager.progress_end()
        except Exception:
            pass

        self._progress_started = False
        self._import_queue = []
        self._current_import_index = 0
        self._context = None
    
    def import_single_file(self, filepath, context):
        """Import a single GLTF file and process it"""
        print(f"GLTF Path: {filepath}")
        
        cache_dir = path.join(path.dirname(filepath), "cache")
        
        # Store current selection before import
        original_selection = list(context.selected_objects)
        
        # Import the GLTF file
        bpy.ops.import_scene.gltf(filepath=filepath, bone_heuristic='TEMPERANCE')
        
        # Get newly imported objects
        current_selected_copy = list(context.selected_objects)
        newly_imported = [obj for obj in current_selected_copy if obj not in original_selection]
        
        # Process imported meshes
        imported_meshes = [obj for obj in newly_imported if obj.type == 'MESH']
        for mesh in imported_meshes:
            if mesh is None:
                continue
            
            try:
                node_configs.map_mesh(mesh, cache_dir)
            except Exception as e:
                print(f"Error mapping mesh {mesh.name}: {e}")
        
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
        
        all_materials_unique = set()
        for obj in selected_objects:
            if obj.type == 'MESH':
                for mat_slot in obj.material_slots:
                    if mat_slot.material is not None:
                        all_materials_unique.add(mat_slot.material)
                        
        for mat in all_materials_unique:
            # change name to remove Meddle prefix if it exists
            if mat.name.startswith("Meddle "):
                mat.name = mat.name[len("Meddle "):]

        for obj in selected_objects:
            if obj.type == 'MESH':
                node_configs.map_mesh(obj, self.directory)
                
        return {'FINISHED'}

classes = [
    ModelImport,
    ApplyToSelected
]