@echo off
rem Referral Desk on Windows: double-click this file, or run  start-desk.bat --dry-run  to test without a key.
rem Installs the Python packages, asks for the API key (kept in this window only, never saved), starts the
rem local server and opens the browser. Uploaded packets stay in the output\ folder on this computer.
cd /d "%~dp0"
set PYTHONUTF8=1
echo Installing Python packages (first time takes a minute)...
python -m pip install --quiet --disable-pip-version-check pymupdf anthropic reportlab pydantic python-docx
if errorlevel 1 (
  echo.
  echo Python or pip did not run. Install Python from python.org, tick "Add python.exe to PATH", then try again.
  pause
  exit /b 1
)
if /i "%~1"=="--dry-run" goto run
if "%ANTHROPIC_API_KEY%"=="" set /p ANTHROPIC_API_KEY=Paste your Anthropic API key and press Enter:
if "%ANTHROPIC_WORKSPACE_ID%"=="" set /p ANTHROPIC_WORKSPACE_ID=Workspace ID (starts with wrkspc_), or press Enter to skip:
:run
echo Starting Referral Desk. The browser opens when it is ready...
python src\desk_server.py --open %*
echo.
echo Referral Desk stopped. If you see an error above, take a screenshot of this window.
pause
