@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "APP_DIR=%PROJECT_DIR%app"
set "VENV_PY=%APP_DIR%\.venv\Scripts\python.exe"

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python Launcher 'py' was not found. Install Python 3.10 or newer.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    if exist "%APP_DIR%\.venv" (
        echo ERROR: app\.venv exists but is incomplete. Remove it and retry.
        pause
        exit /b 1
    )
    echo Creating isolated application environment in app\.venv...
    py -3 -m venv "%APP_DIR%\.venv"
    if errorlevel 1 (
        echo ERROR: Could not create the virtual environment.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -m pip install --disable-pip-version-check -r "%APP_DIR%\requirements.txt"
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)
"%VENV_PY%" "%APP_DIR%\app.py"
if errorlevel 1 pause
endlocal
