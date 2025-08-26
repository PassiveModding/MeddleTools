import bpy
import idprop.types
import os.path as path
import re
import logging
from . import version

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass
# This file defines configs for specific nodes for new meddle shaders

class ColorMapping:
    def __init__(self, prop_name: str, field_name: str):
        self.prop_name = prop_name
        self.field_name = field_name

    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return
        
        if self.field_name not in group_node.inputs:
            logger.debug("Field %s not found in group node inputs.", self.field_name)
            return
        
        group_input = group_node.inputs[self.field_name]
        if group_input.type == 'RGBA':
            # pad to 4 values
            if len(prop_value) == 3:
                prop_value = (*prop_value, 1.0)
            if len(prop_value) == 4:
                group_input.default_value = prop_value
        else:
            logger.debug("Unsupported field type %s for %s", group_input.type, self.field_name)

class ColorHdrMapping:
    def __init__(self, prop_name: str, field_name: str, field_magnitude: str):
        self.prop_name = prop_name
        self.field_name = field_name
        self.field_magnitude = field_magnitude
        
    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return
        if self.field_name not in group_node.inputs:
            logger.debug("Field %s not found in group node inputs.", self.field_name)
            return
        if self.field_magnitude not in group_node.inputs:
            logger.debug("Field %s not found in group node inputs.", self.field_magnitude)
            return
        
        field_input = group_node.inputs[self.field_name]
        field_magnitude_input = group_node.inputs[self.field_magnitude]
        
        magnitude = 0
        for val in prop_value:
            if val > magnitude:
                magnitude = val
        
        if magnitude == 0:
            return
        
        adjusted_value = [val / magnitude for val in prop_value]
        
        if len(adjusted_value) == 3:
            adjusted_value.append(1.0)

        field_input.default_value = adjusted_value
        field_magnitude_input.default_value = magnitude

class FloatMapping:
    def __init__(self, prop_name: str, field_name: str, field_index: int = 0):
        self.prop_name = prop_name
        self.field_name = field_name
        self.field_index = field_index
        
    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return
        if self.field_name not in group_node.inputs:
            logger.debug("Field %s not found in group node inputs.", self.field_name)
            return
        
        group_input = group_node.inputs.get(self.field_name)
        if group_input.type == 'VALUE':
            # if prop_value is array, index using field_index, otherwise, use value as-is
            if isinstance(prop_value, (list, tuple, idprop.types.IDPropertyArray)):
                if self.field_index < len(prop_value):
                    group_input.default_value = prop_value[self.field_index]
                else:
                    logger.debug("Index %d out of range for %s", self.field_index, self.prop_name)
            else:
                group_input.default_value = prop_value
        else:
            logger.debug("Unsupported field type %s for %s", group_input.type, self.field_name)
            
class FloatArrayMapping:
    def __init__(self, prop_name: str, field_name: str):
        self.prop_name = prop_name
        self.field_name = field_name

    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return
        if self.field_name not in group_node.inputs:
            logger.debug("Field %s not found in group node inputs.", self.field_name)
            return

        group_input = group_node.inputs.get(self.field_name)
        if group_input.type == 'VECTOR':
            prop_list = prop_value.to_list()
            while len(prop_list) < 3:
                prop_list.append(0.0)
            group_input.default_value = prop_list
        else:
            logger.debug("Unsupported field type %s for %s", group_input.type, self.field_name)

class MaterialKeyMapping:
    def __init__(self, prop_name: str, prop_value: str, field_name: str, value_if_present: bool = True):
        self.prop_name = prop_name
        self.prop_value = prop_value
        self.field_name = field_name
        self.value_if_present = value_if_present

    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            return
        
        if prop_value != self.prop_value:
            return
        
        if self.field_name not in group_node.inputs:
            return

        group_node.inputs[self.field_name].default_value = self.value_if_present

