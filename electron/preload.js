const { contextBridge, ipcRenderer } = require('electron');

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
  }
});