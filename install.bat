@echo off
setlocal EnableDelayedExpansion
title DUST AI - Installazione

echo.
echo  ██████╗ ██╗   ██╗███████╗████████╗     █████╗ ██╗
echo  ██╔══██╗██║   ██║██╔════╝╚══██╔══╝    ██╔══██╗██║
echo  ██║  ██║██║   ██║███████╗   ██║       ███████║██║
echo  ██║  ██║██║   ██║╚════██║   ██║       ██╔══██║██║
echo  ██████╔╝╚██████╔╝███████║   ██║       ██║  ██║██║
echo  ╚═════╝  ╚═════╝ ╚══════╝   ╚═╝       ╚═╝  ╚═╝╚═╝
echo.
echo  Desktop Unified Smart Tool AI - Setup
echo  =========================================
echo.

:: ─── Verifica Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRORE] Python non trovato nel PATH.
    echo.
    echo Tentativo installazione via winget...
    winget install Python.Python.3.12 --silent --accept-package-agreements
    if !errorlevel! neq 0 (
        echo Scarica Python manualmente: https://python.org/downloads/
        pause
        exit /b 1
    )
    echo Python installato. Riavvia questo script.
    pause
    exit /b 0
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

:: ─── Aggiorna pip ─────────────────────────────────────────────────────────────
echo.
echo Aggiorno pip...
python -m pip install --upgrade pip --quiet

:: ─── Installa dipendenze base (il bootstrap farà il resto) ────────────────────
echo Installo dipendenze base...
python -m pip install --upgrade --quiet ^
    google-generativeai ^
    requests ^
    python-dotenv ^
    colorama

:: ─── Crea struttura directory ─────────────────────────────────────────────────
echo.
echo Creo struttura directory...
if not exist "%APPDATA%\dustai" mkdir "%APPDATA%\dustai"
if not exist "%APPDATA%\dustai\logs" mkdir "%APPDATA%\dustai\logs"

:: ─── File .env ────────────────────────────────────────────────────────────────
if not exist "%APPDATA%\dustai\.env" (
    echo # DUST AI – API Keys > "%APPDATA%\dustai\.env"
    echo # Ottieni da: https://aistudio.google.com >> "%APPDATA%\dustai\.env"
    echo GOOGLE_API_KEY=inserisci_qui_la_tua_gemini_key >> "%APPDATA%\dustai\.env"
    echo PERPLEXITY_API_KEY=inserisci_qui_la_tua_perplexity_key >> "%APPDATA%\dustai\.env"
    echo.
    echo [IMPORTANTE] File .env creato: %APPDATA%\dustai\.env
    echo Aprilo e inserisci la tua GOOGLE_API_KEY prima di avviare DUST AI.
    echo.
    start notepad "%APPDATA%\dustai\.env"
    echo Premi un tasto dopo aver salvato le API keys...
    pause >nul
)

:: ─── Avvia Bootstrap Python (installa tutto il resto autonomamente) ───────────
echo.
echo Avvio Bootstrap automatico...
echo (installerà PySide6, Playwright, Ollama, ecc. in autonomia)
echo.
python -c "import sys; sys.path.insert(0,'%~dp0'); from src.bootstrap import Bootstrap; from pathlib import Path; Bootstrap(Path(r'%APPDATA%\dustai')).run()"

echo.
echo =========================================
echo  Setup completato!
echo  Avvia DUST AI con: run.bat
echo  oppure: python run.py --gui
echo =========================================
echo.
pause
