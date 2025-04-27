"""
YouTube Auto Uploader - Main Application Entry Point

A tool for automatically uploading videos to YouTube from a watched folder.
"""
import os
import sys
import threading
import logging
import time
import traceback

# Enable insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.FileHandler("app.log"),
                       logging.StreamHandler()
                   ])
logger = logging.getLogger('app')

def create_app():
    """
    Create and configure the Flask application
    
    Returns:
        Flask: The configured Flask application
    """
    # Create Flask app
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    
    # Import routes here to prevent circular imports
    from routes import register_blueprints
    register_blueprints(app)
    
    return app

def init_app_background():
    """Initialize app components in background thread to not block server startup"""
    time.sleep(1)  # Wait for server to start
    
    try:
        logger.info("Starting background initialization...")
        
        # Import modules here to prevent slowdown of server start
        import config
        import youtube_api
        import uploader
        import file_monitor
        import auto_updater
        
        # Load configuration
        logger.info("Loading configuration...")
        app_config = config.load_config()
        
        # Initialize YouTube API
        logger.info("Initializing YouTube API...")
        youtube_api.get_youtube_service()
        
        # Sync channel selection in Electron environment
        if os.environ.get('ELECTRON_APP') == 'true':
            # Get channel ID from config before trying to sync
            channel_id = app_config.get('selected_channel_id')
            if channel_id:
                logger.info(f"Syncing channel ID: {channel_id}")
                youtube_api.save_selected_channel(channel_id)
            else:
                logger.info("No channel ID found in config to sync")
        
        # Initialize uploader
        logger.info("Initializing uploader...")
        uploader.init_uploader()
        
        # Check for updates
        if auto_updater.is_auto_update_enabled():
            logger.info("Checking for updates...")
            updated, new_version, error_message = auto_updater.run_update()
            
            if updated:
                logger.info(f"Updated to version {new_version}, restarting...")
                auto_updater.restart_application()
            elif error_message:
                logger.info(f"Update check result: {error_message}")
        else:
            logger.info("Auto-update is disabled")
            
        logger.info("Background initialization completed successfully")
    except Exception as e:
        logger.error(f"Error in background initialization: {e}")
        logger.error(traceback.format_exc())

def ensure_app_directories():
    """Create necessary directories for the application"""
    directories = [
        'credentials',
        'tokens',
        'logs',
        'temp'
    ]
    
    # If we're running in Electron and have a USER_DATA_DIR, prioritize that
    user_data_dir = os.environ.get('USER_DATA_DIR')
    if user_data_dir:
        for dir_name in directories:
            full_path = os.path.join(user_data_dir, dir_name)
            try:
                os.makedirs(full_path, exist_ok=True)
                logger.info(f"Created directory: {full_path}")
            except Exception as e:
                logger.error(f"Error creating directory {full_path}: {e}")
    
    # Also create local directories
    for dir_name in directories:
        try:
            os.makedirs(dir_name, exist_ok=True)
            logger.info(f"Created local directory: {dir_name}")
        except Exception as e:
            logger.error(f"Error creating local directory {dir_name}: {e}")

def create_version_json():
    """Create the version.json file if it doesn't exist"""
    version_file = 'version.json'
    if not os.path.exists(version_file):
        # Import here to avoid slow startup
        import auto_updater
        current_version = auto_updater.get_current_version()
        
        # Create a basic version file
        try:
            with open(version_file, 'w') as f:
                f.write(f'''{{
    "version": "{current_version}",
    "build_date": "{time.strftime('%Y-%m-%d %H:%M:%S')}",
    "auto_update": false
}}''')
            logger.info(f"Created version.json file with version {current_version}")
        except Exception as e:
            logger.error(f"Error creating version.json: {e}")

def run_app():
    """Run the Flask application"""
    try:
        # Ensure all required directories exist
        ensure_app_directories()
        
        # Create version file if needed
        create_version_json()
        
        # Create the app
        app = create_app()
        
        # Start initialization in background to not block server startup
        threading.Thread(target=init_app_background, daemon=True).start()
        
        # Get port from environment variable (for Electron integration)
        port = int(os.environ.get('PORT', 5000))
        
        logger.info(f"Starting Flask app on 127.0.0.1:{port}")
        
        # Run the Flask app - explicitly bind to IPv4 only
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Error starting Flask app: {e}")
        logger.error(traceback.format_exc())
        # Exit with error code to notify the wrapper
        sys.exit(1)

if __name__ == '__main__':
    run_app()