"""
CircularGauge: runder Ring-Anzeiger auf Basis eines CTkCanvas.

Zeichnet einen grauen Voll-Track sowie einen farbigen Wertbogen, der bei
-90° (oben) beginnt und im Uhrzeigersinn bis zum Prozentwert läuft. Neben
dem Ring stehen ein großer Wert und zwei kleine Meta-Zeilen.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

from .. import theme


class CircularGauge(ctk.CTkFrame):
    """Zusammengesetztes Widget: Ring (Canvas) + Wertetext + Meta-Zeilen."""

    def __init__(
        self,
        master,
        size: int = 78,
        thickness: int = 8,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._size = size
        self._thickness = thickness

        # Äußerer Container: Ring links, Texte rechts daneben
        self._reihe = ctk.CTkFrame(self, fg_color="transparent")
        self._reihe.pack(expand=True)

        # Canvas für den Ring. Hintergrund muss zur Kachel-Farbe passen,
        # da CTkCanvas keine echte Transparenz kennt.
        self._canvas = tk.Canvas(
            self._reihe,
            width=size,
            height=size,
            highlightthickness=0,
            bg=theme.CARD_BG,
        )
        self._canvas.pack(side="left", padx=(0, 10))

        # Textblock rechts vom Ring: großer Wert + zwei Meta-Zeilen
        self._textblock = ctk.CTkFrame(self._reihe, fg_color="transparent")
        self._textblock.pack(side="left", anchor="w")

        self._wert_label = ctk.CTkLabel(
            self._textblock,
            text="—",
            font=(theme.FONT_FAMILY_MONO, theme.FONT_SIZE_VALUE_MEDIUM, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        )
        self._wert_label.pack(anchor="w")

        self._meta_oben_label = ctk.CTkLabel(
            self._textblock,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._meta_oben_label.pack(anchor="w")

        self._meta_unten_label = ctk.CTkLabel(
            self._textblock,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._meta_unten_label.pack(anchor="w")

        self._track_id: Optional[int] = None
        self._bogen_id: Optional[int] = None
        self._zeichne_grundgeruest()

    def _zeichne_grundgeruest(self) -> None:
        """Zeichnet den grauen Track-Kreis einmalig."""
        rand = self._thickness / 2 + 2
        koordinaten = (rand, rand, self._size - rand, self._size - rand)
        self._track_id = self._canvas.create_arc(
            *koordinaten,
            start=0,
            extent=359.999,
            style=tk.ARC,
            outline=theme.TRACK_GRAY,
            width=self._thickness,
        )
        self._bogen_id = self._canvas.create_arc(
            *koordinaten,
            start=90,
            extent=0,
            style=tk.ARC,
            outline=theme.ACCENT_BLUE,
            width=self._thickness,
        )

    def set_value(
        self,
        percent: Optional[float],
        wert_text: str,
        meta_oben: str = "",
        meta_unten: str = "",
        farbe: Optional[str] = None,
        na: bool = False,
    ) -> None:
        """Aktualisiert Ring, Wert und Meta-Zeilen ohne Widgets neu zu bauen.

        Bei na=True (kein Sensor vorhanden) wird der Ring grau und leer
        dargestellt, der Wert zeigt "n/a".
        """
        try:
            # Nur bei tatsächlicher Änderung neu zeichnen - sonst "blitzen"
            # die Zahlen bei jedem GUI-Tick, obwohl sich nichts geändert hat.
            stand = (
                na,
                None if percent is None else round(float(percent), 1),
                wert_text,
                meta_oben,
                meta_unten,
                farbe,
            )
            if stand == getattr(self, "_letzter_stand", None):
                return
            self._letzter_stand = stand
            if na or percent is None:
                if self._bogen_id is not None:
                    self._canvas.itemconfigure(self._bogen_id, extent=0)
                self._wert_label.configure(text="n/a", text_color=theme.TEXT_DIM)
            else:
                prozent = max(0.0, min(100.0, float(percent)))
                extent = -(prozent / 100.0) * 360.0
                ringfarbe = farbe or theme.status_color(prozent)
                if self._bogen_id is not None:
                    self._canvas.itemconfigure(
                        self._bogen_id, extent=extent, outline=ringfarbe
                    )
                self._wert_label.configure(text=wert_text, text_color=theme.TEXT_BRIGHT)

            self._meta_oben_label.configure(text=meta_oben)
            self._meta_unten_label.configure(text=meta_unten)
        except Exception:
            # Eine Kachel darf nie wegen eines Zeichenfehlers abstürzen.
            pass
