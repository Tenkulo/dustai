@echo off
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM ── Processa TaskQueue pending prima della GUI ──
python process_queue.py

REM ── Avvia GUI ──
python run.py %*
