@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -m venv .venv
    ) else (
        py -3.11 -c "import sys" >nul 2>&1
        if errorlevel 1 goto :python_required
        py -3.11 -m venv .venv
    )
    if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)" >nul 2>&1
if errorlevel 1 goto :incompatible_environment
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto :error
exit /b 0
:python_required
echo.
echo Install Python 3.11 or 3.12 with the Windows Python launcher, then try again.
echo See RUN_WAUTRACE.txt for manual setup if the py command is unavailable.
pause
exit /b 1
:incompatible_environment
echo.
echo The existing .venv must use Python 3.11 or 3.12.
echo Its files have been kept. Use a fresh extracted folder for setup with a supported Python.
pause
exit /b 1
:error
echo.
echo WauTrace could not start. Read the error above and RUN_WAUTRACE.txt.
pause
exit /b 1
