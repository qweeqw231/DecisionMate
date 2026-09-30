@echo off
title DecisionMate
cd /d "%~dp0"
"%~dp0..\decision-backend\decision-backend\.venv\Scripts\python.exe" "%~dp0launcher.py" --mode main
if errorlevel 1 pause