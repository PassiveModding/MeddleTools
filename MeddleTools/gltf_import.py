import bpy
from os import path

from . import node_configs
from . import blend_import
from . import lighting


def getRootObject(obj: bpy.types.Object) -> bpy.types.Object:
    if obj is None:
        return None
    
    # find the root object, which is the first parent that has no parent
    while obj.parent is not None:
        obj = obj.parent
    
    return obj

def unlinkFromSceneCollection(obj: bpy.types.Object, context: bpy.types.Context):
    if obj is None or context is None:
        return {'CANCELLED'}
    
    # if object is not in the scene collection, do nothing
    if obj.name not in context.scene.collection.objects:
        return {'CANCELLED'}
    
    # unlink the object from the scene collection
    context.scene.collection.objects.unlink(obj)
    
    return {'FINISHED'}

   
def addToGroup(obj: bpy.types.Object, group_name: str, context: bpy.types.Context):
    if obj is None or group_name is None or context is None:
        return {'CANCELLED'}
    
    # check if the group exists
    if group_name not in bpy.data.collections:
        # create the group
        new_collection = bpy.data.collections.new(group_name)
        context.scene.collection.children.link(new_collection)
        
    # check if the object is already in the group
    if obj.name in bpy.data.collections[group_name].objects:
        print(f"Object {obj.name} is already in the group {group_name}.")
        return {'CANCELLED'}
    
    # link the object to the group
    collection = bpy.data.collections[group_name]
    collection.objects.link(obj)
    
    # unlink from scene collection
    unlinkFromSceneCollection(obj, context)
    
    return {'FINISHED'}
      
def setCollection(obj: bpy.types.Object, context: bpy.types.Context):
    if obj is None or context is None:
        return {'CANCELLED'}
    
    # get the root object
    checkObj = getRootObject(obj)
    
    # based on name of the object, set the collection
    if checkObj.name.startswith("Decal_"):
        addToGroup(obj, "Decals", context)
            
    if checkObj.name.startswith("Light_") or checkObj.name.startswith("EnvLighting_"):
        addToGroup(obj, "Lights", context)
        
    if checkObj.name.startswith("SharedGroup_"):
        addToGroup(obj, "SharedGroups", context)        
        
    if checkObj.name.startswith("Housing_"):
        addToGroup(obj, "Housing", context)   
        
    if checkObj.name.startswith("BgPart_"):
        addToGroup(obj, "BgParts", context)
        
    if checkObj.name.startswith("Terrain_"):
        addToGroup(obj, "Terrain", context)
        
    return {'FINISHED'} 

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
                bpy.ops.import_scene.gltf(filepath=filepath, bone_heuristic='TEMPERANCE')
                
                current_selected_copy = list(context.selected_objects)
                
                imported_meshes = [obp for obp in current_selected_copy if obp.type == 'MESH']

                for mesh in imported_meshes:
                    if mesh is None:
                        continue
                    
                    node_configs.map_mesh(mesh, cache_dir)
                    
                imported_lights = [obp for obp in current_selected_copy if obp.name.startswith("Light")]
                
                for light in imported_lights:
                    if light is None:
                        continue
                    
                    try:
                        lighting.setupLight(light)
                    except Exception as e:
                        print(e)
                        
                for obj in current_selected_copy:                    
                    setCollection(obj, context)
                            
            for file in self.files:
                filepath = path.join(self.directory, file.name)
                import_gltf(filepath)
                            
            return {'FINISHED'}
        finally:
            bpy.context.window.cursor_set('DEFAULT')
            
class ApplyToSelected(bpy.types.Operator):
    bl_idname = "meddle.apply_to_selected"
    bl_label = "Apply Shaders to Selected"
    bl_description = "Apply shaders to the selected objects based on their shader package"
    directory: bpy.props.StringProperty(subtype='DIR_PATH')  

    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        selected_objects = context.selected_objects
        for obj in selected_objects:
            if obj.type == 'MESH':
                node_configs.map_mesh(obj, self.directory, True)
                
        return {'FINISHED'}

classes = [
    ModelImport,
    ApplyToSelected
]