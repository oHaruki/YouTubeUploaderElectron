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
    Get the current installed version with improved handling of multiple version sources
    
    Returns:
        str: Current version string or "0.0.0" if not found
    """
    # Dictionary to track versions from different sources
    version_sources = {}
    
    # Try to read from package.json first
    try:
        package_path = 'package.json'
        if os.path.exists(package_path):
            with open(package_path, 'r') as f:
                package_data = json.load(f)
                package_version = package_data.get('version')
                if package_version and package_version != "0.0.0":
                    logger.info(f"Read version from package.json: {package_version}")
                    version_sources['package.json'] = package_version
    except Exception as e:
        logger.error(f"Error reading package.json: {e}")
    
    # Try root version.json
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r') as f:
                version_data = json.load(f)
                root_version = version_data.get("version")
                if root_version:
                    logger.info(f"Read version from root version.json: {root_version}")
                    version_sources['root_version.json'] = root_version
    except Exception as e:
        logger.error(f"Error reading root version.json: {e}")
    
    # Try flask_app/version.json
    flask_version_file = os.path.join('flask_app', 'version.json')
    try:
        if os.path.exists(flask_version_file):
            with open(flask_version_file, 'r') as f:
                version_data = json.load(f)
                flask_version = version_data.get("version")
                if flask_version:
                    logger.info(f"Read version from flask_app/version.json: {flask_version}")
                    version_sources['flask_version.json'] = flask_version
    except Exception as e:
        logger.error(f"Error reading flask_app/version.json: {e}")
    
    # Debug all found versions
    logger.info(f"All found versions: {version_sources}")
    
    # Choose the highest version number
    if version_sources:
        # Convert to list of (source, version_str) tuples
        versions_list = [(source, ver_str) for source, ver_str in version_sources.items()]
        
        # Sort by version (highest first)
        try:
            versions_list.sort(key=lambda x: version.parse(x[1]), reverse=True)
            highest_source, highest_version = versions_list[0]
            logger.info(f"Using highest version: {highest_version} from {highest_source}")
            return highest_version
        except Exception as e:
            logger.error(f"Error parsing versions: {e}")
            # If sorting fails, just take the first one
            if versions_list:
                return versions_list[0][1]
    
    # If no versions found or all parsing failed, create a new version file
    logger.warning("No valid version found, creating default version.json")
    initial_version = {
        "version": "1.0.0",
        "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "auto_update": True  # Changed to enabled by default
    }
    
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(initial_version, f, indent=4)
    except Exception as e:
        logger.error(f"Error creating version file: {e}")
    
    return "1.0.0"

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

def check_for_update():
    """
    Check if a newer version is available on GitHub with improved error handling and debugging
    
    Returns:
        tuple: (update_available, latest_version, download_url, release_notes)
    """
    current_version = get_current_version()
    
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
        
        # Find the ZIP asset
        for asset in assets:
            asset_name = asset.get("name", "")
            asset_url = asset.get("browser_download_url")
            logger.info(f"Checking asset: {asset_name}, URL: {asset_url}")
            
            if asset_name.endswith((".zip", ".exe")):
                download_url = asset_url
                logger.info(f"Found download URL: {download_url}")
                break
        
        release_notes = release_data.get("body", "No release notes available.")
        
        # Compare versions - improved handling
        if not latest_version or not download_url:
            logger.warning(f"Invalid release data: version={latest_version}, download_url={download_url}")
            return (False, latest_version, None, None)
        
        try:
            is_newer = version.parse(latest_version) > version.parse(current_version)
            logger.info(f"Version comparison: {latest_version} > {current_version} = {is_newer}")
            
            if is_newer:
                return (True, latest_version, download_url, release_notes)
            else:
                return (False, latest_version, None, None)
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            # Try a simple string comparison as fallback
            is_newer = latest_version > current_version
            logger.info(f"Fallback string comparison: {latest_version} > {current_version} = {is_newer}")
            
            if is_newer:
                return (True, latest_version, download_url, release_notes)
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
        str: Path to the downloaded update file, or None if download failed
    """
    try:
        logger.info(f"Downloading update from {download_url}")
        
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "youtube_auto_uploader_update.zip")
        
        # Download the file with a proper user agent
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
        with open(zip_path, 'wb') as f:
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
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            logger.info(f"Update downloaded to {zip_path}")
            return zip_path
        else:
            logger.error(f"Downloaded file is empty or missing: {zip_path}")
            return None
            
    except Exception as e:
        logger.error(f"Error downloading update: {e}")
        logger.error(traceback.format_exc())
        return None

