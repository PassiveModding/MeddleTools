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