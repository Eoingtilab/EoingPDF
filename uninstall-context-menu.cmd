@echo off
cd /d "%~dp0"
start /wait "" "EoingPDF.exe" --uninstall-menu
exit /b %errorlevel%
