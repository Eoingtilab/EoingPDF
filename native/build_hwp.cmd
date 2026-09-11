@echo off
setlocal
if not exist temp mkdir temp
if not exist assets mkdir assets
set "EOING_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%EOING_VSWHERE%" exit /b 2
for /f "usebackq tokens=*" %%i in (`"%EOING_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "EOING_VS=%%i"
if not defined EOING_VS exit /b 2
call "%EOING_VS%\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /LD /EHsc native\HwpPathGuard.cpp /Fo:temp\hwp-x86.obj /link /DEF:native\hwp-x86.def /OUT:assets\hwp-x86.dll /IMPLIB:temp\hwp-x86.lib
if errorlevel 1 exit /b 1
call "%EOING_VS%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /LD /EHsc native\HwpPathGuard.cpp /Fo:temp\hwp-x64.obj /link /OUT:assets\hwp-x64.dll /IMPLIB:temp\hwp-x64.lib
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /EHsc /std:c++17 native\WindowsOcr.cpp /Fo:temp\WindowsOcr.obj /Fe:assets\EoingPDF.Ocr.exe /link windowsapp.lib
exit /b %errorlevel%
