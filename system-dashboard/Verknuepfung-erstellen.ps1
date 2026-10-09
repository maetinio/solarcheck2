# ---------------------------------------------------------------------
# Verknuepfung-erstellen.ps1
#
# Legt auf dem Desktop eine Verknuepfung "System-Dashboard" an, die
#  - main.py mit pythonw.exe startet (also ohne Konsolenfenster),
#  - das Symbol assets\dashboard.ico traegt und
#  - das Flag "Als Administrator ausfuehren" gesetzt hat.
#
# Aufruf per Doppelklick auf Verknuepfung-erstellen.bat.
# ---------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$projekt = Split-Path -Parent $MyInvocation.MyCommand.Definition
$skript  = Join-Path $projekt "main.py"
$symbol  = Join-Path $projekt "assets\dashboard.ico"

if (-not (Test-Path $skript)) {
    throw "main.py nicht gefunden. Liegt dieses Skript im Projektordner system-dashboard?"
}

# Python suchen. pythonw.exe startet die App ohne Konsolenfenster.
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Python wurde nicht gefunden. Ist es installiert und im PATH?" }

$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$ziel = Join-Path ([Environment]::GetFolderPath("Desktop")) "System-Dashboard.lnk"

$shell        = New-Object -ComObject WScript.Shell
$verknuepfung = $shell.CreateShortcut($ziel)
$verknuepfung.TargetPath       = $pythonw
$verknuepfung.Arguments        = '"{0}"' -f $skript
$verknuepfung.WorkingDirectory = $projekt
$verknuepfung.Description      = "System-Dashboard - Live-Uebersicht ueber Laufwerke, CPU, RAM und mehr"
if (Test-Path $symbol) { $verknuepfung.IconLocation = $symbol }
$verknuepfung.Save()

# "Als Administrator ausfuehren" laesst sich ueber WScript.Shell nicht setzen.
# Im .lnk-Format steckt dieses Flag (RunAsUser) in den LinkFlags ab Offset
# 0x14; sein Bit 13 liegt damit im Byte an Position 0x15 als Wert 0x20.
$bytes = [System.IO.File]::ReadAllBytes($ziel)
$bytes[0x15] = $bytes[0x15] -bor 0x20
[System.IO.File]::WriteAllBytes($ziel, $bytes)

Write-Host ""
Write-Host "Fertig - die Verknuepfung liegt auf dem Desktop:" -ForegroundColor Green
Write-Host "  $ziel"
Write-Host ""
Write-Host "Ein Doppelklick startet das Dashboard; Windows fragt dabei nach"
Write-Host "Administratorrechten (noetig fuer Temperatursensoren und Wartung)."
Write-Host ""
Write-Host "Soll die Abfrage nicht kommen: Rechtsklick auf die Verknuepfung ->"
Write-Host "Eigenschaften -> Erweitert -> Haken bei 'Als Administrator ausfuehren'"
Write-Host "entfernen. Temperaturen und Admin-Aktionen sind dann deaktiviert."
