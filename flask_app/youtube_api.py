"""
YouTube API integration for YouTube Auto Uploader
"""
import os
import glob
import pickle
import random
import shutil
import time
import sys
import json
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpRequest
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
import google.oauth2.credentials

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler("youtube_api.log"),
                       logging.StreamHandler()
                   ])
logger = logging.getLogger('youtube_api')

# Debug information
logger.info(f"ELECTRON_APP environment variable: {os.environ.get('ELECTRON_APP')}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Python executable: {sys.executable}")

def debug_print_environment():
    """Print detailed environment information for debugging"""
    logger.info("\n==== DEBUGGING ENVIRONMENT INFO ====")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Platform: {sys.platform}")
    logger.info(f"User home directory: {os.path.expanduser('~')}")
    logger.info(f"ELECTRON_APP env variable: {os.environ.get('ELECTRON_APP')}")
    logger.info(f"USER_DATA_DIR env variable: {os.environ.get('USER_DATA_DIR')}")
    
    # Check for common locations
    for location in [
        os.path.expanduser('~'),
        os.environ.get('USER_DATA_DIR', ''),
        os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader'),
        os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader', 'tokens'),
        os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader', 'credentials'),
        os.environ.get('APPDATA', ''),
        os.path.join(os.environ.get('APPDATA', ''), 'youtube-auto-uploader'),
        os.path.join(os.environ.get('APPDATA', ''), 'youtube-auto-uploader', 'tokens'),
        'credentials',
        'tokens'
    ]:
        if location:
            logger.info(f"Checking location: {location}")
            logger.info(f"  - Exists: {os.path.exists(location)}")
            if os.path.exists(location):
                logger.info(f"  - Is directory: {os.path.isdir(location)}")
                if os.path.isdir(location):
                    logger.info(f"  - Readable: {os.access(location, os.R_OK)}")
                    logger.info(f"  - Writable: {os.access(location, os.W_OK)}")
                    try:
                        # List content
                        files = os.listdir(location)
                        logger.info(f"  - Contents: {files[:10]}{' (truncated)' if len(files) > 10 else ''}")
                    except Exception as e:
                        logger.info(f"  - Error listing contents: {e}")
    
    logger.info("==== END ENVIRONMENT INFO ====\n")

# Print detailed environment info at startup
debug_print_environment()

