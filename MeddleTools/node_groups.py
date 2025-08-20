from tracemalloc import start
import bpy
from os import path
   
def setInputSafe(node, input_name: str, value):
    if node is None:
        print("Node is None")
        return
    
    if input_name is None:
        print("Input name is None")
        return
    
    if input_name in node.inputs:
        node.inputs[input_name].default_value = value
    else:
        print(f"Input {input_name} not found in node {node.name}")
        
def linkInputSafe(material, source, groupNode, input_name):
    if input_name in groupNode.inputs:
        material.links.new(source, groupNode.inputs[input_name])
    else:
        print(f"Input {input_name} not found in group node {groupNode.name}")

class NodeGroup:
    def __init__(self, name: str, mapping_definitions: list):
        self.name = name
        self.mapping_definitions = mapping_definitions
        
class PngMapping:
    def __init__(self, property_name: str, color_dest: str | None, alpha_dest: str | None, color_space: str, interpolation: str = 'Linear', optional: bool = False, extension: str = 'REPEAT', alpha_mode: str = 'CHANNEL_PACKED'):
        self.property_name = property_name
        self.color_dest = color_dest
        self.alpha_dest = alpha_dest
        self.color_space = color_space
        self.interpolation = interpolation
        self.optional = optional
        self.extension = extension
        self.alpha_mode = alpha_mode
        
    def __repr__(self):
        return f"PngMapping({self.property_name}, {self.color_dest}, {self.alpha_dest}, {self.color_space})"
    
    def apply(self, material, groupNode, properties, directory, node_height):
        if self.color_dest is not None and self.color_dest not in groupNode.inputs:
            print(f"Property {self.color_dest} not found in group node")
            return node_height - 300
        
        if self.alpha_dest is not None and self.alpha_dest not in groupNode.inputs:
            print(f"Property {self.alpha_dest} not found in group node")
            return node_height - 300
        
        if self.property_name not in properties:
            if self.optional:
                return node_height
            print(f"Property {self.property_name} not found in material")
            return node_height - 300
        
        pathStr = bpy.path.native_pathsep(properties[self.property_name])

        if pathStr is None or not isinstance(pathStr, str):
            print(f"Property {self.property_name} is not a string")
            return node_height - 300
        
        if pathStr.endswith('.tex'):
            print(f"Property {self.property_name} is a .tex file, amending to .png")
            pathStr = pathStr + '.png'
        
        texture = material.nodes.new('ShaderNodeTexImage')
        
        # if image exists in scene, use that instead of loading from file
        for img in bpy.data.images:
            if img.filepath == path.join(directory, pathStr) and img.colorspace_settings.name == self.color_space:
                texture.image = img
                break
        else:
            if not path.exists(path.join(directory, pathStr)):
                print(f"Texture {path.join(directory, pathStr)} not found")
                return node_height - 300
            texture.image = bpy.data.images.load(path.join(directory, pathStr))
        texture.name = self.property_name
        texture.label = self.property_name
        texture.location = (-500, node_height)
        texture.image.colorspace_settings.name = self.color_space
        texture.image.alpha_mode = self.alpha_mode
        texture.interpolation = self.interpolation
        texture.extension = self.extension

        if self.alpha_dest is not None:
            #material.links.new(texture.outputs['Alpha'], groupNode.inputs[self.alpha_dest])
            linkInputSafe(material, texture.outputs['Alpha'], groupNode, self.alpha_dest)
        if self.color_dest is not None:
            #material.links.new(texture.outputs['Color'], groupNode.inputs[self.color_dest])
            linkInputSafe(material, texture.outputs['Color'], groupNode, self.color_dest)
        
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
                #groupNode.inputs[self.color_dest].default_value = self.default_color      
                setInputSafe(groupNode, self.color_dest, self.default_color)          
            if self.alpha_dest is not None:
                #groupNode.inputs[self.alpha_dest].default_value = self.default_color[3]       
                setInputSafe(groupNode, self.alpha_dest, self.default_color[3])     
            return node_height - 300
        else:
            vertexColor = material.nodes.new('ShaderNodeVertexColor')
            if not isinstance(vertexColor, bpy.types.ShaderNodeVertexColor):
                print(f"Node {vertexColor.name} is not a ShaderNodeVertexColor")
                return node_height - 300
            
            vertexColor.layer_name = self.property_name
            vertexColor.location = (-500, node_height)        
            
            if self.color_dest is not None:
                #material.links.new(vertexColor.outputs['Color'], groupNode.inputs[self.color_dest])          
                linkInputSafe(material, vertexColor.outputs['Color'], groupNode, self.color_dest)      
            if self.alpha_dest is not None:
                #material.links.new(vertexColor.outputs['Alpha'], groupNode.inputs[self.alpha_dest])    
                linkInputSafe(material, vertexColor.outputs['Alpha'], groupNode, self.alpha_dest)        
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
            return
            
        if len(value_arr) == 3:
            value_arr.append(1.0)
            
        #groupNode.inputs[self.color_dest].default_value = value_arr
        setInputSafe(groupNode, self.color_dest, value_arr)
        
class FloatArrayMapping:
    def __init__(self, property_name: str, dest: str, destLength: int):
        self.property_name = property_name
        self.dest = dest
        self.destLength = destLength
        
    def __repr__(self) -> str:
        return f"FloatArrayMapping({self.property_name}, {self.dest})"
    
    def apply(self, groupNode, properties):
        if self.property_name not in properties:
            print(f"Property {self.property_name} not found in material")
            return
        
        value_arr = properties[self.property_name].to_list()
        
        # pad to destLength
        while len(value_arr) < self.destLength:
            value_arr.append(0.0)
            
        #groupNode.inputs[self.dest].default_value = value_arr
        setInputSafe(groupNode, self.dest, value_arr)
        
class FloatRgbaAlphaMapping:
    def __init__(self, property_name: str, color_dest: str):
        self.property_name = property_name
        self.color_dest = color_dest
        
    def __repr__(self):
        return f"FloatRgbAlphaMapping({self.property_name}, {self.color_dest})"
    
    def apply(self, groupNode, properties):
        value_arr = [0.5, 0.5, 0.5, 1.0]
        if self.property_name in properties:      
            value_arr = properties[self.property_name].to_list()
        else:
            print(f"Property {self.property_name} not found in material")
            return
            
        if len(value_arr) == 3:
            value_arr.append(1.0)
            
        #groupNode.inputs[self.color_dest].default_value = value_arr[3]
        setInputSafe(groupNode, self.color_dest, value_arr[3])
        
class FloatValueMapping:
    def __init__(self, value: float, property_dest: str):
        self.value = value
        self.property_dest = property_dest
        
    def __repr__(self):
        return f"FloatValueMappping({self.value}, {self.property_dest})"
    
    def apply(self, groupNode):                    
        #groupNode.inputs[self.property_dest].default_value = self.value           
        setInputSafe(groupNode, self.property_dest, self.value)
            
