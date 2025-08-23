import bpy
import logging
from bpy.types import Operator
import os

# Module logger - operators still use self.report for user-facing messages
logger = logging.getLogger(__name__)
try:
    # Avoid 'No handler found' warnings in library usage
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

# Helper: safely deselect all objects without relying on operators (avoids context poll failures)
def _safe_deselect_all_objects(context: bpy.types.Context):
    try:
        for ob in context.view_layer.objects:
            try:
                ob.select_set(False)
            except Exception:
                pass
    except Exception:
        # Fallback: try currently selected objects
        for ob in list(getattr(context, 'selected_objects', [])):
            try:
                ob.select_set(False)
            except Exception:
                pass


# Shared helpers to reduce duplication across operators
def ensure_object_mode(context: bpy.types.Context, mode: str = 'OBJECT'):
    """Ensure the active object is in the specified mode (default: OBJECT).
    This wraps the common pattern of checking and calling the operator.
    """
    try:
        obj = context.object
        if obj and obj.mode != mode:
            bpy.ops.object.mode_set(mode=mode)
    except Exception:
        # Best-effort; if it fails, don't raise
        pass


def get_selected_meshes(context: bpy.types.Context, edit_mode_as_active: bool = False):
    """Return a list of selected mesh objects. If edit_mode_as_active is True and
    the active object is in EDIT mode, return only the active mesh (common UI case).
    """
    try:
        if edit_mode_as_active and context.object and context.object.mode == 'EDIT' and context.object.type == 'MESH':
            return [context.object]
    except Exception:
        pass
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def vertex_group_has_weights(mesh_obj, vertex_group):
    """Return True if the specified vertex_group has any vertex with weight > 0.
    Shared between multiple operators to avoid duplicated implementations.
    """
    mesh = mesh_obj.data
    group_index = vertex_group.index
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == group_index and g.weight > 0.0:
                return True
    return False


def cleanup_imported_objects(imported_objects):
    """Safely remove imported objects and their data-blocks. Non-fatal on errors."""
    for obj in imported_objects:
        try:
            if obj.type == 'MESH' and obj.data:
                bpy.data.meshes.remove(obj.data, do_unlink=True)
            elif obj.type == 'ARMATURE' and obj.data:
                bpy.data.armatures.remove(obj.data, do_unlink=True)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass

class FindProperties(Operator):
    """Find materials with specific custom properties"""
    bl_idname = "meddle.find_properties"
    bl_label = "Find Properties"
    bl_description = "Search for materials containing the specified property"
    
    def execute(self, context):
        search_value = context.scene.meddle_settings.search_property
        
        if not search_value:
            self.report({'WARNING'}, "Please enter a property to search for")
            return {'CANCELLED'}
        
        matching_materials = []
        
        # Iterate through all materials in the blend file
        for material in bpy.data.materials:
            # Check if the search value exists as a custom property
            if search_value in material:
                matching_materials.append({
                    'material': material.name,
                    'property': search_value,
                    'value': material[search_value]
                })
        
        if matching_materials:
            self.report({'INFO'}, f"Found {len(matching_materials)} material(s) with '{search_value}'")
            logger.info("Searching for materials containing '%s' in custom properties...", search_value)
            for match in matching_materials:
                logger.info("Material: '%s' - %s = %r", match['material'], match['property'], match['value'])
        else:
            self.report({'INFO'}, f"No materials found containing '{search_value}' in their custom properties")
        
        return {'FINISHED'}

