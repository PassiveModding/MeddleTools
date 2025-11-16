from .bake import RunBake
from .panel import MeddleBakePanel, MEDDLE_UL_MaterialBakeList, MEDDLE_OT_InitMaterialSettings, MEDDLE_OT_ClearMaterialSettings
from .atlas import RunAtlas
from .export_fbx import ExportFBX
from .reproject_retile import ReprojectRetile
from .reproject_rebake import ReprojectRebake
from .create_copy_for_baking import CreateCopyForBaking
from .create_uv_bake_layers import CreateUVBakeLayers
from .join_meshes import JoinMeshes

classes = [
	RunBake,
	MEDDLE_UL_MaterialBakeList,
	MEDDLE_OT_InitMaterialSettings,
	MEDDLE_OT_ClearMaterialSettings,
	MeddleBakePanel,
	RunAtlas,
	ExportFBX,
	ReprojectRetile,
	ReprojectRebake,
	CreateCopyForBaking,
	CreateUVBakeLayers,
	JoinMeshes,
]
