"""
selbsttest.py - Nicht-destruktiver Windows-Selbsttest für das System-Dashboard.

Prüft alle Windows-spezifischen Codepfade, die sich in der Linux-
Entwicklungsumgebung nicht verifizieren ließen: Shell-API (Papierkorb),
Registry-Zugriffe, LibreHardwareMonitor-DLL, Adminrechte usw.

WICHTIG: Dieses Skript LIEST nur. Es löscht nichts, leert nichts und
startet nichts neu. Es kann gefahrlos jederzeit ausgeführt werden.

Aufruf:   python selbsttest.py
Am Ende erscheint eine Zusammenfassung (OK / WARNUNG / FEHLER je Prüfung).
"""

from __future__ import annotations

import os
import sys
import traceback

# Ergebnis-Sammlung: Liste aus (Status, Prüfname, Detailtext).
ERGEBNISSE: list[tuple[str, str, str]] = []


def _eintragen(status: str, name: str, detail: str = "") -> None:
    ERGEBNISSE.append((status, name, detail))
    symbol = {"OK": "[OK]     ", "WARN": "[WARNUNG]", "FEHLER": "[FEHLER] "}[status]
    print(f"{symbol} {name}" + (f" - {detail}" if detail else ""))


def pruefe(name: str, warn_statt_fehler: bool = False):
    """Dekorator: führt eine Prüfung aus und fängt jede Ausnahme ab."""

    def wrapper(funktion):
        try:
            detail = funktion()
            _eintragen("OK", name, detail or "")
        except Exception as fehler:
            status = "WARN" if warn_statt_fehler else "FEHLER"
            _eintragen(status, name, f"{type(fehler).__name__}: {fehler}")
        return funktion

    return wrapper