def get_guaranteed_token_storage():
    """Get a guaranteed-writable token storage location"""
    # Try user data dir from Electron first
    user_data_dir = os.environ.get('USER_DATA_DIR')
    if user_data_dir and os.path.exists(user_data_dir) and os.access(user_data_dir, os.W_OK):
        token_folder = os.path.join(user_data_dir, 'tokens')
    else:
        # Use Documents folder which should be reliably writable
        if os.name == 'nt':  # Windows
            docs_folder = os.path.join(os.path.expanduser('~'), 'Documents')
        else:
            docs_folder = os.path.expanduser('~/Documents')
        
        # Create a hidden folder in Documents
        token_folder = os.path.join(docs_folder, '.youtube_uploader_tokens')
    
    # Ensure the folder exists
    try:
        os.makedirs(token_folder, exist_ok=True)
        logger.info(f"Using token storage: {token_folder}")
    except Exception as e:
        logger.error(f"Error creating token folder: {e}")
        # Final fallback - current directory
        token_folder = os.path.join(os.getcwd(), 'tokens')
        os.makedirs(token_folder, exist_ok=True)
        logger.info(f"Using fallback token storage: {token_folder}")
    
    # Test write access
    try:
        test_file = os.path.join(token_folder, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        logger.info(f"Confirmed write access to token folder")
    except Exception as e:
        logger.error(f"Cannot write to token folder: {e}")
        
    return token_folder

# Save and load tokens with simple storage
def save_token_simple(credentials, project_id="default"):
    """Save token to a simple, reliable location"""
    token_folder = get_guaranteed_token_storage()
    token_file = os.path.join(token_folder, f"youtube_token_{project_id}.pickle")
    
    try:
        logger.info(f"Saving token to: {token_file}")
        with open(token_file, 'wb') as f:
            pickle.dump(credentials, f)
        logger.info(f"Token saved successfully!")
        return True
    except Exception as e:
        logger.error(f"Error saving token: {e}")
        return False

def load_token_simple(project_id="default"):
    """Load token from a simple, reliable location"""
    token_folder = get_guaranteed_token_storage()
    token_file = os.path.join(token_folder, f"youtube_token_{project_id}.pickle")
    
    if not os.path.exists(token_file):
        logger.info(f"Token file does not exist: {token_file}")
        return None
    
    try:
        logger.info(f"Loading token from: {token_file}")
        with open(token_file, 'rb') as f:
            credentials = pickle.load(f)
        logger.info(f"Token loaded successfully!")
        return credentials
    except Exception as e:
        logger.error(f"Error loading token: {e}")
        return None

# YouTube API constants
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Determine appropriate directories for storing credentials
# Use simple Electron detection
IS_ELECTRON = os.environ.get('ELECTRON_APP') == 'true'

logger.info(f"Running in Electron environment: {IS_ELECTRON}")

if IS_ELECTRON:
    # Use user data dir from environment if available
    USER_DATA_DIR = os.environ.get('USER_DATA_DIR')
    if USER_DATA_DIR and os.path.exists(USER_DATA_DIR):
        APP_DATA_DIR = USER_DATA_DIR
    else:
        # Fall back to standard locations
        if os.name == 'nt':  # Windows
            APP_DATA_DIR = os.path.join(os.environ.get('APPDATA', ''), 'youtube-auto-uploader')
        elif os.name == 'darwin':  # macOS
            APP_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'youtube-auto-uploader')
        else:  # Linux
            APP_DATA_DIR = os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader')
    
    # Create directory if it doesn't exist
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    logger.info(f"Using Electron app data directory: {APP_DATA_DIR}")
    
    API_CREDENTIALS_DIR = os.path.join(APP_DATA_DIR, 'credentials')
    TOKENS_DIR = os.path.join(APP_DATA_DIR, 'tokens')
    
    # Legacy paths for backward compatibility in Electron
    CLIENT_SECRETS_FILE = os.path.join(APP_DATA_DIR, 'client_secret.json')
    TOKEN_PICKLE_FILE = os.path.join(APP_DATA_DIR, 'token.pickle')
else:
    # Regular relative paths when running as Flask app
    API_CREDENTIALS_DIR = 'credentials'
    TOKENS_DIR = 'tokens'
    
    # Legacy paths for backward compatibility
    CLIENT_SECRETS_FILE = 'client_secret.json'
    TOKEN_PICKLE_FILE = 'token.pickle'

# Create necessary directories with better error handling
for directory in [API_CREDENTIALS_DIR, TOKENS_DIR]:
    try:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Created directory: {directory}")
    except Exception as e:
        logger.error(f"Error creating directory {directory}: {e}")
        # Try to create in home directory as fallback
        fallback_dir = os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader', os.path.basename(directory))
        try:
            os.makedirs(fallback_dir, exist_ok=True)
            logger.info(f"Created fallback directory: {fallback_dir}")
            if directory == API_CREDENTIALS_DIR:
                API_CREDENTIALS_DIR = fallback_dir
            elif directory == TOKENS_DIR:
                TOKENS_DIR = fallback_dir
        except Exception as fallback_e:
            logger.error(f"Error creating fallback directory: {fallback_e}")

# Track YouTube clients and active client
youtube_clients = {}
active_client_id = None
youtube = None  # Current active client

# Track upload limits
upload_limit_reached = False
upload_limit_reset_time = None

def migrate_legacy_credentials():
    """Migrate legacy credentials to the new directory structure"""
    # Check if old-style client secret exists and migrate it
    if os.path.exists(CLIENT_SECRETS_FILE):
        try:
            new_path = os.path.join(API_CREDENTIALS_DIR, 'client_secret_default.json')
            shutil.copy(CLIENT_SECRETS_FILE, new_path)
            os.rename(CLIENT_SECRETS_FILE, f"{CLIENT_SECRETS_FILE}.bak")
            logger.info(f"Migrated legacy client secret to {new_path}")
            
            # Also migrate token if it exists
            if os.path.exists(TOKEN_PICKLE_FILE):
                new_token_path = os.path.join(TOKENS_DIR, 'token_default.pickle')
                shutil.copy(TOKEN_PICKLE_FILE, new_token_path)
                os.rename(TOKEN_PICKLE_FILE, f"{TOKEN_PICKLE_FILE}.bak")
                logger.info(f"Migrated legacy token to {new_token_path}")
        except Exception as e:
            logger.error(f"Error migrating legacy credentials: {e}")

