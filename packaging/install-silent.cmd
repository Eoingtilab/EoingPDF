@echo off
setlocal EnableExtensions DisableDelayedExpansion
if /I not "%~1"=="/S" goto usage
set "EOING_SETUP_EXE="
for %%I in ("%~dp0EoingPDF-*-Setup-x64.exe") do (
    if exist "%%~fI" (
        if defined EOING_SETUP_EXE goto ambiguous
        set "EOING_SETUP_EXE=%%~fI"
    )
)
if not defined EOING_SETUP_EXE (
    echo EoingPDF installer is missing beside this script. 1>&2
    exit /b 2
)
rem /S is the script alias. Inno Setup uses the explicit switches below.
"%EOING_SETUP_EXE%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- %*
exit /b %ERRORLEVEL%
:ambiguous
echo Keep exactly one EoingPDF Setup EXE beside this script. 1>&2
exit /b 3
:usage
echo Usage: install-silent.cmd /S [/DIR="C:\Target Folder"] [/LOG="C:\setup.log"] 1>&2
exit /b 64
