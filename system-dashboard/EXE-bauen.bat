@echo off
setlocal
rem ---------------------------------------------------------------------
rem EXE-bauen.bat
rem
rem Baut per Doppelklick eine einzelne, eigenstaendige
rem System-Dashboard.exe - danach laeuft die App auch auf Rechnern ohne
rem installiertes Python.
rem
rem Dauer: einige Minuten. Ergebnis: dist\System-Dashboard.exe
rem ---------------------------------------------------------------------

cd /d "%~dp0"

echo =====================================================================
echo  System-Dashboard - eigenstaendige .exe bauen
echo =====================================================================
echo.

rem --- 1. Python vorhanden? --------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python wurde nicht gefunden.
    echo         Bitte Python 3.11+ installieren und beim Setup die Option
    echo         "Add python.exe to PATH" anhaken.
    goto :ende
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo Gefunden: %%v

rem --- 2. Abhaengigkeiten sicherstellen --------------------------------
echo.
echo Pruefe Abhaengigkeiten ...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo FEHLER: Die Pakete aus requirements.txt liessen sich nicht installieren.
    goto :ende
)

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller wird nachinstalliert ...
    python -m pip install --quiet --disable-pip-version-check pyinstaller
    if errorlevel 1 (
        echo FEHLER: PyInstaller liess sich nicht installieren.
        goto :ende
    )
)

rem --- 3. Hinweis, falls die Sensor-DLL fehlt --------------------------
rem PyInstaller bricht ab, wenn der per --add-data angegebene Ordner gar
rem nicht existiert - deshalb notfalls anlegen.
if not exist "lib" mkdir "lib"

if not exist "lib\LibreHardwareMonitorLib.dll" (
    echo.
    echo HINWEIS: lib\LibreHardwareMonitorLib.dll fehlt.
    echo          Die .exe wird trotzdem gebaut, zeigt dann aber bei den
    echo          Temperatur-Kacheln "n/a". Die DLL laesst sich auch spaeter
    echo          neben die fertige .exe legen - ein Neubau ist nicht noetig.
    echo.
)

rem --- 4. Bauen --------------------------------------------------------
echo.
echo Baue ... das dauert einige Minuten, bitte warten.
echo.

python -m PyInstaller --noconfirm --onefile --windowed --uac-admin --name "System-Dashboard" --icon "assets\dashboard.ico" --add-data "lib;lib" --collect-all customtkinter --collect-all pythonnet --collect-all clr_loader main.py
if errorlevel 1 (
    echo.
    echo FEHLER: Der Build ist fehlgeschlagen. Die Meldungen oben nennen den Grund.
    goto :ende
)

rem --- 5. Ergebnis -----------------------------------------------------
echo.
if exist "dist\System-Dashboard.exe" (
    echo =====================================================================
    echo  Fertig!
    echo =====================================================================
    echo.
    echo  Die Datei liegt hier:
    echo    %~dp0dist\System-Dashboard.exe
    echo.
    echo  Sie ist eigenstaendig - einfach auf den Desktop ziehen oder
    echo  weitergeben. Python muss auf dem Zielrechner nicht installiert
    echo  sein. Beim Start fragt Windows nach Administratorrechten.
    echo.
    echo  Beim allerersten Start kann Windows SmartScreen anspringen:
    echo    "Weitere Informationen" anklicken, dann "Trotzdem ausfuehren".
    echo.
    choice /c JN /n /m "Ordner mit der .exe jetzt oeffnen? [J/N] "
    if not errorlevel 2 explorer "%~dp0dist"
) else (
    echo FEHLER: dist\System-Dashboard.exe wurde nicht erzeugt.
)

:ende
echo.
pause
endlocal