def get_available_api_projects():
    """
    Get a list of available API projects based on client secret files
    
    Returns:
        list: List of dictionaries containing project information
    """
    # First check if legacy credentials exist and migrate them
    migrate_legacy_credentials()
    
    # Look for all client secret files in the credentials directory
    client_files = glob.glob(os.path.join(API_CREDENTIALS_DIR, 'client_secret_*.json'))
    logger.info(f"Found {len(client_files)} client secret files: {client_files}")
    
    # Extract project IDs from filenames
    projects = []
    for file_path in client_files:
        filename = os.path.basename(file_path)
        # Extract project ID from filename (format: client_secret_PROJECT_ID.json)
        if '_' in filename and '.' in filename:
            parts = filename.split('_', 1)[1].split('.')[0]
            token_path = os.path.join(TOKENS_DIR, f'token_{parts}.pickle')
            projects.append({
                'id': parts,
                'file_path': file_path,
                'token_path': token_path
            })
            logger.info(f"Added project: ID={parts}, file={file_path}, token={token_path}")
    
    return projects

def get_youtube_api_with_retry():
    """
    Creates YouTube API client with retry capabilities for transient network issues
    
    Returns:
        function: A function to build YouTube API clients with retry logic
    """
    # Store the original execute method
    original_execute = HttpRequest.execute
    
    # Create a patched execute method with retry logic
    def _patched_execute(self, *args, **kwargs):
        from config import load_config
        
        config = load_config()
        max_retries = config.get('max_retries', 3)
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                return original_execute(self, *args, **kwargs)
            except HttpError as e:
                # Don't retry for most HTTP errors
                if e.resp.status < 500:
                    raise
                retry_count += 1
                if retry_count > max_retries:
                    raise
                # Exponential backoff
                time.sleep(2 ** retry_count)
            except Exception as e:
                error_str = str(e).lower()
                # Retry on network errors
                if ("ssl" in error_str or 
                   "connection" in error_str or 
                   "timeout" in error_str or 
                   "broken pipe" in error_str):
                    retry_count += 1
                    if retry_count > max_retries:
                        raise
                    # Exponential backoff
                    time.sleep(2 ** retry_count)
                else:
                    # Don't retry for other types of errors
                    raise
    
    # Patch the execute method
    HttpRequest.execute = _patched_execute
    
    # All subsequent API calls will use our patched execute method
    return build

def get_youtube_service():
    """
    Get an authenticated YouTube service, try all available projects if needed
    
    Returns:
        object: YouTube API client if successful, None otherwise
    """
    global youtube, active_client_id
    
    logger.info("Attempting to get YouTube service...")
    
    # If we already have a YouTube client, return it
    if youtube:
        logger.info("Using existing YouTube client")
        return youtube
    
    # Try to restore from our simple storage first, for any project
    projects = get_available_api_projects()
    
    if not projects:
        logger.info("No API projects available")
        return None
    
    logger.info(f"Found {len(projects)} API projects")
    
    # First try our simple storage
    logger.info("Checking simple token storage first...")
    for project in projects:
        project_id = project['id']
        logger.info(f"Checking simple storage for project: {project_id}")
        
        credentials = load_token_simple(project_id)
        if credentials:
            try:
                logger.info(f"Found token for project {project_id} in simple storage")
                
                # Refresh if needed
                if credentials.expired and credentials.refresh_token:
                    logger.info("Token expired, refreshing...")
                    credentials.refresh(Request())
                    save_token_simple(credentials, project_id)
                
                # Build the client
                client_builder = get_youtube_api_with_retry()
                client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
                
                youtube_clients[project_id] = client
                youtube = client
                active_client_id = project_id
                
                logger.info(f"Authenticated with project: {project_id} using simple storage")
                
                # After successful authentication, try to restore the channel
                channel_id = get_selected_channel()
                if channel_id:
                    # Update config to ensure it has the channel ID
                    from config import load_config, update_config
                    config_data = load_config()
                    config_data['selected_channel_id'] = channel_id
                    update_config(config_data)
                
                return client
            except Exception as e:
                logger.error(f"Error creating client from simple storage: {e}")
    
    # If simple storage didn't work, try the standard approach
    logger.info("Simple storage check failed, trying standard methods...")
    
    # Try each project until one works
    for project in projects:
        logger.info(f"Trying standard authentication for project: {project['id']}")
        client = select_api_project(project['id'])
        if client:
            return client
    
    logger.info("All authentication attempts failed")
    return None

