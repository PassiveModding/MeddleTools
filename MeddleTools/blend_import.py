import bpy
from os import path
from . import version
    
class ImportShaders(bpy.types.Operator):

    bl_idname = "meddle.import_shaders"
    bl_label = "Import Shaders"
    
    def execute(self, context):
        import_shaders()
            
        return {'FINISHED'}

def import_shaders():        
    blendfile = path.join(path.dirname(path.abspath(__file__)), "shaders.blend")
    
    added = []
    with bpy.data.libraries.load(blendfile, link=False) as (data_from, data_to):
        for material in data_from.materials:
            versioned_name = f"{material} {version.current_version}"
            if versioned_name in bpy.data.materials:
                print(f"Material {versioned_name} already exists, skipping")
                continue
            data_to.materials.append(material)
            added.append(material)
            
    for material in added:
        # rename to include meddle version
        material_obj = bpy.data.materials[material]
        material_obj.name = f"{material_obj.name} {version.current_version}"

def replace_shaders():
    blendfile = path.join(path.dirname(path.abspath(__file__)), "shaders.blend")
    
    added = []
    with bpy.data.libraries.load(blendfile, link=False) as (data_from, data_to):
        for material in data_from.materials:
            versioned_name = f"{material} {version.current_version}"
            if versioned_name in bpy.data.materials:
                print(f"Material {versioned_name} already exists, replacing")
                bpy.data.materials.remove(bpy.data.materials[versioned_name])
            data_to.materials.append(material)
            added.append(material)
            
    for material in added:
        # rename to include meddle version
        material_obj = bpy.data.materials[material]
        material_obj.name = f"{material_obj.name} {version.current_version}"
    

class ReplaceShaders(bpy.types.Operator):
    
    bl_idname = "meddle.replace_shaders"
    bl_label = "Replace Shaders"
    
    def execute(self, context):
        replace_shaders()
            
        return {'FINISHED'}
    
classes = [
    ImportShaders,
    ReplaceShaders
]