class UvScrollMapping:
    def __init__(self) -> None:
        pass
    
    def apply(self, material_properties: dict, group_node):
        scrollAmount = None
        if '0x9A696A17' not in material_properties:
            return
        
        if 'Multiplier' not in group_node.inputs:
            return
        
        scrollAmount = material_properties['0x9A696A17']
        
        multiplier_values = None
        if group_node.label == 'UV0Scroll':
            multiplier_values = [scrollAmount[0] * -1, scrollAmount[1], 0.0]
        elif group_node.label == 'UV1Scroll':
            multiplier_values = [scrollAmount[2] * -1, scrollAmount[3], 0.0]

        if multiplier_values is None:
            return

        group_node.inputs['Multiplier'].default_value = multiplier_values

class TextureNodeConfig:
    def __init__(self, colorSpace: str, alphaMode: str, interpolation: str, extension: str):
        self.colorSpace = colorSpace
        self.alphaMode = alphaMode
        self.interpolation = interpolation
        self.extension = extension

TextureNodeConfigs = {
    'g_SamplerDiffuse_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),    
    'g_SamplerSkinDiffuse_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerNormal_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerSkinNormal_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerMask_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerSkinMask_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerIndex_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Closest',
        extension='REPEAT'
    ),
    'Decal_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='CLIP'
    ),
    'g_SamplerEnvMap_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerWaveMap_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerWaveMap1_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerWhitecapMap_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerColorMap0_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerColorMap1_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerNormalMap0_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerNormalMap1_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_SamplerSpecularMap0_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_Sampler0_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'g_Sampler1_PngCachePath': TextureNodeConfig(
        colorSpace='sRGB',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    )
}

