"""
system_info.py - Zentrale Sammelstelle für ALLE Datenabfragen.

Jede Funktion ist einzeln gegen Fehler abgesichert und liefert im
Fehlerfall None bzw. ein leeres Ergebnis, statt eine Ausnahme nach oben
zu werfen. So kann eine einzelne fehlschlagende Abfrage niemals eine
ganze Kachel oder die App zum Absturz bringen.

Teure Abfragen (Temp-Ordner-Größe, Autostart, Windows-Update-Status)
werden über einen kleinen TTL-Cache nur alle paar Zyklen neu berechnet,
damit der 2-Sekunden-Refresh flüssig bleibt.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional, TypedDict

import psutil

from . import actions, hardware

# ---------------------------------------------------------------------------
# Verlaufs-Puffer (für Ø/Spitze der CPU und die Temperatur-Verlaufsgraphen)
# ---------------------------------------------------------------------------

# Bei ~2 s Abtastintervall entsprechen 300 Einträge rund 10 Minuten Verlauf.
VERLAUF_CPU: deque[tuple[float, float]] = deque(maxlen=300)
VERLAUF_CPU_TEMP: deque[tuple[float, float]] = deque(maxlen=300)
VERLAUF_GPU_TEMP: deque[tuple[float, float]] = deque(maxlen=300)

# Merker für die Netzwerk-Raten (Delta zweier Messungen).
_letzte_netz_messung: Optional[tuple[float, int, int]] = None

# TTL-Cache für teure Abfragen: schluessel -> (zeitpunkt, wert).
_cache: dict[str, tuple[float, object]] = {}

# Zustand der winget-Messung. winget braucht je nach Netzverbindung mehrere
# Sekunden, darf den 2-Sekunden-Zyklus also nicht blockieren - die Messung
# läuft daher in einem eigenen Thread, snapshot() liest nur das Ergebnis.
WINGET_MESSINTERVALL_SEKUNDEN = 1800.0
_winget_lock = threading.Lock()
_winget_stand: dict = {"anzahl": None, "zeitpunkt": 0.0, "laeuft": False}


def _gecacht(schluessel: str, ttl_sekunden: float, berechnen):
    """Liefert den gecachten Wert oder berechnet ihn neu, wenn er abgelaufen ist."""
    jetzt = time.time()
    eintrag = _cache.get(schluessel)
    if eintrag is not None and jetzt - eintrag[0] < ttl_sekunden:
        return eintrag[1]
    try:
        wert = berechnen()
    except Exception:
        wert = None
    _cache[schluessel] = (jetzt, wert)
    return wert


def cpu_aufwaermen() -> None:
    """Erste cpu_percent-Messung "aufwärmen" (der erste Aufruf liefert 0.0)."""
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Laufwerke
# ---------------------------------------------------------------------------


class DiskInfo(TypedDict):
    """Ergebnis einer Laufwerks-Abfrage in GB und Prozent."""

    laufwerk: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


def disk_usage(laufwerk_pfad: str) -> Optional[DiskInfo]:
    """Liefert Belegung eines Laufwerks (z. B. "C:\\") in GB, oder None."""
    try:
        nutzung = psutil.disk_usage(laufwerk_pfad)
        bytes_pro_gb = 1024 ** 3
        return DiskInfo(
            laufwerk=laufwerk_pfad,
            total_gb=nutzung.total / bytes_pro_gb,
            used_gb=nutzung.used / bytes_pro_gb,
            free_gb=nutzung.free / bytes_pro_gb,
            percent=nutzung.percent,
        )
    except Exception:
        return None


def weitere_laufwerke() -> list[DiskInfo]:
    """Alle festen Laufwerke außer C: (keine CD-ROMs, keine Netzlaufwerke)."""
    ergebnis: list[DiskInfo] = []
    try:
        for partition in psutil.disk_partitions(all=False):
            try:
                mount = partition.mountpoint
                # Nur echte Windows-Laufwerksbuchstaben außer C: berücksichtigen.
                if not mount or mount.upper().startswith("C:"):
                    continue
                if "cdrom" in partition.opts.lower() or partition.fstype == "":
                    continue
                info = disk_usage(mount)
                if info is not None:
                    ergebnis.append(info)
            except Exception:
                continue
    except Exception:
        pass
    return ergebnis


# ---------------------------------------------------------------------------
# RAM / CPU
# ---------------------------------------------------------------------------


def ram_info() -> Optional[dict]:
    """Belegter/gesamter Arbeitsspeicher in GB plus Prozent."""
    try:
        speicher = psutil.virtual_memory()
        bytes_pro_gb = 1024 ** 3
        return {
            "total_gb": speicher.total / bytes_pro_gb,
            "used_gb": speicher.used / bytes_pro_gb,
            "percent": speicher.percent,
        }
    except Exception:
        return None


def cpu_info() -> Optional[dict]:
    """CPU-Auslastung (nicht blockierend) inkl. Ø/Spitze der letzten 60 s."""
    try:
        prozent = psutil.cpu_percent(interval=None)
        jetzt = time.time()
        VERLAUF_CPU.append((jetzt, prozent))

        # Ø und Spitze über das 60-Sekunden-Fenster des Verlaufs-Puffers.
        fenster = [wert for (zeit, wert) in VERLAUF_CPU if jetzt - zeit <= 60.0]
        durchschnitt = sum(fenster) / len(fenster) if fenster else prozent
        spitze = max(fenster) if fenster else prozent

        return {
            "percent": prozent,
            "kerne": psutil.cpu_count(logical=True) or 0,
            "avg60": durchschnitt,
            "peak60": spitze,
        }
    except Exception:
        return None


def top_cpu_prozesse(anzahl: int = 5) -> list[tuple[str, float]]:
    """Die CPU-hungrigsten Prozesse. Blockiert kurz (~0,4 s) für die Messung.

    Wird nur auf Button-Klick (in einem Hintergrund-Thread) aufgerufen,
    nicht im Refresh-Zyklus.
    """
    ergebnis: list[tuple[str, float]] = []
    try:
        # Erster Durchlauf primt die per-Prozess-Messung, ...
        for prozess in psutil.process_iter(["name"]):
            try:
                prozess.cpu_percent(interval=None)
            except Exception:
                continue
        time.sleep(0.4)
        # ... der zweite liefert verwertbare Prozentwerte.
        kern_anzahl = psutil.cpu_count(logical=True) or 1
        for prozess in psutil.process_iter(["name"]):
            try:
                wert = prozess.cpu_percent(interval=None) / kern_anzahl
                name = prozess.info.get("name") or f"PID {prozess.pid}"
                ergebnis.append((name, wert))
            except Exception:
                continue
        ergebnis.sort(key=lambda eintrag: eintrag[1], reverse=True)
    except Exception:
        pass
    return ergebnis[:anzahl]


# ---------------------------------------------------------------------------
# Temperaturen (LibreHardwareMonitor via hardware.py)
# ---------------------------------------------------------------------------


def temperaturen() -> dict:
    """CPU-/GPU-Temperatur inkl. Verlaufs-Pflege. None = kein Sensor."""
    cpu_temp = None
    gpu_temp = None
    try:
        cpu_temp = hardware.get_cpu_temp()
        gpu_temp = hardware.get_gpu_temp()
        jetzt = time.time()
        if cpu_temp is not None:
            VERLAUF_CPU_TEMP.append((jetzt, cpu_temp))
        if gpu_temp is not None:
            VERLAUF_GPU_TEMP.append((jetzt, gpu_temp))
    except Exception:
        pass
    return {"cpu": cpu_temp, "gpu": gpu_temp}


# ---------------------------------------------------------------------------
# Netzwerk
# ---------------------------------------------------------------------------


def netzwerk_info() -> Optional[dict]:
    """Down-/Upload-Rate in MB/s aus dem Delta zweier Messungen + lokale IP."""
    global _letzte_netz_messung
    try:
        zaehler = psutil.net_io_counters()
        jetzt = time.time()

        down_mbs = 0.0
        up_mbs = 0.0
        if _letzte_netz_messung is not None:
            damals, empfangen_alt, gesendet_alt = _letzte_netz_messung
            dauer = max(0.001, jetzt - damals)
            down_mbs = (zaehler.bytes_recv - empfangen_alt) / dauer / (1024 ** 2)
            up_mbs = (zaehler.bytes_sent - gesendet_alt) / dauer / (1024 ** 2)
        _letzte_netz_messung = (jetzt, zaehler.bytes_recv, zaehler.bytes_sent)

        return {
            "down_mbs": max(0.0, down_mbs),
            "up_mbs": max(0.0, up_mbs),
            "ip": _gecacht("lokale_ip", 30.0, lokale_ip) or "—",
        }
    except Exception:
        return None


def lokale_ip() -> Optional[str]:
    """Ermittelt die aktive lokale IP über eine UDP-"Verbindung" zu 8.8.8.8.

    Es werden keine Daten gesendet - connect() auf einem UDP-Socket wählt
    nur die passende ausgehende Schnittstelle aus. Fällt das fehl, wird
    die Hostnamen-IP als Ersatz geliefert.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Autostart (Registry + Autostart-Ordner)