class DeleteEmptyVertexGroups(Operator):
    """Delete vertex groups that have no vertex weights from selected mesh objects"""
    bl_idname = "meddle.delete_empty_vertex_groups"
    bl_label = "Delete Empty Vertex Groups"
    bl_description = "Remove vertex groups from selected mesh objects that have no vertices assigned (weight == 0)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure object mode
        ensure_object_mode(context, 'OBJECT')

        selected_meshes = get_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        total_removed = 0
        for obj in selected_meshes:
            removed_this_obj = 0

            # Fast-path: if there are no vertex groups, skip
            vg_count = len(obj.vertex_groups)
            if vg_count == 0:
                continue

            # Build a boolean list marking which vertex groups have any weight > 0
            # This iterates vertices only once (O(#vertices + #groups)) instead of
            # checking every group against all vertices (O(#groups * #vertices)).
            has_weight = [False] * vg_count
            try:
                mesh = obj.data
                for v in mesh.vertices:
                    for g in v.groups:
                        gi = g.group
                        if 0 <= gi < vg_count and g.weight > 0.0:
                            has_weight[gi] = True
                # Collect groups to remove (use list to avoid mutating while iterating)
                to_remove = [vg for vg in obj.vertex_groups if vg.index < vg_count and not has_weight[vg.index]]

                for vg in to_remove:
                    try:
                        obj.vertex_groups.remove(vg)
                        removed_this_obj += 1
                    except Exception:
                        # Ignore failures to remove a specific group
                        pass
            except Exception:
                # If anything goes wrong accessing mesh data, skip this object defensively
                removed_this_obj = 0

            if removed_this_obj > 0:
                logger.info("Removed %d empty vertex group(s) from '%s'", removed_this_obj, obj.name)
            total_removed += removed_this_obj

        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} empty vertex group(s) from selected meshes")
        else:
            self.report({'INFO'}, "No empty vertex groups found on selected meshes")
        return {'FINISHED'}

    def vertex_group_has_weights(self, mesh_obj, vertex_group):
        """Return True if the vertex group has any vertex with weight > 0"""
        return vertex_group_has_weights(mesh_obj, vertex_group)

class BoostLights(Operator):
    """Boost all area, spot, and point lights by specified factor"""
    bl_idname = "meddle.boost_lights"
    bl_label = "Boost Lights"
    bl_description = "Boost the power of all area, spot, and point lights by the specified factor"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        boost_factor = context.scene.meddle_settings.light_boost_factor
        
        # Define the light types we want to boost
        target_light_types = {'AREA', 'SPOT', 'POINT'}
        
        # Counter for boosted lights
        boosted_count = 0
        
        # Iterate through all objects in the scene
        for obj in bpy.context.scene.objects:
            # Check if the object is a light and of the target types
            if obj.type == 'LIGHT' and obj.data.type in target_light_types:
                # Store the original power for reference
                original_power = obj.data.energy
                
                # Boost the light power by the specified factor
                obj.data.energy *= boost_factor
                
                # Log info about the boosted light
                logger.info("Boosted %s light '%s': %s -> %s", obj.data.type, obj.name, original_power, obj.data.energy)
                
                boosted_count += 1
        
        if boosted_count > 0:
            self.report({'INFO'}, f"Successfully boosted {boosted_count} lights by {boost_factor}x")
            logger.info("Successfully boosted %d lights by %sx", boosted_count, boost_factor)
        else:
            self.report({'WARNING'}, "No area, spot, or point lights found in the scene")
        
        return {'FINISHED'}

class JoinByMaterial(Operator):
    """Join meshes that share the same material as the active object's active material"""
    bl_idname = "meddle.join_by_material"
    bl_label = "Join by Selected Material"
    bl_description = "Join mesh objects that use the same material as the active object's active material"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Work with selected mesh objects and group them by material
        ensure_object_mode(context, 'OBJECT')

        selected_meshes = get_selected_meshes(context)
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        # Map material name -> set of objects that use it
        mat_to_objs = {}
        for obj in selected_meshes:
            try:
                for slot in getattr(obj, 'material_slots', []):
                    mat = getattr(slot, 'material', None)
                    if mat is None:
                        continue
                    key = mat.name
                    if key not in mat_to_objs:
                        mat_to_objs[key] = {
                            'material': mat,
                            'objects': set()
                        }
                    mat_to_objs[key]['objects'].add(obj)
            except Exception:
                logger.exception("Error while checking material slots for object '%s'", getattr(obj, 'name', '<unknown>'))

        # Only perform joins for material groups with 2 or more objects
        join_groups = [v for v in mat_to_objs.values() if len(v['objects']) >= 2]
        if not join_groups:
            self.report({'INFO'}, "No groups of selected meshes share the same material — nothing to join")
            return {'CANCELLED'}

        total_joined = 0
        original_active = context.view_layer.objects.active

        for group in join_groups:
            objs = list(group['objects'])
            # Deselect all then select group's objects
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except Exception:
                _safe_deselect_all_objects(context)

            for o in objs:
                try:
                    o.select_set(True)
                except Exception:
                    logger.warning("Could not select object '%s' for join", getattr(o, 'name', '<unknown>'))

            # Prefer previous active if it's part of the group
            if original_active in objs:
                context.view_layer.objects.active = original_active
            else:
                context.view_layer.objects.active = objs[0]

            # Ensure object mode and attempt join
            ensure_object_mode(context, 'OBJECT')
            try:
                bpy.ops.object.join()
                joined_count = len(objs)
                total_joined += joined_count
                logger.info("Joined %d objects using material '%s'", joined_count, group['material'].name)
            except Exception as e:
                logger.exception("Failed to join objects for material '%s': %s", group['material'].name, str(e))
                # continue with other groups
                continue

        # Restore a sensible selection: select the active object if still present
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            _safe_deselect_all_objects(context)
        if context.view_layer.objects.active and context.view_layer.objects.active.name in bpy.data.objects:
            try:
                context.view_layer.objects.active.select_set(True)
            except Exception:
                pass

        if total_joined > 0:
            self.report({'INFO'}, f"Joined {total_joined} objects across {len(join_groups)} material group(s)")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No objects were joined")
            return {'CANCELLED'}

