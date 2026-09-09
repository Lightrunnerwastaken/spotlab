@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0einrichten.ps1" %*
set "SETUP_RESULT=%errorlevel%"
if not "%SETUP_RESULT%"=="0" echo Einrichtung fehlgeschlagen. Bitte die Meldung oben beachten.
pause
exit /b %SETUP_RESULT%