# ---------------------------------------------------------------------------


def autostart_eintraege() -> list[tuple[str, str]]:
    """Alle Autostart-Einträge als Liste (Name, Pfad/Kommando).

    Quellen: Run-Schlüssel in HKCU und HKLM sowie die beiden
    Autostart-Ordner des Benutzers und aller Benutzer.
    """
    eintraege: list[tuple[str, str]] = []

    if sys.platform == "win32":
        try:
            import winreg

            registry_quellen = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ]
            for wurzel, pfad in registry_quellen:
                try:
                    with winreg.OpenKey(wurzel, pfad) as schluessel:
                        index = 0
                        while True:
                            try:
                                name, wert, _ = winreg.EnumValue(schluessel, index)
                                eintraege.append((str(name), str(wert)))
                                index += 1
                            except OSError:
                                break
                except Exception:
                    continue
        except Exception:
            pass

    # Autostart-Ordner: "shell:startup" und "shell:common startup".
    ordner_quellen = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"),
    ]
    for ordner in ordner_quellen:
        try:
            if not os.path.isdir(ordner):
                continue
            for eintrag in os.scandir(ordner):
                if eintrag.is_file() and eintrag.name.lower() != "desktop.ini":
                    eintraege.append((eintrag.name, eintrag.path))
        except Exception:
            continue

    return eintraege


