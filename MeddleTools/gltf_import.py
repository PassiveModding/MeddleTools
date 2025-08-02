import bpy
from os import path

from . import shader_fix
from . import blend_import
    

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

                #bpy.ops.import_scene.gltf(filepath=self.filepath, disable_bone_shape=True)
                if context.scene.model_import_settings.gltfImportMode == 'BLENDER':
                    bpy.ops.import_scene.gltf(filepath=filepath, disable_bone_shape=True)
                elif context.scene.model_import_settings.gltfImportMode == 'TEMPERANCE':
                    bpy.ops.import_scene.gltf(filepath=filepath, bone_heuristic='TEMPERANCE')
                
                imported_meshes = [obp for obp in context.selected_objects if obp.type == 'MESH']
                deduplicate: bool = context.scene.model_import_settings.deduplicateMaterials
                
                # for obj in context.selected_objects:
                #     if "RealScale" in obj:
                #         obj.scale = [obj["RealScale"]["X"], obj["RealScale"]["Y"], obj["RealScale"]["Z"]]
                           
                for obj in context.selected_objects:                    
                    shader_fix.setCollection(obj, context)
                                  
                for mesh in imported_meshes:
                    if mesh is None:
                        continue                    
                    
                    for slot in mesh.material_slots:
                        if slot.material is not None:
                            try:
                                shader_fix.handleShaderFix(mesh, slot.material, deduplicate, cache_dir)
                            except Exception as e:
                                print(e)
                                
                imported_lights = [obp for obp in context.selected_objects if obp.name.startswith("Light")]
                
                for light in imported_lights:
                    if light is None:
                        continue
                    
                    try:
                        shader_fix.handleLightFix(light)
                    except Exception as e:
                        print(e)
                            
            for file in self.files:
                filepath = path.join(self.directory, file.name)
                import_gltf(filepath)
                            
            return {'FINISHED'}
        finally:
            bpy.context.window.cursor_set('DEFAULT')