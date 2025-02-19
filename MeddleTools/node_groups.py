import bpy
from os import path


class NodeGroup:
    def __init__(self, name: str, mapping_definitions: list):
        self.name = name
        self.mapping_definitions = mapping_definitions
        
class PngMapping:
    def __init__(self, property_name: str, color_dest: str, alpha_dest: str | None, color_space: str, interpolation: str = 'Linear'):
        self.property_name = property_name
        self.color_dest = color_dest
        self.alpha_dest = alpha_dest
        self.color_space = color_space
        self.interpolation = interpolation
        
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
            if img.filepath == path.join(directory, pathStr):
                texture.image = img
                break
        else:        
            if not path.exists(path.join(directory, pathStr)):
                print(f"Texture {path.join(directory, pathStr)} not found")
                return node_height - 300
            texture.image = bpy.data.images.load(path.join(directory, pathStr))
        texture.location = (-500, node_height)
        texture.image.colorspace_settings.name = self.color_space
        texture.interpolation = self.interpolation
        
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
            
        if len(value_arr) == 3:
            value_arr.append(1.0)
            
        groupNode.inputs[self.color_dest].default_value = value_arr[3]
        
class FloatValueMapping:
    def __init__(self, value: float, property_dest: str):
        self.value = value
        self.property_dest = property_dest
        
    def __repr__(self):
        return f"FloatValueMappping({self.value}, {self.property_dest})"
    
    def apply(self, groupNode):                        
        groupNode.inputs[self.property_dest].default_value = self.value           
            
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
        pathStr = properties[self.index_texture_name]
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
        material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])
        
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
            material.links.new(textureSeparate.outputs['Green'], pairNode.inputs['id_mix'])
            
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
            
            material.links.new(tileIndexNorm0Node.outputs['Color'], pairNode.inputs['tile_norm_array_texture_0'])
            material.links.new(tileIndexOrb0Node.outputs['Color'], pairNode.inputs['tile_orb_array_texture_0'])
            material.links.new(tileIndexNorm1Node.outputs['Color'], pairNode.inputs['tile_norm_array_texture_1'])
            material.links.new(tileIndexOrb1Node.outputs['Color'], pairNode.inputs['tile_orb_array_texture_1'])
                        
            for key, value in evenInputs.items():
                if key in pairNode.inputs:
                    pairNode.inputs[key].default_value = value
            for key, value in oddInputs.items():
                if key in pairNode.inputs:
                    pairNode.inputs[key].default_value = value
            
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
            material.links.new(textureSeparate.outputs['Red'], pairMixer.inputs['id_mix'])
            pairMixer.inputs['idx_0'].default_value = prev_idx
            pairMixer.inputs['idx_1'].default_value = i
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
                material.links.new(output, pairMixer.inputs[mappedName])
        for output in pair.outputs:
            mappedName = f'{output.name}_1'
            if mappedName in pairMixer.inputs:
                material.links.new(output, pairMixer.inputs[mappedName])
        
    
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
        
            
class ColorSetMapping:
    def __init__(self, property_name: str, id_texture_name: str, color_ramp_a: str, color_ramp_b: str, specular_ramp_a: str, specular_ramp_b: str, color_a_dest: str, color_b_dest: str, specular_a_dest: str, specular_b_dest: str, index_g_dest: str):
        self.property_name = property_name
        self.id_texture_name = id_texture_name
        self.color_ramp_a = color_ramp_a
        self.color_ramp_b = color_ramp_b
        self.specular_ramp_a = specular_ramp_a
        self.specular_ramp_b = specular_ramp_b
        self.color_a_dest = color_a_dest
        self.color_b_dest = color_b_dest
        self.specular_a_dest = specular_a_dest
        self.specular_b_dest = specular_b_dest
        self.index_g_dest = index_g_dest
        
    def __repr__(self):
        return f"ColorSetMapping({self.property_name})"
    
    
    def setup_ramp(self, node_height, material, ramp_name):
        ramp = None
        if ramp_name not in material.nodes:
            ramp = material.nodes.new('ShaderNodeValToRGB')
            ramp.name = ramp_name
            ramp.location = (0, node_height)
            ramp.color_ramp.interpolation = 'CONSTANT'
        else:
            ramp = material.nodes[ramp_name]
        
            
        # clear existing elements, leaving last one
        while len(ramp.color_ramp.elements) > 1:
            ramp.color_ramp.elements.remove(ramp.color_ramp.elements[0])
            
        return ramp
    
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
            if img.filepath == path.join(directory, pathStr):
                texture.image = img
                break
        else:        
            if not path.exists(path.join(directory, pathStr)):
                print(f"Texture {path.join(directory, pathStr)} not found")
                return node_height - 300
            texture.image = bpy.data.images.load(path.join(directory, pathStr))
        texture.location = (-500, node_height)
        texture.name = self.id_texture_name
        texture.label = self.id_texture_name
        texture.image.colorspace_settings.name = 'Non-Color'
        texture.interpolation = 'Closest'
        
        
        # separate color
        textureSeparate = material.nodes.new('ShaderNodeSeparateColor')
        textureSeparate.location = (-300, node_height)
        material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])        
        material.links.new(texture.outputs['Color'], textureSeparate.inputs['Color'])
        
        # create colorRamp if it doesn't exist
        colorRampA = self.setup_ramp(node_height - 300, material, self.color_ramp_a)            
        colorRampB = self.setup_ramp(node_height - 600, material, self.color_ramp_b)
            
        # create specularRamp if it doesn't exist
        specularRampA = self.setup_ramp(node_height - 900, material, self.specular_ramp_a)            
        specularRampB = self.setup_ramp(node_height - 1200, material, self.specular_ramp_b)
        
        odds = []
        evens = []
        for i, row in enumerate(rows):
            if i % 2 == 0:
                evens.append(row)
            else:
                odds.append(row)
                
        for i, row in enumerate(evens):
            pos = i / len(evens)
            if i == 0:
                colorRampA.color_ramp.elements[0].position = pos
                colorRampA.color_ramp.elements[0].color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
                specularRampA.color_ramp.elements[0].position = pos
                specularRampA.color_ramp.elements[0].color = (row['Specular']['X'], row['Specular']['Y'], row['Specular']['Z'], 1.0)
            else:
                colorElementA = colorRampA.color_ramp.elements.new(pos)
                colorElementA.color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
                specularElementA = specularRampA.color_ramp.elements.new(pos)
                specularElementA.color = (row['Specular']['X'], row['Specular']['Y'], row['Specular']['Z'], 1.0)
                
                
        for i, row in enumerate(odds):
            pos = i / len(odds)
            if i == 0:
                colorRampB.color_ramp.elements[0].position = pos
                colorRampB.color_ramp.elements[0].color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)
                specularRampB.color_ramp.elements[0].position = pos
                specularRampB.color_ramp.elements[0].color = (row['Specular']['X'], row['Specular']['Y'], row['Specular']['Z'], 1.0)
            else:
                element = colorRampB.color_ramp.elements.new(pos)
                element.color = (row['Diffuse']['X'], row['Diffuse']['Y'], row['Diffuse']['Z'], 1.0)  
                specularElementB = specularRampB.color_ramp.elements.new(pos)
                specularElementB.color = (row['Specular']['X'], row['Specular']['Y'], row['Specular']['Z'], 1.0)
                
        material.links.new(textureSeparate.outputs['Red'], colorRampA.inputs['Fac'])
        material.links.new(textureSeparate.outputs['Red'], colorRampB.inputs['Fac'])
        material.links.new(textureSeparate.outputs['Red'], specularRampA.inputs['Fac'])
        material.links.new(textureSeparate.outputs['Red'], specularRampB.inputs['Fac'])
        material.links.new(colorRampA.outputs['Color'], groupNode.inputs[self.color_a_dest])
        material.links.new(colorRampB.outputs['Color'], groupNode.inputs[self.color_b_dest])
        material.links.new(specularRampA.outputs['Color'], groupNode.inputs[self.specular_a_dest])
        material.links.new(specularRampB.outputs['Color'], groupNode.inputs[self.specular_b_dest])
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
            val_arr = properties[property_name].to_list()
            return val_arr[0]
        
        groupNode.inputs[self.float_dest].default_value = getFixedValueFloat(properties, self.property_name)
        
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
        
        groupNode.inputs[self.float_dest].default_value = getFixedValueFloat(properties, self.property_name, self.index)

        
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
        material.links.new(uvMapNode.outputs['UV'], groupNode.inputs[self.uv_dest])
        
        return node_height - 300
        
            
