from dataclasses import dataclass
from enum import Enum


class Strategy(Enum):
    """How a pass gets its pixel data out of the material."""

    # Cycles has a dedicated bake type for this channel.
    NATIVE = 'NATIVE'
    # No dedicated bake type: route the source BSDF input through an
    # Emission shader into the Material Output, then bake EMIT.
    EMIT_CHANNEL = 'EMIT_CHANNEL'


@dataclass(frozen=True)
class BakePassSpec:
    id: str
    label: str
    description: str
    default_enabled: bool
    strategy: Strategy
    bake_type: str                      # bpy.ops.object.bake(type=...)
    background_color: tuple             # image fill before baking
    alpha_mode: str                     # bpy Image.alpha_mode
    colorspace: str                     # bpy Image colorspace name
    pass_filter: frozenset = frozenset()  # e.g. {'COLOR'} to exclude lighting
    source_socket: str = None           # EMIT_CHANNEL only: BSDF input to bake
    rebuild_socket: str = None          # BSDF input the baked image feeds afterwards
    rebuild_alpha_socket: str = None    # BSDF input the image alpha feeds afterwards
    needs_normal_map: bool = False      # route through a Normal Map node instead

    @property
    def toggle_attr(self) -> str:
        return f"bake_{self.id}"


PASSES = (
    BakePassSpec(
        id='diffuse',
        label="Diffuse",
        description="Bake base color (lighting excluded)",
        default_enabled=True,
        strategy=Strategy.NATIVE,
        bake_type='DIFFUSE',
        pass_filter=frozenset({'COLOR'}),
        background_color=(0.0, 0.0, 0.0, 1.0),
        alpha_mode='CHANNEL_PACKED',
        colorspace='sRGB',
        rebuild_socket='Base Color',
        rebuild_alpha_socket='Alpha',
    ),
    BakePassSpec(
        id='normal',
        label="Normal",
        description="Bake tangent-space normals",
        default_enabled=True,
        strategy=Strategy.NATIVE,
        bake_type='NORMAL',
        background_color=(0.5, 0.5, 1.0, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='Non-Color',
        needs_normal_map=True,
    ),
    BakePassSpec(
        id='roughness',
        label="Roughness",
        description="Bake roughness",
        default_enabled=True,
        strategy=Strategy.NATIVE,
        bake_type='ROUGHNESS',
        background_color=(0.5, 0.5, 0.5, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='Non-Color',
        rebuild_socket='Roughness',
    ),
    BakePassSpec(
        id='metallic',
        label="Metallic",
        description="Bake the Metallic input (via an emission rig)",
        default_enabled=True,
        strategy=Strategy.EMIT_CHANNEL,
        bake_type='EMIT',
        source_socket='Metallic',
        background_color=(0.0, 0.0, 0.0, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='Non-Color',
        rebuild_socket='Metallic',
    ),
    BakePassSpec(
        id='glossy',
        label="Glossy",
        description="Bake glossy color (lighting excluded)",
        default_enabled=False,
        strategy=Strategy.NATIVE,
        bake_type='GLOSSY',
        pass_filter=frozenset({'COLOR'}),
        background_color=(0.0, 0.0, 0.0, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='Non-Color',
        rebuild_socket='Specular Tint',
    ),
    BakePassSpec(
        id='transmission',
        label="Transmission",
        description="Bake transmission color (lighting excluded)",
        default_enabled=False,
        strategy=Strategy.NATIVE,
        bake_type='TRANSMISSION',
        pass_filter=frozenset({'COLOR'}),
        background_color=(1.0, 1.0, 1.0, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='Non-Color',
        rebuild_socket='Transmission Weight',
    ),
    BakePassSpec(
        id='emission',
        label="Emission",
        description="Bake emission",
        default_enabled=True,
        strategy=Strategy.NATIVE,
        bake_type='EMIT',
        background_color=(0.0, 0.0, 0.0, 1.0),
        alpha_mode='STRAIGHT',
        colorspace='sRGB',
        rebuild_socket='Emission Color',
        rebuild_alpha_socket='Emission Strength',
    ),
)

PASS_MAP = {spec.id: spec for spec in PASSES}

# Inputs of the rebuilt (post-bake) Principled BSDF that are not fed by a
# baked image. Matches the legacy bake defaults.
REBUILT_BSDF_DEFAULTS = {
    'IOR': 1.2,
    'Metallic': 0.0,
    'Roughness': 0.5,
    'Base Color': (1.0, 1.0, 1.0, 1.0),
    'Emission Color': (1.0, 1.0, 1.0, 1.0),
    'Emission Strength': 0.0,
}


def enabled_passes(settings):
    return [spec for spec in PASSES if getattr(settings, spec.toggle_attr, False)]
