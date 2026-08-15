"""
hardware.py - Anbindung an LibreHardwareMonitor für CPU-/GPU-Temperatur.

Es werden ausschließlich die beiden Temperaturen benötigt (keine
Auslastung, kein VRAM, keine Lüfter). Die DLL wird beim ersten Zugriff
einmalig über pythonnet geladen. Schlägt irgendetwas fehl (DLL fehlt,
keine Admin-Rechte, kein passender Sensor, pythonnet nicht installiert),
liefern get_cpu_temp() / get_gpu_temp() schlicht None - die beiden
Temperatur-Kacheln zeigen dann "n/a" und laufen fehlerfrei weiter.

Der Grund eines fehlgeschlagenen Ladeversuchs wird in init_fehler()
festgehalten, damit selbsttest.py ihn anzeigen kann.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Pfad zur DLL: liegt im Projektordner unter lib/.
_PROJEKT_ORDNER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_ORDNER = os.path.join(_PROJEKT_ORDNER, "lib")
DLL_PFAD = os.path.join(LIB_ORDNER, "LibreHardwareMonitorLib.dll")

# Modulzustand: Computer-Objekt aus LibreHardwareMonitor (oder None).
_computer = None
_initialisierung_versucht = False
_init_fehler: Optional[str] = None


def _initialisieren() -> None:
    """Lädt die DLL und öffnet das Computer-Objekt - genau ein Versuch."""
    global _computer, _initialisierung_versucht, _init_fehler
    if _initialisierung_versucht:
        return
    _initialisierung_versucht = True

    if sys.platform != "win32":
        _init_fehler = "Nur unter Windows verfügbar."
        return
    if not os.path.isfile(DLL_PFAD):
        _init_fehler = f"DLL nicht gefunden: {DLL_PFAD}"
        return

    # 1) pythonnet laden.
    try:
        import clr
    except Exception as fehler:
        _init_fehler = f"pythonnet (clr) nicht ladbar: {fehler}"
        return

    # 2) Assembly referenzieren. clr.AddReference mit vollem Dateipfad
    #    funktioniert nicht in jeder pythonnet-Version - deshalb mehrere
    #    Strategien der Reihe nach versuchen.
    geladen = False
    lade_fehler: list[str] = []

    # Strategie A: Ordner in sys.path aufnehmen, per Assembly-Name laden
    # (der dokumentierte pythonnet-Weg).
    try:
        if LIB_ORDNER not in sys.path:
            sys.path.append(LIB_ORDNER)
        clr.AddReference("LibreHardwareMonitorLib")
        geladen = True
    except Exception as fehler:
        lade_fehler.append(f"per Name: {fehler}")

    # Strategie B: voller Dateipfad (klappt bei manchen Versionen).
    if not geladen:
        try:
            clr.AddReference(DLL_PFAD)
            geladen = True
        except Exception as fehler:
            lade_fehler.append(f"per Pfad: {fehler}")

    # Strategie C: direkt über die .NET-Klasse Assembly laden.
    if not geladen:
        try:
            from System.Reflection import Assembly  # type: ignore[import-not-found]

            Assembly.LoadFrom(DLL_PFAD)
            geladen = True
        except Exception as fehler:
            lade_fehler.append(f"per Assembly.LoadFrom: {fehler}")

    if not geladen:
        _init_fehler = "DLL-Laden fehlgeschlagen - " + " | ".join(lade_fehler)
        return

    # 3) Computer-Objekt öffnen (hier zeigen sich fehlende Adminrechte
    #    oder eine blockierte/inkompatible DLL).
    try:
        from LibreHardwareMonitor.Hardware import Computer  # type: ignore[import-not-found]

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.Open()
        _computer = computer
        _init_fehler = None
    except Exception as fehler:
        _init_fehler = (
            f"Computer.Open() fehlgeschlagen: {fehler} "
            "(DLL evtl. blockiert -> 'Unblock-File lib\\*.dll', "
            "oder App ohne Adminrechte gestartet)"
        )
        _computer = None


def _lese_temperatur(
    hardware_typen: tuple[str, ...], sensor_hinweise: tuple[str, ...]
) -> Optional[float]:
    """Liest den ersten passenden Temperatursensor der gewünschten Hardware.

    hardware_typen:  Namen der HardwareType-Enum-Werte (z. B. "Cpu").
    sensor_hinweise: Teilstrings des Sensornamens in Präferenz-Reihenfolge
                     (z. B. erst "Package", dann beliebig).
    """
    _initialisieren()
    if _computer is None:
        return None

    try:
        kandidaten: list[tuple[str, float]] = []
        for hardware in _computer.Hardware:
            if str(hardware.HardwareType) not in hardware_typen:
                continue
            hardware.Update()
            for sensor in hardware.Sensors:
                if str(sensor.SensorType) != "Temperature":
                    continue
                if sensor.Value is None:
                    continue
                kandidaten.append((str(sensor.Name), float(sensor.Value)))

        if not kandidaten:
            return None

        # Bevorzugten Sensor anhand der Namens-Hinweise wählen.
        for hinweis in sensor_hinweise:
            for name, wert in kandidaten:
                if hinweis.lower() in name.lower():
                    return wert
        # Kein bevorzugter Name gefunden: ersten Temperaturwert nehmen.
        return kandidaten[0][1]
    except Exception:
        return None


def get_cpu_temp() -> Optional[float]:
    """CPU-Package-Temperatur in °C, oder None wenn kein Sensor verfügbar."""
    return _lese_temperatur(("Cpu",), ("CPU Package", "Package", "Core (Tctl", "Core"))


def get_gpu_temp() -> Optional[float]:
    """GPU-Temperatur in °C, oder None wenn kein Sensor verfügbar."""
    return _lese_temperatur(
        ("GpuNvidia", "GpuAmd", "GpuIntel"),
        ("GPU Core", "Core", "Hot Spot"),
    )


def sensoren_verfuegbar() -> bool:
    """True, wenn die DLL geladen werden konnte."""
    _initialisieren()
    return _computer is not None


def init_fehler() -> Optional[str]:
    """Der Grund des letzten fehlgeschlagenen Ladeversuchs (für Diagnose)."""
    _initialisieren()
    return _init_fehler


def sensor_uebersicht() -> list[tuple[str, str, str]]:
    """Alle gefundenen Temperatursensoren als (Hardware, Sensor, Wert).

    Nur für die Diagnose in selbsttest.py - so sieht man, welche Sensoren
    LibreHardwareMonitor auf diesem Rechner überhaupt meldet.
    """
    _initialisieren()
    if _computer is None:
        return []
    ergebnis: list[tuple[str, str, str]] = []
    try:
        for hardware in _computer.Hardware:
            hardware.Update()
            for sensor in hardware.Sensors:
                if str(sensor.SensorType) != "Temperature":
                    continue
                wert = "—" if sensor.Value is None else f"{float(sensor.Value):.1f} °C"
                ergebnis.append(
                    (str(hardware.HardwareType), str(sensor.Name), wert)
                )
    except Exception:
        pass
    return ergebnis
