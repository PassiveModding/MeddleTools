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


class ShaderHelper(bpy.types.Operator):

    bl_idname = "append.shader_helper"
    bl_label = "map selected"
    
    def execute(self, context):
            
        if context is None:
            return {'CANCELLED'}

        if context.active_object is None or context.active_object.active_material is None or context.active_object.active_material.node_tree is None:
            return {'CANCELLED'}
        
                
        # if group is selected, get selected noded within group
        node_group: bpy.types.ShaderNodeGroup | None = None
        for n in context.active_object.active_material.node_tree.nodes:
            if n.select:
                if n.type == "GROUP" and isinstance(n, bpy.types.ShaderNodeGroup):
                    node_group = n

        if node_group is None:
            print("No group selected")
            return {'CANCELLED'}
                
        selected_bsdf: bpy.types.ShaderNodeBsdfPrincipled | None = None       
        for n in node_group.node_tree.nodes:
            if n.select:
                if n.type == "BSDF_PRINCIPLED":
                    selected_bsdf = n
                
        if selected_bsdf is None:
            print("No bsdf selected")
            return {'CANCELLED'}
        
        group_output = None
        for n in node_group.node_tree.nodes:
            if n.type == "GROUP_OUTPUT":
                group_output = n

        # get selected bsdf inputs
        inputs = selected_bsdf.inputs

        for i in inputs:
            if not isinstance(i, bpy.types.NodeSocket):
                continue
            if i.hide or not i.enabled:
                print(f"Input {i.name} is hidden or disabled")
                continue
            
            print(f"Mapping {i.name}")

            if i.name in node_group.inputs:
                print(f"Input {i.name} already exists")
                continue
            
            mappedType = self.mapType(i.type)
            output = node_group.node_tree.interface.new_socket(name=i.name, socket_type=mappedType, in_out='OUTPUT')
            # set default value of output to value of i  
            mapped_value = i.default_value
            node_group.outputs[i.name].default_value = mapped_value
            group_output.inputs[i.name].default_value = mapped_value
            output.default_value = mapped_value
            if i.is_linked:                
                node_group.node_tree.links.new(i.links[0].from_socket, group_output.inputs[i.name])

            
        return {'FINISHED'}
        
        raise Exception(f"Unknown type: {i.type}, {type(i)}")
    
    def mapType(self, type: str):
        # ('NodeSocketBool', 'NodeSocketVector', 'NodeSocketInt', 'NodeSocketShader', 'NodeSocketFloat', 'NodeSocketColor')
        if (type == "RGBA"):
            return "NodeSocketColor"
        
        if (type == "VALUE"):
            return "NodeSocketFloat"
        
        if (type == "VECTOR"):
            return "NodeSocketVector"
        
        error = "Unknown type: " + type
        print(error)
        raise Exception(error)