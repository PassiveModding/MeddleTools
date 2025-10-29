import bpy
import requests
import os
import tempfile
import logging
import addon_utils

logging.basicConfig()
logger = logging.getLogger('MeddleTools.version')
logger.setLevel(logging.INFO)


# Local manifest path
extension_parts = str(__package__).split(".")
if len(extension_parts) < 2:
    raise Exception("Failed to determine extension directory from package name, __package__ is too short.", __package__)
extension_directory = extension_parts[1]
EXTENSIONS_PATH = bpy.utils.user_resource('EXTENSIONS', path=extension_directory)

current_version = "Unknown"  # Holds the current version string


def updateCurrentRelease():
    global current_version
    current_version = "Unknown"
    
    enabledAddons = [addon.module for addon in bpy.context.preferences.addons]
    for mod in addon_utils.modules():
        if mod.__name__ in enabledAddons and mod.bl_info.get("name") == "Meddle Tools":
            if current_version != "Unknown":
                logger.warning("Multiple Meddle Tools addons found, version may not be accurate.")
            version = mod.bl_info.get("version", [])
            current_version = ".".join([str(v) for v in version])
    
    if current_version == "Unknown":
        logger.warning("Current version is unknown, please check the addon info.")
        return

def runInit():
    try:
        updateCurrentRelease()
        if current_version is not None:
            logger.info(f"Current version: {current_version}")
    except Exception as e:
        logger.error(f"Failed to update current release: {e}")