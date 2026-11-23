@echo off
setlocal
cd /d "%TEMP%"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0installer.py"
    goto :end
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0installer.py"
    goto :end
)
echo Python 3 is required to open the installer window.
echo Install Python 3 for Windows, then try again.
pause
:end
