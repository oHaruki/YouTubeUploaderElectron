const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, shell, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const portfinder = require('portfinder');
const isDev = process.env.NODE_ENV === 'development';
const Store = require('electron-store');
const log = require('electron-log');
const { autoUpdater } = require('electron-updater');

// Remove application menu
Menu.setApplicationMenu(null);

// Configure logger
log.transports.file.level = 'info';
log.info('Application starting...');

// Configure auto-updater
autoUpdater.logger = log;
autoUpdater.autoDownload = false;

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
      PYTHONUNBUFFERED: '1' // Ensure Python output is not buffered
    };
    
    // Start Flask as a child process
    flaskProcess = spawn(pythonCommand, [scriptPath], { 
      env,
      shell: true,
      stdio: 'pipe',
      cwd: app.isPackaged ? process.resourcesPath : app.getAppPath() // Set working directory
    });
    
    flaskProcess.stdout.on('data', (data) => {
      const output = data.toString();
      log.info(`Flask stdout: ${output}`);
      
      const port = extractPortFromOutput(output);
      if (port) {
        log.info(`Detected Flask running on port ${port} from stdout`);
        flaskPort = port;
        tryConnect(flaskPort).then(result => {
          if (result) {
            serverRunning = true;
            log.info(`Successfully connected to Flask on port ${flaskPort}`);
            if (!mainWindow) {
              createWindow();
            } else {
              mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);
            }
          }
        });
      }
    });
    
    flaskProcess.stderr.on('data', (data) => {
      const output = data.toString();
      log.error(`Flask stderr: ${output}`);
      
      const port = extractPortFromOutput(output);
      if (port) {
        log.info(`Detected Flask running on port ${port} from stderr`);
        flaskPort = port;
        tryConnect(flaskPort).then(result => {
          if (result) {
            serverRunning = true;
            log.info(`Successfully connected to Flask on port ${flaskPort}`);
            if (!mainWindow) {
              createWindow();
            } else {
              mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);
            }
          }
        });
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
        setTimeout(startFlaskServer, 1000);
      }
    });

    // Check if Flask server starts successfully
    const maxWaitTime = 30000;
    const startTime = Date.now();
    
    // Try to connect to the server with multiple attempts
    let attempts = 0;
    const portsToTry = [flaskPort, 5000, 5001, 5002, 5003, 5004, 5005];
    
    while (Date.now() - startTime < maxWaitTime) {
      attempts++;
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Try the expected port first
      log.info(`Connection attempt ${attempts} to Flask on port ${flaskPort}...`);
      if (await tryConnect(flaskPort)) {
        serverRunning = true;
        log.info(`✓ Successfully connected to Flask on port ${flaskPort}`);
        
        if (!mainWindow) {
          createWindow();
        } else {
          mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);
        }
        return true;
      }
      
      // Try other possible ports
      for (const altPort of portsToTry) {
        if (altPort !== flaskPort) {
          log.info(`Trying alternative port ${altPort}...`);
          if (await tryConnect(altPort)) {
            flaskPort = altPort;
            serverRunning = true;
            log.info(`✓ Found Flask server on alternative port ${altPort}`);
            
            if (!mainWindow) {
              createWindow();
            } else {
              mainWindow.loadURL(`http://127.0.0.1:${flaskPort}`);
            }
            return true;
          }
        }
      }
    }
    
    const errorMessage = 'Flask server might be running but not responding. Check for errors in the server logs.';
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
      spawn('taskkill', ['/pid', flaskProcess.pid, '/f', '/t']);
    } else {
      flaskProcess.kill('SIGTERM');
    }
    
    flaskProcess = null;
    serverRunning = false;
  }
};

// Set up auto-updater
function setupAutoUpdater() {
  autoUpdater.on('checking-for-update', () => {
    log.info('Checking for updates...');
  });

  autoUpdater.on('update-available', (info) => {
    log.info('Update available:', info);
    if (mainWindow) {
      mainWindow.webContents.send('update-available', info);
    }
  });

  autoUpdater.on('update-not-available', (info) => {
    log.info('Update not available:', info);
    if (mainWindow) {
      mainWindow.webContents.send('update-not-available');
    }
  });

  autoUpdater.on('error', (err) => {
    log.error('Error in auto-updater:', err);
    if (mainWindow) {
      mainWindow.webContents.send('update-error', err.message);
    }
  });

  autoUpdater.on('download-progress', (progressObj) => {
    log.info(`Download progress: ${progressObj.percent}%`);
    if (mainWindow) {
      mainWindow.webContents.send('update-progress', progressObj);
    }
  });

  autoUpdater.on('update-downloaded', (info) => {
    log.info('Update downloaded:', info);
    if (mainWindow) {
      mainWindow.webContents.send('update-downloaded', info);
    }
  });

  // Check for updates once an hour
  setInterval(() => {
    autoUpdater.checkForUpdates().catch(err => {
      log.error('Error checking for updates:', err);
    });
  }, 60 * 60 * 1000);
}

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
      label: 'Check for Updates',
      click: () => {
        autoUpdater.checkForUpdates().catch(err => {
          log.error('Error checking for updates:', err);
        });
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

// Add update-related IPC handlers
ipcMain.handle('check-for-updates', () => {
  return autoUpdater.checkForUpdates();
});

ipcMain.handle('download-update', () => {
  autoUpdater.downloadUpdate();
  return true;
});

ipcMain.handle('install-update', () => {
  autoUpdater.quitAndInstall(false, true);
  return true;
});

// Application initialization
app.whenReady().then(async () => {
  try {
    log.info('App ready, initializing...');
    
    // Set working directory to resources path when packaged
    if (app.isPackaged) {
      try {
        process.chdir(process.resourcesPath);
        log.info(`Changed working directory to: ${process.resourcesPath}`);
      } catch (error) {
        log.error('Failed to change working directory:', error);
      }
    }
    
    // Create system tray
    createTray();
    
    // Set up auto-updater
    setupAutoUpdater();
    
    // Start the Flask server
    await startFlaskServer();
    
    // Check for updates after initialization
    autoUpdater.checkForUpdates().catch(err => {
      log.error('Error checking for updates on startup:', err);
    });
    
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