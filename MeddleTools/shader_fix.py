import bpy
from os import path

from numpy import isin
from . import blend_import
from . import node_groups

class ShaderFixActive(bpy.types.Operator):    
    bl_idname = "meddle.use_shaders_active_material"
    bl_label = "Use Shaders"    
    
    directory: bpy.props.StringProperty(subtype='DIR_PATH')    
    
    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        active = context.active_object
        
        blend_import.import_shaders()
        
        print(f"Folder selected: {self.directory}")
        
        if active is None:
            return {'CANCELLED'}
            
        if active.active_material is None:
            return {'CANCELLED'}
        
        return handleShaderFix(active, active.active_material, False, self.directory)
    
class ShaderFixSelected(bpy.types.Operator):    
    bl_idname = "meddle.use_shaders_selected_objects"
    bl_label = "Use Shaders on Selected"
        
    directory: bpy.props.StringProperty(subtype='DIR_PATH')    
    
    def invoke(self, context, event):
        if context is None:
            return {'CANCELLED'}
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        # copy of selected objects
        selected = context.selected_objects.copy()
        
        blend_import.import_shaders()
        
        print(f"Folder selected: {self.directory}")
        deduplicate: bool = context.scene.model_import_settings.deduplicateMaterials
        
        for obj in selected:
            if obj is None:
                continue
            
            for slot in obj.material_slots:
                if slot.material is not None:
                    try:
                        handleShaderFix(obj, slot.material, deduplicate, self.directory)
                        #shpkMtrlFixer(obj, slot.material, self.directory)
                    except Exception as e:
                        print(f"Error on {slot.material.name}: {e}")
                                    
        return {'FINISHED'}
    
def handleShaderFix(object: bpy.types.Object, mat: bpy.types.Material, deduplicate: bool, directory: str):
    if mat is None:
        return {'CANCELLED'}
    
    mesh = object.data
    if mesh is None:
        return {'CANCELLED'}
    
    if not isinstance(mesh, bpy.types.Mesh):
        return {'CANCELLED'}
    
    return node_groups.handleShader(mat, mesh, object, deduplicate, directory)
      
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
    
      
class MeddleClear(bpy.types.Operator):
    bl_idname = "meddle.clear_applied"
    bl_label = "Clear"
    
    def execute(self, context):
        # removes the 'MeddleApplied' custom property from all objects
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                # get materials
                for slot in obj.material_slots:
                    if slot.material is not None:
                        if 'MeddleApplied' in slot.material:
                            print(f"Removing MeddleApplied from {slot.material.name}")
                            del slot.material['MeddleApplied']
                
        return {'FINISHED'}
      
class LightingBoost(bpy.types.Operator):
    bl_idname = "meddle.lighting_boost"
    bl_label = "Lighting Boost"
    
    def execute(self, context):
        if context is None:
            return {'CANCELLED'}
        
        for obj in context.selected_objects:
            if obj is None:
                continue
            
            if obj.type == 'LIGHT':
                handleLightFix(obj)
        
        return {'FINISHED'}
    