class ColorSetMapping2:
    def __init__(self, index_texture_name: str = 'g_SamplerIndex_PngCachePath', color_table_name: str = 'ColorTable'):
        self.index_texture_name = index_texture_name
        self.color_table_name = color_table_name
    
    def apply(self, material, groupNode, properties, directory, node_height):
        if self.color_table_name not in properties:
            print(f"Property ColorTable not found in material")
            return node_height - 300
        
        colorTableProp = properties[self.color_table_name]
        if 'ColorTable' not in colorTableProp:
            print(f"Property ColorTable does not contain ColorTable")
            return node_height - 300
        
        colorSet = colorTableProp['ColorTable']
        
        if 'Rows' not in colorSet:
            print(f"Property ColorTable does not contain Rows")
            return node_height - 300
        
        rows = colorSet['Rows']
        if len(rows) == 0:
            print(f"Property ColorTable contains no Rows")
            return node_height - 300
        
        # spawn index texture
        texture = material.nodes.new('ShaderNodeTexImage')
        pathStr = bpy.path.native_pathsep(properties[self.index_texture_name])
        if pathStr is None or not isinstance(pathStr, str):
            return node_height - 300
        
        texture.image = bpy.data.images.load(path.join(directory, pathStr))
        texture.location = (-500, node_height)
        texture.name = self.index_texture_name
        # set to closest
        texture.interpolation = 'Closest'
        texture.image.colorspace_settings.name = 'Non-Color'
        
        # separate color
        textureSeparate = material.nodes.new('ShaderNodeSeparateColor')
        textureSeparate.location = (-300, node_height)
        #material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])
        linkInputSafe(material, texture.outputs['Color'], textureSeparate, 'Color')
        
        odds = []
        evens = []
        for i, row in enumerate(rows):
            if i % 2 == 0:
                evens.append(row)
            else:
                odds.append(row)
                
        pairGroups = []
        pairHorizontalPos = 0
        pairPositions = []
        for i, row in enumerate(evens):
            even = evens[i]
            odd = odds[i]
            
            # spawn colortablepair group
            pairNode = material.nodes.new('ShaderNodeGroup')
            pairNodeData = bpy.data.node_groups['meddle colortablepair']
            pairNode.node_tree = pairNodeData
            pairGroups.append(pairNode)
            pairNode.location = (pairHorizontalPos, node_height)
            pairPositions.append(pairHorizontalPos)
            
            # link index green to id_mix
            #material.links.new(textureSeparate.outputs['Green'], pairNode.inputs['id_mix'])
            linkInputSafe(material, textureSeparate.outputs['Green'], pairNode, 'id_mix')
            
            # map inputs
            # 'Diffuse': {'X': 0.03692627, 'Y': 0.029800415, 'Z': 0.012779236}, 'Specular': {'X': 0.48999023, 'Y': 0.48999023, 'Z': 0.48999023}, 'Emissive': {'X': 0, 'Y': 0, 'Z': 0}, 'SheenRate': 0.099975586, 'SheenTint': 0.19995117, 'SheenAptitude': 5, 'Roughness': 0.5, 'Metalness': 0, 'Anisotropy': 0, 'SphereMask': 0, 'ShaderId': 0, 'TileIndex': 12, 'TileAlpha': 1, 'SphereIndex': 0, 'TileMatrix': {'UU': 4.3320312, 'UV': 2.5, 'VU': -50, 'VV': 86.625}}
            evenInputs = self.getRowInputs(even, '_0')
            oddInputs = self.getRowInputs(odd, '_1')
            
            tileIndex0 = even['TileIndex']
            tileIndex1 = odd['TileIndex']
            # lookup tile index textures under 
            # array_textures\chara\common\texture\tile_norm_array\tile_norm_array.{index}.png 
            # array_textures\chara\common\texture\tile_orb_array\tile_orb_array.{index}.png
            # create texture nodes for each if not already in nodes
            # link to pairNode inputs
            tileIndexNormPath0 = path.join(directory, f'array_textures/chara/common/texture/tile_norm_array/tile_norm_array.{tileIndex0}.png')
            tileIndexOrbPath0 = path.join(directory, f'array_textures/chara/common/texture/tile_orb_array/tile_orb_array.{tileIndex0}.png')
            tileIndexNormPath1 = path.join(directory, f'array_textures/chara/common/texture/tile_norm_array/tile_norm_array.{tileIndex1}.png')
            tileIndexOrbPath1 = path.join(directory, f'array_textures/chara/common/texture/tile_orb_array/tile_orb_array.{tileIndex1}.png')
            
            def loadImage(path):
                for img in bpy.data.images:
                    if img.filepath == path:
                        return img
                return bpy.data.images.load(path)
            
            def setupImageNode(path, location, name):
                img = loadImage(path)
                node = material.nodes.new('ShaderNodeTexImage')
                node.image = img
                node.location = location
                node.name = name
                node.image.colorspace_settings.name = 'Non-Color'
                return node
            
            tileIndexNorm0Node = setupImageNode(tileIndexNormPath0, (pairHorizontalPos - 300, node_height), f'tile_norm_array_{tileIndex0}')
            tileIndexOrb0Node = setupImageNode(tileIndexOrbPath0, (pairHorizontalPos - 300, node_height - 300), f'tile_orb_array_{tileIndex0}')
            tileIndexNorm1Node = setupImageNode(tileIndexNormPath1, (pairHorizontalPos - 300, node_height - 600), f'tile_norm_array_{tileIndex1}')
            tileIndexOrb1Node = setupImageNode(tileIndexOrbPath1, (pairHorizontalPos - 300, node_height - 900), f'tile_orb_array_{tileIndex1}')
            
            # material.links.new(tileIndexNorm0Node.outputs['Color'], pairNode.inputs['tile_norm_array_texture_0'])
            # material.links.new(tileIndexOrb0Node.outputs['Color'], pairNode.inputs['tile_orb_array_texture_0'])
            # material.links.new(tileIndexNorm1Node.outputs['Color'], pairNode.inputs['tile_norm_array_texture_1'])
            # material.links.new(tileIndexOrb1Node.outputs['Color'], pairNode.inputs['tile_orb_array_texture_1'])
            linkInputSafe(material, tileIndexNorm0Node.outputs['Color'], pairNode, 'tile_norm_array_texture_0')
            linkInputSafe(material, tileIndexOrb0Node.outputs['Color'], pairNode, 'tile_orb_array_texture_0')
            linkInputSafe(material, tileIndexNorm1Node.outputs['Color'], pairNode, 'tile_norm_array_texture_1')
            linkInputSafe(material, tileIndexOrb1Node.outputs['Color'], pairNode, 'tile_orb_array_texture_1')
                        
            for key, value in evenInputs.items():
                if key in pairNode.inputs:
                    #pairNode.inputs[key].default_value = value
                    setInputSafe(pairNode, key, value)
            for key, value in oddInputs.items():
                if key in pairNode.inputs:
                    #pairNode.inputs[key].default_value = value
                    setInputSafe(pairNode, key, value)
            
            pairHorizontalPos += 600
                    
        # map outputs of pairGroups to pairMixer i.e. pair0 -> tile_norm_array_texture_0, pair1 -> tile_norm_array_texture_1, use red channel of index texture as factor
        # set idx_0 to index of pair0, idx_1 to index of pair1
        # set id_mix to mapIndex
        # if id_mix == idx_0, use pair0, if id_mix == idx_1, use pair1, otherwise use pair0
        prev_pair = pairGroups[0]
        node_height -= 1500
        prev_idx = 0
        
        for i, pair in enumerate(pairGroups):
            if i == 0:
                continue
            pairMixer = material.nodes.new('ShaderNodeGroup')
            pairMixer.node_tree = bpy.data.node_groups['meddle colortablepair_mixer']
            horizontal_pos = pairPositions[i]
            pairMixer.location = (horizontal_pos + 200, node_height)
            #material.links.new(textureSeparate.outputs['Red'], pairMixer.inputs['id_mix'])
            linkInputSafe(material, textureSeparate.outputs['Red'], pairMixer, 'id_mix')
            #pairMixer.inputs['idx_0'].default_value = prev_idx
            #pairMixer.inputs['idx_1'].default_value = i
            setInputSafe(pairMixer, 'idx_0', prev_idx)
            setInputSafe(pairMixer, 'idx_1', i)
            self.mapPairMixer(material, pairMixer, pair, prev_pair)
            prev_pair = pairMixer  
            prev_idx = i

        # connect final mixer to 'meddle character.shpk' inputs
        for output in prev_pair.outputs:
            if output.name in groupNode.inputs:
                material.links.new(output, groupNode.inputs[output.name])
            
        return node_height - 300
    
    def mapPairMixer(self, material, pairMixer, pair, prev_pair):
        for output in prev_pair.outputs:
            mappedName = f'{output.name}_0'
            if mappedName in pairMixer.inputs:
                #material.links.new(output, pairMixer.inputs[mappedName])
                linkInputSafe(material, output, pairMixer, mappedName)
        for output in pair.outputs:
            mappedName = f'{output.name}_1'
            if mappedName in pairMixer.inputs:
                #material.links.new(output, pairMixer.inputs[mappedName])
                linkInputSafe(material, output, pairMixer, mappedName)
        
    
    def fixColorArray(self, color):
        return (color['X'], color['Y'], color['Z'], 1.0)
    
    def getRowInputs(self, row, suffix): 
        diffuse = self.fixColorArray(row['Diffuse'])
        specular = self.fixColorArray(row['Specular'])
        emissive = self.fixColorArray(row['Emissive'])
        sheenRate = row['SheenRate']
        sheenTint = row['SheenTint']
        sheenAptitude = row['SheenAptitude']
        roughness = row['Roughness']
        metalness = row['Metalness']
        anisotropy = row['Anisotropy']
        sphereMask = row['SphereMask']
        shaderId = row['ShaderId']
        tileIndex = row['TileIndex']
        tileAlpha = row['TileAlpha']
        sphereIndex = row['SphereIndex']
        tileMatrix = row['TileMatrix']
        
        return {
            f'diffuse_color{suffix}': diffuse,
            f'specular_color{suffix}': specular,
            f'emissive_color{suffix}': emissive,
            f'sheen_rate{suffix}': sheenRate,
            f'sheen_tint{suffix}': sheenTint,
            f'sheen_aptitude{suffix}': sheenAptitude,
            f'roughness{suffix}': roughness,
            f'metallic{suffix}': metalness,
            f'anisotropy{suffix}': anisotropy,
            f'sphere_mask{suffix}': sphereMask,
            f'shader_id{suffix}': shaderId,
            f'tile_index{suffix}': tileIndex,
            f'tile_alpha{suffix}': tileAlpha,
            f'sphere_index{suffix}': sphereIndex,
            f'tile_matrix{suffix}': tileMatrix
        }

