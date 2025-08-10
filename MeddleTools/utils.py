import bpy
from bpy.types import Operator, PropertyGroup
from bpy.props import StringProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper
import os

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

class MeddleUtilsProperties(PropertyGroup):
    """Properties for Meddle utility operations"""
    search_property: StringProperty(
        name="Property Search",
        description="Search for materials containing this property",
        default=""
    )
    
    light_boost_factor: FloatProperty(
        name="Light Boost Factor",
        description="Factor to multiply light power by",
        default=10.0,
        min=0.1,
        max=100.0
    )
    
    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Distance threshold for merging vertices",
        default=0.001,
        min=0.0001,
        max=1.0
    )
    
    animation_gltf_path: StringProperty(
        name="Animation GLTF Path",
        description="Path to the animation GLTF file to import",
        default="",
        subtype='FILE_PATH'
    )

class FindProperties(Operator):
    """Find materials with specific custom properties"""
    bl_idname = "meddle.find_properties"
    bl_label = "Find Properties"
    bl_description = "Search for materials containing the specified property"
    
    def execute(self, context):
        search_value = context.scene.meddle_utils_props.search_property
        
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
            print(f"\nSearching for materials containing '{search_value}' in custom properties...")
            print("-" * 60)
            for match in matching_materials:
                print(f"Material: '{match['material']}' - {match['property']} = {match['value']}")
            print("-" * 60)
        else:
            self.report({'INFO'}, f"No materials found containing '{search_value}' in their custom properties")
        
        return {'FINISHED'}

class BoostLights(Operator):
    """Boost all area, spot, and point lights by specified factor"""
    bl_idname = "meddle.boost_lights"
    bl_label = "Boost Lights"
    bl_description = "Boost the power of all area, spot, and point lights by the specified factor"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        boost_factor = context.scene.meddle_utils_props.light_boost_factor
        
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
                
                # Print info about the boosted light
                print(f"Boosted {obj.data.type} light '{obj.name}': {original_power} -> {obj.data.energy}")
                
                boosted_count += 1
        
        if boosted_count > 0:
            self.report({'INFO'}, f"Successfully boosted {boosted_count} lights by {boost_factor}x")
            print(f"\nSuccessfully boosted {boosted_count} lights by {boost_factor}x")
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
        # Ensure we're in object mode
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        active_obj = bpy.context.view_layer.objects.active
        if not active_obj or active_obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object with the material you want to join by")
            return {'CANCELLED'}

        # Determine the target material: prefer active material, fallback to first slot
        target_mat = active_obj.active_material
        if target_mat is None and active_obj.data.materials:
            target_mat = active_obj.data.materials[0]

        if target_mat is None:
            self.report({'WARNING'}, "Active mesh has no material")
            return {'CANCELLED'}

        target_name = target_mat.name

        # Collect all mesh objects in the scene that use this material in any slot
        candidates = []
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH':
                continue
            try:
                if any(ms.material and ms.material.name == target_name for ms in obj.material_slots):
                    candidates.append(obj)
            except Exception:
                # Defensive: some objects may have problematic slots
                pass

        if len(candidates) < 2:
            self.report({'INFO'}, f"Found {len(candidates)} object(s) using material '{target_name}' — nothing to join")
            return {'CANCELLED'}

        # Deselect all and select only the candidates
        bpy.ops.object.select_all(action='DESELECT')
        for obj in candidates:
            obj.select_set(True)

        # Make a stable active object (prefer the current active if it's in the set)
        if active_obj in candidates:
            bpy.context.view_layer.objects.active = active_obj
        else:
            bpy.context.view_layer.objects.active = candidates[0]

        # Join them
        bpy.ops.object.join()

        self.report({'INFO'}, f"Joined {len(candidates)} objects using material '{target_name}'")
        return {'FINISHED'}

class JoinByMaterialAll(Operator):
    """Join meshes across the scene, per first material group (original behavior)"""
    bl_idname = "meddle.join_by_material_all"
    bl_label = "Join by Material (All in Scene)"
    bl_description = "Join all mesh objects in the scene grouped by their first material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure object mode
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in the scene")
            return {'CANCELLED'}

        # Group by first material name (or "No Material")
        material_groups = {}
        for obj in mesh_objects:
            if obj.data.materials:
                material_name = obj.data.materials[0].name if obj.data.materials[0] else "No Material"
            else:
                material_name = "No Material"
            material_groups.setdefault(material_name, []).append(obj)

        joined_groups = 0
        for material_name, objects in material_groups.items():
            if len(objects) <= 1:
                continue
            bpy.ops.object.select_all(action='DESELECT')
            for obj in objects:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = objects[0]
            bpy.ops.object.join()
            joined_groups += 1
            print(f"Joined {len(objects)} objects with material '{material_name}'")

        if joined_groups > 0:
            self.report({'INFO'}, f"Successfully joined {joined_groups} material groups")
        else:
            self.report({'INFO'}, "No objects to join (each material has only one object)")

        return {'FINISHED'}

class JoinByDistance(Operator):
    """Join meshes within selected objects by merging nearby vertices"""
    bl_idname = "meddle.join_by_distance"
    bl_label = "Join by Distance"
    bl_description = "Merge vertices within the specified distance for selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        merge_distance = context.scene.meddle_utils_props.merge_distance
        
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
            print(f"Processed object '{obj.name}' with merge distance {merge_distance}")
        
        # Restore original mode and active object
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=original_mode)
        
        if original_active:
            bpy.context.view_layer.objects.active = original_active
        
        self.report({'INFO'}, f"Processed {processed_count} objects with merge distance {merge_distance}")
        
        return {'FINISHED'}

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
                    print(f"Pass {pass_num + 1}: Removed {pass_removed} unused {name}")
            
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
            print(f"\n=== Purge Unused Data Summary ===")
            print(f"Total datablocks removed: {total_removed}")
            
            for name, _ in data_types:
                removed = initial_counts[name] - final_counts[name]
                if removed > 0:
                    print(f"  {name.title()}: {removed} removed ({initial_counts[name]} → {final_counts[name]})")
            print("=" * 35)
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
            print(f"Material {mat.name} already has a voronoi texture.")
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
                print(f"Texture node {texNode.name} does not have a Vector input.")
        
        return {'FINISHED'}

