"""
Meter: waagerechter Balken-Anzeiger auf Basis von CTkProgressBar.

Zeigt einen Fortschrittsbalken (Farbe nach Status) und darunter eine
Zeile "belegt (groß) · frei (klein)". Wird für Laufwerke, weitere
Laufwerke (kompakte Variante) und RAM verwendet.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from .. import theme


class Meter(ctk.CTkFrame):
    """Balken-Meter mit Beschriftungszeile."""

    def __init__(self, master, kompakt: bool = False, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._kompakt = kompakt
        balken_hoehe = 8 if kompakt else 12

        self._titel_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        if kompakt:
            self._titel_label.pack(fill="x", pady=(0, 2))

        self._balken = ctk.CTkProgressBar(
            self,
            height=balken_hoehe,
            corner_radius=balken_hoehe // 2,
            fg_color=theme.TRACK_GRAY,
            progress_color=theme.ACCENT_BLUE,
        )
        self._balken.pack(fill="x", pady=(0, 6) if not kompakt else (0, 4))
        self._balken.set(0)

        self._beschriftung_label = ctk.CTkLabel(
            self,
            text="—",
            font=(
                theme.FONT_FAMILY_MONO,
                theme.FONT_SIZE_LABEL if kompakt else theme.FONT_SIZE_VALUE_MEDIUM,
                "bold",
            ),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        )
        self._beschriftung_label.pack(fill="x")

    def set_titel(self, text: str) -> None:
        """Setzt die kleine Titelzeile über dem Balken (kompakte Variante)."""
        try:
            self._titel_label.configure(text=text)
        except Exception:
            pass

    def set_value(
        self,
        percent: Optional[float],
        belegt_text: str,
        frei_text: str = "",
        farbe: Optional[str] = None,
    ) -> None:
        """Aktualisiert Balkenstand und Beschriftung ohne Neuaufbau."""
        try:
            prozent = 0.0 if percent is None else max(0.0, min(100.0, float(percent)))
            self._balken.set(prozent / 100.0)
            self._balken.configure(progress_color=farbe or theme.status_color(prozent))

            if frei_text:
                text = f"{belegt_text} · {frei_text}"
            else:
                text = belegt_text
            self._beschriftung_label.configure(text=text)
        except Exception:
            # Eine Kachel darf nie wegen eines Anzeigefehlers abstürzen.
            pass
