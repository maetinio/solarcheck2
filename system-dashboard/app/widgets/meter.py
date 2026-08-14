"""
Meter: waagerechter Balken-Anzeiger auf Basis von CTkProgressBar.

Zwei Ausprägungen:
- Normal (kompakt=False): Balken, darunter der belegte Wert groß und der
  freie Platz klein darunter. Für Laufwerk C: und Arbeitsspeicher.
- Kompakt (kompakt=True): eine einzige Infozeile über einem dünnen
  Balken. Für die Kachel "Weitere Laufwerke", in der zwei Balken
  übereinander Platz finden müssen.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from .. import theme


class Meter(ctk.CTkFrame):
    """Balken-Meter mit Beschriftung."""

    def __init__(self, master, kompakt: bool = False, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._kompakt = kompakt
        self._titel_prefix = ""
        balken_hoehe = 8 if kompakt else 12

        # Infozeile - in der kompakten Variante steht hier alles drin.
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
        self._balken.pack(fill="x", pady=(0, 6) if not kompakt else (0, 0))
        self._balken.set(0)

        # Nur in der normalen Variante: belegt groß, frei klein darunter.
        self._beschriftung_label = ctk.CTkLabel(
            self,
            text="—",
            font=(theme.FONT_FAMILY_MONO, 17, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        )
        self._frei_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        if not kompakt:
            self._beschriftung_label.pack(fill="x")
            self._frei_label.pack(fill="x")

    def set_titel(self, text: str) -> None:
        """Setzt den festen Teil der Infozeile (kompakte Variante, z. B. "D:")."""
        try:
            self._titel_prefix = text
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

            if self._kompakt:
                # Alles in eine Zeile: "D:  ·  62 %  ·  120 GB frei"
                teile = [self._titel_prefix, belegt_text, frei_text]
                self._titel_label.configure(
                    text="  ·  ".join(teil for teil in teile if teil)
                )
            else:
                self._beschriftung_label.configure(text=belegt_text)
                self._frei_label.configure(text=frei_text)
        except Exception:
            pass
