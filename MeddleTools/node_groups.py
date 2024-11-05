import bpy
from os import path

meddleSkinName = 'meddle skin.shpk'
meddleFaceSkinName = 'meddle face skin.shpk'
meddleHairName = 'meddle hair.shpk'
meddleFaceHairName = 'meddle face hair.shpk'
meddleIrisName = 'meddle iris.shpk'
meddleCharacterTattooName = 'meddle charactertattoo.shpk'
meddleCharacterOcclusionName = 'meddle characterocclusion.shpk'
meddleCharacterName = 'meddle character.shpk'
meddleBgName = 'meddle bg.shpk'
meddleBgColorChangeName = 'meddle bgcolorchange.shpk'

pngMappings = 'PngMappings'
floatRgbMappings = 'FloatRgbMappings'
boolToFloatMappings = 'BoolToFloatMappings'

nodegroups: list[str] = [
    meddleSkinName,
    meddleFaceSkinName,
    meddleHairName,
    meddleFaceHairName,
    meddleIrisName,
    meddleCharacterTattooName,
    meddleCharacterOcclusionName,
    meddleBgName,
    meddleBgColorChangeName,
    meddleCharacterName
]

class NodeGroup:
    def __init__(self, name: str, mapping_definitions: list):
        self.name = name
        self.mapping_definitions = mapping_definitions
        
class PngMapping:
    def __init__(self, property_name: str, color_dest: str, alpha_dest: str | None, color_space: str):
        self.property_name = property_name
        self.color_dest = color_dest
        self.alpha_dest = alpha_dest
        self.color_space = color_space
        
    def __repr__(self):
        return f"PngMapping({self.property_name}, {self.color_dest}, {self.alpha_dest}, {self.color_space})"
    
    def apply(self, material, groupNode, properties, directory, node_height):
        texture = material.nodes.new('ShaderNodeTexImage')
        
        if self.property_name not in properties:
            print(f"Property {self.property_name} not found in material")
            return node_height - 300
        
        pathStr = properties[self.property_name]
        if pathStr is None or not isinstance(pathStr, str):
            return node_height - 300
        
        if pathStr.endswith('.tex'):
            pathStr = pathStr + '.png'
        
        # if image exists in scene, use that instead of loading from file
        for img in bpy.data.images:
            if img.filepath == directory + pathStr:
                texture.image = img
                break
        else:        
            if not path.exists(directory + pathStr):
                print(f"Texture {directory + pathStr} not found")
                return node_height - 300
            texture.image = bpy.data.images.load(directory + pathStr)
        texture.location = (-500, node_height)
        texture.image.colorspace_settings.name = self.color_space
        
        if self.alpha_dest is not None:
            material.links.new(texture.outputs['Alpha'], groupNode.inputs[self.alpha_dest])
        material.links.new(texture.outputs['Color'], groupNode.inputs[self.color_dest])
        
        return node_height - 300
    
class VertexPropertyMapping:
    def __init__(self, property_name: str, color_dest: str | None, alpha_dest: str | None, default_color: tuple = (0.5, 0.5, 0.5, 1.0)):
        self.property_name = property_name
        self.color_dest = color_dest
        self.alpha_dest = alpha_dest
        self.default_color = default_color
        
    def __repr__(self):
        return f"VertexPropertyMapping({self.property_name}, {self.color_dest})"
    
    def apply(self, material, mesh, groupNode, node_height):           
        if mesh is None:
            return node_height - 300
        
        if not isinstance(mesh, bpy.types.Mesh):
            print(f"Object {mesh.name} is not a Mesh")
            return node_height - 300     
                
        use_default_colors = False
        if self.property_name not in mesh.vertex_colors:
            use_default_colors = True
        

        if use_default_colors:
            if self.color_dest is not None:
                groupNode.inputs[self.color_dest].default_value = self.default_color                
            if self.alpha_dest is not None:
                groupNode.inputs[self.alpha_dest].default_value = self.default_color[3]            
            return node_height - 300
        else:
            vertexColor = material.nodes.new('ShaderNodeVertexColor')
            if not isinstance(vertexColor, bpy.types.ShaderNodeVertexColor):
                print(f"Node {vertexColor.name} is not a ShaderNodeVertexColor")
                return node_height - 300
            
            vertexColor.layer_name = self.property_name
            vertexColor.location = (-500, node_height)        
            
            if self.color_dest is not None:
                material.links.new(vertexColor.outputs['Color'], groupNode.inputs[self.color_dest])                
            if self.alpha_dest is not None:
                material.links.new(vertexColor.outputs['Alpha'], groupNode.inputs[self.alpha_dest])            
            return node_height - 300
    
