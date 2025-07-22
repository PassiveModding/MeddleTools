import bpy
from os import path

from . import shader_fix
from . import blend_import

def registerModelImportSettings():
    bpy.utils.register_class(ModelImportSettings)
    bpy.utils.register_class(ModelImportHelpHover)
    bpy.types.Scene.model_import_settings = bpy.props.PointerProperty(type=ModelImportSettings)
    
def unregisterModelImportSettings():
    bpy.utils.unregister_class(ModelImportSettings)
    bpy.utils.unregister_class(ModelImportHelpHover)
    del bpy.types.Scene.model_import_settings
  
def drawModelImportHelp(layout):
    box = layout.box()
    col = box.column()
    col.label(text="Import and automatically apply shaders")
    col.label(text="Navigate to your Meddle export folder")
    col.label(text="and select the .gltf or .glb file")
    col.separator()
    col.label(text="Make sure you exported in 'raw' mode")
    col.label(text="from the Meddle ffxiv plugin")

class ModelImportHelpHover(bpy.types.Operator):
    bl_idname = "meddle.model_import_help_hover"
    bl_label = "Import Help"
    bl_description = "Import and automatically apply shaders. Navigate to your Meddle export folder and select the .gltf or .glb file. Make sure you exported in 'raw' mode from the Meddle ffxiv plugin."
    
    def execute(self, context):
        # toggle the display of the import help
        context.scene.model_import_settings.displayImportHelp = not context.scene.model_import_settings.displayImportHelp
        return {'FINISHED'}        


class ModelImportSettings(bpy.types.PropertyGroup):
    gltfImportMode: bpy.props.EnumProperty(
        items=[
            ('BLENDER', 'Blender', 'Blender (Bone tips are placed on their local +Y axis (In gLTF space))'),
            ('TEMPERANCE', 'Temperance', 'Temperance (A bone with one child has its tip placed on the axis closest to its child)'),
        ],
        name='Import Mode',
        default='BLENDER',
    )
    
    displayImportHelp: bpy.props.BoolProperty(
        name="Display Import Help",
        default=False,
    )
    
    deduplicateMaterials: bpy.props.BoolProperty(
        name="Deduplicate Materials",
        default=True,
    )

class ModelImport(bpy.types.Operator):
    bl_idname = "meddle.import_gltf"
    bl_label = "Import Model"    
    bl_description = "Import GLTF/GLB files exported from Meddle, automatically applying shaders"
    #filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    files: bpy.props.CollectionProperty(name="File Path Collection", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_glob: bpy.props.StringProperty(default='*.gltf;*.glb', options={'HIDDEN'})

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):    
        if context is None:
            return {'CANCELLED'}
        
        bpy.context.window.cursor_set('WAIT')
        try:
            blend_import.import_shaders()
            
            def import_gltf(filepath):            
                print(f"GLTF Path: {filepath}")
                
                cache_dir = path.join(path.dirname(filepath), "cache")

                #bpy.ops.import_scene.gltf(filepath=self.filepath, disable_bone_shape=True)
                if context.scene.model_import_settings.gltfImportMode == 'BLENDER':
                    bpy.ops.import_scene.gltf(filepath=filepath, disable_bone_shape=True)
                elif context.scene.model_import_settings.gltfImportMode == 'TEMPERANCE':
                    bpy.ops.import_scene.gltf(filepath=filepath, bone_heuristic='TEMPERANCE')
                
                imported_meshes = [obp for obp in context.selected_objects if obp.type == 'MESH']
                deduplicate: bool = context.scene.model_import_settings.deduplicateMaterials
                
                # for obj in context.selected_objects:
                #     if "RealScale" in obj:
                #         obj.scale = [obj["RealScale"]["X"], obj["RealScale"]["Y"], obj["RealScale"]["Z"]]
                           
                for obj in context.selected_objects:                    
                    shader_fix.setCollection(obj, context)
                                  
                for mesh in imported_meshes:
                    if mesh is None:
                        continue                    
                    
                    for slot in mesh.material_slots:
                        if slot.material is not None:
                            try:
                                shader_fix.handleShaderFix(mesh, slot.material, deduplicate, cache_dir)
                            except Exception as e:
                                print(e)
                                
                imported_lights = [obp for obp in context.selected_objects if obp.name.startswith("Light")]
                
                for light in imported_lights:
                    if light is None:
                        continue
                    
                    try:
                        shader_fix.handleLightFix(light)
                    except Exception as e:
                        print(e)
                            
            for file in self.files:
                filepath = path.join(self.directory, file.name)
                import_gltf(filepath)
                            
            return {'FINISHED'}
        finally:
            bpy.context.window.cursor_set('DEFAULT')