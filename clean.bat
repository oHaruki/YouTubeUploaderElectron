@echo off
echo Cleaning up build environment...

REM Kill any running Electron processes
echo Stopping any running Electron processes...
taskkill /F /IM electron.exe /T 2>nul
taskkill /F /IM YouTube* /T 2>nul

REM Wait a moment for processes to fully terminate
timeout /t 2 /nobreak >nul

REM Remove dist directory
echo Removing dist directory...
if exist "dist" (
    rmdir /S /Q "dist"
    if exist "dist" (
        echo WARNING: Could not remove dist directory. It may be locked by another process.
    ) else (
        echo Successfully removed dist directory.
    )
) else (
    echo Dist directory doesn't exist. Nothing to clean.
)

REM Remove node_modules/.cache directory
echo Removing build cache...
if exist "node_modules\.cache" (
    rmdir /S /Q "node_modules\.cache"
    echo Removed build cache.
)

echo Cleanup complete. You can now try running "npm run build" again.