const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, shell, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs'); // Add fs module
const { spawn, spawnSync } = require('child_process');
const http = require('http'); // Use http instead of fetch
const portfinder = require('portfinder');
const isDev = process.env.NODE_ENV === 'development';
const Store = require('electron-store');
const log = require('electron-log');

// Configure logger
log.transports.file.level = 'info';
log.info('Application starting...');

// Initialize settings store
const store = new Store({
  defaults: {
    autoLaunch: false,
    startMinimized: false,
    port: 5000
  }
});

// Application state
let mainWindow = null;
let tray = null;
let flaskProcess = null;
let flaskPort = store.get('port');
let serverRunning = false;
let quitting = false;
let startupMinimize = store.get('startMinimized');

// Check if Python is installed and get the correct executable path
const checkPythonPath = () => {
  // First, try to detect common Python locations
  const pythonCommands = [
    process.platform === 'win32' ? 'python' : 'python3',
    process.platform === 'win32' ? 'py' : 'python',
    'python3',
    'python'
  ];

  for (const cmd of pythonCommands) {
    try {
      // Using spawnSync to check if the command exists
      const result = spawnSync(cmd, ['--version'], {
        stdio: 'pipe',
        encoding: 'utf8'
      });
      
      if (result.status === 0) {
        log.info(`Found Python command: ${cmd} (${result.stdout.trim()})`);
        return cmd;
      }
    } catch (error) {
      log.info(`Command ${cmd} not found or failed: ${error.message}`);
      // Continue to try the next command
    }
  }
  
  // If we get here, we couldn't find Python
  return null;
};

// Try to connect to a server on the given port
const tryConnect = async (port) => {
  return new Promise(resolve => {
    const req = http.get(`http://localhost:${port}/`, {timeout: 1000}, (res) => {
      resolve(res.statusCode < 400);
    });
    
    req.on('error', () => {
      resolve(false);
    });
    
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
};

// Start Flask server
const startFlaskServer = async () => {
  if (serverRunning) {
    log.info('Flask server is already running');
    return true;
  }

  try {
    // Find an available port
    flaskPort = await portfinder.getPortPromise({ port: flaskPort });
    store.set('port', flaskPort);
    log.info(`Starting Flask server on port ${flaskPort}...`);

    // Check for Python executable
    const pythonCommand = checkPythonPath();
    if (!pythonCommand) {
      const errorMessage = 'Python is required but was not found on your system. Please install Python and try again.';
      log.error(errorMessage);
      dialog.showErrorBox('Python Not Found', errorMessage);
      return false;
    }

    // Ensure the Flask app script exists
    const scriptPath = path.join(app.getAppPath(), 'flask_app', 'app.py');
    if (!fs.existsSync(scriptPath)) {
      const errorMessage = `Flask app script not found at ${scriptPath}`;
      log.error(errorMessage);
      dialog.showErrorBox('Flask App Not Found', errorMessage);
      return false;
    }
    log.info(`Using script path: ${scriptPath}`);
    
    // Environment variables for Flask
    const env = { ...process.env, PORT: flaskPort.toString() };
    
    // Start Flask as a child process
    flaskProcess = spawn(pythonCommand, [scriptPath], { 
      env,
      shell: true, // Use shell on Windows to find python properly
      stdio: 'pipe' // Capture stdio for logging
    });
    
    flaskProcess.stdout.on('data', (data) => {
      log.info(`Flask stdout: ${data}`);
      
      // Check if the output contains the actual port Flask is using
      const match = data.toString().match(/Running on http:\/\/127\.0\.0\.1:(\d+)/);
      if (match && match[1]) {
        const actualPort = parseInt(match[1]);
        if (actualPort !== flaskPort) {
          log.info(`Flask is actually using port ${actualPort} instead of ${flaskPort}`);
          flaskPort = actualPort;
        }
      }
    });
    
    flaskProcess.stderr.on('data', (data) => {
      log.error(`Flask stderr: ${data}`);
      
      // Also check stderr for port information
      const match = data.toString().match(/Running on http:\/\/127\.0\.0\.1:(\d+)/);
      if (match && match[1]) {
        const actualPort = parseInt(match[1]);
        if (actualPort !== flaskPort) {
          log.info(`Flask is actually using port ${actualPort} instead of ${flaskPort}`);
          flaskPort = actualPort;
        }
      }
    });
    
    flaskProcess.on('error', (err) => {
      log.error(`Failed to start Flask process: ${err}`);
      dialog.showErrorBox('Flask Error', `Failed to start Flask: ${err.message}`);
      return false;
    });
    
    flaskProcess.on('close', (code) => {
      log.info(`Flask server process exited with code ${code}`);
      serverRunning = false;
      
      // Restart server if it crashes and app is not quitting
      if (!quitting && code !== 0) {
        log.info('Flask server crashed, restarting...');
        setTimeout(startFlaskServer, 1000);
      }
    });

    // Check if Flask server starts successfully
    const maxWaitTime = 30000; // 30 seconds (increased from 10)
    const startTime = Date.now();
    
    // Try to connect to the server
    while (Date.now() - startTime < maxWaitTime) {
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Try both the expected port and the default Flask port (5000)
      if (await tryConnect(flaskPort)) {
        serverRunning = true;
        log.info(`Flask server is running on port ${flaskPort}`);
        
        // Create or reload the window once server is running
        if (!mainWindow) {
          createWindow();
        } else {
          mainWindow.loadURL(`http://localhost:${flaskPort}`);
        }
        return true;
      }
      
      // If Flask ignored our PORT and used the default port (5000)
      if (flaskPort !== 5000 && await tryConnect(5000)) {
        flaskPort = 5000;
        serverRunning = true;
        log.info('Flask server is running on default port 5000');
        
        // Create or reload the window once server is running
        if (!mainWindow) {
          createWindow();
        } else {
          mainWindow.loadURL(`http://localhost:${flaskPort}`);
        }
        return true;
      }
    }
    
    // If we get here, the server didn't start in time
    const errorMessage = 'Flask server failed to start within the expected time';
    log.error(errorMessage);
    dialog.showErrorBox('Server Error', errorMessage);
    return false;
  } catch (error) {
    log.error('Failed to start Flask server:', error);
    dialog.showErrorBox('Server Error', `Failed to start the Flask server: ${error.message}`);
    return false;
  }
};

// Shut down Flask server
const stopFlaskServer = () => {
  if (flaskProcess) {
    log.info('Stopping Flask server...');
    
    if (process.platform === 'win32') {
      // On Windows we need to use taskkill to kill the process tree
      spawn('taskkill', ['/pid', flaskProcess.pid, '/f', '/t']);
    } else {
      // On Unix we can kill the process group
      flaskProcess.kill('SIGTERM');
    }
    
    flaskProcess = null;
    serverRunning = false;
  }
};

// Create the main application window
const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1024,
    height: 768,
    title: 'YouTube Auto Uploader',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Load the Flask app URL
  mainWindow.loadURL(`http://localhost:${flaskPort}`);

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Show dev tools in development mode
  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  // Handle window close event - minimize to tray instead of quitting
  mainWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow.hide();
      return false;
    }
  });

  // Cleanup on window closed
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
};

