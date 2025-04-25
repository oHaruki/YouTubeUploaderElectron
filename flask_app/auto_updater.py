"""
Simplified version checker for YouTube Auto Uploader
"""
import os
import json
import logging
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
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
VERSION_FILE = "version.json"

def get_current_version():
    """
    Get the current installed version
    
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
    
    # Return the first available version, prioritized by the order above
    if version_sources:
        source, version = version_sources[0]
        logger.info(f"Using version from {source}: {version}")
        return version
    
    # Absolute fallback
    logger.warning(f"No version information found, using default: 0.0.0")
    return "0.0.0"

def check_for_update():
    """
    Check if a newer version is available on GitHub
    
    Returns:
        tuple: (update_available, latest_version, release_page_url, release_notes)
    """
    current_version = get_current_version()
    
    try:
        logger.info(f"Checking for updates (current version: {current_version})")
        
        # Set up proper headers for GitHub API
        headers = {
            'User-Agent': 'YT-Auto-Uploader-App',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Try the latest release endpoint
        logger.info(f"Requesting latest release from: {GITHUB_API_URL}")
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"GitHub API error: {response.status_code} {response.text}")
            return (False, None, GITHUB_RELEASES_URL, None)
            
        # Get latest release data
        release_data = response.json()
        tag_name = release_data.get("tag_name", "")
        latest_version = tag_name.lstrip('v') if tag_name else ""
        logger.info(f"Latest version: {latest_version}")
        
        if not latest_version:
            logger.warning(f"Invalid release data: version={latest_version}")
            return (False, latest_version, GITHUB_RELEASES_URL, None)
        
        try:
            # Compare versions
            is_newer = version.parse(latest_version) > version.parse(current_version)
            logger.info(f"Version comparison: {latest_version} > {current_version} = {is_newer}")
            
            return (is_newer, latest_version, GITHUB_RELEASES_URL, release_data.get("body", "No release notes available."))
        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            # Try simple string comparison as fallback
            is_newer = latest_version > current_version
            logger.info(f"Fallback string comparison: {latest_version} > {current_version} = {is_newer}")
            
            return (is_newer, latest_version, GITHUB_RELEASES_URL, release_data.get("body", "No release notes available."))
            
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return (False, None, GITHUB_RELEASES_URL, None)

def get_all_versions():
    """
    Get a list of all available versions from GitHub
    
    Returns:
        list: List of version objects with details
    """
    try:
        logger.info("Fetching available versions")
        
        # Set up proper headers for GitHub API
        headers = {
            'User-Agent': 'YT-Auto-Uploader-App',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        current_version = get_current_version()
        logger.info(f"Current version: {current_version}")
        
        # Get release info
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"GitHub API error: {response.status_code} {response.text}")
            # Return at least the current version
            return [{
                'id': 'current',
                'version': current_version,
                'name': f'Current Version {current_version}',
                'date': '',
                'notes': 'This is your currently installed version.',
                'is_current': True,
                'release_url': GITHUB_RELEASES_URL
            }]
        
        release = response.json()
        logger.info(f"Found latest release: {release.get('tag_name')}")
        
        versions = []
        
        # Add current version
        versions.append({
            'id': 'current',
            'version': current_version,
            'name': f'Current Version {current_version}',
            'date': '',
            'notes': 'This is your currently installed version.',
            'is_current': True,
            'release_url': GITHUB_RELEASES_URL
        })
        
        # Add latest release from GitHub
        tag_name = release.get("tag_name", "")
        version_number = tag_name.lstrip('v') if tag_name else ""
        
        if version_number and version_number != current_version:
            versions.append({
                'id': str(release.get("id", "")),
                'version': version_number,
                'name': release.get("name") or f"Version {version_number}",
                'date': release.get("published_at", ""),
                'notes': release.get("body", "No release notes available."),
                'is_current': False,
                'release_url': release.get("html_url", GITHUB_RELEASES_URL)
            })
        
        return versions
        
    except Exception as e:
        logger.error(f"Error getting versions: {e}")
        
        # Return at least the current version
        return [{
            'id': 'current',
            'version': current_version,
            'name': f'Current Version {current_version}',
            'date': '',
            'notes': 'This is your currently installed version.',
            'is_current': True,
            'release_url': GITHUB_RELEASES_URL
        }]

def is_auto_update_enabled():
    """Stub function to maintain compatibility"""
    return False

def set_auto_update_enabled(enabled=False):
    """Stub function to maintain compatibility"""
    pass

def run_update():
    """Check for updates and return information"""
    try:
        update_available, latest_version, release_url, release_notes = check_for_update()
        
        if not update_available:
            logger.info("No updates available")
            return (False, None, "No updates available")
        
        logger.info(f"Update available: {latest_version}")
        return (True, latest_version, None)
    except Exception as e:
        logger.error(f"Update check error: {e}")
        return (False, None, str(e))

def restart_application():
    """Stub function to maintain compatibility"""
    logger.info("Restart application called, but not implemented")
    pass

if __name__ == "__main__":
    # Manual test
    print(f"Current version: {get_current_version()}")
    
    print("Checking for updates...")
    update_available, latest_version, release_url, release_notes = check_for_update()
    print(f"Update available: {update_available}")
    
    if update_available:
        print(f"Latest version: {latest_version}")
        print(f"Release URL: {release_url}")
        print(f"Release notes: {release_notes}")
    else:
        print("No updates available or error checking for updates.")