NodeGroupConfigs = {
    'meddle skin.shpk': 
    [
        ColorMapping('SkinColor', 'Skin Color'),
        ColorMapping('LipColor', 'Lip Color'),
        FloatMapping('LipColor', 'Lip Color Strength', 3),
        ColorMapping('MainColor', 'Hair Color'),
        ColorMapping('MeshColor', 'Highlights Color'),
        ColorMapping('DecalColor', 'Decal Color'),
        FloatMapping('DecalColor', 'Decal Color Strength', 3),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueFace', 'IS_FACE'),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueBodyJJM', 'IS_HROTHGAR'),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueFaceEmissive', 'IS_EMISSIVE'),
    ],
    'meddle decaluv': 
    [
        FloatMapping('FacePaintUVMultiplier', 'UVMultiplier'),
        FloatMapping('FacePaintUVOffset', 'UVOffset')
    ],
    'meddle hair.shpk': 
    [
        ColorMapping('MainColor', 'Hair Color'),
        ColorMapping('MeshColor', 'Highlights Color'),
        MaterialKeyMapping('GetSubColor', 'GetSubColorFace', 'IS_FACE', True),
        MaterialKeyMapping('GetSubColor', 'GetSubColorHair', 'IS_FACE', False),
    ],
    'meddle charactertattoo.shpk':
    [        
        ColorMapping('OptionColor', 'OptionColor'),
    ],
    'meddle iris.shpk':
    [        
        ColorMapping('g_WhiteEyeColor', 'g_WhiteEyeColor'),
        ColorMapping('LeftIrisColor', 'left_iris_color'),
        ColorMapping('RightIrisColor', 'right_iris_color'),
        FloatMapping('LeftIrisColor', 'left_iris_limbal_ring_intensity', 3),
        FloatMapping('RightIrisColor', 'right_iris_limbal_ring_intensity', 3),
        ColorMapping('g_IrisRingColor', 'g_IrisRingColor'),
        FloatMapping('g_IrisRingEmissiveIntensity', 'g_IrisRingEmissiveIntensity'),
        FloatMapping('unk_LimbalRingRange', 'unk_LimbalRingRange_start', 0),
        FloatMapping('unk_LimbalRingRange', 'unk_LimbalRingRange_end', 1),
        FloatMapping('unk_LimbalRingFade', 'unk_LimbalRingFade_start', 0),
        FloatMapping('unk_LimbalRingFade', 'unk_LimbalRingFade_end', 1),        
    ],
    "meddle bg.shpk":
    [
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
        ColorHdrMapping('g_EmissiveColor', 'g_EmissiveColor', 'g_EmissiveColor_magnitude'),        
        MaterialKeyMapping('GetValues', 'GetMultiValues', 'GetMultiValues', True),
    ],
    "meddle water.shpk":
    [
        ColorMapping('0xD315E728', 'unk_WaterColor'),
        ColorMapping('unk_WaterColor', 'unk_WaterColor'),
        ColorMapping('g_RefractionColor', 'g_RefractionColor'),
        ColorMapping('g_WhitecapColor', 'g_WhitecapColor'),
        FloatMapping('g_Transparency', 'g_Transparency'),
    ],
    "meddle river.shpk":
    [
        ColorMapping('0xD315E728', 'unk_WaterColor'),
        ColorMapping('unk_WaterColor', 'unk_WaterColor'),
        ColorMapping('g_RefractionColor', 'g_RefractionColor'),
        ColorMapping('g_WhitecapColor', 'g_WhitecapColor'),
        FloatMapping('g_Transparency', 'g_Transparency'),
    ],
    "meddle bgcolorchange.shpk":
    [
        ColorMapping('StainColor', 'StainColor'),
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
    ],
    "meddle lightshaft.shpk":
    [
        ColorMapping('g_Color', 'g_Color'),
        FloatArrayMapping('g_TexAnim', 'g_TexAnim'),
        FloatArrayMapping('g_TexU', 'g_TexU'),
        FloatArrayMapping('g_TexV', 'g_TexV'),
        FloatArrayMapping('g_Ray', 'g_Ray'),
    ],
    "meddle scroll":
    [
        UvScrollMapping()
    ],
    "meddle character.shpk":
    [
        ColorMapping('SkinColor', 'SkinColor'),
        MaterialKeyMapping('GetValues', 'GetValuesCompatibility', 'IS_COMPATIBILITY', True),
        MaterialKeyMapping('GetValuesTextureType', 'Compatibility', 'IS_COMPATIBILITY', True), # old meddle naming?  
        MaterialKeyMapping('ShaderPackage', 'characterlegacy.shpk', 'IS_LEGACY', True),     
        MaterialKeyMapping('ShaderPackage', 'characterstockings.shpk', 'IS_STOCKING', True),
        MaterialKeyMapping('ShaderPackage', 'charactertransparency.shpk', 'IS_TRANSPARENCY', True),
    ]
}

def copy_custom_properties(material: bpy.types.Material):
    custom_props = {}
    for key in material.keys():
        if key != "_RNA_UI":
            try:
                custom_props[key] = material[key]
            except Exception as e:
                logger.exception("Could not read custom property '%s' from '%s': %s", key, material.name, e)
    return custom_props

def apply_custom_properties(material: bpy.types.Material, custom_props: dict):
    for key, value in custom_props.items():
        try:
            # avoid 'Cannot assign a 'IDPropertyGroup' value to the existing '{key}' Group IDProperty
            # just skip these without attempting to assign
            if key in material:
                continue
            material[key] = value
        except Exception as e:
            logger.warning("Could not apply custom property '%s' to '%s': %s", key, material.name, e)

shader_package_mappings = {
    "characterlegacy.shpk": "character.shpk",
    "characterstockings.shpk": "character.shpk",
    "characterinc.shpk": "character.shpk",
    "characterglass.shpk": "character.shpk",
    "characterscroll.shpk": "character.shpk",
    "charactertransparency.shpk": "character.shpk",
    "river.shpk": "water.shpk"
}