class BgMapping:
    def __init__(self):
        pass
    
    def __repr__(self):
        return f"BgMapping"
    
    def apply(self, material, mesh, groupNode, properties, directory, node_height):
        # connect 0 maps.
        # only connect vertex property mapping IF 1 maps exist
        def mapTextureIfExists(texture_name, dest_name, alpha_dest_name, colorSpace): # returns node height if exists, otherwise none
            if texture_name not in properties:
                return None
            
            if properties[texture_name] is None:
                return None
            
            # if path contains dummy_ string, skip
            if 'dummy_' in properties[texture_name]:
                return None
            
            # if image loaded already, use that
            img = None
            for image in bpy.data.images:
                if image.filepath == path.join(directory, properties[texture_name]):
                    img = image
                    break
            else:
                img = bpy.data.images.load(path.join(directory, properties[texture_name]))
                
            texture = material.nodes.new('ShaderNodeTexImage')
            texture.image = img
            texture.location = (-500, node_height)
            texture.image.colorspace_settings.name = colorSpace
            
            if alpha_dest_name is not None:
                material.links.new(texture.outputs['Alpha'], groupNode.inputs[alpha_dest_name])
                
            if dest_name is not None:
                material.links.new(texture.outputs['Color'], groupNode.inputs[dest_name])
                
            return node_height - 300
        
        should_connect_vertex = False
        new_height = mapTextureIfExists('g_SamplerColorMap0_PngCachePath', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB')
        if new_height is not None:
            node_height = new_height
            
        new_height = mapTextureIfExists('g_SamplerNormalMap0_PngCachePath', 'g_SamplerNormalMap0', None, 'Non-Color')
        if new_height is not None:
            node_height = new_height
            
        new_height = mapTextureIfExists('g_SamplerSpecularMap0_PngCachePath', 'g_SamplerSpecularMap0', None, 'Non-Color')
        if new_height is not None:
            node_height = new_height
            
        new_height = mapTextureIfExists('g_SamplerColorMap1_PngCachePath', 'g_SamplerColorMap1', 'g_SamplerColorMap1_alpha', 'sRGB')
        if new_height is not None:
            node_height = new_height
            should_connect_vertex = True
            
        new_height = mapTextureIfExists('g_SamplerNormalMap1_PngCachePath', 'g_SamplerNormalMap1', None, 'Non-Color')
        if new_height is not None:
            node_height = new_height
            should_connect_vertex = True
            
        new_height = mapTextureIfExists('g_SamplerSpecularMap1_PngCachePath', 'g_SamplerSpecularMap1', None, 'Non-Color')
        if new_height is not None:
            node_height = new_height
            should_connect_vertex = True
            
        if should_connect_vertex:
            vertexProperty = VertexPropertyMapping('Color', None, 'vertex_alpha', (0.5, 0.5, 0.5, 0))
            new_height = vertexProperty.apply(material, mesh, groupNode, node_height)
            if new_height is not None:
                node_height = new_height
                
        return node_height - 300
            
meddle_skin = NodeGroup(
    'meddle skin.shpk',
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
    ]
)

