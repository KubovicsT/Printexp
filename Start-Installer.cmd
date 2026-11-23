@echo off
setlocal
cd /d "%~dp0"
REM Windows PowerShell and Windows Forms are included with supported Windows 10/11.
REM This bootstrap does not require Python, Git, or the C++ compiler to be installed.
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Bootstrap-Installer.ps1"
if errorlevel 1 (
  echo.
  echo The PrintExp 3D setup did not finish. See the message above.
  pause
)
