"""
Configuration management for YouTube Auto Uploader
"""
import os
import json
import logging

# Configure logging
logger = logging.getLogger('config')

def get_config_path():
    """Get the absolute path to the config file"""
    # Try USER_DATA_DIR from Electron first
    user_data_dir = os.environ.get('USER_DATA_DIR')
    if user_data_dir:
        config_path = os.path.join(user_data_dir, 'config.json')
        logger.info(f"Using config path from USER_DATA_DIR: {config_path}")
        return config_path
    
    # Otherwise use standard paths
    if os.environ.get('ELECTRON_APP') == 'true':
        # In Electron, use the app data directory
        if os.name == 'nt':  # Windows
            app_data = os.environ.get('APPDATA', '')
            return os.path.join(app_data, 'youtube-auto-uploader', 'config.json')
        elif os.name == 'darwin':  # macOS
            return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'youtube-auto-uploader', 'config.json')
        else:  # Linux
            return os.path.join(os.path.expanduser('~'), '.youtube-auto-uploader', 'config.json')
    else:
        # Regular Flask app
        return 'config.json'

# Use absolute path when in Electron
CONFIG_FILE = get_config_path()

def load_config():
    """
    Load the application configuration from config.json file
    
    Returns:
        dict: The application configuration
    """
    default_config = {
        "watch_folder": "",
        "title_template": "Gameplay video - {filename}",
        "description": "Automatically uploaded gameplay video",
        "tags": "gameplay, gaming, auto-upload",
        "privacy": "unlisted",
        "delete_after_upload": True,
        "check_existing_files": True,
        "max_retries": 3,
        "upload_limit_duration": 24,  # hours
        "delete_retry_delay": 5,  # seconds
        "delete_retry_count": 5,  # times
        "selected_channel_id": None,  # Selected YouTube channel ID
        "theme": "light"  # Default theme
    }
    
    # Make sure the directory exists
    try:
        config_dir = os.path.dirname(CONFIG_FILE)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            logger.info(f"Created config directory: {config_dir}")
    except Exception as e:
        logger.error(f"Error creating config directory: {e}")
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config_data = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged_config = {**default_config, **config_data}
                return merged_config
        except Exception as e:
            logger.error(f"Error loading config from {CONFIG_FILE}: {e}")
            # Try to save the default config
            try:
                save_config(default_config)
            except:
                pass
            return default_config
    else:
        # Create the default config file if it doesn't exist
        try:
            save_config(default_config)
            logger.info(f"Created default config file at {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error creating default config file: {e}")
        
        return default_config

def save_config(config):
    """
    Save the application configuration to config.json file
    
    Args:
        config (dict): The configuration to save
    """
    # Ensure the directory exists
    directory = os.path.dirname(CONFIG_FILE)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Created config directory: {directory}")
        except Exception as e:
            logger.error(f"Error creating config directory: {e}")
            # Try to save to current directory as fallback
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            return
    
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Config saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Error saving config to {CONFIG_FILE}: {e}")
        # Try to save to current directory as fallback
        try:
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("Config saved to fallback location: config.json")
        except Exception as e2:
            logger.error(f"Error saving config to fallback location: {e2}")

def update_config(settings):
    """
    Update the configuration with new settings
    
    Args:
        settings (dict): New settings to apply
        
    Returns:
        dict: The updated configuration
    """
    config = load_config()
    config.update(settings)
    save_config(config)
    return config