import bpy
from os import path

from . import shader_fix
from . import blend_import


class ModelImport(bpy.types.Operator):
    bl_idname = "meddle.import_gltf"
    bl_label = "Import Model"    
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})
    
    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):    
        if context is None:
            return {'CANCELLED'}
        
        print(f"GLTF Path: {self.filepath}")
        
        blend_import.import_shaders()
        
        
        cache_dir = path.join(path.dirname(self.filepath), "cache")
        
        bpy.ops.import_scene.gltf(filepath=self.filepath, disable_bone_shape=True)
        imported_meshes = [obp for obp in context.selected_objects if obp.type == 'MESH']
        
        for mesh in imported_meshes:
            if mesh is None:
                continue
            
            for slot in mesh.material_slots:
                if slot.material is not None:
                    try:
                        shader_fix.shpkMtrlFixer(mesh, slot.material, cache_dir)
                    except Exception as e:
                        print(e)
                        
        return {'FINISHED'}