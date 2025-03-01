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
        
        return handleShaderFix(active, active.active_material, self.directory)
    
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
        
        for obj in selected:
            if obj is None:
                continue
            
            for slot in obj.material_slots:
                if slot.material is not None:
                    try:
                        handleShaderFix(obj, slot.material, self.directory)
                        #shpkMtrlFixer(obj, slot.material, self.directory)
                    except Exception as e:
                        print(f"Error on {slot.material.name}: {e}")
                                    
        return {'FINISHED'}
    
def handleShaderFix(object: bpy.types.Object, mat: bpy.types.Material, directory: str):
    if mat is None:
        return {'CANCELLED'}
    
    mesh = object.data
    if mesh is None:
        return {'CANCELLED'}
    
    if not isinstance(mesh, bpy.types.Mesh):
        return {'CANCELLED'}
    
    return node_groups.handleShader(mat, mesh, directory)
        
    
def handleLightFix(light: bpy.types.Object, directory: str):
    if light is None:
        return {'CANCELLED'}
    
    lightData: bpy.types.Light = light.data   # type: ignore
    if lightData is None:
        return {'CANCELLED'}
    
    if "LightType" in light:                        
        if light["LightType"] == "AreaLight":                            
            newLight = bpy.data.lights.new(name=light.name, type='AREA')                           
            newLight.size = light["ShadowNear"]
            newLight.energy = light.data.energy
            rgbCol = light["ColorRGB"]
            newLight.color = [rgbCol["X"], rgbCol["Y"], rgbCol["Z"]]                   
            newLight.use_custom_distance = True
            newLight.cutoff_distance = light["Range"]
            lightData.use_shadow = False
        
            # parent new lightData to the object
            light.data = newLight                            
            # remove old light
            bpy.data.lights.remove(lightData)
        if light["LightType"] == "PointLight":                            
            lightData.use_custom_distance = True
            lightData.cutoff_distance = light["Range"]
            lightData.shadow_soft_size = light["ShadowNear"]
            lightData.use_soft_falloff = False
            lightData.use_shadow = False
        if light["LightType"] == "CapsuleLight":
            newLight = bpy.data.lights.new(name=light.name, type='AREA')      
            newLight.shape = 'RECTANGLE'         
            newLight.energy = light.data.energy          
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