class BoolToFloatMapping:
    def __init__(self, property_name: str, float_dest: str):
        self.property_name = property_name
        self.float_dest = float_dest
        
    def __repr__(self):
        return f"BoolToFloatMapping({self.property_name}, {self.float_dest})"
    
    def apply(self, groupNode, properties):
        if properties[self.property_name]:
            setInputSafe(groupNode, self.float_dest, 1.0)
        else:
            setInputSafe(groupNode, self.float_dest, 0.0)
            
class FloatMapping:
    def __init__(self, property_name: str, float_dest: str):
        self.property_name = property_name
        self.float_dest = float_dest
        
    def __repr__(self):
        return f"FloatMapping({self.property_name}, {self.float_dest})"
    
    def apply(self, groupNode, properties):
        if self.property_name not in properties:
            print(f"Property {self.property_name} not found in material")
            return
        
        def getFixedValueFloat(properties, property_name):
            propVal = properties[property_name]
            if isinstance(propVal, (int, float)):
                return propVal
            val_arr = propVal.to_list()
            return val_arr[0]
        
        #groupNode.inputs[self.float_dest].default_value = getFixedValueFloat(properties, self.property_name)
        setInputSafe(groupNode, self.float_dest, getFixedValueFloat(properties, self.property_name))
        
class FloatArrayIndexedValueMapping:
    def __init__(self, property_name: str, float_dest: str, index: int):
        self.property_name = property_name
        self.float_dest = float_dest
        self.index = index
        
    def __repr__(self):
        return f"FloatArrayIndexedValueMapping({self.property_name}, {self.float_dest}, {self.index})"
    
    def apply(self, groupNode, properties):
        if self.property_name not in properties:
            print(f"Property {self.property_name} not found in material")
            return
        
        def getFixedValueFloat(properties, property_name, index):
            val_arr = properties[property_name].to_list()
            return val_arr[index]
        
        #groupNode.inputs[self.float_dest].default_value = getFixedValueFloat(properties, self.property_name, self.index)
        setInputSafe(groupNode, self.float_dest, getFixedValueFloat(properties, self.property_name, self.index))
        
class UVMapping:
    def __init__(self, uv_map_name: str, uv_dest: str):
        self.uv_map_name = uv_map_name
        self.uv_dest = uv_dest
        
    def __repr__(self):
        return f"UVMapping({self.uv_map_name}, {self.uv_dest})"
    
    def apply(self, material, mesh, groupNode, node_height):
        if mesh is None:
            return node_height - 300
        
        if not isinstance(mesh, bpy.types.Mesh):
            print(f"Object {mesh.name} is not a Mesh")
            return node_height - 300     
                
        if self.uv_map_name not in mesh.uv_layers:
            print(f"UV Map {self.uv_map_name} not found in mesh")
            return node_height - 300
        
        uvMap = mesh.uv_layers[self.uv_map_name]
        uvMapNode = material.nodes.new('ShaderNodeUVMap')
        uvMapNode.uv_map = self.uv_map_name
        uvMapNode.location = (-500, node_height)
        #material.links.new(uvMapNode.outputs['UV'], groupNode.inputs[self.uv_dest])
        linkInputSafe(material, uvMapNode.outputs['UV'], groupNode, self.uv_dest)
        
        return node_height - 300
        
def mapTextureIfExists(material, properties, directory, groupNode, texture_name, dest_name, alpha_dest_name, colorSpace): # returns node height if exists, otherwise none
    if texture_name not in properties:
        return None
    
    pathStr = bpy.path.native_pathsep(properties[texture_name])

    if properties[texture_name] is None:
        return None
    
    # if path contains dummy_ string, skip
    if 'dummy_' in properties[texture_name]:
        return None
    
    # if image loaded already, use that
    img = None
    for image in bpy.data.images:
        if image.filepath == path.join(directory, pathStr):
            img = image
            break
    else:
        img = bpy.data.images.load(path.join(directory, pathStr))
        
    texture = material.nodes.new('ShaderNodeTexImage')
    texture.image = img
    texture.image.colorspace_settings.name = colorSpace
    
    if alpha_dest_name is not None:
        linkInputSafe(material, texture.outputs['Alpha'], groupNode, alpha_dest_name)
        
    if dest_name is not None:
        linkInputSafe(material, texture.outputs['Color'], groupNode, dest_name)
        
    return texture    
        
