"""
Enhanced version of auto_updater.py with better error handling and debugging
"""
import os
import sys
import json
import logging
import time
import tempfile
import shutil
import zipfile
import subprocess
import traceback
import requests
from packaging import version

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler("updater.log"),
                       logging.StreamHandler()
                   ])
logger = logging.getLogger('auto_updater')

# GitHub repository information
GITHUB_REPO = "oHaruki/YouTubeUploaderElectron"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_ALL_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
VERSION_FILE = "version.json"

# Files and directories to exclude during update
UPDATE_EXCLUDE = [
    "config.json",
    "version.json",
    "credentials",
    "tokens",
    "logs",
    "__pycache__",
    ".git",
    ".gitignore",
    "temp",
    "venv",
    "env",
    ".venv"
]

def get_current_version():
    """
    Get the current installed version with fallbacks for both development and production environments
    
    Returns:
        str: Current version string or "0.0.0" if not found
    """
    version_sources = []
    
    # First priority: Try to get version from package.json (works in development)
    try:
        # Try several possible locations for package.json
        potential_paths = [
            'package.json',                             # Current directory
            os.path.join('..', 'package.json'),         # Parent directory 
            os.path.join(os.path.dirname(__file__), 'package.json'),  # Script directory
            os.path.join(os.path.dirname(__file__), '..', 'package.json')  # Parent of script directory
        ]
        
        for package_path in potential_paths:
            if os.path.exists(package_path):
                logger.info(f"Found package.json at: {package_path}")
                with open(package_path, 'r') as f:
                    package_data = json.load(f)
                    package_version = package_data.get('version')
                    if package_version:
                        logger.info(f"Using version from package.json: {package_version}")
                        version_sources.append(('package.json', package_version))
                        
                        # Update version.json files if in development mode
                        if package_path == 'package.json' or package_path == os.path.join('..', 'package.json'):
                            try:
                                sync_version_files(package_version)
                            except Exception as e:
                                logger.error(f"Error syncing version files: {e}")
                        
                        break
    except Exception as e:
        logger.error(f"Error reading package.json: {e}")
    
    # Second priority: Try version.json in various locations
    try:
        version_files = [
            VERSION_FILE,                             # Default location
            os.path.join('flask_app', 'version.json'),  # Flask app directory
            os.path.join(os.path.dirname(__file__), 'version.json'),  # Script directory
            os.path.join(os.path.dirname(__file__), '..', 'version.json'),  # Parent directory
            os.path.join(os.path.dirname(sys.executable), 'version.json')  # Executable directory
        ]
        
        for ver_file in version_files:
            if os.path.exists(ver_file):
                logger.info(f"Found version.json at: {ver_file}")
                with open(ver_file, 'r') as f:
                    version_data = json.load(f)
                    file_version = version_data.get("version")
                    if file_version:
                        logger.info(f"Found version in {ver_file}: {file_version}")
                        version_sources.append((os.path.basename(ver_file), file_version))
    except Exception as e:
        logger.error(f"Error reading version files: {e}")
    
    # Third priority (backup): Check if executable has a version resource (Windows only)
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        try:
            import win32api
            exe_path = sys.executable
            logger.info(f"Checking executable version info: {exe_path}")
            info = win32api.GetFileVersionInfo(exe_path, '\\')
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            exe_version = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
            logger.info(f"Executable version: {exe_version}")
            version_sources.append(('executable', exe_version))
        except Exception as e:
            logger.error(f"Error getting executable version: {e}")
    
    # Log all discovered versions for debugging
    logger.info(f"Found version sources: {version_sources}")
    
    # Return the first available version, prioritized by the order above
    if version_sources:
        source, version = version_sources[0]
        logger.info(f"Using version from {source}: {version}")
        return version
    
    # Absolute fallback
    logger.warning(f"No version information found, using default: 0.0.0")
    return "0.0.0"