class JoinByDistance(Operator):
    """Join meshes within selected objects by merging nearby vertices"""
    bl_idname = "meddle.join_by_distance"
    bl_label = "Join by Distance"
    bl_description = "Merge vertices within the specified distance for selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        merge_distance = context.scene.meddle_settings.merge_distance
        
        # Store the current mode and active object
        original_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
        original_active = bpy.context.view_layer.objects.active
        
        # Get selected mesh objects based on current mode
        if original_mode == 'EDIT':
            # In edit mode, work with the active object only
            if bpy.context.object and bpy.context.object.type == 'MESH':
                selected_objects = [bpy.context.object]
            else:
                self.report({'WARNING'}, "No mesh object in edit mode")
                return {'CANCELLED'}
        else:
            # In object mode, work with all selected mesh objects
            selected_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            
            if not selected_objects:
                self.report({'WARNING'}, "No mesh objects selected")
                return {'CANCELLED'}
        
        processed_count = 0
        
        for obj in selected_objects:
            # Set the object as active
            bpy.context.view_layer.objects.active = obj
            
            # Enter edit mode if not already in it
            if bpy.context.object.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Select all vertices
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Merge by distance
            bpy.ops.mesh.remove_doubles(threshold=merge_distance)
            
            processed_count += 1
            logger.info("Processed object '%s' with merge distance %s", obj.name, merge_distance)
        
        # Restore original mode and active object
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=original_mode)
        
        if original_active:
            bpy.context.view_layer.objects.active = original_active
        
        self.report({'INFO'}, f"Processed {processed_count} objects with merge distance {merge_distance}")
        
        return {'FINISHED'}

class JoinMeshesToParent(Operator):
    """Join selected mesh objects into their mesh parent to reduce object count.
    Groups selected children by their parent and performs a join per-parent.
    """
    bl_idname = "meddle.join_meshes_to_parent"
    bl_label = "Join Meshes to Parent"
    bl_description = "Join selected mesh children into their parent object to optimize performance"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_object_mode(context, 'OBJECT')

        # Collect selected mesh objects that have a mesh parent
        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        # Group children by parent object
        groups = {}
        for obj in selected_meshes:
            parent = getattr(obj, 'parent', None)
            if parent and parent.type == 'MESH' and parent.name in bpy.data.objects:
                if parent not in groups:
                    groups[parent] = []
                # avoid attempting to join the parent to itself
                if obj != parent:
                    groups[parent].append(obj)

        if not groups:
            self.report({'INFO'}, "No selected meshes have a mesh parent to join into")
            return {'CANCELLED'}

        total_joined = 0

        # Perform join for each parent group
        for parent, children in groups.items():
            if not children:
                continue

            # Deselect everything, then select parent and its children
            bpy.ops.object.select_all(action='DESELECT')
            try:
                parent.select_set(True)
            except Exception:
                # If we can't select the parent, skip
                logger.warning("Could not select parent '%s'", getattr(parent, 'name', '<unknown>'))
                continue

            for c in children:
                try:
                    c.select_set(True)
                except Exception:
                    logger.warning("Could not select child '%s'", getattr(c, 'name', '<unknown>'))

            # Make parent the active object
            try:
                context.view_layer.objects.active = parent
            except Exception:
                logger.warning("Could not make '%s' active", getattr(parent, 'name', '<unknown>'))

            # Ensure object mode and join
            ensure_object_mode(context, 'OBJECT')
            try:
                bpy.ops.object.join()
                joined_count = len(children)
                total_joined += joined_count
                logger.info("Joined %d child(ren) into parent '%s'", joined_count, parent.name)
            except Exception as e:
                logger.exception("Failed to join children into parent '%s': %s", getattr(parent, 'name', '<unknown>'), str(e))
                # attempt to continue with other groups
                continue

        # Restore selection to parents that remain
        bpy.ops.object.select_all(action='DESELECT')
        for parent in groups.keys():
            try:
                if parent.name in bpy.data.objects:
                    parent.select_set(True)
            except Exception:
                pass

        if total_joined > 0:
            self.report({'INFO'}, f"Joined {total_joined} objects into their parents")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No meshes were joined to parents")
            return {'CANCELLED'}

