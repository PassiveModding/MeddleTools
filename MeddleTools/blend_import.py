import bpy
from os import path
from . import version

# shaders.blend defines all meddle materials with the name 'meddle {shader_package}', append the meddle version so when meddle is updated, existing shaders don't break
def get_shader_version(material_name):
    return f"{material_name} {version.current_version}"

# since the meddle xiv plugin exports the 'shaderpackage' property with the name of the shpk, we want it to match the format that `get_shader_version` produces
def get_resource_name(shader_package):
    return f'meddle {shader_package} {version.current_version}'

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
            versioned_name = get_shader_version(material)
            if versioned_name in bpy.data.materials:
                print(f"Material {versioned_name} already exists, skipping")
                continue
            data_to.materials.append(material)
            added.append(material)
            
    for material in added:
        # rename to include meddle version
        material_obj = bpy.data.materials[material]
        material_obj.name = get_shader_version(material_obj.name)

def replace_shaders():
    blendfile = path.join(path.dirname(path.abspath(__file__)), "shaders.blend")
    
    added = []
    with bpy.data.libraries.load(blendfile, link=False) as (data_from, data_to):
        for material in data_from.materials:
            versioned_name = get_shader_version(material)
            if versioned_name in bpy.data.materials:
                print(f"Material {versioned_name} already exists, replacing")
                bpy.data.materials.remove(bpy.data.materials[versioned_name])
            data_to.materials.append(material)
            added.append(material)
            
    for material in added:
        # rename to include meddle version
        material_obj = bpy.data.materials[material]
        material_obj.name = get_shader_version(material_obj.name)
    

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