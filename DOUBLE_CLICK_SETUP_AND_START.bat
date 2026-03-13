@echo off
setlocal
cd /d "%~dp0"

:: Check if Python is available before anything else
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  where python3 >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo ============================================================
    echo   Python is not installed on this computer.
    echo   Python is required to run The God Factory University.
    echo ============================================================
    echo.
    echo   This will now install Python for you automatically.
    echo.
    call install_python.bat
    if %ERRORLEVEL% NEQ 0 (
      echo [LAUNCH] Python installation failed or was cancelled.
      pause
      exit /b 1
    )
    :: Refresh PATH for this session after install
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
  )
)

if not exist ".venv\Scripts\python.exe" (
  call setup.bat
  if %ERRORLEVEL% NEQ 0 (
    echo [LAUNCH] Setup failed.
    pause
    exit /b 1
  )
)

call start.bat
