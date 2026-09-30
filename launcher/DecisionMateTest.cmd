@echo off
title DecisionMate Test
cd /d "%~dp0"
"%~dp0..\decision-backend\decision-backend\.venv\Scripts\python.exe" "%~dp0launcher.py" --mode test
if errorlevel 1 pause