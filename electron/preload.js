const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');
const path = require('path');
const app = require('electron').remote?.app;

// Try to write the version to a file that Flask can read
function syncVersionToFile() {
  try {
    // Get the version directly from Electron
    const version = app ? app.getVersion() : require('../package.json').version;
    
    // Create a version.json file in the app resources directory where Flask can find it
    const resourcesPath = process.resourcesPath || path.join(__dirname, '..');
    const versionPath = path.join(resourcesPath, 'flask_app', 'version.json');
    
    // Read existing file if it exists
    let versionData = {
      version: version,
      build_date: new Date().toISOString().split('T')[0] + ' ' + new Date().toTimeString().split(' ')[0],
      auto_update: true
    };
    
    try {
      if (fs.existsSync(versionPath)) {
        const existingData = JSON.parse(fs.readFileSync(versionPath, 'utf8'));
        // Keep auto_update setting but update version
        versionData.auto_update = existingData.auto_update;
      }
    } catch (e) {
      console.error('Error reading existing version file:', e);
    }
    
    // Write the updated version file
    fs.writeFileSync(versionPath, JSON.stringify(versionData, null, 4));
    console.log(`Synchronized version file at ${versionPath} with version ${version}`);
    
    return true;
  } catch (e) {
    console.error('Error syncing version to file:', e);
    return false;
  }
}

// Try to sync version file when preload runs
syncVersionToFile();

// Expose safe APIs to the renderer process
contextBridge.exposeInMainWorld('electron', {
  // App info
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // Settings
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  
  // App control
  restartApp: () => ipcRenderer.invoke('restart-app'),
  
  // Event listeners
  onStartMonitoring: (callback) => {
    ipcRenderer.on('start-monitoring', () => callback());
    return () => ipcRenderer.removeListener('start-monitoring', callback);
  },
  
  onStopMonitoring: (callback) => {
    ipcRenderer.on('stop-monitoring', () => callback());
    return () => ipcRenderer.removeListener('stop-monitoring', callback);
  },
  
  // Auto-updater functions
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  
  // Auto-updater events
  onUpdateAvailable: (callback) => {
    ipcRenderer.on('update-available', (_, info) => callback(info));
    return () => ipcRenderer.removeListener('update-available', callback);
  },
  
  onUpdateNotAvailable: (callback) => {
    ipcRenderer.on('update-not-available', () => callback());
    return () => ipcRenderer.removeListener('update-not-available', callback);
  },
  
  onUpdateError: (callback) => {
    ipcRenderer.on('update-error', (_, message) => callback(message));
    return () => ipcRenderer.removeListener('update-error', callback);
  },
  
  onUpdateProgress: (callback) => {
    ipcRenderer.on('update-progress', (_, progress) => callback(progress));
    return () => ipcRenderer.removeListener('update-progress', callback);
  },
  
  onUpdateDownloaded: (callback) => {
    ipcRenderer.on('update-downloaded', (_, info) => callback(info));
    return () => ipcRenderer.removeListener('update-downloaded', callback);
  },
  
  // Version sync for the Flask backend
  syncVersionFile: () => syncVersionToFile(),
  
  // For the update process
  exitForUpdate: () => ipcRenderer.invoke('exit-for-update')
});