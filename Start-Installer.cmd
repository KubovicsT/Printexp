@echo off
setlocal
cd /d "%~dp0"
REM Launch the single Windows add-on manager; no separate dependency window.
wscript.exe "%~dp0Start-Installer.vbs"
if errorlevel 1 (
  echo Could not start PrintExp 3D Add-on Manager.
  pause
)
