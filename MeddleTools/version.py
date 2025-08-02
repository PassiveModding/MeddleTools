import bpy
import requests
import glob
import os
import tempfile
import logging
import addon_utils
from . import setup

logging.basicConfig()
logger = logging.getLogger('MeddleTools.auto_updating')
logger.setLevel(logging.INFO)

#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#
# Gratiously ripped from FFGear by kajupe.                             #
# https://github.com/kajupe/FFGear/blob/main/FFGear/auto_updating.py   #
#¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤¤#

GITHUB_USER = "PassiveModding"
GITHUB_REPO = "MeddleTools"
GITHUB_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASE_PAGE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

# Local manifest path
extension_directory = str(__package__).split(".")[1] # example of package: bl_ext.vscode_development.FFGear (This will almost always be "user_default")
EXTENSIONS_PATH = bpy.utils.user_resource('EXTENSIONS', path=extension_directory)
FFGEAR_FOLDER = os.path.join(EXTENSIONS_PATH, "FFGear")

latest_version_blob = None  # Holds the latest version blob from GitHub
latest_version = "Unknown"  # Holds the latest version string
latest_version_name = "Unknown"  # Holds the latest version name
latest_version_url = "Unknown"  # Holds the latest version download URL
latest_version_dl_name = "MeddleTools"  # Holds the latest version download name
current_version = "Unknown"  # Holds the current version string


#¤¤¤¤¤¤¤¤¤¤¤#
# Functions #
#¤¤¤¤¤¤¤¤¤¤¤#

def download_addon(url: str, name: str = "download") -> str:
    """Download the selected branch from GitHub and return the ZIP path."""
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"{name}.zip")

    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to download {url}.")
            return None

        with open(zip_path, 'wb') as zip_file:
            zip_file.write(response.content)

    except Exception as e:
        logger.exception(f"Download error: {e}")
        return None

    return zip_path

def updateLatestReleaseBlob():
    response = requests.get(GITHUB_RELEASE_URL)
    if response.status_code != 200:
        raise Exception(f"Failed to get latest version: {response.status_code}")
    data = response.json()
    
    global latest_version_blob
    latest_version_blob = data
    global latest_version
    latest_version = data["tag_name"]
    global latest_version_name
    latest_version_name = data["name"]
    global latest_version_dl_name
    latest_version_dl_name = f"{GITHUB_REPO}-{latest_version}"
    global latest_version_url
    latest_version_url = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/download/{latest_version}/{latest_version_dl_name}.zip"

def updateCurrentRelease():
    global current_version
    current_version = "Unknown"
    
    for mod in addon_utils.modules():
        if mod.bl_info.get("name") == "Meddle Tools":
            version = mod.bl_info.get("version", [])
            current_version = ".".join([str(v) for v in version])
    
    if current_version == "Unknown":
        logger.warning("Current version is unknown, please check the addon info.")
        return

def runInit():
    try:
        updateCurrentRelease()
        if current_version is not None:
            print(f"Current version: {current_version}")
    except Exception as e:
        print(f"Failed to read current version: {e}")
        
    try:        
        bpy.app.timers.register(updateLatestReleaseBlob, first_interval=2)
        if latest_version is not None:
            print(f"Latest version: {latest_version}")
    except Exception as e:
        print(f"Failed to get latest version: {e}")
        

#¤¤¤¤¤¤¤¤¤¤¤#
# Operators #
#¤¤¤¤¤¤¤¤¤¤¤#

class MeddleToolsInstallUpdate(bpy.types.Operator):
    f"""Download and install the latest version of MeddleTools"""
    bl_idname = "meddle.install_update"
    bl_label = "Install Update"
    bl_options = {'REGISTER', 'UNDO'}

    proceed_anyways: bpy.props.BoolProperty(
        name="Proceed anyways",
        description="If checked, Blender will attempt the update even if there are unsaved changes (they may be lost if the update crashes).",
        default=False,
    )
    
    

    # This method is called when the operator is run from the UI.
    def invoke(self, context, event):
        if bpy.data.is_dirty:
            # If the file has unsaved changes, show the confirmation dialog.
            return context.window_manager.invoke_props_dialog(self, width=350)
        else:
            # No unsaved changes, so we can proceed directly to execute.
            return self.execute(context)


    # This method is called by invoke_props_dialog to draw the contents of our confirmation dialog.
    def draw(self, context):
        layout = self.layout
        layout.label(text="The current Blender file has unsaved changes.", icon='ERROR')
        layout.label(text="It is recommended that you save before updating, just in case.")
        layout.prop(self, "proceed_anyways")


    def execute(self, context):
        if bpy.data.is_dirty:
            if not self.proceed_anyways:
                self.report({'WARNING'}, "Update cancelled. Confirmation to proceed was not given.")
                return {'CANCELLED'}
            logger.info("User confirmed to proceed with unsaved changes. Proceeding with update.")
        else:
            logger.info("No unsaved changes detected. Proceeding with update.")

        # Spinny Cursor
        context.window.cursor_set('WAIT')

        try:
            if latest_version_blob is None:
                self.report({'ERROR'}, "Latest version information is not available.")
                return {'CANCELLED'}
            self.report({'INFO'}, "Downloading update...")
            zip = download_addon(latest_version_url, latest_version_dl_name)
            
            if zip == None:
                self.report({'ERROR'}, f"Failed to download {GITHUB_REPO}.")
                return {'CANCELLED'}

            try:
                self.report({'INFO'}, "Installing update...")
                bpy.ops.extensions.package_install_files(directory=EXTENSIONS_PATH, filepath=zip, repo=extension_directory, url=latest_version_url)
            except Exception as e:
                error_message = f"Failed to install {GITHUB_REPO}. Error: {str(e)}"
                self.report({'ERROR'}, error_message)
                return {'CANCELLED'}
            
            return {'FINISHED'}
        finally:
            context.window.cursor_set('DEFAULT')