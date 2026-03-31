@echo off
title Arquive Server
cd /d "~/git\face-detection"
echo Starting Arquive server...
echo.
call venv\Scripts\activate.bat
python -m face_detect serve
pause