class PurgeUnused(Operator):
    """Remove all unused datablocks from the scene"""
    bl_idname = "meddle.purge_unused"
    bl_label = "Purge Unused Data"
    bl_description = "Remove all unused materials, textures, meshes, and other datablocks to optimize the file"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Store initial counts for reporting
        initial_counts = {}
        final_counts = {}
        
        # Get initial counts of different data types
        data_types = [
            ('materials', bpy.data.materials),
            ('textures', bpy.data.textures),
            ('images', bpy.data.images),
            ('meshes', bpy.data.meshes),
            ('curves', bpy.data.curves),
            ('fonts', bpy.data.fonts),
            ('node_groups', bpy.data.node_groups),
            ('actions', bpy.data.actions),
            ('armatures', bpy.data.armatures)
        ]
        
        for name, data_collection in data_types:
            initial_counts[name] = len(data_collection)
        
        # Perform multiple purge passes to catch interdependent unused data
        purge_passes = 3
        total_removed = 0
        
        for pass_num in range(purge_passes):
            removed_this_pass = 0
            
            # Purge each data type
            for name, data_collection in data_types:
                before_count = len(data_collection)
                
                # Remove unused datablocks
                for item in list(data_collection):
                    if item.users == 0:
                        try:
                            data_collection.remove(item)
                            removed_this_pass += 1
                        except:
                            # Some items might not be removable
                            pass
                
                after_count = len(data_collection)
                pass_removed = before_count - after_count
                
                if pass_removed > 0:
                    logger.info("Pass %d: Removed %d unused %s", pass_num + 1, pass_removed, name)
            
            total_removed += removed_this_pass
            
            # If nothing was removed this pass, we can stop early
            if removed_this_pass == 0:
                break
        
        # Get final counts
        for name, data_collection in data_types:
            final_counts[name] = len(data_collection)
        
        # Report summary
        if total_removed > 0:
            self.report({'INFO'}, f"Purged {total_removed} unused datablocks")
            logger.info("=== Purge Unused Data Summary ===")
            logger.info("Total datablocks removed: %d", total_removed)
            for name, _ in data_types:
                removed = initial_counts[name] - final_counts[name]
                if removed > 0:
                    logger.info("  %s: %d removed (%d → %d)", name.title(), removed, initial_counts[name], final_counts[name])
            logger.info("%s", "=" * 35)
        else:
            self.report({'INFO'}, "No unused datablocks found to remove")
        
        return {'FINISHED'}