class BgMapping:
    def __init__(self):
        pass
    
    def __repr__(self):
        return f"BgMapping"
    
    def apply(self, material, mesh, groupNode, properties, directory, node_height):
        color0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerColorMap0_PngCachePath', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB')
        normal0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerNormalMap0_PngCachePath', 'g_SamplerNormalMap0', 'g_SamplerNormalMap0_alpha', 'Non-Color')
        specular0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerSpecularMap0_PngCachePath', 'g_SamplerSpecularMap0', 'g_SamplerSpecularMap0_alpha', 'Non-Color')
        color1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerColorMap1_PngCachePath', 'g_SamplerColorMap1', 'g_SamplerColorMap1_alpha', 'sRGB')
        normal1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerNormalMap1_PngCachePath', 'g_SamplerNormalMap1', 'g_SamplerNormalMap1_alpha', 'Non-Color')
        specular1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerSpecularMap1_PngCachePath', 'g_SamplerSpecularMap1', 'g_SamplerSpecularMap1_alpha', 'Non-Color')
        
        uv0 = None
        uv1 = None
        if 'UVMap' in mesh.uv_layers:
            uv0 = material.nodes.new('ShaderNodeUVMap')
            uv0.uv_map = 'UVMap'
            if color0 is not None:
                material.links.new(uv0.outputs['UV'], color0.inputs['Vector'])
            if normal0 is not None:
                material.links.new(uv0.outputs['UV'], normal0.inputs['Vector'])
            if specular0 is not None:
                material.links.new(uv0.outputs['UV'], specular0.inputs['Vector'])
        if 'UVMap.001' in mesh.uv_layers:
            uv1 = material.nodes.new('ShaderNodeUVMap')
            uv1.uv_map = 'UVMap.001'
            if color1 is not None:
                material.links.new(uv1.outputs['UV'], color1.inputs['Vector'])
            if normal1 is not None:
                material.links.new(uv1.outputs['UV'], normal1.inputs['Vector'])
            if specular1 is not None:
                material.links.new(uv1.outputs['UV'], specular1.inputs['Vector'])
                
        # set node locations
        start_height = node_height
        if color0 is not None:
            color0.location = (-500, node_height)
            node_height -= 300
        if normal0 is not None:
            normal0.location = (-500, node_height)
            node_height -= 300
        if specular0 is not None:
            specular0.location = (-500, node_height)
            node_height -= 300
        if color1 is not None:
            color1.location = (-500, node_height)
            node_height -= 300
        if normal1 is not None:
            normal1.location = (-500, node_height)
            node_height -= 300
        if specular1 is not None:
            specular1.location = (-500, node_height)
            node_height -= 300
            
        node_height = start_height
        if uv0 is not None:
            uv0.location = (-800, node_height)
            node_height -= 300
        if uv1 is not None:
            uv1.location = (-800, node_height)
            node_height -= 300
            
        return node_height

class BgUvScrollMapping:
    def __init__(self):
        pass
    
    def __repr__(self):
        return f"BgUvScrollMapping"
    
    def apply(self, material, mesh, groupNode, properties, directory, node_height):
        color0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerColorMap0_PngCachePath', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB')
        normal0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerNormalMap0_PngCachePath', 'g_SamplerNormalMap0', 'g_SamplerNormalMap0_alpha', 'Non-Color')
        specular0 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerSpecularMap0_PngCachePath', 'g_SamplerSpecularMap0', 'g_SamplerSpecularMap0_alpha', 'Non-Color')
        color1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerColorMap1_PngCachePath', 'g_SamplerColorMap1', 'g_SamplerColorMap1_alpha', 'sRGB')
        normal1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerNormalMap1_PngCachePath', 'g_SamplerNormalMap1', 'g_SamplerNormalMap1_alpha', 'Non-Color')
        specular1 = mapTextureIfExists(material, properties, directory, groupNode, 'g_SamplerSpecularMap1_PngCachePath', 'g_SamplerSpecularMap1', 'g_SamplerSpecularMap1_alpha', 'Non-Color')

        uv0 = None
        uv1 = None
        if 'UVMap' in mesh.uv_layers:
            uv0 = material.nodes.new('ShaderNodeUVMap')
            uv0.uv_map = 'UVMap'
            if color0 is not None:
                material.links.new(uv0.outputs['UV'], color0.inputs['Vector'])
            if normal0 is not None:
                material.links.new(uv0.outputs['UV'], normal0.inputs['Vector'])
            if specular0 is not None:
                material.links.new(uv0.outputs['UV'], specular0.inputs['Vector'])
        if 'UVMap.001' in mesh.uv_layers:
            uv1 = material.nodes.new('ShaderNodeUVMap')
            uv1.uv_map = 'UVMap.001'
            if color1 is not None:
                material.links.new(uv1.outputs['UV'], color1.inputs['Vector'])
            if normal1 is not None:
                material.links.new(uv1.outputs['UV'], normal1.inputs['Vector'])
            if specular1 is not None:
                material.links.new(uv1.outputs['UV'], specular1.inputs['Vector'])    
                
        # spawn meddle scroll group node
        groupNodeData = bpy.data.node_groups.get('meddle scroll')
        if groupNodeData is None:
            print("meddle scroll group not found")
            return node_height - 300
        
        scrollAmount = None
        if '0x9A696A17' in properties:
            scrollAmount = properties['0x9A696A17']
        
        scroll0 = None
        if uv0 is not None:
            scroll0 = material.nodes.new('ShaderNodeGroup')
            scroll0.node_tree = groupNodeData
            # map uv0 to UVMap input
            linkInputSafe(material, uv0.outputs['UV'], scroll0, 'UVMap')
            # set Multiplier on scroll0
            if scrollAmount is not None:
                # scroll0.inputs['Multiplier'].default_value = scrollAmount
                setInputSafe(scroll0, 'Multiplier', [scrollAmount[0] * -1, scrollAmount[1], 0.0])
            if color0 is not None:
                material.links.new(scroll0.outputs['Vector'], color0.inputs['Vector'])
            if normal0 is not None:
                material.links.new(scroll0.outputs['Vector'], normal0.inputs['Vector'])
            if specular0 is not None:
                material.links.new(scroll0.outputs['Vector'], specular0.inputs['Vector'])

        scroll1 = None
        if uv1 is not None:
            scroll1 = material.nodes.new('ShaderNodeGroup')
            scroll1.node_tree = groupNodeData
            # map uv1 to UVMap.001 input
            linkInputSafe(material, uv1.outputs['UV'], scroll1, 'UVMap')
            if scrollAmount is not None:
                # scroll0.inputs['Multiplier'].default_value = scrollAmount
                setInputSafe(scroll1, 'Multiplier', [scrollAmount[2] * -1, scrollAmount[3], 0.0])
            if color1 is not None:
                material.links.new(scroll1.outputs['Vector'], color1.inputs['Vector'])
            if normal1 is not None:
                material.links.new(scroll1.outputs['Vector'], normal1.inputs['Vector'])
            if specular1 is not None:
                material.links.new(scroll1.outputs['Vector'], specular1.inputs['Vector'])
        # set node locations
        def setNodeLocation(node, x, y):
            if node is not None:
                node.location = (x, y) 
                return True
            return False
                
        start_height = node_height
        if setNodeLocation(color0, -500, node_height):
            node_height -= 300
        if setNodeLocation(normal0, -500, node_height):
            node_height -= 300
        if setNodeLocation(specular0, -500, node_height):
            node_height -= 300
        if setNodeLocation(color1, -500, node_height):
            node_height -= 300
        if setNodeLocation(normal1, -500, node_height):
            node_height -= 300
        if setNodeLocation(specular1, -500, node_height):
            node_height -= 300
        
        node_height = start_height
        if uv0 is not None:
            uv0.location = (-900, node_height)
            node_height -= 300
        if uv1 is not None:
            uv1.location = (-900, node_height)
            node_height -= 300
        node_height = start_height
        if scroll0 is not None:
            scroll0.location = (-700, node_height)
            node_height -= 300
        if scroll1 is not None:
            scroll1.location = (-700, node_height)
            node_height -= 300
        
        return node_height
            


def clearMaterialNodes(node_tree: bpy.types.ShaderNodeTree):
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)
        
def createBsdfNode(node_tree: bpy.types.ShaderNodeTree, subsurface_method:str = 'BURLEY'):
    """Creates the principled BSDF node for the material

    Args:
        node_tree (bpy.types.ShaderNodeTree): A reference to the material's node tree
        subsurface_method (str, optional): Which subsurface method to use from BURLEY, RANDOM_WALK and RANDOM_WALK_SKIN. Defaults to 'BURLEY'.

    Returns:
        bsdf_node (bpy.types.ShaderNodeBsdfPrincipled): A reference to the newly created principled BSDF node
    """
    bsdf_node: bpy.types.ShaderNodeBsdfPrincipled = node_tree.nodes.new('ShaderNodeBsdfPrincipled')     # type: ignore
    bsdf_node.width = 300
    try:
        bsdf_node.subsurface_method = subsurface_method
    except:
        print(f"Something went wrong when trying to set subsurface method: \"{subsurface_method}\"")
    return bsdf_node