class CleanBoneHierarchy(Operator):
    """Remove unused bones from armatures that don't affect any vertices"""
    bl_idname = "meddle.clean_bone_hierarchy"
    bl_label = "Clean Bone Hierarchy"
    bl_description = "Remove unused bones from selected armatures that don't affect any vertices"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Get selected armatures
        selected_armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
        
        if not selected_armatures:
            self.report({'WARNING'}, "No armatures selected")
            return {'CANCELLED'}
        
        total_removed = 0
        
        for armature_obj in selected_armatures:
            removed_count = self.clean_armature(armature_obj)
            total_removed += removed_count
            
            if removed_count > 0:
                print(f"Removed {removed_count} unused bones from '{armature_obj.name}'")
        
        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} unused bones from {len(selected_armatures)} armature(s)")
        else:
            self.report({'INFO'}, "No unused bones found to remove")
        
        return {'FINISHED'}
    
    def clean_armature(self, armature_obj):
        """Clean unused bones from a single armature"""
        if not armature_obj or armature_obj.type != 'ARMATURE':
            return 0
        
        armature_data = armature_obj.data
        
        # Find all meshes that use this armature
        mesh_objects = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                # Check if this mesh has an armature modifier pointing to our armature
                for modifier in obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == armature_obj:
                        mesh_objects.append(obj)
                        break
        
        # If no meshes use this armature, we can't determine which bones are used
        if not mesh_objects:
            print(f"No meshes found using armature '{armature_obj.name}'")
            return 0
        
        # Collect all vertex groups used by the meshes
        used_vertex_groups = set()
        for mesh_obj in mesh_objects:
            for vertex_group in mesh_obj.vertex_groups:
                # Check if the vertex group actually has vertices assigned
                if self.vertex_group_has_vertices(mesh_obj, vertex_group):
                    used_vertex_groups.add(vertex_group.name)
        
        # Switch to Edit mode for the armature
        original_active = bpy.context.view_layer.objects.active
        original_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
        
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Find bones to remove (bones not in used vertex groups)
        bones_to_remove = []
        for bone in armature_data.edit_bones:
            # Keep bones that have corresponding vertex groups
            if bone.name not in used_vertex_groups:
                # Also keep bones that have children (they might be important for hierarchy)
                if not bone.children:
                    bones_to_remove.append(bone.name)
        
        # Remove the unused bones
        removed_count = 0
        for bone_name in bones_to_remove:
            if bone_name in armature_data.edit_bones:
                bone = armature_data.edit_bones[bone_name]
                armature_data.edit_bones.remove(bone)
                removed_count += 1
                print(f"  Removed unused bone: '{bone_name}'")
        
        # Return to original mode and active object
        bpy.ops.object.mode_set(mode='OBJECT')
        if original_active:
            bpy.context.view_layer.objects.active = original_active
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)
        
        return removed_count
    
    def vertex_group_has_vertices(self, mesh_obj, vertex_group):
        """Check if a vertex group has any vertices assigned to it"""
        mesh = mesh_obj.data
        group_index = vertex_group.index
        
        for vertex in mesh.vertices:
            for group in vertex.groups:
                if group.group == group_index and group.weight > 0.0:
                    return True
        return False

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
            print(f"Importing animation from GLTF: {gltf_file_path}")
            
            # Use the same import mode as the model import settings
            if context.scene.model_import_settings.gltfImportMode == 'BLENDER':
                bpy.ops.import_scene.gltf(filepath=gltf_file_path, disable_bone_shape=True)
            elif context.scene.model_import_settings.gltfImportMode == 'TEMPERANCE':
                bpy.ops.import_scene.gltf(filepath=gltf_file_path, bone_heuristic='TEMPERANCE')
            else:
                # Default fallback to BLENDER mode
                bpy.ops.import_scene.gltf(filepath=gltf_file_path, disable_bone_shape=True)
            
            # Find imported armatures
            imported_armatures = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
            imported_objects = context.selected_objects.copy()
            
            if not imported_armatures:
                self.report({'WARNING'}, "No armatures found in the imported GLTF file")
                # Clean up imported objects
                for obj in imported_objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
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

                    print(f"Applied animation '{new_action.name}' to armature '{target_armature.name}' as NLA strip '{new_strip.name}' on track '{track_used.name}' starting at frame {start_frame}")
                    animation_applied = True
                    break
            
            # Clean up the imported objects (we only needed the animation data)
            for obj in imported_objects:
                if obj.type == 'MESH' and obj.data:
                    bpy.data.meshes.remove(obj.data, do_unlink=True)
                elif obj.type == 'ARMATURE' and obj.data:
                    bpy.data.armatures.remove(obj.data, do_unlink=True)
                else:
                    bpy.data.objects.remove(obj, do_unlink=True)
            
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
utility_classes = [
    MeddleUtilsProperties,
    FindProperties,
    BoostLights,
    JoinByMaterial,
    JoinByMaterialAll,
    JoinByDistance,
    PurgeUnused,
    AddVoronoiTexture,
    CleanBoneHierarchy,
    ImportAnimationGLTF,
]

