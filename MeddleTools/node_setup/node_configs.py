import os
import bpy
import idprop.types
import os.path as path
import re
import logging
import time
from typing import Callable, List, Tuple, Union, Any
from functools import wraps
from .. import version, blend_import
from .node_mappings import (
    TextureNodeConfig,
    ConditionalTextureConfig,
    material_condition_equals,
    ArrayDefinition,
    ColorMapping,
    FloatMapping,
    VectorMapping,
    MaterialKeyMapping,
    FloatArrayMapping,
    FloatArraySeparateMapping,
    UvScrollMapping,
    ColorTableRampLookup,
    PackedColorTableRampLookup
)

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

# Profiling decorator
def profile_function(func):
    """Decorator to profile function execution time"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        if elapsed > 0.001:  # Only log if > 1ms
            logger.info(f"[PROFILE] {func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

png_custom_vertical_array_definitions = {
    'chara_tile_norm_array': ArrayDefinition('array_textures/chara/common/texture/tile_norm_array', r'tile_norm_array\..+\.vertical\.png$'),
    'chara_tile_orb_array': ArrayDefinition('array_textures/chara/common/texture/tile_orb_array', r'tile_orb_array\..+\.vertical\.png$'),
    'bgcommon_detail_n_array': ArrayDefinition('array_textures/bgcommon/nature/detail/texture/detail_n_array', r'detail_n_array\..+\.vertical\.png$'),
    'bgcommon_detail_d_array': ArrayDefinition('array_textures/bgcommon/nature/detail/texture/detail_d_array', r'detail_d_array\..+\.vertical\.png$'),
}


texture_node_configs: dict[str, Union[TextureNodeConfig, ConditionalTextureConfig]] = {
    'chara_tile_norm_array': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Closest',
        extension='REPEAT'
    ),
    'chara_tile_orb_array': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Closest',
        extension='REPEAT'
    ),
    'bgcommon_detail_n_array': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Closest',
        extension='REPEAT'
    ),
    'bgcommon_detail_d_array': TextureNodeConfig(
        colorSpace='Non-Color',
        alphaMode='CHANNEL_PACKED',
        interpolation='Closest',
        extension='REPEAT'
    ),
    # Default config with conditional override for skin face materials
    'g_SamplerDiffuse_PngCachePath': ConditionalTextureConfig(
        default=TextureNodeConfig(
            colorSpace='sRGB',
            alphaMode='CHANNEL_PACKED',
            interpolation='Linear',
            extension='REPEAT'
        ),
        overrides=[
            (
                # Should fix the issue of teeth being shown when the UV wraps in 'REPEAT' mode.
                material_condition_equals(ShaderPackage='skin.shpk', GetMaterialValue='GetMaterialValueFace'),
                TextureNodeConfig(
                    colorSpace='sRGB',
                    alphaMode='CHANNEL_PACKED',
                    interpolation='Linear',
                    extension='CLIP'
                )
            )
        ]
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

node_group_configs = {
    'meddle skin.shpk': 
    [
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
        ColorMapping('g_EmissiveColor', 'g_EmissiveColor'),
        ColorMapping('SkinColor', 'Skin Color'),
        ColorMapping('LipColor', 'Lip Color'),
        FloatMapping('LipColor', 'Lip Color Strength', 3),
        ColorMapping('MainColor', 'Hair Color'),
        ColorMapping('MeshColor', 'Highlights Color'),
        ColorMapping('DecalColor', 'Decal Color'),
        FloatMapping('DecalColor', 'Decal Color Strength', 3),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueFace', 'GetMaterialValueFace'),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueBody', 'GetMaterialValueBody'), # TODO: Use this input
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueBodyJJM', 'GetMaterialValueBodyJJM'),
        MaterialKeyMapping('GetMaterialValue', 'GetMaterialValueFaceEmissive', 'GetMaterialValueFaceEmissive'),
        MaterialKeyMapping('GetDecalColor', 'GetDecalColorAlpha', 'GetDecalColorAlpha'),
    ],
    'meddle decaluv': 
    [
        FloatMapping('FacePaintUVMultiplier', 'UVMultiplier'),
        FloatMapping('FacePaintUVOffset', 'UVOffset')
    ],
    'meddle hair.shpk': 
    [
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
        ColorMapping('MainColor', 'Hair Color'),
        ColorMapping('MeshColor', 'Highlights Color'),
        MaterialKeyMapping('GetSubColor', 'GetSubColorFace', 'GetSubColorFace'),
        MaterialKeyMapping('GetSubColor', 'GetSubColorHair', 'GetSubColorHair'),
    ],
    'meddle charactertattoo.shpk':
    [        
        ColorMapping('OptionColor', 'OptionColor')
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
        VectorMapping('g_IrisRingUvFadeWidth', 'g_IrisRingUvFadeWidth', 2),
        VectorMapping('g_IrisRingUvRadius', 'g_IrisRingUvRadius', 2),
        # g_IrisOptionColorEmissiveIntensity
        # g_IrisOptionColorEmissiveRate
        # g_IrisOptionColorRate
        # g_IrisRingColor
        # g_IrisRingEmissiveIntensity
        # g_IrisRingForceColor
        # g_IrisRingOddRate
        # g_IrisRingUvFadeWidth
        # g_IrisRingUvRadius
        # g_IrisThickness
        # g_IrisUvRadius
        
        # Stub Mappings
        VectorMapping('unk_LimbalRingFade', 'g_IrisRingUvFadeWidth', 2),
        VectorMapping('unk_LimbalRingRange', 'g_IrisRingUvRadius', 2),
    ],
    "meddle bg.shpk":
    [
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
        ColorMapping('g_MultiDiffuseColor', 'g_MultiDiffuseColor'),
        ColorMapping('g_EmissiveColor', 'g_EmissiveColor'),
        ColorMapping('g_MultiEmissiveColor', 'g_MultiEmissiveColor'),
        FloatMapping('g_NormalScale', 'g_NormalScale'),
        FloatMapping('g_MultiNormalScale', 'g_MultiNormalScale'),
        MaterialKeyMapping('GetValues', 'GetSingleValues', 'GetSingleValues', True),
        MaterialKeyMapping('GetValues', 'GetMultiValues', 'GetMultiValues', True),
        MaterialKeyMapping('GetValues', 'GetAlphaMultiValues', 'GetAlphaMultiValues', True), # GetAlphaMultiValues2, GetAlphaMultiValues3 used in bguvcroll/lightshaft
        MaterialKeyMapping('ApplyVertexColor', 'ApplyVertexColorOff', 'ApplyVertexColor', False),        
        MaterialKeyMapping('ApplyVertexColor', 'ApplyVertexColorOn', 'ApplyVertexColor', True),    
        
        # 0xF769298E
        # R-?
        # G-?
        # B- increases multi influence?
        # A-?    
        
        # PENDING: Fix detail influence for terrain, currently borked
    ],
    "meddle water.shpk":
    [
        ColorMapping('g_RefractionColor', 'g_RefractionColor'),
        ColorMapping('g_WhitecapColor', 'g_WhitecapColor'),
        FloatMapping('g_Transparency', 'g_Transparency'),
        ColorMapping('g_WaterDeepColor', 'g_WaterDeepColor'),
        
        # Old mappings
        ColorMapping('0xD315E728', 'g_WaterDeepColor'),
        ColorMapping('unk_WaterColor', 'g_WaterDeepColor'),
    ],
    # "meddle river.shpk": # Currently re-using water.shpk node group
    # [
    #     ColorMapping('g_RefractionColor', 'g_RefractionColor'),
    #     ColorMapping('g_WhitecapColor', 'g_WhitecapColor'),
    #     FloatMapping('g_Transparency', 'g_Transparency'),
    #     ColorMapping('g_WaterDeepColor', 'g_WaterDeepColor'),
    #
    #     # Old mappings
    #     ColorMapping('0xD315E728', 'unk_WaterColor'),
    #     ColorMapping('unk_WaterColor', 'unk_WaterColor'),
    # ],
    "meddle bgcolorchange.shpk":
    [
        ColorMapping('StainColor', 'StainColor'),
        ColorMapping('g_DiffuseColor', 'g_DiffuseColor'),
        FloatMapping('g_NormalScale', 'g_NormalScale'),
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
        MaterialKeyMapping('GetValues', 'GetValuesCompatibility', 'GetValuesCompatibility', True),
        MaterialKeyMapping('ShaderPackage', 'characterlegacy.shpk', 'IS_LEGACY', True),     
        MaterialKeyMapping('ShaderPackage', 'characterstockings.shpk', 'IS_STOCKING', True),
        MaterialKeyMapping('ShaderPackage', 'charactertransparency.shpk', 'IS_TRANSPARENCY', True),
    
        # Old mappings
        MaterialKeyMapping('GetValuesTextureType', 'Compatibility', 'GetValuesCompatibility', True),  
    ],
    "tile_select":
    [
        FloatMapping('g_TileIndex', 'g_TileIndex'),
        FloatMapping('g_TileAlpha', 'g_TileAlpha'),
        FloatArraySeparateMapping('g_TileScale', ['TileRepeatU', 'TileRepeatV']),
    ],
    "hair_alpha_threshold":
    [
        FloatMapping('g_AlphaThreshold', 'g_AlphaThreshold'),
    ],
    "alpha_threshold":
    [
        FloatMapping('g_AlphaThreshold', 'g_AlphaThreshold'),
    ],
    "bg_alpha_threshold":
    [
        FloatMapping('g_AlphaThreshold', 'g_AlphaThreshold'),
        MaterialKeyMapping('ApplyAlphaTest', 'ApplyAlphaTestOn', 'ApplyAlphaTest', True),
        MaterialKeyMapping('ApplyAlphaTest', 'ApplyAlphaTestOff', 'ApplyAlphaTest', False),
    ],
    "bg_tile_select":
    [        
        FloatMapping('g_DetailID', 'g_DetailID'),
        FloatMapping('g_MultiDetailID', 'g_MultiDetailID'),
        VectorMapping('g_DetailColorUvScale', 'g_DetailColorUvScale', 2),
        VectorMapping('g_DetailColorUvScale', 'g_DetailColorUvScale_Multi', 2, 2),
        VectorMapping('g_DetailNormalUvScale', 'g_DetailNormalUvScale', 2),
        VectorMapping('g_DetailNormalUvScale', 'g_DetailNormalUvScale_Multi', 2, 2),
    ],
    "bg_detail_blend":
    [
        ColorMapping('g_DetailColor', 'g_DetailColor'),
        ColorMapping('g_MultiDetailColor', 'g_MultiDetailColor'),
        FloatMapping('g_DetailNormalScale', 'g_DetailNormalScale'),
        FloatMapping('g_MultiDetailNormalScale', 'g_MultiDetailNormalScale'),
    ]
}

shader_package_mappings = {
    "characterlegacy.shpk": "character.shpk",
    "characterstockings.shpk": "character.shpk",
    "characterinc.shpk": "character.shpk",
    "characterglass.shpk": "character.shpk",
    "characterscroll.shpk": "character.shpk",
    "charactertransparency.shpk": "character.shpk",
    "river.shpk": "water.shpk"
}


ramp_lookups = {
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


@profile_function
def copy_custom_properties(material: bpy.types.Material):
    custom_props = {}
    for key in material.keys():
        if key != "_RNA_UI":
            try:
                custom_props[key] = material[key]
            except Exception as e:
                logger.exception("Could not read custom property '%s' from '%s': %s", key, material.name, e)
    return custom_props

@profile_function
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


@profile_function
def apply_material(material: bpy.types.Material, slots: List[bpy.types.MaterialSlot]) -> Union[bpy.types.Material, None]:
    if material is None:
        return None
    try:            
        source_material = material
        shader_package = source_material.get("ShaderPackage")
        if not shader_package:
            logger.debug("Material does not have a shader package defined.")
            return None
        
        resource_shpk = shader_package_mappings.get(shader_package, shader_package)
        
        resource_name = blend_import.get_resource_name(resource_shpk)
        # replace node tree with copy of the one from the resource
        template_material = bpy.data.materials.get(resource_name)
        if not template_material:
            logger.debug("Resource material %s not found.", resource_name)
            return None
        
        new_name = source_material.name
        if not new_name.startswith('Meddle '):
            # remove substring _<shader_package> if exists
            shpk_substring = f"_{shader_package}"
            if shpk_substring in new_name:
                new_name = new_name.replace(shpk_substring, '')
            new_name = f'Meddle {version.current_version} {shader_package} {new_name}'
        else:
            logger.debug("Material %s already has Meddle prefix, skipping.", new_name)
            return None  # do not apply if already meddle material
        template_copy = template_material.copy()
        template_copy.name = new_name
        #template_copy.use_transparent_shadows = True
        apply_custom_properties(template_copy, copy_custom_properties(source_material))

        for slot in slots:
            if slot.material == source_material:
                slot.material = template_copy

        return template_copy
    except Exception as e:
        logger.exception("Error applying material: %s", e)
        return None
    

@profile_function
def map_mesh(material: bpy.types.Material, slots: List[bpy.types.MaterialSlot], cache_directory: str):    
    material = apply_material(material, slots)
    if not material:
        return
    
    logger.info("Applying material %ss", material.name)
    
    setBackfaceCulling(material)    
    setPngConfig(material, cache_directory)    
    setUvMapConfig(material)    
    setGroupProperties(material)    
    setColorAttributes(material)    
    setColorTableRamps(material)
    
@profile_function
def setColorTableRamps(material: bpy.types.Material):
    from .node_mappings import getOddEvenRows
    
    ramp_nodes = [node for node in material.node_tree.nodes if node.type == 'VALTORGB']
    if not ramp_nodes:
        return
    
    # Fetch rows once for all ramps
    odds_rows, evens_rows = getOddEvenRows(material)
    
    for node in ramp_nodes:
        label = node.label
        if label in ramp_lookups:
            ramp_lookups[label].apply(material, node, odds_rows, evens_rows)

@profile_function
def setColorAttributes(material: bpy.types.Material):
    vertex_color_nodes = [node for node in material.node_tree.nodes if node.type == 'VERTEX_COLOR']
    #node_tree = material.node_tree
    for node in vertex_color_nodes:
        # if has label, lookup color attribute and set
        label = node.label
        node.layer_name = label

@profile_function
def setBackfaceCulling(material: bpy.types.Material):
    if 'RenderBackfaces' not in material:
        return
    
    render_backfaces = material['RenderBackfaces']
    if render_backfaces:
        material.use_backface_culling = False
    else:
        material.use_backface_culling = True

@profile_function
def setPngConfig(material: bpy.types.Material, cache_directory: str):
    node_tree = material.node_tree
    texture_nodes = [node for node in node_tree.nodes if node.type == 'TEX_IMAGE']
    
    if not texture_nodes:
        return
    
    # Cache compiled regex patterns for array definitions
    array_patterns = {
        label: re.compile(array_def.file_name_pattern)
        for label, array_def in png_custom_vertical_array_definitions.items()
    }

    def resolve_image_path(label: str) -> str | None:
        # Custom vertical array path handling
        if label in png_custom_vertical_array_definitions:
            array_def = png_custom_vertical_array_definitions[label]
            array_cache_path = path.join(cache_directory, array_def.cache_path)
            if not path.exists(array_cache_path):
                logger.debug("Array cache path %s does not exist.", array_cache_path)
                return None
            try:
                pattern = array_patterns[label]
                for file_name in os.listdir(array_cache_path):
                    if pattern.match(file_name):
                        return path.join(array_cache_path, file_name)
            except Exception as e:
                logger.warning("Error listing %s: %s", array_cache_path, e)
            logger.debug("No file matching pattern %s found in %s.", array_def.file_name_pattern, array_cache_path)
            return None

        # Standard material property path
        if label not in material:
            return None
        cache_path = bpy.path.native_pathsep(material[label])
        full_path = path.join(cache_directory, cache_path)
        if not path.exists(full_path):
            return None
        return full_path

    def resolve_config(label: str) -> TextureNodeConfig | None:
        entry = texture_node_configs.get(label)
        if not entry:
            return None
        if isinstance(entry, ConditionalTextureConfig):
            return entry.resolve(material)
        return entry

    # Process all nodes
    for node in texture_nodes:
        label = node.label
        if not label:
            continue
            
        full_path = resolve_image_path(label)
        if not full_path:
            continue

        try:
            # check_existing avoids duplicate image data-blocks
            image = bpy.data.images.load(full_path, check_existing=True)
        except Exception as e:
            logger.exception("Could not load image from %s: %s", full_path, e)
            continue

        node.image = image

        config = resolve_config(label)
        if not config:
            # Apply defaults
            image.colorspace_settings.name = 'Non-Color'
            image.alpha_mode = 'CHANNEL_PACKED'
            node.interpolation = 'Linear'
            node.extension = 'REPEAT'
        else:
            # Apply the configuration
            image.colorspace_settings.name = config.colorSpace
            image.alpha_mode = config.alphaMode
            node.interpolation = config.interpolation
            node.extension = config.extension

@profile_function
def setUvMapConfig(material: bpy.types.Material):
    node_tree = material.node_tree
    uv_map_nodes = [node for node in node_tree.nodes if node.type == 'UVMAP']

    for node in uv_map_nodes:
        label = node.label
        node.uv_map = label
        
@profile_function
def setGroupProperties(material: bpy.types.Material):
    node_tree = material.node_tree
    group_nodes = [node for node in node_tree.nodes if node.type == 'GROUP']

    for group_node in group_nodes:
        group_name = group_node.node_tree.name
        if re.search(r'\.\d+$', group_name):
            group_name = re.sub(r'\.\d+$', '', group_name)

        if group_name not in node_group_configs:
            logger.debug("No config found for group %s.", group_name)
            continue
        
        config = node_group_configs[group_name]
        for mapping in config:
            try:
                mapping.apply(material, group_node)
            except Exception as e:
                logger.exception("Error applying mapping for group %s: %s", group_name, e)