def select_api_project(project_id=None):
    """
    Select an API project to use
    
    Args:
        project_id (str, optional): ID of the project to select. If None, try to find an authenticated project.
        
    Returns:
        object: YouTube API client if successful, None otherwise
    """
    global youtube, active_client_id
    
    projects = get_available_api_projects()
    
    if not projects:
        logger.info("No API projects found")
        return None
    
    # If no specific project requested, try to use the one that's already authenticated
    if project_id is None:
        # First check for a project in simple storage
        for project in projects:
            if load_token_simple(project['id']):
                project_id = project['id']
                logger.info(f"Found previously authenticated project in simple storage: {project_id}")
                break
                
        # If still no project found, check standard locations
        if project_id is None:
            for project in projects:
                if os.path.exists(project['token_path']):
                    project_id = project['id']
                    logger.info(f"Found previously authenticated project in standard location: {project_id}")
                    break
        
        # If still no project, pick a random one
        if project_id is None and projects:
            project = random.choice(projects)
            project_id = project['id']
            logger.info(f"No authenticated project found, selecting random project: {project_id}")
    
    # Find the selected project
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    if not selected_project:
        logger.info(f"Project not found: {project_id}")
        return None
    
    # If we already have this client loaded, activate it
    if project_id in youtube_clients:
        logger.info(f"Using cached client for project: {project_id}")
        youtube = youtube_clients[project_id]
        active_client_id = project_id
        return youtube
    
    # Try to authenticate with simple storage first
    credentials = load_token_simple(project_id)
    
    # If simple storage didn't work, try standard paths
    if not credentials:
        logger.info(f"No token in simple storage for {project_id}, trying standard location...")
        client_file = selected_project['file_path']
        token_file = selected_project['token_path']
        
        # Try to load from standard location
        if os.path.exists(token_file):
            try:
                with open(token_file, 'rb') as token:
                    credentials = pickle.load(token)
                logger.info(f"Loaded credentials from standard location: {token_file}")
                
                # Save to simple storage for next time
                save_token_simple(credentials, project_id)
                
            except Exception as e:
                logger.error(f"Error loading credentials from standard location: {e}")
                return None
    
    if not credentials:
        logger.info(f"No valid credentials found for project {project_id}")
        return None
    
    # Check if credentials need refreshing
    logger.info(f"Credentials expired: {getattr(credentials, 'expired', 'unknown')}")
    logger.info(f"Has refresh token: {bool(getattr(credentials, 'refresh_token', None))}")
    
    # Refresh if needed
    if getattr(credentials, 'expired', False) and getattr(credentials, 'refresh_token', None):
        try:
            logger.info("Refreshing expired credentials")
            credentials.refresh(Request())
            logger.info("Successfully refreshed credentials")
            
            # Save refreshed credentials
            save_token_simple(credentials, project_id)
            
        except Exception as refresh_error:
            logger.error(f"Error refreshing credentials: {refresh_error}")
            return None
    
    # Use our improved builder with retry logic
    try:
        client_builder = get_youtube_api_with_retry()
        client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        
        youtube_clients[project_id] = client
        youtube = client
        active_client_id = project_id
        logger.info(f"Successfully authenticated with project: {project_id}")
        return client
    except Exception as build_error:
        logger.error(f"Error building YouTube client: {build_error}")
        return None

