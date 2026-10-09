@echo off
rem ---------------------------------------------------------------------
rem Verknuepfung-erstellen.bat
rem
rem Legt per Doppelklick eine Desktop-Verknuepfung fuer das Dashboard an.
rem Der Umweg ueber diese Datei ist noetig, weil Windows das direkte
rem Starten von .ps1-Dateien per Doppelklick standardmaessig blockiert.
rem ---------------------------------------------------------------------

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Verknuepfung-erstellen.ps1"

echo.
pause