def sync_version_files(version):
    """
    Synchronize version.json files with the given version
    
    Args:
        version (str): Version string to write to files
    """
    # Update root version.json
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r') as f:
                version_data = json.load(f)
            
            version_data["version"] = version
            
            with open(VERSION_FILE, 'w') as f:
                json.dump(version_data, f, indent=4)
                
            logger.info(f"Updated version.json to match package.json: {version}")
    except Exception as e:
        logger.error(f"Error updating version.json: {e}")

    # Update flask_app/version.json
    try:
        flask_version_file = os.path.join('flask_app', 'version.json')
        if os.path.exists(flask_version_file):
            with open(flask_version_file, 'r') as f:
                flask_version_data = json.load(f)
            
            flask_version_data["version"] = version
            
            with open(flask_version_file, 'w') as f:
                json.dump(flask_version_data, f, indent=4)
                
            logger.info(f"Updated flask_app/version.json to match package.json: {version}")
    except Exception as e:
        logger.error(f"Error updating flask_app/version.json: {e}")

def is_auto_update_enabled():
    """
    Check if auto-update is enabled in settings with better error handling
    
    Returns:
        bool: True if auto-update is enabled, False otherwise
    """
    # Default to True if file doesn't exist or has errors
    if not os.path.exists(VERSION_FILE):
        logger.info("No version file found, auto-update assumed enabled")
        return True
        
    try:
        with open(VERSION_FILE, 'r') as f:
            version_data = json.load(f)
            is_enabled = version_data.get("auto_update", True)
            logger.info(f"Auto-update is {'enabled' if is_enabled else 'disabled'}")
            return is_enabled
    except Exception as e:
        logger.error(f"Error reading version file auto-update setting: {e}")
        # Default to enabled if there's an error
        return True

def set_auto_update_enabled(enabled=True):
    """
    Set the auto-update enabled setting
    
    Args:
        enabled (bool): Whether auto-update should be enabled
    """
    logger.info(f"Setting auto-update to: {enabled}")
    
    if not os.path.exists(VERSION_FILE):
        # Create version file with the setting
        version_data = {
            "version": "1.0.0",
            "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "auto_update": enabled
        }
    else:
        # Update existing version file
        try:
            with open(VERSION_FILE, 'r') as f:
                version_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading version file: {e}")
            version_data = {
                "version": "1.0.0",
                "build_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
    
    # Update the auto-update setting
    version_data["auto_update"] = enabled
    
    # Save the updated version file
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_data, f, indent=4)
        logger.info(f"Updated auto-update setting to: {enabled}")
    except Exception as e:
        logger.error(f"Error updating version file: {e}")

"""
Modified check_for_update function to fix version mismatch
Replace this function in your auto_updater.py
"""