def main() -> int:
    print("=" * 72)
    print("System-Dashboard · Windows-Selbsttest (nur Lesezugriffe)")
    print("=" * 72)
    print()

    # ------------------------------------------------------------------
    print("--- 1. Umgebung " + "-" * 50)

    @pruefe("Python-Version >= 3.11")
    def _():
        haupt, neben = sys.version_info[:2]
        assert (haupt, neben) >= (3, 11), f"gefunden: {haupt}.{neben}"
        return f"{sys.version.split()[0]}"

    @pruefe("Betriebssystem ist Windows")
    def _():
        assert sys.platform == "win32", f"gefunden: {sys.platform}"
        import platform

        return f"Windows {platform.release()}"

    @pruefe("Adminrechte-Abfrage (IsUserAnAdmin)")
    def _():
        import ctypes

        ist_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        return "läuft ALS Administrator" if ist_admin else "läuft OHNE Adminrechte (das ist ok)"

    # ------------------------------------------------------------------
    print()
    print("--- 2. Paket-Importe " + "-" * 45)

    @pruefe("tkinter")
    def _():
        import tkinter

        return f"Tk {tkinter.TkVersion}"

    @pruefe("customtkinter")
    def _():
        import customtkinter

        return f"Version {customtkinter.__version__}"

    @pruefe("psutil")
    def _():
        import psutil

        return f"Version {psutil.__version__}"

    @pruefe("pythonnet (clr)", warn_statt_fehler=True)
    def _():
        import clr  # noqa: F401

        return "importierbar"

    # ------------------------------------------------------------------
    print()
    print("--- 3. Datenquellen (system_info) " + "-" * 32)

    from app import system_info

    @pruefe("Laufwerk C:")
    def _():
        info = system_info.disk_usage("C:\\")
        assert info is not None, "keine Daten"
        return f"{info['used_gb']:.0f} GB belegt / {info['total_gb']:.0f} GB ({info['percent']:.0f} %)"

    @pruefe("Weitere Laufwerke")
    def _():
        laufwerke = system_info.weitere_laufwerke()
        if not laufwerke:
            return "keine weiteren festen Laufwerke (ok, Kachel zeigt Hinweis)"
        return " · ".join(
            f"{e['laufwerk'].rstrip(chr(92))} {e['percent']:.0f} %" for e in laufwerke
        )

    @pruefe("Arbeitsspeicher")
    def _():
        ram = system_info.ram_info()
        assert ram is not None, "keine Daten"
        return f"{ram['used_gb']:.1f} / {ram['total_gb']:.0f} GB ({ram['percent']:.0f} %)"

    @pruefe("CPU-Auslastung")
    def _():
        system_info.cpu_aufwaermen()
        import time

        time.sleep(0.3)
        cpu = system_info.cpu_info()
        assert cpu is not None, "keine Daten"
        return f"{cpu['percent']:.0f} % · {cpu['kerne']} Kerne"

    @pruefe("Netzwerk-Zähler + lokale IP")
    def _():
        netz1 = system_info.netzwerk_info()
        assert netz1 is not None, "keine Daten"
        return f"IP {netz1['ip']}"

    @pruefe("Autostart-Einträge (Registry + Ordner)")
    def _():
        eintraege = system_info.autostart_eintraege()
        beispiele = ", ".join(name for name, _ in eintraege[:3])
        return f"{len(eintraege)} Einträge" + (f" (z. B. {beispiele})" if beispiele else "")

    @pruefe("Papierkorb-Größe (SHQueryRecycleBinW)")
    def _():
        info = system_info.papierkorb_info()
        assert info is not None, "Shell-API lieferte keine Daten"
        mb = info["bytes"] / (1024 ** 2)
        return f"{info['anzahl']} Objekte, {mb:.1f} MB"

    @pruefe("Temp-Ordner-Größe (%TEMP% + Windows\\Temp)")
    def _():
        pfade = system_info.temp_ordner_pfade()
        groesse = system_info.temp_dateien_groesse()
        lesbar = [p for p in pfade if os.path.isdir(p)]
        return f"{groesse / (1024 ** 2):.1f} MB in {len(lesbar)} lesbaren Ordnern"

    @pruefe("Windows-Update-Status (Registry)", warn_statt_fehler=True)
    def _():
        status = system_info.windows_update_status()
        # Der neutrale Text ist der dokumentierte Fallback, kein Fehler -
        # als eigener Hinweis kenntlich machen.
        if status["text"].startswith("Status im"):
            return "Registry-Schlüssel nicht lesbar -> neutraler Fallback-Text (ok)"
        return status["text"]

    @pruefe("System-Details + Laufzeit")
    def _():
        details = system_info.system_details()
        return f"{details['os_name']} · {details['hostname']} · {details['laufzeit']}"

    @pruefe("Akku-Erkennung")
    def _():
        akku = system_info.akku_info()
        if akku is None:
            return "kein Akku -> GPU-Temperatur-Kachel wird angezeigt (Desktop)"
        return (
            f"{akku['percent']:.0f} %, "
            + ("Netzbetrieb" if akku["netzbetrieb"] else "Akkubetrieb")
            + " -> Akku-Kachel ersetzt GPU-Kachel (Laptop)"
        )

    # ------------------------------------------------------------------
    print()
    print("--- 4. Hardware-Sensoren (LibreHardwareMonitor) " + "-" * 18)

    from app import hardware

    @pruefe("DLL-Datei vorhanden", warn_statt_fehler=True)
    def _():
        assert os.path.isfile(hardware.DLL_PFAD), f"nicht gefunden: {hardware.DLL_PFAD}"
        groesse_kb = os.path.getsize(hardware.DLL_PFAD) / 1024
        return f"{hardware.DLL_PFAD} ({groesse_kb:.0f} KB)"

    @pruefe("DLL laden + Computer öffnen", warn_statt_fehler=True)
    def _():
        assert hardware.sensoren_verfuegbar(), (
            hardware.init_fehler()
            or "unbekannter Grund -> Kacheln zeigen 'n/a' (dokumentierter Fallback)"
        )
        return "Computer-Objekt geöffnet"

    @pruefe("Gefundene Temperatursensoren", warn_statt_fehler=True)
    def _():
        sensoren = hardware.sensor_uebersicht()
        assert sensoren, "Liste leer (DLL nicht geladen oder keine Sensoren gemeldet)"
        print()
        for hw_typ, name, wert in sensoren:
            print(f"           · {hw_typ:12s} {name:28s} {wert}")
        return f"{len(sensoren)} Temperatursensoren"

    @pruefe("CPU-Temperatur lesen", warn_statt_fehler=True)
    def _():
        wert = hardware.get_cpu_temp()
        assert wert is not None, "kein Sensorwert (ohne Admin normal) -> Kachel zeigt 'n/a'"
        return f"{wert:.1f} °C"

    @pruefe("GPU-Temperatur lesen", warn_statt_fehler=True)
    def _():
        wert = hardware.get_gpu_temp()
        assert wert is not None, "kein Sensorwert -> Kachel zeigt 'n/a'"
        return f"{wert:.1f} °C"

    # ------------------------------------------------------------------
    print()
    print("--- 5. Reinigungs-Routine (NUR Analyse, kein Löschen) " + "-" * 12)

    from app import cleaning

    for kategorie in cleaning._kategorien_erzeugen():

        @pruefe(f"Analyse: {kategorie.name}", warn_statt_fehler=True)
        def _(kategorie=kategorie):
            groesse = cleaning.analysiere_kategorie(kategorie)
            return cleaning.formatiere_groesse(groesse)

    # ------------------------------------------------------------------
    print()
    print("--- 6. GUI-Rauchtest (Fenster 3 Sekunden, dann automatisch zu) ---")

    @pruefe("Dashboard öffnen, 3 s laufen lassen, schließen")
    def _():
        from app.dashboard import Dashboard
        from main import _pruefe_admin_rechte

        fenster = Dashboard(ist_admin=_pruefe_admin_rechte())
        fenster.after(3000, fenster._beim_schliessen)
        fenster.mainloop()
        return "gestartet und sauber beendet"

    # ------------------------------------------------------------------
    print()
    print("=" * 72)
    anzahl_ok = sum(1 for s, _, _ in ERGEBNISSE if s == "OK")
    anzahl_warn = sum(1 for s, _, _ in ERGEBNISSE if s == "WARN")
    anzahl_fehler = sum(1 for s, _, _ in ERGEBNISSE if s == "FEHLER")
    print(
        f"ERGEBNIS: {anzahl_ok} OK · {anzahl_warn} Warnungen · {anzahl_fehler} Fehler"
    )
    if anzahl_warn:
        print(
            "Warnungen sind meist erwartete Fallbacks (fehlende DLL, keine\n"
            "Adminrechte) - die App läuft damit, zeigt aber 'n/a' bzw. graue Buttons."
        )
    print("=" * 72)
    return 1 if anzahl_fehler else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Auch der Selbsttest selbst soll nie kommentarlos sterben.
        traceback.print_exc()
        sys.exit(2)