class AddVoronoiTexture(Operator):
    """Add voronoi texture setup for background objects"""
    bl_idname = "meddle.add_voronoi_texture"
    bl_label = "Apply Terrain Voronoi"
    bl_description = "Add voronoi texture setup for selected terrain objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        processed_count = 0
        
        # Apply voronoi to all selected objects
        for obj in context.selected_objects:
            if obj is None or obj.type != 'MESH':
                continue
            
            # Get the material slots
            for slot in obj.material_slots:
                if slot.material is not None:
                    result = self.add_voronoi_texture(slot.material)
                    if result == {'FINISHED'}:
                        processed_count += 1
        
        if processed_count > 0:
            self.report({'INFO'}, f"Applied Voronoi texture to {processed_count} materials")
        else:
            self.report({'WARNING'}, "No materials processed (no selected mesh objects or materials already have Voronoi)")
                    
        return {'FINISHED'}
    
    def add_voronoi_texture(self, mat):
        """Add voronoi texture setup to a material"""
        if mat is None or not mat.use_nodes:
            return {'CANCELLED'}
        
        # If already has voronoi texture, do nothing
        if any(node.type == 'TEX_VORONOI' for node in mat.node_tree.nodes):
            logger.info("Material %s already has a voronoi texture.", mat.name)
            return {'CANCELLED'}
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Create nodes
        uvMapNode = nodes.new('ShaderNodeUVMap')
        uvMapNode.uv_map = 'UVMap'
        uvMapNode.location = (-500, 0)
        
        voronoiTexture = nodes.new('ShaderNodeTexVoronoi')
        voronoiTexture.location = (-300, 0)
        
        vectorMapping = nodes.new('ShaderNodeMapping')
        vectorMapping.location = (0, 0)
        
        # Link the nodes
        links.new(uvMapNode.outputs['UV'], vectorMapping.inputs['Vector'])
        links.new(uvMapNode.outputs['UV'], voronoiTexture.inputs['Vector'])
        links.new(voronoiTexture.outputs['Color'], vectorMapping.inputs['Rotation'])
        
        # Get texture nodes for the material
        textureNodes = [node for node in nodes if node.type == 'TEX_IMAGE']
        
        # Link the voronoi texture to the texture nodes
        for texNode in textureNodes:
            if texNode is None:
                continue
            
            # Check if the texture node has an input for vector
            if 'Vector' in texNode.inputs:
                links.new(vectorMapping.outputs['Vector'], texNode.inputs['Vector'])
            else:
                logger.warning("Texture node %s does not have a Vector input.", texNode.name)
        
        return {'FINISHED'}

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

class CleanBoneHierarchy(Operator):
    """Remove unused bones from armatures that don't affect any vertices"""
    bl_idname = "meddle.clean_bone_hierarchy"
    bl_label = "Clean Bone Hierarchy"
    bl_description = "Remove unused bones from selected armatures that don't affect any vertices"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        # Determine target armatures: prefer selected, fallback to active armature
        armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
        if not armatures and context.active_object and context.active_object.type == 'ARMATURE':
            armatures = [context.active_object]

        if not armatures:
            self.report({'WARNING'}, "No armature selected")
            return {'CANCELLED'}

        total_removed = 0

        for arm_obj in armatures:
            used_bones = set()

            # Cache bone name set for quick membership checks
            try:
                arm_bone_names = set(b.name for b in arm_obj.data.bones)
            except Exception:
                arm_bone_names = set()

            # Iterate only meshes that reference this armature via an armature modifier
            for obj in (o for o in bpy.data.objects if o.type == 'MESH'):
                try:
                    # Quick check for armature modifier referencing this armature
                    mods = getattr(obj, 'modifiers', None)
                    if not mods:
                        continue
                    is_skinned = False
                    for mod in mods:
                        # avoid attribute errors by guarded access
                        if getattr(mod, 'type', None) == 'ARMATURE' and getattr(mod, 'object', None) == arm_obj:
                            is_skinned = True
                            break
                    if not is_skinned:
                        continue

                    mesh = obj.data
                    if mesh is None:
                        continue

                    # Build index->bone-name mapping only for groups whose names exist on the armature
                    vg_index_to_name = {}
                    for vg in obj.vertex_groups:
                        try:
                            if vg.name in arm_bone_names:
                                vg_index_to_name[vg.index] = vg.name
                        except Exception:
                            # Defensive: skip problematic groups
                            pass

                    if not vg_index_to_name:
                        continue

                    # Scan vertices once and mark used bone names when weight > 0
                    # Early exit if we've found all possible names referenced by this mesh
                    needed = set(vg_index_to_name.values())
                    for v in mesh.vertices:
                        for g in v.groups:
                            if g.weight > 0.0:
                                name = vg_index_to_name.get(g.group)
                                if name:
                                    used_bones.add(name)
                                    # If we've collected all we can from this mesh, stop
                                    if used_bones >= needed:
                                        break
                        if used_bones >= needed:
                            break
                except Exception:
                    # Defensive: skip problematic meshes/modifiers rather than failing
                    continue

            # Prepare to remove unused edit bones. Switch to edit mode once per armature.
            prev_active = context.view_layer.objects.active
            try:
                context.view_layer.objects.active = arm_obj
                ensure_object_mode(context, 'OBJECT')
                bpy.ops.object.mode_set(mode='EDIT')
            except Exception:
                # If we can't enter edit mode, skip this armature
                logger.warning("Could not enter edit mode for armature '%s'", arm_obj.name)
                if prev_active:
                    context.view_layer.objects.active = prev_active
                continue

            removed_this_arm = 0
            ebones = arm_obj.data.edit_bones

            # Build a set of bone names to keep: any bone that is directly used
            # and all of its ancestors (parents) must be preserved.
            keep_names = set(used_bones)
            bones_ref = arm_obj.data.bones
            for name in list(used_bones):
                try:
                    b = bones_ref.get(name)
                    # Walk parent chain; use a tight loop and local variables
                    while b is not None and b.parent is not None:
                        b = b.parent
                        if b.name in keep_names:
                            break
                        keep_names.add(b.name)
                except Exception:
                    # Defensive: if parent traversal fails for any bone, ignore
                    pass

            # Collect bones to remove (those not in keep_names)
            to_remove = [b for b in list(ebones) if b.name not in keep_names]

            for eb in to_remove:
                try:
                    ebones.remove(eb)
                    removed_this_arm += 1
                except Exception:
                    # Some bones may not be removable in certain situations; ignore
                    pass

            # Return to object mode and restore previous active object
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

            if prev_active and prev_active.name in bpy.data.objects:
                context.view_layer.objects.active = prev_active

            total_removed += removed_this_arm
            if removed_this_arm > 0:
                logger.info("Armature '%s': removed %d unused bone(s)", arm_obj.name, removed_this_arm)

        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} unused bone(s) from armature(s)")
        else:
            self.report({'INFO'}, "No unused bones found on selected armature(s)")

        return {'FINISHED'}
    
