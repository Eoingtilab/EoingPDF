@echo off
cd /d "%~dp0"
start /wait "" "EoingPDF.exe" --install-menu
exit /b %errorlevel%