// Create the system tray icon and menu
const createTray = () => {
  // Create a default empty icon
  const emptyIcon = nativeImage.createEmpty();
  
  // Try to use the app icon if available, otherwise use empty icon
  tray = new Tray(emptyIcon);
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open YouTube Auto Uploader',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else if (serverRunning) {
          createWindow();
        } else {
          startFlaskServer().then(() => {
            createWindow();
          });
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        quitting = true;
        app.quit();
      }
    }
  ]);

  tray.setToolTip('YouTube Auto Uploader');
  tray.setContextMenu(contextMenu);
  
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    } else if (serverRunning) {
      createWindow();
    } else {
      startFlaskServer().then(() => {
        createWindow();
      });
    }
  });
};
// Add IPC handlers for preload.js
ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('get-settings', () => {
  return {
    autoLaunch: store.get('autoLaunch'),
    startMinimized: store.get('startMinimized')
  };
});

ipcMain.handle('save-settings', (_, settings) => {
  store.set('autoLaunch', settings.autoLaunch);
  store.set('startMinimized', settings.startMinimized);
  return { success: true };
});

ipcMain.handle('restart-app', () => {
  app.relaunch();
  app.exit(0);
});
// Application initialization
app.whenReady().then(async () => {
  try {
    log.info('App ready, initializing...');
    
    // Create system tray
    createTray();
    
    // Start the Flask server
    await startFlaskServer();
    
    log.info('Initialization complete');
  } catch (error) {
    log.error('Error during initialization:', error);
    dialog.showErrorBox(
      'Initialization Error',
      `Error starting the application: ${error.message}\nCheck that Python is installed and in your PATH.`
    );
  }
});

// Quit application when all windows are closed (except on macOS)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    // Don't quit, just hide the window
  }
});

// Handle activate event (macOS)
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// Clean up before quitting
app.on('before-quit', () => {
  log.info('Application is quitting...');
  quitting = true;
  stopFlaskServer();
});