def handleLightFix(light: bpy.types.Object):
    if light is None:
        return {'CANCELLED'}
    
    lightData: bpy.types.Light = light.data   # type: ignore
    if lightData is None:
        return {'CANCELLED'}
    
    if "LightType" in light:
        if light["LightType"] in ["SunLight", "MoonLight", "AmbientLight"]:
            newLight = bpy.data.lights.new(name=light.name, type='SUN')
            newLight.energy = light["HDRIntensity"]
            rgbCol = light["ColorRGB"]
            newLight.color = [rgbCol["X"], rgbCol["Y"], rgbCol["Z"]]
            
            light.data = newLight  # replace the light data with the new one
            # set rotation to quaternion identity
            light.rotation_mode = 'QUATERNION'
            light.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)  # identity quaternion
            
            bpy.data.lights.remove(lightData)  # remove old light data       
            return 
        if light["LightType"] == "AreaLight":                            
            newLight = bpy.data.lights.new(name=light.name, type='AREA')                           
            newLight.size = light["ShadowNear"]
            newLight.energy = light["HDRIntensity"]
            rgbCol = light["ColorRGB"]
            newLight.color = [rgbCol["X"], rgbCol["Y"], rgbCol["Z"]]                   
            newLight.use_custom_distance = True
            newLight.cutoff_distance = light["Range"]
            lightData.use_shadow = False
        
            # parent new lightData to the object
            light.data = newLight                            
            # remove old light
            bpy.data.lights.remove(lightData)
            return 
        if light["LightType"] == "PointLight":                            
            lightData.use_custom_distance = True
            lightData.cutoff_distance = light["Range"]
            lightData.shadow_soft_size = light["ShadowNear"]
            lightData.use_soft_falloff = False
            lightData.use_shadow = False
            lightData.energy = light["HDRIntensity"]
            return 
        if light["LightType"] == "SpotLight":                            
            lightData.use_custom_distance = True
            lightData.cutoff_distance = light["Range"]
            lightData.shadow_soft_size = light["ShadowNear"]
            lightData.use_soft_falloff = False
            lightData.use_shadow = False
            lightData.energy = light["HDRIntensity"]
            return
        if light["LightType"] == "CapsuleLight":
            newLight = bpy.data.lights.new(name=light.name, type='AREA')      
            newLight.shape = 'RECTANGLE'         
            newLight.energy = light["HDRIntensity"]    
            newLight.size = (light["BoundsMax"]["X"] / 10)
            newLight.size_y = (light["BoundsMax"]["X"] / 10)       
            rgbCol = light["ColorRGB"]
            newLight.color = [rgbCol["X"], rgbCol["Y"], rgbCol["Z"]]                   
            newLight.use_custom_distance = True
            newLight.cutoff_distance = light["Range"]
            lightData.use_shadow = False
        
            # parent new lightData to the object
            light.data = newLight                            
            # remove old light
            bpy.data.lights.remove(lightData)
            return
        
class AddVoronoiTexture(bpy.types.Operator):
    bl_idname = "meddle.add_voronoi_texture"
    bl_label = "Apply Terrain Vornoi"
    bl_description = "Add voronoi texture setup for background objects"
    
    def execute(self, context):
        # for every material in the scene, add the voronoi texture setup
        for mat in bpy.data.materials:
            if mat is None or not mat.use_nodes:
                continue
            
            # check if the material is a background material
            if "0x36F72D5F" in mat:
                if mat["0x36F72D5F"] == "0x9807BAC4" or mat["0x36F72D5F"] == "0x1E314009" or mat["0x36F72D5F"] == "0x88A3965A":
                    # add the voronoi texture setup
                    addVoronoiTexture(mat)
                    
        return {'FINISHED'}
    
def addVoronoiTexture(mat: bpy.types.Material):
    if mat is None or not mat.use_nodes:
        return {'CANCELLED'}
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    uvMapNode = nodes.new('ShaderNodeUVMap')
    uvMapNode.uv_map = 'UVMap'
    uvMapNode.location = (-500, 0)
    voronoiTexture = nodes.new('ShaderNodeTexVoronoi')
    voronoiTexture.location = (-300, 0)
    vectorMapping = nodes.new('ShaderNodeMapping')
    vectorMapping.location = (0, 0)
    # link the nodes
    links.new(uvMapNode.outputs['UV'], vectorMapping.inputs['Vector'])
    links.new(uvMapNode.outputs['UV'], voronoiTexture.inputs['Vector'])
    links.new(voronoiTexture.outputs['Color'], vectorMapping.inputs['Rotation'])
    
    # get texture nodes for the material
    textureNodes = [node for node in nodes if node.type == 'TEX_IMAGE']
    
    # link the voronoi texture to the texture nodes
    for texNode in textureNodes:
        if texNode is None:
            continue
        
        # check if the texture node has an input for vector
        if 'Vector' in texNode.inputs:
            links.new(vectorMapping.outputs['Vector'], texNode.inputs['Vector'])
        else:
            print(f"Texture node {texNode.name} does not have a Vector input.")
   

    return {'FINISHED'}