def mapBsdfOutput(mat: bpy.types.Material, material_output: bpy.types.ShaderNodeOutputMaterial, bsdf_node: bpy.types.ShaderNodeBsdfPrincipled, targetIdentifier: str):
    source = None
    for output in bsdf_node.outputs:
        if output.identifier == 'BSDF':
            source = output
            break
        
    if source is None:
        print("BSDF output not found")
        return
    
    target = None
    for input in material_output.inputs:
        if input.identifier == targetIdentifier:
            target = input
            break
        
    if target is None:
        print("Surface input not found")
        return
    
    if mat.node_tree is None:
        print("Material has no node tree")
        return
    
    mat.node_tree.links.new(source, target)
    
def mapGroupOutputs(mat: bpy.types.Material, group_target: bpy.types.ShaderNode, group_node: bpy.types.ShaderNodeGroup):
    for output in group_node.outputs:
        inputMatch = None
        for input in group_target.inputs:
            if input.identifier == output.name:
                inputMatch = input
                break
            
        if inputMatch is None:
            for input in group_target.inputs:
                if input.name == output.name:
                    inputMatch = input
                    break
                
        if inputMatch is None:
            print(f"Input {output.name} not found in target node")
            continue
        
        if mat.node_tree is None:
            print("Material has no node tree")
            return
        
        mat.node_tree.links.new(output, inputMatch)
        
def mapMappings(mat: bpy.types.Material, mesh, targetNode: bpy.types.ShaderNode,  directory, mappings: list):
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    node_height = 0
    
    for mapping in mappings:
        if isinstance(mapping, PngMapping):
            node_height = mapping.apply(node_tree, targetNode, mat, directory, node_height)
        elif isinstance(mapping, FloatRgbMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, BoolToFloatMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, VertexPropertyMapping):
            node_height = mapping.apply(node_tree, mesh, targetNode, node_height)
        elif isinstance(mapping, FloatValueMapping):
            mapping.apply(targetNode)
        elif isinstance(mapping, FloatRgbaAlphaMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, ColorSetMapping2):
            node_height = mapping.apply(node_tree, targetNode, mat, directory, node_height)
        elif isinstance(mapping, BgMapping):
            node_height = mapping.apply(node_tree, mesh, targetNode, mat, directory, node_height)
        elif isinstance(mapping, BgUvScrollMapping):
            node_height = mapping.apply(node_tree, mesh, targetNode, mat, directory, node_height)
        elif isinstance(mapping, FloatMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, UVMapping):
            node_height = mapping.apply(node_tree, mesh, targetNode, node_height)
        elif isinstance(mapping, FloatArrayIndexedValueMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, FloatHdrMapping):
            mapping.apply(targetNode, mat)
        elif isinstance(mapping, FloatArrayMapping):
            mapping.apply(targetNode, mat)
        else:
            print(f"Unknown mapping type {type(mapping)}")
    
def getEastModePosition(node_tree: bpy.types.ShaderNodeTree):
    east = 0
    for node in node_tree.nodes:
        if node.location[0] > east:
            east = node.location[0]
            
    return east

def handleSkin(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle skin2.shpk"
    base_mappings = [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
        FloatRgbMapping('LipColor', 'Lip Color'),
        FloatRgbaAlphaMapping('LipColor', 'Lip Color Strength'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
        FloatRgbMapping('DecalColor', 'Decal Color'),
        FloatRgbaAlphaMapping('DecalColor', 'Decal Color Strength'),
    ]
    
    node_tree = mat.node_tree 
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
        
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}

    mappings = [FloatValueMapping(1.0, 'IS_FACE')]
    isFace = False
    if 'GetMaterialValue' in mat:
        if mat["GetMaterialValue"] == 'GetMaterialValueBody':
            mappings = []
        elif mat["GetMaterialValue"] == 'GetMaterialValueFace':
            mappings = [FloatValueMapping(1.0, 'IS_FACE'), PngMapping("Decal_PngCachePath", "DecalTexture", None, "Non-Color", "Linear", True, "CLIP")]
            isFace = True
        elif mat["GetMaterialValue"] == 'GetMaterialValueBodyJJM':
            mappings = [FloatValueMapping(1.0, 'IS_HROTHGAR')]
        elif mat["GetMaterialValue"] == 'GetMaterialValueFaceEmissive':
            mappings = [FloatValueMapping(1.0, 'IS_EMISSIVE')]
            
    if 'CategorySkinType' in mat:
        if mat["CategorySkinType"] == 'Body':
            mappings = []
        elif mat["CategorySkinType"] == 'Face':
            mappings = [FloatValueMapping(1.0, 'IS_FACE')]
        elif mat["CategorySkinType"] == 'Hrothgar':
            mappings = [FloatValueMapping(1.0, 'IS_HROTHGAR')]
          
    clearMaterialNodes(node_tree)    
            
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree, 'RANDOM_WALK_SKIN') # Specify Skin subsurface method
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')    
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    
    decalUv_node: bpy.types.ShaderNodeGroup = None
    uvMapNode = None
    if isFace and 'meddle decaluv' in bpy.data.node_groups:
        decalUv_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')     # type: ignore
        decalUv_node.node_tree = bpy.data.node_groups['meddle decaluv']    # type: ignore
        decalUv_node.width = 300
        # map UVMap.001 to group_node.inputs['UVMap1']
        # map FacePaintReversed to group_node.inputs['FacePaintReversed']
        if 'UVMap.001' in mesh.uv_layers:
            # spawn UVMap node
            uvMapNode = node_tree.nodes.new('ShaderNodeUVMap')
            uvMapNode.uv_map = 'UVMap.001'   # type: ignore
            uvMapNode.location = (-500, 300)
            # link UVMap node to devalUv_node
            linkInputSafe(node_tree, uvMapNode.outputs['UV'], decalUv_node, 'UVMap1')
        decalMappings = [FloatMapping('FacePaintUVMultiplier', 'UVMultiplier'), FloatMapping('FacePaintUVOffset', 'UVOffset')]     
        mapMappings(mat, mesh, decalUv_node, directory, decalMappings)   

        decalTextureNode = None
        for node in node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.name == 'Decal_PngCachePath':
                decalTextureNode = node
                break
            
        if decalTextureNode is not None:
            linkInputSafe(node_tree, decalUv_node.outputs['DecalUV'], decalTextureNode, 'Vector')
                
        
    
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 700, 300)
    material_output.location = (east + 1100, 300)
    if decalUv_node is not None:
        decalUv_node.location = (east - 600, 300)
    if uvMapNode is not None:
        uvMapNode.location = (east - 900, 300)
    return {'FINISHED'}
    
def handleHair(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle hair2.shpk"
    base_mappings = [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
    ]
    
    node_tree = mat.node_tree 
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
        
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = [FloatValueMapping(1.0, 'IS_FACE')]
    if 'GetSubColor' in mat:
        if mat["GetSubColor"] == 'GetSubColorFace':
            mappings = [FloatValueMapping(1.0, 'IS_FACE')]
        if mat["GetSubColor"] == 'GetSubColorHair':
            mappings = []
            
    if 'CategoryHairType' in mat:
        if mat["CategoryHairType"] == 'Face':
            mappings = [FloatValueMapping(1.0, 'IS_FACE')]
        if mat["CategoryHairType"] == 'Hair':
            mappings = []
            
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)

    try:
        bsdf_node.inputs.get("Transmission Weight").default_value = 0.01
        bsdf_node.inputs.get("Subsurface Scale").default_value = 0.15
        node_tree.links.new(group_node.outputs.get("Base Color"), bsdf_node.inputs.get("Subsurface Radius"))
    except Exception as e:
        print(f"Exception occured when setting some hair inputs: {e}")

    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 700, 300)
    material_output.location = (east + 1100, 300)
    return {'FINISHED'}

