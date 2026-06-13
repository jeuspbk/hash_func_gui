@echo off
REM ===== Hash Function Generator GUI 실행기 (콘솔 없이) =====
REM pythonw로 콘솔 창 없이 GUI만 띄웁니다. (pythonw에 tkinter 필요)
cd /d "%~dp0"
start "" pythonw main.py