def check_for_update(forced_current_version=None):
    """
    Check if a newer version is available on GitHub with improved error handling and debugging
    
    Args:
        forced_current_version (str, optional): Override the current version for comparison
        
    Returns:
        tuple: (update_available, latest_version, download_url, release_notes)
    """
    # Use the forced version if provided, otherwise get from files
    current_version = forced_current_version if forced_current_version else get_current_version()
    
    try:
        logger.info(f"Checking for updates (current version: {current_version})")
        
        # Set up proper headers for GitHub API
        headers = {
            'User-Agent': 'YT-Auto-Uploader-App',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Try the latest release endpoint first
        logger.info(f"Requesting latest release from: {GITHUB_API_URL}")
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=15)
        
        # If we get a 404, it means there's no release marked as "latest"
        # Try to get all releases instead
        if response.status_code == 404:
            logger.warning("No 'latest' release found, checking all releases")
            response = requests.get(GITHUB_ALL_RELEASES_URL, headers=headers, timeout=15)
            
            if response.status_code == 200:
                releases = response.json()
                if not releases:
                    logger.warning("No releases found")
                    return (False, None, None, None)
                
                # Get the first release (most recent)
                release_data = releases[0]
                logger.info(f"Using most recent release: {release_data.get('tag_name')}")
            else:
                # Both endpoints failed
                logger.error(f"Failed to get releases: {response.status_code} {response.text}")
                return (False, None, None, None)
        elif response.status_code == 200:
            # We got the latest release
            release_data = response.json()
            logger.info(f"Found latest release: {release_data.get('tag_name')}")
        else:
            # Some other error
            logger.error(f"GitHub API error: {response.status_code} {response.text}")
            return (False, None, None, None)
        
        # Extract release information
        tag_name = release_data.get("tag_name", "")
        latest_version = tag_name.lstrip('v') if tag_name else ""
        logger.info(f"Latest version: {latest_version}")
        
        download_url = None
        
        # Log all assets for debugging
        assets = release_data.get("assets", [])
        logger.info(f"Release assets: {[asset.get('name') for asset in assets]}")
        
        # First, look for ZIP files with "win" in the name (win-unpacked)
        for asset in assets:
            asset_name = asset.get("name", "").lower()
            asset_url = asset.get("browser_download_url")
            logger.info(f"Checking asset: {asset_name}, URL: {asset_url}")
            
            # Specifically look for win ZIP files, which are unpacked builds
            if asset_name.endswith(".zip") and "win" in asset_name:
                download_url = asset_url
                logger.info(f"Found win-unpacked ZIP file: {download_url}")
                break
        
        # IMPORTANT: If no win-unpacked ZIP found, DO NOT fall back to other assets
        # Since we only handle ZIP files and specifically want the win-unpacked ZIP
        if not download_url:
            logger.warning(f"No win-unpacked ZIP file found for version {latest_version}")
            # Return information for display purposes, but don't allow download/update
            return (False, latest_version, None, release_data.get("body", "No release notes available."))
        
        # Compare versions - improved handling
        if not latest_version:
            logger.warning(f"Invalid release data: version={latest_version}")
            return (False, latest_version, None, None)
        
        try:
            # Compare using the exact version provided (fixes mismatch issue)
            is_newer = version.parse(latest_version) > version.parse(current_version)
            logger.info(f"Version comparison: {latest_version} > {current_version} = {is_newer}")
            
            if is_newer:
                return (True, latest_version, download_url, release_data.get("body", "No release notes available."))
            else:
                return (False, latest_version, None, None)
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            # Try a simple string comparison as fallback
            is_newer = latest_version > current_version
            logger.info(f"Fallback string comparison: {latest_version} > {current_version} = {is_newer}")
            
            if is_newer:
                return (True, latest_version, download_url, release_data.get("body", "No release notes available."))
            else:
                return (False, latest_version, None, None)
            
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        logger.error(traceback.format_exc())
        return (False, None, None, None)

def download_update(download_url):
    """
    Download the update package with better error handling
    
    Args:
        download_url (str): URL to download the update from
        
    Returns:
        tuple: (Path to the downloaded file, file_type), or (None, None) if download failed
    """
    try:
        logger.info(f"Downloading update from {download_url}")
        
        temp_dir = tempfile.gettempdir()
        
        # Detect if this is a win-zip file
        url_lower = download_url.lower()
        is_win_zip = url_lower.endswith('.zip') and 'win' in url_lower
        
        # Set file type and path
        if is_win_zip:
            file_type = "win-zip"
            file_path = os.path.join(temp_dir, "youtube_auto_uploader_update_win.zip")
        else:
            file_type = "zip"
            file_path = os.path.join(temp_dir, "youtube_auto_uploader_update.zip")
        
        logger.info(f"Download type: {file_type}, saving to: {file_path}")
        
        # Download with a proper user agent
        headers = {
            'User-Agent': 'YT-Auto-Uploader-App'
        }
        
        # Download with progress reporting
        response = requests.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get total file size if available
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"Download size: {total_size} bytes")
        
        # Download with chunking
        with open(file_path, 'wb') as f:
            downloaded = 0
            last_percent = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress every 10%
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        if percent >= last_percent + 10:
                            logger.info(f"Download progress: {percent}%")
                            last_percent = percent
        
        # Verify the downloaded file
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            logger.info(f"Update downloaded to {file_path}")
            
            # Verify this is actually a ZIP file
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    # Check ZIP magic number
                    if not header.startswith(b'PK\x03\x04'):
                        logger.warning("Downloaded file is not a valid ZIP file!")
                        return None, None
            except Exception as e:
                logger.error(f"Error verifying ZIP file: {e}")
            
            return file_path, file_type
        else:
            logger.error(f"Downloaded file is empty or missing: {file_path}")
            return None, None
            
    except Exception as e:
        logger.error(f"Error downloading update: {e}")
        logger.error(traceback.format_exc())
        return None, None

