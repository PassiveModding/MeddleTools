import bpy
import idprop.types
import logging
from typing import Callable, List, Tuple, Any
from ..utils import helpers

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass


class NodeGroupMapping:
    """Copies a material custom property onto a single node group input.

    Handles the shared lookup/validation flow: fetch the custom property,
    find the target input socket, and check its type. Subclasses declare
    the socket type they write to and implement set_value() for the
    actual assignment.
    """

    expected_socket_type: str | None = None

    def __init__(self, prop_name: str, field_name: str):
        self.prop_name = prop_name
        self.field_name = field_name

    def apply(self, material: bpy.types.Material, group_node: bpy.types.Node):
        prop_value = material.get(self.prop_name)
        if not prop_value:
            logger.debug("Property %s not found in material properties.", self.prop_name)
            return

        group_input = group_node.inputs.get(self.field_name)
        if group_input is None:
            logger.debug("Field %s not found in group node inputs.", self.field_name)
            return

        if self.expected_socket_type is not None and group_input.type != self.expected_socket_type:
            logger.debug("Unsupported field type %s for %s", group_input.type, self.field_name)
            return

        self.set_value(group_input, prop_value)

    def set_value(self, group_input, prop_value):
        raise NotImplementedError


class ColorMapping(NodeGroupMapping):
    expected_socket_type = 'RGBA'

    def set_value(self, group_input, prop_value):
        group_input.default_value = helpers.toBlenderColor(prop_value)


class FloatMapping(NodeGroupMapping):
    expected_socket_type = 'VALUE'

    def __init__(self, prop_name: str, field_name: str, field_index: int = 0):
        super().__init__(prop_name, field_name)
        self.field_index = field_index

    def set_value(self, group_input, prop_value):
        # if prop_value is array, index using field_index, otherwise, use value as-is
        if isinstance(prop_value, (list, tuple, idprop.types.IDPropertyArray)):
            if self.field_index < len(prop_value):
                group_input.default_value = prop_value[self.field_index]
            else:
                logger.debug("Index %d out of range for %s", self.field_index, self.prop_name)
        else:
            group_input.default_value = prop_value


class FloatArrayMapping(NodeGroupMapping):
    expected_socket_type = 'VECTOR'

    def set_value(self, group_input, prop_value):
        prop_list = prop_value.to_list()
        while len(prop_list) < 3:
            prop_list.append(0.0)
        group_input.default_value = prop_list


class VectorMapping(NodeGroupMapping):
    expected_socket_type = 'VECTOR'

    def __init__(self, prop_name: str, field_name: str, destination_size: int, value_offset: int = 0):
        super().__init__(prop_name, field_name)
        self.destination_size = destination_size
        self.value_offset = value_offset

    def set_value(self, group_input, prop_value):
        prop_list = prop_value.to_list()
        if self.value_offset > 0:
            prop_list = prop_list[self.value_offset :]
        while len(prop_list) < self.destination_size:
            prop_list.append(0.0)
        if len(prop_list) > self.destination_size:
            prop_list = prop_list[: self.destination_size]
        group_input.default_value = prop_list


class MaterialKeyMapping(NodeGroupMapping):
    """Sets a boolean-style input when a custom property equals an expected value."""

    def __init__(self, prop_name: str, prop_value: str, field_name: str, value_if_present: bool = True):
        super().__init__(prop_name, field_name)
        self.prop_value = prop_value
        self.value_if_present = value_if_present

    def set_value(self, group_input, prop_value):
        if prop_value != self.prop_value:
            return
        group_input.default_value = self.value_if_present


class FloatArraySeparateMapping:
    """Spreads the elements of an array property across multiple float inputs."""

    def __init__(self, prop_name: str, field_names: list[str]):
        self.prop_name = prop_name
        self.field_names = field_names

    def apply(self, material: bpy.types.Material, group_node: bpy.types.Node):
        prop_value = material.get(self.prop_name)
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


class UvScrollMapping:
    def apply(self, material: bpy.types.Material, group_node: bpy.types.Node):
        if '0x9A696A17' not in material:
            return

        if 'Multiplier' not in group_node.inputs:
            return

        scrollAmount = material['0x9A696A17']

        multiplier_values = None
        if group_node.label == 'UV0Scroll':
            multiplier_values = [scrollAmount[0] * -1, scrollAmount[1], 0.0]
        elif group_node.label == 'UV1Scroll':
            multiplier_values = [scrollAmount[2] * -1, scrollAmount[3], 0.0]

        if multiplier_values is None:
            return

        group_node.inputs['Multiplier'].default_value = multiplier_values


class TextureNodeConfig:
    """Settings applied to an image texture node and its image.

    Defaults match the most common Meddle sampler setup; only deviations
    need to be specified.
    """

    def __init__(
        self,
        colorSpace: str = 'Non-Color',
        alphaMode: str = 'CHANNEL_PACKED',
        interpolation: str = 'Linear',
        extension: str = 'REPEAT',
    ):
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
                logger.warning(
                    "Error evaluating texture override condition on %s: %s", material.name if material else "<None>", e
                )
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


class PackedColorTableRampLookup:
    """Fills a color ramp from color-table rows, packing one or more row
    properties into the RGBA channels of each ramp element.
    """

    def __init__(self, rowNameTypeMaps: list[tuple[str, str]], b_ramp: bool):
        self.rowNameTypeMaps = rowNameTypeMaps
        self.b_ramp = b_ramp

    def apply(self, material: bpy.types.Material, colorRamp, odds_rows=None, evens_rows=None):
        clearRamp(colorRamp)

        if odds_rows is None or evens_rows is None:
            odds_rows, evens_rows = getOddEvenRows(material)
        rows = odds_rows if self.b_ramp else evens_rows

        for i, row in enumerate(rows):
            missing = [name for name, _ in self.rowNameTypeMaps if name not in row]
            if missing:
                logger.debug("Row %d missing properties %s, skipping.", i, missing)
                continue

            row_values = []
            for rowPropName, rowPropType in self.rowNameTypeMaps:
                row_values.extend(getValuesForType(row, rowPropName, rowPropType))
            row_values = helpers.toBlenderColor(row_values)

            try:
                if i == 0:
                    colorRamp.color_ramp.elements[0].position = i / len(rows)
                    colorRamp.color_ramp.elements[0].color = row_values
                else:
                    element = colorRamp.color_ramp.elements.new(i / len(rows))
                    element.color = row_values
            except Exception as e:
                logger.warning("Error setting color for row %d: %s", i, e)


class ColorTableRampLookup(PackedColorTableRampLookup):
    """Single-property variant of PackedColorTableRampLookup."""

    def __init__(self, rowPropName: str, rowPropType: str, b_ramp: bool):
        super().__init__([(rowPropName, rowPropType)], b_ramp)


def getValuesForType(row, rowProp, type):
    def convertValue(val):
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
        return [
            convertValue(row[rowProp]['UU']),
            convertValue(row[rowProp]['UV']),
            convertValue(row[rowProp]['VU']),
            convertValue(row[rowProp]['VV']),
        ]
    else:
        raise Exception(f"Unsupported type {type}")


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
