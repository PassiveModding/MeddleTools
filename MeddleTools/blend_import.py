import bpy
from os import path
from . import node_groups

def import_shaders():        
    blendfile = path.dirname(path.abspath(__file__)) + "/shaders.blend"
    section = "\\NodeTree\\"

    for n in node_groups.nodegroups:
        if n.name in bpy.data.node_groups:
            print(n.name + " already in file")
            continue
        
        print("Appending " + n.name)
        bpy.ops.wm.append(
            filepath = blendfile + section + n.name,
            filename = n.name,
            directory = blendfile + section,
            do_reuse_local_id = True
        )

class ImportShaders(bpy.types.Operator):

    bl_idname = "append.import_shaders"
    bl_label = "Import Shaders"
    
    def execute(self, context):
        import_shaders()
            
        return {'FINISHED'}
