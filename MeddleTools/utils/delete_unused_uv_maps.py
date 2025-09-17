import bpy
import logging
from bpy.types import Operator

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

class DeleteUnusedUvMaps(Operator):
    """Checks materials used by a mesh, deleting all uvmaps greater than the default which are not referenced"""
    bl_idname = "meddle.delete_unused_uvmaps"
    bl_label = "Delete Unused UV Maps"
    bl_description = "Delete unused UV maps from selected mesh objects that are not referenced by any material"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Get selected mesh objects
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        # Iterate over selected meshes and their materials
        removed_count = 0
        for mesh in selected_meshes:
            mesh_uv_maps = [uv for uv in mesh.data.uv_layers if uv.name != "UVMap"]
            if len(mesh_uv_maps) == 0:
                continue

            referenced_uv_maps = []
            for slot in mesh.material_slots:
                if not slot.material:
                    continue

                node_tree = slot.material.node_tree
                uv_map_nodes = [node for node in node_tree.nodes if node.type == 'UVMAP']
                for uv_map in uv_map_nodes:
                    referenced_uv_maps.append(uv_map.uv_map)

            # remove all in mesh_uv_maps which are not in referenced_uv_maps
            for uv in mesh_uv_maps:
                if uv.name not in referenced_uv_maps:
                    mesh.data.uv_layers.remove(uv)
                    removed_count += 1

        self.report({'INFO'}, f"Removed {removed_count} unused UV maps from selected meshes")

        return {'FINISHED'}