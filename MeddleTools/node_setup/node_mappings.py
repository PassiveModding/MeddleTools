import os
import bpy
import idprop.types
import os.path as path
import re
import logging
from typing import Callable, List, Tuple, Union, Any

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

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

class VectorMapping:
    def __init__(self, prop_name: str, field_name: str, destination_size: int, value_offset: int = 0):
        self.prop_name = prop_name
        self.field_name = field_name
        self.destination_size = destination_size
        self.value_offset = value_offset

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
            if self.value_offset > 0:
                prop_list = prop_list[self.value_offset:]            
            while len(prop_list) < self.destination_size:
                prop_list.append(0.0)
            if len(prop_list) > self.destination_size:
                prop_list = prop_list[:self.destination_size]
            group_input.default_value = prop_list
        else:
            logger.debug("Unsupported field type %s for %s", group_input.type, self.field_name)

class FloatArraySeparateMapping:
    def __init__(self, prop_name: str, field_names: list[str]):
        self.prop_name = prop_name
        self.field_names = field_names
        
    def apply(self, material_properties: dict, group_node):
        prop_value = material_properties.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return
        
        if not isinstance(prop_value, (list, tuple, idprop.types.IDPropertyArray)):
            logger.debug("Property %s is not an array.", self.prop_name)
            return
        
        for i, field_name in enumerate(self.field_names):
            if field_name not in group_node.inputs:
                logger.info("Field %s not found in group node inputs.", field_name)
                continue
            
            group_input = group_node.inputs.get(field_name)
            if group_input.type == 'VALUE':
                if i < len(prop_value):
                    group_input.default_value = prop_value[i]
                else:
                    logger.info("Index %d out of range for %s", i, self.prop_name)
            else:
                logger.info("Unsupported field type %s for %s", group_input.type, field_name)

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

class ConditionalTextureConfig:
    """Wraps a default TextureNodeConfig with conditional overrides.

    The first matching condition decides the effective config.
    """
    def __init__(
        self,
        default: TextureNodeConfig,
        overrides: List[Tuple[Callable[[bpy.types.Material], bool], TextureNodeConfig]] | None = None,
    ) -> None:
        self.default = default
        self.overrides = overrides or []

    def resolve(self, material: bpy.types.Material) -> TextureNodeConfig:
        for condition, override in self.overrides:
            try:
                if condition(material):
                    return override
            except Exception as e:
                logger.warning("Error evaluating texture override condition on %s: %s", material.name if material else "<None>", e)
        return self.default

class ArrayDefinition:
    def __init__(self, cache_path: str, file_name_pattern: str):
        self.cache_path = cache_path
        self.file_name_pattern = file_name_pattern

def material_condition_equals(**expected: Any) -> Callable[[bpy.types.Material], bool]:
    """Build a condition function that checks material custom properties for equality.

    Example:
        condition = material_condition_equals(ShaderPackage='skin.shpk', GetMaterialValue='GetMaterialValueFace')
    """
    def _check(material: bpy.types.Material) -> bool:
        if material is None:
            return False
        for key, value in expected.items():
            if material.get(key) != value:
                return False
        return True
    return _check


class ColorTableRampLookup:
    def __init__(self, rowPropName: str, rowPropType: str, b_ramp: bool):
        self.rowPropName = rowPropName
        self.rowPropType = rowPropType
        self.b_ramp = b_ramp
        
        
    def apply(self, material: bpy.types.Material, colorRamp, odds_rows=None, evens_rows=None):
        clearRamp(colorRamp)
        if odds_rows is None or evens_rows is None:
            odds, evens = getOddEvenRows(material)
        else:
            odds, evens = odds_rows, evens_rows

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
        
    def apply(self, material: bpy.types.Material, colorRamp, odds_rows=None, evens_rows=None):
        clearRamp(colorRamp)

        if odds_rows is None or evens_rows is None:
            odds, evens = getOddEvenRows(material)
        else:
            odds, evens = odds_rows, evens_rows
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