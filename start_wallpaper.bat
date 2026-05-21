@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONW_EXE=D:\Anaconda3\pythonw.exe"
if exist "%PYTHONW_EXE%" goto run_hidden

set "PYTHONW_EXE=D:\Anaconda3\python.exe"
if exist "%PYTHONW_EXE%" goto run_visible

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py"
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0main.py"
    if errorlevel 1 pause
    exit /b
)

echo Python was not found. Install Python or add it to PATH.
pause
exit /b 1

:run_hidden
start "" "%PYTHONW_EXE%" "%~dp0main.py"
exit /b

:run_visible
"%PYTHONW_EXE%" "%~dp0main.py"
if errorlevel 1 pause
