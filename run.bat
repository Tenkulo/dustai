@echo off
:: Attiva venv se presente
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)
python run.py %*