def handleIris(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle iris2.shpk"
    base_mappings = [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', None, 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        VertexPropertyMapping('Color', 'vertex_color', None, (1.0, 0, 0, 1)),
        FloatRgbMapping('g_WhiteEyeColor', 'g_WhiteEyeColor'),
        FloatRgbMapping('LeftIrisColor', 'left_iris_color'),
        FloatRgbMapping('RightIrisColor', 'right_iris_color'),
        FloatRgbaAlphaMapping('LeftIrisColor', 'left_iris_limbal_ring_intensity'),
        FloatRgbaAlphaMapping('RightIrisColor', 'right_iris_limbal_ring_intensity'),
        FloatRgbMapping('g_IrisRingColor', 'g_IrisRingColor'),
        FloatMapping('g_IrisRingEmissiveIntensity', 'g_IrisRingEmissiveIntensity'),
        UVMapping('UVMap', 'UVMap'),
        FloatArrayIndexedValueMapping('unk_LimbalRingRange', 'unk_LimbalRingRange_start', 0),
        FloatArrayIndexedValueMapping('unk_LimbalRingRange', 'unk_LimbalRingRange_end', 1),
        FloatArrayIndexedValueMapping('unk_LimbalRingFade', 'unk_LimbalRingFade_start', 0),
        FloatArrayIndexedValueMapping('unk_LimbalRingFade', 'unk_LimbalRingFade_end', 1),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300

    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 700, 300)
    material_output.location = (east + 1100, 300)
    return {'FINISHED'}

def handleCharacter(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle character.shpk"
    base_mappings = [
        ColorSetMapping2(),
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    if 'GetValues' in mat:
        if mat["GetValues"] == 'GetValuesCompatibility':
            mappings = [FloatValueMapping(1.0, 'IS_COMPATIBILITY')]
            
    if 'GetValuesTextureType' in mat:
        if mat["GetValuesTextureType"] == 'Compatibility':
            mappings = [FloatValueMapping(1.0, 'IS_COMPATIBILITY')]
            
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300

    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleCharacterSimple(mat: bpy.types.Material, mesh, directory, shader_package: str):
    group_name = "meddle character.shpk"
    is_legacy = shader_package == 'characterlegacy.shpk'
    is_legacy_value = 1.0 if is_legacy else 0.0
    is_stocking = shader_package == 'characterstockings.shpk'
    is_stocking_value = 1.0 if is_stocking else 0.0
    base_mappings = [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB', optional=True),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        FloatValueMapping(is_legacy_value, 'IS_LEGACY'),
        FloatValueMapping(is_stocking_value, 'IS_STOCKING'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    if 'GetValues' in mat:
        if mat["GetValues"] == 'GetValuesCompatibility':
            mappings.extend([FloatValueMapping(1.0, 'IS_COMPATIBILITY')])
            
    if 'GetValuesTextureType' in mat:
        if mat["GetValuesTextureType"] == 'Compatibility':
            mappings.extend([FloatValueMapping(1.0, 'IS_COMPATIBILITY')])
            
    if 'SkinColor' in mat:
        mappings.extend([FloatRgbMapping('SkinColor', 'SkinColor')])
            
    def setupRamp(node_height, material, name): 
        ramp = None
        for node in material.nodes:
            if node.name == name:
                ramp = node
                break
            
        if ramp is None:
            ramp = material.nodes.new('ShaderNodeValToRGB')
            
        ramp.location = (0, node_height)
        ramp.name = name
        ramp.label = name
        ramp.color_ramp.interpolation = 'CONSTANT'
        
        while len(ramp.color_ramp.elements) > 1:
            ramp.color_ramp.elements.remove(ramp.color_ramp.elements[0])
            
        return ramp
    
    def mapRamp(rampA, rampB, rows, rowProp, type):
        def getValueForType(row, type):
            if type == 'XYZ':
                return (row[rowProp]['X'], row[rowProp]['Y'], row[rowProp]['Z'], 1.0)
            elif type == 'Float':
                return (row[rowProp], row[rowProp], row[rowProp], 1.0)
            elif type == 'FloatPct':
                return (row[rowProp] / 100, row[rowProp] / 100, row[rowProp] / 100, 1.0)
            
        odds = []
        evens = []
        
        for i, row in enumerate(rows):
            if i % 2 == 0:
                evens.append(row)
            else:
                odds.append(row)
                
        for i, row in enumerate(evens):
            if rowProp not in row:
                print(f"Row {i} does not have property {rowProp}")
                continue
            pos = i / len(evens)
            if i == 0:
                rampA.color_ramp.elements[0].position = pos
                rampA.color_ramp.elements[0].color = getValueForType(row, type)
            else:
                elementA = rampA.color_ramp.elements.new(pos)
                elementA.color = getValueForType(row, type)
                
        for i, row in enumerate(odds):
            if rowProp not in row:
                print(f"Row {i} does not have property {rowProp}")
                continue
            pos = i / len(odds)
            if i == 0:
                rampB.color_ramp.elements[0].position = pos
                rampB.color_ramp.elements[0].color = getValueForType(row, type)
            else:
                element = rampB.color_ramp.elements.new(pos)
                element.color = getValueForType(row, type)
    
    if 'ColorTable' not in mat:
        print("ColorTable prop not found")
        return {'CANCELLED'}
    
    colorSet = mat['ColorTable']
    if 'ColorTable' not in colorSet:
        print("ColorTable not found in colorset")
        return {'CANCELLED'}
    
    colorTable = colorSet['ColorTable']
    
    if 'Rows' not in colorTable:
        print("Rows not found in colorTable")
        return {'CANCELLED'}
    
    rows = colorTable['Rows']
    
    if len(rows) == 0:
        print("No rows found in colorTable")
        return {'CANCELLED'}
    
    clearMaterialNodes(node_tree)
    indexMapping = PngMapping('g_SamplerIndex_PngCachePath', None, None, 'Non-Color', 'Closest')    
    indexMapping.apply(node_tree, None, mat, directory, 300)
        
    indexTexture = None
    for node in node_tree.nodes:
        if node.name == 'g_SamplerIndex_PngCachePath':
            indexTexture = node
            break
        
    if indexTexture is None:
        print("Index texture not found")
        return {'CANCELLED'}
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    
    colorRampA = setupRamp(0, node_tree, 'ColorRampA')
    colorRampB = setupRamp(-300, node_tree, 'ColorRampB')
    specularRampA = setupRamp(-600, node_tree, 'SpecularRampA')
    specularRampB = setupRamp(-900, node_tree, 'SpecularRampB')
    emissionRampA = setupRamp(-1200, node_tree, 'EmissionRampA')
    emissionRampB = setupRamp(-1500, node_tree, 'EmissionRampB')
    metalnessRampA = setupRamp(-1800, node_tree, 'MetalnessRampA')
    metalnessRampB = setupRamp(-2100, node_tree, 'MetalnessRampB')
    roughnessRampA = setupRamp(-2400, node_tree, 'RoughnessRampA')
    roughnessRampB = setupRamp(-2700, node_tree, 'RoughnessRampB')
    glossRampA = setupRamp(-3000, node_tree, 'GlossRampA')
    glossRampB = setupRamp(-3300, node_tree, 'GlossRampB')
    specStrengthRampA = setupRamp(-3600, node_tree, 'SpecStrengthRampA')
    specStrengthRampB = setupRamp(-3900, node_tree, 'SpecStrengthRampB')
    sheenRateRampA = setupRamp(-4200, node_tree, 'SheenRateRampA')
    sheenRateRampB = setupRamp(-4500, node_tree, 'SheenRateRampB')
    sheenTintRampA = setupRamp(-4800, node_tree, 'SheenTintRampA')
    sheenTintRampB = setupRamp(-5100, node_tree, 'SheenTintRampB')
    sheenAptitudeRampA = setupRamp(-5400, node_tree, 'SheenAptitudeRampA')
    sheenAptitudeRampB = setupRamp(-5700, node_tree, 'SheenAptitudeRampB')
    anisotropyRampA = setupRamp(-6000, node_tree, 'AnisotropyRampA')
    anisotropyRampB = setupRamp(-6300, node_tree, 'AnisotropyRampB')
    mapRamp(colorRampA, colorRampB, rows, 'Diffuse', 'XYZ')
    mapRamp(specularRampA, specularRampB, rows, 'Specular', 'XYZ')
    mapRamp(emissionRampA, emissionRampB, rows, 'Emissive', 'XYZ')
    mapRamp(metalnessRampA, metalnessRampB, rows, 'Metalness', 'Float')
    mapRamp(roughnessRampA, roughnessRampB, rows, 'Roughness', 'Float')
    mapRamp(glossRampA, glossRampB, rows, 'GlossStrength', 'FloatPct')
    mapRamp(specStrengthRampA, specStrengthRampB, rows, 'SpecularStrength', 'Float')
    mapRamp(sheenRateRampA, sheenRateRampB, rows, 'SheenRate', 'Float')
    mapRamp(sheenTintRampA, sheenTintRampB, rows, 'SheenTint', 'Float')
    mapRamp(sheenAptitudeRampA, sheenAptitudeRampB, rows, 'SheenAptitude', 'Float')
    mapRamp(anisotropyRampA, anisotropyRampB, rows, 'Anisotropy', 'Float')
    
    textureSeparate: bpy.types.ShaderNodeSeparateColor = node_tree.nodes.new('ShaderNodeSeparateColor')     # type: ignore
    textureSeparate.location = (-200, -300)
    node_tree.links.new(indexTexture.outputs['Color'], textureSeparate.inputs['Color'])
    
    allRamps = [
        colorRampA, colorRampB, 
        specularRampA, specularRampB, 
        emissionRampA, emissionRampB, 
        metalnessRampA, metalnessRampB, 
        roughnessRampA, roughnessRampB,
        glossRampA, glossRampB,
        specStrengthRampA, specStrengthRampB,
        sheenRateRampA, sheenRateRampB,
        sheenTintRampA, sheenTintRampB,
        sheenAptitudeRampA, sheenAptitudeRampB,
        anisotropyRampA, anisotropyRampB
    ]
    
    for ramp in allRamps:
        node_tree.links.new(textureSeparate.outputs['Red'], ramp.inputs['Fac'])
        
    pair_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    pair_node.node_tree = bpy.data.node_groups["meddle colortablepair"]     # type: ignore
    pair_node.width = 300
    
    node_tree.links.new(textureSeparate.outputs['Green'], pair_node.inputs['id_mix'])
    node_tree.links.new(colorRampA.outputs['Color'], pair_node.inputs['diffuse_color_0'])
    node_tree.links.new(colorRampB.outputs['Color'], pair_node.inputs['diffuse_color_1'])
    node_tree.links.new(specularRampA.outputs['Color'], pair_node.inputs['specular_color_0'])
    node_tree.links.new(specularRampB.outputs['Color'], pair_node.inputs['specular_color_1'])
    node_tree.links.new(emissionRampA.outputs['Color'], pair_node.inputs['emissive_color_0'])
    node_tree.links.new(emissionRampB.outputs['Color'], pair_node.inputs['emissive_color_1'])
    node_tree.links.new(glossRampA.outputs['Color'], pair_node.inputs['gloss_strength_0'])
    node_tree.links.new(glossRampB.outputs['Color'], pair_node.inputs['gloss_strength_1'])
    node_tree.links.new(specStrengthRampA.outputs['Color'], pair_node.inputs['specular_strength_0'])
    node_tree.links.new(specStrengthRampB.outputs['Color'], pair_node.inputs['specular_strength_1'])
    node_tree.links.new(metalnessRampA.outputs['Color'], pair_node.inputs['metallic_0'])
    node_tree.links.new(metalnessRampB.outputs['Color'], pair_node.inputs['metallic_1'])
    node_tree.links.new(roughnessRampA.outputs['Color'], pair_node.inputs['roughness_0'])
    node_tree.links.new(roughnessRampB.outputs['Color'], pair_node.inputs['roughness_1'])
    node_tree.links.new(sheenRateRampA.outputs['Color'], pair_node.inputs['sheen_rate_0'])
    node_tree.links.new(sheenRateRampB.outputs['Color'], pair_node.inputs['sheen_rate_1'])
    node_tree.links.new(sheenTintRampA.outputs['Color'], pair_node.inputs['sheen_tint_0'])
    node_tree.links.new(sheenTintRampB.outputs['Color'], pair_node.inputs['sheen_tint_1'])
    node_tree.links.new(sheenAptitudeRampA.outputs['Color'], pair_node.inputs['sheen_apt_0'])
    node_tree.links.new(sheenAptitudeRampB.outputs['Color'], pair_node.inputs['sheen_apt_1'])
    node_tree.links.new(anisotropyRampA.outputs['Color'], pair_node.inputs['anisotropy_0'])
    node_tree.links.new(anisotropyRampB.outputs['Color'], pair_node.inputs['anisotropy_1'])
    mapGroupOutputs(mat, group_node, pair_node)
    
    east = getEastModePosition(node_tree)
    pair_node.location = (east + 300, 300)
    group_node.location = (east + 700, 300)
    bsdf_node.location = (east + 1100, 300)
    material_output.location = (east + 1500, 300)
    
    return {'FINISHED'}
    

class FloatHdrMapping:
    def __init__(self, identifier: str, destRgb: str, destMagnitude: str):
        self.identifier = identifier
        self.destRgb = destRgb
        self.destMagnitude = destMagnitude
        
    def apply(self, targetNode: bpy.types.ShaderNode, mat: bpy.types.Material):
        if self.identifier not in mat:
            return
        
        if targetNode is None:
            return
        
        value = mat[self.identifier]
        magnitude = 0
        for val in value:
            if val > magnitude:
                magnitude = val
                
        if magnitude == 0:
            return
                
        adjustedValue = [val / magnitude for val in value]
        
        if len(adjustedValue) == 3:
            adjustedValue.append(1.0)
        
        #targetNode.inputs[self.destRgb].default_value = adjustedValue
        #targetNode.inputs[self.destMagnitude].default_value = magnitude
        setInputSafe(targetNode, self.destRgb, adjustedValue)
        setInputSafe(targetNode, self.destMagnitude, magnitude)

def handleBg(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle bg.shpk"
    base_mappings = [
        BgMapping(),
        FloatRgbMapping('g_DiffuseColor', 'g_DiffuseColor'),
        FloatHdrMapping('g_EmissiveColor', 'g_EmissiveColor', 'g_EmissiveColor_magnitude'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300

    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 200, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleBgUvScroll(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle bg.shpk"
    base_mappings = [
        BgUvScrollMapping(),
        FloatRgbMapping('g_DiffuseColor', 'g_DiffuseColor'),
        FloatHdrMapping('g_EmissiveColor', 'g_EmissiveColor', 'g_EmissiveColor_magnitude'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300

    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 200, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleCharacterTattoo(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle charactertattoo.shpk"
    base_mappings = [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        FloatRgbMapping('OptionColor', 'OptionColor'),
        # DecalColor mapping to g_DecalColor <- not implemented
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300

    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 700, 300)
    material_output.location = (east + 1100, 300)
    return {'FINISHED'}

def handleCharacterOcclusion(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle characterocclusion.shpk"
    base_mappings = [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 700, 300)
    material_output.location = (east + 1100, 300)
    return {'FINISHED'}

def handleBgProp(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle bgprop.shpk"
    base_mappings = [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleBgColorChange(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle bgcolorchange.shpk"
    base_mappings = [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', 'g_SamplerNormalMap0_alpha', 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
        FloatRgbMapping('StainColor', 'StainColor'),
        FloatRgbMapping('g_DiffuseColor', 'g_DiffuseColor'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleLightShaft(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle lightshaft.shpk"
    base_mappings = [
        PngMapping('g_Sampler0_PngCachePath', 'g_Sampler0', 'g_Sampler0_alpha', 'sRGB'),
        PngMapping('g_Sampler1_PngCachePath', 'g_Sampler1', 'g_Sampler1_alpha', 'sRGB'),
        FloatRgbMapping('g_Color', 'g_Color'),
        VertexPropertyMapping('Color', 'vertex_color', 'vertex_alpha'),        
        FloatArrayMapping('g_TexAnim', 'g_TexAnim', 3),
        FloatArrayMapping('g_TexU', 'g_TexU', 3),
        FloatArrayMapping('g_TexV', 'g_TexV', 3),
        FloatArrayMapping('g_Ray', 'g_Ray', 3),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore

    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)    
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleCrystal(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle crystal.shpk"
    base_mappings = [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', None, 'sRGB'),
        PngMapping('g_SamplerEnvMap', 'g_SamplerEnvMap', None, 'Non-Color'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    return {'FINISHED'}

def handleWater(mat: bpy.types.Material, mesh, directory):
    group_name = "meddle water.shpk"
    base_mappings = [
        FloatRgbMapping('0xD315E728', 'unk_WaterColor'),
        FloatRgbMapping('unk_WaterColor', 'unk_WaterColor'),
        
        FloatRgbMapping('g_RefractionColor', 'g_RefractionColor'),
        FloatRgbMapping('g_WhitecapColor', 'g_WhitecapColor'),     
        FloatMapping('g_Transparency', 'g_Transparency'),        
        PngMapping('g_SamplerWaveMap_PngCachePath', 'g_SamplerWaveMap', 'g_SamplerWaveMap_alpha', 'Non-Color'), # water river
        PngMapping('g_SamplerWaveMap1_PngCachePath', 'g_SamplerWaveMap1', 'g_SamplerWaveMap1_alpha', 'Non-Color'), # water only
        PngMapping('g_SamplerWhitecapMap_PngCachePath', 'g_SamplerWhitecapMap', 'g_SamplerWhitecapMap_alpha', 'Non-Color'), # water river
    ]
    
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    if group_name not in bpy.data.node_groups:
        print(f"Node group {group_name} not found")
        return {'CANCELLED'}
    
    mappings = []
    
    clearMaterialNodes(node_tree)
    
    material_output: bpy.types.ShaderNodeOutputMaterial = node_tree.nodes.new('ShaderNodeOutputMaterial')     # type: ignore
    
    group_node: bpy.types.ShaderNodeGroup = node_tree.nodes.new('ShaderNodeGroup')      # type: ignore
    
    group_node.node_tree = bpy.data.node_groups[group_name]     # type: ignore
    group_node.width = 300
    
    bsdf_node = createBsdfNode(node_tree)
    mapBsdfOutput(mat, material_output, bsdf_node, 'Surface')
    mapGroupOutputs(mat, bsdf_node, group_node)
    mapMappings(mat, mesh, group_node, directory, base_mappings + mappings)
    east = getEastModePosition(node_tree)
    group_node.location = (east + 300, 300)
    bsdf_node.location = (east + 600, 300)
    material_output.location = (east + 1000, 300)
    
    return {'FINISHED'}
        
def spawnFallbackTextures(mat: bpy.types.Material, directory):
    # check props for _PngCachePath, spawn image texture nodes for each
    node_tree = mat.node_tree
    if node_tree is None:
        print(f"Material {mat.name} has no node tree")
        return {'CANCELLED'}
    
    clearMaterialNodes(node_tree)
    node_height = 0
    
    try:
        for prop in mat.keys():
            if prop.endswith('_PngCachePath'):
                print(f"Spawning texture node for {prop}")            
                mapping = PngMapping(prop, None, None, 'sRGB', optional=True)
                node_height = mapping.apply(node_tree, None, mat, directory, node_height)
                
    except Exception as e:
        print(f"Error spawning texture nodes: {e}")
        return {'CANCELLED'}
            
    return {'FINISHED'}
    
def handleShader(mat: bpy.types.Material, mesh, object, deduplicate: bool, directory):
    if mat is None:
        return {'CANCELLED'}
    
    shader_package = mat["ShaderPackage"]
    if shader_package is None:
        return {'CANCELLED'}
    
    print(f"Handling shader package {shader_package} on material {mat.name}")
    
    if shader_package == 'skin.shpk':
        handleSkin(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package == 'hair.shpk':
        handleHair(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package == 'iris.shpk':
        handleIris(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package == 'charactertattoo.shpk':
        handleCharacterTattoo(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package == 'characterocclusion.shpk':
        handleCharacterOcclusion(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package in ('character.shpk', 'characterlegacy.shpk', 'characterscroll.shpk', 
                          'characterglass.shpk', 'characterinc.shpk', 'characterstockings.shpk'):
        handleCharacterSimple(mat, mesh, directory, shader_package)
        return {'FINISHED'}
    
    if shader_package == 'bgcolorchange.shpk':
        handleBgColorChange(mat, mesh, directory)
        return {'FINISHED'}
    
    if shader_package in ('water.shpk', 'river.shpk'):
        handleWater(mat, mesh, directory)
        return {'FINISHED'}
    
    # check if material exists already in scene by same name
    # note: any materials with additional inputs outside the .mtrl values, should not be deduplicated as they should be unique to the object
    if 'Material' in mat and deduplicate:
        for obj in (o for o in bpy.data.objects if o.type == 'MESH'):
            for slot in obj.material_slots:
                if slot.material is None:
                    continue
                if 'Material' in slot.material and slot.material['Material'] == mat['Material'] and 'MeddleApplied' in slot.material and slot.material['MeddleApplied'] == True:
                    # there is another object in the scene with the same material as this. Replace object material with the one in the scene
                    for objSlot in object.material_slots:
                        if objSlot.material.name == mat.name:
                            objSlot.material = slot.material
                            print(f"Material {mat.name} already exists in scene, using existing material")
                            return {'FINISHED'}
                
    
    if shader_package == 'bg.shpk' or shader_package == 'bgcrestchange.shpk':
        handleBg(mat, mesh, directory)
        mat['MeddleApplied'] = True
        return {'FINISHED'}
    
    if shader_package == 'bguvscroll.shpk':
        handleBgUvScroll(mat, mesh, directory)
        mat['MeddleApplied'] = True
        return {'FINISHED'}
    
    if shader_package == 'lightshaft.shpk':
        handleLightShaft(mat, mesh, directory)
        mat['MeddleApplied'] = True
        return {'FINISHED'}
    
    if shader_package == 'bgprop.shpk':
        handleBgProp(mat, mesh, directory)
        mat['MeddleApplied'] = True
        return {'FINISHED'}
    
    if shader_package == 'crystal.shpk':
        handleCrystal(mat, mesh, directory)
        mat['MeddleApplied'] = True
        return {'FINISHED'}
    
    spawnFallbackTextures(mat, directory)
    print(f"No suitable shader found for {shader_package} on material {mat.name}")
    return {'CANCELLED'}
