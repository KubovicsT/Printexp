@echo off
setlocal
cd /d "%~dp0"
where cl >nul 2>&1
if not errorlevel 1 goto compile
REM vswhere supports nonstandard install paths such as X:\VisualStudioBuildTools.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
        if exist "%%I\VC\Auxiliary\Build\vcvars64.bat" (
            call "%%I\VC\Auxiliary\Build\vcvars64.bat"
            goto compile
        )
    )
)
for %%Y in (2022 2019) do (
  for %%E in (BuildTools Community Professional Enterprise) do (
    if exist "%ProgramFiles%\Microsoft Visual Studio\%%Y\%%E\VC\Auxiliary\Build\vcvars64.bat" (
      call "%ProgramFiles%\Microsoft Visual Studio\%%Y\%%E\VC\Auxiliary\Build\vcvars64.bat"
      goto compile
    )
    if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\%%Y\%%E\VC\Auxiliary\Build\vcvars64.bat" (
      call "%ProgramFiles(x86)%\Microsoft Visual Studio\%%Y\%%E\VC\Auxiliary\Build\vcvars64.bat"
      goto compile
    )
  )
)
echo ERROR: Microsoft Visual C++ Build Tools x64 not found.
echo Install free Visual Studio 2022 Build Tools with Desktop Development with C++.
exit /b 1
:compile
if not exist "dist\windows" mkdir "dist\windows"
cl /nologo /std:c++17 /DUNICODE /D_UNICODE /EHsc /W4 /O2 /LD "src\native\Stage1Page.cpp" /link /OUT:"dist\windows\UV3DPage.dll" User32.lib Gdi32.lib Comctl32.lib
if errorlevel 1 exit /b 2
cl /nologo /std:c++17 /DUNICODE /D_UNICODE /EHsc /W4 /O2 "src\native\Stage1Launcher.cpp" /link /SUBSYSTEM:WINDOWS /OUT:"dist\windows\PrintExp3DLauncher.exe" User32.lib Shell32.lib Bcrypt.lib
if errorlevel 1 exit /b 3
echo Native Windows x64 3D page successfully built.
exit /b 0
