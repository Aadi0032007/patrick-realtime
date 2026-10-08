@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m patrick.realtime %*
) else (
  python -m patrick.realtime %*
)
