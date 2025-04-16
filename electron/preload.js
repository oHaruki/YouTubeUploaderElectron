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
  }
});