# ---------------------------------------------------------------------------
# Papierkorb & temporäre Dateien
# ---------------------------------------------------------------------------


def papierkorb_info() -> Optional[dict]:
    """Größe und Objektanzahl des Papierkorbs (über Shell-API)."""
    ergebnis = actions.recycle_bin_size()
    if ergebnis is None:
        return None
    groesse, anzahl = ergebnis
    return {"bytes": groesse, "anzahl": anzahl}


def temp_ordner_pfade() -> list[str]:
    """Die beiden Temp-Quellen: %TEMP% des Benutzers und C:\\Windows\\Temp."""
    pfade = []
    benutzer_temp = os.environ.get("TEMP")
    if benutzer_temp:
        pfade.append(benutzer_temp)
    windows_temp = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")
    pfade.append(windows_temp)
    return pfade


def temp_dateien_groesse() -> int:
    """Gesamtgröße aller Temp-Ordner in Bytes (unlesbare Teile übersprungen)."""
    summe = 0
    for pfad in temp_ordner_pfade():
        try:
            if os.path.isdir(pfad):
                summe += actions._ordner_groesse_leise(pfad)
        except Exception:
            pass
    return summe


# ---------------------------------------------------------------------------
# Windows-Update & System
# ---------------------------------------------------------------------------


def windows_update_status() -> dict:
    """Letzte Update-Suche aus der Registry, soweit ohne Admin lesbar.

    Rückgabe: {"text": ..., "ok": bool}. ok=False bedeutet "Aktion nötig"
    (gelber Statuspunkt), z. B. wenn die letzte Suche lange her ist.
    """
    if sys.platform != "win32":
        return {"text": "Status im Einstellungen-Fenster prüfen", "ok": True}

    try:
        import winreg

        pfad = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate"
            r"\Auto Update\Results\Detect"
        )
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pfad) as schluessel:
            wert, _ = winreg.QueryValueEx(schluessel, "LastSuccessTime")

        # Format in der Registry: "2026-08-14 03:15:00" (UTC).
        zeitpunkt = datetime.strptime(str(wert), "%Y-%m-%d %H:%M:%S")
        alter_tage = (datetime.utcnow() - zeitpunkt).days
        datum_text = zeitpunkt.strftime("%d.%m.%Y")
        return {
            "text": f"Letzte Suche: {datum_text}",
            "ok": alter_tage <= 7,
        }
    except Exception:
        return {"text": "Status im Einstellungen-Fenster prüfen", "ok": True}


