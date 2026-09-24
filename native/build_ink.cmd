@echo off
setlocal
if not exist temp mkdir temp
if not exist assets mkdir assets
set "EOING_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%EOING_VSWHERE%" exit /b 2
for /f "usebackq tokens=*" %%i in (`"%EOING_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "EOING_VS=%%i"
if not defined EOING_VS exit /b 2
call "%EOING_VS%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /LD /EHsc /std:c++17 /utf-8 native\InkOverlay.cpp /Fo:temp\InkOverlay.obj /link d2d1.lib d3d11.lib dxgi.lib dcomp.lib user32.lib gdi32.lib /OUT:assets\EoingPDF.Ink.dll /IMPLIB:temp\InkOverlay.lib
exit /b %errorlevel%
