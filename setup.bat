@echo off
setlocal enabledelayedexpansion
title Synapse AI - Setup

echo.
echo  ==========================================
echo    Synapse AI - One-Click Setup (Windows)
echo  ==========================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
echo [1/5] Checking for Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found.
    echo  Please install Python 3.8+ from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  Found: %PYVER%

:: ── Check Git ─────────────────────────────────────────────────────────────────
echo.
echo [2/5] Checking for Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Git not found.
    echo  Please install Git from https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('git --version 2^>^&1') do set GITVER=%%i
echo  Found: %GITVER%

:: ── Clone repo ────────────────────────────────────────────────────────────────
echo.
echo [3/5] Cloning Synapse AI repository...
if exist "synapse_ai" (
    echo  Folder "synapse_ai" already exists - skipping clone.
    echo  If you want a fresh install, delete the "synapse_ai" folder and re-run.
) else (
    git clone https://github.com/MrCryptographic/synapse_ai.git
    if errorlevel 1 (
        echo.
        echo  [ERROR] Failed to clone repository. Check your internet connection.
        echo.
        pause
        exit /b 1
    )
    echo  Cloned successfully.
)

:: ── Install dependencies ──────────────────────────────────────────────────────
echo.
echo [4/5] Installing Python dependencies...
cd synapse_ai
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to install dependencies.
    echo  Try running: pip install -r requirements.txt  manually.
    echo.
    pause
    exit /b 1
)
echo  Dependencies installed.

:: ── Create launch script ──────────────────────────────────────────────────────
echo.
echo [5/5] Creating launch shortcut...
cd ..
(
    echo @echo off
    echo title Synapse AI
    echo cd /d "%%~dp0synapse_ai"
    echo echo.
    echo echo  Starting Synapse AI...
    echo echo  Open your browser and go to: http://localhost:6767
    echo echo  Create an individual account on first visit.
    echo echo  Press Ctrl+C to stop the server.
    echo echo.
    echo python app.py
    echo pause
) > launch_synapse.bat
echo  Created launch_synapse.bat

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ==========================================
echo    Setup complete!
echo  ==========================================
echo.
echo  BEFORE LAUNCHING, make sure LM Studio is:
echo    1. Open and running the Local Server
echo    2. Host is set to localhost if LM Studio runs on this computer
echo    3. Port is 1234 (default)
echo.
echo  Then double-click "launch_synapse.bat" to start.
echo  Network access is disabled by default; see README.md before enabling it.
echo.
pause