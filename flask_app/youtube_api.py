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
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpRequest
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
import google.oauth2.credentials

# Debug information
print(f"ELECTRON_APP environment variable: {os.environ.get('ELECTRON_APP')}")
print(f"Current working directory: {os.getcwd()}")
print(f"Python executable: {sys.executable}")

# YouTube API constants
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Determine appropriate directories for storing credentials
# Use multiple methods to detect if running in Electron
IS_ELECTRON = (
    os.environ.get('ELECTRON_APP') == 'true' or 
    os.path.exists(os.path.join(os.getcwd(), 'resources')) or
    'electron' in os.getcwd().lower() or
    os.path.exists(os.path.join(os.path.dirname(os.getcwd()), 'resources'))
)

print(f"Running in Electron environment: {IS_ELECTRON}")

if IS_ELECTRON:
    # Use app data directory when running in Electron
    if os.name == 'nt':  # Windows
        APP_DATA_DIR = os.path.join(os.environ.get('APPDATA', ''), 'youtube-auto-uploader')
    elif os.name == 'darwin':  # macOS
        APP_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'youtube-auto-uploader')
    else:  # Linux
        APP_DATA_DIR = os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader')
    
    # Create directory if it doesn't exist
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    print(f"Using Electron app data directory: {APP_DATA_DIR}")
    
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

# Create necessary directories
try:
    os.makedirs(API_CREDENTIALS_DIR, exist_ok=True)
    os.makedirs(TOKENS_DIR, exist_ok=True)
    print(f"Created directories: {API_CREDENTIALS_DIR}, {TOKENS_DIR}")
    
    # Test if directories are writable
    test_cred_file = os.path.join(API_CREDENTIALS_DIR, 'write_test.txt')
    test_token_file = os.path.join(TOKENS_DIR, 'write_test.txt')
    
    with open(test_cred_file, 'w') as f:
        f.write('test')
    with open(test_token_file, 'w') as f:
        f.write('test')
        
    os.remove(test_cred_file)
    os.remove(test_token_file)
    print("Directory write test successful")