class FloatRgbMapping:
    def __init__(self, property_name: str, color_dest: str):
        self.property_name = property_name
        self.color_dest = color_dest
        
    def __repr__(self):
        return f"FloatRgbMapping({self.property_name}, {self.color_dest})"
    
    def apply(self, groupNode, properties):
        value_arr = [0.5, 0.5, 0.5, 1.0]
        if self.property_name in properties:      
            value_arr = properties[self.property_name].to_list()
        else:
            print(f"Property {self.property_name} not found in material")
            
        if len(value_arr) == 3:
            value_arr.append(1.0)
            
        groupNode.inputs[self.color_dest].default_value = value_arr            
            
            
class ColorSetMapping:
    def __init__(self, property_name: str, id_texture_name: str, ramp_name_a: str, ramp_name_b: str, ramp_a_dest: str, ramp_b_dest:str, index_g_dest: str):
        self.property_name = property_name
        self.ramp_name_a = ramp_name_a
        self.ramp_name_b = ramp_name_b
        self.id_texture_name = id_texture_name
        self.ramp_a_dest = ramp_a_dest
        self.ramp_b_dest = ramp_b_dest
        self.index_g_dest = index_g_dest
        
    def __repr__(self):
        return f"ColorSetMapping({self.property_name})"
    
    def apply(self, material, groupNode, properties, directory, node_height):
        if self.property_name not in properties:
            print(f"Property {self.property_name} not found in material")
            return node_height - 300
        
        colorSet = properties[self.property_name]
        if colorSet is None:
            print(f"Property {self.property_name} is None")
            return node_height - 300
        
        if 'ColorTable' not in colorSet:
            print(f"Property {self.property_name} does not contain ColorTable")
            return node_height - 300
       
        colorSet = colorSet['ColorTable']
       
        if 'Rows' not in colorSet:
            print(f"Property {self.property_name} does not contain Rows")
            return node_height - 300
        
        rows = colorSet['Rows']
        if len(rows) == 0:
            print(f"Property {self.property_name} contains no Rows")
            return node_height - 300
        
        texture = material.nodes.new('ShaderNodeTexImage')
        

        pathStr = properties[self.id_texture_name]
        if pathStr is None or not isinstance(pathStr, str):
            return node_height - 300
        
        if pathStr.endswith('.tex'):
            pathStr = pathStr + '.png'
        
        # if image exists in scene, use that instead of loading from file
        for img in bpy.data.images:
            if img.filepath == directory + pathStr:
                texture.image = img
                break
        else:        
            if not path.exists(directory + pathStr):
                print(f"Texture {directory + pathStr} not found")
                return node_height - 300
            texture.image = bpy.data.images.load(directory + pathStr)
        texture.location = (-500, node_height)
        texture.name = self.id_texture_name
        texture.label = self.id_texture_name
        texture.image.colorspace_settings.name = 'Non-Color'
        
        
        # separate color
        textureSeparate = material.nodes.new('ShaderNodeSeparateColor')
        textureSeparate.location = (-300, node_height)
        material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])        
        material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])
        
        # create colorRamp if it doesn't exist
        colorRampA = None
        if self.ramp_name_a not in material.nodes:
            colorRampA = material.nodes.new('ShaderNodeValToRGB')
            colorRampA.name = self.ramp_name_a
            colorRampA.location = (0, 0)
            colorRampA.color_ramp.interpolation = 'EASE'
        else:
            colorRampA = material.nodes[self.ramp_name_a]
            
        colorRampB = None
        if self.ramp_name_b not in material.nodes:
            colorRampB = material.nodes.new('ShaderNodeValToRGB')
            colorRampB.name = self.ramp_name_b
            colorRampB.location = (0, 0)
            colorRampB.color_ramp.interpolation = 'EASE'
        else:
            colorRampB = material.nodes[self.ramp_name_b]
            
        # clear existing elements, leaving last one
        while len(colorRampA.color_ramp.elements) > 1:
            colorRampA.color_ramp.elements.remove(colorRampA.color_ramp.elements[0])
        while len(colorRampB.color_ramp.elements) > 1:
            colorRampB.color_ramp.elements.remove(colorRampB.color_ramp.elements[0])
        
        odds = []
        evens = []
        for i, row in enumerate(rows):
            if i % 2 == 0:
                evens.append(row)
            else:
                odds.append(row)
                
        for i, row in enumerate(evens):
            pos = i / (len(evens) - 1)
            if i == 0:
                colorRampA.color_ramp.elements[0].position = pos
                colorRampA.color_ramp.elements[0].color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
            else:
                element = colorRampA.color_ramp.elements.new(pos)
                element.color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
                
        for i, row in enumerate(odds):
            pos = i / (len(odds) - 1)
            if i == 0:
                colorRampB.color_ramp.elements[0].position = pos
                colorRampB.color_ramp.elements[0].color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
            else:
                element = colorRampB.color_ramp.elements.new(pos)
                element.color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)  
                
        material.links.new(textureSeparate.outputs['Red'], colorRampA.inputs['Fac'])
        material.links.new(textureSeparate.outputs['Red'], colorRampB.inputs['Fac'])
        material.links.new(colorRampA.outputs['Color'], groupNode.inputs[self.ramp_a_dest])
        material.links.new(colorRampB.outputs['Color'], groupNode.inputs[self.ramp_b_dest])
        material.links.new(textureSeparate.outputs['Green'], groupNode.inputs[self.index_g_dest])   
        
        return node_height - 300