def apply_material(slot: bpy.types.MaterialSlot, force_apply: bool = False):
    if slot.material is None:
        return False
    try:            
        source_material = slot.material

        shader_package = source_material.get("ShaderPackage")
        if not shader_package:
            logger.debug("Material does not have a shader package defined.")
            return False
        
        resource_shpk = shader_package_mappings.get(shader_package, shader_package)
        
        resource_name = f'meddle {resource_shpk} {version.current_version}'
        # replace node tree with copy of the one from the resource
        template_material = bpy.data.materials.get(resource_name)
        if not template_material:
            logger.debug("Resource material %s not found.", resource_name)
            return False
        
        new_name = source_material.name
        if not new_name.startswith('Meddle '):
            # remove substring _<shader_package> if exists
            shpk_substring = f"_{shader_package}"
            if shpk_substring in new_name:
                new_name = new_name.replace(shpk_substring, '')
            new_name = f'Meddle {version.current_version} {shader_package} {new_name}'
        elif not force_apply:
            logger.debug("Material %s already has Meddle prefix, skipping.", new_name)
            return False  # do not apply if already meddle material
        template_copy = template_material.copy()
        template_copy.name = new_name
        #template_copy.use_transparent_shadows = True
        apply_custom_properties(template_copy, copy_custom_properties(source_material))

        slot.material = template_copy
        # make sure all other slots using source_material are updated
        for obj in (o for o in bpy.data.objects if o.type == 'MESH'):
            for slot in obj.material_slots:
                if slot.material == source_material:
                    slot.material = template_copy

        return True
    except Exception as e:
        logger.exception("Error applying material: %s", e)
        return False
    

def map_mesh(mesh: bpy.types.Mesh, cache_directory: str, force_apply: bool = False):
    for slot in mesh.material_slots:
        if slot.material is None:
            continue
       
       
        if not apply_material(slot, force_apply):
            continue
        
        logger.info("Applying material %s to mesh %s", slot.material.name, mesh.name)
        setBackfaceCulling(mesh, slot.material)        
        setPngConfig(slot.material, cache_directory)
        setUvMapConfig(mesh, slot.material)
        setGroupProperties(mesh, slot.material)
        setColorAttributes(mesh, slot.material)
        setColorTableRamps(mesh, slot.material)
    
def getValuesForType(row, rowProp, type):
    def convertValue(val, divisor = None):
        if val == 'Infinity':
            return float('inf')
        elif val == '-Infinity':
            return float('-inf')
        elif val == 'NaN':
            return float('nan')
        else:
            return val
    
    if type == 'XYZ':
        return [convertValue(row[rowProp]['X']), convertValue(row[rowProp]['Y']), convertValue(row[rowProp]['Z'])]
    elif type == 'Float':
        return [convertValue(row[rowProp])]
    elif type == 'TileMatrix':
        return [convertValue(row[rowProp]['UU']), convertValue(row[rowProp]['UV']), convertValue(row[rowProp]['VU']), convertValue(row[rowProp]['VV'])]
    else:
        raise Exception(f"Unsupported type {type}")
    
def padRgbaValues(list):
    while len(list) < 4:
        list.append(1.0)
    return list
    
def clearRamp(ramp):
    while len(ramp.color_ramp.elements) > 1:
        ramp.color_ramp.elements.remove(ramp.color_ramp.elements[0])
        
def getOddEvenRows(material: bpy.types.Material):
    if 'ColorTable' not in material:
        return ([], [])
    
    colorSet = material['ColorTable']
    if 'ColorTable' not in colorSet:
        return ([], [])
    
    colorTable = colorSet['ColorTable']
    if 'Rows' not in colorTable:
        return ([], [])
    
    rows = colorTable['Rows']
    odds = []
    evens = []
    for i, row in enumerate(rows):
        if i % 2 == 0:
            evens.append(row)
        else:
            odds.append(row)
    return (odds, evens)
    

