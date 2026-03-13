@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Python Auto-Installer for The God Factory University
echo ============================================================
echo.

:: Check if Python is already installed
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python --version 2>nul
    echo [INFO] Python is already installed.
    echo [INFO] No action needed. You can close this window.
    pause
    exit /b 0
)

where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python3 --version 2>nul
    echo [INFO] Python is already installed.
    echo [INFO] No action needed. You can close this window.
    pause
    exit /b 0
)

echo [INFO] Python is not installed on this computer.
echo [INFO] This script will download and install Python 3.11 for you.
echo.
echo   - Download size: ~25 MB
echo   - Install size:  ~100 MB
echo   - Python will be added to your PATH automatically
echo.

set /p CONFIRM="Press Y to install Python, or N to cancel: "
if /i not "%CONFIRM%"=="Y" (
    echo [INFO] Installation cancelled.
    pause
    exit /b 1
)

echo.
echo [DOWNLOAD] Downloading Python 3.11.9 installer...

set "INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
set "URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"

:: Try PowerShell first (available on all modern Windows)
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%URL%' -OutFile '%INSTALLER%'" 2>nul
if exist "%INSTALLER%" goto :install

:: Fallback to curl (built into Windows 10+)
echo [DOWNLOAD] Trying alternative download method...
curl -L -o "%INSTALLER%" "%URL%" 2>nul
if exist "%INSTALLER%" goto :install

:: Fallback to certutil
echo [DOWNLOAD] Trying another download method...
certutil -urlcache -split -f "%URL%" "%INSTALLER%" >nul 2>nul
if exist "%INSTALLER%" goto :install

echo [ERROR] Failed to download Python installer.
echo [ERROR] Please download Python manually from:
echo         https://www.python.org/downloads/
echo.
echo         IMPORTANT: Check "Add Python to PATH" during installation.
pause
exit /b 1

:install
echo [DOWNLOAD] Download complete.
echo.
echo [INSTALL] Installing Python 3.11.9...
echo [INSTALL] This may take a minute. A progress window may appear.
echo.

:: Install Python with PATH enabled, per-user (no admin required for per-user)
"%INSTALLER%" /passive PrependPath=1 Include_test=0 Include_launcher=1

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INSTALL] The installer exited with code %ERRORLEVEL%.
    echo [INSTALL] If it asked for admin permissions, try right-clicking
    echo           this script and selecting "Run as administrator".
    echo.
    echo [INSTALL] Or install manually from: https://www.python.org/downloads/
    echo           IMPORTANT: Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Clean up installer
del "%INSTALLER%" 2>nul

echo.
echo [INSTALL] Python installation complete!
echo.

:: Verify -- need to refresh PATH in this session
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

python --version 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Python is ready to use.
) else (
    echo [NOTE] Python installed but PATH may not update until you open a new terminal.
    echo [NOTE] Close this window and double-click DOUBLE_CLICK_SETUP_AND_START.bat
)

echo.
echo ============================================================
echo   Python is installed! You can now run the university:
echo   Double-click DOUBLE_CLICK_SETUP_AND_START.bat
echo ============================================================
echo.
pause
exit /b 0