def system_details() -> dict:
    """OS-Name, Rechnername und formatierte Laufzeit seit dem letzten Start."""
    os_name = "Unbekanntes System"
    try:
        if sys.platform == "win32":
            edition = ""
            try:
                edition = platform.win32_edition() or ""
            except Exception:
                pass
            os_name = f"Windows {platform.release()} {edition}".strip()
        else:
            os_name = f"{platform.system()} {platform.release()}"
    except Exception:
        pass

    hostname = "—"
    try:
        hostname = socket.gethostname()
    except Exception:
        pass

    laufzeit_text = "—"
    try:
        sekunden = max(0, int(time.time() - psutil.boot_time()))
        tage, rest = divmod(sekunden, 86400)
        stunden, rest = divmod(rest, 3600)
        minuten = rest // 60
        laufzeit_text = f"{tage} T · {stunden} Std · {minuten} Min"
    except Exception:
        pass

    return {"os_name": os_name, "hostname": hostname, "laufzeit": laufzeit_text}


def akku_info() -> Optional[dict]:
    """Akku-Ladestand, Restzeit und Netzbetrieb - None auf Desktop-PCs."""
    try:
        akku = psutil.sensors_battery()
        if akku is None:
            return None

        restzeit_text = "—"
        if akku.power_plugged:
            restzeit_text = "am Netz"
        elif akku.secsleft not in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED, None):
            stunden, rest = divmod(int(akku.secsleft), 3600)
            minuten = rest // 60
            restzeit_text = f"noch {stunden} Std {minuten} Min"

        return {
            "percent": float(akku.percent),
            "netzbetrieb": bool(akku.power_plugged),
            "restzeit": restzeit_text,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Wartung: App-Updates (winget) und Viren-Scan (MRT)
# ---------------------------------------------------------------------------


def winget_pfad() -> Optional[str]:
    """Pfad zu winget.exe, oder None wenn der App-Installer fehlt."""
    try:
        return shutil.which("winget")
    except Exception:
        return None


def _winget_tabelle_zaehlen(ausgabe: str) -> int:
    """Zählt die Paketzeilen in der Tabellenausgabe von "winget upgrade".

    winget gibt eine Kopfzeile, eine Strich-Trennlinie und danach je Paket
    eine Zeile aus (Name, Id, Version, Verfügbar, Quelle). Abschlusszeilen
    wie "3 Upgrades verfügbar." haben deutlich weniger Spalten und werden
    dadurch zuverlässig aussortiert - unabhängig von der Sprache.
    """
    zeilen = ausgabe.splitlines()

    start = None
    for index, zeile in enumerate(zeilen):
        inhalt = zeile.strip()
        # Trennlinie unter der Kopfzeile: ausschließlich Striche.
        if len(inhalt) >= 10 and set(inhalt) == {"-"}:
            start = index + 1
            break
    if start is None:
        return 0

    anzahl = 0
    for zeile in zeilen[start:]:
        inhalt = zeile.strip()
        if not inhalt:
            continue
        spalten = [teil for teil in re.split(r"\s{2,}", inhalt) if teil]
        if len(spalten) >= 4:
            anzahl += 1
    return anzahl


def winget_messen() -> Optional[int]:
    """Ermittelt blockierend, wie viele Programme aktualisiert werden können.

    Rückgabe None bedeutet: winget fehlt oder der Aufruf schlug fehl.
    Diese Funktion braucht mehrere Sekunden - im Dashboard wird sie daher
    ausschließlich über winget_messung_anstossen() im Thread aufgerufen.
    """
    pfad = winget_pfad()
    if pfad is None:
        return None
    try:
        ergebnis = subprocess.run(
            [pfad, "upgrade", "--accept-source-agreements"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=actions.CREATE_NO_WINDOW,
            timeout=180,
        )
    except Exception:
        return None
    return _winget_tabelle_zaehlen(ergebnis.stdout or "")


def winget_messung_anstossen() -> None:
    """Startet bei Bedarf eine winget-Messung in einem eigenen Thread."""
    jetzt = time.time()
    with _winget_lock:
        if _winget_stand["laeuft"]:
            return
        if jetzt - _winget_stand["zeitpunkt"] < WINGET_MESSINTERVALL_SEKUNDEN:
            return
        _winget_stand["laeuft"] = True

    def messen() -> None:
        anzahl = winget_messen()
        with _winget_lock:
            _winget_stand["anzahl"] = anzahl
            _winget_stand["zeitpunkt"] = time.time()
            _winget_stand["laeuft"] = False

    threading.Thread(target=messen, daemon=True).start()


def winget_neu_messen() -> None:
    """Erzwingt beim nächsten Zyklus eine frische winget-Messung."""
    with _winget_lock:
        _winget_stand["zeitpunkt"] = 0.0


def mrt_letzter_scan() -> Optional[str]:
    """Datum des letzten MRT-Laufs, gelesen aus dessen Protokolldatei."""
    try:
        pfad = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "debug", "mrt.log"
        )
        if not os.path.isfile(pfad):
            return None
        return datetime.fromtimestamp(os.path.getmtime(pfad)).strftime("%d.%m.%Y")
    except Exception:
        return None


def wartung_info() -> dict:
    """Sammelt Wartungsdaten: offene App-Updates und letzter MRT-Scan."""
    winget_messung_anstossen()
    with _winget_lock:
        anzahl = _winget_stand["anzahl"]
        laeuft = _winget_stand["laeuft"]
        gemessen = _winget_stand["zeitpunkt"] > 0.0
    return {
        "winget_anzahl": anzahl,
        "winget_laeuft": laeuft,
        "winget_gemessen": gemessen,
        "winget_da": bool(_gecacht("winget_da", 300.0, winget_pfad)),
        "mrt_datum": _gecacht("mrt_datum", 300.0, mrt_letzter_scan),
    }


# ---------------------------------------------------------------------------
# Gesamt-Momentaufnahme (wird alle ~2 s vom Hintergrund-Thread aufgerufen)
# ---------------------------------------------------------------------------


def snapshot() -> dict:
    """Erfasst einen kompletten Satz aller Kachel-Werte.

    Schnelle Werte (CPU, RAM, Netz, Laufwerke) werden jedes Mal frisch
    gelesen; teure Abfragen laufen über den TTL-Cache und werden nur
    alle 15-60 Sekunden tatsächlich neu berechnet.
    """
    ergebnis: dict = {}
    ergebnis["disk_c"] = disk_usage("C:\\")
    ergebnis["weitere_disks"] = _gecacht("weitere_disks", 10.0, weitere_laufwerke) or []
    ergebnis["ram"] = ram_info()
    ergebnis["cpu"] = cpu_info()
    ergebnis["temps"] = temperaturen()
    ergebnis["netz"] = netzwerk_info()
    ergebnis["autostart"] = _gecacht("autostart", 30.0, autostart_eintraege) or []
    ergebnis["papierkorb"] = _gecacht("papierkorb", 15.0, papierkorb_info)
    ergebnis["temp_bytes"] = _gecacht("temp_bytes", 60.0, temp_dateien_groesse)
    ergebnis["update"] = _gecacht("update", 300.0, windows_update_status) or {
        "text": "Status im Einstellungen-Fenster prüfen",
        "ok": True,
    }
    ergebnis["system"] = system_details()
    ergebnis["akku"] = akku_info()
    ergebnis["wartung"] = wartung_info()
    return ergebnis


def cache_leeren() -> None:
    """Erzwingt beim nächsten Snapshot eine komplette Neuberechnung.

    Wird vom "↻ Aktualisieren"-Button genutzt, damit wirklich alle
    Kacheln (auch die gecachten) sofort neue Werte bekommen.
    """
    _cache.clear()
    winget_neu_messen()