class ColorTableRampLookup:
    def __init__(self, rowPropName: str, rowPropType: str, b_ramp: bool):
        self.rowPropName = rowPropName
        self.rowPropType = rowPropType
        self.b_ramp = b_ramp
        
        
    def apply(self, material: bpy.types.Material, colorRamp):        
        clearRamp(colorRamp)
        odds, evens = getOddEvenRows(material)

        set = odds if self.b_ramp else evens

        for i, row in enumerate(set):
            if self.rowPropName not in row:
                continue
            pos = i / len(set)
            if self.rowPropName not in row:
                raise Exception(f"Row property {self.rowPropName} not found in row")
            row_values = padRgbaValues(getValuesForType(row, self.rowPropName, self.rowPropType))
            if i == 0:
                colorRamp.color_ramp.elements[0].position = pos
                colorRamp.color_ramp.elements[0].color = row_values
            else:
                element = colorRamp.color_ramp.elements.new(pos)
                try:
                    element.color = row_values
                except Exception as e:
                    logger.warning("Error setting color for row %d: %s", i, e)
                    
class PackedColorTableRampLookup:
    def __init__(self, rowNameTypeMaps: list[tuple[str, str]], b_ramp: bool):
        self.rowNameTypeMaps = rowNameTypeMaps
        self.b_ramp = b_ramp
        
    def apply(self, material: bpy.types.Material, colorRamp):
        clearRamp(colorRamp)

        odds, evens = getOddEvenRows(material)
        set = odds if self.b_ramp else evens

        for i, row in enumerate(set):
            row_values = []
            for (rowPropName, rowPropType) in self.rowNameTypeMaps:
                if rowPropName not in row:
                    raise Exception(f"Row property {rowPropName} not found in row")
                values = getValuesForType(row, rowPropName, rowPropType)
                for val in values:
                    row_values.append(val)
            row_values = padRgbaValues(row_values)
            try:
                if i == 0:
                    colorRamp.color_ramp.elements[0].position = i / len(set)
                    colorRamp.color_ramp.elements[0].color = row_values
                else:
                    element = colorRamp.color_ramp.elements.new(i / len(set))
                    element.color = row_values
            except Exception as e:
                logger.warning("Error setting color for row %d: %s", i, e)

RampLookups = {
    "ColorRampA": ColorTableRampLookup("Diffuse", "XYZ", False),
    "ColorRampB": ColorTableRampLookup("Diffuse", "XYZ", True),
    "SpecularRampA": PackedColorTableRampLookup([("Specular", "XYZ"), ("Anisotropy", "Float")], False),
    "SpecularRampB": PackedColorTableRampLookup([("Specular", "XYZ"), ("Anisotropy", "Float")], True),
    "EmissionRampA": ColorTableRampLookup("Emissive", "XYZ", False),
    "EmissionRampB": ColorTableRampLookup("Emissive", "XYZ", True),
    "MetalnessRoughnessGlossSpecularA": PackedColorTableRampLookup([("Metalness", "Float"), ("Roughness", "Float"), ("GlossStrength", "Float"), ("SpecularStrength", "Float")], False),
    "MetalnessRoughnessGlossSpecularB": PackedColorTableRampLookup([("Metalness", "Float"), ("Roughness", "Float"), ("GlossStrength", "Float"), ("SpecularStrength", "Float")], True),
    # "AnisotropyRampA": ColorTableRampLookup("Anisotropy", "Float", False),
    # "AnisotropyRampB": ColorTableRampLookup("Anisotropy", "Float", True),
    "SheenPropertiesA": PackedColorTableRampLookup([("SheenRate", "Float"), ("SheenTint", "Float"), ("SheenAptitude", "Float")], False),
    "SheenPropertiesB": PackedColorTableRampLookup([("SheenRate", "Float"), ("SheenTint", "Float"), ("SheenAptitude", "Float")], True),
    "SpherePropertiesA": PackedColorTableRampLookup([("SphereIndex", "Float"), ("SphereMask", "Float")], False),
    "SpherePropertiesB": PackedColorTableRampLookup([("SphereIndex", "Float"), ("SphereMask", "Float")], True),
    "TilePropertiesA": PackedColorTableRampLookup([("TileIndex", "Float"), ("TileAlpha", "Float")], False),
    "TilePropertiesB": PackedColorTableRampLookup([("TileIndex", "Float"), ("TileAlpha", "Float")], True),
    "TileMatrixPropertiesA": ColorTableRampLookup("TileMatrix", "TileMatrix", False),
    "TileMatrixPropertiesB": ColorTableRampLookup("TileMatrix", "TileMatrix", True)
}

