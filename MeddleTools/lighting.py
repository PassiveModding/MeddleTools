import bpy

def setupLight(light: bpy.types.Object):
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