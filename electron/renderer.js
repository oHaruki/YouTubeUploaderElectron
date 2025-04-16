// This script is injected into the Flask web interface to enable communication with Electron

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only run this script if we're in Electron (check if window.electron exists)
    if (window.electron) {
      console.log('Running in Electron environment');
      setupElectronIntegration();
    } else {
      console.log('Running in browser environment');
    }
  });
  
  // Set up Electron integration with the Flask UI
  function setupElectronIntegration() {
    // Add Electron version to the interface
    addElectronVersionInfo();
    
    // Set up desktop settings
    setupDesktopSettings();
    
    // Add listeners for commands from the main process
    setupCommandListeners();
    
    // Modify certain UI elements for desktop
    enhanceUIForDesktop();
  }
  
  // Add Electron version information to the About tab
  function addElectronVersionInfo() {
    window.electron.getAppVersion().then(version => {
      // Add the Electron version info to the About tab
      const aboutTab = document.getElementById('about-tab-pane');
      if (aboutTab) {
        const versionInfo = document.createElement('div');
        versionInfo.className = 'mt-3 text-center text-muted small';
        versionInfo.innerHTML = `Desktop App v${version} | Powered by Electron`;
        
        // Find a good place to append this information
        const lastCard = aboutTab.querySelector('.card:last-child');
        if (lastCard) {
          lastCard.appendChild(versionInfo);
        } else {
          aboutTab.appendChild(versionInfo);
        }
      }
    });
  }
  
  // Set up desktop-specific settings in the Settings tab
  function setupDesktopSettings() {
    // Find a good place to inject desktop settings
    const settingsTab = document.getElementById('settings-tab-pane');
    if (!settingsTab) return;
    
    // Find the last settings section
    const lastSection = settingsTab.querySelector('.settings-section:last-child');
    if (!lastSection) return;
    
    // Create desktop settings section
    const desktopSettings = document.createElement('div');
    desktopSettings.className = 'settings-section';
    desktopSettings.innerHTML = `
      <h5 class="mb-3">Desktop App Settings</h5>
      <div class="form-check form-switch mb-3">
        <input class="form-check-input" type="checkbox" id="autoLaunchSetting">
        <label class="form-check-label" for="autoLaunchSetting">Start app at login</label>
      </div>
      <div class="form-check form-switch mb-3">
        <input class="form-check-input" type="checkbox" id="startMinimizedSetting">
        <label class="form-check-label" for="startMinimizedSetting">Start minimized in system tray</label>
      </div>
    `;
    
    // Insert before the Save Settings button
    const saveButton = settingsTab.querySelector('#saveSettingsBtn').parentNode;
    saveButton.parentNode.insertBefore(desktopSettings, saveButton);
    
    // Load current settings
    window.electron.getSettings().then(settings => {
      document.getElementById('autoLaunchSetting').checked = settings.autoLaunch;
      document.getElementById('startMinimizedSetting').checked = settings.startMinimized;
    });
    
    // Save desktop settings when main settings are saved
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    const originalClickHandler = saveSettingsBtn.onclick;
    
    saveSettingsBtn.onclick = function(e) {
      // First call the original handler
      if (originalClickHandler) {
        originalClickHandler.call(this, e);
      }
      
      // Then save desktop settings
      const desktopSettings = {
        autoLaunch: document.getElementById('autoLaunchSetting').checked,
        startMinimized: document.getElementById('startMinimizedSetting').checked
      };
      
      window.electron.saveSettings(desktopSettings)
        .then(() => console.log('Desktop settings saved'))
        .catch(err => console.error('Failed to save desktop settings:', err));
    };
  }
  
  // Set up listeners for commands from the main process
  function setupCommandListeners() {
    // Listener for "start monitoring" command from main process
    window.electron.onStartMonitoring(() => {
      console.log('Received start monitoring command from main process');
      const startMonitoringBtn = document.getElementById('startMonitoringBtn');
      if (startMonitoringBtn && !startMonitoringBtn.disabled) {
        startMonitoringBtn.click();
      }
    });
    
    // Listener for "stop monitoring" command from main process
    window.electron.onStopMonitoring(() => {
      console.log('Received stop monitoring command from main process');
      const stopMonitoringBtn = document.getElementById('stopMonitoringBtn');
      if (stopMonitoringBtn && !stopMonitoringBtn.disabled) {
        stopMonitoringBtn.click();
      }
    });
  }
  
  // Enhance UI elements for the desktop experience
  function enhanceUIForDesktop() {
    // Modify the restart application behavior to use Electron's restart
    const restartAppFunctions = document.querySelectorAll('*[onclick*="restartApplication"]');
    restartAppFunctions.forEach(element => {
      const originalOnClick = element.onclick;
      element.onclick = function(e) {
        e.preventDefault();
        window.electron.restartApp();
      };
    });
    
    // Add desktop app indicator to navbar
    const navbar = document.querySelector('.navbar-brand');
    if (navbar) {
      navbar.innerHTML += ' <span class="badge bg-secondary">Desktop</span>';
    }
    
    // Add an About Desktop App section to the About tab
    const aboutTab = document.getElementById('about-tab-pane');
    if (aboutTab) {
      const desktopInfoCard = document.createElement('div');
      desktopInfoCard.className = 'card mt-4 fade-in';
      desktopInfoCard.innerHTML = `
        <div class="card-header">
          <i class="bi bi-pc-display me-2"></i>Desktop App Features
        </div>
        <div class="card-body">
          <ul>
            <li>Starts automatically with your system (optional)</li>
            <li>Runs in the background from the system tray</li>
            <li>Quick access to monitoring controls from system tray</li>
            <li>Native desktop notifications</li>
          </ul>
          <div class="alert alert-info">
            <i class="bi bi-info-circle me-2"></i>
            <strong>Tip:</strong> You can access the app from the system tray icon even when the window is closed.
          </div>
        </div>
      `;
      
      // Add it as the second card in the About tab
      const firstCard = aboutTab.querySelector('.card');
      if (firstCard) {
        firstCard.parentNode.insertBefore(desktopInfoCard, firstCard.nextSibling);
      } else {
        aboutTab.appendChild(desktopInfoCard);
      }
    }
  }