meddle_face_skin = NodeGroup(
    'meddle face skin.shpk',
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
    'meddle iris2.shpk',
    [
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
)

meddle_hair = NodeGroup(
    'meddle hair.shpk',
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
    ]
)

meddle_face_hair = NodeGroup(
    'meddle face hair.shpk',
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('MainColor', 'Hair Color'),
    ]
)

meddle_character_occlusion = NodeGroup(
    'meddle characterocclusion.shpk',
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
    ]
)

meddle_character_tattoo = NodeGroup(
    'meddle charactertattoo.shpk',
    [
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        FloatRgbMapping('OptionColor', 'OptionColor'),
        # DecalColor mapping to g_DecalColor <- not implemented
    ]
)

meddle_character = NodeGroup(
    'meddle character.shpk',
    [
        #ColorSetMapping('ColorTable', 'g_SamplerIndex_PngCachePath', 'DiffuseTableA', 'DiffuseTableB', 'SpecularTableA', 'SpecularTableB', 'color_a', 'color_b', 'specular_a', 'specular_b', 'id_mix'),
        ColorSetMapping2(),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
    ]
)

meddle_character_compatibility = NodeGroup(
    'meddle character_compatibility.shpk',
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', None, 'sRGB'),
        ColorSetMapping('ColorTable', 'g_SamplerIndex_PngCachePath', 'DiffuseTableA', 'DiffuseTableB', 'SpecularTableA', 'SpecularTableB', 'color_a', 'color_b', 'specular_a', 'specular_b', 'id_mix'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', None, 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', None, 'Non-Color'),
    ]
)


meddle_bg = NodeGroup(
    'meddle bg.shpk',
    [
        # PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        # PngMapping('g_SamplerColorMap1', 'g_SamplerColorMap1', 'g_SamplerColorMap1_alpha', 'sRGB'),
        # PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        # PngMapping('g_SamplerNormalMap1', 'g_SamplerNormalMap1', None, 'Non-Color'),
        # PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
        # PngMapping('g_SamplerSpecularMap1', 'g_SamplerSpecularMap1', None, 'Non-Color'),
        # VertexPropertyMapping('Color', None, 'vertex_alpha', (0.5, 0.5, 0.5, 0)),
        BgMapping()
    ]
)

