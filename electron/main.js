const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, shell, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const portfinder = require('portfinder');
const isDev = process.env.NODE_ENV === 'development';
const Store = require('electron-store');
const log = require('electron-log');

// Remove application menu
Menu.setApplicationMenu(null);

// Configure logger
log.transports.file.level = 'info';
log.info('Application starting...');

// Create a version.json file in the Flask app directory
function syncVersionToFlask() {
  try {
    // Get app version from package.json
    const version = app.getVersion();
    log.info(`Current application version: ${version}`);
    
    // Create the file path
    const versionPath = path.join(
      app.isPackaged ? process.resourcesPath : app.getAppPath(), 
      'flask_app', 
      'version.json'
    );
    
    // Read existing file if it exists
    let versionData = {
      version: version,
      build_date: new Date().toISOString().split('T')[0] + ' ' + new Date().toTimeString().split(' ')[0],
      auto_update: false
    };
    
    try {
      if (fs.existsSync(versionPath)) {
        const existingData = JSON.parse(fs.readFileSync(versionPath, 'utf8'));
        // Keep auto_update setting but update version
        versionData.auto_update = existingData.auto_update;
      }
    } catch (e) {
      log.error('Error reading existing version file:', e);
    }
    
    // Write the updated version file
    fs.writeFileSync(versionPath, JSON.stringify(versionData, null, 4));
    log.info(`Synchronized version file at ${versionPath} with version ${version}`);
    
    // Also create a root version.json for the auto_updater.py to find
    const rootVersionPath = path.join(
      app.isPackaged ? process.resourcesPath : app.getAppPath(),
      'version.json'
    );
    
    try {
      fs.writeFileSync(rootVersionPath, JSON.stringify(versionData, null, 4));
      log.info(`Created root version file at ${rootVersionPath}`);
    } catch (e) {
      log.error('Error creating root version file:', e);
    }
    
    return true;
  } catch (e) {
    log.error('Error syncing version to file:', e);
    return false;
  }
}

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

// Chrome's blocked ports
const BLOCKED_PORTS = [
  1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 77, 79, 87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 139, 143, 179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532, 540, 556, 563, 587, 601, 636, 993, 995, 2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6697, 10080
];

// Extract port from Flask output
const extractPortFromOutput = (output) => {
  const match = output.match(/Running on http:\/\/127\.0\.0\.1:(\d+)/);
  if (match && match[1]) {
    return parseInt(match[1]);
  }
  return null;
};

// Check if Python is installed and get the correct executable path
const checkPythonPath = () => {
  const pythonCommands = [
    process.platform === 'win32' ? 'python' : 'python3',
    process.platform === 'win32' ? 'py' : 'python',
    'python3',
    'python'
  ];

  for (const cmd of pythonCommands) {
    try {
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
    }
  }
  
  return null;
};

// More robust waiting for Flask server
const waitForFlaskServer = async (port, maxAttempts = 30, delayBetweenAttempts = 1000) => {
  log.info(`Waiting for Flask server to start on port ${port}...`);
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      log.info(`Connection attempt ${attempt}/${maxAttempts} to Flask on port ${port}`);
      
      const connected = await new Promise(resolve => {
        const req = http.get(`http://127.0.0.1:${port}/`, { timeout: 1000 }, (res) => {
          log.info(`Connection successful! Status: ${res.statusCode}`);
          req.destroy();
          resolve(res.statusCode < 400);
        });
        
        req.on('error', (err) => {
          log.info(`Connection attempt ${attempt} failed: ${err.message}`);
          resolve(false);
        });
        
        req.on('timeout', () => {
          log.info(`Connection attempt ${attempt} timed out`);
          req.destroy();
          resolve(false);
        });
      });
      
      if (connected) {
        return true;
      }
    } catch (error) {
      log.info(`Error in connection attempt ${attempt}: ${error}`);
    }
    
    // Only delay if we're going to try again
    if (attempt < maxAttempts) {
      log.info(`Waiting ${delayBetweenAttempts}ms before next attempt...`);
      await new Promise(resolve => setTimeout(resolve, delayBetweenAttempts));
    }
  }
  
  return false;
};

