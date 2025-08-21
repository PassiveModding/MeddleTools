import bpy
from os import path
    
class ImportShaders(bpy.types.Operator):

    bl_idname = "meddle.import_shaders"
    bl_label = "Import Shaders"
    
    def execute(self, context):
        import_shaders()
            
        return {'FINISHED'}

def import_shaders():        
    blendfile = path.join(path.dirname(path.abspath(__file__)), "shaders_new.blend")
    
    with bpy.data.libraries.load(blendfile, link=False) as (data_from, data_to):
        for material in data_from.materials:
            if material in bpy.data.materials:
                print(f"Material {material} already exists, skipping")
                continue
            data_to.materials.append(material)
        
        # for node_group in data_from.node_groups:
        #     if node_group in bpy.data.node_groups:
        #         print(f"Node group {node_group} already exists")
        #         continue
        #     bpy.ops.wm.append(filename=node_group, directory=blendfile + "/NodeTree/", do_reuse_local_id=True)

def replace_shaders():
    blendfile = path.join(path.dirname(path.abspath(__file__)), "shaders_new.blend")
    
    with bpy.data.libraries.load(blendfile, link=False) as (data_from, data_to):
        for material in data_from.materials:
            if material in bpy.data.materials:
                print(f"Material {material} already exists, replacing")
                bpy.data.materials.remove(bpy.data.materials[material])
            data_to.materials.append(material)
        
        # for node_group in data_from.node_groups:
        #     if node_group in bpy.data.node_groups:
        #         print(f"Node group {node_group} already exists, replacing")
        #         bpy.data.node_groups.remove(bpy.data.node_groups[node_group])
        #     bpy.ops.wm.append(filename=node_group, directory=blendfile + "/NodeTree/", do_reuse_local_id=True)

class ReplaceShaders(bpy.types.Operator):
    
    bl_idname = "meddle.replace_shaders"
    bl_label = "Replace Shaders"
    
    def execute(self, context):
        replace_shaders()
            
        return {'FINISHED'}