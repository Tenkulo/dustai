@echo off
setlocal EnableDelayedExpansion
title DUST AI v2.0 - Installer
echo.
echo  ================================================================
echo   DUST AI v2.0 - Installer
echo   Agente desktop autonomo - Windows 11
echo  ================================================================
echo.

:: ─── Crea cartella base ───────────────────────────────────────────────────────
set BASE=A:\dustai_stuff
if not exist "%BASE%" (
    mkdir "%BASE%"
    echo [OK] Creata cartella base: %BASE%
) else (
    echo [OK] Cartella base: %BASE%
)

:: ─── Python ───────────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [..] Python non trovato - installo via winget...
    winget install -e --id Python.Python.3.11 --silent
    if errorlevel 1 (
        echo [ERR] Installazione Python fallita.
        echo       Installa Python 3.11 manualmente da https://python.org
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [OK] %%i

:: ─── Pip upgrade ──────────────────────────────────────────────────────────────
echo [..] Aggiorno pip...
python -m pip install --upgrade pip --quiet

:: ─── Dipendenze Python ────────────────────────────────────────────────────────
echo [..] Installo dipendenze Python...
python -m pip install --quiet ^
    "google-generativeai>=0.8.0" ^
    "requests>=2.31.0" ^
    "pyautogui>=0.9.54" ^
    "pillow>=10.0.0" ^
    "playwright>=1.40.0" ^
    "python-dotenv>=1.0.0" ^
    "colorama>=0.4.6" ^
    "PySide6>=6.6.0" ^
    "ollama>=0.2.0" ^
    "psutil>=5.9.0" ^
    "mss>=9.0.0"

:: pywin32 separato (richiede post-install)
python -m pip install --quiet "pywin32>=306"
python -c "import win32api" >nul 2>&1
if errorlevel 1 (
    echo [..] pywin32 post-install...
    python Scripts\pywin32_postinstall.py -install >nul 2>&1
)

:: ─── Playwright Chromium ─────────────────────────────────────────────────────
echo [..] Installo Playwright Chromium...
python -m playwright install chromium --quiet

:: ─── Ollama ───────────────────────────────────────────────────────────────────
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [..] Ollama non trovato - installo via winget...
    winget install -e --id Ollama.Ollama --silent
)
ollama --version >nul 2>&1
if not errorlevel 1 (
    echo [OK] Ollama installato

    :: Configura iGPU AMD (Ryzen 5600G)
    setx OLLAMA_GPU_LAYERS 18 >nul 2>&1
    setx OLLAMA_NUM_GPU 1 >nul 2>&1
    echo [OK] iGPU configurata: OLLAMA_GPU_LAYERS=18

    :: Scarica modello locale (opzionale - chiedi conferma)
    set /p PULL_MODEL="Scaricare qwen3:8b (5.5GB)? [s/N] "
    if /i "!PULL_MODEL!"=="s" (
        echo [..] Download qwen3:8b - potrebbe richiedere 10-20 minuti...
        ollama pull qwen3:8b
    )
) else (
    echo [WARN] Ollama non installato - solo modelli cloud disponibili
)

:: ─── File .env ────────────────────────────────────────────────────────────────
if not exist "%BASE%\.env" (
    echo # DUST AI - API Keys > "%BASE%\.env"
    echo GOOGLE_API_KEY=inserisci_qui_la_tua_google_api_key >> "%BASE%\.env"
    echo PERPLEXITY_API_KEY=inserisci_qui_la_tua_perplexity_api_key >> "%BASE%\.env"
    echo. >> "%BASE%\.env"
    echo [!!] File .env creato in %BASE%
    echo      Inserisci le tue API keys prima di avviare DUST AI
    notepad "%BASE%\.env"
) else (
    echo [OK] File .env gia' presente
)

:: ─── Struttura cartelle ────────────────────────────────────────────────────────
for %%d in (logs memory skills profiles backups cache tasks screenshots patches) do (
    if not exist "%BASE%\%%d" mkdir "%BASE%\%%d"
)
echo [OK] Struttura cartelle creata in %BASE%

:: ─── Verifica finale ─────────────────────────────────────────────────────────
echo.
echo  ================================================================
echo   Verifica installazione...
echo  ================================================================
python -c "import google.generativeai, PySide6, playwright, psutil, mss; print('  [OK] Dipendenze Python OK')"
if errorlevel 1 echo   [ERR] Alcune dipendenze mancanti - riesegui install.bat

echo.
echo  ================================================================
echo   Installazione completata!
echo   Avvio: run.bat
echo   Console: run.bat --console
echo   Base path: %BASE%
echo  ================================================================
echo.
pause
