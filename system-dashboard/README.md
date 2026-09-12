# System-Dashboard

Ein natives Windows-Desktop-Dashboard mit 13 Kacheln. Jede Kachel zeigt oben
eine Live-System-Info (runder Gauge, Balken oder große Zahl) und darunter ein
bis zwei Aktions-Buttons, die entweder direkt etwas ausführen oder den
passenden Windows-Dialog öffnen.

Die Oberfläche basiert auf **customtkinter** (dunkles Theme), die Messwerte
kommen von **psutil**, die Temperaturen optional von **LibreHardwareMonitor**.

---

## Installation

Voraussetzung ist **Python 3.11 oder neuer** (unter Windows).

```bat
pip install -r requirements.txt
```

## Starten

```bat
python main.py
```

Das Fenster öffnet sich in 1180×980 (so sind alle 13 Kacheln ohne Scrollen
sichtbar) und lässt sich bis ~960×640 verkleinern; das Raster scrollt dann.
Wird es sehr schmal gezogen, wechselt das Raster von 4 auf 2 Spalten und lässt
sich scrollen.

---

## Die 13 Kacheln

| # | Kachel | Anzeige | Buttons |
|---|--------|---------|---------|
| 1 | Laufwerk C: | Balken | Reinigen · Eigenschaften |
| 2 | Weitere Laufwerke | zwei Balken | Öffnen · Eigenschaften |
| 3 | Arbeitsspeicher | Balken | Task-Manager · Freigeben 🛡 |
| 4 | CPU-Auslastung | Gauge | Task-Manager · Top-Prozesse |
| 5 | CPU-Temperatur | Gauge | Verlauf · Warnschwelle |
| 6 | GPU-Temperatur | Gauge | Verlauf · Warnschwelle |
| 7 | Netzwerk | zwei große Zahlen | Einstellungen · IP erneuern 🛡 |
| 8 | Autostart | große Zahl | Verwalten · Liste |
| 9 | Papierkorb | große Zahl | Leeren · Öffnen |
| 10 | Temporäre Dateien | große Zahl | Löschen · Reinigung |
| 11 | Windows-Update | Statustext | Nach Updates suchen |
| 12 | System | Laufzeit | Systeminfo · Neustart |
| 13 | Wartung | große Zahl (offene App-Updates) | Aktualisieren 🛡 · Viren-Scan 🛡 |

**Laptop-Sonderfall:** Meldet Windows einen Akku, ersetzt eine **Akku**-Kachel
(Ladestand als Ring, Restlaufzeit, Netzbetrieb) automatisch die
GPU-Temperatur-Kachel. Auf einem Desktop-PC bleibt es bei der Aufteilung oben.

Alle Werte werden von einem Hintergrund-Thread alle 2 Sekunden gelesen; die
Anzeige selbst wird ausschließlich im Main-Thread aktualisiert (Tkinter ist
nicht thread-sicher). Aktualisiert werden nur Werte und Farben — es werden nie
Widgets neu gebaut, deshalb flackert nichts.

### Farb-Logik

Auslastung: **< 70 %** blau · **70–90 %** gelb · **> 90 %** lila.
Temperatur: **< 60 °C** blau · **60–80 °C** gelb · **> 80 °C** lila.
Die obere Temperaturschwelle lässt sich pro Kachel über den Button
*Warnschwelle* ändern; oberhalb davon färbt sich die Kachel lila und zeigt ein
Warnzeichen.

---

## Wartung: App-Updates und Viren-Scan

Die Kachel **Wartung** bündelt zwei Windows-Bordmittel:

* **Aktualisieren 🛡** führt `winget upgrade --all` aus und bringt damit alle
  über den Windows-Paketmanager verwalteten Programme auf den neuesten Stand.
  Der Vorgang läuft nach einer Rückfrage bewusst in einem **sichtbaren
  Konsolenfenster** (er dauert mehrere Minuten und zeigt dort den Fortschritt
  je Paket). Als Live-Wert zeigt die Kachel, wie viele Programme aktuell ein
  Update hätten — ermittelt aus der Ausgabe von `winget upgrade`. Diese Abfrage
  braucht einige Sekunden und läuft deshalb in einem eigenen Thread, höchstens
  alle 30 Minuten; der Button **↻ Aktualisieren** in der Kopfzeile erzwingt eine
  sofortige Neumessung.
* **Viren-Scan 🛡** startet `MRT.exe`, das *Windows-Tool zum Entfernen bösartiger
  Software*. Es bringt einen eigenen Assistenten mit, in dem sich Scan-Umfang
  wählen und der Vorgang jederzeit abbrechen lässt. Unter der Zahl zeigt die
  Kachel das Datum des letzten MRT-Laufs, gelesen aus `C:\Windows\debug\mrt.log`.

