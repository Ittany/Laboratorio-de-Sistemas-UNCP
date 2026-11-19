@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No se encuentra el entorno virtual. Siga primero la instalacion del README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py runserver
pause