def apply_update(file_path, latest_version, file_type="zip"):
    """Apply the downloaded update"""
    try:
        logger.info(f"Applying update to version {latest_version}")
        
        # Handle tuple case
        if isinstance(file_path, tuple):
            file_path, file_type = file_path
        
        # Check if file_path is None (download failed)
        if file_path is None:
            logger.error("Cannot apply update: file_path is None (download failed or invalid file type)")
            return False
        
        # Only handle ZIP files now
        if not file_path.endswith('.zip'):
            logger.error(f"Unsupported update file: {file_path}")
            return False
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"Update file does not exist: {file_path}")
            return False
            
        # Verify this is a ZIP file by trying to open it
        try:
            with zipfile.ZipFile(file_path, 'r') as test_zip:
                # Try to get the file list to verify it's a valid ZIP
                file_list = test_zip.namelist()
                logger.info(f"ZIP file verified with {len(file_list)} files")
        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error verifying ZIP file: {e}")
            return False
        
        # Determine app root directory
        if getattr(sys, 'frozen', False):
            # We are running in a bundle
            app_dir = os.path.dirname(sys.executable)
        else:
            # We are running in a normal Python environment
            app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        logger.info(f"Application directory: {app_dir}")
        
        # Ensure app can write to its own directory
        if not os.access(app_dir, os.W_OK):
            logger.error(f"No write access to application directory: {app_dir}")
            return False
        
        # Use a specific temp directory for our update
        temp_dir = os.path.join(tempfile.gettempdir(), "youtube_auto_uploader_update")
        
        # Clear and create temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        # Extract the update to temp directory
        logger.info(f"Extracting update from {file_path}")
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the extracted directory - look specifically for specific structures
        extract_root = temp_dir
        
        # Check for common subdirectory structures in ZIP files
        for possible_subdir in ['win-unpacked', 'app', 'YouTubeAutoUploader']:
            if os.path.exists(os.path.join(temp_dir, possible_subdir)):
                extract_root = os.path.join(temp_dir, possible_subdir)
                logger.info(f"Found app subdirectory: {possible_subdir}")
                break
                
        # Check for alternative structures (just one subdirectory)
        if extract_root == temp_dir:
            subdirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if len(subdirs) == 1:
                extract_root = os.path.join(temp_dir, subdirs[0])
                logger.info(f"Using single subdirectory as extract root: {extract_root}")
        
        logger.info(f"Using extract directory: {extract_root}")
        
        # Create exclude list for the update script
        exclude_path = os.path.join(temp_dir, "exclude.txt")
        with open(exclude_path, "w") as f:
            f.write("update_script.bat\n")
            f.write("config.json\n")
            f.write("version.json\n")
            f.write(".git\n")
            f.write("exclude.txt\n")
        
        # Create update script with better path handling
        script_path = os.path.join(temp_dir, "update_script.bat")
        
        with open(script_path, "w") as f:
            f.write("@echo off\n")
            f.write("setlocal enabledelayedexpansion\n\n")
            f.write("echo Updating YouTube Auto Uploader...\n")
            f.write("echo Waiting for application to close completely...\n")
            f.write("timeout /t 3 /nobreak > nul\n\n")
            
            # Get the current directory (reliably)
            f.write("REM Get the executable directory (where the app is actually installed)\n")
            f.write("set \"APP_DIR=%~dp0\"\n")
            f.write("cd /d \"%APP_DIR%\"\n")
            f.write("cd ..\n\n")
            
            f.write("echo Application directory: %CD%\n\n")
            
            # Try to terminate any running processes
            f.write("REM Try to terminate any running instances of the app\n")
            f.write("taskkill /F /IM \"YouTube Auto Uploader.exe\" /T 2>nul\n")
            f.write("timeout /t 1 /nobreak > nul\n\n")
            
            f.write("echo Copying updated files...\n\n")
            
            # Use xcopy instead of robocopy for better compatibility
            f.write("REM Use xcopy instead of robocopy for better compatibility\n")
            f.write("echo Copying main files...\n")
            f.write(f"xcopy /E /Y /I /Q \"%~dp0extract_root\\*\" \"%CD%\\\" /EXCLUDE:%~dp0exclude.txt\n\n")
            
            # Specially handle flask_app directory
            f.write("REM Check for flask_app directory\n")
            f.write("if not exist \"%CD%\\resources\\flask_app\" (\n")
            f.write("    echo Creating flask_app directory...\n")
            f.write("    mkdir \"%CD%\\resources\\flask_app\"\n")
            f.write(")\n\n")
            
            f.write("REM Ensure flask_app directory is properly populated\n")
            f.write("if exist \"%~dp0extract_root\\resources\\flask_app\" (\n")
            f.write("    echo Copying flask_app files...\n")
            f.write("    xcopy /E /Y /I /Q \"%~dp0extract_root\\resources\\flask_app\\*\" \"%CD%\\resources\\flask_app\\\"\n")
            f.write(")\n\n")
            
            # Update version file
            f.write(f"echo {{\"version\": \"{latest_version}\", \"build_date\": \"{time.strftime('%Y-%m-%d %H:%M:%S')}\", \"auto_update\": true}} > \"%CD%\\version.json\"\n\n")
            
            # Create a verification file
            f.write("REM Create a simple verification file to confirm update completed\n")
            f.write("echo Updated on %DATE% %TIME% > \"%CD%\\resources\\update_completed.txt\"\n\n")
            
            f.write("echo Update completed successfully!\n")
            f.write("echo Starting application...\n\n")
            
            # Start the app
            f.write("REM Start the app\n")
            f.write("start \"\" \"%CD%\\YouTube Auto Uploader.exe\"\n\n")
            
            f.write("echo You can close this window now.\n")
            f.write("exit /b 0\n")
        
        # Copy the extract directory path to an easy-to-find location for the batch script
        extract_root_file = os.path.join(temp_dir, "extract_root")
        with open(extract_root_file, "w") as f:
            f.write(extract_root)
        
        # Launch the update script and exit the application
        logger.info("Launching update script and exiting application")
        subprocess.Popen(["cmd", "/c", script_path], 
                         creationflags=subprocess.CREATE_NEW_CONSOLE, 
                         start_new_session=True)
        
        # Signal to main app that it should exit
        return "EXIT_FOR_UPDATE"
    
    except Exception as e:
        logger.error(f"Error applying update: {e}")
        logger.error(traceback.format_exc())
        return False

