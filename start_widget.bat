@echo off
cd /d "%~dp0"
start "" "http://localhost:5000/widget"
python process_priority_manager.py --widget