def save_selected_channel(channel_id):
    """
    Save the selected channel ID to multiple reliable locations
    
    Args:
        channel_id (str): The selected YouTube channel ID
    """
    if not channel_id:
        logger.info("No channel ID provided to save")
        return False
    
    # List of all possible storage locations to try
    locations = [
        # AppData location
        os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'youtube-auto-uploader', 'channel.txt'),
        # Home directory (hidden file)
        os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader-channel.txt'),
        # Documents folder
        os.path.join(os.path.expanduser('~'), 'Documents', '.youtube-channel.txt'),
        # Local AppData
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'youtube-auto-uploader', 'channel.txt'),
        # Current directory
        'selected_channel.txt'
    ]
    
    # Add user data directory from environment if available
    user_data_dir = os.environ.get('USER_DATA_DIR')
    if user_data_dir:
        locations.append(os.path.join(user_data_dir, 'channel.txt'))
    
    success = False
    
    # Try saving to all locations
    for location in locations:
        try:
            # Create directory if needed
            directory = os.path.dirname(location)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
            # Write the channel ID
            with open(location, 'w') as f:
                f.write(channel_id)
            
            logger.info(f"Saved channel ID to: {location}")
            success = True
        except Exception as e:
            logger.error(f"Failed to save channel ID to {location}: {e}")
    
    # Also save as JSON in home directory for extra reliability
    try:
        json_file = os.path.join(os.path.expanduser('~'), '.youtube-channel.json')
        with open(json_file, 'w') as f:
            json.dump({"channel_id": channel_id}, f)
        logger.info(f"Saved channel ID to JSON: {json_file}")
        success = True
    except Exception as e:
        logger.error(f"Failed to save channel ID to JSON: {e}")
    
    from config import load_config, save_config
    
    # Update config.json directly
    try:
        config_data = load_config()
        config_data['selected_channel_id'] = channel_id
        save_config(config_data)
        logger.info(f"Updated channel ID in config.json: {channel_id}")
        success = True
    except Exception as e:
        logger.error(f"Failed to update config.json: {e}")
    
    # Save specifically to AppData for Electron
    if os.environ.get('ELECTRON_APP') == 'true' and os.name == 'nt':
        app_data = os.environ.get('APPDATA', '')
        appdata_path = os.path.join(app_data, 'youtube-auto-uploader', 'channel.json')
        try:
            directory = os.path.dirname(appdata_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            with open(appdata_path, 'w') as f:
                json.dump({"channel_id": channel_id}, f)
            logger.info(f"Saved channel ID to AppData: {appdata_path}")
            success = True
        except Exception as e:
            logger.error(f"Failed to save to AppData: {e}")
    
    return success

def get_selected_channel():
    """
    Get the previously selected channel ID from any available source
    
    Returns:
        str: The channel ID or None if not found
    """
    # First try getting from config directly
    try:
        from config import load_config
        config_data = load_config()
        channel_id = config_data.get('selected_channel_id')
        if channel_id:
            logger.info(f"Loaded channel ID from config: {channel_id}")
            return channel_id
    except Exception as e:
        logger.error(f"Error loading from config: {e}")
    
    # For Electron, prioritize AppData location
    if os.environ.get('ELECTRON_APP') == 'true':
        app_data_locations = []
        
        # Try USER_DATA_DIR first if available
        user_data_dir = os.environ.get('USER_DATA_DIR')
        if user_data_dir:
            app_data_locations.append(os.path.join(user_data_dir, 'channel.txt'))
            app_data_locations.append(os.path.join(user_data_dir, 'channel.json'))
        
        if os.name == 'nt':  # Windows
            app_data = os.environ.get('APPDATA', '')
            app_data_locations.extend([
                os.path.join(app_data, 'youtube-auto-uploader', 'channel.json'),
                os.path.join(app_data, 'youtube-auto-uploader', 'channel.txt')
            ])
        
        # Try AppData locations first
        for location in app_data_locations:
            try:
                if location.endswith('.json') and os.path.exists(location):
                    with open(location, 'r') as f:
                        data = json.load(f)
                        channel_id = data.get('channel_id')
                        if channel_id:
                            logger.info(f"Loaded channel ID from {location}")
                            return channel_id
                elif os.path.exists(location):
                    with open(location, 'r') as f:
                        channel_id = f.read().strip()
                        if channel_id:
                            logger.info(f"Loaded channel ID from {location}")
                            return channel_id
            except Exception as e:
                logger.error(f"Failed to load from {location}: {e}")

    # List of all possible storage locations to try as backup
    locations = [
        # Home directory (hidden file)
        os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader-channel.txt'),
        # Documents folder
        os.path.join(os.path.expanduser('~'), 'Documents', '.youtube-channel.txt'),
        # Current directory
        'selected_channel.txt',
        # JSON backup
        os.path.join(os.path.expanduser('~'), '.youtube-channel.json')
    ]
    
    # Check each location
    for location in locations:
        try:
            if location.endswith('.json') and os.path.exists(location):
                with open(location, 'r') as f:
                    data = json.load(f)
                    channel_id = data.get('channel_id')
                    if channel_id:
                        logger.info(f"Loaded channel ID from {location}")
                        return channel_id
            elif os.path.exists(location):
                with open(location, 'r') as f:
                    channel_id = f.read().strip()
                    if channel_id:
                        logger.info(f"Loaded channel ID from {location}")
                        return channel_id
        except Exception as e:
            logger.error(f"Failed to load from {location}: {e}")
    
    logger.info("No saved channel ID found in any location")
    return None

def handle_upload_limit_error(previous_client_id):
    """
    Try to switch to a different API client when hitting upload limits
    
    Args:
        previous_client_id (str): ID of the client that hit the upload limit
        
    Returns:
        object: New YouTube API client if available, None otherwise
    """
    # Mark current client as limited
    if previous_client_id:
        youtube_clients.pop(previous_client_id, None)
    
    # Try to find another authenticated client
    projects = get_available_api_projects()
    for project in projects:
        if project['id'] != previous_client_id and os.path.exists(project['token_path']):
            return select_api_project(project['id'])
    
    return None

def set_upload_limit_reached(duration_hours=24):
    """
    Set the upload limit reached flag and calculate reset time
    
    Args:
        duration_hours (int): Number of hours to wait before resetting
    """
    global upload_limit_reached, upload_limit_reset_time
    upload_limit_reached = True
    upload_limit_reset_time = datetime.now() + timedelta(hours=duration_hours)

def get_upload_limit_status():
    """
    Get the current upload limit status
    
    Returns:
        tuple: (is_limit_reached, reset_time)
    """
    # Reset upload limit if time has passed
    global upload_limit_reached, upload_limit_reset_time
    
    if upload_limit_reached and upload_limit_reset_time and datetime.now() > upload_limit_reset_time:
        upload_limit_reached = False
        upload_limit_reset_time = None
        
    return (upload_limit_reached, upload_limit_reset_time)

def get_channel_list():
    """Get the list of YouTube channels for the authenticated user"""
    if not youtube:
        logger.info("Cannot get channel list: No YouTube client available")
        return []
    
    try:
        # First try listing by 'mine' parameter
        channels_response = youtube.channels().list(
            part='snippet,contentDetails',
            mine=True
        ).execute()
        
        channels = []
        for channel in channels_response.get('items', []):
            channels.append({
                'id': channel['id'],
                'title': channel['snippet']['title'],
                'thumbnail': channel['snippet']['thumbnails']['default']['url'],
                'uploads_playlist': channel['contentDetails']['relatedPlaylists']['uploads']
            })
            
        if not channels:
            # Fallback - try listing by 'managedByMe' parameter
            channels_response = youtube.channels().list(
                part='snippet,contentDetails',
                managedByMe=True
            ).execute()
            
            for channel in channels_response.get('items', []):
                channels.append({
                    'id': channel['id'],
                    'title': channel['snippet']['title'],
                    'thumbnail': channel['snippet']['thumbnails']['default']['url'],
                    'uploads_playlist': channel['contentDetails']['relatedPlaylists']['uploads']
                })
        
        logger.info(f"Found {len(channels)} YouTube channels")
        return channels
    except Exception as e:
        logger.error(f"Error getting channel list: {e}")
        # Return a default channel if available from config
        from config import load_config
        config_data = load_config()
        channel_id = config_data.get('selected_channel_id')
        if channel_id:
            logger.info(f"Using fallback channel ID from config: {channel_id}")
            return [{
                'id': channel_id,
                'title': 'Your YouTube Channel',
                'thumbnail': 'https://www.youtube.com/s/desktop/63c65178/img/favicon_144x144.png',
                'uploads_playlist': ''
            }]
        return []