except Exception as e:
    print(f"Error setting up directories: {e}")

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
            print(f"Migrated legacy client secret to {new_path}")
            
            # Also migrate token if it exists
            if os.path.exists(TOKEN_PICKLE_FILE):
                new_token_path = os.path.join(TOKENS_DIR, 'token_default.pickle')
                shutil.copy(TOKEN_PICKLE_FILE, new_token_path)
                os.rename(TOKEN_PICKLE_FILE, f"{TOKEN_PICKLE_FILE}.bak")
                print(f"Migrated legacy token to {new_token_path}")
        except Exception as e:
            print(f"Error migrating legacy credentials: {e}")

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
    print(f"Found {len(client_files)} client secret files: {client_files}")
    
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
            print(f"Added project: ID={parts}, file={file_path}, token={token_path}")
    
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
        print("No API projects found")
        return None
    
    # If no specific project requested, try to use the one that's already authenticated
    if project_id is None:
        # First check if we have a previously authenticated project
        for project in projects:
            if os.path.exists(project['token_path']):
                project_id = project['id']
                print(f"Using previously authenticated project: {project_id}")
                break
        
        # If still no project, pick a random one
        if project_id is None and projects:
            project = random.choice(projects)
            project_id = project['id']
            print(f"Selecting random project: {project_id}")
    
    # Find the selected project
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    if not selected_project:
        print(f"Project not found: {project_id}")
        return None
    
    # If we already have this client loaded, activate it
    if project_id in youtube_clients:
        print(f"Using cached client for project: {project_id}")
        youtube = youtube_clients[project_id]
        active_client_id = project_id
        return youtube
    
    # Try to authenticate with this project
    client_file = selected_project['file_path']
    token_file = selected_project['token_path']
    token_json = token_file.replace('.pickle', '.json')
    
    print(f"Authenticating with project: {project_id}")
    print(f"Client file: {client_file}")
    print(f"Token file: {token_file}")
    print(f"Token JSON file: {token_json}")
    print(f"Token file exists: {os.path.exists(token_file)}")
    print(f"Token JSON exists: {os.path.exists(token_json)}")
    
    # First try to load from pickle
    if os.path.exists(token_file):
        try:
            with open(token_file, 'rb') as token:
                try:
                    # Try to load the credentials
                    credentials = pickle.load(token)
                    print(f"Successfully loaded credentials from {token_file}")
                    
                    # Verify the credentials object is valid
                    if not hasattr(credentials, 'token') or not hasattr(credentials, 'refresh_token'):
                        print("Invalid credentials object, missing token attributes")
                        return None
                    
                except Exception as e:
                    print(f"Error unpickling credentials: {e}")
                    print("Creating fresh credentials")
                    # If loading fails, we'll need to authenticate again
                    return None
                
                # Check if credentials need refreshing
                print(f"Credentials expired: {credentials.expired}")
                print(f"Has refresh token: {bool(credentials.refresh_token)}")
                
                # Refresh if needed
                if credentials.expired and credentials.refresh_token:
                    try:
                        print("Refreshing expired credentials")
                        credentials.refresh(Request())
                        print("Successfully refreshed credentials")
                    except Exception as refresh_error:
                        print(f"Error refreshing credentials: {refresh_error}")
                        # If refresh fails, we might need to re-authenticate
                        return None
                    
                    # Save refreshed token with error handling
                    try:
                        with open(token_file, 'wb') as token_out:
                            pickle.dump(credentials, token_out)
                        print(f"Saved refreshed credentials to {token_file}")
                    except Exception as save_error:
                        print(f"Error saving refreshed credentials: {save_error}")
                
                # Use our improved builder with retry logic
                try:
                    client_builder = get_youtube_api_with_retry()
                    client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
                    
                    youtube_clients[project_id] = client
                    youtube = client
                    active_client_id = project_id
                    print(f"Successfully authenticated with project: {project_id}")
                    return client
                except Exception as build_error:
                    print(f"Error building YouTube client: {build_error}")
                    return None
        except Exception as e:
            print(f"Error loading credentials for project {project_id}: {e}")
    
    # If pickle fails, try JSON backup
    if os.path.exists(token_json):
        try:
            print(f"Attempting to load from JSON backup: {token_json}")
            with open(token_json, 'r') as f:
                token_data = json.load(f)
                credentials = google.oauth2.credentials.Credentials(
                    token=token_data['token'],
                    refresh_token=token_data['refresh_token'],
                    token_uri=token_data['token_uri'],
                    client_id=token_data['client_id'],
                    client_secret=token_data['client_secret'],
                    scopes=token_data['scopes']
                )
                
                # Save in pickle format for future use
                try:
                    with open(token_file, 'wb') as token_out:
                        pickle.dump(credentials, token_out)
                    print(f"Restored pickle credentials from JSON: {token_file}")
                except Exception as e:
                    print(f"Error saving restored credentials: {e}")
                    
                # Continue with client creation
                client_builder = get_youtube_api_with_retry()
                client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
                youtube_clients[project_id] = client
                youtube = client
                active_client_id = project_id
                print(f"Successfully authenticated from JSON with project: {project_id}")
                return client
        except Exception as e:
            print(f"Error loading from JSON backup: {e}")
    
    print(f"No valid tokens found for project {project_id}")
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

def get_youtube_service():
    """
    Get an authenticated YouTube service, try all available projects if needed
    
    Returns:
        object: YouTube API client if successful, None otherwise
    """
    global youtube
    
    # If we already have a YouTube client, return it
    if youtube:
        return youtube
    
    # Try to authenticate with each available project
    projects = get_available_api_projects()
    
    if not projects:
        # No projects available
        print("No API projects available")
        return None
    
    # Try each project until one works
    for project in projects:
        client = select_api_project(project['id'])
        if client:
            return client
    
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
    """
    Get the list of YouTube channels for the authenticated user
    
    Returns:
        list: List of channel dictionaries if successful, empty list otherwise
    """
    if not youtube:
        return []
    
    try:
        # Request channels list from YouTube API
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
        
        return channels
    except Exception as e:
        print(f"Error getting channel list: {e}")
        return []