import bpy
import logging
from bpy.types import Operator
import os

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class ExportFBX(Operator):
    """Export selected mesh objects to FBX format with textures"""
    bl_idname = "meddle.export_fbx"
    bl_label = "Export FBX"
    bl_description = "Export selected mesh objects to FBX format with textures in a subfolder"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Directory path for export
    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to export FBX and textures",
        subtype='DIR_PATH'
    )
    
    def invoke(self, context, event):
        """Open file browser for directory selection"""
        # Set default directory to blend file location or user home
        if bpy.data.filepath:
            self.directory = os.path.dirname(bpy.data.filepath)
        else:
            self.directory = os.path.expanduser("~")
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    @classmethod
    def poll(cls, context):
        """Check if operation can be executed"""
        # Require at least one mesh or armature selected
        return any(obj.type in {'MESH', 'ARMATURE'} for obj in context.selected_objects)
    
    def execute(self, context):
        """Execute the FBX export operation"""
        if not self.directory:
            self.report({'ERROR'}, "No directory selected")
            return {'CANCELLED'}
        
        try:
            # Get selected objects
            selected_objects = context.selected_objects
            mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH']
            armature_objects = [obj for obj in selected_objects if obj.type == 'ARMATURE']
            
            # If armatures are selected, include their child meshes
            for armature in armature_objects:
                for obj in bpy.data.objects:
                    if obj.type == 'MESH' and obj.parent == armature:
                        if obj not in mesh_objects and obj not in selected_objects:
                            selected_objects.append(obj)
                        if obj not in mesh_objects:
                            mesh_objects.append(obj)
            
            if not mesh_objects and not armature_objects:
                self.report({'ERROR'}, "No mesh or armature objects selected")
                return {'CANCELLED'}
            
            # Create textures subfolder
            textures_folder = os.path.join(self.directory, "textures")
            os.makedirs(textures_folder, exist_ok=True)
            logger.info(f"Created textures folder: {textures_folder}")
            
            # Export images to textures folder
            self.export_textures(context, mesh_objects, textures_folder)
            
            # Generate FBX filename
            fbx_filename = self.generate_fbx_filename(context, selected_objects)
            fbx_path = os.path.join(self.directory, fbx_filename)
            
            # Export FBX with packed images
            self.export_fbx_file(context, selected_objects, fbx_path)
            
            self.report({'INFO'}, f"Successfully exported to {fbx_path}")
            logger.info(f"Export complete: {fbx_path}")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            logger.error(f"Export failed: {e}", exc_info=True)
            return {'CANCELLED'}
    
    def export_textures(self, context, mesh_objects, textures_folder):
        """Export all textures used by mesh materials to the textures folder"""
        exported_images = set()
        image_count = 0
        
        for mesh_obj in mesh_objects:
            if not mesh_obj.data.materials:
                continue
            
            for mat_slot in mesh_obj.data.materials:
                if not mat_slot or not mat_slot.use_nodes:
                    continue
                
                material = mat_slot
                for node in material.node_tree.nodes:
                    if node.type != 'TEX_IMAGE' or not node.image:
                        continue
                    
                    image = node.image
                    
                    # Skip if already exported
                    if image.name in exported_images:
                        continue
                    
                    # Determine output filename
                    if image.filepath:
                        # Use existing filename
                        base_name = os.path.basename(image.filepath)
                        if not base_name:
                            base_name = f"{image.name}.png"
                    else:
                        base_name = f"{image.name}.png"
                    
                    # Ensure .png extension
                    if not base_name.lower().endswith('.png'):
                        base_name = os.path.splitext(base_name)[0] + '.png'
                    
                    output_path = os.path.join(textures_folder, base_name)
                    
                    # Save the image
                    try:
                        # Save a copy of the image
                        original_filepath = image.filepath_raw
                        original_format = image.file_format
                        
                        image.filepath_raw = output_path
                        image.file_format = 'PNG'
                        image.save()
                        
                        # Restore original settings
                        image.filepath_raw = original_filepath
                        image.file_format = original_format
                        
                        logger.info(f"Exported texture: {base_name}")
                        exported_images.add(image.name)
                        image_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to export texture {image.name}: {e}")
        
        self.report({'INFO'}, f"Exported {image_count} texture(s) to textures folder")
        logger.info(f"Exported {image_count} textures to {textures_folder}")
    
    def generate_fbx_filename(self, context, selected_objects):
        """Generate a filename for the FBX export"""
        # Try to use armature name, or first mesh name, or default
        armature = next((obj for obj in selected_objects if obj.type == 'ARMATURE'), None)
        
        if armature:
            base_name = armature.name
        elif selected_objects:
            base_name = selected_objects[0].name
        else:
            base_name = "export"
        
        # Sanitize filename
        base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '_', '-')).strip()
        if not base_name:
            base_name = "export"
        
        return f"{base_name}.fbx"
    
    def export_fbx_file(self, context, selected_objects, fbx_path):
        """Export the FBX file with selected objects"""
        # Ensure objects are selected
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        
        # Set active object
        armature = next((obj for obj in selected_objects if obj.type == 'ARMATURE'), None)
        if armature:
            context.view_layer.objects.active = armature
        elif selected_objects:
            context.view_layer.objects.active = selected_objects[0]
        
        # Export FBX with appropriate settings
        bpy.ops.export_scene.fbx(
            filepath=fbx_path,
            use_selection=True,
            global_scale=1.0,
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_NONE',
            bake_space_transform=False,
            object_types={'ARMATURE', 'MESH'},
            use_mesh_modifiers=True,
            use_mesh_modifiers_render=True,
            mesh_smooth_type='FACE',
            use_tspace=True,
            use_custom_props=False,
            add_leaf_bones=False,
            primary_bone_axis='Y',
            secondary_bone_axis='X',
            armature_nodetype='NULL',
            bake_anim=False,
            path_mode='COPY',  # Copy textures to export location
            embed_textures=True,  # Embed textures in FBX
            batch_mode='OFF'
        )
        
        logger.info(f"FBX exported to: {fbx_path}")