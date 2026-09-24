@echo off
setlocal
if not exist temp mkdir temp
if not exist assets mkdir assets
set "EOING_PYTHON=python"
if exist .venv_d\Scripts\python.exe set "EOING_PYTHON=.venv_d\Scripts\python.exe"
"%EOING_PYTHON%" scripts\generate_shell_strings.py
if errorlevel 1 exit /b 1
set "EOING_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%EOING_VSWHERE%" exit /b 2
for /f "usebackq tokens=*" %%i in (`"%EOING_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "EOING_VS=%%i"
if not defined EOING_VS exit /b 2
call "%EOING_VS%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT /LD /EHsc /std:c++17 /utf-8 /Itemp native\ExplorerCommand.cpp /Fo:temp\ExplorerCommand.obj /link shell32.lib shlwapi.lib ole32.lib uuid.lib /DEF:native\explorer.def /OUT:assets\EoingPDF.Explorer.dll /IMPLIB:temp\ExplorerCommand.lib
exit /b %errorlevel%
