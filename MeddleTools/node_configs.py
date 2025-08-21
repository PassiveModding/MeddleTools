import bpy
import idprop.types
import os.path as path
from . import version
# This file defines configs for specific nodes for new meddle shaders

class TextureNodeConfig:
    def __init__(self, colorSpace: str, alphaMode: str, interpolation: str, extension: str):
        self.colorSpace = colorSpace
        self.alphaMode = alphaMode
        self.interpolation = interpolation
        self.extension = extension

TextureNodeConfigs = {
    'skin.shpk;g_SamplerNormal_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    ),
    'skin.shpk;g_SamplerMask_PngCachePath': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Linear',
        extension='REPEAT'
    )
}

class ColorMapping:
    def __init__(self, prop_name: str, field_name: str):
        self.prop_name = prop_name
        self.field_name = field_name

    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            print(f"Property {self.prop_name} not found in material properties.")
            return
        
        if self.field_name not in group_node.inputs:
            print(f"Field {self.field_name} not found in group node inputs.")
            return
        
        group_input = group_node.inputs[self.field_name]
        if group_input.type == 'RGBA':
            # pad to 4 values
            if len(prop_value) == 3:
                prop_value = (*prop_value, 1.0)
            if len(prop_value) == 4:
                group_input.default_value = prop_value
        else:
            print(f"Unsupported field type {group_input.type} for {self.field_name}")


class FloatMapping:
    def __init__(self, prop_name: str, field_name: str, field_index: int = 0):
        self.prop_name = prop_name
        self.field_name = field_name
        self.field_index = field_index
        
    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            print(f"Property {self.prop_name} not found in material properties.")
            return
        if self.field_name not in group_node.inputs:
            print(f"Field {self.field_name} not found in group node inputs.")
            return
        
        group_input = group_node.inputs.get(self.field_name)
        if group_input.type == 'VALUE':
            # if prop_value is array, index using field_index, otherwise, use value as-is
            if isinstance(prop_value, (list, tuple, idprop.types.IDPropertyArray)):
                if self.field_index < len(prop_value):
                    group_input.default_value = prop_value[self.field_index]
                else:
                    print(f"Index {self.field_index} out of range for {self.prop_name}")
            else:
                group_input.default_value = prop_value
        else:
            print(f"Unsupported field type {group_input.type} for {self.field_name}")
            
class MaterialKeyMapping:
    def __init__(self, prop_name: str, prop_value: str, field_name: str, value_if_present: float = 1.0):
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
    'meddle hair2.shpk': 
    [
        ColorMapping('MainColor', 'Hair Color'),
        ColorMapping('MeshColor', 'Highlights Color'),
        MaterialKeyMapping('GetSubColor', 'GetSubColorFace', 'IS_FACE', 1.0),
        MaterialKeyMapping('GetSubColor', 'GetSubColorHair', 'IS_FACE', 0.0),
    ],
    'meddle charactertattoo.shpk':
    [        
        ColorMapping('OptionColor', 'OptionColor'),
    ],
    'meddle iris2.shpk':
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
    ]
}
  
def copy_custom_properties(material: bpy.types.Material):
    custom_props = {}
    for key in material.keys():
        if key != "_RNA_UI":
            try:
                custom_props[key] = material[key]
            except Exception as e:
                print(f"Could not read custom property '{key}' from '{material.name}': {e}")
    return custom_props

def apply_custom_properties(material: bpy.types.Material, custom_props: dict):
    for key, value in custom_props.items():
        material[key] = value
        
def apply_material(slot: bpy.types.MaterialSlot):
    if slot.material is None:
        return False
    try:            
        source_material = slot.material

        shader_package = source_material.get("ShaderPackage")
        if not shader_package:
            print("Material does not have a shader package defined.")
            return False
        
        resource_name = f'meddle {shader_package}'
        # replace node tree with copy of the one from the resource
        template_material = bpy.data.materials.get(resource_name)
        if not template_material:
            print(f"Resource material {resource_name} not found.")
            return False

        
        new_name = source_material.name
        if not new_name.startswith('Meddle '):
            new_name = f'Meddle {version.current_version} {new_name}'
        else:
            print(f"Material {new_name} already has Meddle prefix, skipping.")
            return False  # do not apply if already meddle material
        # give mat a version
        template_copy = template_material.copy()
        template_copy.name = new_name
        apply_custom_properties(template_copy, copy_custom_properties(source_material))

        slot.material = template_copy
        # make sure all other slots using source_material are updated
        for obj in (o for o in bpy.data.objects if o.type == 'MESH'):
            for slot in obj.material_slots:
                if slot.material == source_material:
                    slot.material = template_copy

        return True
    except Exception as e:
        print(e)
        return False
    

def map_mesh(mesh: bpy.types.Mesh, cache_directory: str):
    for slot in mesh.material_slots:
        if slot.material is None:
            continue
       
       
        if not apply_material(slot):
            continue
        
        setPngConfig(slot.material, slot.material.get("ShaderPackage"), cache_directory)
        setUvMapConfig(mesh, slot.material)
        setGroupProperties(mesh, slot.material)


def setPngConfig(material: bpy.types.Material, shader_package: str, cache_directory: str):
    node_tree = material.node_tree
    texture_nodes = [node for node in node_tree.nodes if node.type == 'TEX_IMAGE']

    # based on node label, lookup property on material
    for node in texture_nodes:
        label = node.label
        if label not in material:
            print(f"Node {label} not found in material properties.")
            continue
        
        cache_path = bpy.path.native_pathsep(material[label])
        full_path = path.join(cache_directory, cache_path)
        if not path.exists(full_path):
            print(f"Cache path {full_path} does not exist.")
            continue
        
        node.image = bpy.data.images.load(full_path)
        nodeKey = f'{shader_package};{label}'
        # check if the node label exists in the TextureNodeConfigs
        if nodeKey in TextureNodeConfigs:
            config = TextureNodeConfigs[nodeKey]
            node.image.colorspace_settings.name = config.colorSpace
            node.image.alpha_mode = config.alphaMode
            node.interpolation = config.interpolation
            node.extension = config.extension
        else:
            print(f"No config found for node label {label}. Using default settings.")
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
            print(f"UV Map {label} not found in mesh {mesh.name}.")
            continue

        node.uv_map = label
        
def setGroupProperties(mesh: bpy.types.Mesh, material: bpy.types.Material):
    node_tree = material.node_tree
    group_nodes = [node for node in node_tree.nodes if node.type == 'GROUP']

    for group_node in group_nodes:
        group_name = group_node.node_tree.name
        if group_name not in NodeGroupConfigs:
            print(f"No config found for group {group_name}.")
            continue
        
        config = NodeGroupConfigs[group_name]
        for mapping in config:
            mapping.apply(material, group_node)