class ImportAnimationGLTF(Operator):
    """Import animation GLTF to the selected armature"""
    bl_idname = "meddle.import_animation_gltf"
    bl_label = "Import Animation GLTF"
    bl_description = "Import animation from a GLTF file to the selected armature"
    bl_options = {'REGISTER', 'UNDO'}
    
    # File browser properties
    files: bpy.props.CollectionProperty(name="File Path Collection", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        """Execute the animation import process"""
        # Check if an armature is selected
        target_armature = None
        if context.active_object and context.active_object.type == 'ARMATURE':
            target_armature = context.active_object
        else:
            # Look for selected armatures
            selected_armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
            if selected_armatures:
                target_armature = selected_armatures[0]
        
        if not target_armature:
            self.report({'ERROR'}, "No armature selected. Please select an armature to import animation to.")
            return {'CANCELLED'}
        
        # Make sure only one file is selected
        if len(self.files) != 1:
            self.report({'ERROR'}, "Please select exactly one GLTF file to import.")
            return {'CANCELLED'}

        gltf_file_path = os.path.join(self.directory, self.files[0].name)
        
        # Store temp existing selections
        original_selected = context.selected_objects.copy()
        original_active = context.active_object
        
        try:
            # Clear selection before import (safe)
            _safe_deselect_all_objects(context)
            
            # Import using same logic as gltf_import.py - check import mode first
            logger.info("Importing animation from GLTF: %s", gltf_file_path)
            
            # Use the same import mode as the model import settings
            # if context.scene.meddle_settings.gltf_bone_dir == 'BLENDER':
            #     bpy.ops.import_scene.gltf(filepath=gltf_file_path, disable_bone_shape=True)
            # elif context.scene.meddle_settings.gltf_bone_dir == 'TEMPERANCE':
            # else:
            #     # Default fallback to BLENDER mode
            #     bpy.ops.import_scene.gltf(filepath=gltf_file_path, disable_bone_shape=True)
            
            bpy.ops.import_scene.gltf(filepath=gltf_file_path, bone_heuristic='TEMPERANCE')
            
            # Find imported armatures
            imported_armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
            imported_objects = context.selected_objects.copy()
            
            if not imported_armatures:
                self.report({'WARNING'}, "No armatures found in the imported GLTF file")
                # Clean up imported objects
                cleanup_imported_objects(imported_objects)
                return {'CANCELLED'}
            
            # Hide the imported stuff since we only need the animation
            for obj in imported_objects:
                obj.hide_set(True)
                obj.hide_viewport = True
                obj.hide_render = True
            
            # Apply the imported animation to the selected armature
            animation_applied = False
            
            for imported_armature in imported_armatures:
                if imported_armature.animation_data and imported_armature.animation_data.action:
                    # Get the action from the imported armature
                    imported_action = imported_armature.animation_data.action
                    
                    # Create a copy to avoid it being deleted when we remove the imported armature
                    new_action = imported_action.copy()
                    new_action.name = f"Imported_{imported_action.name}"
                    
                    # Apply the action to the target armature as an NLA strip (Blender 4.0+ best practice)
                    if not target_armature.animation_data:
                        target_armature.animation_data_create()

                    ad = target_armature.animation_data

                    # Get or create a dedicated NLA track for imported animations
                    track_name = "Meddle Imported"
                    base_track = None
                    for t in ad.nla_tracks:
                        if t.name == track_name:
                            base_track = t
                            break
                    if base_track is None:
                        base_track = ad.nla_tracks.new()
                        base_track.name = track_name
                        base_track.mute = False

                    # Determine desired start: current frame if possible (no overlap), else find/create a track with space, else append after last strip
                    act_start, act_end = new_action.frame_range
                    desired_start = int(max(1, round(context.scene.frame_current)))
                    desired_end = desired_start + (act_end - act_start)

                    def has_overlap(track, start, end):
                        for s in track.strips:
                            if not (end <= s.frame_start or start >= s.frame_end):
                                return True
                        return False

                    track_used = base_track
                    start_frame = desired_start
                    # Try base track at current frame
                    if has_overlap(base_track, desired_start, desired_end):
                        # Try to find another existing track with space at current frame
                        found = False
                        for t in ad.nla_tracks:
                            if not has_overlap(t, desired_start, desired_end):
                                track_used = t
                                start_frame = desired_start
                                found = True
                                break
                        if not found:
                            # Create a new track and try at current frame
                            track_used = ad.nla_tracks.new()
                            track_used.name = f"{track_name} (Alt)"
                            start_frame = desired_start
                            # If creation later fails due to constraints, we will append after last strip as fallback
                            pass

                    # If we didn't manage a free slot, append after the last strip of the chosen track
                    if track_used.strips and has_overlap(track_used, start_frame, desired_end):
                        try:
                            last_end = max(s.frame_end for s in track_used.strips)
                        except Exception:
                            last_end = None
                        if last_end is not None and start_frame <= int(last_end):
                            start_frame = int(last_end) + 1

                    # Clear selection on existing strips for clean UI selection
                    for t in ad.nla_tracks:
                        for s in t.strips:
                            s.select = False

                    # Create the strip and select it; if the track has no room per API, create a new track and retry
                    try:
                        new_strip = track_used.strips.new(new_action.name, start_frame, new_action)
                    except Exception:
                        # Fallback: make a fresh track
                        fallback_track = ad.nla_tracks.new()
                        fallback_track.name = f"{track_name} (Alt)"
                        track_used = fallback_track
                        new_strip = fallback_track.strips.new(new_action.name, start_frame, new_action)
                    new_strip.select = True
                    new_strip.mute = False

                    # Clear active action so only NLA plays (prevents double playback)
                    ad.action = None

                    # Optionally extend scene end frame to cover the new strip (leave start unchanged)
                    try:
                        new_end = int(round(new_strip.frame_end))
                        if new_end > context.scene.frame_end:
                            context.scene.frame_end = new_end
                    except Exception:
                        pass

                    logger.info("Applied animation '%s' to armature '%s' as NLA strip '%s' on track '%s' starting at frame %d", new_action.name, target_armature.name, new_strip.name, track_used.name, start_frame)
                    animation_applied = True
                    break
            
            # Clean up the imported objects (we only needed the animation data)
            cleanup_imported_objects(imported_objects)
            
            # Restore previous selection; we'll activate the target armature if import succeeded
            _safe_deselect_all_objects(context)
            for obj in original_selected:
                if obj.name in bpy.data.objects:  # Make sure object still exists
                    obj.select_set(True)
            
            if animation_applied:
                # Ensure the target armature is selected and active so the action slot is visible
                if target_armature and target_armature.name in bpy.data.objects:
                    target_armature.select_set(True)
                    context.view_layer.objects.active = target_armature
                self.report({'INFO'}, f"Successfully imported animation to '{target_armature.name}'")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No animation data found in the imported GLTF file")
                return {'CANCELLED'}
                
        except Exception as e:
            # Restore selection even if there's an error
            _safe_deselect_all_objects(context)
            for obj in original_selected:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active
            
            self.report({'ERROR'}, f"Error importing animation: {str(e)}")
            return {'CANCELLED'}

# List of all utility classes for easy registration
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
]