def apply_update(zip_path, latest_version):
    """
    Apply the downloaded update
    
    Args:
        zip_path (str): Path to the downloaded update ZIP file
        latest_version (str): Version string of the update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        logger.info(f"Applying update to version {latest_version}")
        
        temp_dir = os.path.join(tempfile.gettempdir(), "youtube_auto_uploader_update")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Log directories for debugging
        logger.info(f"Temp directory: {temp_dir}")
        logger.info(f"Current directory: {current_dir}")
        
        # Clear previous temp directory if it exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        os.makedirs(temp_dir)
        
        # Extract the update
        logger.info(f"Extracting update from {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the root directory in the extracted files
        extracted_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
        logger.info(f"Extracted directories: {extracted_dirs}")
        
        if extracted_dirs:
            extract_root = os.path.join(temp_dir, extracted_dirs[0])
        else:
            extract_root = temp_dir
        
        logger.info(f"Extract root: {extract_root}")
        
        # List files that will be updated
        logger.info("Files to be updated:")
        for item in os.listdir(extract_root):
            if item not in UPDATE_EXCLUDE:
                logger.info(f" - {item}")
        
        # Copy the update files to the current directory
        for item in os.listdir(extract_root):
            source = os.path.join(extract_root, item)
            destination = os.path.join(current_dir, item)
            
            # Skip excluded items
            if item in UPDATE_EXCLUDE:
                logger.info(f"Skipping excluded item: {item}")
                continue
                
            # Copy files and directories
            if os.path.isdir(source):
                if os.path.exists(destination):
                    # Update existing directory
                    logger.info(f"Updating directory: {item}")
                    for root, dirs, files in os.walk(source):
                        # Get the relative path from source root
                        rel_path = os.path.relpath(root, source)
                        
                        for file in files:
                            # Skip updating files in excluded directories
                            if any(excluded in os.path.join(rel_path, file) for excluded in UPDATE_EXCLUDE):
                                continue
                                
                            src_file = os.path.join(root, file)
                            dst_file = os.path.join(destination, rel_path, file)
                            
                            # Ensure destination directory exists
                            dst_dir = os.path.dirname(dst_file)
                            if not os.path.exists(dst_dir):
                                os.makedirs(dst_dir)
                                
                            # Copy the file
                            logger.info(f"Copying file: {rel_path}/{file}")
                            shutil.copy2(src_file, dst_file)
                else:
                    # Copy new directory
                    logger.info(f"Adding new directory: {item}")
                    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*UPDATE_EXCLUDE))
            else:
                # Copy file
                logger.info(f"Copying file: {item}")
                shutil.copy2(source, destination)
        
        # Update version file
        logger.info(f"Updating version file to {latest_version}")
        update_version_file(latest_version)
        
        # Update other version files for consistency
        try:
            # Update package.json if it exists
            if os.path.exists('package.json'):
                with open('package.json', 'r') as f:
                    package_data = json.load(f)
                    
                package_data['version'] = latest_version
                
                with open('package.json', 'w') as f:
                    json.dump(package_data, f, indent=2)
                    
                logger.info(f"Updated package.json version to {latest_version}")
            
            # Update flask_app/version.json if it exists
            flask_version_file = os.path.join('flask_app', 'version.json')
            if os.path.exists(flask_version_file):
                with open(flask_version_file, 'r') as f:
                    flask_version_data = json.load(f)
                    
                flask_version_data['version'] = latest_version
                flask_version_data['build_date'] = time.strftime("%Y-%m-%d %H:%M:%S")
                
                with open(flask_version_file, 'w') as f:
                    json.dump(flask_version_data, f, indent=4)
                    
                logger.info(f"Updated flask_app/version.json to {latest_version}")
        except Exception as e:
            logger.error(f"Error updating additional version files: {e}")
        
        # Clean up
        try:
            os.remove(zip_path)
            shutil.rmtree(temp_dir)
            logger.info("Update cleanup completed")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        
        logger.info("Update applied successfully")
        return True
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
        response = requests.get(GITHUB_ALL_RELEASES_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"GitHub API error: {response.status_code} {response.text}")
            return []
        
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
            
            if not download_url:
                logger.warning(f"No download URL found for version {version_number}")
                continue
            
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
        
        return versions
        
    except Exception as e:
        logger.error(f"Error getting versions: {e}")
        logger.error(traceback.format_exc())
        return []

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
        zip_path = download_update(download_url)
        if not zip_path:
            logger.error("Failed to download update")
            return (False, None, "Failed to download update")
        
        logger.info("Applying update...")
        success = apply_update(zip_path, latest_version)
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