"""
icon_erzeugen.py - Erzeugt das Programmsymbol dashboard.ico.

Zeichnet das Logo der App (abgerundetes Quadrat mit Verlauf Blau -> Lila,
darin ein heller Ring wie bei den Gauge-Kacheln) und speichert es als
Windows-Icon in allen üblichen Größen.

Das fertige dashboard.ico liegt bereits im Repository - dieses Skript
wird nur gebraucht, wenn das Symbol geändert werden soll:

    pip install pillow
    python assets/icon_erzeugen.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

# Farben aus app/theme.py, damit Symbol und Oberfläche zusammenpassen.
ACCENT_BLUE = (59, 130, 246)
ACCENT_PURPLE = (168, 85, 247)
TEXT_BRIGHT = (232, 232, 240)

# Intern wird groß gezeichnet und am Ende verkleinert - das ergibt
# weiche Kanten ohne eigene Antialiasing-Logik.
KANTE = 1024
ICON_GROESSEN = [16, 24, 32, 48, 64, 128, 256]


def _verlauf_blau_lila(groesse: int) -> Image.Image:
    """Erzeugt einen diagonalen Farbverlauf von Blau nach Lila."""
    verlauf = Image.new("RGB", (groesse, groesse))
    zeichner = ImageDraw.Draw(verlauf)
    for x in range(groesse):
        anteil = x / max(1, groesse - 1)
        farbe = tuple(
            round(ACCENT_BLUE[i] + (ACCENT_PURPLE[i] - ACCENT_BLUE[i]) * anteil)
            for i in range(3)
        )
        zeichner.line([(x, 0), (x, groesse)], fill=farbe)
    return verlauf


def _abgerundete_maske(groesse: int, radius_anteil: float = 0.22) -> Image.Image:
    """Maske für ein abgerundetes Quadrat (wie die Kacheln der App)."""
    maske = Image.new("L", (groesse, groesse), 0)
    ImageDraw.Draw(maske).rounded_rectangle(
        [(0, 0), (groesse - 1, groesse - 1)],
        radius=int(groesse * radius_anteil),
        fill=255,
    )
    return maske


def symbol_zeichnen(kante: int = KANTE) -> Image.Image:
    """Zeichnet das komplette Symbol als RGBA-Bild."""
    # 1. Abgerundete Kachel mit Farbverlauf als Grundfläche.
    symbol = Image.new("RGBA", (kante, kante), (0, 0, 0, 0))
    symbol.paste(_verlauf_blau_lila(kante), (0, 0), _abgerundete_maske(kante))

    # 2. Heller Ring in der Mitte - das Erkennungsmerkmal der Gauge-Kacheln.
    zeichner = ImageDraw.Draw(symbol)
    rand = kante * 0.27
    dicke = int(kante * 0.085)
    kasten = [(rand, rand), (kante - rand, kante - rand)]
    # Bei -90° (oben) beginnen und wie im Dashboard im Uhrzeigersinn laufen.
    zeichner.arc(kasten, start=-90, end=200, fill=TEXT_BRIGHT + (255,), width=dicke)

    return symbol


def main() -> None:
    ordner = os.path.dirname(os.path.abspath(__file__))
    ziel = os.path.join(ordner, "dashboard.ico")

    symbol = symbol_zeichnen()
    # Pillow verkleinert beim Speichern selbst auf alle gewünschten Größen.
    symbol.save(ziel, format="ICO", sizes=[(g, g) for g in ICON_GROESSEN])
    print(f"Symbol geschrieben: {ziel}")


if __name__ == "__main__":
    main()
