import bpy
from os import path

from numpy import isin
from . import blend_import
from . import node_groups

class ShaderFixActive(bpy.types.Operator):    
    bl_idname = "meddle.use_shaders_active_material"
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
    bl_idname = "meddle.use_shaders_selected_objects"
    bl_label = "Use Shaders on Selected"
        
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
                    try:
                        shpkMtrlFixer(obj, slot.material, self.directory)
                    except Exception as e:
                        print(f"Error on {slot.material.name}: {e}")
                                    
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
    node_group = groupData[0]
    additional_mappings = groupData[1]
    if node_group is None:
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
    
    if node_group.name not in bpy.data.node_groups:
        print(f"Node group {node_group.name} not found")
        return {'CANCELLED'}
    
    nodeGroupData = bpy.data.node_groups[node_group.name]
    if not isinstance(nodeGroupData, bpy.types.ShaderNodeTree):
        print(f"Node group {node_group.name} is not a ShaderNodeTree")
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
    all_mappings = node_group.mapping_definitions + additional_mappings
    for mapping in all_mappings:
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
        elif isinstance(mapping, node_groups.FloatValueMapping):
            mapping.apply(groupNode)
        elif isinstance(mapping, node_groups.FloatRgbaAlphaMapping):
            mapping.apply(groupNode, properties)
        elif isinstance(mapping, node_groups.ColorSetMapping2):
            node_height = mapping.apply(material, groupNode, properties, directory, node_height)
        elif isinstance(mapping, node_groups.BgMapping):
            node_height = mapping.apply(material, mesh, groupNode, properties, directory, node_height)
        elif isinstance(mapping, node_groups.FloatMapping):
            mapping.apply(groupNode, properties)
        elif isinstance(mapping, node_groups.UVMapping):
            node_height = mapping.apply(material, mesh, groupNode, node_height)
        elif isinstance(mapping, node_groups.FloatArrayIndexedValueMapping):
            mapping.apply(groupNode, properties)
            
    # get horizontal pos of east most node
    east = 0
    for node in material.nodes:
        if node.location[0] > east:
            east = node.location[0]
            
    # set bsdfNode location and output location
    groupNode.location = (east + 200, 300)
    bsdfNode.location = (east + 600, 300)
    materialOutput.location = (east + 1000, 300)
                
    return {'FINISHED'}
        
    
        
    