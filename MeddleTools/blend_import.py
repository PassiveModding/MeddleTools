import bpy
from os import path
from . import node_groups

def import_shaders():        
    blendfile = path.dirname(path.abspath(__file__)) + "/shaders.blend"
    section = "\\NodeTree\\"

    for n in node_groups.nodegroups:
        if n in bpy.data.node_groups:
            print(n + " already in file")
            continue
        
        print("Appending " + n)
        bpy.ops.wm.append(
            filepath = blendfile + section + n,
            filename = n,
            directory = blendfile + section,
            do_reuse_local_id = True
        )

class ImportShaders(bpy.types.Operator):

    bl_idname = "append.import_shaders"
    bl_label = "Import Shaders"
    
    def execute(self, context):
        import_shaders()
            
        return {'FINISHED'}
