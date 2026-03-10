@echo off
echo ===================================
echo   DUST AI - Installazione Windows
echo ===================================

:: Verifica Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Python non trovato nel PATH.
    echo Scarica Python da https://python.org
    pause
    exit /b 1
)

:: Crea ambiente virtuale
if not exist "venv" (
    echo Creazione ambiente virtuale...
    python -m venv venv
)

:: Attiva e installa
call venv\Scripts\activate.bat
echo Installazione dipendenze...
pip install -r requirements.txt
pip install pywin32

:: Installa browser Playwright
echo Installazione browser Chromium per Playwright...
playwright install chromium

:: Crea file .env se non esiste
if not exist "%APPDATA%\dustai\.env" (
    mkdir "%APPDATA%\dustai" 2>nul
    echo # DUST AI - API Keys > "%APPDATA%\dustai\.env"
    echo GOOGLE_API_KEY=inserisci_qui_la_tua_key >> "%APPDATA%\dustai\.env"
    echo PERPLEXITY_API_KEY=inserisci_qui_la_tua_key >> "%APPDATA%\dustai\.env"
    echo.
    echo FILE .ENV CREATO: %APPDATA%\dustai\.env
    echo Apri il file e inserisci le tue API keys!
)

echo.
echo ===================================
echo  Installazione completata!
echo  Avvia con: run.bat
echo ===================================
pause
