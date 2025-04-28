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
import argparse
import json

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
    """Run the Flask application with improved error handling"""
    # Create version file if needed
    create_version_json()
    
    # Create the app
    app = create_app()
    
    # Start initialization in background to not block server startup
    threading.Thread(target=init_app_background, daemon=True).start()
    
    # Get port from environment variable (for Electron integration)
    port = int(os.environ.get('PORT', 5000))
    
    # Check if the port is already in use before attempting to bind
    def is_port_in_use(port):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0
            
    # If specified port is in use, try to find an available port
    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use, trying to find an available port")
        # Try ports in range 5000-5010, then 8000-8010
        for test_port in range(5000, 5010) + range(8000, 8010):
            if not is_port_in_use(test_port):
                logger.info(f"Found available port: {test_port}")
                port = test_port
                break
    
    try:
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            sys.exit(0)
            
        import signal
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        # Log that we're starting the server
        logger.info(f"Starting Flask server on http://127.0.0.1:{port}")
        
        # Run the Flask app - explicitly bind to IPv4 only with improved parameters
        app.run(
            host='127.0.0.1', 
            port=port, 
            debug=False, 
            threaded=True,
            use_reloader=False  # Disable reloader to prevent duplicate processes
        )
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"Port {port} is already in use. Please close any other instances of this application or processes using this port.")
            # If running in Electron, display an error dialog
            if os.environ.get('ELECTRON_APP') == 'true':
                # Create a simple error file that Electron can read
                try:
                    with open('flask_startup_error.txt', 'w') as f:
                        f.write(f"Port {port} is already in use. Please close any other instances of this application.")
                except:
                    pass
        else:
            logger.error(f"Error starting Flask app: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error starting Flask app: {e}")
        sys.exit(1)

if __name__ == '__main__':
    run_app()