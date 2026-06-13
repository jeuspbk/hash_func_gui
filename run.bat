@echo off
REM ===== Hash Function Generator GUI 실행기 (콘솔 표시) =====
REM 더블클릭하거나 명령창에서 run.bat 실행. 오류가 나면 창이 유지됩니다.
cd /d "%~dp0"
python main.py
if errorlevel 1 (
  echo.
  echo [실행 실패] Python(3.10+, tkinter 포함)이 설치되어 PATH에 있는지 확인하세요.
  pause
)
