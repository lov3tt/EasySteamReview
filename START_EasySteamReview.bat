@echo off
setlocal EnableDelayedExpansion
title EasySteamReview Analytics Platform
color 0B
cls

echo.
echo  ============================================================
echo   EasySteamReview ^| Steam Review Analytics Platform v2.0
echo  ============================================================
echo.

:: ── FIND PYTHON ──────────────────────────────────────────────────────────────
set PYTHON_CMD=
where python >nul 2>&1 && set PYTHON_CMD=python
if "!PYTHON_CMD!"=="" (
    where python3 >nul 2>&1 && set PYTHON_CMD=python3
)
if "!PYTHON_CMD!"=="" (
    echo  [ERROR] Python not found in PATH.
    echo  Install Python 3.10+ from https://python.org
    echo  During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Check version is 3.8+
for /f "tokens=2 delims= " %%v in ('!PYTHON_CMD! --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python !PYVER! found

:: ── MOVE TO SCRIPT DIRECTORY ─────────────────────────────────────────────────
cd /d "%~dp0"
echo  [OK] Working directory: %~dp0

:: ── CREATE VIRTUAL ENVIRONMENT ───────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  [SETUP] Creating virtual environment...
    !PYTHON_CMD! -m venv venv
    if errorlevel 1 (
        echo  [ERROR] Could not create venv. Try running as Administrator.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] Virtual environment found.
)

:: ── ACTIVATE VENV ─────────────────────────────────────────────────────────────
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo  [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo  [OK] Virtual environment activated.

:: ── UPGRADE PIP ───────────────────────────────────────────────────────────────
echo  [SETUP] Upgrading pip...
python -m pip install --upgrade pip -q
echo  [OK] pip upgraded.

:: ── INSTALL PACKAGES ─────────────────────────────────────────────────────────
if exist "%~dp0requirements.txt" (
    echo  [SETUP] Installing packages from requirements.txt...
    pip install -r "%~dp0requirements.txt" -q
    if errorlevel 1 (
        echo  [WARN] Some installs may have issues. Retrying verbosely...
        pip install -r "%~dp0requirements.txt"
    )
) else (
    echo  [SETUP] Installing core packages directly...
    pip install fastapi "uvicorn[standard]" sqlalchemy httpx nltk textblob pandas jinja2 pydantic aiofiles -q
)
echo  [OK] Packages installed.

:: ── NLTK DATA ────────────────────────────────────────────────────────────────
echo  [SETUP] Downloading NLTK language data...
python -c "import nltk; [nltk.download(p, quiet=True) for p in ['vader_lexicon','punkt','stopwords','punkt_tab']]"
echo  [OK] NLTK data ready.

:: ── TEXTBLOB CORPORA ─────────────────────────────────────────────────────────
echo  [SETUP] Downloading TextBlob corpora...
python -m textblob.download_corpora >nul 2>&1
echo  [OK] TextBlob ready.

:: ── CHECK REQUIRED FILES ─────────────────────────────────────────────────────
if not exist "%~dp0main.py" (
    echo  [ERROR] main.py not found in %~dp0
    echo  Make sure all project files are in the same folder as this batch file.
    pause
    exit /b 1
)
if not exist "%~dp0templates\index.html" (
    echo  [ERROR] templates\index.html not found.
    pause
    exit /b 1
)
if not exist "%~dp0templates\dashboard.html" (
    echo  [ERROR] templates\dashboard.html not found.
    pause
    exit /b 1
)
echo  [OK] All project files found.

:: ── FIND FREE PORT ───────────────────────────────────────────────────────────
set PORT=8000
netstat -ano 2>nul | findstr ":8000 " >nul 2>&1
if not errorlevel 1 (
    echo  [INFO] Port 8000 in use, switching to 8001...
    set PORT=8001
    netstat -ano 2>nul | findstr ":8001 " >nul 2>&1
    if not errorlevel 1 (
        set PORT=8002
        echo  [INFO] Port 8001 also busy, using 8002...
    )
)
echo  [OK] Using port !PORT!

:: ── OPEN BROWSER AFTER DELAY ─────────────────────────────────────────────────
echo.
echo  [START] Launching server at http://localhost:!PORT!
echo  [INFO]  Browser will open automatically in ~3 seconds.
echo  [INFO]  Press CTRL+C in this window to stop the server.
echo.

start "" cmd /c "timeout /t 3 /nobreak >nul 2>&1 && start http://localhost:!PORT!"

:: ── LAUNCH FASTAPI ───────────────────────────────────────────────────────────
python -m uvicorn main:app --host 0.0.0.0 --port !PORT! --reload

:: ── ON EXIT ──────────────────────────────────────────────────────────────────
echo.
echo  Server stopped.
pause
endlocal