// Start Flask server with improved error handling and connection
const startFlaskServer = async () => {
  if (serverRunning) {
    log.info('Flask server is already running');
    return true;
  }

  try {
    // Try to use a fixed port first, with fallbacks if needed
    const preferredPorts = [5000, 5001, 8000, 8080, 8081];
    let portFound = false;
    
    // Try each preferred port
    for (const port of preferredPorts) {
      if (BLOCKED_PORTS.includes(port)) {
        log.info(`Port ${port} is in blocked list, skipping`);
        continue;
      }
      
      try {
        // Check if port is available
        const isAvailable = await new Promise(resolve => {
          const server = require('net').createServer();
          server.once('error', () => {
            resolve(false);
          });
          server.once('listening', () => {
            server.close();
            resolve(true);
          });
          server.listen(port);
        });
        
        if (isAvailable) {
          flaskPort = port;
          portFound = true;
          log.info(`Found available port: ${flaskPort}`);
          break;
        } else {
          log.info(`Port ${port} is not available, trying next port`);
        }
      } catch (error) {
        log.info(`Error checking port ${port}: ${error.message}`);
      }
    }
    
    // If no preferred port works, use portfinder as a last resort
    if (!portFound) {
      log.info(`No preferred ports available, using portfinder`);
      flaskPort = await portfinder.getPortPromise({
        port: 8000,
        stopPort: 9000,
        filter: (port) => !BLOCKED_PORTS.includes(port)
      });
    }
    
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
    const scriptPath = path.join(app.isPackaged ? process.resourcesPath : app.getAppPath(), 'flask_app', 'app.py');
    if (!fs.existsSync(scriptPath)) {
      const errorMessage = `Flask app script not found at ${scriptPath}`;
      log.error(errorMessage);
      dialog.showErrorBox('Flask App Not Found', errorMessage);
      return false;
    }
    log.info(`Using script path: ${scriptPath}`);
    
    // Environment variables for Flask
    const env = { 
      ...process.env, 
      PORT: flaskPort.toString(), 
      ELECTRON_APP: 'true',
      PYTHONUNBUFFERED: '1',
      FLASK_DEBUG: '0'  // Explicitly disable Flask debug mode
    };
    
    // Start Flask as a child process with better error handling
    log.info(`Spawning Flask process with command: ${pythonCommand} ${scriptPath}`);
    log.info(`Working directory: ${app.isPackaged ? process.resourcesPath : app.getAppPath()}`);
    log.info(`Environment PORT: ${env.PORT}`);
    
    flaskProcess = spawn(pythonCommand, [scriptPath], { 
      env,
      shell: true,
      stdio: 'pipe',
      cwd: app.isPackaged ? process.resourcesPath : app.getAppPath()
    });
    
    // Add event listeners for process output and errors
    flaskProcess.stdout.on('data', (data) => {
      const output = data.toString();
      log.info(`Flask stdout: ${output}`);
      
      // Look for successful startup message
      if (output.includes('Running on http://')) {
        const port = extractPortFromOutput(output);
        if (port) {
          log.info(`Detected Flask running on port ${port} from stdout`);
          flaskPort = port;
        }
      }
    });
    
    flaskProcess.stderr.on('data', (data) => {
      const output = data.toString();
      log.error(`Flask stderr: ${output}`);
      
      // Still check stderr for port info as some Flask info goes to stderr
      if (output.includes('Running on http://')) {
        const port = extractPortFromOutput(output);
        if (port) {
          log.info(`Detected Flask running on port ${port} from stderr`);
          flaskPort = port;
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
      
      if (!quitting && code !== 0) {
        log.info('Flask server crashed, restarting...');
        setTimeout(startFlaskServer, 2000);  // Increased delay before restart
      }
    });

    // Wait for Flask server to be available
    log.info(`Waiting for Flask server to become available...`);
    const isServerRunning = await waitForFlaskServer(flaskPort);
    
    if (isServerRunning) {
      serverRunning = true;
      log.info(`✓ Successfully connected to Flask on port ${flaskPort}`);
      
      if (!mainWindow) {
        createWindow();
      } else {
        mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);
      }
      return true;
    } else {
      // Still not running after all attempts - show a more helpful error message
      log.error(`Failed to connect to Flask server after multiple attempts`);
      
      const errorMessage = 
        'Could not connect to the Flask server. This could be due to:\n\n' +
        '1. Python or required packages not properly installed\n' +
        '2. Port conflicts\n' +
        '3. Firewall blocking the connection\n\n' +
        'Please check the logs for more details.';
      
      dialog.showErrorBox('Server Connection Error', errorMessage);
      return false;
    }
  } catch (error) {
    log.error('Failed to start Flask server:', error);
    dialog.showErrorBox('Server Error', `Failed to start the Flask server: ${error.message}`);
    return false;
  }
};

// Try to connect to a server on the given port
const tryConnect = async (port) => {
  return new Promise(resolve => {
    log.info(`Attempting to connect to http://127.0.0.1:${port}/`);
    const req = http.get(`http://127.0.0.1:${port}/`, {timeout: 1000}, (res) => {
      req.destroy();
      log.info(`Connection to port ${port} successful (status: ${res.statusCode})`);
      resolve(res.statusCode < 400);
    });
    
    req.on('error', (err) => {
      log.info(`Connection to port ${port} failed: ${err.message}`);
      resolve(false);
    });
    
    req.on('timeout', () => {
      log.info(`Connection to port ${port} timed out`);
      req.destroy();
      resolve(false);
    });
  });
};

// Shut down Flask server
const stopFlaskServer = () => {
  if (flaskProcess) {
    log.info('Stopping Flask server...');
    
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', flaskProcess.pid, '/f', '/t']);
    } else {
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
    autoHideMenuBar: true,
    menuBarVisible: false,
    icon: path.join(__dirname, 'icons', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Set menu to null to completely remove it
  mainWindow.setMenu(null);

  // Load the Flask app URL
  mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);

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
  const iconPath = path.join(__dirname, 'icons', process.platform === 'win32' ? 'icon.ico' : 'icon.png');
  let trayIcon;
  
  try {
    if (fs.existsSync(iconPath)) {
      trayIcon = nativeImage.createFromPath(iconPath);
    } else {
      trayIcon = nativeImage.createEmpty();
    }
  } catch (error) {
    log.error('Error loading tray icon:', error);
    trayIcon = nativeImage.createEmpty();
  }
  
  tray = new Tray(trayIcon);
  
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
      label: 'Visit GitHub for Updates',
      click: () => {
        shell.openExternal('https://github.com/oHaruki/YouTubeUploaderElectron/releases');
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
    const { dirs, pathsFile } = initializeAppDirectories();
    
    // Set working directory to resources path when packaged
    if (app.isPackaged) {
      try {
        process.chdir(process.resourcesPath);
        log.info(`Changed working directory to: ${process.resourcesPath}`);
      } catch (error) {
        log.error('Failed to change working directory:', error);
      }
    }
    
    // Sync version.json for Flask
    syncVersionToFlask();
    
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

// Get application directories for different environments
function getAppDirectories() {
  const appDirs = {
    // Main application directory
    appDir: app.isPackaged ? process.resourcesPath : app.getAppPath(),
    
    // Electron-specific directories
    userData: app.getPath('userData'),
    appData: app.getPath('appData'),
    logs: app.getPath('logs'),
    temp: app.getPath('temp'),
    
    // App-specific directories
    config: path.join(app.getPath('userData'), 'config'),
    data: path.join(app.getPath('userData'), 'data')
  };
  
  // Create directories that don't exist
  Object.values(appDirs).forEach(dir => {
    if (!fs.existsSync(dir)) {
      try {
        fs.mkdirSync(dir, { recursive: true });
        log.info(`Created directory: ${dir}`);
      } catch (error) {
        log.error(`Failed to create directory ${dir}: ${error}`);
      }
    }
  });
  
  // Log all directories for debugging
  log.info('Application directories:');
  Object.entries(appDirs).forEach(([key, value]) => {
    log.info(`  ${key}: ${value}`);
  });
  
  return appDirs;
}

// Save application paths to a file that update scripts can read
function saveAppPaths() {
  try {
    const dirs = getAppDirectories();
    const appPathsFile = path.join(dirs.temp, 'app_paths.json');
    
    const pathData = {
      executable: app.getPath('exe'),
      appRoot: app.isPackaged ? path.dirname(app.getPath('exe')) : app.getAppPath(),
      resourcesPath: process.resourcesPath,
      userData: dirs.userData,
      appData: dirs.appData,
      isPackaged: app.isPackaged
    };
    
    fs.writeFileSync(appPathsFile, JSON.stringify(pathData, null, 2));
    log.info(`Saved application paths to ${appPathsFile}`);
    
    return appPathsFile;
  } catch (error) {
    log.error(`Error saving app paths: ${error}`);
    return null;
  }
}

// Call this during app initialization
function initializeAppDirectories() {
  const dirs = getAppDirectories();
  const pathsFile = saveAppPaths();
  
  // Create a version file in the userData directory for easier syncing
  try {
    const versionFile = path.join(dirs.userData, 'version.json');
    const versionData = {
      version: app.getVersion(),
      buildDate: new Date().toISOString(),
      autoUpdate: false
    };
    
    fs.writeFileSync(versionFile, JSON.stringify(versionData, null, 2));
    log.info(`Saved version information to ${versionFile}`);
  } catch (error) {
    log.error(`Error saving version file: ${error}`);
  }
  
  return { dirs, pathsFile };
}


// Function to find the bundled Python executable
const findBundledPython = () => {
  // For packaged app, look in the resources directory
  if (app.isPackaged) {
    const pythonExePath = path.join(
      process.resourcesPath,
      'python',
      process.platform === 'win32' ? 'python.exe' : 'bin/python3'
    );
    
    if (fs.existsSync(pythonExePath)) {
      log.info(`Found bundled Python at: ${pythonExePath}`);
      return pythonExePath;
    }
    
    // Also check resources/app.asar.unpacked/python if it exists
    const unpackedPythonPath = path.join(
      process.resourcesPath,
      'app.asar.unpacked',
      'python',
      process.platform === 'win32' ? 'python.exe' : 'bin/python3'
    );
    
    if (fs.existsSync(unpackedPythonPath)) {
      log.info(`Found bundled Python in unpacked resources: ${unpackedPythonPath}`);
      return unpackedPythonPath;
    }
  }
  
  return null;
};

// Function to create a file-based ready signal
const setupFileBasedReadySignal = () => {
  const signalPath = path.join(app.getPath('temp'), 'youtube-uploader-ready.txt');
  
  // Delete any existing signal file
  if (fs.existsSync(signalPath)) {
    try {
      fs.unlinkSync(signalPath);
      log.info(`Deleted existing ready signal at ${signalPath}`);
    } catch (err) {
      log.error(`Failed to delete existing ready signal: ${err}`);
    }
  }
  
  return signalPath;
};

// Function to wait for the file-based ready signal
const waitForFileReadySignal = async (signalPath, maxWaitTime = 30000) => {
  const startTime = Date.now();
  log.info(`Waiting for ready signal file at ${signalPath}`);
  
  while (Date.now() - startTime < maxWaitTime) {
    if (fs.existsSync(signalPath)) {
      try {
        const content = fs.readFileSync(signalPath, 'utf8');
        const data = JSON.parse(content);
        log.info(`Ready signal found with data: ${JSON.stringify(data)}`);
        return data;
      } catch (err) {
        log.error(`Error reading ready signal: ${err}`);
      }
    }
    
    // Wait a short time before checking again
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  log.error(`Timed out waiting for ready signal after ${maxWaitTime}ms`);
  return null;
};