def update_version_file(new_version):
    """
    Update the version file with the new version
    
    Args:
        new_version (str): New version string
    """
    version_data = {
        "version": new_version,
        "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "auto_update": is_auto_update_enabled()
    }
    
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_data, f, indent=4)
        logger.info(f"Version file updated to {new_version}")
    except Exception as e:
        logger.error(f"Error updating version file: {e}")

def get_all_versions():
    """
    Get a list of all available versions from GitHub
    
    Returns:
        list: List of version objects with details
    """
    try:
        logger.info("Fetching all available versions")
        
        # Set up proper headers for GitHub API
        headers = {
            'User-Agent': 'YT-Auto-Uploader-App',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        current_version = get_current_version()
        logger.info(f"Current version: {current_version}")
        
        # Get all releases
        logger.info(f"Requesting all releases from: {GITHUB_ALL_RELEASES_URL}")
        response = requests.get(GITHUB_ALL_RELEASES_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"GitHub API error: {response.status_code} {response.text}")
            # Don't return an empty list - return at least the current version
            return [{
                'id': 'current',
                'version': current_version,
                'name': f'Current Version {current_version}',
                'date': time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                'notes': 'This is your currently installed version.',
                'is_current': True
            }]
        
        releases = response.json()
        logger.info(f"Found {len(releases)} releases")
        
        versions = []
        for release in releases:
            tag_name = release.get("tag_name", "")
            version_number = tag_name.lstrip('v') if tag_name else ""
            
            # Skip empty versions
            if not version_number:
                continue
                
            logger.info(f"Processing release: {tag_name}")
            
            # Find download URL
            download_url = None
            for asset in release.get("assets", []):
                asset_name = asset.get("name", "")
                if asset_name.endswith((".zip", ".exe")):
                    download_url = asset.get("browser_download_url")
                    break
            
            # If no compatible download found, just record the version info anyway
            if not download_url:
                logger.warning(f"No compatible download URL found for version {version_number}")
                # Look for any asset to use as fallback
                if release.get("assets"):
                    download_url = release["assets"][0].get("browser_download_url")
                else:
                    download_url = release.get("html_url")  # Use GitHub page URL as fallback
            
            # Create version object
            version_obj = {
                "id": str(release.get("id", "")),
                "version": version_number,
                "name": release.get("name") or f"Version {version_number}",
                "date": release.get("published_at"),
                "notes": release.get("body", ""),
                "download_url": download_url,
                "is_current": version_number == current_version
            }
            
            versions.append(version_obj)
        
        # Ensure current version is included
        if not any(v.get("is_current") for v in versions):
            logger.info(f"Adding current version {current_version} to list")
            versions.append({
                "id": "current",
                "version": current_version,
                "name": f"Current Version {current_version}",
                "date": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "notes": "This is your currently installed version.",
                "is_current": True
            })
        
        # Sort by version number (latest first)
        try:
            versions.sort(key=lambda v: version.parse(v["version"]), reverse=True)
        except Exception as e:
            logger.error(f"Error sorting versions: {e}")
            # Fall back to string sort
            versions.sort(key=lambda v: v["version"], reverse=True)
        
        return versions
        
    except Exception as e:
        logger.error(f"Error getting versions: {e}")
        logger.error(traceback.format_exc())
        
        # Return at least the current version
        return [{
            'id': 'current',
            'version': current_version,
            'name': f'Current Version {current_version}',
            'date': time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            'notes': 'This is your currently installed version.',
            'is_current': True
        }]

def run_update():
    """
    Run the update process
    
    Returns:
        tuple: (updated, new_version, error_message)
    """
    if not is_auto_update_enabled():
        logger.info("Auto-update is disabled")
        return (False, None, "Auto-update is disabled")
    
    try:
        update_available, latest_version, download_url, release_notes = check_for_update()
        
        if not update_available:
            logger.info("No updates available")
            return (False, None, "No updates available")
        
        logger.info(f"Update available: {latest_version}, downloading...")
        file_path, file_type = download_update(download_url)
        if not file_path:
            logger.error("Failed to download update")
            return (False, None, "Failed to download update")
        
        logger.info("Applying update...")
        success = apply_update(file_path, latest_version, file_type)
        if not success:
            logger.error("Failed to apply update")
            return (False, None, "Failed to apply update")
        
        logger.info(f"Successfully updated to version {latest_version}")
        return (True, latest_version, None)
    except Exception as e:
        logger.error(f"Update process error: {e}")
        logger.error(traceback.format_exc())
        return (False, None, str(e))

def restart_application():
    """
    Restart the application after update
    """
    logger.info("Restarting application...")
    
    try:
        if getattr(sys, 'frozen', False):
            # Running as bundled executable
            logger.info(f"Restarting bundled executable: {sys.executable}")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Running as script
            logger.info(f"Restarting Python script: {sys.executable} {sys.argv}")
            args = [sys.executable] + sys.argv
            subprocess.Popen(args)
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error restarting application: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Manual test
    print(f"Current version: {get_current_version()}")
    print(f"Auto-update enabled: {is_auto_update_enabled()}")
    
    print("Checking for updates...")
    update_available, latest_version, download_url, release_notes = check_for_update()
    print(f"Update available: {update_available}")
    
    if update_available:
        print(f"Latest version: {latest_version}")
        print(f"Download URL: {download_url}")
        print(f"Release notes: {release_notes}")
        
        if input("Download and apply update? (y/n): ").lower() == 'y':
            print("Downloading update...")
            zip_path = download_update(download_url)
            
            if zip_path:
                print("Applying update...")
                apply_update(zip_path, latest_version)
                print("Update applied. Restart application to use the new version.")
    else:
        print("No updates available or error checking for updates.")
        
    # Get all versions
    print("\nGetting all versions...")
    versions = get_all_versions()
    for v in versions:
        print(f"- {v['version']} ({v['name']}): {v['date']}")