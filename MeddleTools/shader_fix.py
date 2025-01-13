import bpy
from os import path

from numpy import isin
from . import blend_import
from . import node_groups

class ShaderFixActive(bpy.types.Operator):    
    bl_idname = "append.use_shaders"
    bl_label = "Use Shaders"    
    
    directory: bpy.props.StringProperty(subtype='DIR_PATH')    
    
    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        active = context.active_object
        
        blend_import.import_shaders()
        
        print(f"Folder selected: {self.directory}")
        
        if active is None:
            return {'CANCELLED'}
            
        if active.active_material is None:
            return {'CANCELLED'}
        
        return shpkMtrlFixer(active, active.active_material, self.directory)
    
class ShaderFixSelected(bpy.types.Operator):    
    bl_idname = "append.use_shaders_current"
    bl_label = "Use Shaders on Current Material"
        
    directory: bpy.props.StringProperty(subtype='DIR_PATH')    
    
    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        # copy of selected objects
        selected = context.selected_objects.copy()
        
        blend_import.import_shaders()
        
        print(f"Folder selected: {self.directory}")
        
        for obj in selected:
            if obj is None:
                continue
            
            for slot in obj.material_slots:
                if slot.material is not None:
                    shpkMtrlFixer(obj, slot.material, self.directory)
            
        return {'FINISHED'}

def shpkMtrlFixer(object: bpy.types.Object, mat: bpy.types.Material, directory: str):
    if mat is None:
        return {'CANCELLED'}
    
    mesh = object.data
    if mesh is None:
        return {'CANCELLED'}
    
    if not isinstance(mesh, bpy.types.Mesh):
        return {'CANCELLED'}    
    
    groupData = node_groups.matchShader(mat)
    if groupData is None:
        return {'CANCELLED'}
    material = mat.node_tree
    if material is None:
        return {'CANCELLED'}
    properties = mat

    #Removes all nodes other than textures to make it simpler to construct a node setup
    for node in material.nodes:
        material.nodes.remove(node)
    
    #Add Material Output
    output = material.nodes.new('ShaderNodeOutputMaterial')
    output.location = (500,300)

    #Add the appropriate shader node group
    groupNode = material.nodes.new('ShaderNodeGroup')
    if not isinstance(groupNode, bpy.types.ShaderNodeGroup):
        print(f"Node {groupNode.name} is not a ShaderNodeGroup")
        return {'CANCELLED'}
    
    if groupData.name not in bpy.data.node_groups:
        print(f"Node group {groupData.name} not found")
        return {'CANCELLED'}
    
    nodeGroupData = bpy.data.node_groups[groupData.name]
    if not isinstance(nodeGroupData, bpy.types.ShaderNodeTree):
        print(f"Node group {groupData.name} is not a ShaderNodeTree")
        return {'CANCELLED'}
    
    groupNode.node_tree = nodeGroupData
    groupNode.location = (200, 300)
    groupNode.width = 300
    
    # create principal bsdf node
    bsdfNode = material.nodes.new('ShaderNodeBsdfPrincipled')
    bsdfNode.location = (600, 300)
    bsdfNode.width = 300
    
    # connect groupNode outputs to bsdf inputs
    # for input in bsdfNode.inputs:
    #    print(f"{input.name}")
    
    for output in groupNode.outputs:
        if output.name in ['BSDF', 'Surface']:
            continue
        if output.name not in bsdfNode.inputs:
            print(f"Output {output.name} not found in bsdfNode")
            continue
        
        material.links.new(output, bsdfNode.inputs[output.name])
    
    # connect bsdf to output
    materialOutput = material.nodes['Material Output']
    surfaceInput = materialOutput.inputs['Surface']
    bsdfOutput = bsdfNode.outputs['BSDF']
    materialOutput.location = (1000, 300)    
    material.links.new(bsdfOutput, surfaceInput)
    
    node_height = 300
    for mapping in groupData.mapping_definitions:
        if isinstance(mapping, node_groups.PngMapping):
            node_height = mapping.apply(material, groupNode, properties, directory, node_height)
        elif isinstance(mapping, node_groups.FloatRgbMapping):
            mapping.apply(groupNode, properties)
        elif isinstance(mapping, node_groups.BoolToFloatMapping):
            mapping.apply(groupNode, properties)
        elif isinstance(mapping, node_groups.VertexPropertyMapping):
            node_height = mapping.apply(material, mesh, groupNode, node_height)
        elif isinstance(mapping, node_groups.ColorSetMapping):
            node_height = mapping.apply(material, groupNode, properties, directory, node_height)
                
    return {'FINISHED'}
        
    
        
    