def setColorTableRamps(mesh: bpy.types.Mesh, material: bpy.types.Material):
    ramp_nodes = [node for node in material.node_tree.nodes if node.type == 'VALTORGB']
    
    for node in ramp_nodes:
        label = node.label
        if label in RampLookups:
            RampLookups[label].apply(material, node)

def setColorAttributes(mesh: bpy.types.Mesh, material: bpy.types.Material):
    vertex_color_nodes = [node for node in material.node_tree.nodes if node.type == 'VERTEX_COLOR']
    #node_tree = material.node_tree
    for node in vertex_color_nodes:
        # if has label, lookup color attribute and set
        label = node.label
        if label not in mesh.data.vertex_colors:
            # find connections from node and disconnect
            # skip for now, should ideally be driven by material keys
            # for link in node.outputs[0].links:
            #     node_tree.links.remove(link)
            # for link in node.outputs[1].links:
            #     node_tree.links.remove(link)
            continue
        node.layer_name = label

def setBackfaceCulling(mesh: bpy.types.Mesh, material: bpy.types.Material):
    if not mesh.data:
        return

    if 'RenderBackfaces' not in material:
        return
    
    render_backfaces = material['RenderBackfaces']
    if render_backfaces:
        material.use_backface_culling = False
    else:
        material.use_backface_culling = True

def setPngConfig(material: bpy.types.Material, cache_directory: str):
    node_tree = material.node_tree
    texture_nodes = [node for node in node_tree.nodes if node.type == 'TEX_IMAGE']

    # based on node label, lookup property on material
    for node in texture_nodes:
        label = node.label
        if label not in material:
            logger.debug("Node %s not found in material properties.", label)
            continue
        
        cache_path = bpy.path.native_pathsep(material[label])
        full_path = path.join(cache_directory, cache_path)
        if not path.exists(full_path):
            logger.debug("Cache path %s does not exist.", full_path)
            continue
        
        node.image = bpy.data.images.load(full_path)
        # check if the node label exists in the TextureNodeConfigs
        if label in TextureNodeConfigs:
            config = TextureNodeConfigs[label]
            node.image.colorspace_settings.name = config.colorSpace
            node.image.alpha_mode = config.alphaMode
            node.interpolation = config.interpolation
            node.extension = config.extension
        else:
            logger.debug("No config found for node label %s. Using default settings.", label)
            node.image.colorspace_settings.name = 'Non-Color'
            node.image.alpha_mode = 'CHANNEL_PACKED'
            node.interpolation = 'Linear'
            node.extension = 'REPEAT'

def setUvMapConfig(mesh: bpy.types.Mesh, material: bpy.types.Material):
    if not mesh.data:
        return
    
    node_tree = material.node_tree
    uv_map_nodes = [node for node in node_tree.nodes if node.type == 'UVMAP']

    for node in uv_map_nodes:
        label = node.label
        if label not in mesh.data.uv_layers:
            logger.debug("UV Map %s not found in mesh %s.", label, mesh.name)
            continue

        node.uv_map = label
        
def setGroupProperties(mesh: bpy.types.Mesh, material: bpy.types.Material):
    node_tree = material.node_tree
    group_nodes = [node for node in node_tree.nodes if node.type == 'GROUP']

    for group_node in group_nodes:
        group_name = group_node.node_tree.name
        if re.search(r'\.\d+$', group_name):
            group_name = re.sub(r'\.\d+$', '', group_name)

        if group_name not in NodeGroupConfigs:
            logger.debug("No config found for group %s.", group_name)
            continue
        
        config = NodeGroupConfigs[group_name]
        for mapping in config:
            try:
                mapping.apply(material, group_node)
            except Exception as e:
                logger.exception("Error applying mapping for group %s: %s", group_name, e)