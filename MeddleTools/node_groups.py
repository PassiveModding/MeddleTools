import bpy
from os import path

meddleSkinName = 'meddle skin.shpk'
meddleFaceSkinName = 'meddle face skin.shpk'
meddleHairName = 'meddle hair.shpk'
meddleFaceHairName = 'meddle face hair.shpk'
meddleIrisName = 'meddle iris.shpk'
meddleCharacterTattooName = 'meddle charactertattoo.shpk'
meddleCharacterOcclusionName = 'meddle characterocclusion.shpk'
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
    meddleBgColorChangeName
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
        PngMapping('g_SamplerDiffuse_PngCachePath', 'Diffuse Texture', 'Diffuse Alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'Mask Texture', None, 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
    ]
)

meddle_face_skin = NodeGroup(
    meddleFaceSkinName,
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'Diffuse Texture', 'Diffuse Alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', 'Normal Alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'Mask Texture', None, 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
        FloatRgbMapping('LipColor', 'Lip Color'),
        BoolToFloatMapping('LipStick', 'Lip Color Strength')
    ]
)

meddle_iris = NodeGroup(
    meddleIrisName,
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'Diffuse Texture', None, 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'Mask Texture', None, 'Non-Color'),
        FloatRgbMapping('LeftIrisColor', 'Eye Color'),
        FloatRgbMapping('RightIrisColor', 'Second Eye Color')
    ]
)

meddle_hair = NodeGroup(
    meddleHairName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', 'Normal Alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'Mask Texture', 'Mask Alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
    ]
)

meddle_face_hair = NodeGroup(
    meddleFaceHairName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', 'Normal Alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'Mask Texture', 'Mask Alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
    ]
)

meddle_character_occlusion = NodeGroup(
    meddleCharacterOcclusionName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', None, 'Non-Color'),
    ]
)

meddle_character_tattoo = NodeGroup(
    meddleCharacterTattooName,
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'Normal Texture', 'Normal Alpha', 'Non-Color'),
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
    
    if shaderPackage == 'bg.shpk':
        return meddle_bg
    
    if shaderPackage == 'bgcolorchange.shpk':
        return meddle_bg_colorchange
    
    print("No suitable shader found for " + shaderPackage + " on material " + mat.name)
    return None