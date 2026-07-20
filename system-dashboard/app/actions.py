"""
actions.py - Zentrale, abgesicherte Helfer für alle Windows-Aktionen.

Jede Funktion gibt ein Tupel (erfolg: bool, meldung: str) zurück, das die
GUI als Toast/Statusmeldung anzeigen kann (Erfolg blau, Warnung gelb,
Fehler lila). Kein Aufruf darf jemals eine unbehandelte Ausnahme werfen.

Hinweis: Diese Datei wird in Schritt 4 um weitere Aktionen (Papierkorb,
Autostart, Speicher freigeben, IP erneuern, usw.) erweitert. Aktuell
enthält sie die Basis-Helfer, die für die Beispiel-Kachel "Laufwerk C:"
benötigt werden.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Sequence, Union

# Unterdrückt das Aufpoppen eines Konsolenfensters bei externen
# Bordmittel-Aufrufen. Unter Nicht-Windows-Systemen (z. B. beim
# Entwickeln/Testen) existiert das Flag nicht - dann einfach 0 verwenden.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _ist_windows() -> bool:
    return sys.platform == "win32"


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


def open_settings(uri: str) -> tuple[bool, str]:
    """Öffnet einen Windows-Settings-Link (z. B. "ms-settings:network-status")."""
    try:
        os.startfile(uri)  # type: ignore[attr-defined]  # nur unter Windows vorhanden
        return True, "Einstellungen geöffnet."
    except Exception as fehler:
        return False, f"Einstellungen konnten nicht geöffnet werden: {fehler}"


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
