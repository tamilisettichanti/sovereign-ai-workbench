@echo off
rem Starts the Sovereign AI Workbench and opens it in the browser.
cd /d "%~dp0"

where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed or not on PATH.
  pause
  exit /b 1
)

rem Start the Ollama model server if it is not already running.
curl -s -o nul http://127.0.0.1:11434/api/version
if errorlevel 1 (
  echo Starting Ollama...
  start "" /min ollama serve
  timeout /t 5 /nobreak >nul
)

start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" server.py
pause
