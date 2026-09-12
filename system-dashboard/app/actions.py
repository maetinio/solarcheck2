"""
actions.py - Zentrale, abgesicherte Helfer für alle Windows-Aktionen.

Jede Funktion gibt ein Tupel (erfolg: bool, meldung: str) zurück, das die
GUI als Toast/Statusmeldung anzeigen kann (Erfolg blau, Warnung gelb,
Fehler lila). Kein Aufruf darf jemals eine unbehandelte Ausnahme werfen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Sequence, Union

# Unterdrückt das Aufpoppen eines Konsolenfensters bei externen
# Bordmittel-Aufrufen. Unter Nicht-Windows-Systemen (z. B. beim
# Entwickeln/Testen) existiert das Flag nicht - dann einfach 0 verwenden.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Gegenstück für die wenigen Fälle, in denen ein Konsolenfenster erwünscht
# ist (siehe run_sichtbar).
CREATE_NEW_CONSOLE = 0x00000010 if sys.platform == "win32" else 0

# Flags für SHEmptyRecycleBinW: keine Rückfrage, kein Fortschritts-Dialog,
# kein Sound - die Bestätigung übernimmt unser eigener Dialog.
_SHERB_NOCONFIRMATION = 0x00000001
_SHERB_NOPROGRESSUI = 0x00000002
_SHERB_NOSOUND = 0x00000004


def _ist_windows() -> bool:
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Prozesse / Bordmittel starten
# ---------------------------------------------------------------------------


def run(befehl: Union[str, Sequence[str]]) -> tuple[bool, str]:
    """Startet ein Windows-Bordmittel ohne Konsolenfenster.

    Nimmt entweder einen fertigen Kommandozeilen-String oder eine Liste
    von Argumenten entgegen. Fehler werden abgefangen und als Meldung
    zurückgegeben statt die App zu gefährden.
    """
    try:
        subprocess.Popen(
            befehl,
            shell=isinstance(befehl, str),
            creationflags=CREATE_NO_WINDOW,
        )
        return True, "Befehl wurde gestartet."
    except Exception as fehler:
        return False, f"Befehl konnte nicht gestartet werden: {fehler}"


def run_und_warten(befehl: Union[str, Sequence[str]], timeout: float = 60.0) -> tuple[bool, str]:
    """Startet ein Bordmittel und wartet auf dessen Ende (z. B. net stop).

    Wird für die Reinigungs-Routine gebraucht, wenn die Reihenfolge der
    Schritte wichtig ist (Dienst stoppen -> Ordner leeren -> Dienst starten).
    """
    try:
        ergebnis = subprocess.run(
            befehl,
            shell=isinstance(befehl, str),
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            timeout=timeout,
        )
        if ergebnis.returncode == 0:
            return True, "Befehl erfolgreich ausgeführt."
        return False, f"Befehl endete mit Code {ergebnis.returncode}."
    except Exception as fehler:
        return False, f"Befehl fehlgeschlagen: {fehler}"


def run_sichtbar(befehl: Union[str, Sequence[str]]) -> tuple[bool, str]:
    """Startet ein Kommando MIT sichtbarem Konsolenfenster.

    Bewusste Ausnahme von der Regel "keine Konsolenfenster": Bei lange
    laufenden Vorgängen wie "winget upgrade --all" (mehrere Minuten, mit
    Fortschrittsanzeige und möglichen Rückfragen) wäre ein unsichtbarer
    Hintergrundprozess für den Nutzer nicht nachvollziehbar.
    """
    try:
        subprocess.Popen(befehl, creationflags=CREATE_NEW_CONSOLE)
        return True, "Vorgang wurde in einem Konsolenfenster gestartet."
    except Exception as fehler:
        return False, f"Vorgang konnte nicht gestartet werden: {fehler}"


def open_settings(uri: str, fallback_befehl: Optional[str] = None) -> tuple[bool, str]:
    """Öffnet einen Windows-Settings-Link (z. B. "ms-settings:network-status").

    Schlägt der ms-settings-Link fehl, wird - falls angegeben - ein
    klassisches Bordmittel als Fallback gestartet (z. B. "control ncpa.cpl").
    """
    try:
        os.startfile(uri)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        return True, "Einstellungen geöffnet."
    except Exception:
        if fallback_befehl:
            erfolg, _ = run(fallback_befehl)
            if erfolg:
                return True, "Einstellungen (klassisch) geöffnet."
        return False, "Einstellungen konnten nicht geöffnet werden."


def shell_properties(pfad: str) -> tuple[bool, str]:
    """Öffnet den Windows-"Eigenschaften"-Dialog für einen Pfad via ShellExecuteW."""
    if not _ist_windows():
        return False, "Eigenschaften-Dialog ist nur unter Windows verfügbar."
    try:
        import ctypes

        ergebnis_code = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "properties", pfad, None, None, 1
        )
        if ergebnis_code <= 32:
            return False, f"Eigenschaften-Dialog für {pfad} konnte nicht geöffnet werden."
        return True, f"Eigenschaften-Dialog für {pfad} geöffnet."
    except Exception as fehler:
        return False, f"Fehler beim Öffnen der Eigenschaften: {fehler}"


def shell_open(pfad: str) -> tuple[bool, str]:
    """Öffnet einen Ordner/Pfad im Explorer (oder Standard-Anwendung)."""
    try:
        os.startfile(pfad)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        return True, f"{pfad} geöffnet."
    except Exception as fehler:
        return False, f"{pfad} konnte nicht geöffnet werden: {fehler}"


def restart_as_admin() -> tuple[bool, str]:
    """Startet die App mit Adminrechten neu (UAC-Abfrage) und beendet diese Instanz.

    Rückgabe False bedeutet: Neustart nicht möglich (z. B. UAC abgelehnt),
    die aktuelle Instanz läuft weiter.
    """
    if not _ist_windows():
        return False, "Elevation ist nur unter Windows möglich."
    try:
        import ctypes

        # Bei gefrorener .exe (PyInstaller) ist sys.executable die App selbst,
        # im Skript-Betrieb muss main.py als Argument mitgegeben werden.
        if getattr(sys, "frozen", False):
            programm, argumente = sys.executable, ""
        else:
            programm = sys.executable
            skript = os.path.abspath(sys.argv[0])
            argumente = f'"{skript}"'

        ergebnis_code = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", programm, argumente, None, 1
        )
        if ergebnis_code <= 32:
            return False, "Neustart als Administrator wurde abgebrochen."
        # Erfolgreich gestartet: aktuelle Instanz beenden.
        os._exit(0)
    except Exception as fehler:
        return False, f"Neustart als Administrator fehlgeschlagen: {fehler}"


# ---------------------------------------------------------------------------
# Papierkorb (ctypes / Shell-API)
# ---------------------------------------------------------------------------


def recycle_bin_size() -> Optional[tuple[int, int]]:
    """Liefert (Größe in Bytes, Anzahl Objekte) des Papierkorbs, oder None."""
    if not _ist_windows():
        return None
    try:
        import ctypes

        class SHQUERYRBINFO(ctypes.Structure):
            # Struktur laut Windows-SDK: DWORD + 2x __int64.
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong),
            ]

        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        ergebnis_code = ctypes.windll.shell32.SHQueryRecycleBinW(  # type: ignore[attr-defined]
            None, ctypes.byref(info)
        )
        if ergebnis_code != 0:
            return None
        return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        return None


def empty_recycle_bin() -> tuple[bool, str]:
    """Leert den Papierkorb ohne Windows-Dialog und ohne Sound."""
    if not _ist_windows():
        return False, "Papierkorb leeren ist nur unter Windows möglich."
    try:
        import ctypes

        flags = _SHERB_NOCONFIRMATION | _SHERB_NOPROGRESSUI | _SHERB_NOSOUND
        ergebnis_code = ctypes.windll.shell32.SHEmptyRecycleBinW(  # type: ignore[attr-defined]
            None, None, flags
        )
        if ergebnis_code == 0:
            return True, "Papierkorb wurde geleert."
        # Ein bereits leerer Papierkorb liefert einen Fehlercode - das ist
        # aus Nutzersicht kein Fehler.
        return True, "Papierkorb war bereits leer."
    except Exception as fehler:
        return False, f"Papierkorb konnte nicht geleert werden: {fehler}"


# ---------------------------------------------------------------------------
# Arbeitsspeicher: Standby-Liste leeren (Admin, undokumentierte NT-API)
# ---------------------------------------------------------------------------


def free_standby_memory() -> tuple[bool, str]:
    """Leert die Standby-Liste des Speicher-Managers (benötigt Adminrechte).

    Nutzt NtSetSystemInformation(SystemMemoryListInformation) mit dem
    Kommando MemoryPurgeStandbyList. Dafür muss zunächst das Privileg
    "SeProfileSingleProcessPrivilege" im eigenen Token aktiviert werden.
    Schlägt irgendein Schritt fehl, wird sauber eine Meldung geliefert.
    """
    if not _ist_windows():
        return False, "Speicher freigeben ist nur unter Windows möglich."
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        SE_PRIVILEGE_ENABLED = 0x00000002
        TOKEN_ADJUST_PRIVILEGES = 0x0020
        TOKEN_QUERY = 0x0008
        SYSTEM_MEMORY_LIST_INFORMATION = 80
        MEMORY_PURGE_STANDBY_LIST = 4

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class LUID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [
                ("PrivilegeCount", wintypes.DWORD),
                ("Privileges", LUID_AND_ATTRIBUTES * 1),
            ]

        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ntdll = ctypes.windll.ntdll  # type: ignore[attr-defined]

        # 1) Privileg "SeProfileSingleProcessPrivilege" aktivieren.
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(),
            TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
            ctypes.byref(token),
        ):
            return False, "Prozess-Token konnte nicht geöffnet werden."

        try:
            luid = LUID()
            if not advapi32.LookupPrivilegeValueW(
                None, "SeProfileSingleProcessPrivilege", ctypes.byref(luid)
            ):
                return False, "Benötigtes Privileg wurde nicht gefunden."

            privilegien = TOKEN_PRIVILEGES()
            privilegien.PrivilegeCount = 1
            privilegien.Privileges[0].Luid = luid
            privilegien.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
            advapi32.AdjustTokenPrivileges(
                token, False, ctypes.byref(privilegien), 0, None, None
            )
            if kernel32.GetLastError() != 0:
                return False, "Privileg konnte nicht aktiviert werden (Adminrechte nötig)."
        finally:
            kernel32.CloseHandle(token)

        # 2) Standby-Liste über die NT-API leeren.
        kommando = ctypes.c_int(MEMORY_PURGE_STANDBY_LIST)
        status = ntdll.NtSetSystemInformation(
            SYSTEM_MEMORY_LIST_INFORMATION,
            ctypes.byref(kommando),
            ctypes.sizeof(kommando),
        )
        if status != 0:
            return False, f"Standby-Liste konnte nicht geleert werden (Status 0x{status & 0xFFFFFFFF:08X})."
        return True, "Standby-Speicher wurde freigegeben."
    except Exception as fehler:
        return False, f"Speicher freigeben fehlgeschlagen: {fehler}"


# ---------------------------------------------------------------------------
# Temporäre Dateien löschen
# ---------------------------------------------------------------------------


def delete_temp_files(ordner: Optional[str] = None) -> tuple[bool, str]:
    """Löscht den Inhalt von %TEMP% (oder eines angegebenen Ordners).

    Gesperrte oder gerade benutzte Dateien werden übersprungen, nicht
    abgebrochen. Am Ende gibt es eine Zusammenfassung mit freigegebenem
    Speicher und Anzahl übersprungener Einträge.
    """
    ziel_ordner = ordner or os.environ.get("TEMP", "")
    if not ziel_ordner or not os.path.isdir(ziel_ordner):
        return False, "Temp-Ordner wurde nicht gefunden."

    freigegeben, geloescht, uebersprungen = leere_ordner_inhalt(ziel_ordner)
    mb = freigegeben / (1024 ** 2)
    return True, (
        f"{geloescht} Einträge gelöscht ({mb:.1f} MB frei), "
        f"{uebersprungen} übersprungen."
    )


def leere_ordner_inhalt(ordner: str) -> tuple[int, int, int]:
    """Löscht defensiv den Inhalt eines Ordners (nicht den Ordner selbst).

    Rückgabe: (freigegebene Bytes, gelöschte Einträge, übersprungene Einträge).
    Jede Datei und jeder Ordner ist einzeln abgesichert - existiert der
    Pfad nicht oder ist etwas gesperrt, wird still übersprungen.
    """
    import shutil

    freigegeben = 0
    geloescht = 0
    uebersprungen = 0

    try:
        eintraege = list(os.scandir(ordner))
    except Exception:
        return 0, 0, 0

    for eintrag in eintraege:
        try:
            if eintrag.is_file(follow_symlinks=False) or eintrag.is_symlink():
                groesse = 0
                try:
                    groesse = eintrag.stat(follow_symlinks=False).st_size
                except Exception:
                    pass
                os.remove(eintrag.path)
                freigegeben += groesse
                geloescht += 1
            elif eintrag.is_dir(follow_symlinks=False):
                groesse = _ordner_groesse_leise(eintrag.path)
                shutil.rmtree(eintrag.path)
                freigegeben += groesse
                geloescht += 1
        except Exception:
            uebersprungen += 1

    return freigegeben, geloescht, uebersprungen


def _ordner_groesse_leise(ordner: str) -> int:
    """Summiert die Dateigrößen eines Ordners, ohne bei Fehlern zu scheitern."""
    summe = 0
    try:
        for wurzel, _, dateien in os.walk(ordner):
            for datei in dateien:
                try:
                    summe += os.path.getsize(os.path.join(wurzel, datei))
                except Exception:
                    pass
    except Exception:
        pass
    return summe


# ---------------------------------------------------------------------------
# Wartung: App-Updates (winget) und Viren-Scan (MRT)
# ---------------------------------------------------------------------------


def winget_upgrade_alle() -> tuple[bool, str]:
    """Aktualisiert alle über winget verwalteten Programme.

    Läuft bewusst in einem sichtbaren Konsolenfenster: Der Vorgang dauert
    mehrere Minuten und zeigt dort Fortschritt und Ergebnis je Paket.
    "cmd /k" hält das Fenster nach dem Durchlauf offen, damit die
    Zusammenfassung lesbar bleibt.
    """
    if not _ist_windows():
        return False, "winget ist nur unter Windows verfügbar."

    import shutil

    if shutil.which("winget") is None:
        return False, "winget wurde nicht gefunden (App-Installer fehlt)."

    erfolg, meldung = run_sichtbar(
        "cmd /k winget upgrade --all "
        "--accept-source-agreements --accept-package-agreements"
    )
    if erfolg:
        return True, "App-Updates laufen im Konsolenfenster."
    return erfolg, meldung


def mrt_starten() -> tuple[bool, str]:
    """Startet das Windows-Tool zum Entfernen bösartiger Software (MRT).

    MRT bringt einen eigenen Assistenten mit; der Scan wird dort gestartet
    und kann jederzeit abgebrochen werden.
    """
    if not _ist_windows():
        return False, "MRT ist nur unter Windows verfügbar."

    pfad = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "MRT.exe"
    )
    if not os.path.isfile(pfad):
        return False, "MRT.exe wurde auf diesem System nicht gefunden."

    erfolg, meldung = run([pfad])
    if erfolg:
        return True, "Tool zum Entfernen bösartiger Software wurde gestartet."
    return erfolg, meldung