Beide Aktionen brauchen Administratorrechte und sind ohne diese ausgegraut.
Fehlt `winget` (älteres Windows ohne App-Installer), zeigt die Kachel „n/a"; der
Viren-Scan funktioniert davon unabhängig weiter.

---

---

## Adminrechte

Die App läuft **ohne Administratorrechte** vollständig — lediglich die Aktionen
mit einem gelben Schild-Symbol 🛡 sind dann ausgegraut:

* Arbeitsspeicher → *Freigeben* (Standby-Liste leeren)
* Netzwerk → *IP erneuern*
* Reinigung → Windows-Temp, Windows-Update-Cache, Delivery-Optimization

Ein Klick auf die Pille **„Standard-Benutzer"** oben rechts startet die App nach
Rückfrage mit Administratorrechten neu (Windows zeigt dabei die übliche
UAC-Abfrage).

---

## Temperaturen: LibreHardwareMonitor-DLL

CPU- und GPU-Temperatur werden über **LibreHardwareMonitor** gelesen. Die
dafür nötige DLL liegt aus Lizenzgründen nicht bei:

> **Wichtig:** pythonnet lädt die DLL in das klassische **.NET Framework**.
> Es muss daher die **net472-Variante** der Bibliothek sein — die Builds
> „.NET 8" / „.NET 10" aus den neuesten Releases funktionieren **nicht**
> (Symptom: „No module named 'LibreHardwareMonitor'"). Am besten alle DLLs
> aus dem net472-Paket zusammen nach `lib/` kopieren, damit auch die
> Abhängigkeiten (HidSharp usw.) auffindbar sind.

1. `LibreHardwareMonitorLib.dll` von der offiziellen Quelle herunterladen:
   <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases>
2. Die Datei (und am besten auch die im selben ZIP enthaltene
   `HidSharp.dll`) in den Ordner **`lib/`** dieses Projekts legen:
   ```
   system-dashboard/lib/LibreHardwareMonitorLib.dll
   system-dashboard/lib/HidSharp.dll
   ```
3. Falls Windows die heruntergeladenen DLLs blockiert (Rechtsklick →
   Eigenschaften → „Zulassen"), in PowerShell: `Unblock-File lib\*.dll`
4. Die App als **Administrator** starten — ohne erhöhte Rechte geben die
   Sensoren in der Regel keine Werte zurück.

Bequem per PowerShell (aus dem Ordner `system-dashboard/`) — sucht in den
Releases automatisch nach dem net472-Paket und kopiert alle DLLs:

```powershell
$rels = Invoke-RestMethod "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases"
$asset = $rels | ForEach-Object { $_.assets } | Where-Object { $_.name -match 'net4|4\.7' } | Select-Object -First 1
Invoke-WebRequest $asset.browser_download_url -OutFile lhm472.zip
Expand-Archive lhm472.zip -DestinationPath lhm472 -Force
Remove-Item lib\*.dll -ErrorAction SilentlyContinue
Get-ChildItem lhm472 -Recurse -Filter *.dll | Copy-Item -Destination lib\ -Force
Unblock-File lib\*.dll
```

Fehlt die DLL, laufen die Sensoren nicht oder es findet sich kein passender
Sensor, zeigen beide Temperatur-Kacheln sauber **„n/a"** mit grauem Ring und
deaktivierten Buttons. Die restliche App ist davon nicht betroffen.

---

## Reinigungs-Routine

Der Button *Reinigen* (Kachel „Laufwerk C:") bzw. *Reinigung öffnen* (Kachel
„Temporäre Dateien") öffnet ein eigenes, modales Fenster mit drei Schritten:

1. **Analysieren** — pro Kategorie wird ermittelt, wie viel Platz frei würde.
2. **Auswählen** — Kategorien an-/abwählen, unten läuft die Summe mit.
3. **Löschen** — nach Sicherheitsabfrage, mit Fortschrittsbalken, Live-Zähler
   („gelöscht / übersprungen") und abschließender Zusammenfassung.

| Kategorie | Quelle | Admin | Vorausgewählt |
|---|---|---|---|
| Temporäre Dateien (Benutzer) | `%TEMP%` | nein | **ja** |
| Temporäre Dateien (Windows) | `C:\Windows\Temp` | ja | nein |
| Papierkorb | Shell-API | nein | **ja** |
| Miniaturansichten-Cache | `%LocalAppData%\…\Explorer\thumbcache_*.db` | nein | **ja** |
| Windows-Update-Cache *(Erweitert)* | `C:\Windows\SoftwareDistribution\Download` | ja | nein |
| Delivery-Optimization *(Erweitert)* | Übermittlungsoptimierung | ja | nein |

**Sicherheitsregeln:** Es werden ausschließlich die oben genannten Cache- und
Temp-Pfade angefasst. Benutzerdaten — Downloads, Dokumente, Bilder,
Browser-Historie, Programmdateien — werden **niemals** berührt. Alle Pfade
stehen als Konstanten oben in `app/cleaning.py` und lassen sich dort anpassen.
Gesperrte oder gerade benutzte Dateien werden übersprungen, nicht erzwungen.

### Windows-Datenträgerbereinigung

Im selben Fenster startet der Button *Windows-Datenträgerbereinigung* das
Bordmittel `cleanmgr /d C:` für die offizielle, tiefere Bereinigung.

Wer sich die Kategorien dort einmalig zusammenstellen möchte:

```bat
cleanmgr /sageset:1     :: einmalig: Kategorien auswählen und speichern
cleanmgr /sagerun:1     :: danach: gespeicherte Auswahl ohne Rückfrage ausführen
```

---

## Projektstruktur

```
system-dashboard/
├─ main.py                 Einstiegspunkt: Admin-Check, Fenster starten
├─ requirements.txt
├─ README.md
├─ app/
│  ├─ theme.py             Farben, Schriftgrößen, status_color / temp_color
│  ├─ dashboard.py         Hauptfenster, Kopfzeile, Raster, Refresh-Loop
│  ├─ system_info.py       alle Datenabfragen (psutil, winreg, Größen)
│  ├─ hardware.py          LibreHardwareMonitor-Anbindung + Fallback
│  ├─ actions.py           alle Aktionen (subprocess, ShellExecute, ctypes)
│  ├─ cleaning.py          Reinigungs-Routine (eigenes Fenster)
│  └─ widgets/
│     ├─ tile.py           Basis-Kachel + StatValue („große Zahl")
│     ├─ gauge.py          CircularGauge (runder Ring auf Canvas)
│     ├─ meter.py          Balken-Meter (auf CTkProgressBar)
│     └─ dialogs.py        Bestätigung, Info-Popup, Verlaufsgraph, Eingabe
└─ lib/
   └─ LibreHardwareMonitorLib.dll   (selbst hinzufügen, siehe oben)
```

---

## Als einzelne .exe verpacken

Mit **PyInstaller** lässt sich die App zu einer einzelnen ausführbaren Datei
bündeln. Empfohlener Befehl (aus dem Ordner `system-dashboard/`, die
Sensor-DLLs müssen dafür bereits in `lib/` liegen):

```bat
pip install pyinstaller
pyinstaller --onefile --windowed --uac-admin --name System-Dashboard --add-data "lib;lib" --collect-all customtkinter --collect-all pythonnet --collect-all clr_loader main.py
```

Die fertige Datei liegt anschließend unter `dist\System-Dashboard.exe`.

Hinweise:

* `--windowed` verhindert, dass beim Start ein Konsolenfenster aufgeht.
* `--add-data "lib;lib"` nimmt die LibreHardwareMonitor-DLLs mit ins Paket.
  Unter Windows ist das Trennzeichen ein **Semikolon** (nicht `:`).
* `--collect-all customtkinter` bündelt die Theme-Dateien von customtkinter -
  ohne sie startet die gepackte App nicht.
* `--collect-all pythonnet --collect-all clr_loader` bündelt die
  .NET-Brücke vollständig (Python.Runtime.dll und die Runtime-Lader) -
  sonst bleiben die Temperatur-Kacheln in der .exe auf "n/a".
* Ein eigenes Icon lässt sich mit `--icon meinicon.ico` setzen.
* Der erste Start einer frisch gebauten .exe kann von Windows SmartScreen
  angehalten werden: "Weitere Informationen" → "Trotzdem ausführen".

### Die .exe standardmäßig als Administrator starten

Temperatur-Sensoren und die admin-pflichtigen Reinigungs-Kategorien brauchen
erhöhte Rechte. Damit die .exe immer danach fragt, gibt es zwei Wege:

**A. Über die Verknüpfung (ohne Neu-Bauen):**
Rechtsklick auf `main.exe` → *Eigenschaften* → Reiter *Kompatibilität* →
Haken bei **„Programm als Administrator ausführen"** → *Übernehmen*.

**B. Fest ins Programm einbauen (UAC-Manifest):**

Das `--uac-admin` im empfohlenen Befehl oben hinterlegt im
Programm-Manifest, dass Windows beim Start grundsätzlich die UAC-Abfrage
anzeigt - die Temperatursensoren funktionieren dann direkt. Wer die .exe
lieber ohne erzwungene Abfrage baut, lässt `--uac-admin` einfach weg.

Wird die App ohne Adminrechte gestartet, funktioniert sie trotzdem — die
betroffenen Aktionen sind dann lediglich mit 🛡 ausgegraut, und über die Pille
oben rechts lässt sie sich jederzeit erhöht neu starten.
