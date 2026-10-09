@echo off
rem ---------------------------------------------------------------------
rem Dashboard-starten.bat
rem
rem Startet das System-Dashboard per Doppelklick:
rem  - ohne Konsolenfenster (pythonw.exe statt python.exe)
rem  - mit Administratorrechten (Windows fragt per UAC nach), damit die
rem    Temperatursensoren und die Admin-Aktionen zur Verfuegung stehen
rem ---------------------------------------------------------------------

cd /d "%~dp0"

rem pythonw.exe startet Python ohne Konsolenfenster. Fehlt sie, tut es python.exe.
set "PYSTART=pythonw.exe"
where pythonw.exe >nul 2>&1 || set "PYSTART=python.exe"

powershell -NoProfile -Command "try { Start-Process -FilePath '%PYSTART%' -ArgumentList 'main.py' -WorkingDirectory '%~dp0' -Verb RunAs } catch { Write-Host ''; Write-Host ('Start nicht moeglich: ' + $_.Exception.Message) -ForegroundColor Yellow; Write-Host 'Wurde die Administrator-Abfrage abgebrochen? Sonst pruefen: python --version'; Read-Host 'Zum Schliessen Enter druecken' }"
