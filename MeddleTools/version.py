import bpy
import logging
import threading
import tomllib
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    pass

REPO_JSON_URL = "https://raw.githubusercontent.com/PassiveModding/MeddleTools/main/repo.json"

current_version = "Unknown"  # Holds the current version string
latest_version = "Unknown"  # Holds the latest version string from the repo
attempted_version_check = False  # Flag to prevent repeated update checks

# Set when the latest release requires a newer Blender than the one running;
# holds the required version string (e.g. "5.1.0") so the UI can explain why
# the update is not offered in Preferences.
required_blender_version = None

def _parse_version_tuple(version_str):
    """Parse 'X.Y.Z' into a tuple of ints, or None if it doesn't parse."""
    try:
        return tuple(int(part) for part in str(version_str).split("."))
    except (ValueError, AttributeError):
        return None


def updateCurrentRelease():
    """Read the add-on version from the blender_manifest.toml next to the code.

    The manifest is the single source of truth for the installed version; no
    Blender add-on state is involved.
    """
    global current_version
    manifest_path = Path(__file__).parent / "blender_manifest.toml"
    try:
        with open(manifest_path, 'rb') as f:
            manifest = tomllib.load(f)
        current_version = manifest.get("version", "Unknown")
    except Exception as e:
        current_version = "Unknown"
        logger.warning(f"Could not read version from {manifest_path}: {e}")


def updateLatestRelease():
    global attempted_version_check
    global latest_version
    if attempted_version_check:
        return

    attempted_version_check = True
    try:
        response = requests.get(REPO_JSON_URL, timeout=5)
        response.raise_for_status()
        repo_data = response.json()
        latest_version = repo_data.get("version", "Unknown")
        if latest_version != "Unknown":
            logger.info(f"Latest version available: {latest_version}")
            if latest_version != current_version:
                logger.info(
                    f"A new version of Meddle Tools is available! Current: {current_version}, Latest: {latest_version}"
                )
                _check_blender_compatibility(repo_data)
        else:
            logger.warning("Could not determine the latest version from the repository.")

    except requests.RequestException as e:
        logger.error(f"Failed to check for updates: {e}")


def _check_blender_compatibility(repo_data):
    """Flag when the latest release needs a newer Blender than is running.

    Looks up the listing entry for the latest version and compares its
    blender_version_min against bpy.app.version (a static tuple, safe to
    read from the worker thread).
    """
    global required_blender_version
    required_blender_version = None

    entry = next(
        (e for e in repo_data.get("data", []) if e.get("version") == latest_version),
        None,
    )
    if entry is None:
        return

    minimum = _parse_version_tuple(entry.get("blender_version_min"))
    if minimum is None:
        return

    if tuple(bpy.app.version[: len(minimum)]) < minimum:
        required_blender_version = entry["blender_version_min"]
        logger.info(
            f"MeddleTools {latest_version} requires Blender {required_blender_version}+ "
            f"(running {'.'.join(str(v) for v in bpy.app.version)})."
        )


def _start_update_check():
    """Timer callback: run the update check in a background thread.

    Runs after startup so register() never blocks, and honors the
    'Check for Updates' toggle in the add-on preferences. The worker thread
    only performs HTTP and sets module-level strings, so it does not touch
    Blender data from off the main thread.
    """
    from . import preferences

    prefs = preferences.get_addon_preferences()
    if prefs is not None and not prefs.enable_update_check:
        logger.info("Update check disabled in add-on preferences.")
        return None

    threading.Thread(target=updateLatestRelease, name="MeddleToolsUpdateCheck", daemon=True).start()
    return None  # run once; unregisters the timer


def runInit():
    try:
        updateCurrentRelease()
        logger.info(f"Current version: {current_version}")
    except Exception as e:
        logger.error(f"Failed to determine current version: {e}")

    # Defer the network check so registration never blocks Blender startup
    try:
        bpy.app.timers.register(_start_update_check, first_interval=2.0)
    except Exception as e:
        logger.error(f"Failed to schedule update check: {e}")


def shutdown():
    """Cancel the pending update check when the add-on is unregistered."""
    try:
        if bpy.app.timers.is_registered(_start_update_check):
            bpy.app.timers.unregister(_start_update_check)
    except Exception:
        pass
