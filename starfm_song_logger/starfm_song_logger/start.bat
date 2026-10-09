@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Follow the setup instructions in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" starfm_logger.py
pause
