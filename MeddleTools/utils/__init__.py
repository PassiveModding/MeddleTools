from .instance_meshes import InstanceMeshes
from .find_properties import FindProperties
from .boost_lights import BoostLights
from .join_by_material import JoinByMaterial
from .join_by_distance import JoinByDistance
from .purge_unused import PurgeUnused
from .add_vornoi_texture import AddVoronoiTexture
from .clean_bone_heirarchy import CleanBoneHierarchy
from .import_animation_gltf import ImportAnimationGLTF
from .delete_empty_vertex_groups import DeleteEmptyVertexGroups
from .join_meshes_to_parent import JoinMeshesToParent
from .delete_unused_uv_maps import DeleteUnusedUvMaps
from .remove_bones_by_prefix import RemoveBonesByPrefix
from .set_render_defaults import (SetCyclesDefaults, SetCameraCulling)


classes = [
	FindProperties,
	BoostLights,
	JoinByMaterial,
	JoinByDistance,
	PurgeUnused,
	AddVoronoiTexture,
	CleanBoneHierarchy,
	ImportAnimationGLTF,
	DeleteEmptyVertexGroups,
	JoinMeshesToParent,
	DeleteUnusedUvMaps,
	RemoveBonesByPrefix,
	SetCyclesDefaults,
	SetCameraCulling,
	InstanceMeshes
]
