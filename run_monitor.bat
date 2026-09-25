@echo off
title SIH Problem Statement Monitor
cd /d "%~dp0"
echo ============================================================
echo Starting SIH Problem Statement Count Monitor...
echo Press Ctrl+C to stop the monitor.
echo ============================================================
python app.py
pause