meddle_bg_prop = NodeGroup(
    'meddle bgprop.shpk',
    [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
    ]
)

meddle_bg_colorchange = NodeGroup(
    'meddle bgcolorchange.shpk',
    [
        PngMapping('g_SamplerColorMap0', 'g_SamplerColorMap0', 'g_SamplerColorMap0_alpha', 'sRGB'),
        PngMapping('g_SamplerNormalMap0', 'g_SamplerNormalMap0', None, 'Non-Color'),
        PngMapping('g_SamplerSpecularMap0', 'g_SamplerSpecularMap0', None, 'Non-Color'),
        FloatRgbMapping('StainColor', 'StainColor'),
    ]
)

meddle_colortablepair = NodeGroup(
    'meddle colortablepair',
    []
)
meddle_colortablepair_mixer = NodeGroup(
    'meddle colortablepair_mixer',
    []
)

meddle_skin2 = NodeGroup(
    'meddle skin2.shpk',
    [
        PngMapping('g_SamplerDiffuse_PngCachePath', 'g_SamplerDiffuse', 'g_SamplerDiffuse_alpha', 'sRGB'),
        PngMapping('g_SamplerNormal_PngCachePath', 'g_SamplerNormal', 'g_SamplerNormal_alpha', 'Non-Color'),
        PngMapping('g_SamplerMask_PngCachePath', 'g_SamplerMask', 'g_SamplerMask_alpha', 'Non-Color'),
        FloatRgbMapping('SkinColor', 'Skin Color'),
        FloatRgbMapping('LipColor', 'Lip Color'),
        FloatRgbaAlphaMapping('LipColor', 'Lip Color Strength'),
        FloatRgbMapping('MainColor', 'Hair Color'),
        FloatRgbMapping('MeshColor', 'Highlights Color'),
    ]
)

nodegroups: list[NodeGroup] = [
    meddle_skin,
    meddle_face_skin,
    meddle_iris,
    meddle_hair,
    meddle_face_hair,
    meddle_character_occlusion,
    meddle_character_tattoo,
    meddle_character,
    meddle_bg,
    meddle_bg_colorchange,
    meddle_character_compatibility,
    meddle_bg_prop,
    meddle_skin2,
    meddle_colortablepair,
    meddle_colortablepair_mixer
]

def matchShader(mat):
    if mat is None:
        return (None, [])
    
    properties = mat
    shaderPackage = properties["ShaderPackage"]
    
    print(f"Matching shader {shaderPackage} on material {mat.name}")
    
    if shaderPackage is None:
        return (None, [])
    
    if shaderPackage == 'skin.shpk':
        output = (meddle_skin2, [FloatValueMapping(1.0, 'IS_FACE')])
        if 'CategorySkinType' in properties:
            if properties["CategorySkinType"] == 'Body':
                output = (meddle_skin2, [])
            elif properties["CategorySkinType"] == 'Face':
                output =  (meddle_skin2, [FloatValueMapping(1.0, 'IS_FACE')])
            elif properties["CategorySkinType"] == 'Hrothgar':
                output = (meddle_skin2, [FloatValueMapping(1.0, 'IS_HROTHGAR')])
                
        return output
       
    if shaderPackage == 'hair.shpk':
        output = (meddle_hair, [])
        if 'CategoryHairType' in properties:
            if properties["CategoryHairType"] == 'Face':
                output = (meddle_face_hair, [])
                
        return output
    
    if shaderPackage == 'iris.shpk':
        # need to map heterochromia and limbal ring enabled values
        return (meddle_iris, [])
    
    if shaderPackage == 'charactertattoo.shpk':
        return (meddle_character_tattoo, [])
    
    if shaderPackage == 'characterocclusion.shpk':
        return (meddle_character_occlusion, [])
    
    if shaderPackage == 'character.shpk' or shaderPackage == 'characterlegacy.shpk' or shaderPackage == 'characterscroll.shpk':
        # check if GetValuesTextureType is 'Compatibility'
        if 'GetValuesTextureType' in properties:
            if properties['GetValuesTextureType'] == 'Compatibility':
                return (meddle_character_compatibility, [])
            
        return (meddle_character, [])
    
    if shaderPackage == 'bg.shpk':
        return (meddle_bg, [])
    
    if shaderPackage == 'bgcolorchange.shpk':
        return (meddle_bg_colorchange, [])
    
    if shaderPackage == 'bgprop.shpk':
        return (meddle_bg_prop, [])
    
    print("No suitable shader found for " + shaderPackage + " on material " + mat.name)
    return (None, [])