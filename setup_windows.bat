@echo off
REM Weekend Deal Hunter + ZR Bot — Windows setup script
REM Run this on a fresh Windows machine from any directory

echo ============================================
echo  Weekend Deal Hunter — Windows Setup
echo ============================================
echo.

REM ── 1. Check Python ──
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python not found. Install from https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install.
    exit /b 1
)
python --version

REM ── 2. Clone repos ──
echo [2/6] Cloning repositories...
if not exist "%USERPROFILE%\bots" mkdir "%USERPROFILE%\bots"
cd /d "%USERPROFILE%\bots"

if not exist "weekendmaxxing" (
    git clone https://github.com/bryanygan/weekendmaxxing.git
) else (
    echo   weekendmaxxing exists, pulling latest...
    cd weekendmaxxing && git pull && cd ..
)

if not exist "zrbot" (
    git clone https://github.com/bryanygan/zrbot.git
) else (
    echo   zrbot exists, pulling latest...
    cd zrbot && git pull && cd ..
)

REM ── 3. Install Python deps ──
echo [3/6] Installing Python dependencies...
pip install -r "%USERPROFILE%\bots\weekendmaxxing\requirements.txt"
pip install -r "%USERPROFILE%\bots\zrbot\requirements.txt"

REM ── 4. Playwright ──
echo [4/6] Installing Playwright Chromium...
playwright install chromium

REM ── 5. Ollama ──
echo [5/6] Checking Ollama...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   Ollama not found. Download and install from:
    echo   https://ollama.com/download/windows
    echo.
    echo   After installing, run these commands:
    echo     ollama pull llama3.1:8b
    echo     ollama serve
    echo.
    pause
) else (
    echo   Ollama found. Pulling model...
    ollama pull llama3.1:8b
)

REM ── 6. Configuration ──
echo [6/6] Setting up configuration...
if not exist "%USERPROFILE%\bots\weekendmaxxing\data" mkdir "%USERPROFILE%\bots\weekendmaxxing\data"

if not exist "%USERPROFILE%\bots\zrbot\.env" (
    copy "%USERPROFILE%\bots\zrbot\.env.example" "%USERPROFILE%\bots\zrbot\.env"
    echo.
    echo   !! IMPORTANT: Edit %USERPROFILE%\bots\zrbot\.env !!
    echo   Add your DISCORD_TOKEN and other settings.
    echo.
)

REM Add DEAL_HUNTER_PATH if not present
findstr /C:"DEAL_HUNTER_PATH" "%USERPROFILE%\bots\zrbot\.env" >nul 2>&1
if %errorlevel% neq 0 (
    echo. >> "%USERPROFILE%\bots\zrbot\.env"
    echo # Weekend Deal Hunter path >> "%USERPROFILE%\bots\zrbot\.env"
    echo DEAL_HUNTER_PATH=%USERPROFILE%\bots\weekendmaxxing >> "%USERPROFILE%\bots\zrbot\.env"
    echo   Added DEAL_HUNTER_PATH to .env
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo  1. Edit your bot token:
echo     notepad "%USERPROFILE%\bots\zrbot\.env"
echo.
echo  2. Start Ollama (if not running):
echo     ollama serve
echo.
echo  3. Start the bot (new terminal):
echo     cd "%USERPROFILE%\bots\zrbot"
echo     set DEAL_HUNTER_PATH=%USERPROFILE%\bots\weekendmaxxing
echo     python bot.py
echo.
echo  4. In Discord, type:
echo     /deals
echo.
pause