class BoolToFloatMapping:
    def __init__(self, property_name: str, float_dest: str):
        self.property_name = property_name
        self.float_dest = float_dest
        
    def __repr__(self):
        return f"BoolToFloatMapping({self.property_name}, {self.float_dest})"
    
    def apply(self, groupNode, properties):
        if properties[self.property_name]:
            groupNode.inputs[self.float_dest].default_value = 1.0
        else:
            groupNode.inputs[self.float_dest].default_value = 0.0

meddle_skin = NodeGroup(
    meddleSkinName,
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
    ]
)

meddle_face_skin = NodeGroup(
    meddleFaceSkinName,
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
        FloatRgbMapping('LipColor', 'Lip Color'),
        BoolToFloatMapping('LipStick', 'Lip Color Strength')
    ]
)

meddle_iris = NodeGroup(
    meddleIrisName,
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', None, 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        FloatRgbMapping('LeftIrisColor', 'Eye Color'),
        FloatRgbMapping('RightIrisColor', 'Second Eye Color')
    ]
)

meddle_hair = NodeGroup(
    meddleHairName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
    ]
)

meddle_face_hair = NodeGroup(
    meddleFaceHairName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
    ]
)

meddle_character_occlusion = NodeGroup(
    meddleCharacterOcclusionName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
    ]
)

meddle_character_tattoo = NodeGroup(
    meddleCharacterTattooName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
    ]
)

meddle_character = NodeGroup(
    meddleCharacterName,
    [
        ColorSetMapping('ColorTable', 'g_SamplerIndex_PngCachePath', 'TableA', 'TableB', 'color_a', 'color_b', 'id_mix'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
    ]
)

meddle_bg = NodeGroup(
    meddleBgName,
    [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerColorMap1', 'g_SamplerColorMap1', 'g_SamplerColorMap1_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerNormalMap1', 'g_SamplerNormalMap1', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap1', 'g_SamplerSpecularMap1', None, 'Non-Color'),
        VertexPropertyMapping('Color', None, 'vertex_alpha', (0.5, 0.5, 0.5, 0)),
    ]
)

meddle_bg_colorchange = NodeGroup(
    meddleBgColorChangeName,
    [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
        FloatRgbMapping('StainColor', 'StainColor'),
    ]
)
        
def matchShader(mat):
    if mat is None:
        return None
    
    properties = mat
    shaderPackage = properties["ShaderPackage"]
    
    if shaderPackage is None:
        return None
    
    if shaderPackage == 'skin.shpk':
        output = meddle_face_skin
        if 'CategorySkinType' in properties:
            if properties["CategorySkinType"] == 'Body':
                output = meddle_skin
            elif properties["CategorySkinType"] == 'Face':
                output = meddle_face_skin
            elif properties["CategorySkinType"] == 'Hrothgar':
                print("Hrothgar, not implemented")
                
        return output
       
    if shaderPackage == 'hair.shpk':
        output = meddle_hair
        if 'CategoryHairType' in properties:
            if properties["CategoryHairType"] == 'Face':
                output = meddle_face_hair
                
        return output
    
    if shaderPackage == 'iris.shpk':
        return meddle_iris
    
    if shaderPackage == 'charactertattoo.shpk':
        return meddle_character_tattoo
    
    if shaderPackage == 'characterocclusion.shpk':
        return meddle_character_occlusion
    
    if shaderPackage == 'character.shpk':
        return meddle_character
    
    if shaderPackage == 'characterlegacy.shpk':
        return meddle_character
    
    if shaderPackage == 'bg.shpk':
        return meddle_bg
    
    if shaderPackage == 'bgcolorchange.shpk':
        return meddle_bg_colorchange
    
    print("No suitable shader found for " + shaderPackage + " on material " + mat.name)
    return None