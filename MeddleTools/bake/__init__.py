from .bake import RunBake
from .panel import MeddleBakePanel, MEDDLE_OT_InitMaterialSettings, MEDDLE_OT_ClearMaterialSettings
from .atlas import RunAtlas
from .export_fbx import ExportFBX
from .create_copy_for_baking import CreateCopyForBaking
from .create_uv_bake_layers import CreateUVBakeLayers
from .join_meshes import JoinMeshes

classes = [
	RunBake,
	MEDDLE_OT_InitMaterialSettings,
	MEDDLE_OT_ClearMaterialSettings,
	MeddleBakePanel,
	RunAtlas,
	ExportFBX,
	CreateCopyForBaking,
	CreateUVBakeLayers,
	JoinMeshes,
]
