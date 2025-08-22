from functools import cache
from multiprocessing import context
import bpy
from os import path

from . import node_configs
from . import blend_import
from . import lighting
    

class ModelImport(bpy.types.Operator):
    bl_idname = "meddle.import_gltf"
    bl_label = "Import Model"    
    bl_description = "Import GLTF/GLB files exported from Meddle, automatically applying shaders"
    #filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    files: bpy.props.CollectionProperty(name="File Path Collection", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):    
        if context is None:
            return {'CANCELLED'}
        
        bpy.context.window.cursor_set('WAIT')
        try:
            blend_import.import_shaders()
            
            def import_gltf(filepath):            
                print(f"GLTF Path: {filepath}")
                
                cache_dir = path.join(path.dirname(filepath), "cache")
                bpy.ops.import_scene.gltf(filepath=filepath, bone_heuristic='TEMPERANCE')                
                imported_meshes = [obp for obp in context.selected_objects if obp.type == 'MESH']

                for mesh in imported_meshes:
                    if mesh is None:
                        continue
                    
                    node_configs.map_mesh(mesh, cache_dir)
                    
                imported_lights = [obp for obp in context.selected_objects if obp.name.startswith("Light")]
                
                for light in imported_lights:
                    if light is None:
                        continue
                    
                    try:
                        lighting.setupLight(light)
                    except Exception as e:
                        print(e)
                            
            for file in self.files:
                filepath = path.join(self.directory, file.name)
                import_gltf(filepath)
                            
            return {'FINISHED'}
        finally:
            bpy.context.window.cursor_set('DEFAULT')
            
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
        for obj in selected_objects:
            if obj.type == 'MESH':
                node_configs.map_mesh(obj, self.directory, True)
                
        return {'FINISHED'}

classes = [
    ModelImport,
    ApplyToSelected
]