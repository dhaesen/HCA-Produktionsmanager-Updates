@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0ROLLBACK.ps1"
set "HCA_EXIT=%ERRORLEVEL%"
echo.
if not "%HCA_EXIT%"=="0" echo Die Wiederherstellung wurde mit Fehlercode %HCA_EXIT% beendet.
pause
exit /b %HCA_EXIT%
