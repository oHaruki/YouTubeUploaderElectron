@echo off
REM Build script for YouTube Auto Uploader on Windows
REM This script prepares the project for packaging with electron-builder

echo Building YouTube Auto Uploader...

REM Create python virtual environment and install dependencies
if not exist python (
    echo Creating Python virtual environment...
    python -m venv python
    call python\Scripts\activate.bat
    pip install -r flask_app\requirements.txt
    pip install pyinstaller
    deactivate
) else (
    echo Python environment already exists, updating dependencies...
    call python\Scripts\activate.bat
    pip install -r flask_app\requirements.txt
    deactivate
)

REM Create directory structure
if not exist flask_app mkdir flask_app
if not exist electron\icons mkdir electron\icons

REM Create dist directory if it doesn't exist
if not exist dist mkdir dist

REM Install Node.js dependencies
echo Installing Node.js dependencies...
call npm install

REM Build the application
echo Building Electron application...
call npm run build

echo Build completed!