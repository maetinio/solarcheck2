"""
system_info.py - Zentrale Sammelstelle für ALLE Datenabfragen.

Jede Funktion ist einzeln gegen Fehler abgesichert und liefert im
Fehlerfall None bzw. ein leeres Ergebnis, statt eine Ausnahme nach oben
zu werfen. So kann eine einzelne fehlschlagende Abfrage niemals eine
ganze Kachel oder die App zum Absturz bringen.

Hinweis: Diese Datei wird in Schritt 4 um die Datenquellen für die
übrigen 11 Kacheln (RAM, CPU, Netzwerk, Autostart, Papierkorb, Temp,
Windows-Update, System, Akku) erweitert. Aktuell enthält sie die
Laufwerks-Abfrage für die erste funktionierende Beispiel-Kachel.
"""

from __future__ import annotations

from typing import Optional, TypedDict

import psutil


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


def snapshot() -> dict:
    """Erfasst einen Momentaufnahme-Satz aller aktuell verfügbaren Werte.

    Wird vom Hintergrund-Thread in dashboard.py alle ~2 Sekunden
    aufgerufen. Wächst in Schritt 4 um die weiteren Kacheln-Daten.
    """
    ergebnis: dict = {}
    ergebnis["disk_c"] = disk_usage("C:\\")
    return ergebnis
