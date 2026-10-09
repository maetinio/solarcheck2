"""
Zentrales Design-System des System-Dashboards.

Enthält alle Farbkonstanten, Schriftgrößen/-familien sowie die zwei
zentralen Helferfunktionen zur Bestimmung der Statusfarbe (Auslastung /
Temperatur). Alle anderen Module importieren ihre Farben ausschließlich
von hier, damit das Farbschema an genau einer Stelle gepflegt wird.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Basisfarben
# ---------------------------------------------------------------------------

BG_DARK = "#0D0D14"            # Fenster-Hintergrund (Schwarz)
CARD_BG = "#1A1A26"            # Kachel-Karte (oberer Verlaufspunkt)
CARD_BG_GRADIENT_END = "#15151F"  # Kachel-Karte (unterer Verlaufspunkt)
CARD_BORDER = "#2A2A3C"        # Kachel-Rahmen

# Akzentfarben
ACCENT_BLUE = "#3B82F6"        # Standard-Aktion, niedrige Auslastung
ACCENT_PURPLE = "#A855F7"      # Titel-Highlights, System/Netzwerk, hohe Auslastung
ACCENT_YELLOW = "#FACC15"      # Warnungen, mittlere Auslastung, Admin-Schild

# Textfarben
TEXT_BRIGHT = "#E8E8F0"        # Haupttext
TEXT_MUTED = "#9A9AB0"         # Gedämpfter Text (Untertitel, Meta)
TEXT_DIM = "#6A6A80"           # Sehr dezenter Text

# Abgeleitete Hilfsfarben (Rahmen/Hover), zentral statt verstreut definiert
CARD_BORDER_HOVER = "#3B3B52"
TRACK_GRAY = "#33334A"         # Grauer Gauge-Track
DISABLED_GRAY = "#4A4A5C"      # Für "n/a"-Ringe / deaktivierte Buttons

ICON_BG_TINT = "#241C36"       # Lila getönter Hintergrund fürs Kachel-Icon-Quadrat

# Button-Stile (primäre Aktion vs. dezente Aktion)
BUTTON_PRIMARY_BG = "#1C2E4F"
BUTTON_PRIMARY_BORDER = ACCENT_BLUE
BUTTON_PRIMARY_HOVER = "#25406E"

BUTTON_SECONDARY_BG = "#1E1E2C"
BUTTON_SECONDARY_BORDER = "#3A3A4E"
BUTTON_SECONDARY_HOVER_BORDER = ACCENT_BLUE

# ---------------------------------------------------------------------------
# Typografie
# ---------------------------------------------------------------------------

FONT_FAMILY_UI = "Segoe UI Semibold"     # Titel/Überschriften
FONT_FAMILY_UI_REGULAR = "Segoe UI"      # Fließtext / Untertitel
FONT_FAMILY_MONO = "Consolas"            # Zahlenwerte (Gauges, große Stats)

FONT_SIZE_TITLE = 14
FONT_SIZE_LABEL = 11
FONT_SIZE_VALUE_LARGE = 30
FONT_SIZE_VALUE_MEDIUM = 20

# ---------------------------------------------------------------------------
# Statusfarben-Logik
# ---------------------------------------------------------------------------


def status_color(percent: float) -> str:
    """Liefert die Akzentfarbe passend zu einem Auslastungs-Prozentwert.

    < 70 % -> Blau, 70-90 % -> Gelb, > 90 % -> Lila.
    """
    try:
        wert = float(percent)
    except (TypeError, ValueError):
        return ACCENT_BLUE

    if wert > 90:
        return ACCENT_PURPLE
    if wert >= 70:
        return ACCENT_YELLOW
    return ACCENT_BLUE


def temp_color(celsius: float | None, warn_schwelle: float = 80.0) -> str:
    """Liefert die Akzentfarbe passend zu einer Temperatur in °C.

    < 60 °C -> Blau, 60-80 °C -> Gelb, > 80 °C -> Lila.
    Die obere Warnschwelle ist konfigurierbar (Kachel "Warnschwelle"-Dialog).
    Ist kein Wert vorhanden (Sensor fehlt), wird Grau (deaktiviert) geliefert.
    """
    if celsius is None:
        return DISABLED_GRAY

    try:
        wert = float(celsius)
    except (TypeError, ValueError):
        return DISABLED_GRAY

    untere_schwelle = min(60.0, warn_schwelle * 0.75)
    if wert > warn_schwelle:
        return ACCENT_PURPLE
    if wert >= untere_schwelle:
        return ACCENT_YELLOW
    return ACCENT_BLUE
