"""
YouTube Auto Uploader - Main Application Entry Point

A tool for automatically uploading videos to YouTube from a watched folder.
"""
import os
import sys
import threading
import logging
import time

# Enable insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
        # Import modules here to prevent slowdown of server start
        import config
        import youtube_api
        import uploader
        import file_monitor
        import auto_updater
        
        # Load configuration
        app_config = config.load_config()
        
        # Initialize YouTube API
        youtube_api.get_youtube_service()
        
        # Sync channel selection in Electron environment
        if os.environ.get('ELECTRON_APP') == 'true':
            # Get channel ID from config before trying to sync
            channel_id = app_config.get('selected_channel_id')
            if channel_id:
                youtube_api.save_selected_channel(channel_id)
        
        # Initialize uploader
        uploader.init_uploader()
        
        # Start monitoring if configured
        if app_config.get('watch_folder') and youtube_api.get_youtube_service():
            file_monitor.start_monitoring(
                app_config.get('watch_folder'),
                app_config.get('check_existing_files', True)
            )
            
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
    except Exception as e:
        logger.error(f"Error in background initialization: {e}")

def create_version_json():
    """Create the version.json file if it doesn't exist"""
    if not os.path.exists('version.json'):
        # Import here to avoid slow startup
        import auto_updater
        auto_updater.get_current_version()
        logger.info("Created version.json file")

def run_app():
    """Run the Flask application"""
    # Create version file if needed
    create_version_json()
    
    # Create the app
    app = create_app()
    
    # Start initialization in background to not block server startup
    threading.Thread(target=init_app_background, daemon=True).start()
    
    # Get port from environment variable (for Electron integration)
    port = int(os.environ.get('PORT', 5000))
    
    # Run the Flask app - explicitly bind to IPv4 only
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)

if __name__ == '__main__':
    run_app()