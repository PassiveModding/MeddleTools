# UV layer produced by the "Create Bake UV Layer" operator (uvprep).
PACKED_UV_LAYER = "MeddlePackedUVs"

# Fallback UV layer name used by Meddle imports.
DEFAULT_UV_LAYER = "UVMap"

# Mesh custom property: layout-preserving bake UVs record how much the
# layout was shrunk to fit 0-1, so the bake image can grow to compensate.
UV_SIZE_SCALE_PROP = "meddle_bake2_size_scale"

# Baked images are named f"{BAKE_IMAGE_PREFIX}{pass_id}_{material.name}.png".
BAKE_IMAGE_PREFIX = "Bake_"

# Subfolder (next to the .blend file) baked images are saved into.
BAKE_OUTPUT_DIR = "Bake"

# Suffix for materials created in 'New Material' output mode.
BAKED_MATERIAL_SUFFIX = ".baked"

# Atlas outputs: images are f"{ATLAS_PREFIX}{pass_id}_{object.name}.png",
# the combined material is f"{ATLAS_PREFIX}{object.name}".
ATLAS_PREFIX = "Atlas_"

# Shared name for every mesh's bake UV layer before an atlas join, so
# Blender's join (which merges UV layers by name) keeps them in one layer.
ATLAS_UV_LAYER = "MeddleAtlasUVs"

# Material output modes (enum values shared by properties, plan and engine).
OUTPUT_NEW_MATERIAL = 'NEW'
OUTPUT_REPLACE_MATERIAL = 'REPLACE'
