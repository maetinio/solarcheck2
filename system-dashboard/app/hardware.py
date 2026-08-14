"""
hardware.py - Anbindung an LibreHardwareMonitor für CPU-/GPU-Temperatur.

Es werden ausschließlich die beiden Temperaturen benötigt (keine
Auslastung, kein VRAM, keine Lüfter). Die DLL wird beim ersten Zugriff
einmalig über pythonnet geladen. Schlägt irgendetwas fehl (DLL fehlt,
keine Admin-Rechte, kein passender Sensor, pythonnet nicht installiert),
liefern get_cpu_temp() / get_gpu_temp() schlicht None - die beiden
Temperatur-Kacheln zeigen dann "n/a" und laufen fehlerfrei weiter.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Pfad zur DLL: liegt im Projektordner unter lib/.
_PROJEKT_ORDNER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL_PFAD = os.path.join(_PROJEKT_ORDNER, "lib", "LibreHardwareMonitorLib.dll")

# Modulzustand: Computer-Objekt aus LibreHardwareMonitor (oder None).
_computer = None
_initialisierung_versucht = False


def _initialisieren() -> None:
    """Lädt die DLL und öffnet das Computer-Objekt - genau ein Versuch."""
    global _computer, _initialisierung_versucht
    if _initialisierung_versucht:
        return
    _initialisierung_versucht = True

    if sys.platform != "win32" or not os.path.isfile(DLL_PFAD):
        return

    try:
        import clr  # pythonnet

        clr.AddReference(DLL_PFAD)
        from LibreHardwareMonitor.Hardware import Computer  # type: ignore[import-not-found]

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.Open()
        _computer = computer
    except Exception:
        # Bewusst still: ohne Sensor-Anbindung laufen die Kacheln als "n/a".
        _computer = None


def _lese_temperatur(hardware_typen: tuple[str, ...], sensor_hinweise: tuple[str, ...]) -> Optional[float]:
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
